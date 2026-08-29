"""Tests for the Codex TUI register-time session_config builder.

Mirrors integrations/cli_wrappers/claude_code/utils/tests/test_initial_session_config.py
but reads the CODEX_* env vars that the daemon sets at spawn time. Closes the
brief "row exists but session_config is null" window mobile sees right after
spawn, before the Rust bridge has had a chance to PATCH from a TurnContext
event.
"""

from __future__ import annotations

from integrations.codex_helpers.initial_session_config import (
    build_initial_session_config_codex,
)


def test_includes_full_payload_when_all_env_set(monkeypatch) -> None:
    monkeypatch.setenv("CODEX_MODEL", "gpt-5-codex")
    monkeypatch.setenv("CODEX_REASONING_EFFORT", "high")
    monkeypatch.setenv("CODEX_PERMISSION_MODE", "on-request")
    assert build_initial_session_config_codex() == {
        "agent": "codex",
        "model": "gpt-5-codex",
        "reasoning_effort": "high",
        "permission_mode": "on-request",
    }


def test_omits_missing_env_keys(monkeypatch) -> None:
    """When the daemon only sets some CODEX_* vars (e.g. model but not
    permission_mode), the payload carries only the known values. Absent
    keys are NOT serialized as null — the server's field-present
    semantics would otherwise overwrite any pre-staged row value with
    None."""
    monkeypatch.delenv("CODEX_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("CODEX_PERMISSION_MODE", raising=False)
    monkeypatch.setenv("CODEX_MODEL", "gpt-5")
    assert build_initial_session_config_codex() == {
        "agent": "codex",
        "model": "gpt-5",
    }


def test_returns_none_when_nothing_known(monkeypatch) -> None:
    """All CODEX_* vars absent — return None so the launcher omits the
    session_config field from the register POST entirely. Mirrors
    the Claude TUI helper's no-knowledge path."""
    monkeypatch.delenv("CODEX_MODEL", raising=False)
    monkeypatch.delenv("CODEX_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("CODEX_PERMISSION_MODE", raising=False)
    assert build_initial_session_config_codex() is None


def test_blank_env_treated_as_missing(monkeypatch) -> None:
    """Empty-string env values (`export CODEX_MODEL=`) count as unknown.
    Some shells emit them when a flag is forwarded without a value."""
    monkeypatch.setenv("CODEX_MODEL", "")
    monkeypatch.setenv("CODEX_REASONING_EFFORT", "")
    monkeypatch.setenv("CODEX_PERMISSION_MODE", "")
    assert build_initial_session_config_codex() is None
