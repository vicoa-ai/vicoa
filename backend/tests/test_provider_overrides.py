"""User-defined agent providers from ``~/.vicoa/config.json``.

This is the change that decouples "add an agent" from "ship a release", so the
tests pin the contract a user's hand-edited file relies on: what is accepted,
what is inherited from the agent being extended, and — most importantly — that
one bad entry never costs the user the agents Vicoa ships.
"""

from __future__ import annotations

import pytest

from integrations.headless.generic_acp import (
    GENERIC_ACP_AGENTS,
    build_effective_acp_agents,
    spec_from_override,
)
from protocol.provider_overrides import (
    MAX_PROVIDERS,
    is_valid_provider_id,
    read_provider_overrides,
    validate_providers,
)


BUILTINS = frozenset(GENERIC_ACP_AGENTS)


def _validate(raw):
    return validate_providers(raw, builtin_ids=BUILTINS)


class TestValidation:
    def test_acp_provider_needs_a_command(self):
        """extends:"acp" inherits nothing, so without a command there is no way
        to launch it."""
        clean, errors = _validate({"nope": {"extends": "acp", "label": "Nope"}})
        assert clean == {}
        assert any("must" in e and "command" in e for e in errors)

    def test_new_provider_needs_extends_and_label(self):
        clean, errors = _validate({"orphan": {"command": ["x"]}})
        assert clean == {}
        assert any("extends" in e for e in errors)

        clean, errors = _validate({"orphan": {"extends": "acp", "command": ["x"]}})
        assert clean == {}
        assert any("label" in e for e in errors)

    def test_extends_must_name_something_real(self):
        clean, errors = _validate(
            {"x": {"extends": "windsurf", "label": "X", "command": ["x"]}}
        )
        assert clean == {}
        assert any("unknown provider" in e for e in errors)

    @pytest.mark.parametrize(
        "provider_id", ["Bad", "9lives", "under_score", "has space", "", "-leading"]
    )
    def test_provider_ids_must_be_slugs(self, provider_id):
        """The id becomes a log directory name and a spawn argument."""
        assert not is_valid_provider_id(provider_id)
        clean, errors = _validate(
            {provider_id: {"extends": "acp", "label": "X", "command": ["x"]}}
        )
        assert clean == {}
        assert errors

    def test_a_builtin_may_be_overridden_without_extends_or_label(self):
        """Overriding an agent Vicoa already ships only replaces what is named."""
        clean, errors = _validate({"cursor": {"command": ["/opt/cursor-nightly"]}})
        assert errors == []
        assert clean["cursor"]["command"] == ["/opt/cursor-nightly"]

    def test_one_bad_entry_does_not_drop_the_good_ones(self):
        """The file is hand-edited; a typo must not cost the user every agent."""
        clean, errors = _validate(
            {
                "good": {"extends": "acp", "label": "Good", "command": ["good", "acp"]},
                "bad": {"extends": "acp", "label": "Bad"},  # no command
            }
        )
        assert sorted(clean) == ["good"]
        assert errors

    def test_non_object_section_is_reported_not_raised(self):
        clean, errors = _validate(["not", "an", "object"])
        assert clean == {}
        assert errors

    def test_provider_count_is_capped(self):
        raw = {
            f"p{i}": {"extends": "acp", "label": f"P{i}", "command": ["p"]}
            for i in range(MAX_PROVIDERS + 5)
        }
        clean, errors = _validate(raw)
        assert len(clean) == MAX_PROVIDERS
        assert any(str(MAX_PROVIDERS) in e for e in errors)

    def test_reads_the_nested_config_section(self):
        clean, errors = read_provider_overrides(
            {
                "agents": {
                    "providers": {
                        "x": {"extends": "acp", "label": "X", "command": ["x"]}
                    }
                }
            },
            builtin_ids=BUILTINS,
        )
        assert sorted(clean) == ["x"]
        assert errors == []

    def test_missing_section_is_not_an_error(self):
        assert read_provider_overrides({}, builtin_ids=BUILTINS) == ({}, [])
        assert read_provider_overrides(None, builtin_ids=BUILTINS) == ({}, [])


class TestSpecMerge:
    def test_acp_provider_command_becomes_binary_plus_args(self):
        spec = spec_from_override(
            "gem-nightly",
            {
                "extends": "acp",
                "label": "Gemini Nightly",
                "command": ["gemini-nightly", "--experimental-acp"],
            },
            GENERIC_ACP_AGENTS,
        )
        assert spec is not None
        assert spec.catalog_id == "gem-nightly"
        assert spec.display_name == "Gemini Nightly"
        assert spec.binaries == ("gemini-nightly",)
        assert spec.acp_args == ("--experimental-acp",)

    def test_extending_a_builtin_inherits_its_launch_details(self):
        """A profile that only swaps credentials must keep the base agent's
        binary names, ACP args and model-flag ordering."""
        base = GENERIC_ACP_AGENTS["kimi"]
        spec = spec_from_override(
            "kimi-work",
            {"extends": "kimi", "label": "Kimi (Work)", "env": {"KIMI_KEY": "k"}},
            GENERIC_ACP_AGENTS,
        )
        assert spec is not None
        assert spec.binaries == base.binaries
        assert spec.acp_args == base.acp_args
        assert spec.model_arg == base.model_arg
        assert spec.model_arg_first == base.model_arg_first
        assert spec.extra_dirs == base.extra_dirs
        assert spec.display_name == "Kimi (Work)"
        assert spec.env["KIMI_KEY"] == "k"

    def test_env_is_merged_over_the_base_not_replaced(self):
        """Gemini's NO_BROWSER matters for headless spawns; a profile adding an
        API key must not silently drop it."""
        spec = spec_from_override(
            "gem-work",
            {"extends": "gemini", "label": "G", "env": {"GEMINI_API_KEY": "k"}},
            GENERIC_ACP_AGENTS,
        )
        assert spec is not None
        assert spec.env["NO_BROWSER"] == "true"
        assert spec.env["GEMINI_API_KEY"] == "k"

    def test_builtins_survive_alongside_custom_providers(self):
        clean, _ = _validate(
            {"mine": {"extends": "acp", "label": "Mine", "command": ["mine", "acp"]}}
        )
        effective = build_effective_acp_agents(clean)
        assert set(GENERIC_ACP_AGENTS) < set(effective)
        assert "mine" in effective

    def test_disabling_a_builtin_removes_it(self):
        clean, _ = _validate({"hermes": {"enabled": False}})
        effective = build_effective_acp_agents(clean)
        assert "hermes" not in effective
        assert "cursor" in effective

    def test_overriding_a_builtin_replaces_its_binary_in_place(self):
        clean, _ = _validate({"cursor": {"command": ["/opt/cursor-nightly", "acp"]}})
        effective = build_effective_acp_agents(clean)
        assert effective["cursor"].binaries == ("/opt/cursor-nightly",)
        assert effective["cursor"].catalog_id == "cursor"

    def test_no_overrides_is_exactly_the_builtins(self):
        assert build_effective_acp_agents({}) == GENERIC_ACP_AGENTS
