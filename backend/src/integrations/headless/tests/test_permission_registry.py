"""Unit tests for ``permission.PermissionReplyRegistry``.

The registry is the Future-based fix for the §2c permission-echo bug
documented in ``docs/design/mcp-headless-refactor.md``. Mirrors the AUQ
registry tests in shape but the future resolves to a plain reply string.
"""

from __future__ import annotations

import asyncio

from integrations.headless.permission import PermissionReplyRegistry


async def test_resolve_text_fifo():
    reg = PermissionReplyRegistry()
    fut = reg.create("req-1")
    assert reg.has_pending() is True
    assert reg.resolve_text("Allow once") is True
    assert await fut == "Allow once"
    assert reg.has_pending() is False


async def test_resolve_for_request_id():
    """Phase-2 path: a structured control reply carrying ``request_id``
    can target a specific pending future even if it's not at the FIFO head.
    """
    reg = PermissionReplyRegistry()
    older = reg.create("req-older")
    target = reg.create("req-target")
    assert reg.resolve_for_request("req-target", "Deny") is True
    assert await target == "Deny"
    assert not older.done(), "FIFO-older future must stay pending"


async def test_resolve_text_returns_false_when_empty():
    reg = PermissionReplyRegistry()
    assert reg.has_pending() is False
    assert reg.resolve_text("anything") is False


async def test_resolve_for_request_returns_false_for_unknown():
    reg = PermissionReplyRegistry()
    reg.create("req-1")
    assert reg.resolve_for_request("ghost", "x") is False


async def test_cancel_forgets_future():
    reg = PermissionReplyRegistry()
    fut = reg.create("req-1")
    reg.cancel("req-1")
    assert fut.cancelled()
    assert reg.has_pending() is False
    # Late reply finds nothing to resolve.
    assert reg.resolve_text("Allow once") is False
    assert reg.resolve_for_request("req-1", "x") is False


async def test_cancel_all_cancels_every_pending():
    reg = PermissionReplyRegistry()
    a = reg.create("a")
    b = reg.create("b")
    reg.cancel_all()
    assert a.cancelled() and b.cancelled()
    assert reg.resolve_text("Allow once") is False


async def test_resolved_future_is_forgotten():
    reg = PermissionReplyRegistry()
    fut = reg.create("req-1")
    assert reg.resolve_text("Deny")
    await fut
    # Second attempt with same ids — nothing left.
    assert reg.resolve_text("anything") is False
    assert reg.resolve_for_request("req-1", "x") is False


async def test_concurrent_create_and_resolve():
    reg = PermissionReplyRegistry()
    fut = reg.create("req-1")

    async def resolver():
        await asyncio.sleep(0)
        reg.resolve_text("Allow once")

    task = asyncio.create_task(resolver())
    result = await fut
    await task

    assert result == "Allow once"
