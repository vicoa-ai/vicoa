"""Multi-change settings dispatch — back-to-back control messages all apply.

Regression: the SSE listener used to ``await`` ``_handle_control_command``
inline. A ``model`` or ``effort`` change triggers ``_reconnect_claude_client``
which takes several seconds. During that await the ``async for`` over the
SSE stream was paused, so subsequent gear-pill changes from the app could
arrive while the listener was blocked. If the SSE keep-alive expired the
buffered events were lost; even when they survived, the second reconnect
fought with the SDK's internal session-ID state.

Fix: route control commands through ``_control_command_queue`` consumed by
a dedicated worker. SSE never blocks; controls process serially in order.
Interrupts bypass the queue (must preempt a slow reconnect in flight).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import List

import pytest

from _fakes import FakeAsyncVicoaClient


class _FakeClaudeClient:
    def __init__(self) -> None:
        self.set_permission_mode_calls: List[str] = []

    async def set_permission_mode(self, mode: str) -> None:
        self.set_permission_mode_calls.append(mode)


def _prime(runner) -> None:
    runner.model = "claude-sonnet-4-6"
    runner.thinking_effort = "low"
    runner.permission_mode = "default"
    runner.enable_thinking = False


# ---------------------------------------------------------------------------
# Queue + worker — the core regression test.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_back_to_back_controls_all_apply(make_runner, monkeypatch):
    """Three rapid-fire gear-pill changes (model / effort / permission_mode)
    must all take effect — even when the reconnect for the first is slow."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    _prime(runner)
    runner.claude_client = _FakeClaudeClient()

    # Slow reconnect — under the old inline-await code this would block the
    # SSE listener long enough to lose subsequent controls.
    async def _slow_reconnect() -> bool:
        await asyncio.sleep(0.02)
        return True

    monkeypatch.setattr(runner, "_reconnect_claude_client", _slow_reconnect)

    worker = asyncio.create_task(runner._run_control_worker())
    try:
        # The SSE listener calls _maybe_route_control_command for every
        # control message. With the queue, each returns immediately.
        await runner._maybe_route_control_command(
            '{"type":"control","setting":"model","value":"claude-opus-4-7"}'
        )
        await runner._maybe_route_control_command(
            '{"type":"control","setting":"effort","value":"high"}'
        )
        await runner._maybe_route_control_command(
            '{"type":"control","setting":"permission_mode","value":"acceptEdits"}'
        )
        # Drain. join() returns once every queued item is task_done.
        await asyncio.wait_for(runner._control_command_queue.join(), timeout=2.0)
    finally:
        runner.running = False
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

    assert runner.model == "claude-opus-4-7"
    assert runner.thinking_effort == "high"
    assert runner.permission_mode == "acceptEdits"
    # Each successful change flips the status row.
    awaiting = [c for c in fake.status_calls if c["status"] == "AWAITING_INPUT"]
    assert len(awaiting) == 3


@pytest.mark.asyncio
async def test_maybe_route_returns_immediately(make_runner, monkeypatch):
    """The SSE-listener entrypoint must NOT block on slow reconnect work.
    Without this, the async-for over the SSE stream is paused and
    subsequent events buffer (or worse, the server-side keep-alive
    expires and they're dropped)."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    _prime(runner)
    runner.claude_client = _FakeClaudeClient()

    # If the test ever reaches the reconnect, it would take 5s — but
    # _maybe_route_control_command must return long before that.
    async def _too_slow_reconnect() -> bool:
        await asyncio.sleep(5.0)
        return True

    monkeypatch.setattr(runner, "_reconnect_claude_client", _too_slow_reconnect)

    # No worker started — verify enqueue is non-blocking.
    handled = await asyncio.wait_for(
        runner._maybe_route_control_command(
            '{"type":"control","setting":"model","value":"claude-opus-4-7"}'
        ),
        timeout=0.5,
    )
    assert handled is True
    assert runner._control_command_queue.qsize() == 1


# ---------------------------------------------------------------------------
# Interrupt bypass — must preempt anything queued.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_interrupt_bypasses_queue(make_runner, monkeypatch):
    """Interrupt is time-sensitive — it must NOT wait behind a slow
    reconnect already running on the worker."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    _prime(runner)
    runner.claude_client = _FakeClaudeClient()

    inline_calls: List[str] = []
    original = runner._handle_control_command

    async def _spy(content: str):
        inline_calls.append(content)
        await original(content)

    monkeypatch.setattr(runner, "_handle_control_command", _spy)

    handled = await runner._maybe_route_control_command(
        '{"type":"control","setting":"interrupt"}'
    )

    assert handled is True
    # Interrupt was routed inline, NOT through the queue.
    assert inline_calls == ['{"type":"control","setting":"interrupt"}']
    assert runner._control_command_queue.empty()


# ---------------------------------------------------------------------------
# Worker dispatches in arrival order — last-write-wins semantics for the
# user (the order they tapped the gear pill).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_processes_in_arrival_order(make_runner, monkeypatch):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    _prime(runner)
    runner.claude_client = _FakeClaudeClient()

    async def _fast_reconnect() -> bool:
        return True

    monkeypatch.setattr(runner, "_reconnect_claude_client", _fast_reconnect)

    worker = asyncio.create_task(runner._run_control_worker())
    try:
        # Two model changes in sequence — final value should be the last.
        await runner._maybe_route_control_command(
            '{"type":"control","setting":"model","value":"claude-opus-4-7"}'
        )
        await runner._maybe_route_control_command(
            '{"type":"control","setting":"model","value":"claude-haiku-4-5"}'
        )
        await asyncio.wait_for(runner._control_command_queue.join(), timeout=2.0)
    finally:
        runner.running = False
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

    assert runner.model == "claude-haiku-4-5"
