"""Tests for mid-session control commands in OpenCodeACPWrapper.

Covers session_config PATCH after agent_type and model changes.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from integrations.headless.opencode_acp import OpenCodeACPConfig, OpenCodeACPWrapper


_INSTANCE_ID = "oc-inst-001"
_SESSION_ID = "oc-sess-abc"


def _build_wrapper(
    *,
    vicoa_client: MagicMock | None = None,
    agent_mode: str = "build",
    model: str | None = None,
) -> OpenCodeACPWrapper:
    """Construct an OpenCodeACPWrapper for unit tests without running __init__."""
    wrapper: OpenCodeACPWrapper = OpenCodeACPWrapper.__new__(OpenCodeACPWrapper)

    wrapper.config = OpenCodeACPConfig(
        api_key="test-key",
        base_url="http://localhost:8080",
        agent_instance_id=_INSTANCE_ID,
        project_path="/tmp/test",
        agent_mode=agent_mode,
        model=model,
    )

    wrapper.vicoa_client = vicoa_client or MagicMock()
    wrapper.session_id = _SESSION_ID
    wrapper.last_message_id = None
    wrapper.running = True
    wrapper.debug_log_file = None

    # ACP client — mock by default so tests can configure it per-scenario
    wrapper.acp = MagicMock()

    # State used by _send_feedback_message / interrupt handling
    wrapper._awaiting_input_requested_for_message_id = None
    wrapper._awaiting_after_next_agent_output = False
    wrapper._assistant_chunk_buffer = ""
    wrapper._drop_stream_output_until_next_prompt = False

    # Live ACP session state (populated by _apply_session_state in real runs).
    wrapper.session_config_options = []
    wrapper.available_modes = []
    wrapper.current_mode_id = None
    wrapper.available_models = []
    wrapper.current_model_id = None

    return wrapper


def _model_option(current: str = "opencode/big-pickle") -> dict:
    """A standard ACP model config option as OpenCode advertises it."""
    return {
        "id": "model",
        "category": "model",
        "currentValue": current,
        "options": [
            {"value": "opencode/big-pickle", "name": "Big Pickle"},
            {"value": "opencode/deepseek-v4-flash-free", "name": "DeepSeek"},
        ],
    }


def _patched_session_configs(vc: MagicMock) -> list[dict]:
    return [
        c.kwargs["session_config"]
        for c in vc.patch_agent_instance.call_args_list
        if "session_config" in c.kwargs
    ]


def _set_option_calls(wrapper: OpenCodeACPWrapper) -> list:
    return [
        c
        for c in wrapper.acp.send_request.call_args_list
        if c.args and c.args[0] == "session/set_config_option"
    ]


def _acp_ok() -> MagicMock:
    """Return an ACP client whose send_request always succeeds."""
    acp = MagicMock()
    resp = MagicMock()
    resp.raise_for_error = MagicMock()
    acp.send_request.return_value = resp
    return acp


def _acp_fail() -> MagicMock:
    """Return an ACP client whose send_request always raises."""
    acp = MagicMock()
    acp.send_request.side_effect = Exception("method not found")
    return acp


# ---------------------------------------------------------------------------
# agent_type (build / plan) — tracer bullet
# ---------------------------------------------------------------------------


def test_agent_type_change_patches_session_config() -> None:
    """Mode change should persist opencode_mode to Vicoa via session_config PATCH."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc, agent_mode="build")
    wrapper.acp = _acp_ok()

    wrapper._apply_control_command({"setting": "agent_type", "value": "plan"})

    vc.patch_agent_instance.assert_called_once_with(
        _INSTANCE_ID,
        session_config={"agent": "opencode", "opencode_mode": "plan"},
    )


def test_agent_type_same_mode_no_patch() -> None:
    """If the requested mode matches current, no PATCH is sent."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc, agent_mode="plan")
    wrapper.acp = _acp_ok()

    wrapper._apply_control_command({"setting": "agent_type", "value": "plan"})

    vc.patch_agent_instance.assert_not_called()


def test_agent_type_acp_failure_no_patch() -> None:
    """If ACP rejects the mode change, no PATCH should be sent."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc, agent_mode="build")
    wrapper.acp = _acp_fail()

    wrapper._apply_control_command({"setting": "agent_type", "value": "plan"})

    vc.patch_agent_instance.assert_not_called()


def test_agent_type_change_updates_config() -> None:
    """Mode change should update self.config.agent_mode."""
    wrapper = _build_wrapper(agent_mode="build")
    wrapper.acp = _acp_ok()

    wrapper._apply_control_command({"setting": "agent_type", "value": "plan"})

    assert wrapper.config.agent_mode == "plan"


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------


def test_model_change_applied_live_via_config_option() -> None:
    """OpenCode advertises a standard ACP model option, so a mid-session model
    change is applied immediately (session/set_config_option) and persisted."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc, model="opencode/big-pickle")
    wrapper.session_config_options = [_model_option()]
    resp = MagicMock()
    resp.raise_for_error = MagicMock()
    resp.result = {}
    wrapper.acp.send_request.return_value = resp

    wrapper._apply_control_command(
        {"setting": "model", "value": "opencode/deepseek-v4-flash-free"}
    )

    calls = _set_option_calls(wrapper)
    assert len(calls) == 1
    assert calls[0].args[1] == {
        "sessionId": _SESSION_ID,
        "configId": "model",
        "value": "opencode/deepseek-v4-flash-free",
    }
    patched = _patched_session_configs(vc)
    assert any(
        p.get("current_model") == "opencode/deepseek-v4-flash-free" for p in patched
    )


def test_model_change_persists_without_live_option() -> None:
    """No advertised model option (e.g. a resume path) → no live set, but the
    choice is still persisted for the next session."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc, model="opencode/big-pickle")
    wrapper.session_config_options = []

    wrapper._apply_control_command(
        {"setting": "model", "value": "opencode/deepseek-v4-flash-free"}
    )

    assert _set_option_calls(wrapper) == []
    patched = _patched_session_configs(vc)
    assert patched and patched[-1].get("model") == "opencode/deepseek-v4-flash-free"


def test_model_empty_value_no_patch() -> None:
    """Empty model value should not PATCH."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc, model="opencode/big-pickle")
    wrapper.session_config_options = [_model_option()]

    wrapper._apply_control_command({"setting": "model", "value": ""})

    vc.patch_agent_instance.assert_not_called()


def test_create_session_applies_spawn_model_via_config_option() -> None:
    """OpenCode's session/new `model` param isn't reliably honored, so the
    spawn-time model is applied via session/set_config_option (the gear's path)
    and reported as the active model."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc, model="opencode/deepseek-v4-flash-free")

    def _send(method: str, params: dict, **kwargs: object) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_error = MagicMock()
        if method == "session/new":
            resp.result = {
                "sessionId": _SESSION_ID,
                "configOptions": [_model_option(current="opencode/big-pickle")],
            }
        else:
            resp.result = {}
        return resp

    wrapper.acp.send_request.side_effect = _send

    wrapper.create_session()

    calls = _set_option_calls(wrapper)
    assert len(calls) == 1
    assert calls[0].args[1] == {
        "sessionId": _SESSION_ID,
        "configId": "model",
        "value": "opencode/deepseek-v4-flash-free",
    }
    patched = _patched_session_configs(vc)
    assert any(
        p.get("current_model") == "opencode/deepseek-v4-flash-free" for p in patched
    )


def test_create_session_no_model_makes_no_set() -> None:
    """The 'default' sentinel is filtered out before spawn (no --model), so
    create_session with no model issues no set_config_option."""
    wrapper = _build_wrapper(model=None)

    def _send(method: str, params: dict, **kwargs: object) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_error = MagicMock()
        resp.result = (
            {"sessionId": _SESSION_ID, "configOptions": [_model_option()]}
            if method == "session/new"
            else {}
        )
        return resp

    wrapper.acp.send_request.side_effect = _send
    wrapper.create_session()
    assert _set_option_calls(wrapper) == []


def test_reports_available_models_for_gear() -> None:
    """After session/new, OpenCode's live provider-aware model list is PATCHed
    onto session_config so the mid-session gear can list + switch models."""
    vc = MagicMock()
    wrapper = _build_wrapper(vicoa_client=vc, model="opencode/big-pickle")
    wrapper.session_config_options = [_model_option(current="opencode/big-pickle")]
    wrapper.current_model_id = "opencode/big-pickle"

    wrapper._report_available_models()

    patched = _patched_session_configs(vc)
    assert patched
    last = patched[-1]
    ids = [m["id"] for m in last["available_models"]]
    assert "opencode/deepseek-v4-flash-free" in ids
    assert last["current_model"] == "opencode/big-pickle"
