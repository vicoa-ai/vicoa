"""codex_native serialized turn consumer + burst coalescing.

``CodexNativeRunner`` runs user messages through a single consumer task over
``_turn_queue`` (``_consume_user_messages``) instead of firing a
fire-and-forget ``create_task`` per message. This gives two properties the old
design lacked:

* Serialization — one turn at a time, so nothing races the session's single
  turn slot.
* Coalescing — a burst the user sent while a turn was running drains into ONE
  follow-up turn, not one turn each.

Permission replies are peeled off in ``_route`` and resolved inline (never
enqueued) so the turn awaiting them can't deadlock behind its own reply.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional, Tuple

import pytest

from integrations.headless.codex_native import CodexNativeRunner

pytestmark = pytest.mark.asyncio


class _FakeSession:
    def __init__(self) -> None:
        self.delivered: List[Tuple[str, tuple]] = []
        self.permission_answer = False
        self.resolved: List[str] = []
        # When set, the first deliver_user_message parks on this until the test
        # releases it — simulating a long-running turn.
        self.gate: Optional[asyncio.Event] = None
        self._gated_once = False

    async def maybe_route_auq_reply(self, _content: str) -> bool:
        return False

    def try_resolve_pending_reply(self, text: str) -> bool:
        if self.permission_answer:
            self.resolved.append(text)
            return True
        return False

    async def deliver_user_message(self, text: str, attachments: tuple = ()) -> None:
        self.delivered.append((text, attachments))
        if self.gate is not None and not self._gated_once:
            self._gated_once = True
            await self.gate.wait()


def _build_runner(session: _FakeSession) -> CodexNativeRunner:
    from _fakes import FakeAsyncVicoaClient

    runner = CodexNativeRunner.__new__(CodexNativeRunner)
    runner.session = session  # type: ignore[assignment]
    runner.session_id = "codex-inst"
    runner.agent_name = "Codex"
    runner.running = True
    runner.vicoa_client = FakeAsyncVicoaClient()  # type: ignore[assignment]
    runner._turn_queue = asyncio.Queue()
    runner._consumer_task = None
    runner._cancelled_message_ids = set()
    return runner


async def test_coalesce_turn_batch_joins_text_and_concats_attachments() -> None:
    from vicoa.attachments import AttachmentRef

    a1 = AttachmentRef("att-1", "image/png", "a.png")
    a2 = AttachmentRef("att-2", "image/png", "b.png")

    text, attachments = CodexNativeRunner._coalesce_turn_batch(
        [("first", (a1,), "m1"), ("", (a2,), "m2"), ("third", (), "m3")]
    )

    assert text == "first\n\nthird"
    assert attachments == (a1, a2)


async def test_route_enqueues_plain_message_with_id() -> None:
    session = _FakeSession()
    runner = _build_runner(session)

    await runner._route("hello", (), "m1")

    assert runner._turn_queue.get_nowait() == ("hello", (), "m1")


async def test_route_resolves_permission_reply_inline_and_clears_badge() -> None:
    session = _FakeSession()
    session.permission_answer = True
    runner = _build_runner(session)

    await runner._route("Allow once", (), "m9")

    assert session.resolved == ["Allow once"]
    assert runner._turn_queue.empty()
    # The reply's own queued badge is cleared even though it never ran a turn.
    assert runner.vicoa_client.mark_consumed_calls == ["m9"]


async def test_consumer_coalesces_burst_during_a_turn() -> None:
    """A and then (B, C sent while A's turn runs) → two turns: A, then B+C."""
    session = _FakeSession()
    session.gate = asyncio.Event()
    runner = _build_runner(session)

    consumer = asyncio.create_task(runner._consume_user_messages())
    try:
        # A starts turn 1, which parks on the gate.
        runner._turn_queue.put_nowait(("A", (), "mA"))
        await _wait_until(lambda: session.delivered == [("A", ())])
        # B and C arrive DURING turn 1 — they queue, they don't each fire.
        runner._turn_queue.put_nowait(("B", (), "mB"))
        runner._turn_queue.put_nowait(("C", (), "mC"))
        # Let turn 1 finish; the consumer drains B + C and coalesces them.
        session.gate.set()
        await _wait_until(lambda: session.delivered == [("A", ()), ("B\n\nC", ())])
        # Every message's queued badge is cleared as its batch is picked up.
        assert runner.vicoa_client.mark_consumed_calls == ["mA", "mB", "mC"]
    finally:
        runner.running = False
        consumer.cancel()
        try:
            await consumer
        except asyncio.CancelledError:
            pass


async def test_consumer_drops_a_cancelled_message_mid_burst() -> None:
    """A message cancelled while the prior turn runs is dropped at drain.

    The cancel arrives as a message-update (``_on_ws_message_update`` stamps the
    id), and when the consumer drains the burst it leaves the cancelled message
    out of the coalesced follow-up turn and does NOT mark it consumed (it's
    cancelled, not consumed)."""
    session = _FakeSession()
    session.gate = asyncio.Event()
    runner = _build_runner(session)

    consumer = asyncio.create_task(runner._consume_user_messages())
    try:
        # A starts turn 1, which parks on the gate.
        runner._turn_queue.put_nowait(("A", (), "mA"))
        await _wait_until(lambda: session.delivered == [("A", ())])
        # B and C queue behind the running turn; the user then cancels B.
        runner._turn_queue.put_nowait(("B", (), "mB"))
        runner._turn_queue.put_nowait(("C", (), "mC"))
        runner._on_ws_message_update(
            {"id": "mB", "message_metadata": {"queue": {"status": "cancelled"}}}
        )
        # Turn 1 ends; the drain drops B and runs C alone.
        session.gate.set()
        await _wait_until(lambda: session.delivered == [("A", ()), ("C", ())])
        # B is neither delivered nor marked consumed; its id is cleared so it
        # can't suppress a later message that happens to reuse the id.
        assert runner.vicoa_client.mark_consumed_calls == ["mA", "mC"]
        assert runner._cancelled_message_ids == set()
    finally:
        runner.running = False
        consumer.cancel()
        try:
            await consumer
        except asyncio.CancelledError:
            pass


async def test_consumer_survives_a_turn_that_raises() -> None:
    """A turn error is logged and the next queued message still runs."""

    class _RaiseOnceSession(_FakeSession):
        async def deliver_user_message(
            self, text: str, attachments: tuple = ()
        ) -> None:
            self.delivered.append((text, attachments))
            if text == "boom":
                raise RuntimeError("turn blew up")

    session = _RaiseOnceSession()
    runner = _build_runner(session)

    consumer = asyncio.create_task(runner._consume_user_messages())
    try:
        # Enqueue sequentially (waiting for the first to be picked up) so "boom"
        # runs as its own turn and raises, rather than coalescing with "after".
        runner._turn_queue.put_nowait(("boom", (), "m1"))
        await _wait_until(lambda: session.delivered == [("boom", ())])
        runner._turn_queue.put_nowait(("after", (), "m2"))
        await _wait_until(lambda: session.delivered == [("boom", ()), ("after", ())])
    finally:
        runner.running = False
        consumer.cancel()
        try:
            await consumer
        except asyncio.CancelledError:
            pass


async def _wait_until(predicate, *, timeout: float = 2.0) -> None:
    elapsed = 0.0
    step = 0.01
    while elapsed < timeout:
        if predicate():
            return
        await asyncio.sleep(step)
        elapsed += step
    raise AssertionError("predicate never became true within timeout")
