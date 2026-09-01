"""Worktree lifecycle execution engine — success, failure, env, stream, bounds.

POSIX-only (the engine runs commands under ``bash``); skipped on Windows, where
the shell path differs. Commands are trivial builtins so the suite stays fast and
hermetic — no network, no package installs.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

from vicoa.rpc import worktree_setup as ws

pytestmark = pytest.mark.skipif(os.name == "nt", reason="engine tests assume bash")


def _run(commands: list[str], *, worktree: Path, hook: ws.HookName = "setup", **kw):
    return ws.run_commands(
        commands,
        hook=hook,
        worktree_path=str(worktree),
        source_repo=str(worktree),
        branch_name="feat/x",
        **kw,
    )


class TestRunCommands:
    def test_empty_is_vacuous_success(self, tmp_path: Path) -> None:
        result = _run([], worktree=tmp_path)
        assert result.ok
        assert result.results == []

    def test_success_captures_output(self, tmp_path: Path) -> None:
        result = _run(["echo hello"], worktree=tmp_path)
        assert result.ok
        assert result.results[0].exit_code == 0
        assert "hello" in result.results[0].output

    def test_nonzero_exit_fails_and_stops(self, tmp_path: Path) -> None:
        marker = tmp_path / "ran_second"
        result = _run(
            ["exit 3", f"touch {marker}"],
            worktree=tmp_path,
        )
        assert not result.ok
        # Only the first command ran; the second never fired.
        assert len(result.results) == 1
        assert result.results[0].exit_code == 3
        assert not marker.exists()
        assert result.failed_result is result.results[0]

    def test_runs_in_worktree_cwd(self, tmp_path: Path) -> None:
        result = _run(["pwd"], worktree=tmp_path)
        assert str(tmp_path.resolve()) in result.results[0].output

    def test_injects_env(self, tmp_path: Path) -> None:
        result = ws.run_commands(
            ['echo "$VICOA_WORKTREE_PATH|$VICOA_BRANCH_NAME|$VICOA_PROJECT_ID"'],
            hook="setup",
            worktree_path=str(tmp_path),
            source_repo=str(tmp_path),
            branch_name="feat/x",
            project_id="proj-123",
        )
        out = result.results[0].output
        assert str(tmp_path) in out
        assert "feat/x" in out
        assert "proj-123" in out


class TestStreaming:
    def test_events_bracket_each_command(self, tmp_path: Path) -> None:
        events: list[ws.SetupEvent] = []
        _run(["echo streamed"], worktree=tmp_path, on_event=events.append)
        types = [e.type for e in events]
        assert types[0] == "command_started"
        assert types[-1] == "command_completed"
        assert "output" in types
        assert any(e.type == "output" and "streamed" in (e.chunk or "") for e in events)


class TestTimeoutAndAbort:
    def test_command_timeout_kills(self, tmp_path: Path) -> None:
        start = time.monotonic()
        result = _run(["sleep 30"], worktree=tmp_path, command_timeout_s=0.3)
        elapsed = time.monotonic() - start
        assert elapsed < 10  # killed, not waited out
        assert result.results[0].timed_out
        assert not result.ok

    def test_preset_abort_short_circuits(self, tmp_path: Path) -> None:
        abort = threading.Event()
        abort.set()
        result = _run(["sleep 30"], worktree=tmp_path, abort=abort)
        assert result.aborted
        assert result.results == []  # loop guard fired before running anything

    def test_mid_command_abort_kills(self, tmp_path: Path) -> None:
        abort = threading.Event()
        threading.Timer(0.2, abort.set).start()
        start = time.monotonic()
        result = _run(["sleep 30"], worktree=tmp_path, abort=abort)
        elapsed = time.monotonic() - start
        assert elapsed < 10
        assert result.aborted
        assert result.results[0].aborted


class TestBoundedOutput:
    def test_truncates_large_output(self) -> None:
        buf = ws._BoundedOutput(max_bytes=1024)
        buf.append("A" * 5000)
        rendered = buf.render()
        assert ws._TRUNCATION_MARKER in rendered
        assert len(rendered.encode()) < 2000

    def test_small_output_not_truncated(self) -> None:
        buf = ws._BoundedOutput(max_bytes=1024)
        buf.append("small")
        assert buf.render() == "small"


class TestReadCommittedConfig:
    def test_reads_setup_and_teardown(self, tmp_path: Path) -> None:
        (tmp_path / "vicoa.json").write_text(
            json.dumps(
                {"worktree": {"setup": ["npm ci"], "teardown": "rm -rf node_modules"}}
            )
        )
        assert ws.read_committed_config_commands(str(tmp_path), "setup") == ["npm ci"]
        assert ws.read_committed_config_commands(str(tmp_path), "teardown") == [
            "rm -rf node_modules"
        ]

    def test_missing_file_is_empty(self, tmp_path: Path) -> None:
        assert ws.read_committed_config_commands(str(tmp_path), "setup") == []

    def test_malformed_json_is_empty(self, tmp_path: Path) -> None:
        (tmp_path / "vicoa.json").write_text("{ not json")
        assert ws.read_committed_config_commands(str(tmp_path), "setup") == []


class TestRunWorktreeSetup:
    def test_no_config_is_vacuous_success(self, tmp_path: Path) -> None:
        result = ws.run_worktree_setup(str(tmp_path), str(tmp_path))
        assert result.ok
        assert result.results == []

    def test_runs_setup_from_source_repo_in_worktree(self, tmp_path: Path) -> None:
        source = tmp_path / "src"
        worktree = tmp_path / "wt"
        source.mkdir()
        worktree.mkdir()
        # Config comes from the SOURCE repo; the command runs in the WORKTREE.
        (source / "vicoa.json").write_text(
            json.dumps({"worktree": {"setup": ["pwd > ran.txt"]}})
        )
        result = ws.run_worktree_setup(str(worktree), str(source))
        assert result.ok
        assert (worktree / "ran.txt").exists()
        assert str(worktree.resolve()) in (worktree / "ran.txt").read_text()


class TestRunWorktreeTeardown:
    def test_no_config_is_vacuous_success(self, tmp_path: Path) -> None:
        result = ws.run_worktree_teardown(str(tmp_path), str(tmp_path))
        assert result.ok
        assert result.results == []

    def test_runs_teardown_from_worktree_config(self, tmp_path: Path) -> None:
        worktree = tmp_path / "wt"
        worktree.mkdir()
        marker = worktree / "torn_down"
        (worktree / "vicoa.json").write_text(
            json.dumps({"worktree": {"teardown": [f"touch {marker}"]}})
        )
        result = ws.run_worktree_teardown(str(worktree), str(tmp_path))
        assert result.ok
        assert marker.exists()

    def test_teardown_failure_is_reported_not_raised(self, tmp_path: Path) -> None:
        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / "vicoa.json").write_text(
            json.dumps({"worktree": {"teardown": "exit 1"}})
        )
        result = ws.run_worktree_teardown(str(worktree), str(tmp_path))
        assert not result.ok
        assert result.results[0].exit_code == 1
