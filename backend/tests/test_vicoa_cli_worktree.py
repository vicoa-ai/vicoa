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
    assert "usage: vicoa worktree setup" in capsys.readouterr().err
