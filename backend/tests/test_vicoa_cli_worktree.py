"""`vicoa worktree setup` — the terminal entry point for a worktree's setup.

Runs the real engine (bash) against a temp repo + a real linked worktree; only
HOME is redirected so the trust store and run records stay hermetic. Skipped on
Windows like the engine tests.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from vicoa.commands.worktree import add_worktree_subparser, run_worktree_command
from vicoa.rpc import worktree_setup as ws
from vicoa.rpc.worktree_trust import is_repo_trusted

pytestmark = pytest.mark.skipif(os.name == "nt", reason="engine tests assume bash")


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    return h


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "src" / "app"
    r.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    for k, v in (
        ("user.email", "t@e.com"),
        ("user.name", "T"),
        ("commit.gpgsign", "false"),
    ):
        subprocess.run(["git", "-C", str(r), "config", k, v], check=True)
    (r / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "-C", str(r), "add", "seed.txt"], check=True)
    subprocess.run(["git", "-C", str(r), "commit", "-q", "-m", "seed"], check=True)
    return r


@pytest.fixture
def worktree(repo: Path, home: Path) -> Path:
    from vicoa.rpc.worktree_ops import create_worktree

    created = create_worktree(str(repo))
    assert "error" not in created, created
    return Path(created["path"])


def _config(repo: Path, commands: list[str]) -> None:
    (repo / ".vicoa").mkdir(exist_ok=True)
    (repo / ".vicoa" / "config.json").write_text(
        json.dumps({"worktree": {"setup": commands}})
    )


def _run(*argv: str) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    add_worktree_subparser(sub)
    args = parser.parse_args(["worktree", *argv])
    return run_worktree_command(args)


def test_setup_runs_the_source_repo_config_in_the_worktree(
    repo: Path, worktree: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Config lives in the SOURCE repo; the worktree is a fresh checkout of the
    # seed commit and has no .vicoa/ at all.
    marker = repo / "ran"
    _config(
        repo,
        [
            "echo hello-from-setup",
            f'printf "%s|%s|%s" "$PWD" "$VICOA_ROOT_PATH" "$VICOA_BRANCH_NAME" > {marker}',
        ],
    )
    assert not (worktree / ".vicoa").exists()

    code = _run("setup", str(worktree))

    assert code == 0
    out = capsys.readouterr().out
    assert "$ echo hello-from-setup" in out
    assert "hello-from-setup" in out
    assert "Setup done: 2 commands" in out
    # Untrusted repo → the hint about --trust, but the run itself was not gated.
    assert "--trust" in out
    cwd, root, branch = marker.read_text().split("|")
    assert Path(cwd).resolve() == worktree.resolve()
    assert Path(root).resolve() == repo.resolve()
    # Managed layout is <project>-worktrees/<branch>/<project>: the branch is the
    # middle directory, and what git reports for the checkout.
    assert branch == worktree.parent.name
    assert branch == ws.current_branch(str(worktree))
    # Same run record the daemon writes → the dashboard badge sees this run.
    status = ws.read_setup_status(str(worktree))
    assert status["status"] == "succeeded"
    assert [c["status"] for c in status["commands"]] == ["ok", "ok"]
    assert Path(status["source_repo"]).resolve() == repo.resolve()


def test_setup_from_a_subfolder_resolves_the_worktree_root(
    repo: Path, worktree: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (worktree / "apps" / "web").mkdir(parents=True)
    _config(repo, ['printf "%s" "$PWD" > ran-at'])

    assert _run("setup", str(worktree / "apps" / "web")) == 0

    assert Path((worktree / "ran-at").read_text()).resolve() == worktree.resolve()
    assert f"Worktree: {worktree.resolve()}" in capsys.readouterr().out


def test_failure_stops_and_returns_the_exit_code(
    repo: Path, worktree: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _config(repo, ["echo first", "exit 3", "touch never"])

    code = _run("setup", str(worktree))

    assert code == 3
    captured = capsys.readouterr()
    assert "→ exit 3" in captured.out
    assert "Setup failed at step 2/3: exit 3" in captured.err
    assert not (worktree / "never").exists()
    status = ws.read_setup_status(str(worktree))
    assert status["status"] == "failed"
    assert [c["status"] for c in status["commands"]] == ["ok", "failed", "pending"]


def test_dry_run_lists_without_running_or_recording(
    repo: Path, worktree: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _config(repo, ["touch should_not_exist", "echo two"])

    assert _run("setup", str(worktree), "--dry-run") == 0

    out = capsys.readouterr().out
    assert "1. touch should_not_exist" in out
    assert "2. echo two" in out
    assert not (worktree / "should_not_exist").exists()
    assert ws.read_setup_status(str(worktree)) == {"status": "none"}


def test_trust_flag_grants_trust_for_the_source_repo(
    repo: Path, worktree: Path, home: Path
) -> None:
    _config(repo, ["true"])
    assert not is_repo_trusted(str(repo))

    assert _run("setup", str(worktree), "--trust") == 0

    assert is_repo_trusted(str(repo))
    assert not is_repo_trusted(str(worktree))  # trust keys on the source, not the copy


def test_main_checkout_is_its_own_source(
    repo: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _config(repo, ['printf "%s" "$VICOA_ROOT_PATH" > root'])

    assert _run("setup", str(repo)) == 0

    assert Path((repo / "root").read_text()).resolve() == repo.resolve()
    out = capsys.readouterr().out
    assert "Source:" not in out  # only printed when it differs from the worktree


def test_no_config_is_a_noop_success(
    repo: Path, worktree: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run("setup", str(worktree)) == 0
    assert "Nothing to run" in capsys.readouterr().out
    assert ws.read_setup_status(str(worktree)) == {"status": "none"}


def test_outside_a_git_checkout_is_a_usage_error(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert _run("setup", str(plain)) == 2
    assert "not inside a git checkout" in capsys.readouterr().err


def test_refuses_while_a_daemon_run_is_in_flight_unless_forced(
    repo: Path, worktree: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _config(repo, ["touch cli_ran"])
    # A live record, as the daemon leaves it while its own thread is running.
    live = ws.SetupRunRecorder(
        worktree_path=str(worktree), source_repo=str(repo), commands=["sleep 60"]
    )
    live(
        ws.SetupEvent(
            type="command_started",
            hook="setup",
            index=1,
            total=1,
            command="sleep 60",
            cwd=str(worktree),
        )
    )

    assert _run("setup", str(worktree)) == 1
    assert "already in progress" in capsys.readouterr().err
    assert not (worktree / "cli_ran").exists()

    assert _run("setup", str(worktree), "--force") == 0
    assert (worktree / "cli_ran").exists()


def test_a_stale_running_record_does_not_block(
    repo: Path, worktree: Path, home: Path
) -> None:
    _config(repo, ["touch cli_ran"])
    # A daemon that died mid-run leaves `running` behind; past the engine's
    # whole-hook budget nothing can still be executing it.
    stale = ws.SetupRunRecorder(
        worktree_path=str(worktree), source_repo=str(repo), commands=["sleep 60"]
    )
    status_path = stale.status_path
    record = json.loads(status_path.read_text())
    record["started_at"] = time.time() - ws.DEFAULT_TOTAL_TIMEOUT_S - 60
    status_path.write_text(json.dumps(record))

    assert _run("setup", str(worktree)) == 0
    assert (worktree / "cli_ran").exists()


def test_bare_worktree_command_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run() == 2
    err = capsys.readouterr().err
    assert "usage: vicoa worktree new" in err
    assert "vicoa worktree setup" in err


# --- `vicoa worktree new` -------------------------------------------------------


@pytest.fixture
def no_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never re-file a real session: these tests may run inside one."""
    monkeypatch.delenv("VICOA_AGENT_INSTANCE_ID", raising=False)
    monkeypatch.delenv("VICOA_API_KEY", raising=False)


def _last_line(out: str) -> str:
    return out.strip().splitlines()[-1]


def test_new_makes_a_named_worktree_and_prints_where_to_work(
    repo: Path, home: Path, no_session: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run("new", "vic-42", "--path", str(repo)) == 0
    path = home / "vicoa" / "workspaces" / "app-worktrees" / "vic-42" / "app"
    assert (path / "seed.txt").exists()
    assert _last_line(capsys.readouterr().out) == str(path)


def test_new_takes_the_next_free_name_when_it_is_taken(
    repo: Path, home: Path, no_session: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run("new", "vic-42", "--path", str(repo)) == 0
    capsys.readouterr()
    assert _run("new", "vic-42", "--path", str(repo)) == 0
    out = capsys.readouterr().out
    assert "Made worktree vic-42-2 (vic-42 was taken)" in out
    assert _last_line(out).endswith("/vic-42-2/app")


def test_new_from_a_subfolder_works_in_the_same_subfolder(
    repo: Path, home: Path, no_session: None, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "apps" / "web").mkdir(parents=True)
    (repo / "apps" / "web" / "keep").write_text("")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "web"], check=True)
    assert _run("new", "vic-1", "--path", str(repo / "apps" / "web")) == 0
    work = Path(_last_line(capsys.readouterr().out))
    assert work.parts[-2:] == ("apps", "web")
    assert work.is_dir()


def test_new_inside_a_worktree_makes_nothing(
    worktree: Path, no_session: None, capsys: pytest.CaptureFixture[str]
) -> None:
    before = sorted(p.name for p in worktree.parent.parent.iterdir())
    assert _run("new", "--path", str(worktree)) == 0
    out = capsys.readouterr().out
    assert "Already in worktree" in out
    assert _last_line(out) == os.path.realpath(worktree)
    assert sorted(p.name for p in worktree.parent.parent.iterdir()) == before


def test_new_outside_git_refuses(
    tmp_path: Path, home: Path, no_session: None, capsys: pytest.CaptureFixture[str]
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert _run("new", "--path", str(plain)) == 1
    assert "not inside a git repository" in capsys.readouterr().err


def test_new_runs_setup_only_for_a_trusted_repo(
    repo: Path, home: Path, no_session: None, capsys: pytest.CaptureFixture[str]
) -> None:
    from vicoa.rpc.worktree_trust import grant_repo_trust

    _config(repo, ['touch "$VICOA_WORKTREE_PATH/set-up"'])
    assert _run("new", "untrusted", "--path", str(repo)) == 0
    untrusted = Path(_last_line(capsys.readouterr().out))
    assert not (untrusted / "set-up").exists()

    grant_repo_trust(str(repo))
    assert _run("new", "trusted", "--path", str(repo)) == 0
    out = capsys.readouterr().out
    assert "Setup done." in out
    assert (Path(_last_line(out)) / "set-up").exists()

    assert _run("new", "skipped", "--path", str(repo), "--no-setup") == 0
    assert not (Path(_last_line(capsys.readouterr().out)) / "set-up").exists()


def test_new_files_the_running_session_under_the_worktree(
    repo: Path,
    home: Path,
    no_session: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from vicoa.commands import worktree as worktree_cmd

    filed: list[tuple[str, str]] = []

    def fake_file(args, session_id: str, branch: str) -> str | None:
        filed.append((session_id, branch))
        return None

    monkeypatch.setattr(worktree_cmd, "_file_session", fake_file)
    monkeypatch.setenv("VICOA_AGENT_INSTANCE_ID", "sess-1")
    assert _run("new", "vic-9", "--path", str(repo)) == 0
    assert filed == [("sess-1", "vic-9")]
    assert "Filed this session under it." in capsys.readouterr().out

    assert _run("new", "vic-10", "--path", str(repo), "--no-session") == 0
    assert filed == [("sess-1", "vic-9")]


def test_new_still_succeeds_when_the_session_cannot_be_filed(
    repo: Path,
    home: Path,
    no_session: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The worktree exists: a non-zero exit would have the agent make another."""
    from vicoa.commands import instance

    def unreachable(*args, **kwargs):
        raise SystemExit(1)

    monkeypatch.setattr(instance, "_resolve_worktree_move", unreachable)
    monkeypatch.setenv("VICOA_AGENT_INSTANCE_ID", "sess-1")
    monkeypatch.setenv("VICOA_API_KEY", "key")
    assert _run("new", "vic-11", "--path", str(repo)) == 0
    captured = capsys.readouterr()
    assert "Couldn't file this session under it" in captured.err
    assert "--worktree vic-11" in captured.err
    assert _last_line(captured.out).endswith("/vic-11/app")


def test_file_session_patches_the_folder_fields(
    no_session: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vicoa.commands import _api, instance
    from vicoa.commands import worktree as worktree_cmd

    body = {"project": "~/w/vic-1/app", "worktree_name": "vic-1", "repo_root": "~/app"}
    sent: list[dict] = []
    monkeypatch.setattr(instance, "_resolve_worktree_move", lambda *a, **k: body)

    def fake_request(args, api_key, method, endpoint, **kwargs):
        sent.append({"method": method, "endpoint": endpoint, **kwargs})
        return dict(kwargs["json"])

    monkeypatch.setattr(_api, "request", fake_request)
    args = argparse.Namespace(api_key="key", base_url="http://example.test")
    assert worktree_cmd._file_session(args, "sess-1", "vic-1") is None
    assert sent == [
        {
            "method": "PATCH",
            "endpoint": "/api/v1/agent-instances/sess-1",
            "json": body,
            "raise_on_error": True,
        }
    ]

    # A server that predates the folder fields echoes the row unchanged.
    monkeypatch.setattr(_api, "request", lambda *a, **k: {"project": "~/app"})
    assert "predates" in (worktree_cmd._file_session(args, "sess-1", "vic-1") or "")
