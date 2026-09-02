"""Behavioral tests for the generic ACP layer (spec conformance hardening).

Covers the ACP v1 surface the base wrapper speaks for every ACP agent
(cursor / gemini / copilot / kimi / hermes / opencode):

* initialize handshake shape + capability storage
* generic session/new (+ authenticate retry, modes/configOptions state)
* prompt-turn stopReason handling and session status flow
* session/set_mode switching + current_mode_update
* permission decision → status transitions
* unknown agent→client requests → JSON-RPC method-not-found

Test idiom mirrors test_opencode_acp_control.py: wrappers are built via
``__new__`` with mocked ACP + Vicoa clients, and behavior is asserted on
the wire (send_request calls) and externally visible state.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from integrations.headless.acp_base import ACPWrapperBase, ACPWrapperConfig
from integrations.headless.acp_client import ACPError, ACPMethodNotFound


_INSTANCE_ID = "acp-inst-001"
_SESSION_ID = "acp-sess-abc"


class _TestConfig(ACPWrapperConfig):
    """Minimal concrete config for exercising the base wrapper."""

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
    """Build a fake ACPResponse-like object."""
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
    config: Optional[_TestConfig] = None,
    vicoa_client: Optional[MagicMock] = None,
) -> ACPWrapperBase:
    wrapper: ACPWrapperBase = ACPWrapperBase.__new__(ACPWrapperBase)
    wrapper.config = config or _TestConfig()
    wrapper.vicoa_client = vicoa_client if vicoa_client is not None else MagicMock()
    wrapper.acp = MagicMock()
    wrapper._replaying_session = False
    wrapper._startup_complete = True
    wrapper._stopping = False
    wrapper.session_id = None
    wrapper.last_message_id = None
    wrapper.running = True
    wrapper.debug_log_file = None

    # Handshake / session state
    wrapper.agent_capabilities = {}
    wrapper.auth_methods = []
    wrapper.negotiated_protocol_version = None
    wrapper.available_modes = []
    wrapper.current_mode_id = None
    wrapper.available_models = []
    wrapper.current_model_id = None
    wrapper.session_config_options = []
    wrapper.available_commands = []

    # Prompt / permission state
    wrapper._prompt_state_lock = threading.Lock()
    wrapper._prompt_in_flight = False
    wrapper._queued_prompts = []
    wrapper._prompt_cancel_event = threading.Event()
    wrapper._interrupt_active = False
    wrapper._permission_request_active = False
    wrapper._suspend_vicoa_polling = False
    wrapper.message_queue = []
    wrapper._cancelled_message_ids = set()

    # Streaming state
    wrapper._awaiting_input_requested_for_message_id = None
    wrapper._awaiting_after_next_agent_output = False
    wrapper._turn_produced_output = False
    wrapper._turn_stderr = deque(maxlen=20)
    wrapper._drop_stream_output_until_next_prompt = False
    wrapper._assistant_chunk_buffer = ""
    wrapper._thought_chunk_buffer = ""
    wrapper._assistant_chunk_first_update_at = 0.0
    wrapper._assistant_chunk_last_update_at = 0.0
    wrapper._show_tool_updates = False
    wrapper._last_tool_change_signature = None
    wrapper._tool_output_max_lines = 80
    wrapper._tool_output_max_chars = 4000
    wrapper._tool_output_preview_lines = 24
    wrapper._tool_output_preview_chars = 1400
    return wrapper


def _feedback_texts(vicoa_client: MagicMock) -> list[str]:
    return [
        call.kwargs.get("content", "")
        for call in vicoa_client.send_message.call_args_list
    ]


# ---------------------------------------------------------------------------
# initialize handshake — tracer bullet
# ---------------------------------------------------------------------------


def test_initialize_sends_spec_payload_and_stores_capabilities() -> None:
    """initialize must follow ACP v1: integer protocolVersion 1,
    clientCapabilities with explicit fs/terminal flags, clientInfo — and the
    agent's advertised capabilities + authMethods must be retained."""
    wrapper = _build_wrapper()
    wrapper.acp.send_request.return_value = _response(
        result={
            "protocolVersion": 1,
            "agentCapabilities": {"loadSession": True},
            "authMethods": [{"id": "oauth", "name": "Log in"}],
        }
    )

    wrapper._initialize_acp_session()

    call = wrapper.acp.send_request.call_args
    assert call.args[0] == "initialize"
    payload = call.args[1]
    assert payload["protocolVersion"] == 1
    assert payload["clientCapabilities"] == {
        "fs": {"readTextFile": False, "writeTextFile": False},
        "terminal": False,
    }
    assert payload["clientInfo"]["name"] == "vicoa"
    assert wrapper.agent_capabilities == {"loadSession": True}
    assert wrapper.auth_methods == [{"id": "oauth", "name": "Log in"}]


def test_initialize_uses_configurable_timeout() -> None:
    """Slow-starting agents (Gemini) need a longer initialize window."""
    wrapper = _build_wrapper(config=_TestConfig(initialize_timeout_seconds=180.0))
    wrapper.acp.send_request.return_value = _response(result={"protocolVersion": 1})

    wrapper._initialize_acp_session()

    assert wrapper.acp.send_request.call_args.kwargs["timeout"] == 180.0


# ---------------------------------------------------------------------------
# generic session/new
# ---------------------------------------------------------------------------


def test_create_session_sends_spec_params_and_stores_session_state() -> None:
    """session/new must carry cwd + mcpServers; sessionId, modes and
    configOptions from the response must be retained."""
    wrapper = _build_wrapper()
    wrapper.acp.send_request.return_value = _response(
        result={
            "sessionId": _SESSION_ID,
            "modes": {
                "currentModeId": "agent",
                "availableModes": [
                    {"id": "agent", "name": "Agent"},
                    {"id": "plan", "name": "Plan"},
                ],
            },
            "configOptions": [
                {"id": "model", "category": "model", "currentValue": "auto"}
            ],
        }
    )

    wrapper.create_session()

    call = wrapper.acp.send_request.call_args_list[0]
    assert call.args[0] == "session/new"
    assert call.args[1]["cwd"] == "/tmp/test-project"
    assert call.args[1]["mcpServers"] == []
    assert wrapper.session_id == _SESSION_ID
    assert wrapper.current_mode_id == "agent"
    assert [m["id"] for m in wrapper.available_modes] == ["agent", "plan"]
    assert wrapper.session_config_options[0]["category"] == "model"


def _reported_session_config(vc: MagicMock) -> Dict[str, Any]:
    """Merge of every session_config PATCH the wrapper issued."""
    merged: Dict[str, Any] = {}
    for call in vc.patch_agent_instance.call_args_list:
        sc = call.kwargs.get("session_config")
        if isinstance(sc, dict):
            merged.update(sc)
    return merged


def test_create_session_reports_live_modes_and_models() -> None:
    """The wrapper must surface the agent's live availableModes/availableModels
    (from session/new) onto session_config so the mobile gear can render real
    pickers instead of catalog guesses."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.acp.send_request.return_value = _response(
        result={
            "sessionId": _SESSION_ID,
            "modes": {
                "currentModeId": "agent",
                "availableModes": [
                    {"id": "agent", "name": "Agent"},
                    {"id": "plan", "name": "Plan"},
                ],
            },
            "models": {
                "currentModelId": "m1",
                "availableModels": [
                    {"modelId": "m1", "name": "Model One"},
                    {"modelId": "m2", "name": "Model Two"},
                ],
            },
        }
    )

    wrapper.create_session()

    reported = _reported_session_config(vc)
    assert [m["id"] for m in reported["available_modes"]] == ["agent", "plan"]
    assert [m["label"] for m in reported["available_modes"]] == ["Agent", "Plan"]
    assert reported["current_mode"] == "agent"
    assert [m["id"] for m in reported["available_models"]] == ["m1", "m2"]
    assert reported["current_model"] == "m1"


def test_create_session_reports_models_from_config_option() -> None:
    """When the agent uses a model config option (category=model) instead of a
    dedicated models block (cursor/copilot), models are still reported."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.acp.send_request.return_value = _response(
        result={
            "sessionId": _SESSION_ID,
            "configOptions": [
                {
                    "id": "model",
                    "category": "model",
                    "currentValue": "auto",
                    "options": [
                        {"value": "auto", "name": "Auto"},
                        {"value": "sonnet", "name": "Sonnet"},
                    ],
                }
            ],
        }
    )

    wrapper.create_session()

    reported = _reported_session_config(vc)
    assert [m["id"] for m in reported["available_models"]] == ["auto", "sonnet"]


def test_create_session_authenticates_on_auth_required() -> None:
    """An auth-required (-32000) session/new must trigger the authenticate
    flow with an advertised method id, then retry session/new."""
    wrapper = _build_wrapper()
    wrapper.auth_methods = [{"id": "device-login", "name": "Device login"}]

    calls: list[str] = []

    def _send(method: str, params: Dict[str, Any], **kwargs: Any) -> MagicMock:
        calls.append(method)
        if method == "session/new" and calls.count("session/new") == 1:
            return _response(
                error={"code": -32000, "message": "Authentication required"}
            )
        if method == "authenticate":
            assert params == {"methodId": "device-login"}
            return _response(result={})
        return _response(result={"sessionId": _SESSION_ID})

    wrapper.acp.send_request.side_effect = _send

    wrapper.create_session()

    assert calls == ["session/new", "authenticate", "session/new"]
    assert wrapper.session_id == _SESSION_ID


def test_create_session_applies_requested_initial_mode() -> None:
    """A spawn-time permission_mode different from the agent default must be
    applied via session/set_mode."""
    wrapper = _build_wrapper(config=_TestConfig(permission_mode="plan"))

    def _send(method: str, params: Dict[str, Any], **kwargs: Any) -> MagicMock:
        if method == "session/new":
            return _response(
                result={
                    "sessionId": _SESSION_ID,
                    "modes": {
                        "currentModeId": "agent",
                        "availableModes": [{"id": "agent"}, {"id": "plan"}],
                    },
                }
            )
        return _response(result={})

    wrapper.acp.send_request.side_effect = _send

    wrapper.create_session()

    set_mode_calls = [
        c
        for c in wrapper.acp.send_request.call_args_list
        if c.args[0] == "session/set_mode"
    ]
    assert len(set_mode_calls) == 1
    assert set_mode_calls[0].args[1] == {"sessionId": _SESSION_ID, "modeId": "plan"}
    assert wrapper.current_mode_id == "plan"


def test_create_session_skips_unsupported_initial_mode() -> None:
    """An unknown requested mode must not fail session creation."""
    wrapper = _build_wrapper(config=_TestConfig(permission_mode="yolo"))
    wrapper.acp.send_request.return_value = _response(
        result={
            "sessionId": _SESSION_ID,
            "modes": {"currentModeId": "agent", "availableModes": [{"id": "agent"}]},
        }
    )

    wrapper.create_session()

    methods = [c.args[0] for c in wrapper.acp.send_request.call_args_list]
    assert "session/set_mode" not in methods
    assert wrapper.session_id == _SESSION_ID


# ---------------------------------------------------------------------------
# prompt turn: stopReason → status flow
# ---------------------------------------------------------------------------


def _run_prompt(wrapper: ACPWrapperBase, stop_reason: str) -> None:
    wrapper.session_id = _SESSION_ID
    wrapper.acp.send_request.return_value = _response(
        result={"stopReason": stop_reason}
    )
    wrapper._run_prompt_request("do something")


def test_stop_reason_refusal_is_surfaced_to_user() -> None:
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)

    _run_prompt(wrapper, "refusal")

    assert any("declined" in text for text in _feedback_texts(vc))


def test_stop_reason_end_turn_sets_awaiting_input_without_noise() -> None:
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)

    _run_prompt(wrapper, "end_turn")

    vc.update_agent_instance_status.assert_called_with(_INSTANCE_ID, "AWAITING_INPUT")
    assert not any("declined" in text for text in _feedback_texts(vc))


def test_stop_reason_max_tokens_is_surfaced_to_user() -> None:
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)

    _run_prompt(wrapper, "max_tokens")

    assert any("token limit" in text for text in _feedback_texts(vc))


# ---------------------------------------------------------------------------
# queued-message coalescing — a burst the user sent while the agent was busy
# runs as ONE turn, not one turn per message.
# ---------------------------------------------------------------------------


def test_coalesce_prompt_parts_joins_text_and_concats_attachments() -> None:
    """Non-empty texts join on a blank line; attachments concatenate in order;
    empty-text parts contribute only their attachments."""
    from vicoa.attachments import AttachmentRef

    a1 = AttachmentRef(id="att-1", mime_type="image/png", filename="a.png")
    a2 = AttachmentRef(id="att-2", mime_type="image/png", filename="b.png")

    text, attachments = ACPWrapperBase._coalesce_prompt_parts(
        [("first", (a1,)), ("", (a2,)), ("third", ())]
    )

    assert text == "first\n\nthird"
    assert attachments == (a1, a2)


def test_drain_coalesces_burst_into_one_prompt() -> None:
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.session_id = _SESSION_ID
    wrapper.send_prompt = MagicMock()  # type: ignore[method-assign]
    wrapper.message_queue = [
        ("one", (), "m1"),
        ("two", (), "m2"),
        ("three", (), "m3"),
    ]

    wrapper._drain_and_dispatch_queue()

    wrapper.send_prompt.assert_called_once_with("one\n\ntwo\n\nthree", ())
    assert wrapper.message_queue == []
    # Every message's queued badge is cleared, not just the first.
    consumed = [c.args[0] for c in vc.mark_message_consumed.call_args_list]
    assert consumed == ["m1", "m2", "m3"]
    vc.update_agent_instance_status.assert_called_with(_INSTANCE_ID, "ACTIVE")


def test_drain_holds_messages_while_a_prompt_is_in_flight() -> None:
    """While a turn is running, messages stay in the queue (flagged "queued")
    instead of dripping to the agent one per tick — so the turn-end drain runs
    the whole burst as a single follow-up turn."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.session_id = _SESSION_ID
    wrapper.send_prompt = MagicMock()  # type: ignore[method-assign]
    wrapper._prompt_in_flight = True
    wrapper.message_queue = [("one", (), "m1"), ("two", (), "m2")]

    wrapper._drain_and_dispatch_queue()

    wrapper.send_prompt.assert_not_called()
    # Nothing consumed or dispatched yet — the messages are still queued.
    assert wrapper.message_queue == [("one", (), "m1"), ("two", (), "m2")]
    vc.mark_message_consumed.assert_not_called()

    # When the turn ends, the next tick drains the whole burst at once.
    wrapper._prompt_in_flight = False
    wrapper._drain_and_dispatch_queue()
    wrapper.send_prompt.assert_called_once_with("one\n\ntwo", ())
    assert wrapper.message_queue == []


def test_drain_single_message_is_unchanged() -> None:
    wrapper = _build_wrapper()
    wrapper.session_id = _SESSION_ID
    wrapper.send_prompt = MagicMock()  # type: ignore[method-assign]
    wrapper.message_queue = [("hello", (), "m1")]

    wrapper._drain_and_dispatch_queue()

    wrapper.send_prompt.assert_called_once_with("hello", ())


def test_drain_empty_queue_is_a_noop() -> None:
    wrapper = _build_wrapper()
    wrapper.send_prompt = MagicMock()  # type: ignore[method-assign]

    wrapper._drain_and_dispatch_queue()

    wrapper.send_prompt.assert_not_called()


def test_drain_handles_control_command_without_prompting_it() -> None:
    """A control command mixed into the burst is handled inline and left out
    of the coalesced prompt text; the surrounding messages still run as one
    turn, and every message is marked consumed."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.session_id = _SESSION_ID
    wrapper.send_prompt = MagicMock()  # type: ignore[method-assign]
    wrapper._handle_control_command = MagicMock(  # type: ignore[method-assign]
        side_effect=lambda text: text == "CTRL"
    )
    wrapper.message_queue = [
        ("before", (), "m1"),
        ("CTRL", (), "m2"),
        ("after", (), "m3"),
    ]

    wrapper._drain_and_dispatch_queue()

    wrapper.send_prompt.assert_called_once_with("before\n\nafter", ())
    consumed = [c.args[0] for c in vc.mark_message_consumed.call_args_list]
    assert consumed == ["m1", "m2", "m3"]


def test_drain_only_control_commands_does_not_prompt() -> None:
    wrapper = _build_wrapper()
    wrapper.session_id = _SESSION_ID
    wrapper.send_prompt = MagicMock()  # type: ignore[method-assign]
    wrapper._handle_control_command = MagicMock(  # type: ignore[method-assign]
        return_value=True
    )
    wrapper.message_queue = [("CTRL", (), "m1")]

    wrapper._drain_and_dispatch_queue()

    wrapper.send_prompt.assert_not_called()


def test_drain_drops_a_cancelled_message_and_keeps_the_rest() -> None:
    """A message the user cancelled while the prior turn ran (its id landed in
    ``_cancelled_message_ids`` via a message-update) is dropped at drain time:
    left out of the coalesced prompt and NOT marked consumed (it's cancelled,
    not consumed), while its siblings still run as one turn."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.session_id = _SESSION_ID
    wrapper.send_prompt = MagicMock()  # type: ignore[method-assign]
    wrapper._cancelled_message_ids = {"m2"}
    wrapper.message_queue = [
        ("keep-one", (), "m1"),
        ("cancelled", (), "m2"),
        ("keep-two", (), "m3"),
    ]

    wrapper._drain_and_dispatch_queue()

    wrapper.send_prompt.assert_called_once_with("keep-one\n\nkeep-two", ())
    consumed = [c.args[0] for c in vc.mark_message_consumed.call_args_list]
    assert consumed == ["m1", "m3"]
    # The id is consumed from the set so it can't suppress a future reuse.
    assert wrapper._cancelled_message_ids == set()


def test_drain_all_cancelled_does_not_prompt() -> None:
    """When every queued message was cancelled, the turn is skipped entirely —
    no empty prompt reaches the agent."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.session_id = _SESSION_ID
    wrapper.send_prompt = MagicMock()  # type: ignore[method-assign]
    wrapper._cancelled_message_ids = {"m1", "m2"}
    wrapper.message_queue = [("gone-one", (), "m1"), ("gone-two", (), "m2")]

    wrapper._drain_and_dispatch_queue()

    wrapper.send_prompt.assert_not_called()
    vc.mark_message_consumed.assert_not_called()
    assert wrapper.message_queue == []


def test_queued_prompts_coalesced_into_next_turn(monkeypatch) -> None:
    """Prompts that piled up in ``_queued_prompts`` during a turn are merged
    into a single follow-up turn when the current prompt finishes."""
    import integrations.headless.acp_base as acp_base

    captured: dict[str, Any] = {}

    class _CapturingThread:
        def __init__(self, target=None, args=(), daemon=None) -> None:
            captured["args"] = args

        def start(self) -> None:  # never actually recurse
            pass

    monkeypatch.setattr(acp_base.threading, "Thread", _CapturingThread)

    wrapper = _build_wrapper()
    wrapper.session_id = _SESSION_ID
    wrapper.acp.send_request.return_value = _response(result={"stopReason": "end_turn"})
    wrapper._prompt_in_flight = True
    wrapper._queued_prompts = [("a", ()), ("b", ())]

    wrapper._run_prompt_request("current turn")

    assert captured["args"] == ("a\n\nb", ())
    assert wrapper._queued_prompts == []
    assert wrapper._prompt_in_flight is True  # re-armed for the coalesced turn


# ---------------------------------------------------------------------------
# empty / swallowed-failure turns
# ---------------------------------------------------------------------------


def test_empty_turn_is_surfaced_when_agent_produces_no_output() -> None:
    """A ``session/prompt`` that succeeds but streams nothing (no text, no
    tools, no error) — the shape a swallowed provider failure takes over ACP,
    e.g. Kimi's unsupported-thinking 400 — must be reported, not swallowed."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.session_id = _SESSION_ID
    wrapper.acp.send_request.return_value = _response(result={"stopReason": "end_turn"})

    wrapper._run_prompt_request("hi")

    texts = _feedback_texts(vc)
    assert any("without producing any output" in t for t in texts), texts
    assert any("stop reason: end_turn" in t for t in texts), texts


def test_empty_turn_notice_includes_agent_stderr() -> None:
    """Whatever the agent printed to stderr during the turn is attached to the
    empty-turn notice, so failure modes that DO report a cause surface it."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.session_id = _SESSION_ID
    wrapper._turn_stderr.append("400 thinking.keep is not supported by model x")
    wrapper.acp.send_request.return_value = _response(result={"stopReason": "end_turn"})

    wrapper._run_prompt_request("hi")

    texts = _feedback_texts(vc)
    assert any("thinking.keep is not supported" in t for t in texts), texts


def test_turn_with_output_is_not_flagged_empty() -> None:
    """A turn that streamed real assistant text must not trigger the notice."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.session_id = _SESSION_ID
    # An agent_message_chunk before the prompt result marks real activity.
    wrapper._handle_session_update(
        {
            "sessionId": _SESSION_ID,
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "hello"},
            },
        }
    )
    wrapper.acp.send_request.return_value = _response(result={"stopReason": "end_turn"})

    wrapper._run_prompt_request("hi")

    texts = _feedback_texts(vc)
    assert not any("without producing any output" in t for t in texts), texts


def test_cancelled_empty_turn_stays_silent() -> None:
    """A user-interrupted turn legitimately produces no output — the cancel
    path already narrates it, so the empty-turn notice must not also fire."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.session_id = _SESSION_ID
    wrapper._prompt_cancel_event.set()
    wrapper.acp.send_request.return_value = _response(result={"stopReason": "end_turn"})

    wrapper._run_prompt_request("hi")

    texts = _feedback_texts(vc)
    assert not any("without producing any output" in t for t in texts), texts


# ---------------------------------------------------------------------------
# startup failure surfacing (agent never came up — e.g. not logged in)
# ---------------------------------------------------------------------------


def test_startup_failure_message_flags_auth_and_names_agent() -> None:
    """An ACP -32000 (auth required) startup crash must produce a sign-in
    message, not a raw error — that's the not-logged-in case the UI otherwise
    shows only as "not accepting input"."""
    wrapper = _build_wrapper()
    msg = wrapper._startup_failure_message(
        ACPError("ACP Error -32000: Authentication required")
    )
    assert "testagent" in msg
    assert "sign" in msg.lower()
    # The daemon-spawn-env case is a Vicoa bug the user can't self-fix, so the
    # copy must invite a report.
    assert "hi@vicoa.ai" in msg


def test_startup_failure_message_falls_back_to_raw_error() -> None:
    """A non-auth spawn failure still surfaces the underlying error and a way
    to report it."""
    wrapper = _build_wrapper()
    msg = wrapper._startup_failure_message(RuntimeError("binary not found"))
    assert "binary not found" in msg
    assert "hi@vicoa.ai" in msg


def test_report_startup_failure_posts_to_session() -> None:
    """The reason is posted to the session so it lands in the transcript."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper._report_startup_failure(
        ACPError("ACP Error -32000: Authentication required")
    )
    texts = _feedback_texts(vc)
    assert any("couldn't start" in t for t in texts), texts


def test_run_reports_startup_failure_when_setup_crashes() -> None:
    """A crash during _setup (startup not complete) routes through the
    startup-failure reporter before cleanup writes the FAILED status."""
    wrapper = _build_wrapper()
    wrapper._startup_complete = False
    wrapper._install_signal_handlers = lambda: None  # type: ignore[method-assign]

    def _setup() -> None:
        raise ACPError("ACP Error -32000: Authentication required")

    reported: dict[str, Any] = {}

    def _report(error: Exception) -> None:
        reported["error"] = error

    cleanup: dict[str, Any] = {}

    def _cleanup(final_status=None) -> None:
        cleanup["status"] = final_status

    wrapper._setup = _setup  # type: ignore[method-assign]
    wrapper._report_startup_failure = _report  # type: ignore[method-assign]
    wrapper._cleanup = _cleanup  # type: ignore[method-assign]

    rc = wrapper.run()

    assert rc == 1
    assert isinstance(reported.get("error"), ACPError)
    assert cleanup["status"] == "FAILED"


def test_run_skips_startup_reporter_after_startup_completes() -> None:
    """A mid-session crash (startup already complete) must NOT be reported as a
    startup failure — it isn't one."""
    wrapper = _build_wrapper()
    wrapper._startup_complete = True
    wrapper._install_signal_handlers = lambda: None  # type: ignore[method-assign]
    wrapper._setup = lambda: None  # type: ignore[method-assign]

    def _loop() -> None:
        raise RuntimeError("crash after startup")

    called = {"reported": False}

    def _report(error: Exception) -> None:
        called["reported"] = True

    wrapper._run_event_loop = _loop  # type: ignore[method-assign]
    wrapper._report_startup_failure = _report  # type: ignore[method-assign]
    wrapper._cleanup = lambda final_status=None: None  # type: ignore[method-assign]

    rc = wrapper.run()

    assert rc == 1
    assert called["reported"] is False


# ---------------------------------------------------------------------------
# mode switching (session/set_mode + current_mode_update)
# ---------------------------------------------------------------------------


def _wrapper_with_modes(vc: Optional[MagicMock] = None) -> ACPWrapperBase:
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.session_id = _SESSION_ID
    wrapper.available_modes = [
        {"id": "agent", "name": "Agent"},
        {"id": "plan", "name": "Plan"},
    ]
    wrapper.current_mode_id = "agent"
    return wrapper


def test_permission_mode_control_switches_mode_and_patches_config() -> None:
    vc = MagicMock()
    wrapper = _wrapper_with_modes(vc)
    wrapper.acp.send_request.return_value = _response(result={})

    wrapper._apply_control_command({"setting": "permission_mode", "value": "plan"})

    call = wrapper.acp.send_request.call_args
    assert call.args[0] == "session/set_mode"
    assert call.args[1] == {"sessionId": _SESSION_ID, "modeId": "plan"}
    assert wrapper.current_mode_id == "plan"
    vc.patch_agent_instance.assert_called_once_with(
        _INSTANCE_ID,
        session_config={
            "agent": "testagent",
            "permission_mode": "plan",
            "current_mode": "plan",
        },
    )


def test_invalid_mode_feedback_lists_agent_advertised_modes() -> None:
    """Catalog hints can drift — the error must teach the real mode ids."""
    vc = MagicMock()
    wrapper = _wrapper_with_modes(vc)

    wrapper._apply_control_command({"setting": "permission_mode", "value": "yolo"})

    wrapper.acp.send_request.assert_not_called()
    feedback = "\n".join(_feedback_texts(vc))
    assert "agent, plan" in feedback
    vc.patch_agent_instance.assert_not_called()


def test_mode_control_without_modes_reports_unsupported() -> None:
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.session_id = _SESSION_ID

    wrapper._apply_control_command({"setting": "permission_mode", "value": "plan"})

    assert any("not supported" in text for text in _feedback_texts(vc))


def test_current_mode_update_patches_session_config() -> None:
    """Agent-initiated mode changes (plan-exit tools) must reach the UI."""
    vc = MagicMock()
    wrapper = _wrapper_with_modes(vc)

    wrapper._handle_session_update(
        {
            "sessionId": _SESSION_ID,
            "update": {"sessionUpdate": "current_mode_update", "currentModeId": "plan"},
        }
    )

    assert wrapper.current_mode_id == "plan"
    vc.patch_agent_instance.assert_called_once_with(
        _INSTANCE_ID,
        session_config={
            "agent": "testagent",
            "permission_mode": "plan",
            "current_mode": "plan",
        },
    )


def test_unknown_session_updates_are_ignored_gracefully() -> None:
    wrapper = _build_wrapper()

    for update in (
        {"sessionUpdate": "plan", "entries": []},
        {"sessionUpdate": "usage_update", "used": 10, "size": 100},
        {"sessionUpdate": "session_info_update", "title": "T"},
        {"sessionUpdate": "some_future_variant", "x": 1},
    ):
        wrapper._handle_session_update({"sessionId": _SESSION_ID, "update": update})

    assert wrapper._assistant_chunk_buffer == ""


def test_available_commands_update_is_retained() -> None:
    wrapper = _build_wrapper()

    wrapper._handle_session_update(
        {
            "sessionId": _SESSION_ID,
            "update": {
                "sessionUpdate": "available_commands_update",
                "availableCommands": [{"name": "plan", "description": "Plan"}],
            },
        }
    )

    assert wrapper.available_commands == [{"name": "plan", "description": "Plan"}]


def test_tool_call_update_renders_as_collapsed_tool_card() -> None:
    """A completed tool_call_update surfaces as its own "Using tool:" card
    message (which web/mobile collapse), not glued inline into the narration
    buffer — so raw tool output stops flooding the transcript as flat text."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.session_id = _SESSION_ID
    wrapper._show_tool_updates = False

    wrapper._handle_session_update(
        {
            "sessionId": _SESSION_ID,
            "update": {
                "sessionUpdate": "tool_call_update",
                "status": "completed",
                "kind": "read",
                "title": "Read",
                "content": [{"type": "text", "text": "Found 3 matches"}],
            },
        }
    )

    contents = [c for c in _feedback_texts(vc) if c]
    cards = [c for c in contents if c.startswith("🔧 Using tool:")]
    assert len(cards) == 1
    assert "Read" in cards[0].splitlines()[0]
    assert "Found 3 matches" in cards[0]
    # Nothing was left glued into the narration buffer.
    assert wrapper._assistant_chunk_buffer == ""


def test_tool_card_flushes_pending_narration_first() -> None:
    """Narration buffered before a tool result flushes as its own message so
    the tool card leads with the "Using tool:" prefix the clients detect."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.session_id = _SESSION_ID
    wrapper._show_tool_updates = False

    wrapper._handle_session_update(
        {
            "sessionId": _SESSION_ID,
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "Let me read the file."},
            },
        }
    )
    wrapper._handle_session_update(
        {
            "sessionId": _SESSION_ID,
            "update": {
                "sessionUpdate": "tool_call_update",
                "status": "completed",
                "kind": "read",
                "title": "Read",
                "content": [{"type": "text", "text": "line 1"}],
            },
        }
    )

    contents = [c for c in _feedback_texts(vc) if c]
    # Narration first (plain), then the tool card — two separate messages.
    assert contents[0] == "Let me read the file."
    assert contents[1].startswith("🔧 Using tool:")
    assert "line 1" in contents[1]


def test_tool_card_name_is_hyphen_safe_for_paths() -> None:
    """ACP agents put the file path in ``title``; the card NAME must come from
    the clean ``kind`` enum so a hyphenated filename (``pricing-cards.tsx``)
    isn't severed by the clients' "<name> - <arg>" split."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.session_id = _SESSION_ID
    wrapper._show_tool_updates = False

    wrapper._handle_session_update(
        {
            "sessionId": _SESSION_ID,
            "update": {
                "sessionUpdate": "tool_call_update",
                "status": "completed",
                "kind": "read",
                "title": "apps/web/components/billing/pricing-cards.tsx",
                "content": [{"type": "text", "text": "file body"}],
            },
        }
    )

    card = next(c for c in _feedback_texts(vc) if c.startswith("🔧 Using tool:"))
    first_line = card.splitlines()[0]
    # The name segment (before the first " - ") is the clean kind — no hyphen,
    # so the client can't sever the filename.
    name_seg = first_line.split(" - ", 1)[0]
    assert name_seg == "🔧 Using tool: Read"
    # The full hyphenated path survives intact in the arg slot.
    assert "pricing-cards.tsx" in first_line


def _sent_calls(vc: MagicMock) -> list[tuple[str, object]]:
    return [
        (call.kwargs.get("content", ""), call.kwargs.get("message_metadata"))
        for call in vc.send_message.call_args_list
    ]


def test_agent_thought_chunk_becomes_thinking_card() -> None:
    """Model reasoning on the thought channel is surfaced as a metadata-tagged
    thinking card, emitted BEFORE the answer it reasoned toward."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.session_id = _SESSION_ID

    wrapper._handle_session_update(
        {
            "sessionId": _SESSION_ID,
            "update": {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": "text", "text": "weighing the options"},
            },
        }
    )
    wrapper._handle_session_update(
        {
            "sessionId": _SESSION_ID,
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "Here is the answer."},
            },
        }
    )
    wrapper._flush_assistant_chunk_buffer()

    calls = _sent_calls(vc)
    tagged = [
        content for content, md in calls if isinstance(md, dict) and "thinking" in md
    ]
    assert tagged == ["weighing the options"]
    # The thinking card precedes the plain answer.
    contents = [content for content, _ in calls]
    assert contents.index("weighing the options") < contents.index(
        "Here is the answer."
    )


# ---------------------------------------------------------------------------
# permission flow → status transitions
# ---------------------------------------------------------------------------


def test_permission_grant_returns_status_to_active() -> None:
    """After the user answers a permission prompt the agent resumes working,
    so the instance status must flip AWAITING_INPUT → ACTIVE."""
    vc = MagicMock()
    reply = MagicMock()
    reply.message_id = "msg-1"
    reply.queued_user_messages = ["Allow"]
    vc.send_message.return_value = reply

    wrapper = _build_wrapper(vicoa_client=vc)
    wrapper.session_id = _SESSION_ID

    option_id = wrapper._handle_permission_request(
        {
            "sessionId": _SESSION_ID,
            "toolCall": {"toolCallId": "tc-1", "title": "Edit file", "kind": "edit"},
            "options": [
                {"optionId": "allow", "name": "Allow", "kind": "allow_once"},
                {"optionId": "reject", "name": "Reject", "kind": "reject_once"},
            ],
        }
    )

    assert option_id == "allow"
    statuses = [c.args[1] for c in vc.update_agent_instance_status.call_args_list]
    assert statuses == ["AWAITING_INPUT", "ACTIVE"]


def test_permission_request_with_object_locations_does_not_crash() -> None:
    """ACP toolCall.locations are {path, line} objects, not strings. The
    handler must not crash joining them (the bug that made Gemini render
    '[object Object]'); the prompt should list the paths."""
    wrapper = _build_wrapper()

    captured: Dict[str, Any] = {}

    def _fake_wait(message: str, options: list) -> str:
        captured["message"] = message
        return options[0]["option_id"] if options else "proceed"

    wrapper._wait_for_permission_decision = _fake_wait  # type: ignore[method-assign]

    selected = wrapper._handle_permission_request(
        {
            "sessionId": _SESSION_ID,
            "toolCall": {
                "toolCallId": "t1",
                "title": "Edit",
                "kind": "edit",
                "locations": [
                    {"path": "/repo/foo.py", "line": 3},
                    {"path": "/repo/bar.py"},
                ],
            },
            "options": [
                {"optionId": "proceed_once", "name": "Proceed", "kind": "allow_once"},
            ],
        }
    )

    assert selected == "proceed_once"
    assert "/repo/foo.py" in captured["message"]
    assert "/repo/bar.py" in captured["message"]


def test_permission_request_while_interrupted_is_cancelled() -> None:
    """Spec: pending permission requests must resolve with the cancelled
    outcome when the turn is being cancelled."""
    wrapper = _build_wrapper()
    wrapper.session_id = _SESSION_ID
    wrapper._interrupt_active = True

    result = wrapper.handle_request(
        "session/request_permission",
        {"sessionId": _SESSION_ID, "toolCall": {}, "options": []},
    )

    assert result == {"outcome": {"outcome": "cancelled"}}


# ---------------------------------------------------------------------------
# unknown agent→client requests
# ---------------------------------------------------------------------------


def test_unknown_agent_request_raises_method_not_found() -> None:
    wrapper = _build_wrapper()

    with pytest.raises(ACPMethodNotFound):
        wrapper.handle_request("fs/read_text_file", {"path": "/etc/passwd"})


def test_extension_request_hook_can_answer() -> None:
    wrapper = _build_wrapper()
    wrapper.handle_extension_request = lambda method, params: (
        {"answer": "42"} if method == "vendor/ask" else None
    )

    assert wrapper.handle_request("vendor/ask", {}) == {"answer": "42"}


def test_acp_client_replies_method_not_found_for_rejected_requests() -> None:
    """The wire-level contract: ACPMethodNotFound from the request handler
    becomes a JSON-RPC -32601 error response."""
    from integrations.headless.acp_client import ACPClient

    def _reject(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        raise ACPMethodNotFound(method)

    client = ACPClient(command=["x"], cwd="/tmp", on_request=_reject)
    written: list[Dict[str, Any]] = []
    client._write_message = written.append  # type: ignore[method-assign]

    client._handle_message(
        {"jsonrpc": "2.0", "id": 7, "method": "terminal/create", "params": {}}
    )

    assert written == [
        {
            "jsonrpc": "2.0",
            "id": 7,
            "error": {"code": -32601, "message": "Method not found"},
        }
    ]
