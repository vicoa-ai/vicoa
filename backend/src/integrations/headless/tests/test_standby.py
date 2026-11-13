"""Standby (prewarm) launch: the stdin go protocol, the Claude runner's use of
it, and the `vicoa headless --standby` gate."""

from __future__ import annotations

import asyncio
import io
import os
import sys
import threading
import types
from argparse import Namespace
from typing import Any, Optional

import pytest
from integrations.headless import claude_code
from integrations.headless.claude_code import StandbyDiscarded
from vicoa import cli
from vicoa import standby as standby_mod


@pytest.fixture(autouse=True)
def _keep_test_stdin(monkeypatch):
    # The real one points fd 0 at /dev/null; the test process keeps its own.
    monkeypatch.setattr(standby_mod, "_detach_stdin", lambda: None)


# ---- the protocol -----------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('{"prompt": "fix the build"}\n', {"prompt": "fix the build"}),
        ('{"prompt": null}\n', {"prompt": None}),
        ("{}\n", {"prompt": None}),
        ('{"discard": true}\n', None),
        ("not json\n", None),
        ("[1, 2]\n", None),
        ('{"prompt": 3}\n', None),
        ("\n", None),
    ],
)
def test_go_line_parsing(line: str, expected: Optional[dict[str, Any]]) -> None:
    assert standby_mod.parse_go_line(line) == expected


def test_go_line_on_stdin_adopts(monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"prompt": "hi"}\n'))
    assert standby_mod.read_go(2) == {"prompt": "hi"}


def test_end_of_file_discards(monkeypatch) -> None:
    """The daemon closing the pipe (or dying) drops the standby."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert standby_mod.read_go(2) is None


def test_no_go_in_time_discards(monkeypatch) -> None:
    class IdlePipe(io.StringIO):
        def readline(self, *_args: Any) -> str:
            threading.Event().wait(1)  # a pipe nobody writes to
            return ""

    monkeypatch.setattr(sys, "stdin", IdlePipe())
    assert standby_mod.read_go(0.05) is None


def test_stdin_is_detached_after_the_go(monkeypatch) -> None:
    detached: list[bool] = []
    monkeypatch.setattr(standby_mod, "_detach_stdin", lambda: detached.append(True))
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}\n"))
    standby_mod.read_go(2)
    assert detached == [True]


def test_standby_requested_reads_the_env(monkeypatch) -> None:
    monkeypatch.delenv(standby_mod.STANDBY_ENV, raising=False)
    assert standby_mod.standby_requested() is False
    monkeypatch.setenv(standby_mod.STANDBY_ENV, "1")
    assert standby_mod.standby_requested() is True


# ---- the Claude runner ------------------------------------------------------


class _FakeSdkClient:
    def __init__(self, options: Any) -> None:
        self.connected = False

    async def connect(self) -> None:
        self.connected = True


def _go(payload: Optional[dict[str, Any]]):
    async def read_go_async(timeout: Optional[float] = None):
        return payload

    return read_go_async


@pytest.fixture
def standby_runner(make_runner, monkeypatch):
    monkeypatch.setattr(claude_code, "ClaudeSDKClient", _FakeSdkClient)
    runner = make_runner()
    runner.claude_options = object()
    return runner


async def test_the_engine_is_up_before_the_go_is_read(standby_runner, monkeypatch):
    seen: list[bool] = []

    async def read_go_async(timeout: Optional[float] = None):
        seen.append(standby_runner.claude_client.connected)
        return {"prompt": "hello"}

    monkeypatch.setattr(claude_code, "read_go_async", read_go_async)
    await standby_runner._standby_bring_up()
    assert seen == [True]
    assert standby_runner._engine_preconnected is True
    assert standby_runner._adopted_prompt == "hello"


async def test_a_go_without_a_prompt_adopts_with_none(standby_runner, monkeypatch):
    monkeypatch.setattr(claude_code, "read_go_async", _go({"prompt": None}))
    await standby_runner._standby_bring_up()
    assert standby_runner._adopted_prompt is None


async def test_a_discard_raises_before_anything_is_registered(
    standby_runner, monkeypatch
):
    monkeypatch.setattr(claude_code, "read_go_async", _go(None))
    with pytest.raises(StandbyDiscarded):
        await standby_runner._standby_bring_up()
    assert getattr(standby_runner, "_registered", False) is False


# ---- the adopted prompt: runs once, its row is dropped by id, ordered -------


class _GatedVicoaClient:
    """``send_user_message`` blocks until released, so a test can deliver the
    broadcast before the POST's response, as the server sometimes does."""

    def __init__(self, message_id: str = "srv-1") -> None:
        self.release = asyncio.Event()
        self.message_id = message_id
        self.agent_messages: list[str] = []

    async def send_user_message(self, agent_instance_id, content, mark_as_read=True):
        await self.release.wait()
        return {"success": True, "message_id": self.message_id}

    async def send_message(self, content, **_kwargs):
        self.agent_messages.append(content)
        return None


async def test_adopted_prompt_runs_once_and_its_row_is_dropped_by_id(make_runner):
    from _fakes import FakeAsyncVicoaClient

    runner = make_runner(vicoa_client=FakeAsyncVicoaClient())
    await runner._feed_adopted_prompt("run the tests")
    assert runner._user_message_queue.get_nowait().content == "run the tests"
    await runner._prompt_post_task
    posted_id = runner._adopted_prompt_message_id
    assert posted_id

    # The live broadcast, then a catch-up / reconcile replay of the same row
    # (the read cursor stays put until the first agent message): never rerun.
    await runner._route("run the tests", (), message_id=posted_id)
    await runner._route("run the tests", (), message_id=posted_id)
    assert runner._user_message_queue.empty()

    # The user really sending the same words again is a different row: run it.
    await runner._route("run the tests", (), message_id="srv-2")
    assert runner._user_message_queue.get_nowait().content == "run the tests"


async def test_an_echo_that_beats_the_post_response_waits_for_the_id(make_runner):
    client = _GatedVicoaClient(message_id="srv-1")
    runner = make_runner(vicoa_client=client)
    await runner._feed_adopted_prompt("hello")
    runner._user_message_queue.get_nowait()

    echo = asyncio.create_task(runner._route("hello", (), message_id="srv-1"))
    await asyncio.sleep(0)
    assert not echo.done()  # parked until the POST says which row is ours

    client.release.set()
    await echo
    assert runner._user_message_queue.empty()


async def test_no_agent_message_is_filed_before_the_adopted_prompt(make_runner):
    client = _GatedVicoaClient()
    runner = make_runner(vicoa_client=client)
    await runner._feed_adopted_prompt("hello")

    reply = asyncio.create_task(runner.send_to_vicoa("hi there"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert client.agent_messages == []  # waits behind the prompt POST

    client.release.set()
    await reply
    assert client.agent_messages == ["hi there"]
    assert not runner._send_lock.locked()


async def test_a_post_cancelled_before_it_starts_still_frees_the_send_lock(
    make_runner,
):
    runner = make_runner(vicoa_client=_GatedVicoaClient())
    await runner._feed_adopted_prompt("hello")
    runner._prompt_post_task.cancel()  # before its first step
    with pytest.raises(asyncio.CancelledError):
        await runner._prompt_post_task
    await asyncio.sleep(0)  # done callbacks run on the next loop pass
    assert not runner._send_lock.locked()


# ---- `vicoa headless --standby` ---------------------------------------------


def _run_headless(monkeypatch, agent: str, supports: bool) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(cli, "ensure_api_key", lambda args: "k")
    monkeypatch.setattr(cli, "sync_user_commands_async", lambda *a: None)
    monkeypatch.setattr(cli, "sync_project_files_async", lambda *a: None)
    monkeypatch.delenv(standby_mod.STANDBY_ENV, raising=False)
    runner = types.ModuleType("fake_runner")
    runner.main = lambda: calls.append(os.environ.get(standby_mod.STANDBY_ENV, ""))  # type: ignore[attr-defined]
    if supports:
        runner.SUPPORTS_ENGINE_STANDBY = True  # type: ignore[attr-defined]
    import importlib

    real_import = importlib.import_module
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name, *a: runner
        if name.startswith("integrations.headless")
        else real_import(name, *a),
    )
    cli.cmd_headless(
        Namespace(agent=agent, base_url="http://x", session_id="s", standby=True), []
    )
    return calls


def test_standby_runs_an_engine_standby_runner_with_the_flag_set(monkeypatch):
    assert _run_headless(monkeypatch, "claude", supports=True) == ["1"]


def test_standby_is_refused_for_a_runner_that_cannot_warm_its_engine(monkeypatch):
    with pytest.raises(SystemExit) as exc:
        _run_headless(monkeypatch, "codex", supports=False)
    assert exc.value.code == 2
