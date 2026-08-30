"""Unit tests for JSONLMonitor handling of TUI queued-command entries.

The Claude TUI lets the user type a new prompt while Claude is still
working on the previous turn. That text is queued and lands in the jsonl
with a different schema than normal input:

    {"type": "queue-operation", "operation": "enqueue", "content": "<text>"}
    # later, when Claude drains the queue:
    {"type": "queue-operation", "operation": "remove"}
    {"type": "attachment", "attachment": {"type": "queued_command",
                                          "prompt": "<text>"}}

Without explicit handling, ``_process_entry`` falls through the
``type ∈ {user, assistant, summary, permission-mode, progress}`` branches
and the prompt is silently dropped — the backend never sees the message,
mobile/web shows nothing. These tests pin the contract: we forward on the
``enqueue`` step (treating it like a normal TUI user message) and ignore
the ``remove`` / ``queued_command attachment`` confirmations so the same
prompt isn't posted twice.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from integrations.cli_wrappers.claude_code.monitoring.jsonl_monitor import (
    JSONLMonitor,
)


INSTANCE_ID = "00000000-0000-0000-0000-000000000001"


def _make_monitor() -> tuple[JSONLMonitor, MagicMock]:
    processor = MagicMock()
    processor.suppress_cli_user_echo_until = 0.0
    monitor = JSONLMonitor.__new__(JSONLMonitor)
    monitor.agent_instance_id = INSTANCE_ID
    monitor.log = lambda _msg: None  # noqa: E731
    monitor.message_processor = processor
    monitor.message_queue = MagicMock()
    monitor.vicoa_client = None
    monitor._last_session_config = {}
    return monitor, processor


def test_queue_operation_enqueue_forwards_as_tui_user_message() -> None:
    """The user typed while Claude was busy; treat it like a normal TUI input
    so the backend (and therefore mobile/web) sees it."""
    monitor, processor = _make_monitor()
    entry = {
        "type": "queue-operation",
        "operation": "enqueue",
        "content": "comment it out instead of removing it.",
        "sessionId": INSTANCE_ID,
    }

    monitor._process_entry(entry)

    processor.process_user_message.assert_called_once()
    kwargs = processor.process_user_message.call_args.kwargs
    assert kwargs["content"] == "comment it out instead of removing it."
    assert kwargs["from_web"] is False


def test_queue_operation_remove_is_ignored() -> None:
    """The ``remove`` event marks queue drain — same content was already
    forwarded on enqueue. Forwarding again here would double-post."""
    monitor, processor = _make_monitor()
    entry = {
        "type": "queue-operation",
        "operation": "remove",
        "content": "",
        "sessionId": INSTANCE_ID,
    }

    monitor._process_entry(entry)

    processor.process_user_message.assert_not_called()
    processor.send_cli_command_echo.assert_not_called()


def test_queue_operation_enqueue_with_empty_content_is_ignored() -> None:
    """Defensive guard: never post empty/whitespace queued prompts."""
    monitor, processor = _make_monitor()
    entry = {
        "type": "queue-operation",
        "operation": "enqueue",
        "content": "   \n  ",
        "sessionId": INSTANCE_ID,
    }

    monitor._process_entry(entry)

    processor.process_user_message.assert_not_called()


def test_queued_command_attachment_is_ignored() -> None:
    """Claude re-emits the queued prompt as an ``attachment`` when it drains
    the queue. We already forwarded on enqueue — this confirmation must not
    produce a second message."""
    monitor, processor = _make_monitor()
    entry = {
        "type": "attachment",
        "attachment": {
            "type": "queued_command",
            "prompt": "comment it out instead of removing it.",
        },
    }

    monitor._process_entry(entry)

    processor.process_user_message.assert_not_called()
    processor.send_cli_command_echo.assert_not_called()
