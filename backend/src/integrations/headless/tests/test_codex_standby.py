"""Codex standby (prewarm): codex comes up before registration, the first
prompt arrives with the go line and runs at once, its own row is dropped by id,
and agent messages wait for the prompt's display POST."""

from __future__ import annotations

import asyncio
from typing import Any, List, Optional, Tuple

import pytest

from integrations.headless import codex_native
from integrations.headless.codex_app_server import CodexAppServerSession
from integrations.headless.codex_native import CodexNativeRunner, StandbyDiscarded


class _FakeSession:
    def __init__(self) -> None:
        self.held: Optional[asyncio.Task[Any]] = None

    async def maybe_route_auq_reply(self, _content: str) -> bool:
        return False

    def try_resolve_pending_reply(self, _text: str) -> bool:
        return False

    def hold_agent_posts_until(self, task: "asyncio.Task[Any]") -> None:
        self.held = task


class _GatedClient:
    """``send_user_message`` blocks until released, so a test can deliver the
    broadcast before the POST's response."""

    def __init__(self, message_id: str = "srv-1") -> None:
        self.release = asyncio.Event()
        self.message_id = message_id
        self.posts: List[str] = []

    async def send_user_message(self, agent_instance_id, content, mark_as_read=True):
        self.posts.append(content)
        await self.release.wait()
        return {"success": True, "message_id": self.message_id}


def _runner(client: Any) -> CodexNativeRunner:
    runner = CodexNativeRunner.__new__(CodexNativeRunner)
    runner.session = _FakeSession()  # type: ignore[assignment]
    runner.session_id = "codex-inst"
    runner.agent_name = "Codex"
    runner.running = True
    runner.vicoa_client = client  # type: ignore[assignment]
    runner._turn_queue = asyncio.Queue()
    runner._consumer_task = None
    runner._cancelled_message_ids = set()
    runner._pending_by_id = {}
    runner._steer_requested_ids = set()
    runner._steer_in_flight = {}
    return runner


def _go(payload: Optional[dict[str, Any]]):
    async def read_go_async(timeout: Optional[float] = None):
        return payload

    return read_go_async


# ---- bring-up ---------------------------------------------------------------


async def test_codex_is_up_before_the_go_and_reports_nothing(monkeypatch) -> None:
    runner = _runner(_GatedClient())
    order: List[Tuple[str, Any]] = []

    async def start_codex(*, report: bool) -> None:
        order.append(("start", report))

    async def read_go_async(timeout: Optional[float] = None):
        order.append(("go", None))
        return {"prompt": "fix the build"}

    monkeypatch.setattr(runner, "_start_codex", start_codex)
    monkeypatch.setattr(codex_native, "read_go_async", read_go_async)
    await runner._standby_bring_up()
    assert order == [("start", False), ("go", None)]
    assert runner._engine_preconnected is True
    assert runner._adopted_prompt == "fix the build"


async def test_a_discard_raises_before_anything_is_registered(monkeypatch) -> None:
    runner = _runner(_GatedClient())

    async def start_codex(*, report: bool) -> None:
        pass

    monkeypatch.setattr(runner, "_start_codex", start_codex)
    monkeypatch.setattr(codex_native, "read_go_async", _go(None))
    with pytest.raises(StandbyDiscarded):
        await runner._standby_bring_up()
    assert getattr(runner, "_registered", False) is False


# ---- the adopted prompt -----------------------------------------------------


async def test_the_prompt_runs_at_once_and_its_row_is_dropped_by_id() -> None:
    client = _GatedClient(message_id="srv-1")
    runner = _runner(client)
    runner._feed_adopted_prompt("run the tests")

    assert runner._turn_queue.get_nowait() == ("run the tests", (), None)
    assert runner.session.held is runner._prompt_post_task  # type: ignore[union-attr]

    client.release.set()
    await runner._prompt_post_task
    for _ in range(2):  # the live broadcast, then a catch-up replay
        await runner._route("run the tests", (), "srv-1")
    assert runner._turn_queue.empty()

    # The same words sent again by the user are a different row: they run.
    await runner._route("run the tests", (), "srv-2")
    assert runner._turn_queue.get_nowait()[0] == "run the tests"


async def test_an_echo_that_beats_the_post_response_waits_for_the_id() -> None:
    client = _GatedClient(message_id="srv-1")
    runner = _runner(client)
    runner._feed_adopted_prompt("hello")
    runner._turn_queue.get_nowait()

    echo = asyncio.create_task(runner._route("hello", (), "srv-1"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert not echo.done()

    client.release.set()
    await echo
    assert runner._turn_queue.empty()


# ---- the session side -------------------------------------------------------


class _Transport:
    def __init__(self) -> None:
        self.requests: List[str] = []
        self.on_notification: Any = None
        self.on_close: Any = None
        self.last_activity = 0.0

    def register_request_handler(self, *_a: Any, **_k: Any) -> None:
        pass

    async def start(self) -> None:
        pass

    async def aclose(self) -> None:
        pass

    async def send_request(self, method: str, params: Any = None, timeout: Any = None):
        self.requests.append(method)
        if method == "thread/start":
            return {"thread": {"id": "thread-1"}}
        return {}

    def notify(self, method: str, params: Any = None) -> None:
        pass


class _CountingClient:
    def __init__(self) -> None:
        self.calls: List[str] = []

    async def patch_agent_instance(self, *_a: Any, **_k: Any) -> None:
        self.calls.append("patch")

    async def update_agent_instance_status(self, *_a: Any, **_k: Any) -> None:
        self.calls.append("status")


def _session(client: Any) -> CodexAppServerSession:
    return CodexAppServerSession(
        vicoa_client=client,
        instance_id="codex-inst",
        cwd="/tmp",
        transport=_Transport(),  # type: ignore[arg-type]
        thread_id=None,
        agent_type="codex",
    )


async def test_an_unregistered_start_opens_the_thread_without_server_writes() -> None:
    client = _CountingClient()
    session = _session(client)
    await session.start(report=False)
    assert session.thread_id == "thread-1"
    assert client.calls == []
    await session.persist_thread_id()
    assert client.calls == ["patch"]
    await session.aclose()


async def test_agent_posts_wait_for_the_prompt_post_and_survive_its_failure() -> None:
    session = _session(_CountingClient())
    release = asyncio.Event()

    async def prompt_post() -> None:
        await release.wait()
        raise RuntimeError("POST failed")

    task = asyncio.create_task(prompt_post())
    session.hold_agent_posts_until(task)
    waiter = asyncio.create_task(session._wait_agent_post_gate())
    await asyncio.sleep(0)
    assert not waiter.done()
    release.set()
    await waiter  # a failed display POST must not block replies
