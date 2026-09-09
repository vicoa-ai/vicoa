"""How an agent profile's ``system_prompt`` reaches each agent (collaboration P1).

The product rule under test is a uniform capability: **every** agent can carry
custom instructions, and **no** agent writes a file to do it. Each agent gets the
best channel it has (`protocol/system_prompt.py`), with a per-turn prompt prefix
as the universal fallback for the ACP agents, which have no system-prompt slot in
ACP v1 or v2.
"""

from __future__ import annotations

import threading
from typing import Any, Optional
from unittest.mock import MagicMock

from integrations.headless.acp_base import ACPWrapperBase, ACPWrapperConfig
from integrations.headless.pi_family.spec import PI_FAMILY_AGENTS
from protocol.system_prompt import (
    SystemPromptTransport,
    cli_flag_for,
    format_prompt_prefix,
    transport_for,
)

_PROMPT = "Refactor ruthlessly."


class TestTransportTable:
    def test_each_agent_gets_its_best_channel(self):
        assert transport_for("claude") is SystemPromptTransport.SDK_APPEND
        assert transport_for("codex") is SystemPromptTransport.COLLAB_SETTINGS
        assert transport_for("pi") is SystemPromptTransport.CLI_FLAG
        assert transport_for("omp") is SystemPromptTransport.CLI_FLAG

    def test_acp_agents_fall_back_to_the_prefix(self):
        """ACP has no system-prompt field in v1 or v2, and `_meta.systemPrompt`
        is a claude-agent-acp-only convention every other agent ignores."""
        for agent in ("opencode", "cursor", "gemini", "copilot", "kimi", "hermes"):
            assert transport_for(agent) is SystemPromptTransport.PROMPT_PREFIX

    def test_unknown_agent_gets_the_universal_fallback_not_nothing(self):
        """A newly added agent must gain working instructions by default rather
        than silently losing them."""
        assert transport_for("some-future-agent") is SystemPromptTransport.PROMPT_PREFIX

    def test_agent_id_is_normalised(self):
        assert transport_for("  CLAUDE ") is SystemPromptTransport.SDK_APPEND
        assert transport_for("") is SystemPromptTransport.PROMPT_PREFIX

    def test_cli_flag_only_for_cli_flag_agents(self):
        assert cli_flag_for("pi") == "--append-system-prompt"
        assert cli_flag_for("omp") == "--append-system-prompt"
        assert cli_flag_for("claude") is None
        assert cli_flag_for("opencode") is None


class TestPiFamilyCliFlag:
    def test_spec_declares_the_flag_both_agents_actually_have(self):
        for agent in ("pi", "omp"):
            assert PI_FAMILY_AGENTS[agent].system_prompt_arg == cli_flag_for(agent)

    def _runner(self, agent: str, system_prompt: Optional[str]):
        from integrations.headless.pi_family.runner import PiFamilyRunner

        runner: Any = PiFamilyRunner.__new__(PiFamilyRunner)
        runner.spec = PI_FAMILY_AGENTS[agent]
        runner.agent_command = "/usr/bin/" + agent
        runner.model = None
        runner.thinking_effort = None
        runner.permission_mode = None
        runner.system_prompt = system_prompt
        runner.agent_session_id = None
        return runner

    def test_flag_is_emitted_with_the_text(self):
        command = self._runner("pi", _PROMPT).build_command()
        assert "--append-system-prompt" in command
        assert command[command.index("--append-system-prompt") + 1] == _PROMPT

    def test_absent_when_no_profile(self):
        assert "--append-system-prompt" not in self._runner("pi", None).build_command()

    def test_blank_is_not_a_prompt(self):
        assert "--append-system-prompt" not in self._runner("pi", "   ").build_command()


class TestClaudeSdkAppend:
    def _runner(self, system_prompt: Optional[str]):
        from integrations.headless.claude_code import HeadlessClaudeRunner

        runner: Any = HeadlessClaudeRunner.__new__(HeadlessClaudeRunner)
        runner.system_prompt = system_prompt
        return runner

    def test_appends_onto_the_preset_rather_than_replacing_it(self):
        """Replacing the preset would strip Claude Code's own tooling behaviour;
        the profile should only *add* guidance."""
        option = self._runner(_PROMPT)._build_system_prompt_option()
        assert option == {
            "type": "preset",
            "preset": "claude_code",
            "append": _PROMPT,
        }

    def test_without_a_profile_it_is_byte_identical_to_the_old_behaviour(self):
        assert self._runner(None)._build_system_prompt_option() == {
            "type": "preset",
            "preset": "claude_code",
        }


class TestCodexDeveloperInstructions:
    def _session(self, system_prompt: Optional[str], effort: Optional[str] = None):
        from integrations.headless.codex_app_server import CodexAppServerSession

        session: Any = CodexAppServerSession.__new__(CodexAppServerSession)
        session.model = "gpt-5.5"
        session.effort = effort
        session.system_prompt = system_prompt
        return session

    def test_rides_the_settings_struct_field_codex_already_has(self):
        settings = self._session(_PROMPT)._collab_settings()
        assert settings["developer_instructions"] == _PROMPT

    def test_absent_when_no_profile(self):
        assert "developer_instructions" not in self._session(None)._collab_settings()

    def test_does_not_disturb_the_other_settings(self):
        settings = self._session(_PROMPT, effort="high")._collab_settings()
        assert settings["model"] == "gpt-5.5"
        assert settings["reasoning_effort"] == "high"


class _TestConfig(ACPWrapperConfig):
    def __init__(self, **overrides: Any) -> None:
        self.api_key = "test-key"
        self.base_url = "http://localhost:8080"
        self.agent_instance_id = "acp-inst-sysprompt"
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


def _acp_wrapper(system_prompt: Optional[str]) -> ACPWrapperBase:
    wrapper: ACPWrapperBase = ACPWrapperBase.__new__(ACPWrapperBase)
    wrapper.config = _TestConfig(system_prompt=system_prompt)
    wrapper.vicoa_client = MagicMock()
    wrapper.acp = MagicMock()
    wrapper.session_id = "sess-1"
    wrapper.running = True
    wrapper.debug_log_file = None
    wrapper._prompt_state_lock = threading.Lock()
    wrapper._supports_image_prompts = False
    return wrapper


class TestAcpPromptPrefix:
    def test_prefix_lands_on_an_attachment_free_turn(self):
        """The regression this guards: `_run_prompt_request` used to bypass
        `_build_prompt_blocks` whenever there were no attachments — i.e. for the
        vast majority of messages — so only attachment-bearing turns would have
        carried the instructions."""
        blocks = _acp_wrapper(_PROMPT)._build_prompt_blocks("fix the bug", ())
        assert blocks == [
            {"type": "text", "text": format_prompt_prefix(_PROMPT) + "fix the bug"}
        ]

    def test_every_turn_carries_it_not_just_the_first(self):
        """First-turn-only fails silently: once the agent compacts, the session
        quietly reverts to a plain agent while the UI still shows the profile."""
        wrapper = _acp_wrapper(_PROMPT)
        for message in ("first", "second", "third"):
            text = wrapper._build_prompt_blocks(message, ())[0]["text"]
            assert text.startswith(_PROMPT)
            assert text.endswith(message)

    def test_no_profile_leaves_the_payload_untouched(self):
        assert _acp_wrapper(None)._build_prompt_blocks("fix the bug", ()) == [
            {"type": "text", "text": "fix the bug"}
        ]

    def test_empty_message_still_yields_one_text_block(self):
        """Preserves the replaced non-attachment path, which always emitted
        exactly one text block; an empty `prompt` array is rejected by agents."""
        assert _acp_wrapper(None)._build_prompt_blocks("", ()) == [
            {"type": "text", "text": ""}
        ]

    def test_prefix_is_separated_from_the_user_text(self):
        assert format_prompt_prefix(_PROMPT) == f"{_PROMPT}\n\n---\n\n"
