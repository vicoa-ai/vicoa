"""ACP wrappers name their ``~/.vicoa/`` log folder from a stable, safe slug.

The folder used to be ``f"{agent_type}_wrapper"`` off the *display* name, which
put spaces and capitals on disk ("Gemini CLI_wrapper", "Copilot CLI_wrapper")
right next to the lowercase "codex_native" / "claude_headless" ones. These pin
the folder to the catalog id (or a sanitized display-name fallback) so every
agent's logs live under a uniform lowercase, underscore-joined, space-free name.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from integrations.headless.acp_base import ACPWrapperBase


def _dir_name(catalog_agent_id, agent_type: str) -> str:
    stub = SimpleNamespace(
        config=SimpleNamespace(catalog_agent_id=catalog_agent_id, agent_type=agent_type)
    )
    return ACPWrapperBase._log_dir_name(stub)


@pytest.mark.parametrize(
    "catalog_id, agent_type, expected",
    [
        ("gemini", "Gemini CLI", "gemini_wrapper"),
        ("copilot", "Copilot CLI", "copilot_wrapper"),
        ("kimi", "Kimi CLI", "kimi_wrapper"),
        ("cursor", "Cursor", "cursor_wrapper"),
        ("hermes", "Hermes", "hermes_wrapper"),
        # opencode / legacy codex_acp leave catalog id unset → display fallback.
        (None, "OpenCode", "opencode_wrapper"),
        (None, "Codex", "codex_wrapper"),
    ],
)
def test_log_dir_name_is_lowercase_and_space_free(catalog_id, agent_type, expected):
    name = _dir_name(catalog_id, agent_type)
    assert name == expected
    assert " " not in name
    assert name == name.lower()


def test_display_name_fallback_sanitizes_spaces_and_case():
    # No catalog id and a spaced display name still yields a safe slug.
    assert _dir_name(None, "Gemini CLI") == "gemini_cli_wrapper"


def test_empty_slug_falls_back_to_acp():
    assert _dir_name("", "") == "acp_wrapper"
