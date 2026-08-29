"""End-to-end user-message delivery for ACP wrappers.

This is the path that carries *every* user message to an ACP agent:

    /ws new-message  ->  _on_ws_user_message  ->  _ingest_user_message
                     ->  message_queue        ->  drain  ->  send_prompt

Nothing covered it before. `test_ws_callback.py` exercises claude_code's
asyncio `_user_message_queue`, and `test_acp_base_protocol.py` stubs
`message_queue` without ever driving the callback into the drain. That gap let
a total delivery outage ship silently: `_on_ws_user_message` was updated to
pass a `message_id` while `_ingest_user_message` still took two arguments, so
every inbound message raised `TypeError` inside the callback's bare
`except Exception` and the queue stayed permanently empty. The session came
up, the initial prompt was persisted and visible in the transcript, and the
agent was never prompted at all.

These tests pin the producer/consumer contract (tuple arity included) so an
arity drift fails loudly here instead of silently in production.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from integrations.headless.acp_base import ACPWrapperBase, ACPWrapperConfig

_INSTANCE_ID = "acp-inst-delivery"
_MESSAGE_ID = "msg-0001"


class _TestConfig(ACPWrapperConfig):
    def __init__(self, **overrides: Any) -> None:
        self.api_key = "test-key"
        self.base_url = "http://localhost:8080"
        self.agent_instance_id = _INSTANCE_ID
        self.project_path = "/tmp/test-project"
        self.agent_type = "testagent"
        self.agent_command = "testagent"
        self.name = "TestAgent"
        self.is_resuming = False
        self.initial_prompt = None
        for key, value in overrides.items():
            setattr(self, key, value)

    def get_acp_command(self) -> list[str]:
        return ["testagent", "acp"]

    def get_acp_env(self) -> dict[str, str]:
        return {}


def _build_wrapper(vicoa_client: Optional[MagicMock] = None) -> ACPWrapperBase:
    wrapper: ACPWrapperBase = ACPWrapperBase.__new__(ACPWrapperBase)
    wrapper.config = _TestConfig()
    wrapper.vicoa_client = vicoa_client if vicoa_client is not None else MagicMock()
    wrapper.acp = MagicMock()
    wrapper._replaying_session = False
    wrapper._stopping = False
    wrapper.session_id = "sess-1"
    wrapper.running = True
    wrapper.debug_log_file = None
    wrapper.message_queue = []
    wrapper._suspend_vicoa_polling = False
    wrapper._prompt_state_lock = threading.Lock()
    wrapper._prompt_in_flight = False
    wrapper._queued_prompts = []
    wrapper._prompt_cancel_event = threading.Event()
    wrapper._interrupt_active = False
    wrapper._permission_request_active = False
    return wrapper


def _user_message(
    content: str = "hello agent",
    message_id: Optional[str] = _MESSAGE_ID,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """A `new-message` broadcast body as the wrapper receives it."""
    body: Dict[str, Any] = {
        "id": message_id,
        "content": content,
        "sender_type": "user",
        "message_metadata": metadata,
    }
    return body


# ---------------------------------------------------------------------------
# The callback must actually reach the queue
# ---------------------------------------------------------------------------


def test_ws_user_message_reaches_the_queue():
    """The regression guard. An arity mismatch here is invisible in production
    because the callback swallows every exception."""
    wrapper = _build_wrapper()

    wrapper._on_ws_user_message(_user_message())

    assert len(wrapper.message_queue) == 1, (
        "user message never reached message_queue — the WS callback swallowed "
        "an exception (likely an _ingest_user_message signature mismatch)"
    )


def test_queued_entry_shape_matches_the_drain():
    """Producer and consumer must agree on the tuple, or the drain raises
    ValueError and drops the message after popping it."""
    wrapper = _build_wrapper()

    wrapper._on_ws_user_message(_user_message())

    entry = wrapper.message_queue[0]
    assert len(entry) == 3
    message, attachments, message_id = entry  # must unpack exactly as :814 does
    assert message == "hello agent"
    assert attachments == ()
    assert message_id == _MESSAGE_ID


def test_message_id_is_threaded_through_for_the_consumed_stamp():
    """Without the id the queued-messages bar in the web UI never clears."""
    wrapper = _build_wrapper()

    wrapper._on_ws_user_message(_user_message(message_id="abc-123"))

    assert wrapper.message_queue[0][2] == "abc-123"


def test_missing_message_id_degrades_to_none():
    wrapper = _build_wrapper()

    wrapper._on_ws_user_message(_user_message(message_id=None))

    assert wrapper.message_queue[0][2] is None


# ---------------------------------------------------------------------------
# Filtering — the callback sees every broadcast on the session room
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sender", ["agent", "system", ""])
def test_non_user_senders_are_ignored(sender: str):
    """Agent echoes and instance-update frames share this room; only user
    messages are input."""
    wrapper = _build_wrapper()

    body = _user_message()
    body["sender_type"] = sender
    wrapper._on_ws_user_message(body)

    assert wrapper.message_queue == []


def test_empty_message_without_attachments_is_ignored():
    wrapper = _build_wrapper()

    wrapper._on_ws_user_message(_user_message(content=""))

    assert wrapper.message_queue == []


def test_suspended_polling_defers_delivery():
    """Permission long-polling reads queued messages inline; delivering here
    too would double-send the same turn."""
    wrapper = _build_wrapper()
    wrapper._suspend_vicoa_polling = True

    wrapper._on_ws_user_message(_user_message())

    assert wrapper.message_queue == []


# ---------------------------------------------------------------------------
# Consumed stamp — clears the web UI's queued-messages bar
# ---------------------------------------------------------------------------


def test_mark_message_consumed_calls_the_sdk():
    vicoa_client = MagicMock()
    wrapper = _build_wrapper(vicoa_client)

    wrapper._mark_message_consumed(_MESSAGE_ID)

    vicoa_client.mark_message_consumed.assert_called_once_with(_MESSAGE_ID)


def test_mark_message_consumed_skips_when_id_is_missing():
    vicoa_client = MagicMock()
    wrapper = _build_wrapper(vicoa_client)

    wrapper._mark_message_consumed(None)

    vicoa_client.mark_message_consumed.assert_not_called()


def test_mark_message_consumed_never_aborts_the_turn():
    """Queue bookkeeping is cosmetic; the user is waiting on the prompt."""
    vicoa_client = MagicMock()
    vicoa_client.mark_message_consumed.side_effect = RuntimeError("backend down")
    wrapper = _build_wrapper(vicoa_client)
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]

    wrapper._mark_message_consumed(_MESSAGE_ID)  # must not raise
