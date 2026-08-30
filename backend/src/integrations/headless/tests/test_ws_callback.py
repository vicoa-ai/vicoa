"""WS subscriber callback bridging — sender filter + asyncio handoff.

The headless runner consumes user messages over a session-scoped /ws
connection (``SessionMessagesWsClient``). Its sync callback runs on a
background thread, so it has to filter sender + bridge into the asyncio
loop via ``run_coroutine_threadsafe``. The handoff is what these tests
exercise — the routing tree itself is covered by ``test_runner_handlers``
and ``test_control_queue``.

``_route`` is async and tested directly via ``await``; the bridge step
(``run_coroutine_threadsafe``) is verified by mocking — in-thread it's a
no-op (Python's docs require it to be called from a different OS thread
than the target loop), so we'd never observe the side effect otherwise.
"""

from __future__ import annotations

import asyncio

import pytest

from _fakes import FakeAsyncVicoaClient


# ---------------------------------------------------------------------------
# _route — routing tree fan-out (driven by the WS callback in production).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_plain_user_message_to_queue(make_runner):
    """Plain content (no AUQ, no permission, no control) lands on the
    user-message queue."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    await runner._route("hello")
    queued = await runner._user_message_queue.get()
    assert queued.content == "hello"
    assert queued.attachments == ()


@pytest.mark.asyncio
async def test_route_message_with_attachments_keeps_refs(make_runner):
    """Attachment refs from message_metadata ride along on the queue, and an
    image-only message (empty content) is still delivered."""
    from vicoa.attachments import AttachmentRef

    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    refs = (AttachmentRef(id="att-1", mime_type="image/png", filename="a.png"),)
    await runner._route("", refs)
    queued = await runner._user_message_queue.get()
    assert queued.content == ""
    assert queued.attachments == refs


@pytest.mark.asyncio
async def test_route_control_command_to_control_queue(make_runner):
    """Control commands (model/effort/permission_mode) skip the user-message
    queue and land on the out-of-band control queue — feeding the worker
    that lets back-to-back settings changes apply without serializing on
    the SDK reconnect."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)

    await runner._route(
        '{"type":"control","setting":"model","value":"claude-opus-4-7"}'
    )

    assert runner._control_command_queue.qsize() == 1
    assert runner._user_message_queue.empty()


# ---------------------------------------------------------------------------
# _wait_for_user_input — burst coalescing.
#
# A user who fires several messages while the agent is busy should have them
# run as ONE turn, not one turn per message. _wait_for_user_input drains every
# message already waiting in the queue and merges them.
# ---------------------------------------------------------------------------


from integrations.headless.claude_code import InboundUserMessage  # noqa: E402


@pytest.mark.asyncio
async def test_wait_coalesces_ready_messages(make_runner):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    for text, mid in [("first", "m1"), ("second", "m2"), ("third", "m3")]:
        runner._user_message_queue.put_nowait(InboundUserMessage(text, (), mid))

    merged = await runner._wait_for_user_input()

    assert merged is not None
    assert merged.content == "first\n\nsecond\n\nthird"
    # Primary id rides the merged message; run_conversation_turn stamps it.
    assert merged.message_id == "m1"
    # The extra ids' queued badges are cleared here (the primary's is cleared
    # by run_conversation_turn).
    assert fake.mark_consumed_calls == ["m2", "m3"]
    assert runner._user_message_queue.empty()


@pytest.mark.asyncio
async def test_wait_single_message_is_unchanged(make_runner):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    runner._user_message_queue.put_nowait(InboundUserMessage("solo", (), "m1"))

    merged = await runner._wait_for_user_input()

    assert merged is not None
    assert merged.content == "solo"
    assert merged.message_id == "m1"
    # A lone message is not re-stamped consumed here — that stays with
    # run_conversation_turn, exactly as before coalescing existed.
    assert fake.mark_consumed_calls == []


@pytest.mark.asyncio
async def test_wait_coalesce_concats_attachments(make_runner):
    from vicoa.attachments import AttachmentRef

    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    a1 = AttachmentRef(id="att-1", mime_type="image/png", filename="a.png")
    a2 = AttachmentRef(id="att-2", mime_type="image/png", filename="b.png")
    runner._user_message_queue.put_nowait(InboundUserMessage("look", (a1,), "m1"))
    runner._user_message_queue.put_nowait(InboundUserMessage("", (a2,), "m2"))

    merged = await runner._wait_for_user_input()

    assert merged is not None
    assert merged.content == "look"
    assert merged.attachments == (a1, a2)


@pytest.mark.asyncio
async def test_wait_coalesce_drops_cancelled_extras(make_runner):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    runner._cancelled_message_ids.add("m2")
    runner._user_message_queue.put_nowait(InboundUserMessage("keep", (), "m1"))
    runner._user_message_queue.put_nowait(InboundUserMessage("cancelled", (), "m2"))
    runner._user_message_queue.put_nowait(InboundUserMessage("also-keep", (), "m3"))

    merged = await runner._wait_for_user_input()

    assert merged is not None
    assert merged.content == "keep\n\nalso-keep"
    assert "m2" not in runner._cancelled_message_ids  # discarded on drop
    assert fake.mark_consumed_calls == ["m3"]


# ---------------------------------------------------------------------------
# _on_ws_user_message — sender filter + bridge.
#
# In production this fires on the sync WS reader thread; here we mock the
# asyncio bridge to capture what would have been scheduled.
# ---------------------------------------------------------------------------


def _capture_bridge(monkeypatch):
    """Mock ``run_coroutine_threadsafe`` to capture coroutines it received."""
    scheduled = []

    def _fake(coro, loop):
        scheduled.append(coro)
        # Close the coroutine so pytest doesn't warn about un-awaited routes.
        coro.close()
        return None

    monkeypatch.setattr(
        "integrations.headless.claude_code.asyncio.run_coroutine_threadsafe",
        _fake,
    )
    return scheduled


@pytest.mark.asyncio
async def test_user_message_bridges_to_loop(make_runner, monkeypatch):
    scheduled = _capture_bridge(monkeypatch)
    runner = make_runner(vicoa_client=FakeAsyncVicoaClient())
    runner._loop = asyncio.get_running_loop()

    runner._on_ws_user_message({"id": "m1", "sender_type": "user", "content": "hello"})

    assert len(scheduled) == 1


@pytest.mark.asyncio
async def test_agent_echo_is_filtered(make_runner, monkeypatch):
    """The /ws broadcast includes AGENT echoes of our own POSTs. The
    callback must drop them — otherwise Claude would receive its own last
    reply as the next turn's user input."""
    scheduled = _capture_bridge(monkeypatch)
    runner = make_runner(vicoa_client=FakeAsyncVicoaClient())
    runner._loop = asyncio.get_running_loop()

    runner._on_ws_user_message(
        {"id": "m1", "sender_type": "agent", "content": "I just said this"}
    )

    assert scheduled == []


@pytest.mark.asyncio
async def test_empty_content_dropped(make_runner, monkeypatch):
    scheduled = _capture_bridge(monkeypatch)
    runner = make_runner(vicoa_client=FakeAsyncVicoaClient())
    runner._loop = asyncio.get_running_loop()

    runner._on_ws_user_message({"id": "m1", "sender_type": "user", "content": ""})

    assert scheduled == []


@pytest.mark.asyncio
async def test_callback_swallows_handler_exceptions(make_runner, monkeypatch):
    """If the asyncio bridge raises (e.g. loop closed mid-shutdown), the
    callback must not propagate — the WS reader thread would die silently
    and the connection would never reconnect."""

    class _OpenLoop:
        def is_closed(self) -> bool:
            return False

    runner = make_runner(vicoa_client=FakeAsyncVicoaClient())
    runner._loop = _OpenLoop()  # type: ignore[assignment]

    def _raise(coro, _loop):
        coro.close()  # avoid "coroutine was never awaited" RuntimeWarning
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "integrations.headless.claude_code.asyncio.run_coroutine_threadsafe",
        _raise,
    )

    # Must not raise.
    runner._on_ws_user_message({"id": "m1", "sender_type": "user", "content": "hello"})


@pytest.mark.asyncio
async def test_callback_no_op_when_loop_missing(make_runner, monkeypatch):
    """Pre-``run()`` (or post-shutdown) the loop reference is None; the
    callback should silently drop without invoking the bridge."""
    scheduled = _capture_bridge(monkeypatch)
    runner = make_runner(vicoa_client=FakeAsyncVicoaClient())
    runner._loop = None

    runner._on_ws_user_message({"id": "m1", "sender_type": "user", "content": "hello"})

    assert scheduled == []


# ---------------------------------------------------------------------------
# _schedule_message_update — cancellation-frame bridge (Task B5).
#
# Mirrors ``_on_ws_user_message`` above: fires on the sync WS reader thread
# and is wired as ``SessionMessagesWsClient(on_message_update=...)``. Unlike
# the user-message path it hops via ``call_soon_threadsafe`` (sync callback,
# no coroutine to schedule) straight into ``_on_ws_message_update``.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_message_update_bridges_to_loop(make_runner):
    runner = make_runner(vicoa_client=FakeAsyncVicoaClient())
    runner._loop = asyncio.get_running_loop()

    runner._schedule_message_update(
        {"id": "c-3", "message_metadata": {"queue": {"status": "cancelled"}}}
    )
    await asyncio.sleep(0)  # let the scheduled callback run on the loop

    assert "c-3" in runner._cancelled_message_ids


@pytest.mark.asyncio
async def test_schedule_message_update_no_op_when_loop_missing(make_runner):
    """Pre-``run()`` (or post-shutdown) the loop reference is None; the
    callback should silently drop without scheduling anything."""
    runner = make_runner(vicoa_client=FakeAsyncVicoaClient())
    runner._loop = None

    runner._schedule_message_update(
        {"id": "c-4", "message_metadata": {"queue": {"status": "cancelled"}}}
    )

    assert "c-4" not in runner._cancelled_message_ids
