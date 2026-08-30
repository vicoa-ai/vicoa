"""``build_claude_available_models`` merges the static catalog with the
machine's custom Claude models, the same way paseo's Claude provider does
(``providers/claude/models.ts``). Claude Code has no ``model/list`` RPC, so this
merge — catalog + ``~/.claude/settings.json`` ``model`` + ``ANTHROPIC_*_MODEL``
env — is the whole of "live" discovery for Claude.

All cases inject ``home`` / ``env`` so the real machine's config is never read.
"""

from __future__ import annotations

import json
from pathlib import Path

from integrations.headless.claude_model_catalog import (
    build_claude_available_models,
    _catalog_claude_models,
)


def _write_settings(home: Path, payload: object) -> None:
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "settings.json").write_text(json.dumps(payload), encoding="utf-8")


def test_bare_machine_returns_catalog_only(tmp_path: Path) -> None:
    models = build_claude_available_models(home=tmp_path, env={})
    assert models == _catalog_claude_models()
    assert models, "catalog must ship at least one Claude model"
    # Every entry is a well-formed {id, label}.
    assert all(m["id"] and m["label"] for m in models)
    # A known built-in is present.
    assert any(m["id"] == "claude-sonnet-5" for m in models)


def test_settings_json_custom_model_appended_once(tmp_path: Path) -> None:
    _write_settings(tmp_path, {"model": "sonnet"})
    models = build_claude_available_models(home=tmp_path, env={})
    assert models[-1] == {"id": "sonnet", "label": "sonnet"}
    assert [m["id"] for m in models].count("sonnet") == 1


def test_anthropic_model_env_vars_appended(tmp_path: Path) -> None:
    env = {
        "ANTHROPIC_MODEL": "custom-primary",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "custom-sonnet",
        "ANTHROPIC_SMALL_FAST_MODEL": "custom-fast",
        "ANTHROPIC_API_KEY": "should-be-ignored",  # not a *MODEL key
        "UNRELATED": "nope",
    }
    ids = {m["id"] for m in build_claude_available_models(home=tmp_path, env=env)}
    assert {"custom-primary", "custom-sonnet", "custom-fast"} <= ids
    assert "should-be-ignored" not in ids
    assert "nope" not in ids


def test_custom_id_already_in_catalog_is_not_duplicated(tmp_path: Path) -> None:
    _write_settings(tmp_path, {"model": "claude-opus-4-8"})
    env = {"ANTHROPIC_MODEL": "claude-sonnet-5"}
    models = build_claude_available_models(home=tmp_path, env=env)
    ids = [m["id"] for m in models]
    assert ids.count("claude-opus-4-8") == 1
    assert ids.count("claude-sonnet-5") == 1
    # No custom ids were added — both already existed in the catalog.
    assert models == _catalog_claude_models()


def test_malformed_settings_json_is_ignored(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text("{ not json", encoding="utf-8")
    models = build_claude_available_models(home=tmp_path, env={})
    assert models == _catalog_claude_models()


def test_non_string_and_blank_custom_values_are_skipped(tmp_path: Path) -> None:
    _write_settings(tmp_path, {"model": "   "})  # blank -> skipped
    env = {"ANTHROPIC_MODEL": "", "ANTHROPIC_OTHER_MODEL": "real"}
    models = build_claude_available_models(home=tmp_path, env=env)
    ids = [m["id"] for m in models]
    assert "real" in ids
    assert "" not in ids
    assert "   " not in ids
