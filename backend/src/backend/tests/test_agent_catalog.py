"""Tests for the agent catalog module and endpoint (plans/new-session-model-selection.md §5.1–5.2)."""

import hashlib
import json

from shared.agent_catalog import (
    AGENT_CATALOG,
    AGENT_CATALOG_ETAG,
    AGENT_CATALOG_JSON,
    PERMISSION_MODES,
    REASONING_EFFORTS,
    THINKING_EFFORTS,
)


class TestAgentCatalogShape:
    """Verify the static catalog has the expected agents and enums."""

    def test_contains_expected_agents(self):
        agent_ids = {agent["id"] for agent in AGENT_CATALOG["agents"]}
        assert agent_ids == {
            "claude",
            "codex",
            "opencode",
            "cursor",
            "gemini",
            "copilot",
            "kimi",
            "hermes",
        }

    def test_claude_default_model_is_sonnet(self):
        claude = next(a for a in AGENT_CATALOG["agents"] if a["id"] == "claude")
        defaults = [m for m in claude["models"] if m.get("is_default")]
        assert len(defaults) == 1
        assert defaults[0]["id"] == "claude-sonnet-5"

    def test_xhigh_is_common_for_all_models(self):
        """`xhigh` is a common thinking effort — every Claude model can pick it."""
        claude = next(a for a in AGENT_CATALOG["agents"] if a["id"] == "claude")
        xhigh = next(e for e in claude["thinking_efforts"] if e["id"] == "xhigh")
        assert xhigh.get("opt_in") is not True

    def test_default_thinking_effort_is_high(self):
        """Agent-level default is `high`; Opus 4.7+ override to `xhigh`."""
        claude = next(a for a in AGENT_CATALOG["agents"] if a["id"] == "claude")
        defaults = [e for e in claude["thinking_efforts"] if e.get("is_default")]
        assert len(defaults) == 1
        assert defaults[0]["id"] == "high"

    def test_auto_marked_opt_in_at_agent_level(self):
        """`auto` is an opt-in capability — only modern models opt in."""
        claude = next(a for a in AGENT_CATALOG["agents"] if a["id"] == "claude")
        auto = next(e for e in claude["permission_modes"] if e["id"] == "auto")
        assert auto.get("opt_in") is True

    def test_modern_models_opt_into_auto(self):
        """Sonnet 4.6+, Opus 4.7+, Opus 5, and Fable 5 per-model arrays opt into `auto`."""
        claude = next(a for a in AGENT_CATALOG["agents"] if a["id"] == "claude")
        for model in claude["models"]:
            model_id = model["id"]
            is_opus_47_plus = (
                model_id.startswith("claude-opus-4-7")
                or model_id.startswith("claude-opus-4-8")
                or model_id.startswith("claude-opus-5")
            )
            is_sonnet_46_plus = model_id.startswith(
                "claude-sonnet-4-6"
            ) or model_id.startswith("claude-sonnet-5")
            # Fable 5 is newer/more capable than Opus 4.8, so it carries the
            # same `auto`-mode SDK capability.
            is_fable_5 = model_id.startswith("claude-fable-5")
            should_have_auto = is_opus_47_plus or is_sonnet_46_plus or is_fable_5
            perm_opts = model.get("permission_modes", [])
            if should_have_auto:
                assert "auto" in perm_opts, f"{model_id} should opt into `auto`"
            else:
                assert "auto" not in perm_opts, f"{model_id} must NOT opt into `auto`"

    def test_opus_47_plus_default_to_xhigh(self):
        """Opus 4.7/4.8, Opus 5, and Fable 5 per-model `default_thinking_effort` → `xhigh`."""
        claude = next(a for a in AGENT_CATALOG["agents"] if a["id"] == "claude")
        for model in claude["models"]:
            model_id = model["id"]
            is_opus_47_plus = (
                model_id.startswith("claude-opus-4-7")
                or model_id.startswith("claude-opus-4-8")
                or model_id.startswith("claude-opus-5")
            )
            # Fable 5 is the deepest-reasoning tier, so it shares the xhigh
            # baseline with Opus 4.7+.
            is_fable_5 = model_id.startswith("claude-fable-5")
            should_default_xhigh = is_opus_47_plus or is_fable_5
            override = model.get("default_thinking_effort")
            if should_default_xhigh:
                assert override == "xhigh", (
                    f"{model_id} should override default_thinking_effort to xhigh"
                )
            else:
                assert override is None, (
                    f"{model_id} must NOT carry a default_thinking_effort override"
                )


class TestDerivedConstants:
    """The daemon imports these for structural validation — keep them honest."""

    def test_etag_is_sha256_of_json(self):
        assert (
            AGENT_CATALOG_ETAG
            == hashlib.sha256(AGENT_CATALOG_JSON.encode("utf-8")).hexdigest()
        )

    def test_json_round_trips_catalog(self):
        assert json.loads(AGENT_CATALOG_JSON) == AGENT_CATALOG

    def test_permission_modes_per_agent(self):
        # `auto` is part of Claude's superset (gated to Sonnet 4.6+ / Opus 4.7+
        # via per-model allowlists — the daemon doesn't know about the gating,
        # it just validates against this superset).
        assert PERMISSION_MODES["claude"] == {
            "default",
            "auto",
            "acceptEdits",
            "plan",
            "bypassPermissions",
        }
        assert PERMISSION_MODES["codex"] == {"default", "bypassPermissions"}
        # OpenCode has no permission_modes block in v1 — it must be absent, not
        # an empty set, so daemon validation can distinguish "agent has no
        # permission_mode knob" from "agent has knob but value is unknown".
        assert "opencode" not in PERMISSION_MODES

    def test_thinking_efforts_union_includes_xhigh(self):
        assert "xhigh" in THINKING_EFFORTS
        assert {"off", "low", "medium", "high", "max"}.issubset(THINKING_EFFORTS)

    def test_reasoning_efforts_match_codex_enum(self):
        # Subset of codex's full enum (none/minimal/low/medium/high/xhigh) —
        # we expose the four most useful for coding sessions.
        assert REASONING_EFFORTS == {"low", "medium", "high", "xhigh"}


class TestAgentCatalogEndpoint:
    """GET /api/v1/agent-catalog — public-cache-safe with ETag conditional GET."""

    def test_returns_200_with_catalog_and_etag(self, authenticated_client):
        response = authenticated_client.get("/api/v1/agent-catalog")
        assert response.status_code == 200
        # Body is the pre-serialized JSON, byte-identical with the constant.
        assert response.json() == AGENT_CATALOG
        assert response.headers["etag"] == AGENT_CATALOG_ETAG

    def test_matching_if_none_match_returns_304(self, authenticated_client):
        response = authenticated_client.get(
            "/api/v1/agent-catalog",
            headers={"If-None-Match": AGENT_CATALOG_ETAG},
        )
        assert response.status_code == 304
        assert response.content == b""

    def test_non_matching_if_none_match_returns_full_body(self, authenticated_client):
        response = authenticated_client.get(
            "/api/v1/agent-catalog",
            headers={"If-None-Match": "deadbeef"},
        )
        assert response.status_code == 200
        assert response.json() == AGENT_CATALOG
