"""Unit tests for JSONLMonitor handling of skill / project slash commands.

Two distinct shapes share the ``<command-name>`` element:

1. TUI built-in (`/model`, `/effort`, `/clear`, …) — has ``<command-args>``.
   Only mutates terminal state; the user already saw the result locally.
   Drop entirely; the ``<local-command-stdout>`` confirmation handles the
   visible result. Existing behavior, locked in by
   ``test_jsonl_monitor_cli_command_echo``.

2. Skill / project command (`/ideabrowser-daily-idea`, `.claude/commands/*.md`,
   …) — has ``<command-message>`` but NO ``<command-args>``. The next user
   entry is the expanded skill body (multi-KB structured content,
   intentionally not forwarded). Without this fix the typed command name is
   silently dropped — mobile/web shows an empty session, then a permission
   prompt for a Bash tool the user has no context for.
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


def _user_entry(content: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": content}}


def test_skill_command_forwarded_as_user_message() -> None:
    """Skill shape (no ``<command-args>``) — forward the typed command name
    so the user's intent is visible on mobile/web."""
    monitor, processor = _make_monitor()
    entry = _user_entry(
        "<command-message>ideabrowser-daily-idea</command-message>\n"
        "<command-name>/ideabrowser-daily-idea</command-name>"
    )

    monitor._process_entry(entry)

    processor.process_user_message.assert_called_once()
    kwargs = processor.process_user_message.call_args.kwargs
    assert kwargs["content"] == "/ideabrowser-daily-idea"
    assert kwargs["from_web"] is False
    processor.send_cli_command_echo.assert_not_called()


def test_skill_command_with_hyphens_extracted_in_full() -> None:
    """Skill names commonly include hyphens — the regex must capture them."""
    monitor, processor = _make_monitor()
    entry = _user_entry(
        "<command-message>find-skills</command-message>\n"
        "<command-name>/find-skills</command-name>"
    )

    monitor._process_entry(entry)

    processor.process_user_message.assert_called_once()
    assert processor.process_user_message.call_args.kwargs["content"] == "/find-skills"


def test_tui_builtin_with_empty_args_still_dropped() -> None:
    """Regression guard: existing ``<command-name>/model</command-name>
    <command-args></command-args>`` shape must still be dropped — same as
    before this fix. Locked alongside the existing CLI-echo suite."""
    monitor, processor = _make_monitor()
    entry = _user_entry(
        "<command-name>/model</command-name><command-args></command-args>"
    )

    monitor._process_entry(entry)

    processor.process_user_message.assert_not_called()
    processor.send_cli_command_echo.assert_not_called()


def test_tui_builtin_with_nonempty_args_still_dropped() -> None:
    """Regression guard: ``/effort high`` shape — dropped."""
    monitor, processor = _make_monitor()
    entry = _user_entry(
        "<command-name>/effort</command-name>\n"
        "<command-message>effort</command-message>\n"
        "<command-args>high</command-args>"
    )

    monitor._process_entry(entry)

    processor.process_user_message.assert_not_called()


def test_skill_command_with_no_extractable_name_is_dropped() -> None:
    """Malformed ``<command-name>`` (no slug captured) must not crash and
    must not forward something useless like an empty string."""
    monitor, processor = _make_monitor()
    entry = _user_entry(
        "<command-message>weird</command-message>\n<command-name></command-name>"
    )

    monitor._process_entry(entry)

    processor.process_user_message.assert_not_called()
