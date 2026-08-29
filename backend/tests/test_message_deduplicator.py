"""Tests for MessageDeduplicator's time-bounded dedup behaviour.

The deduplicator suppresses SSE echoes of TUI inputs. Earlier behaviour kept
an unbounded set, which caused common short responses ("Yes" / "No" / "1")
to be silently dropped if the same string had been sent earlier in the
session via any channel. This module pins the corrected behaviour.
"""

import time

from integrations.cli_wrappers.claude_code.messaging.deduplicator import (
    MessageDeduplicator,
)


def test_recent_track_is_detected_as_duplicate() -> None:
    """An SSE echo arriving within the dedup window is suppressed."""
    dedup = MessageDeduplicator()
    dedup.track("1. Yes")

    assert dedup.is_duplicate("1. Yes") is True
    assert "1. Yes" in dedup


def test_old_track_does_not_falsely_suppress_later_send() -> None:
    """Regression for the 'Yes' UI-suppression bug.

    User answers a permission via TUI; much later, for a separate permission,
    they send the same short reply via the web UI. The earlier track must
    have aged out of the window so the later UI message is forwarded.
    """
    dedup = MessageDeduplicator()
    dedup.track("Yes")

    # Force the recent-window entry to look old (now 60 s window).
    cutoff = time.time() - dedup._recent_window_seconds - 1.0
    dedup._recent_messages.clear()
    dedup._recent_messages.append((cutoff, "Yes"))

    assert dedup.is_duplicate("Yes") is False
    assert "Yes" not in dedup


def test_late_sse_echo_within_window_still_suppressed() -> None:
    """Regression for the AUQ auto-resolution bug: SSE echo of a TUI input
    can arrive 15+ seconds after the TUI message was tracked. The window
    must be wide enough to catch echoes of that delay."""
    dedup = MessageDeduplicator()
    dedup.track("Ask me a question using AskUserQuestion")

    # Simulate echo arriving 20 s after track — well past the old 10 s window
    # but inside the new 60 s window.
    cutoff = time.time() - 20.0
    dedup._recent_messages.clear()
    dedup._recent_messages.append((cutoff, "Ask me a question using AskUserQuestion"))

    assert dedup.is_duplicate("Ask me a question using AskUserQuestion") is True


def test_whitespace_normalised_in_dedup_window() -> None:
    """Echo with cosmetic whitespace differences still matches a track."""
    dedup = MessageDeduplicator()
    dedup.track("1. Yes")

    assert dedup.is_duplicate("  1.   Yes  ") is True


def test_empty_content_is_not_a_duplicate() -> None:
    dedup = MessageDeduplicator()
    dedup.track("Yes")

    assert dedup.is_duplicate("") is False
    assert dedup.is_duplicate("   ") is False
