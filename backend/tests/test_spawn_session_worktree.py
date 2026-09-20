"""`spawn-session` RPC with the `worktree` param — create, spawn-in, rollback.

The worktree is created for real against a temp git repo; only the agent
launch (`subprocess.Popen` + monitor + install check) is stubbed, so the
worktree lifecycle — including rollback on a failed launch — is exercised end
to end.
"""

from __future__ import annotations

import os
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
    # The stubbed child never registers; these tests are about the worktree
    # side of the spawn, so treat registration as instant.
    monkeypatch.setattr(
        daemon, "_wait_for_registration", lambda session_id, process, **kw: None
    )
    return daemon


def _patch_popen(monkeypatch: pytest.MonkeyPatch, calls: dict, *, fail: bool = False):
    real_popen = subprocess.Popen

    def fake_popen(command, *args, **kw):
        # Only intercept the daemon's agent launch: it alone detaches stdio to
        # DEVNULL in its own session. git's subprocess.run calls, and the setup
        # engine's `bash -lc` children (own session too, but piped stdout), must
        # reach the real implementation.
        if (
            not kw.get("start_new_session")
            or kw.get("stdout") is not subprocess.DEVNULL
        ):
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


def test_spawn_new_worktree_untrusted_hands_setup_to_the_client(
    monkeypatch: pytest.MonkeyPatch, home: Path, committed_repo: Path
):
    import json

    # Config in the source repo working tree (need not be committed). The repo
    # is untrusted, so the daemon must NOT run it — the client confirms first.
    marker = committed_repo / "must_not_run"
    (committed_repo / "vicoa.json").write_text(
        json.dumps({"worktree": {"setup": [f"touch {marker}", "npm run build"]}})
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

    # Contract: `setup_commands` present ⇔ the daemon did not run them. An old
    # web shows its confirm and types these into the terminal itself.
    assert result.get("setup_commands") == [f"touch {marker}", "npm run build"]
    assert result.get("setup_trusted") is False
    assert result.get("worktree_setup") == {
        "status": "untrusted",
        "total": 2,
        "worktree_path": result["worktree_path"],
    }
    # The client exports these before typing setup into the terminal (that shell
    # doesn't inherit the hook env the engine sets in its own subprocess).
    setup_env = result.get("setup_env")
    assert isinstance(setup_env, dict)
    assert setup_env["VICOA_ROOT_PATH"] == str(committed_repo)
    assert setup_env["VICOA_WORKTREE_PATH"] == result["worktree_path"]
    assert setup_env["VICOA_BRANCH_NAME"] == result["branch"]
    assert not marker.exists()


@pytest.mark.skipif(os.name == "nt", reason="setup engine assumes bash")
def test_spawn_new_worktree_trusted_runs_setup_on_the_daemon(
    monkeypatch: pytest.MonkeyPatch, home: Path, committed_repo: Path
):
    import json
    import time

    from vicoa.rpc.worktree_trust import grant_repo_trust

    # Marker outside the worktree so it survives; the command also proves the
    # hook env reaches the daemon-run shell.
    marker = committed_repo / "daemon_setup_ran"
    (committed_repo / "vicoa.json").write_text(
        json.dumps(
            {"worktree": {"setup": [f'echo "$VICOA_BRANCH_NAME" > {marker}', "true"]}}
        )
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

    # The daemon ran it, so nothing is handed to the client to run (an old web
    # would otherwise type them into its terminal → two runs).
    assert "setup_commands" not in result
    assert "setup_env" not in result
    assert result.get("worktree_setup") == {
        "status": "running",
        "total": 2,
        "worktree_path": result["worktree_path"],
    }
    # Background thread — poll for the effect, then for the recorded outcome.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = daemon._handle_rpc_request(
            {
                "method": "worktree-setup-status",
                "params": {"worktree_path": result["worktree_path"]},
            }
        )
        if status.get("status") in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert marker.read_text().strip() == result["branch"]
    assert status["status"] == "succeeded"
    assert [c["status"] for c in status["commands"]] == ["ok", "ok"]
    assert status["source_repo"] == str(committed_repo)


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


def test_spawn_with_named_worktree_uses_the_name(
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
                "worktree": {"new": True, "name": "feat-login"},
            }
        }
    )

    assert "agent_instance_id" in result
    assert result["branch"] == "feat-login"
    assert Path(result["worktree_path"]).parent.name == "feat-login"
    assert calls["cwd"] == result["worktree_path"]


def test_spawn_with_taken_worktree_name_errors_without_launching(
    monkeypatch: pytest.MonkeyPatch, home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import create_worktree

    create_worktree(str(committed_repo), name="feat-login")
    daemon = _prep_daemon(monkeypatch)
    calls: dict = {}
    _patch_popen(monkeypatch, calls)

    result = daemon.spawn_session_rpc(
        {
            "params": {
                "directory": str(committed_repo),
                "agent": "claude",
                "worktree": {"new": True, "name": "feat-login"},
            }
        }
    )

    assert result["error"].endswith("name_taken")
    assert calls.get("called") is not True


def test_spawn_with_blank_or_non_string_name_falls_back_to_random(
    monkeypatch: pytest.MonkeyPatch, home: Path, committed_repo: Path
):
    daemon = _prep_daemon(monkeypatch)
    _patch_popen(monkeypatch, {})

    for name in ("", "  ", None, 42):
        result = daemon.spawn_session_rpc(
            {
                "params": {
                    "directory": str(committed_repo),
                    "agent": "claude",
                    "worktree": {"new": True, "name": name},
                }
            }
        )
        assert "agent_instance_id" in result, (name, result)
        assert result["branch"].strip(), name


def test_spawn_new_worktree_from_a_subfolder_starts_at_the_same_subfolder(
    monkeypatch: pytest.MonkeyPatch, home: Path, committed_repo: Path
):
    """`directory` may be a subfolder of the repo: the worktree forks the
    whole repo and the agent starts at that subfolder inside the new checkout.
    `repo_root` in the result names the checkout the worktree was forked
    from, so the server files the project's folder — not the worktree — as
    the recent directory."""
    subdir = committed_repo / "apps" / "web"
    subdir.mkdir(parents=True)
    (subdir / "index.txt").write_text("x\n")
    subprocess.run(["git", "-C", str(committed_repo), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(committed_repo), "commit", "-q", "-m", "subdir"], check=True
    )
    daemon = _prep_daemon(monkeypatch)
    calls: dict = {}
    _patch_popen(monkeypatch, calls)

    result = daemon.spawn_session_rpc(
        {
            "params": {
                "directory": str(subdir),
                "agent": "claude",
                "worktree": {"new": True},
            }
        }
    )

    assert "error" not in result, result
    worktree = Path(result["worktree_path"])
    assert worktree.name == committed_repo.name
    assert Path(calls["cwd"]).resolve() == (worktree / "apps" / "web").resolve()
    assert (worktree / "apps" / "web" / "index.txt").is_file()
    assert Path(result["repo_root"]).expanduser().resolve() == committed_repo.resolve()


def test_spawn_without_worktree_reports_the_repo_root(
    monkeypatch: pytest.MonkeyPatch, home: Path, committed_repo: Path
):
    subdir = committed_repo / "apps"
    subdir.mkdir()
    daemon = _prep_daemon(monkeypatch)
    calls: dict = {}
    _patch_popen(monkeypatch, calls)

    result = daemon.spawn_session_rpc(
        {"params": {"directory": str(subdir), "agent": "claude"}}
    )

    assert "error" not in result, result
    assert Path(calls["cwd"]).resolve() == subdir.resolve()
    assert Path(result["repo_root"]).expanduser().resolve() == committed_repo.resolve()
