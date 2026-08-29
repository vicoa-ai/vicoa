"""Transport + session robustness for the native ``codex app-server`` path.

Covers the message/turn-flow hardening from
``plans/codex-session-robustness.md``:
* per-call request timeouts (``send_request(..., timeout=...)``)
* fail-pending-on-EOF when codex dies, with the stderr tail attached
* the ``on_close`` hook that unblocks a turn parked on its own future
* the session's silence-settle + unexpected-close handlers
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from integrations.headless.codex.transport import (
    CodexTransport,
    CodexTransportClosed,
)
from integrations.headless.codex_app_server import (
    CodexAppServerSession,
    _STATUS_AWAITING_INPUT,
)


class _FakeReader:
    """Queue-backed ``readline``; ``feed_eof`` makes it return b'' (EOF)."""

    def __init__(self) -> None:
        self._q: "asyncio.Queue[bytes | None]" = asyncio.Queue()

    async def readline(self) -> bytes:
        item = await self._q.get()
        return b"" if item is None else item

    def feed(self, line: bytes) -> None:
        self._q.put_nowait(line)

    def feed_eof(self) -> None:
        self._q.put_nowait(None)


class _FakeWriter:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:  # pragma: no cover - unused
        pass


async def test_send_request_times_out_and_clears_pending() -> None:
    reader, writer = _FakeReader(), _FakeWriter()
    transport = CodexTransport(reader, writer)
    await transport.start()
    try:
        with pytest.raises(TimeoutError):
            await transport.send_request("turn/start", {}, timeout=0.02)
        # A timed-out request must not leak its pending future.
        assert transport._pending == {}
        # The request was still written to the child.
        assert any(b"turn/start" in w for w in writer.writes)
    finally:
        await transport.aclose()


async def test_eof_fails_pending_with_stderr_tail_and_fires_on_close() -> None:
    reader, writer = _FakeReader(), _FakeWriter()
    closed_reasons: list[str] = []
    transport = CodexTransport(
        reader,
        writer,
        on_close=closed_reasons.append,
        stderr_tail=lambda: "thread 'main' panicked: boom",
    )
    await transport.start()

    req = asyncio.ensure_future(transport.send_request("model/list", {}))
    await asyncio.sleep(0)  # let send_request register its pending future
    reader.feed_eof()

    with pytest.raises(CodexTransportClosed) as excinfo:
        await req
    # The child's stderr tail is attached so the failure explains itself.
    assert "boom" in str(excinfo.value)
    assert closed_reasons and "boom" in closed_reasons[0]
    # After death the transport fast-fails new requests instead of hanging.
    with pytest.raises(CodexTransportClosed):
        await transport.send_request("turn/start", {})


async def test_aclose_does_not_fire_on_close() -> None:
    reader, writer = _FakeReader(), _FakeWriter()
    closed_reasons: list[str] = []
    transport = CodexTransport(reader, writer, on_close=closed_reasons.append)
    await transport.start()
    await transport.aclose()
    # Deliberate teardown must not look like an unexpected codex death.
    assert closed_reasons == []


def _make_session(thread_id: str | None = "thread-1") -> CodexAppServerSession:
    """Session wired to a never-started transport + an AsyncMock vicoa client."""
    reader, writer = _FakeReader(), _FakeWriter()
    transport = CodexTransport(reader, writer)
    return CodexAppServerSession(
        vicoa_client=AsyncMock(),
        instance_id="inst-1",
        cwd="/tmp",
        transport=transport,
        thread_id=thread_id,
    )


async def test_settle_stalled_turn_resolves_future_and_settles_status() -> None:
    session = _make_session()
    fut: "asyncio.Future[None]" = asyncio.get_running_loop().create_future()
    session._turn_completed = fut

    await session._settle_stalled_turn()

    assert fut.done() and fut.result() is None
    session.vicoa_client.update_agent_instance_status.assert_awaited_with(
        "inst-1", _STATUS_AWAITING_INPUT
    )


async def test_on_transport_closed_unparks_turn_and_reports() -> None:
    session = _make_session()
    fut: "asyncio.Future[None]" = asyncio.get_running_loop().create_future()
    session._turn_completed = fut

    session._on_transport_closed("codex app-server exited\nboom")
    assert fut.done()  # parked turn unblocked synchronously
    assert session._close_task is not None
    await session._close_task

    # Error surfaced to chat, then the row settled to AWAITING_INPUT.
    session.vicoa_client.send_message.assert_awaited()
    session.vicoa_client.update_agent_instance_status.assert_awaited_with(
        "inst-1", _STATUS_AWAITING_INPUT
    )


async def test_interrupt_waits_for_turn_identification() -> None:
    session = _make_session()
    session.transport.send_request = AsyncMock(return_value={})  # type: ignore[method-assign]
    # Simulate a turn/start in flight whose id hasn't landed yet.
    session._turn_start_pending = True
    session.active_turn_id = None
    session._turn_identified.clear()

    task = asyncio.ensure_future(session.interrupt())
    await asyncio.sleep(0.01)
    assert not task.done()  # blocked waiting for identification

    # Turn identifies mid-wait; interrupt should now target that turn.
    session.active_turn_id = "turn-42"
    session._turn_identified.set()
    await task

    session.transport.send_request.assert_awaited_once()
    method, params = session.transport.send_request.await_args.args
    assert method == "turn/interrupt"
    assert params["turnId"] == "turn-42"


async def test_interrupt_settles_when_no_turn() -> None:
    session = _make_session()
    session.transport.send_request = AsyncMock(return_value={})  # type: ignore[method-assign]
    session.active_turn_id = None
    session._turn_start_pending = False

    await session.interrupt()

    session.transport.send_request.assert_not_awaited()
    session.vicoa_client.update_agent_instance_status.assert_awaited_with(
        "inst-1", _STATUS_AWAITING_INPUT
    )
