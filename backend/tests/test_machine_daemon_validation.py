"""Structural validation tests for spawn-session metadata in MachineDaemon.

Covers plans/new-session-model-selection.md §3.9, §5.3, §5.4. The daemon
imports the per-agent enums from `shared.agent_catalog`, so adding a new
catalog value automatically widens what the daemon accepts — no per-deploy
snapshot to maintain.
"""

from __future__ import annotations

import pytest

from vicoa.machine_daemon import MachineDaemon


@pytest.fixture
def daemon() -> MachineDaemon:
    return MachineDaemon(api_key="test-key", base_url="http://localhost:0")


class TestExtractPermissionMode:
    """`permission_mode` validates against the agent's catalog enum."""

    def test_claude_canonical_value_passes_through(self, daemon: MachineDaemon):
        result = daemon._extract_permission_mode(
            {"permission_mode": "acceptEdits"}, agent="claude"
        )
        assert result == "acceptEdits"

    def test_codex_canonical_value_passes_through(self, daemon: MachineDaemon):
        # `plan` and `bypassPermissions` are shared with Claude, but `default`
        # carries different daemon-side translation (see §3.7); the validator
        # only cares that the value is in the per-agent set.
        result = daemon._extract_permission_mode(
            {"permission_mode": "default"}, agent="codex"
        )
        assert result == "default"

    def test_missing_returns_none(self, daemon: MachineDaemon):
        assert daemon._extract_permission_mode({}, agent="claude") is None
        assert daemon._extract_permission_mode(None, agent="claude") is None

    def test_empty_string_returns_none(self, daemon: MachineDaemon):
        assert (
            daemon._extract_permission_mode({"permission_mode": ""}, agent="claude")
            is None
        )

    def test_garbage_raises_value_error(self, daemon: MachineDaemon):
        with pytest.raises(ValueError, match="permission_mode"):
            daemon._extract_permission_mode(
                {"permission_mode": "garbage"}, agent="claude"
            )

    def test_claude_value_rejected_for_codex(self, daemon: MachineDaemon):
        # `acceptEdits` is Claude-only; Codex must reject it so we don't end
        # up emitting Claude-shaped CLI flags into a codex command line.
        with pytest.raises(ValueError, match="permission_mode"):
            daemon._extract_permission_mode(
                {"permission_mode": "acceptEdits"}, agent="codex"
            )

    def test_legacy_alias_still_normalizes_for_claude(self, daemon: MachineDaemon):
        # Back-compat: old web/mobile clients sent `accept_edits` etc. Drop
        # this once both clients ship the v2 selection key (§3.5 migration).
        result = daemon._extract_permission_mode(
            {"permission_mode": "accept_edits"}, agent="claude"
        )
        assert result == "acceptEdits"

    def test_opencode_silently_ignores_mode(self, daemon: MachineDaemon):
        # OpenCode has no `permission_mode` knob in v1 — the extractor must
        # not raise when given one (a forward-compat client might send the
        # field as `null` or an artifact of shared persistence shape).
        assert (
            daemon._extract_permission_mode(
                {"permission_mode": "plan"}, agent="opencode"
            )
            is None
        )


class TestExtractThinkingEffort:
    """`thinking_effort` (Claude) — opaque enum, raises on bad value."""

    def test_canonical_value_passes_through(self, daemon: MachineDaemon):
        assert daemon._extract_thinking_effort({"thinking_effort": "high"}) == "high"

    def test_xhigh_opus_only_value_is_accepted(self, daemon: MachineDaemon):
        # The catalog flags `xhigh` as Opus-only via per-model `thinking_efforts`.
        # Per-model gating is a UI concern — the daemon accepts any catalog
        # member and lets the agent CLI reject mismatches.
        assert daemon._extract_thinking_effort({"thinking_effort": "xhigh"}) == "xhigh"

    def test_missing_returns_none(self, daemon: MachineDaemon):
        assert daemon._extract_thinking_effort({}) is None
        assert daemon._extract_thinking_effort(None) is None

    def test_garbage_raises_value_error(self, daemon: MachineDaemon):
        with pytest.raises(ValueError, match="thinking_effort"):
            daemon._extract_thinking_effort({"thinking_effort": "ultra"})


class TestExtractReasoningEffort:
    """`reasoning_effort` (Codex) — same shape as thinking_effort."""

    def test_canonical_value_passes_through(self, daemon: MachineDaemon):
        assert (
            daemon._extract_reasoning_effort({"reasoning_effort": "medium"}) == "medium"
        )

    def test_missing_returns_none(self, daemon: MachineDaemon):
        assert daemon._extract_reasoning_effort({}) is None
        assert daemon._extract_reasoning_effort(None) is None

    def test_garbage_raises_value_error(self, daemon: MachineDaemon):
        with pytest.raises(ValueError, match="reasoning_effort"):
            daemon._extract_reasoning_effort({"reasoning_effort": "ultra"})


class TestSpawnSessionRpcSurfacesValidationError:
    """Bad metadata must convert to an `{"error": ...}` RPC result, not a Popen."""

    def test_bad_permission_mode_returns_error_dict(
        self, daemon: MachineDaemon, tmp_path
    ):
        frame = {
            "method": "spawn-session",
            "params": {
                "directory": str(tmp_path),
                "agent": "claude",
                "metadata": {"permission_mode": "garbage"},
            },
        }
        result = daemon.spawn_session_rpc(frame)
        assert "error" in result
        assert "permission_mode" in result["error"]
        # No agent_instance_id was returned — verifies we failed before Popen.
        assert "agent_instance_id" not in result
