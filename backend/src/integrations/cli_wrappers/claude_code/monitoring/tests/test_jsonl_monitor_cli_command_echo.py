"""Unit tests for how JSONLMonitor handles TUI slash-command artifacts.

Two related jsonl entries fire when a user uses a TUI command like `/model`:

1. `<command-name>/X</command-name><command-args>...</command-args>` — the
   raw slash-command the user typed. Local to the terminal; the user
   already saw it. Dropped entirely.
2. `<local-command-stdout>...</local-command-stdout>` — the command's
   stdout confirmation (e.g. "Set model to Opus 4.8 (1M context)").
   Forwarded as an AGENT message so it's visible in the timeline without
   seeding session-title generation, dedup tracking, or being
   re-dispatched into Claude's stdin.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from integrations.cli_wrappers.claude_code.monitoring.jsonl_monitor import (
    JSONLMonitor,
)


INSTANCE_ID = "00000000-0000-0000-0000-000000000001"


def _make_monitor() -> tuple[JSONLMonitor, MagicMock]:
    """Build a JSONLMonitor bypassing __init__ — sets only the attributes the
    user-entry path reads. Returns both the monitor and the processor mock so
    callers can assert on it directly (avoids Pyright complaining about
    MagicMock attributes on the typed MessageProcessor field).
    """
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


def _user_entry(content: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": content}}


def test_local_command_stdout_routes_to_send_cli_command_echo() -> None:
    """Set-model stdout becomes an AGENT message, not a user message."""
    monitor, processor = _make_monitor()
    entry = _user_entry(
        "<local-command-stdout>Set model to Opus 4.8 (1M context)"
        "</local-command-stdout>"
    )

    monitor._process_entry(entry)

    processor.send_cli_command_echo.assert_called_once()
    call_arg = processor.send_cli_command_echo.call_args.args[0]
    assert "Set model to Opus 4.8" in call_arg
    processor.process_user_message.assert_not_called()


def test_command_name_block_is_dropped_entirely() -> None:
    """`/model` typed in the TUI must not surface in the timeline — the user
    already saw it locally, and forwarding it as either USER or AGENT just
    adds noise. The stdout confirmation handles the visible state change."""
    monitor, processor = _make_monitor()
    entry = _user_entry(
        "<command-name>/model</command-name><command-args></command-args>"
    )

    monitor._process_entry(entry)

    processor.send_cli_command_echo.assert_not_called()
    processor.process_user_message.assert_not_called()


def test_command_name_block_with_args_is_dropped_entirely() -> None:
    """Same rule when the slash command carries args — drop, don't echo."""
    monitor, processor = _make_monitor()
    entry = _user_entry(
        "<command-name>/effort</command-name><command-args>high</command-args>"
    )

    monitor._process_entry(entry)

    processor.send_cli_command_echo.assert_not_called()
    processor.process_user_message.assert_not_called()


def test_empty_local_command_stdout_is_skipped_entirely() -> None:
    """Pre-existing behavior — empty stdout produces nothing at all."""
    monitor, processor = _make_monitor()
    entry = _user_entry("<local-command-stdout></local-command-stdout>")

    monitor._process_entry(entry)

    processor.send_cli_command_echo.assert_not_called()
    processor.process_user_message.assert_not_called()


def test_plain_user_message_still_routes_to_process_user_message() -> None:
    """Real user input must continue through the user-message path so that
    title generation / dispatch into Claude / dedup tracking all still run."""
    monitor, processor = _make_monitor()
    entry = _user_entry("Please fix the auth bug")

    monitor._process_entry(entry)

    processor.send_cli_command_echo.assert_not_called()
    processor.process_user_message.assert_called_once()
    call_kwargs = processor.process_user_message.call_args.kwargs
    assert call_kwargs["content"] == "Please fix the auth bug"
    assert call_kwargs["from_web"] is False
