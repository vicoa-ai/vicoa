"""ACP session resume: persist the agent's session id, reload it via session/load.

The ACP session id lives only in the wrapper's memory, so a conversation became
unresumable the moment the process exited — even for agents that advertise
``loadSession``. These tests pin both halves:

* the id is recorded on ``instance_metadata.acp_session_id`` when a session is
  created or loaded, so a later resume has something to target, and
* ``session/load`` is gated on the advertised capability.

The gate matters more than it looks. An agent that can't reload would answer
``session/load`` with an error, and falling back to ``session/new`` there would
hand the user a blank agent while the UI still shows the old transcript. Silent
context loss is worse than refusing to resume.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from integrations.headless.acp_base import ACPWrapperBase, ACPWrapperConfig
from integrations.headless.acp_client import ACPError

_INSTANCE_ID = "acp-inst-resume"
_SESSION_ID = "acp-sess-original"


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


def _response(
    result: Optional[Dict[str, Any]] = None, error: Optional[Dict[str, Any]] = None
) -> MagicMock:
    resp = MagicMock()
    resp.result = result
    resp.error = error
    resp.is_error = error is not None

    def _raise() -> None:
        if error is not None:
            raise ACPError(f"ACP Error {error.get('code')}: {error.get('message')}")

    resp.raise_for_error = MagicMock(side_effect=_raise)
    return resp


def _build_wrapper(
    *,
    capabilities: Optional[Dict[str, Any]] = None,
    vicoa_client: Optional[MagicMock] = None,
) -> ACPWrapperBase:
    wrapper: ACPWrapperBase = ACPWrapperBase.__new__(ACPWrapperBase)
    wrapper.config = _TestConfig()
    wrapper.vicoa_client = vicoa_client if vicoa_client is not None else MagicMock()
    wrapper.acp = MagicMock()
    wrapper.session_id = None
    wrapper.running = True
    wrapper.debug_log_file = None
    wrapper.agent_capabilities = capabilities if capabilities is not None else {}
    wrapper.auth_methods = []
    wrapper.available_modes = []
    wrapper.current_mode_id = None
    wrapper.available_models = []
    wrapper.current_model_id = None
    wrapper.session_config_options = []
    wrapper.available_commands = []
    wrapper._prompt_state_lock = threading.Lock()
    wrapper._prompt_in_flight = False
    wrapper._queued_prompts = []
    wrapper._prompt_cancel_event = threading.Event()
    wrapper._interrupt_active = False
    wrapper._permission_request_active = False
    wrapper._suspend_vicoa_polling = False
    wrapper._stopping = False
    wrapper._replaying_session = False
    wrapper.message_queue = []
    wrapper._awaiting_input_requested_for_message_id = None
    wrapper._awaiting_after_next_agent_output = False
    wrapper._assistant_chunk_buffer = ""
    wrapper._assistant_chunk_first_update_at = 0.0
    wrapper._assistant_chunk_last_update_at = 0.0
    wrapper._show_tool_updates = False
    wrapper._last_tool_change_signature = None
    return wrapper


def _patched_metadata(vicoa_client: MagicMock) -> Dict[str, Any]:
    """Merge every instance_metadata PATCH the wrapper issued."""
    merged: Dict[str, Any] = {}
    for call in vicoa_client.patch_agent_instance.call_args_list:
        meta = call.kwargs.get("instance_metadata")
        if meta:
            merged.update(meta)
    return merged


# --------------------------------------------------------------------------
# Capability gate
# --------------------------------------------------------------------------


def test_capability_is_read_from_the_handshake():
    assert _build_wrapper(capabilities={"loadSession": True}).supports_session_load
    assert not _build_wrapper(capabilities={"loadSession": False}).supports_session_load
    assert not _build_wrapper(capabilities={}).supports_session_load


def test_load_is_refused_when_the_agent_cannot_reload():
    """Must not attempt the call, and must not silently start a blank session
    that looks like a resumed one."""
    wrapper = _build_wrapper(capabilities={})
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]

    assert wrapper.load_session(_SESSION_ID) is False
    wrapper.acp.send_request.assert_not_called()


# --------------------------------------------------------------------------
# session/load
# --------------------------------------------------------------------------


def test_load_sends_session_load_with_the_stored_id():
    wrapper = _build_wrapper(capabilities={"loadSession": True})
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]
    wrapper.acp.send_request.return_value = _response({"sessionId": _SESSION_ID})

    assert wrapper.load_session(_SESSION_ID) is True

    method, params = wrapper.acp.send_request.call_args[0]
    assert method == "session/load"
    assert params["sessionId"] == _SESSION_ID
    assert params["cwd"] == "/tmp/test-project"
    assert wrapper.session_id == _SESSION_ID


def test_load_keeps_the_requested_id_when_the_agent_returns_no_result():
    """The spec allows an empty result; the id we asked for stays valid."""
    wrapper = _build_wrapper(capabilities={"loadSession": True})
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]
    wrapper.acp.send_request.return_value = _response(None)

    assert wrapper.load_session(_SESSION_ID) is True
    assert wrapper.session_id == _SESSION_ID


def test_load_reports_failure_rather_than_raising():
    """A deleted session file or an agent upgrade that changed its schema must
    degrade to a caller-visible False, mirroring codex's thread/resume."""
    wrapper = _build_wrapper(capabilities={"loadSession": True})
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]
    wrapper.acp.send_request.return_value = _response(
        error={"code": -32602, "message": "unknown session"}
    )

    assert wrapper.load_session(_SESSION_ID) is False


# --------------------------------------------------------------------------
# Persisting the id — without this, resume has nothing to target
# --------------------------------------------------------------------------


def test_created_session_id_is_persisted():
    vicoa_client = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vicoa_client)
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]
    wrapper.acp.send_request.return_value = _response({"sessionId": "sess-new"})

    wrapper.create_session()

    assert _patched_metadata(vicoa_client)["acp_session_id"] == "sess-new"


def test_loaded_session_id_is_persisted():
    """A reload can hand back a different id; the next resume must target the
    session the agent actually continued."""
    vicoa_client = MagicMock()
    wrapper = _build_wrapper(
        capabilities={"loadSession": True}, vicoa_client=vicoa_client
    )
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]
    wrapper.acp.send_request.return_value = _response({"sessionId": "sess-rotated"})

    assert wrapper.load_session(_SESSION_ID) is True
    assert _patched_metadata(vicoa_client)["acp_session_id"] == "sess-rotated"


def test_persist_uses_metadata_not_session_config():
    """session_config is display-only spawn config; a resume handle is
    operational state and belongs in instance_metadata."""
    vicoa_client = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vicoa_client)
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]
    wrapper.acp.send_request.return_value = _response({"sessionId": "sess-new"})

    wrapper.create_session()

    call = vicoa_client.patch_agent_instance.call_args
    assert "instance_metadata" in call.kwargs
    assert "session_config" not in call.kwargs


def test_persist_failure_never_breaks_bring_up():
    """Losing the id costs a future resume; it must not stop the session that
    is coming up right now."""
    vicoa_client = MagicMock()
    vicoa_client.patch_agent_instance.side_effect = RuntimeError("backend down")
    wrapper = _build_wrapper(vicoa_client=vicoa_client)
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]
    wrapper.acp.send_request.return_value = _response({"sessionId": "sess-new"})

    wrapper.create_session()  # must not raise

    assert wrapper.session_id == "sess-new"


# --------------------------------------------------------------------------
# Bring-up wiring: load when we have a handle, create otherwise
# --------------------------------------------------------------------------


def _bringup(wrapper: ACPWrapperBase) -> str:
    """Drive the real bring-up branch; report which ACP method it chose."""
    calls: list[str] = []

    def _record(method: str, _params: Dict[str, Any]) -> MagicMock:
        calls.append(method)
        return _response({"sessionId": "sess-x"})

    wrapper.acp.send_request.side_effect = _record
    wrapper._establish_session()
    return "load" if "session/load" in calls else "new"


def test_bringup_loads_when_a_handle_exists_and_the_agent_can():
    wrapper = _build_wrapper(capabilities={"loadSession": True})
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]
    wrapper.config.acp_session_id = _SESSION_ID

    assert _bringup(wrapper) == "load"


def test_bringup_creates_a_fresh_session_without_a_handle():
    """A normal spawn must be unaffected by the resume path."""
    wrapper = _build_wrapper(capabilities={"loadSession": True})
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]
    wrapper.config.acp_session_id = None

    assert _bringup(wrapper) == "new"


def test_bringup_falls_back_when_the_agent_cannot_reload():
    """Handle present but the agent lacks loadSession: start fresh rather than
    abort. The transcript stays visible either way, so bring-up must not fail."""
    wrapper = _build_wrapper(capabilities={})
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]
    wrapper.config.acp_session_id = _SESSION_ID

    assert _bringup(wrapper) == "new"


def test_is_resuming_is_independent_of_the_conversation_handle():
    """The two were conflated behind one --resume flag. is_resuming reattaches
    the Vicoa row; acp_session_id restores the agent's conversation. Reattaching
    without a handle must NOT imply a restored conversation."""
    wrapper = _build_wrapper(capabilities={"loadSession": True})
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]
    wrapper.config.is_resuming = True
    wrapper.config.acp_session_id = None

    assert _bringup(wrapper) == "new"


@pytest.mark.parametrize("missing", ["client", "instance_id"])
def test_persist_is_skipped_without_a_target(missing: str):
    vicoa_client = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vicoa_client)
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]
    if missing == "client":
        wrapper.vicoa_client = None
    else:
        wrapper.config.agent_instance_id = ""

    wrapper.session_id = "sess-new"
    wrapper._persist_acp_session_id()

    vicoa_client.patch_agent_instance.assert_not_called()


# --------------------------------------------------------------------------
# Transient agent errors must not surface as chat messages
# --------------------------------------------------------------------------


def test_retriable_error_is_not_shown_to_the_user():
    """Cursor emits "RetriableError: WritableIterable is closed" mid-stream and
    then answers normally. Forwarding it put an "Error:" bubble above a
    perfectly good reply, which reads as the agent having failed."""
    vicoa_client = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vicoa_client)
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]

    wrapper._handle_session_error(
        {"error": {"message": "RetriableError: WritableIterable is closed"}}
    )

    vicoa_client.send_message.assert_not_called()


def test_real_session_errors_are_still_shown():
    """The filter must stay narrow — anything it swallows is invisible."""
    vicoa_client = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vicoa_client)
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]

    wrapper._handle_session_error({"error": {"message": "Model overloaded"}})

    vicoa_client.send_message.assert_called_once()
    assert "Model overloaded" in vicoa_client.send_message.call_args.kwargs["content"]


@pytest.mark.parametrize(
    "message",
    [
        "RetriableError: WritableIterable is closed",
        "retriableerror: something else",
        "Stream failed: WritableIterable is closed",
    ],
)
def test_transient_matching_is_case_insensitive(message: str):
    assert ACPWrapperBase._is_transient_session_error(message) is True


@pytest.mark.parametrize(
    "message", ["Unknown error", "", "Permission denied", "context length exceeded"]
)
def test_ordinary_errors_are_not_treated_as_transient(message: str):
    assert ACPWrapperBase._is_transient_session_error(message) is False


def test_retriable_error_as_reply_text_is_not_forwarded():
    """Cursor also emits "RetriableError: WritableIterable is closed" as its
    *reply text* (not on session/error), then retries and answers. That path
    goes through ``_forward_agent_text`` and must be dropped just the same."""
    vicoa_client = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vicoa_client)
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]

    wrapper._forward_agent_text("Error: RetriableError: WritableIterable is closed")

    vicoa_client.send_message.assert_not_called()


@pytest.mark.parametrize(
    "text",
    [
        "Error: RetriableError: WritableIterable is closed",
        "RetriableError: WritableIterable is closed",
        "retriableerror: something else",
        "WritableIterable is closed",
    ],
)
def test_transient_agent_text_matches_whole_message(text: str):
    assert ACPWrapperBase._is_transient_agent_text(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Here's the fix for the RetriableError: WritableIterable is closed bug",
        "The build failed. Error: RetriableError: WritableIterable is closed\n\n"
        "Want me to retry?",
        "Done — everything passes now.",
    ],
)
def test_real_replies_are_not_dropped_as_transient(text: str):
    """A reply that merely *mentions* the error, or spans multiple lines, is a
    real message and must survive — only a whole-message error is dropped."""
    assert ACPWrapperBase._is_transient_agent_text(text) is False


# --------------------------------------------------------------------------
# session/load replays the prior conversation — it must not be re-recorded
# --------------------------------------------------------------------------


def test_replayed_updates_are_not_forwarded_during_load():
    """``session/load`` streams the whole prior conversation back through
    ``session/update`` so a client can rebuild its UI. Vicoa already has that
    transcript, so forwarding the replay appended a second copy of the
    conversation on every resume — observed with Cursor as one more agent reply
    each time Resume was clicked."""
    wrapper = _build_wrapper(capabilities={"loadSession": True})
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]
    forwarded: list[str] = []
    wrapper._append_assistant_chunk = lambda text: forwarded.append(text)  # type: ignore[method-assign]

    def _replay_then_respond(method: str, _params: Dict[str, Any]) -> MagicMock:
        # The agent replays while the request is still in flight.
        wrapper._handle_session_update(
            {
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"text": "old reply"},
                }
            }
        )
        return _response({"sessionId": _SESSION_ID})

    wrapper.acp.send_request.side_effect = _replay_then_respond

    assert wrapper.load_session(_SESSION_ID) is True
    assert forwarded == [], "replayed history must not be re-sent to Vicoa"


def test_updates_are_forwarded_again_after_the_load_completes():
    """The suppression is scoped to the replay — live output after it must
    still reach the user."""
    wrapper = _build_wrapper(capabilities={"loadSession": True})
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]
    wrapper.acp.send_request.return_value = _response({"sessionId": _SESSION_ID})

    wrapper.load_session(_SESSION_ID)

    assert wrapper._replaying_session is False


def test_replay_flag_clears_even_when_the_load_fails():
    """A failed load must not leave the wrapper permanently deaf to updates."""
    wrapper = _build_wrapper(capabilities={"loadSession": True})
    wrapper.log = lambda *_a, **_k: None  # type: ignore[method-assign]
    wrapper.acp.send_request.return_value = _response(
        error={"code": -32602, "message": "unknown session"}
    )

    assert wrapper.load_session(_SESSION_ID) is False
    assert wrapper._replaying_session is False
