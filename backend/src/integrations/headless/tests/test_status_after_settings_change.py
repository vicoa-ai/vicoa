"""After a successful mid-session settings change (model / effort /
permission_mode), the runner must flip the agent_instance status to
``AWAITING_INPUT``.

Why: the change is driven from the mobile app while the session is idle.
Without the flip, the mobile UI keeps showing whatever status the row had
before the toggle (frequently ``ACTIVE`` from the prior turn), and the
list / chat header looks stale until the next message arrives.

Failed changes (e.g. SDK reconnect raised) must NOT flip — the session is
in an undefined state, not "ready for input".
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from _fakes import FakeAsyncVicoaClient


# ---------------------------------------------------------------------------
# Minimal Claude-client double. The runner only calls .set_permission_mode
# on the permission_mode arm; the model / effort arms call
# _reconnect_claude_client which we patch out per-test.
# ---------------------------------------------------------------------------


class _FakeClaudeClient:
    def __init__(self) -> None:
        self.set_permission_mode_calls: List[str] = []

    async def set_permission_mode(self, mode: str) -> None:
        self.set_permission_mode_calls.append(mode)


def _prime_settings(runner) -> None:
    """Attach the attributes the model/effort/permission_mode arms read."""
    runner.model = "claude-sonnet-4-6"
    runner.thinking_effort = "low"
    runner.permission_mode = "default"
    runner.enable_thinking = False


async def _patch_reconnect(monkeypatch, runner, *, success: bool) -> None:
    """Stub _reconnect_claude_client so model / effort tests don't spin up the SDK."""

    async def _fake_reconnect() -> bool:
        return success

    monkeypatch.setattr(runner, "_reconnect_claude_client", _fake_reconnect)


# ---------------------------------------------------------------------------
# Permission-mode change.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permission_mode_change_flips_status_to_awaiting_input(make_runner):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    _prime_settings(runner)
    runner.claude_client = _FakeClaudeClient()

    handled = await runner._handle_control_command(
        '{"type":"control","setting":"permission_mode","value":"acceptEdits"}'
    )

    assert handled is True
    assert _last_status(fake) == "AWAITING_INPUT"


@pytest.mark.asyncio
async def test_invalid_permission_mode_does_not_flip_status(make_runner):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    _prime_settings(runner)
    runner.claude_client = _FakeClaudeClient()

    await runner._handle_control_command(
        '{"type":"control","setting":"permission_mode","value":"bogus"}'
    )

    assert fake.status_calls == []


# ---------------------------------------------------------------------------
# Model change.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_model_change_flips_status_to_awaiting_input(make_runner, monkeypatch):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    _prime_settings(runner)
    await _patch_reconnect(monkeypatch, runner, success=True)

    handled = await runner._handle_control_command(
        '{"type":"control","setting":"model","value":"claude-opus-4-7"}'
    )

    assert handled is True
    assert _last_status(fake) == "AWAITING_INPUT"


@pytest.mark.asyncio
async def test_model_change_no_op_does_not_flip_status(make_runner):
    """Same value as already set — runner short-circuits with "Model is already
    X" feedback and must not pretend the session just became idle."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    _prime_settings(runner)

    await runner._handle_control_command(
        '{"type":"control","setting":"model","value":"claude-sonnet-4-6"}'
    )

    assert fake.status_calls == []


@pytest.mark.asyncio
async def test_model_change_failure_does_not_flip_status(make_runner, monkeypatch):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    _prime_settings(runner)
    await _patch_reconnect(monkeypatch, runner, success=False)

    await runner._handle_control_command(
        '{"type":"control","setting":"model","value":"claude-opus-4-7"}'
    )

    assert fake.status_calls == []


# ---------------------------------------------------------------------------
# Effort change.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_effort_change_flips_status_to_awaiting_input(make_runner, monkeypatch):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    _prime_settings(runner)
    await _patch_reconnect(monkeypatch, runner, success=True)

    handled = await runner._handle_control_command(
        '{"type":"control","setting":"effort","value":"high"}'
    )

    assert handled is True
    assert _last_status(fake) == "AWAITING_INPUT"


@pytest.mark.asyncio
async def test_effort_change_failure_does_not_flip_status(make_runner, monkeypatch):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    _prime_settings(runner)
    await _patch_reconnect(monkeypatch, runner, success=False)

    await runner._handle_control_command(
        '{"type":"control","setting":"effort","value":"high"}'
    )

    assert fake.status_calls == []


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _last_status(fake: FakeAsyncVicoaClient) -> str:
    assert fake.status_calls, "expected at least one update_agent_instance_status call"
    call: Dict[str, Any] = fake.status_calls[-1]
    return call["status"]
