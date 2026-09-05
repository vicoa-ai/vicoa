"""Daemon wiring for the generic ACP agents (cursor/gemini/copilot/kimi/hermes).

Covers spawn-command construction, agent normalization, installation
detection and availability reporting. Mirrors the command-vector idiom of
test_machine_daemon_command_build.py — we assert the argv the daemon would
Popen, never spawning anything.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from vicoa.machine_daemon import MachineDaemon


@pytest.fixture
def daemon() -> MachineDaemon:
    return MachineDaemon(api_key="test-key", base_url="http://localhost:0")


def _pair_following(cmd: list[str], flag: str) -> str | None:
    try:
        idx = cmd.index(flag)
    except ValueError:
        return None
    return cmd[idx + 1] if idx + 1 < len(cmd) else None


def _build(daemon: MachineDaemon, agent: str, **metadata: Any) -> list[str]:
    return daemon._build_headless_command(
        directory="/tmp/x",
        agent=agent,
        session_id="sess-1",
        metadata=metadata or None,
    )


class TestGenericAgentCommandBuild:
    @pytest.mark.parametrize("agent", ["cursor", "gemini", "copilot", "kimi", "hermes"])
    def test_spawns_generic_acp_module_with_agent_flag(
        self, daemon: MachineDaemon, agent: str
    ):
        cmd = _build(daemon, agent)
        assert cmd[:3] == [sys.executable, "-m", "integrations.headless.generic_acp"]
        assert _pair_following(cmd, "--agent") == agent
        assert _pair_following(cmd, "--project-path") == "/tmp/x"
        assert _pair_following(cmd, "--session-id") == "sess-1"

    def test_model_flag_flows_through(self, daemon: MachineDaemon):
        cmd = _build(daemon, "gemini", model="gemini-2.5-flash")
        assert _pair_following(cmd, "--model") == "gemini-2.5-flash"

    def test_permission_mode_flows_through(self, daemon: MachineDaemon):
        cmd = _build(daemon, "cursor", permission_mode="plan")
        assert _pair_following(cmd, "--permission-mode") == "plan"

    def test_invalid_permission_mode_rejected(self, daemon: MachineDaemon):
        with pytest.raises(ValueError):
            _build(daemon, "cursor", permission_mode="not-a-mode")

    def test_prompt_flows_through(self, daemon: MachineDaemon):
        cmd = _build(daemon, "kimi", prompt="fix the bug")
        assert _pair_following(cmd, "--prompt") == "fix the bug"

    def test_display_name_used(self, daemon: MachineDaemon):
        cmd = _build(daemon, "copilot")
        assert _pair_following(cmd, "--name") == "Copilot CLI"


class TestGenericAgentNormalization:
    @pytest.mark.parametrize("agent", ["cursor", "gemini", "copilot", "kimi", "hermes"])
    def test_new_agents_accepted(self, daemon: MachineDaemon, agent: str):
        assert daemon._normalize_agent(agent) == agent

    def test_unknown_agent_still_rejected(self, daemon: MachineDaemon):
        with pytest.raises(ValueError):
            daemon._normalize_agent("windsurf")


class TestGenericAgentDetection:
    def test_available_agents_reports_all_known_agents(
        self, daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(daemon, "_check_agent_installation", lambda agent: None)
        agents = daemon._detect_available_agents()
        assert set(agents) == {
            "claude",
            "codex",
            "opencode",
            "cursor",
            "gemini",
            "copilot",
            "kimi",
            "hermes",
            # Native-RPC Pi family — detected the same way, so the app's
            # per-machine agent scan picks them up with no client change.
            "omp",
            "pi",
        }
        assert all(agents.values())

    def test_installation_check_uses_binary_candidates(
        self, daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch
    ):
        """Cursor must be detected through either `cursor-agent` or `agent`."""
        found = {"agent"}
        monkeypatch.setattr(
            "vicoa.machine_daemon._find_cli_in_common_locations",
            lambda name: f"/usr/bin/{name}" if name in found else None,
        )
        assert daemon._check_agent_installation("cursor") is None

    def test_installation_check_reports_missing_binary(
        self, daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(
            "vicoa.machine_daemon._find_cli_in_common_locations", lambda name: None
        )
        error = daemon._check_agent_installation("gemini")
        assert error is not None
        assert "gemini" in error.lower()

    def test_installation_check_finds_kimi_in_extra_dir(
        self, daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch
    ):
        """kimi-code installs to ~/.kimi-code/bin (off PATH); detection must
        fall back to the spec's extra_dirs rather than report 'not installed'."""
        import os

        monkeypatch.setattr(
            "vicoa.machine_daemon._find_cli_in_common_locations", lambda name: None
        )
        expected = os.path.join(os.path.expanduser("~/.kimi-code/bin"), "kimi")
        monkeypatch.setattr(
            "integrations.headless.generic_acp.os.path.isfile",
            lambda p: p == expected,
        )
        monkeypatch.setattr(
            "integrations.headless.generic_acp.os.access",
            lambda p, mode: p == expected,
        )
        assert daemon._check_agent_installation("kimi") is None


class TestSpawnRequestModelValidation:
    """Server-side SpawnSessionRequest must accept catalog agents."""

    @pytest.mark.parametrize(
        "agent",
        [
            "claude",
            "codex",
            "opencode",
            "cursor",
            "gemini",
            "copilot",
            "kimi",
            "hermes",
        ],
    )
    def test_catalog_agents_accepted(self, agent: str):
        from servers.api.models import SpawnSessionRequest

        req = SpawnSessionRequest(directory="/tmp/x", agent=agent)
        assert req.agent == agent

    def test_unknown_agent_rejected(self):
        from servers.api.models import SpawnSessionRequest

        with pytest.raises(ValueError):
            SpawnSessionRequest(directory="/tmp/x", agent="windsurf")

    def test_legacy_claude_code_alias(self):
        from servers.api.models import SpawnSessionRequest

        assert (
            SpawnSessionRequest(directory="/tmp/x", agent="Claude Code").agent
            == "claude"
        )
