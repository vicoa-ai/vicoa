"""`spawn-session` RPC with the `worktree` param — create, spawn-in, rollback.

The worktree is created for real against a temp git repo; only the agent
launch (`subprocess.Popen` + monitor + install check) is stubbed, so the
worktree lifecycle — including rollback on a failed launch — is exercised end
to end.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from vicoa.machine_daemon import MachineDaemon


class _FakeProc:
    pid = 4321

    def poll(self) -> None:
        return None


@pytest.fixture
def committed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "src" / "my-app"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    for k, v in (
        ("user.email", "t@e.com"),
        ("user.name", "T"),
        ("commit.gpgsign", "false"),
    ):
        subprocess.run(["git", "-C", str(repo), "config", k, v], check=True)
    (repo / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "-C", str(repo), "add", "seed.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True)
    return repo


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    return h


def _prep_daemon(monkeypatch: pytest.MonkeyPatch) -> MachineDaemon:
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    monkeypatch.setattr(daemon, "send_heartbeat", lambda: None)
    monkeypatch.setattr(daemon, "_check_agent_installation", lambda agent: None)
    monkeypatch.setattr(daemon, "_build_headless_command", lambda **kw: ["true"])
    monkeypatch.setattr(daemon, "_monitor_session_process", lambda **kw: None)
    return daemon


def _patch_popen(monkeypatch: pytest.MonkeyPatch, calls: dict, *, fail: bool = False):
    real_popen = subprocess.Popen

    def fake_popen(command, *args, **kw):
        # Only intercept the daemon's agent launch (it alone passes
        # start_new_session=True). git's subprocess.run calls also route
        # through Popen and must reach the real implementation.
        if not kw.get("start_new_session"):
            return real_popen(command, *args, **kw)
        calls["called"] = True
        calls["cwd"] = kw.get("cwd")
        if fail:
            raise OSError("simulated launch failure")
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)


def test_spawn_with_new_worktree_creates_and_spawns_in_it(
    monkeypatch: pytest.MonkeyPatch, home: Path, committed_repo: Path
):
    daemon = _prep_daemon(monkeypatch)
    calls: dict = {}
    _patch_popen(monkeypatch, calls)

    result = daemon.spawn_session_rpc(
        {
            "params": {
                "directory": str(committed_repo),
                "agent": "claude",
                "worktree": {"new": True},
            }
        }
    )

    assert "agent_instance_id" in result
    assert "error" not in result
    # The result surfaces the new worktree for immediate display...
    assert "worktree_path" in result and "branch" in result
    # ...the agent is launched IN the worktree, not the base repo...
    assert calls["cwd"] == result["worktree_path"]
    assert calls["cwd"] != str(committed_repo)
    # ...and the worktree exists under the managed root.
    assert Path(result["worktree_path"]).is_dir()


def test_spawn_new_worktree_surfaces_setup_commands(
    monkeypatch: pytest.MonkeyPatch, home: Path, committed_repo: Path
):
    import json

    # Config in the source repo working tree (need not be committed) — the client
    # runs these, visibly, in the new session's terminal.
    (committed_repo / "vicoa.json").write_text(
        json.dumps({"worktree": {"setup": ["npm ci", "npm run build"]}})
    )
    daemon = _prep_daemon(monkeypatch)
    _patch_popen(monkeypatch, {})

    result = daemon.spawn_session_rpc(
        {
            "params": {
                "directory": str(committed_repo),
                "agent": "claude",
                "worktree": {"new": True},
            }
        }
    )

    assert result.get("setup_commands") == ["npm ci", "npm run build"]
    # Untrusted by default — the web asks before auto-running a cloned repo's setup.
    assert result.get("setup_trusted") is False


def test_spawn_new_worktree_setup_trusted_after_grant(
    monkeypatch: pytest.MonkeyPatch, home: Path, committed_repo: Path
):
    import json

    from vicoa.rpc.worktree_trust import grant_repo_trust

    (committed_repo / "vicoa.json").write_text(
        json.dumps({"worktree": {"setup": ["npm ci"]}})
    )
    grant_repo_trust(str(committed_repo))
    daemon = _prep_daemon(monkeypatch)
    _patch_popen(monkeypatch, {})

    result = daemon.spawn_session_rpc(
        {
            "params": {
                "directory": str(committed_repo),
                "agent": "claude",
                "worktree": {"new": True},
            }
        }
    )

    assert result.get("setup_commands") == ["npm ci"]
    assert result.get("setup_trusted") is True


def test_spawn_new_worktree_without_config_has_no_setup_commands(
    monkeypatch: pytest.MonkeyPatch, home: Path, committed_repo: Path
):
    daemon = _prep_daemon(monkeypatch)
    _patch_popen(monkeypatch, {})

    result = daemon.spawn_session_rpc(
        {
            "params": {
                "directory": str(committed_repo),
                "agent": "claude",
                "worktree": {"new": True},
            }
        }
    )

    assert "worktree_path" in result
    assert "setup_commands" not in result


def test_spawn_without_worktree_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, home: Path, committed_repo: Path
):
    daemon = _prep_daemon(monkeypatch)
    calls: dict = {}
    _patch_popen(monkeypatch, calls)

    result = daemon.spawn_session_rpc(
        {"params": {"directory": str(committed_repo), "agent": "claude"}}
    )

    assert "agent_instance_id" in result
    assert "worktree_path" not in result
    assert "branch" not in result
    assert calls["cwd"] == str(committed_repo)


def test_spawn_failure_rolls_back_the_worktree(
    monkeypatch: pytest.MonkeyPatch, home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import list_worktrees

    daemon = _prep_daemon(monkeypatch)
    calls: dict = {}
    _patch_popen(monkeypatch, calls, fail=True)

    result = daemon.spawn_session_rpc(
        {
            "params": {
                "directory": str(committed_repo),
                "agent": "claude",
                "worktree": {"new": True},
            }
        }
    )

    assert "error" in result
    # No orphan worktree left behind — the daemon rolled it back.
    assert list_worktrees(str(committed_repo))["worktrees"] == []


def test_spawn_worktree_on_non_repo_errors_without_launching(
    monkeypatch: pytest.MonkeyPatch, home: Path, tmp_path: Path
):
    daemon = _prep_daemon(monkeypatch)
    calls: dict = {}
    _patch_popen(monkeypatch, calls)

    plain = tmp_path / "plain"
    plain.mkdir()

    result = daemon.spawn_session_rpc(
        {
            "params": {
                "directory": str(plain),
                "agent": "claude",
                "worktree": {"new": True},
            }
        }
    )

    assert "error" in result
    assert calls.get("called") is not True  # never tried to launch the agent
