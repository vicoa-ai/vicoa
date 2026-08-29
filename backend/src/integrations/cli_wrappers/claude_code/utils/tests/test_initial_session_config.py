"""Tests for the register-time session_config builder.

Folds the wrapper's CLI args + ANTHROPIC_MODEL env into the dict we POST
on first register, so the row has model + permission_mode populated
before the JSONLMonitor catches up via the jsonl. Closes the brief
"row exists but session_config is null" window users see when opening
the chat page right after spawn.
"""

from __future__ import annotations

from integrations.cli_wrappers.claude_code.utils.initial_session_config import (
    build_initial_session_config,
)


def test_includes_model_from_env() -> None:
    sc = build_initial_session_config(
        anthropic_model_env="claude-sonnet-4-6",
        permission_mode=None,
        dangerously_skip_permissions=False,
    )
    # Sonnet defaults to `high` thinking; covered separately by
    # test_sonnet_46_gets_high_thinking_default.
    assert sc == {
        "agent": "claude",
        "model": "claude-sonnet-4-6",
        "thinking_effort": "high",
    }


def test_includes_permission_mode_flag() -> None:
    sc = build_initial_session_config(
        anthropic_model_env=None,
        permission_mode="plan",
        dangerously_skip_permissions=False,
    )
    assert sc == {"agent": "claude", "permission_mode": "plan"}


def test_dangerously_skip_implies_bypass() -> None:
    """`--dangerously-skip-permissions` is the CLI shortcut for
    `--permission-mode bypassPermissions`. The register payload must
    normalize it so the mobile pill picks up the canonical id."""
    sc = build_initial_session_config(
        anthropic_model_env=None,
        permission_mode=None,
        dangerously_skip_permissions=True,
    )
    assert sc == {"agent": "claude", "permission_mode": "bypassPermissions"}


def test_explicit_permission_mode_wins_over_skip_flag() -> None:
    """If both are present, the explicit `--permission-mode <x>` value is
    authoritative — matches what the Claude CLI itself does (the skip
    flag is just shorthand)."""
    sc = build_initial_session_config(
        anthropic_model_env=None,
        permission_mode="acceptEdits",
        dangerously_skip_permissions=True,
    )
    assert sc == {"agent": "claude", "permission_mode": "acceptEdits"}


def test_full_payload() -> None:
    sc = build_initial_session_config(
        anthropic_model_env="us.anthropic.claude-opus-4-7-20251001-v1:0",
        permission_mode="bypassPermissions",
        dangerously_skip_permissions=False,
    )
    assert sc == {
        "agent": "claude",
        "model": "claude-opus-4-7",
        "thinking_effort": "xhigh",
        "permission_mode": "bypassPermissions",
    }


def test_returns_none_when_nothing_known() -> None:
    """No env, no flags — return None so the wrapper omits session_config
    from the POST entirely (field-present semantics preserve any value the
    spawn-request row pre-staged)."""
    assert (
        build_initial_session_config(
            anthropic_model_env=None,
            permission_mode=None,
            dangerously_skip_permissions=False,
        )
        is None
    )


def test_opus_47_gets_xhigh_thinking_default() -> None:
    """The Claude TUI doesn't expose a current thinking effort at register
    time, but the catalog defines model-tier defaults that make sense:
    Opus carries the deeper `xhigh` effort it's uniquely capable of."""
    sc = build_initial_session_config(
        anthropic_model_env="claude-opus-4-7",
        permission_mode=None,
        dangerously_skip_permissions=False,
    )
    assert sc == {
        "agent": "claude",
        "model": "claude-opus-4-7",
        "thinking_effort": "xhigh",
    }


def test_opus_48_gets_xhigh_thinking_default() -> None:
    sc = build_initial_session_config(
        anthropic_model_env="claude-opus-4-8",
        permission_mode=None,
        dangerously_skip_permissions=False,
    )
    assert sc == {
        "agent": "claude",
        "model": "claude-opus-4-8",
        "thinking_effort": "xhigh",
    }


def test_sonnet_46_gets_high_thinking_default() -> None:
    """Non-Opus tiers default to `high` per the user's UX preference — the
    catalog's `low` agent-level default is too conservative for the
    interactive coding use case."""
    sc = build_initial_session_config(
        anthropic_model_env="claude-sonnet-4-6",
        permission_mode=None,
        dangerously_skip_permissions=False,
    )
    assert sc == {
        "agent": "claude",
        "model": "claude-sonnet-4-6",
        "thinking_effort": "high",
    }


def test_haiku_45_gets_high_thinking_default() -> None:
    sc = build_initial_session_config(
        anthropic_model_env="claude-haiku-4-5",
        permission_mode=None,
        dangerously_skip_permissions=False,
    )
    assert sc == {
        "agent": "claude",
        "model": "claude-haiku-4-5",
        "thinking_effort": "high",
    }


def test_1m_context_variants_share_base_model_default() -> None:
    """`[1m]` is a context-window variant; the base model's thinking default
    applies."""
    sc = build_initial_session_config(
        anthropic_model_env="claude-opus-4-7[1m]",
        permission_mode=None,
        dangerously_skip_permissions=False,
    )
    assert sc is not None
    assert sc["thinking_effort"] == "xhigh"


def test_unknown_claude_model_skips_thinking_default() -> None:
    """Don't guess for an id we can't map — leave thinking_effort absent
    so the JSONLMonitor's /effort path can fill it in if/when the user
    runs the command."""
    sc = build_initial_session_config(
        anthropic_model_env="claude-quasar-9000",
        permission_mode=None,
        dangerously_skip_permissions=False,
    )
    assert sc is not None
    assert "thinking_effort" not in sc


def test_returns_none_when_env_only_blank() -> None:
    """Empty/whitespace ANTHROPIC_MODEL counts as nothing known."""
    assert (
        build_initial_session_config(
            anthropic_model_env="   ",
            permission_mode=None,
            dangerously_skip_permissions=False,
        )
        is None
    )
