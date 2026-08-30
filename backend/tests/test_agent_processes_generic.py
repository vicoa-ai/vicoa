"""Process classification for the generic ACP headless agents."""

from __future__ import annotations

import pytest

from vicoa.agent_processes import _classify


@pytest.mark.parametrize("agent", ["cursor", "gemini", "copilot", "kimi", "hermes"])
def test_generic_acp_headless_processes_are_classified(agent: str) -> None:
    command = (
        "/usr/bin/python3 -m integrations.headless.generic_acp "
        f"--agent {agent} --api-key k --base-url http://x --project-path /tmp/p"
    )
    assert _classify(command) == (agent, "headless")


def test_generic_acp_without_agent_flag_still_counts_as_headless() -> None:
    command = "/usr/bin/python3 -m integrations.headless.generic_acp --api-key k"
    agent, kind = _classify(command)
    assert kind == "headless"
