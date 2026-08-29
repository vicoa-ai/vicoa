"""Rate-limit chat notices must not repeat every turn.

Once a Claude window enters warning territory the CLI re-reports it on
effectively every turn; forwarding each event would post the same
"⚠️ Approaching 7-day rate limit" line for days. The notice gate keeps the
warning as a reminder — one chat message per escalation step (75/90/95%)
per window per reset period — while ``rejected`` always shows.

See integrations/headless/claude_code.py::_RateLimitNoticeGate.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("claude_agent_sdk", reason="claude-agent-sdk not installed")

from claude_agent_sdk import RateLimitEvent  # noqa: E402
from claude_agent_sdk.types import RateLimitInfo  # noqa: E402

from integrations.headless import claude_code  # noqa: E402

RESETS_AT = 1_770_000_000


def _event(
    status: Any = "allowed_warning",
    window: Any = "seven_day",
    utilization: float | None = 0.86,
    resets_at: int | None = RESETS_AT,
) -> RateLimitEvent:
    return RateLimitEvent(
        rate_limit_info=RateLimitInfo(
            status=status,
            resets_at=resets_at,
            rate_limit_type=window,
            utilization=utilization,
        ),
        uuid="uuid-1",
        session_id="session-1",
    )


def test_first_warning_notifies_then_repeats_stay_quiet():
    gate = claude_code._RateLimitNoticeGate()
    text = gate.text_for(_event(utilization=0.86))
    assert text is not None and "Approaching 7-day rate limit" in text

    # Same warning re-reported turn after turn: quiet until the next step.
    assert gate.text_for(_event(utilization=0.86)) is None
    assert gate.text_for(_event(utilization=0.87)) is None
    assert gate.text_for(_event(utilization=0.89)) is None


def test_each_escalation_step_notifies_once():
    gate = claude_code._RateLimitNoticeGate()
    assert gate.text_for(_event(utilization=0.76)) is not None  # crossed 75%
    assert gate.text_for(_event(utilization=0.89)) is None
    assert gate.text_for(_event(utilization=0.90)) is not None  # crossed 90%
    assert gate.text_for(_event(utilization=0.93)) is None
    assert gate.text_for(_event(utilization=0.96)) is not None  # crossed 95%
    assert gate.text_for(_event(utilization=0.99)) is None


def test_new_reset_period_rearms_the_notices():
    gate = claude_code._RateLimitNoticeGate()
    assert gate.text_for(_event(utilization=0.95)) is not None
    assert gate.text_for(_event(utilization=0.95)) is None

    # The window rolled over: same 75% crossing notifies again.
    next_period = RESETS_AT + 7 * 24 * 3600
    assert gate.text_for(_event(utilization=0.76, resets_at=next_period)) is not None
    assert gate.text_for(_event(utilization=0.76, resets_at=next_period)) is None


def test_windows_dedupe_independently():
    gate = claude_code._RateLimitNoticeGate()
    assert gate.text_for(_event(window="seven_day", utilization=0.86)) is not None
    assert gate.text_for(_event(window="five_hour", utilization=0.86)) is not None
    assert gate.text_for(_event(window="seven_day", utilization=0.86)) is None
    assert gate.text_for(_event(window="five_hour", utilization=0.86)) is None


def test_rejected_always_shows():
    gate = claude_code._RateLimitNoticeGate()
    assert gate.text_for(_event(utilization=0.96)) is not None

    # Hitting the wall must be visible on every attempt — the user needs to
    # know why the agent isn't responding.
    for _ in range(3):
        text = gate.text_for(_event(status="rejected", utilization=1.0))
        assert text is not None and "rate limit reached" in text


def test_allowed_transitions_stay_silent_and_do_not_consume_a_step():
    gate = claude_code._RateLimitNoticeGate()
    assert gate.text_for(_event(status="allowed", utilization=0.50)) is None
    # The suppressed "allowed" event must not have recorded state that would
    # swallow the first real warning.
    assert gate.text_for(_event(utilization=0.86)) is not None


def test_warning_without_utilization_notifies_once_per_period():
    gate = claude_code._RateLimitNoticeGate()
    assert gate.text_for(_event(utilization=None)) is not None
    assert gate.text_for(_event(utilization=None)) is None
    # Once a real figure crosses 75%, that step still fires.
    assert gate.text_for(_event(utilization=0.80)) is not None


def test_runner_routes_chat_notices_through_the_gate():
    # Both paths that can turn a RateLimitEvent into chat text — the main
    # stream loop and the sub-agent forward via format_message_content —
    # must share one gate, or dedupe state would diverge.
    import inspect

    src = inspect.getsource(claude_code.HeadlessClaudeRunner)
    assert src.count("_rate_limit_gate.text_for(") >= 2
    assert "_format_rate_limit_event(message)" not in src
