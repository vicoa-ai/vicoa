"""Unit tests for ``integrations.headless.auq.AskUserQuestionRegistry``.

The registry is the Future-based fix for the §2g cursor race documented in
``docs/design/mcp-headless-refactor.md``. These tests cover its lookup
priority (request_id → message_id → FIFO) and its lifecycle (resolve, cancel,
cancel_all).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from integrations.headless.auq import AskUserQuestionRegistry


def _payload(
    *,
    request_id: str | None = None,
    message_id: str | None = None,
    cancelled: bool = False,
) -> Dict[str, Any]:
    """Build a decoded-reply dict shaped like ``auq.decode_reply`` returns."""
    return {
        "cancelled": cancelled,
        "answers": [],
        "display_answers": [],
        "request_id": request_id,
        "message_id": message_id,
    }


async def test_resolve_by_request_id():
    reg = AskUserQuestionRegistry()
    fut = reg.create("req-1")
    assert reg.resolve(_payload(request_id="req-1")) is True
    result = await fut
    assert result["request_id"] == "req-1"


async def test_resolve_by_message_id_when_bound():
    reg = AskUserQuestionRegistry()
    fut = reg.create("req-1")
    reg.bind_message_id("req-1", "msg-99")
    # Reply echoes only the message_id (legacy dashboards).
    assert reg.resolve(_payload(message_id="msg-99")) is True
    result = await fut
    assert result["message_id"] == "msg-99"


async def test_request_id_preferred_over_message_id():
    """When both ids match different pending futures, request_id wins."""
    reg = AskUserQuestionRegistry()
    other = reg.create("req-other")
    reg.bind_message_id("req-other", "msg-shared")
    target = reg.create("req-target")
    # Reply matches msg-shared (which is bound to ``other``) AND req-target.
    # request_id should win because it's more specific.
    assert reg.resolve(_payload(request_id="req-target", message_id="msg-shared"))
    result = await target
    assert result["request_id"] == "req-target"
    assert not other.done(), "non-target future must stay pending"


async def test_fifo_fallback_when_no_ids_match():
    """A reply that echoes neither id resolves the oldest pending future.

    Legacy clients (and the cancel control message, which has no payload
    json) hit this path. There's typically one AUQ in flight so this is
    unambiguous.
    """
    reg = AskUserQuestionRegistry()
    first = reg.create("req-first")
    second = reg.create("req-second")
    # Cancel-reply shape: cancelled=True, both ids None.
    assert reg.resolve(_payload(cancelled=True)) is True
    assert first.done()
    assert not second.done(), "FIFO must resolve only the oldest pending"


async def test_resolve_returns_false_when_empty():
    reg = AskUserQuestionRegistry()
    assert reg.resolve(_payload(request_id="ghost")) is False


async def test_cancel_clears_future_and_prevents_resolve():
    reg = AskUserQuestionRegistry()
    fut = reg.create("req-1")
    reg.bind_message_id("req-1", "msg-1")
    reg.cancel("req-1")
    assert fut.cancelled()
    # A late reply finds no pending future to resolve.
    assert reg.resolve(_payload(request_id="req-1")) is False
    assert reg.resolve(_payload(message_id="msg-1")) is False


async def test_cancel_all_cancels_every_pending():
    reg = AskUserQuestionRegistry()
    a = reg.create("a")
    b = reg.create("b")
    c = reg.create("c")
    reg.cancel_all()
    assert a.cancelled() and b.cancelled() and c.cancelled()
    # Subsequent resolves find nothing.
    assert reg.resolve(_payload(request_id="a")) is False


async def test_resolved_future_is_forgotten():
    """After resolve, the same ids no longer match anything."""
    reg = AskUserQuestionRegistry()
    fut = reg.create("req-1")
    reg.bind_message_id("req-1", "msg-1")
    assert reg.resolve(_payload(request_id="req-1"))
    await fut
    # Second resolve attempt with the same ids — no future left.
    assert reg.resolve(_payload(request_id="req-1")) is False
    assert reg.resolve(_payload(message_id="msg-1")) is False


async def test_concurrent_create_and_resolve():
    """A future awaited concurrently with resolve unblocks the awaiter."""
    reg = AskUserQuestionRegistry()
    fut = reg.create("req-1")

    async def resolver():
        await asyncio.sleep(0)
        reg.resolve(_payload(request_id="req-1"))

    task = asyncio.create_task(resolver())
    result = await fut
    await task

    assert result["request_id"] == "req-1"


async def test_bind_message_id_on_unknown_request_is_noop():
    reg = AskUserQuestionRegistry()
    # Should not raise.
    reg.bind_message_id("ghost", "msg-x")
    # And a later resolve targeting msg-x finds nothing.
    assert reg.resolve(_payload(message_id="msg-x")) is False


async def test_bind_message_id_none_is_noop():
    """``send_message`` may return a response without ``message_id``."""
    reg = AskUserQuestionRegistry()
    fut = reg.create("req-1")
    reg.bind_message_id("req-1", None)
    # request_id route still works.
    assert reg.resolve(_payload(request_id="req-1"))
    await fut
