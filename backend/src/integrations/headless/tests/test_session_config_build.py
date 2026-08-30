"""Unit tests: each headless wrapper builds the right session_config dict
from its own self-state and forwards it into the self-register POST.

Per-agent shape (plans/session-config-storage.md §3.1):
- claude  -> agent, model, thinking_effort, permission_mode
- codex   -> agent, model, reasoning_effort, permission_mode
- opencode-> agent, model, opencode_mode

None-valued keys are stripped so the wire payload only carries values the
wrapper actually knows — the backend treats missing keys as "wrapper doesn't
know," not "explicitly null."
"""

from __future__ import annotations


def test_claude_runner_builds_full_session_config(make_runner) -> None:
    runner = make_runner()
    runner.agent_name = "claude"
    runner.model = "claude-sonnet-4-6"
    runner.thinking_effort = "low"
    runner.permission_mode = "acceptEdits"

    assert runner._build_session_config() == {
        "agent": "claude",
        "model": "claude-sonnet-4-6",
        "thinking_effort": "low",
        "permission_mode": "acceptEdits",
    }


def test_claude_runner_strips_unknown_fields(make_runner) -> None:
    """Wrappers must omit keys whose value is None — the chat header pill
    skips rows for absent fields rather than rendering "None"."""
    runner = make_runner()
    runner.agent_name = "claude"
    runner.model = None
    runner.thinking_effort = None
    runner.permission_mode = None

    assert runner._build_session_config() == {"agent": "claude"}


def _build_codex_runner(**overrides):
    from integrations.headless.codex_native import CodexNativeRunner

    runner = CodexNativeRunner.__new__(CodexNativeRunner)
    runner.model = overrides.get("model")
    runner.effort = overrides.get("effort")
    runner.permission_mode = overrides.get("permission_mode")
    return runner


def test_codex_runner_builds_full_session_config() -> None:
    runner = _build_codex_runner(
        model="gpt-5-codex", effort="medium", permission_mode="auto"
    )
    assert runner._build_session_config() == {
        "agent": "codex",
        "model": "gpt-5-codex",
        "reasoning_effort": "medium",
        "permission_mode": "auto",
    }


def test_codex_runner_strips_unknown_fields() -> None:
    runner = _build_codex_runner()
    assert runner._build_session_config() == {"agent": "codex"}


def _build_codex_acp_wrapper():
    from integrations.headless.codex_acp import CodexACPConfig, CodexACPWrapper

    config = CodexACPConfig.__new__(CodexACPConfig)
    wrapper = CodexACPWrapper.__new__(CodexACPWrapper)
    wrapper.config = config
    return wrapper


def test_codex_acp_reads_env_vars(monkeypatch) -> None:
    """Codex ACP captures model/effort/permission_mode via env (set by main()
    before the wrapper is built). The session_config builder reads them back
    so the wire payload reflects the actual spawn-time config."""
    monkeypatch.setenv("CODEX_MODEL", "gpt-5-codex")
    monkeypatch.setenv("CODEX_REASONING_EFFORT", "high")
    monkeypatch.setenv("CODEX_PERMISSION_MODE", "default")

    wrapper = _build_codex_acp_wrapper()
    assert wrapper.build_session_config() == {
        "agent": "codex",
        "model": "gpt-5-codex",
        "reasoning_effort": "high",
        "permission_mode": "default",
    }


def test_codex_acp_omits_missing_env(monkeypatch) -> None:
    monkeypatch.delenv("CODEX_MODEL", raising=False)
    monkeypatch.delenv("CODEX_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("CODEX_PERMISSION_MODE", raising=False)

    wrapper = _build_codex_acp_wrapper()
    assert wrapper.build_session_config() == {"agent": "codex"}


def _build_opencode_acp_wrapper(**config_kwargs):
    from integrations.headless.opencode_acp import (
        OpenCodeACPConfig,
        OpenCodeACPWrapper,
    )

    config = OpenCodeACPConfig.__new__(OpenCodeACPConfig)
    for k, v in config_kwargs.items():
        setattr(config, k, v)
    wrapper = OpenCodeACPWrapper.__new__(OpenCodeACPWrapper)
    wrapper.config = config
    return wrapper


def test_opencode_acp_builds_session_config() -> None:
    wrapper = _build_opencode_acp_wrapper(
        model="anthropic/claude-sonnet-4-6", agent_mode="plan"
    )
    assert wrapper.build_session_config() == {
        "agent": "opencode",
        "model": "anthropic/claude-sonnet-4-6",
        "opencode_mode": "plan",
    }


def test_opencode_acp_omits_unknown_model() -> None:
    wrapper = _build_opencode_acp_wrapper(model=None, agent_mode="build")
    assert wrapper.build_session_config() == {
        "agent": "opencode",
        "opencode_mode": "build",
    }


def test_acp_base_default_returns_none() -> None:
    """Wrappers that don't override return None so the existing register call
    passes nothing — keeps the activate-existing branch's pre-staged value."""
    from integrations.headless.acp_base import ACPWrapperBase

    class _Stub(ACPWrapperBase):
        def create_session(self) -> None:
            pass

    stub = _Stub.__new__(_Stub)
    assert stub.build_session_config() is None
