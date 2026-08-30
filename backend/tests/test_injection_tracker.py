"""Tests for InjectionTracker's consume-once FIFO semantics.

The tracker fixes the UI→Claude→JSONL echo duplication: when a user message
is injected into Claude's input queue, Claude transcribes it into JSONL, and
without the tracker the JSONL monitor would create a second copy of the
message in the backend database.

Set-based dedup can't solve this without breaking legitimate repeated short
replies (e.g., two "No" clicks on consecutive permission prompts). The
tracker gives each injection its own slot.
"""

import time

from integrations.cli_wrappers.claude_code.messaging.injection_tracker import (
    InjectionTracker,
)


def test_inject_then_consume() -> None:
    t = InjectionTracker()
    t.mark_injected("Create a file text.txt")

    assert t.try_consume_echo("Create a file text.txt") is True
    # Slot is gone after consume.
    assert t.try_consume_echo("Create a file text.txt") is False


def test_two_identical_injections_consume_independently() -> None:
    """Regression: user clicks 'No' on two consecutive permission prompts.

    Each click is a legitimate UI message stored separately in the DB and
    forwarded separately into Claude. Each JSONL echo must consume its own
    slot; the second echo must not be wrongly suppressed by leftover state
    from the first, and the second click must not be wrongly suppressed by
    the first click's slot.
    """
    t = InjectionTracker()
    t.mark_injected("No")
    t.mark_injected("No")
    assert t.pending_count() == 2

    assert t.try_consume_echo("No") is True
    assert t.pending_count() == 1
    assert t.try_consume_echo("No") is True
    assert t.pending_count() == 0
    # A third echo (e.g., Claude re-typed the word on its own) is not
    # suppressed — no slot left to consume.
    assert t.try_consume_echo("No") is False


def test_echo_without_injection_is_not_consumed() -> None:
    """A CLI-originated user message (user typed directly in TUI) has no
    injection slot and must be forwarded to Vicoa normally."""
    t = InjectionTracker()
    assert t.try_consume_echo("user typed this in the terminal") is False


def test_normalization_collapses_whitespace() -> None:
    t = InjectionTracker()
    t.mark_injected("hello   world")
    # Claude may rewrap whitespace when echoing into JSONL.
    assert t.try_consume_echo("hello world") is True


def test_empty_content_is_ignored() -> None:
    t = InjectionTracker()
    t.mark_injected("")
    t.mark_injected("   ")
    assert t.pending_count() == 0
    assert t.try_consume_echo("") is False


def test_expired_entries_trimmed() -> None:
    """Entries older than the window must be dropped so a never-consumed
    injection (e.g., Claude crashed) doesn't linger forever and accidentally
    suppress an unrelated identical message minutes later."""
    t = InjectionTracker(window_seconds=60.0)
    t.mark_injected("stale message")
    # Backdate the only entry to before the window.
    _, content = t._pending[0]
    t._pending[0] = (time.time() - 61.0, content)

    assert t.try_consume_echo("stale message") is False
    assert t.pending_count() == 0


def test_max_pending_bounds_memory() -> None:
    """Pathological injection burst is capped by the deque maxlen so the
    process can never OOM from unconsumed entries."""
    t = InjectionTracker(max_pending=10)
    for i in range(50):
        t.mark_injected(f"msg {i}")

    # Only the last 10 fit; oldest 40 were evicted by the deque.
    assert t.pending_count() == 10
    # First one to survive should be msg 40.
    assert t.try_consume_echo("msg 40") is True
    assert t.try_consume_echo("msg 39") is False  # evicted


def test_fifo_match_picks_oldest_first() -> None:
    """When multiple slots match the same content, the oldest is consumed
    first (deterministic FIFO order)."""
    t = InjectionTracker()
    t.mark_injected("hi")
    first_ts = t._pending[0][0]
    time.sleep(0.01)
    t.mark_injected("hi")
    second_ts = t._pending[1][0]
    assert second_ts > first_ts

    t.try_consume_echo("hi")
    # The surviving slot is the newer one.
    assert t._pending[0][0] == second_ts
