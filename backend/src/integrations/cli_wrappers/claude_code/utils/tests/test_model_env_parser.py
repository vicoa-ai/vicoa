"""Unit tests for parse_anthropic_model_env — the helper that normalizes
ANTHROPIC_MODEL into a catalog-matchable id at Claude TUI register time.

Real-world ANTHROPIC_MODEL values come in three shapes:
- bare catalog id: `claude-opus-4-7`
- region-prefixed: `global.anthropic.claude-sonnet-4-6`
- Bedrock-versioned: `us.anthropic.claude-haiku-4-5-20251001-v1:0`

Plan: plans/session-config-storage.md §6 (TUI follow-up — initial model
detection besides the env var).
"""

from __future__ import annotations

import pytest

from integrations.cli_wrappers.claude_code.utils.model_env_parser import (
    parse_anthropic_model_env,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("claude-opus-4-7", "claude-opus-4-7"),
        ("claude-sonnet-4-6", "claude-sonnet-4-6"),
        ("claude-haiku-4-5", "claude-haiku-4-5"),
        # Region prefix only.
        ("global.anthropic.claude-sonnet-4-6", "claude-sonnet-4-6"),
        ("us.anthropic.claude-opus-4-7", "claude-opus-4-7"),
        ("eu.anthropic.claude-haiku-4-5", "claude-haiku-4-5"),
        # Bedrock-versioned (suffix with date + version).
        (
            "us.anthropic.claude-haiku-4-5-20251001-v1:0",
            "claude-haiku-4-5",
        ),
        ("anthropic.claude-opus-4-7-20260301-v2:0", "claude-opus-4-7"),
    ],
)
def test_parses_canonical_id(raw: str, expected: str) -> None:
    assert parse_anthropic_model_env(raw) == expected


def test_returns_none_for_blank() -> None:
    assert parse_anthropic_model_env("") is None
    assert parse_anthropic_model_env(None) is None
    assert parse_anthropic_model_env("   ") is None


def test_preserves_unknown_shapes_verbatim() -> None:
    """If the input doesn't match any known prefix/suffix pattern, return it
    unchanged so a future model id we don't anticipate still surfaces on
    the row (never-delete-a-model-entry rule means an unknown id still gets
    rendered as the raw string by the mobile pill catalog reverse-lookup)."""
    assert (
        parse_anthropic_model_env("custom-future-model-id") == "custom-future-model-id"
    )


def test_trims_whitespace() -> None:
    assert parse_anthropic_model_env("  claude-sonnet-4-6  ") == "claude-sonnet-4-6"
