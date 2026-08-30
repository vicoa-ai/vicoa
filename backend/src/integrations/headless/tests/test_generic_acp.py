"""Tests for the generic ACP agent module (cursor / gemini / copilot / kimi / hermes).

Each agent is a GenericAgentSpec table row; these tests pin the spawn
command, env, timeout and session_config behavior per agent.
"""

from __future__ import annotations

import os
from collections import deque
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from integrations.headless.generic_acp import (
    GENERIC_ACP_AGENTS,
    GenericACPConfig,
    GenericACPWrapper,
)


_INSTANCE_ID = "gen-inst-001"
_SESSION_ID = "gen-sess-abc"


def _config(agent_id: str, **overrides: Any) -> GenericACPConfig:
    return GenericACPConfig(
        GENERIC_ACP_AGENTS[agent_id],
        api_key="test-key",
        base_url="http://localhost:8080",
        agent_instance_id=_INSTANCE_ID,
        project_path="/tmp/test-project",
        **overrides,
    )


def _which_first_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "integrations.headless.generic_acp.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )


# ---------------------------------------------------------------------------
# spawn commands per agent — tracer bullet
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "agent_id,expected_command",
    [
        ("cursor", ["cursor-agent", "acp"]),
        ("gemini", ["gemini", "--experimental-acp"]),
        ("copilot", ["copilot", "--acp", "--stdio"]),
        ("kimi", ["kimi", "acp"]),
        ("hermes", ["hermes", "acp"]),
    ],
)
def test_agent_spec_builds_acp_command(
    monkeypatch: pytest.MonkeyPatch, agent_id: str, expected_command: list[str]
) -> None:
    _which_first_candidate(monkeypatch)
    assert _config(agent_id).get_acp_command() == expected_command


def test_cursor_falls_back_to_renamed_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cursor shipped as `cursor-agent` and renamed to `agent` — accept both."""
    monkeypatch.setattr(
        "integrations.headless.generic_acp.shutil.which",
        lambda name: "/usr/local/bin/agent" if name == "agent" else None,
    )
    assert _config("cursor").get_acp_command() == ["agent", "acp"]


def test_missing_binary_raises_with_install_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "integrations.headless.generic_acp.shutil.which", lambda name: None
    )
    with pytest.raises(FileNotFoundError) as exc:
        _config("gemini").get_acp_command()
    assert "gemini" in str(exc.value).lower()
    assert "install" in str(exc.value).lower()


def test_kimi_resolves_binary_from_extra_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """kimi-code installs to ~/.kimi-code/bin (not on PATH) — it must still
    resolve via the spec's extra_dirs, returning the full path."""
    monkeypatch.setattr(
        "integrations.headless.generic_acp.shutil.which", lambda name: None
    )
    expected = os.path.join(os.path.expanduser("~/.kimi-code/bin"), "kimi")
    monkeypatch.setattr(
        "integrations.headless.generic_acp.os.path.isfile", lambda p: p == expected
    )
    monkeypatch.setattr(
        "integrations.headless.generic_acp.os.access", lambda p, mode: p == expected
    )
    cmd = _config("kimi").get_acp_command()
    assert cmd[0] == expected
    assert cmd[-1] == "acp"


def test_agent_command_override_skips_path_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "integrations.headless.generic_acp.shutil.which", lambda name: None
    )
    config = _config("kimi", agent_command="/opt/kimi/bin/kimi")
    assert config.get_acp_command() == ["/opt/kimi/bin/kimi", "acp"]


# ---------------------------------------------------------------------------
# per-agent quirks
# ---------------------------------------------------------------------------


def test_gemini_env_suppresses_browser_login() -> None:
    assert _config("gemini").get_acp_env()["NO_BROWSER"] == "true"


def test_gemini_gets_long_initialize_timeout() -> None:
    """Gemini's first ACP start is slow (happy uses 120s; we allow more)."""
    assert _config("gemini").initialize_timeout_seconds >= 120.0


def test_specs_cover_expected_agents() -> None:
    assert set(GENERIC_ACP_AGENTS) == {"cursor", "gemini", "copilot", "kimi", "hermes"}


# ---------------------------------------------------------------------------
# spawn-time model via the agent's own launch flag (reliable; sidesteps the
# unstable ACP set-model for dedicated-models-block agents like Gemini)
# ---------------------------------------------------------------------------


def test_gemini_passes_selected_model_as_launch_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _which_first_candidate(monkeypatch)
    cmd = _config("gemini", model="gemini-2.5-flash").get_acp_command()
    assert cmd == ["gemini", "--experimental-acp", "--model", "gemini-2.5-flash"]


def test_kimi_passes_model_flag_before_acp_subcommand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Kimi's `--model` is a global flag that must precede the `acp` subcommand.
    _which_first_candidate(monkeypatch)
    cmd = _config("kimi", model="moonshot-ai/kimi-k2.5").get_acp_command()
    assert cmd == ["kimi", "--model", "moonshot-ai/kimi-k2.5", "acp"]


def test_auto_model_does_not_add_launch_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    _which_first_candidate(monkeypatch)
    assert "--model" not in _config("gemini", model="auto").get_acp_command()


def test_no_model_no_launch_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    _which_first_candidate(monkeypatch)
    assert "--model" not in _config("gemini").get_acp_command()


def test_config_option_agent_has_no_launch_model_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Cursor uses the model config-option path, not a launch flag.
    _which_first_candidate(monkeypatch)
    assert "--model" not in _config("cursor", model="composer-2").get_acp_command()


# ---------------------------------------------------------------------------
# session config + initial model
# ---------------------------------------------------------------------------


def _build_wrapper(agent_id: str, **config_overrides: Any) -> GenericACPWrapper:
    wrapper: GenericACPWrapper = GenericACPWrapper.__new__(GenericACPWrapper)
    wrapper.config = _config(agent_id, **config_overrides)
    wrapper.vicoa_client = MagicMock()
    wrapper.acp = MagicMock()
    wrapper.session_id = None
    wrapper.last_message_id = None
    wrapper.running = True
    wrapper.debug_log_file = None
    wrapper.agent_capabilities = {}
    wrapper.auth_methods = []
    wrapper.negotiated_protocol_version = None
    wrapper.available_modes = []
    wrapper.current_mode_id = None
    wrapper.available_models = []
    wrapper.current_model_id = None
    wrapper.session_config_options = []
    wrapper.available_commands = []
    wrapper._awaiting_input_requested_for_message_id = None
    wrapper._awaiting_after_next_agent_output = False
    wrapper._turn_produced_output = False
    wrapper._turn_stderr = deque(maxlen=20)
    wrapper._assistant_chunk_buffer = ""
    return wrapper


def test_build_session_config_carries_agent_model_and_mode() -> None:
    wrapper = _build_wrapper("cursor", model="auto", permission_mode="plan")
    assert wrapper.build_session_config() == {
        "agent": "cursor",
        "model": "auto",
        "permission_mode": "plan",
    }


def test_initial_model_applied_via_session_config_option() -> None:
    """For a config-option agent (no launch flag), the spawn-time model is
    applied with session/set_config_option. (Cursor — Gemini uses --model.)"""
    wrapper = _build_wrapper("cursor", model="composer-2")

    def _send(method: str, params: Dict[str, Any], **kwargs: Any) -> MagicMock:
        resp = MagicMock()
        resp.error = None
        resp.is_error = False
        resp.raise_for_error = MagicMock()
        if method == "session/new":
            resp.result = {
                "sessionId": _SESSION_ID,
                "configOptions": [
                    {
                        "id": "model",
                        "category": "model",
                        "currentValue": "auto",
                    }
                ],
            }
        else:
            resp.result = {}
        return resp

    wrapper.acp.send_request.side_effect = _send

    wrapper.create_session()

    set_option_calls = [
        c
        for c in wrapper.acp.send_request.call_args_list
        if c.args[0] == "session/set_config_option"
    ]
    assert len(set_option_calls) == 1
    assert set_option_calls[0].args[1] == {
        "sessionId": _SESSION_ID,
        "configId": "model",
        "value": "composer-2",
    }


def _cursor_model_option(
    current: str = "gpt-5.4-nano[reasoning=medium]",
) -> Dict[str, Any]:
    """A cursor-shaped model config option whose values carry variant
    suffixes (e.g. ``composer-2.5[fast=true]``)."""
    return {
        "id": "model",
        "category": "model",
        "currentValue": current,
        "options": [
            {"value": "default[]", "name": "Auto"},
            {"value": "composer-2.5[fast=true]", "name": "composer-2.5"},
            {"value": "gpt-5.4-nano[reasoning=medium]", "name": "gpt-5.4-nano"},
        ],
    }


def _create_with_model_option(
    wrapper: GenericACPWrapper, option: Dict[str, Any]
) -> None:
    def _send(method: str, params: Dict[str, Any], **kwargs: Any) -> MagicMock:
        resp = MagicMock()
        resp.error = None
        resp.is_error = False
        resp.raise_for_error = MagicMock()
        if method == "session/new":
            resp.result = {"sessionId": _SESSION_ID, "configOptions": [option]}
        elif method == "session/set_config_option":
            # Cursor echoes back the updated configOptions on a successful set.
            resp.result = {
                "configOptions": [{**option, "currentValue": params["value"]}]
            }
        else:
            resp.result = {}
        return resp

    wrapper.acp.send_request.side_effect = _send
    wrapper.create_session()


def _set_option_calls(wrapper: GenericACPWrapper) -> list[Any]:
    return [
        c
        for c in wrapper.acp.send_request.call_args_list
        if c.args[0] == "session/set_config_option"
    ]


def _reported_current_model(wrapper: GenericACPWrapper) -> Optional[str]:
    patches = [
        c.kwargs["session_config"]
        for c in wrapper.vicoa_client.patch_agent_instance.call_args_list
        if "session_config" in c.kwargs
    ]
    return patches[-1].get("current_model") if patches else None


def test_spawn_model_resolves_variant_suffix() -> None:
    """Catalog 'composer-2.5' resolves to the agent's real suffixed value
    'composer-2.5[fast=true]' and is reported as the active model — so the
    new-session choice and the mid-session gear agree."""
    wrapper = _build_wrapper("cursor", model="composer-2.5")
    _create_with_model_option(wrapper, _cursor_model_option())

    calls = _set_option_calls(wrapper)
    assert len(calls) == 1
    assert calls[0].args[1]["value"] == "composer-2.5[fast=true]"
    assert _reported_current_model(wrapper) == "composer-2.5[fast=true]"


def test_spawn_model_auto_keeps_agent_default() -> None:
    wrapper = _build_wrapper("cursor", model="auto")
    _create_with_model_option(wrapper, _cursor_model_option())
    assert _set_option_calls(wrapper) == []


def test_spawn_model_not_offered_keeps_default() -> None:
    """An unknown model is never forced — the agent keeps its own default."""
    wrapper = _build_wrapper("cursor", model="totally-unknown-model")
    _create_with_model_option(wrapper, _cursor_model_option())
    assert _set_option_calls(wrapper) == []


def test_spawn_model_already_active_is_reported_without_a_set() -> None:
    """When the agent already starts on the requested model, skip the redundant
    set but still report it (the bug: it used to report the persisted model)."""
    wrapper = _build_wrapper("cursor", model="composer-2.5")
    _create_with_model_option(
        wrapper, _cursor_model_option(current="composer-2.5[fast=true]")
    )
    assert _set_option_calls(wrapper) == []
    assert _reported_current_model(wrapper) == "composer-2.5[fast=true]"


def test_initial_model_skipped_without_model_option() -> None:
    """No model config option → session creation succeeds, model is a
    next-session hint only."""
    wrapper = _build_wrapper("hermes", model="default")

    def _send(
        method: str, params: Dict[str, Any], **kwargs: Any
    ) -> Optional[MagicMock]:
        resp = MagicMock()
        resp.error = None
        resp.is_error = False
        resp.raise_for_error = MagicMock()
        resp.result = {"sessionId": _SESSION_ID} if method == "session/new" else {}
        return resp

    wrapper.acp.send_request.side_effect = _send

    wrapper.create_session()

    methods = [c.args[0] for c in wrapper.acp.send_request.call_args_list]
    assert "session/set_config_option" not in methods
    assert wrapper.session_id == _SESSION_ID


# ---------------------------------------------------------------------------
# Interrupt: drop the cancelled turn's trailing stream output.
#
# Agents keep emitting session/update chunks for a beat after session/cancel
# lands. Forwarding that tail re-opened the row as ACTIVE (every
# non-requires_user_input POST does) *after* the interrupt had settled it on
# AWAITING_INPUT, so the session showed "active" with nothing running — the
# same stuck-status bug reported against claude. OpenCode had immunised
# itself with a private flag; the behaviour now lives in ACPWrapperBase so
# cursor / gemini / copilot / kimi / hermes get it too.
# ---------------------------------------------------------------------------


def _interruptible_wrapper(agent_id: str) -> GenericACPWrapper:
    """A wrapper with just the state ``_handle_interrupt_control`` touches."""
    import threading

    wrapper: GenericACPWrapper = GenericACPWrapper.__new__(GenericACPWrapper)
    wrapper.config = _config(agent_id)
    wrapper.vicoa_client = MagicMock()
    wrapper.session_id = _SESSION_ID
    wrapper.acp = MagicMock()
    wrapper.running = True
    wrapper.debug_log_file = None
    wrapper.last_message_id = None
    wrapper._stopping = False
    wrapper._interrupt_active = False
    wrapper._permission_request_active = False
    wrapper._prompt_cancel_event = threading.Event()
    wrapper._prompt_state_lock = threading.Lock()
    wrapper._prompt_in_flight = True
    wrapper._queued_prompts = []
    wrapper._awaiting_after_next_agent_output = True
    wrapper._awaiting_input_requested_for_message_id = None
    wrapper._assistant_chunk_buffer = "half a sentence from the cancelled turn"
    wrapper._assistant_chunk_first_update_at = 0.0
    wrapper._assistant_chunk_last_update_at = 0.0
    wrapper._drop_stream_output_until_next_prompt = False
    wrapper._turn_produced_output = False
    wrapper._turn_stderr = deque(maxlen=20)
    return wrapper


@pytest.mark.parametrize("agent_id", ["cursor", "gemini", "copilot", "kimi", "hermes"])
def test_interrupt_drops_trailing_stream_output(agent_id: str) -> None:
    wrapper = _interruptible_wrapper(agent_id)

    wrapper._handle_interrupt_control()

    # The partial buffer is dropped rather than flushed as orphan text after
    # the "Interrupted." notice.
    assert wrapper._assistant_chunk_buffer == ""
    assert wrapper._awaiting_after_next_agent_output is False
    # Chunks arriving after the cancel are refused, so nothing re-opens the
    # row as ACTIVE behind the interrupt's AWAITING_INPUT write.
    assert wrapper._drop_stream_output_until_next_prompt is True
    assert wrapper._should_buffer_assistant_chunk("late chunk") is False


@pytest.mark.parametrize("agent_id", ["cursor", "gemini"])
def test_next_prompt_re_enables_stream_output(agent_id: str) -> None:
    """The drop is scoped to the cancelled turn — the next prompt streams
    normally, otherwise a Stop would mute the session permanently."""
    wrapper = _interruptible_wrapper(agent_id)
    wrapper._handle_interrupt_control()

    wrapper._prepare_for_new_prompt()

    assert wrapper._drop_stream_output_until_next_prompt is False
    assert wrapper._interrupt_active is False
    assert wrapper._should_buffer_assistant_chunk("fresh turn") is True
