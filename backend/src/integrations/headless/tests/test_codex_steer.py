"""Steer: deliver a queued message into the *running* codex turn.

Two layers:

* ``CodexAppServerSession.steer`` — sends ``turn/steer`` with the active turn
  id as the ``expectedTurnId`` precondition and reports acceptance; any
  rejection (not steerable, turn already over, method unknown) is a plain
  ``False`` so the runner can leave the message queued.
* ``CodexNativeRunner._steer_queued_message`` — the runner side of the queue
  bar's Steer button: finds the queued message by id, steers it, stamps it
  consumed (``steered``), and makes sure the serialized consumer drops it at
  drain instead of running it again as its own turn.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import List, Optional, Tuple

import pytest
from _fakes import FakeAsyncVicoaClient
from test_codex_app_server import FakeCodexPipe, _drive_bringup, _wait_until

from integrations.headless.codex.transport import CodexTransport
from integrations.headless.codex_app_server import CodexAppServerSession
from integrations.headless.codex_native import CodexNativeRunner

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Session: turn/steer on the wire
# ---------------------------------------------------------------------------


async def _drive_steer_turn(
    s2c: FakeCodexPipe,
    c2s: FakeCodexPipe,
    *,
    steer_reply: dict,
    thread_id: str = "thread-1",
    turn_id: str = "turn-1",
) -> None:
    """Bring-up + turn/start, answer the SUT's turn/steer with ``steer_reply``
    (a ``result`` or ``error`` fragment), then complete the turn."""
    await _drive_bringup(s2c, c2s, expect_resume=False, start_thread_id=thread_id)
    msg = await s2c.read_message()
    assert msg["method"] == "turn/start"
    c2s.feed_message(
        {
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {"turn": {"id": turn_id, "status": "inProgress"}},
        }
    )
    msg = await s2c.read_message()
    assert msg["method"] == "turn/steer"
    assert msg["params"]["threadId"] == thread_id
    assert msg["params"]["expectedTurnId"] == turn_id
    assert msg["params"]["input"] == [{"type": "text", "text": "use bun instead"}]
    c2s.feed_message({"jsonrpc": "2.0", "id": msg["id"], **steer_reply})
    c2s.feed_message(
        {
            "jsonrpc": "2.0",
            "method": "turn/completed",
            "params": {
                "threadId": thread_id,
                "turn": {"id": turn_id, "status": "completed"},
            },
        }
    )


async def _steer_against_script(steer_reply: dict) -> bool:
    s2c = FakeCodexPipe()
    c2s = FakeCodexPipe()
    transport = CodexTransport(reader=c2s, writer=s2c)
    session = CodexAppServerSession(
        vicoa_client=FakeAsyncVicoaClient(),
        instance_id="inst-steer",
        cwd="/tmp/codex-steer-cwd",
        transport=transport,
    )
    script = asyncio.create_task(_drive_steer_turn(s2c, c2s, steer_reply=steer_reply))
    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        turn = asyncio.create_task(session.on_user_message("write a poem"))
        await _wait_until(lambda: session.active_turn_id is not None)
        steered = await asyncio.wait_for(session.steer("use bun instead"), timeout=2.0)
        await asyncio.wait_for(turn, timeout=2.0)
        await asyncio.wait_for(script, timeout=2.0)
    finally:
        if not script.done():
            script.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script
        await session.aclose()
    return steered


async def test_steer_sends_turn_steer_with_the_active_turn_as_precondition():
    assert await _steer_against_script({"result": {"turnId": "turn-1"}}) is True


async def test_steer_reports_a_rejection_instead_of_raising():
    """``activeTurnNotSteerable`` (review/compact), an ``expectedTurnId``
    mismatch, or an unknown method all come back as a JSON-RPC error — the
    runner just needs ``False`` so the message runs as the next turn."""
    error = {
        "error": {
            "code": -32600,
            "message": "active turn is not steerable",
            "data": {
                "codexErrorInfo": {"activeTurnNotSteerable": {"turnKind": "review"}}
            },
        }
    }
    assert await _steer_against_script(error) is False


async def test_steer_without_an_active_turn_is_a_no_op():
    s2c = FakeCodexPipe()
    c2s = FakeCodexPipe()
    session = CodexAppServerSession(
        vicoa_client=FakeAsyncVicoaClient(),
        instance_id="inst-steer-idle",
        cwd="/tmp/codex-steer-cwd",
        transport=CodexTransport(reader=c2s, writer=s2c),
    )
    session.thread_id = "thread-1"
    session.active_turn_id = None

    assert await asyncio.wait_for(session.steer("hello"), timeout=2.0) is False
    assert not s2c.requests_by_method["turn/steer"]


# ---------------------------------------------------------------------------
# Runner: the Steer button's delivery + queue bookkeeping
# ---------------------------------------------------------------------------


class _FakeSession:
    """Stands in for ``CodexAppServerSession``: records deliveries and steers,
    parks the first turn on ``gate`` so the test can hold it open."""

    def __init__(self, *, accept_steer: bool = True) -> None:
        self.delivered: List[Tuple[str, tuple]] = []
        self.steered: List[Tuple[str, tuple]] = []
        self.accept_steer = accept_steer
        self.active_turn_id: Optional[str] = None
        self.gate: Optional[asyncio.Event] = None
        self._gated_once = False

    async def maybe_route_auq_reply(self, _content: str) -> bool:
        return False

    def try_resolve_pending_reply(self, _text: str) -> bool:
        return False

    async def deliver_user_message(self, text: str, attachments: tuple = ()) -> None:
        self.delivered.append((text, attachments))
        if self.gate is not None and not self._gated_once:
            self._gated_once = True
            self.active_turn_id = "turn-1"
            await self.gate.wait()
            self.active_turn_id = None

    async def steer(self, text: str, attachments: tuple = ()) -> bool:
        if self.active_turn_id is None:
            return False
        self.steered.append((text, attachments))
        return self.accept_steer


def _build_runner(session: _FakeSession) -> CodexNativeRunner:
    runner = CodexNativeRunner.__new__(CodexNativeRunner)
    runner.session = session  # type: ignore[assignment]
    runner.session_id = "codex-inst"
    runner.agent_name = "Codex"
    runner.running = True
    runner.vicoa_client = FakeAsyncVicoaClient()  # type: ignore[assignment]
    runner._turn_queue = asyncio.Queue()
    runner._consumer_task = None
    runner._cancelled_message_ids = set()
    runner._pending_by_id = {}
    runner._steer_requested_ids = set()
    runner._steer_in_flight = {}
    return runner


@contextlib.asynccontextmanager
async def _running_consumer(runner: CodexNativeRunner):
    consumer = asyncio.create_task(runner._consume_user_messages())
    try:
        yield consumer
    finally:
        runner.running = False
        consumer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await consumer


async def test_steer_delivers_a_queued_message_into_the_open_turn_and_drops_it():
    session = _FakeSession()
    session.gate = asyncio.Event()
    runner = _build_runner(session)

    async with _running_consumer(runner):
        await runner._route("A", (), "mA")
        await _wait_until(lambda: session.active_turn_id == "turn-1")
        # B queues behind A's turn; the user presses Steer on it.
        await runner._route("B", (), "mB")
        await runner._steer_queued_message("mB")

        assert session.steered == [("B", ())]
        assert runner.vicoa_client.mark_steered_calls == ["mB"]
        assert runner.vicoa_client.requeue_calls == []
        # A's turn ends: the consumer drains B but must NOT run it again.
        session.gate.set()
        await asyncio.sleep(0.05)
        assert session.delivered == [("A", ())]
        assert runner._steer_in_flight == {}
        assert runner._pending_by_id == {}


async def test_rejected_steer_requeues_and_the_message_runs_as_the_next_turn():
    session = _FakeSession(accept_steer=False)
    session.gate = asyncio.Event()
    runner = _build_runner(session)

    async with _running_consumer(runner):
        await runner._route("A", (), "mA")
        await _wait_until(lambda: session.active_turn_id == "turn-1")
        await runner._route("B", (), "mB")
        await runner._steer_queued_message("mB")

        assert session.steered == [("B", ())]
        assert runner.vicoa_client.mark_steered_calls == []
        # The row goes back to `queued` and the user is told why.
        assert runner.vicoa_client.requeue_calls == ["mB"]
        assert any(
            "Couldn't steer" in m["content"] for m in runner.vicoa_client.sent_messages
        )
        session.gate.set()
        await _wait_until(lambda: session.delivered == [("A", ()), ("B", ())])
        assert runner.vicoa_client.mark_consumed_calls[-1] == "mB"


async def test_steer_with_no_open_turn_leaves_the_message_to_the_consumer():
    """No turn to steer into: the consumer is about to run it, so nothing is
    delivered, requeued, or announced."""
    session = _FakeSession()
    runner = _build_runner(session)

    await runner._route("B", (), "mB")
    await runner._steer_queued_message("mB")

    assert session.steered == []
    assert runner.vicoa_client.requeue_calls == []
    assert runner.vicoa_client.sent_messages == []
    assert runner._turn_queue.get_nowait() == ("B", (), "mB")


async def test_steer_request_that_overtakes_its_message_is_honored_on_enqueue():
    """Both events ride the same WS, but ``_route`` awaits before it enqueues,
    so the ``steer`` update can be processed first."""
    session = _FakeSession()
    session.active_turn_id = "turn-1"
    runner = _build_runner(session)

    await runner._steer_queued_message("mB")
    assert session.steered == []
    assert runner._steer_requested_ids == {"mB"}

    await runner._route("B", (), "mB")

    assert session.steered == [("B", ())]
    assert runner.vicoa_client.mark_steered_calls == ["mB"]
    assert runner._steer_requested_ids == set()


async def test_ws_steer_update_is_bridged_onto_the_loop():
    session = _FakeSession()
    session.active_turn_id = "turn-1"
    runner = _build_runner(session)
    runner._loop = asyncio.get_running_loop()
    await runner._route("B", (), "mB")

    runner._on_ws_message_update(
        {"id": "mB", "message_metadata": {"queue": {"status": "steer"}}}
    )
    await _wait_until(lambda: session.steered == [("B", ())])
