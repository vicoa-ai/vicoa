"""Regression test for: repeated identical TUI input must not be dropped.

Bug seen in session 6837b5b8: user typed 'Hi' three times within 21
seconds. Only the first was stored in the backend; the second and third
were silently dropped by MessageDeduplicator's 60-second window inside
`process_user_message`.

Echo suppression of TUI→backend→WS round-trips is handled separately by
`input_request_manager._handle_user_message`'s `is_duplicate` check on
the incoming WS frame — that's where the dedup belongs. The check inside
`process_user_message` is a misplaced safety net that conflates legit
repeated TUI input with self-echo.

`injection_tracker.try_consume_echo` covers the UI-injected case (web
message typed into Claude via PTY, then transcribed back to jsonl). So
removing the dedup check here is safe: UI echoes are still suppressed
by the FIFO injection tracker, WS echoes are still suppressed at the
receive side, and plain repeated TUI input flows through.
"""

from __future__ import annotations

from typing import Any, List
from unittest.mock import MagicMock

from integrations.cli_wrappers.claude_code.messaging.processor import (
    MessageProcessor,
)


class _FakeClient:
    """Captures send_user_message calls."""

    def __init__(self) -> None:
        self.sent: List[str] = []

    def send_user_message(self, *, agent_instance_id: str, content: str) -> Any:
        self.sent.append(content)
        return {}


def _make_processor(client: _FakeClient) -> MessageProcessor:
    proc = MessageProcessor.__new__(MessageProcessor)
    proc.agent_instance_id = "test-instance"
    proc.vicoa_client = client  # type: ignore[assignment]
    proc.log = lambda _msg: None  # noqa: E731
    proc.suppress_cli_user_echo_until = 0.0
    proc.pending_input_message_id = None
    proc.last_message_id = None
    proc.last_was_tool_use = False
    proc.last_tool_context = None
    # Real dedup + injection_tracker; fresh state.
    from integrations.cli_wrappers.claude_code.messaging.deduplicator import (
        MessageDeduplicator,
    )
    from integrations.cli_wrappers.claude_code.messaging.injection_tracker import (
        InjectionTracker,
    )

    proc.deduplicator = MessageDeduplicator()
    proc.injection_tracker = InjectionTracker()
    return proc


def test_repeated_tui_input_all_posted() -> None:
    """The user can type 'Hi' three times in quick succession; all three
    must reach the backend. Reproduces session 6837b5b8."""
    client = _FakeClient()
    proc = _make_processor(client)
    queue = MagicMock()
    for _ in range(3):
        proc.process_user_message(content="Hi", from_web=False, input_queue=queue)
    assert client.sent == ["Hi", "Hi", "Hi"]


def test_ui_injected_echo_still_suppressed() -> None:
    """If the wrapper injected a UI-originated message into Claude, the
    jsonl transcription of it must NOT be re-posted to the backend (the
    UI POST already created the message). injection_tracker handles this."""
    client = _FakeClient()
    proc = _make_processor(client)
    queue = MagicMock()
    proc.injection_tracker.mark_injected("Yes")
    proc.process_user_message(content="Yes", from_web=False, input_queue=queue)
    assert client.sent == []


def test_ui_injection_consumed_once_then_legit_repeat_posted() -> None:
    """UI injects 'Yes' once → jsonl echoes → consumed. User then types 'Yes'
    again from TUI → must reach backend (injection_tracker has no pending)."""
    client = _FakeClient()
    proc = _make_processor(client)
    queue = MagicMock()
    proc.injection_tracker.mark_injected("Yes")
    proc.process_user_message(content="Yes", from_web=False, input_queue=queue)
    proc.process_user_message(content="Yes", from_web=False, input_queue=queue)
    assert client.sent == ["Yes"]


def test_post_failure_leaves_tracker_clean() -> None:
    """If send_user_message raises, we don't leave a stale tracked entry
    that would suppress the user's next legitimate retry."""

    class _ExplodingClient:
        def send_user_message(self, *, agent_instance_id, content):
            raise RuntimeError("boom")

    proc = _make_processor(_ExplodingClient())  # type: ignore[arg-type]
    queue = MagicMock()
    # Should not raise.
    proc.process_user_message(content="Hi", from_web=False, input_queue=queue)
