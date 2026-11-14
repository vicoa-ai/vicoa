"""`vicoa headless` start-up: nothing that only feeds the dashboard holds up the
agent.

The daemon launches every app-started session as `vicoa headless`. Two things
used to run, blocking, before the agent's own code: the npm update check (a
banner nobody reads for a background session) and the slash-command upload
(the server's fallback copy of the command index, whose client retries for up
to 30s per attempt when the server is slow).
"""

from __future__ import annotations

import importlib
import sys
import types
from argparse import Namespace
from typing import Any

import pytest

from vicoa import cli


def test_headless_skips_the_update_check(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "check_for_updates", lambda: calls.append("update-check"))
    monkeypatch.setattr(
        cli, "cmd_headless", lambda args, unknown: calls.append("headless")
    )
    monkeypatch.setattr(sys, "argv", ["vicoa", "headless", "--api-key", "k"])

    cli.main()

    assert calls == ["headless"]


def test_other_commands_still_check_for_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "check_for_updates", lambda: calls.append("update-check"))
    monkeypatch.setattr(cli, "cmd_machine_daemon", lambda args: calls.append("daemon"))
    monkeypatch.setattr(sys, "argv", ["vicoa", "daemon"])

    cli.main()

    assert calls == ["update-check", "daemon"]


def test_sync_user_commands_async_starts_a_daemon_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeThread:
        def __init__(self, *, target, args, daemon, name):
            captured.update(target=target, args=args, daemon=daemon, name=name)

        def start(self) -> None:
            captured["started"] = True

    monkeypatch.setattr(cli.threading, "Thread", FakeThread)

    cli.sync_user_commands_async("test-key", "https://api.vicoa.ai", "claude")

    assert captured == {
        "target": cli.sync_user_commands,
        "args": ("test-key", "https://api.vicoa.ai", "claude"),
        "daemon": True,
        "name": "vicoa-command-sync",
        "started": True,
    }


def test_headless_runs_the_agent_without_waiting_for_the_command_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []

    def blocking_sync(*_args: Any) -> None:
        pytest.fail("the command upload ran on the session's start path")

    monkeypatch.setattr(cli, "ensure_api_key", lambda args: "test-key")
    monkeypatch.setattr(cli, "sync_user_commands", blocking_sync)
    monkeypatch.setattr(
        cli, "sync_user_commands_async", lambda *a: calls.append(("upload", *a))
    )
    monkeypatch.setattr(cli, "sync_project_files_async", lambda *a: None)

    runner = types.ModuleType("fake_headless_runner")
    runner.main = lambda: calls.append("agent")  # type: ignore[attr-defined]
    real_import = importlib.import_module
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name, *a: runner
        if name.startswith("integrations.headless")
        else real_import(name, *a),
    )

    cli.cmd_headless(
        Namespace(agent="claude", base_url="https://api.vicoa.ai", session_id="s"),
        [],
    )

    assert calls == [("upload", "test-key", "https://api.vicoa.ai", "claude"), "agent"]
