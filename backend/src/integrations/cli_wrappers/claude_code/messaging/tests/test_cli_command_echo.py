"""Unit tests for MessageProcessor.send_cli_command_echo.

CLI command echoes are TUI artifacts (slash commands the user types, and
their `<local-command-stdout>` confirmations) that show up in the Claude
jsonl as `user` entries but aren't real chat input. The monitor routes
them through `send_cli_command_echo` so they become AGENT messages
(sender_type=AGENT, requires_user_input=False) — preserving visibility
in the timeline without seeding session-title generation or being
re-dispatched into Claude's stdin.
"""

from __future__ import annotations

from typing import Any, List
from unittest.mock import MagicMock

from integrations.cli_wrappers.claude_code.messaging.processor import (
    MessageProcessor,
)


class _FakeClient:
    """Captures send_message calls (the AGENT-message path)."""

    def __init__(self) -> None:
        self.sent: List[dict[str, Any]] = []

    def send_message(
        self,
        *,
        content: str,
        agent_type: str,
        agent_instance_id: str,
        requires_user_input: bool,
    ) -> Any:
        self.sent.append(
            {
                "content": content,
                "agent_type": agent_type,
                "agent_instance_id": agent_instance_id,
                "requires_user_input": requires_user_input,
            }
        )
        return MagicMock(message_id="msg-1", queued_user_messages=None)


def _make_processor(client: _FakeClient | None) -> MessageProcessor:
    proc = MessageProcessor.__new__(MessageProcessor)
    proc.agent_instance_id = "test-instance"
    proc.agent_name = "Claude Code"
    proc.vicoa_client = client  # type: ignore[assignment]
    proc.log = lambda _msg: None  # noqa: E731
    return proc


def test_sends_as_agent_message_with_requires_user_input_false() -> None:
    client = _FakeClient()
    proc = _make_processor(client)

    proc.send_cli_command_echo(
        "<local-command-stdout>Set model to Opus 4.8 (1M context)"
        "</local-command-stdout>"
    )

    assert len(client.sent) == 1
    call = client.sent[0]
    assert call["agent_instance_id"] == "test-instance"
    assert call["agent_type"] == "Claude Code"
    assert call["requires_user_input"] is False
    assert "Set model to Opus 4.8" in call["content"]


def test_noop_when_vicoa_client_missing() -> None:
    """Defensive: replaying jsonl without a client must not raise."""
    proc = _make_processor(None)
    # Should be a quiet no-op, not an attribute error.
    proc.send_cli_command_echo("/model")


def test_swallows_client_exceptions() -> None:
    """A failing send must not kill the monitor thread."""

    class _BoomClient:
        def send_message(self, **_kwargs: Any) -> Any:
            raise RuntimeError("network down")

    proc = _make_processor(None)
    proc.vicoa_client = _BoomClient()  # type: ignore[assignment]

    # No exception propagates.
    proc.send_cli_command_echo("/model")
