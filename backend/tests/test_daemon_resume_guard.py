"""Resuming must not attach a second agent to a live session.

Archiving a session doesn't kill its agent, so a resume can arrive while the
previous process is still running. Both wrappers then subscribe to the same
session's message channel and every user message gets answered twice — reported
from the mobile app against an archived ACP session.

The guard lives in the daemon rather than in each client because the daemon is
the only party that can see whether a process is actually running: sessions are
spawned with ``start_new_session=True`` so they outlive a daemon restart, and
the clients only ever see a heartbeat that lags reality by up to the online
threshold.
"""

from __future__ import annotations

from typing import Any

import pytest

from vicoa.agent_processes import RunningAgent
from vicoa.machine_daemon import MachineDaemon

_INSTANCE_ID = "a0d4ac23-8ec4-47ad-acf7-08c3fc6306a4"


@pytest.fixture
def daemon() -> MachineDaemon:
    return MachineDaemon(api_key="test-key", base_url="http://localhost:0")


def _running(session_id: str | None) -> RunningAgent:
    return RunningAgent(
        pid=4242,
        agent="kimi",
        kind="headless",
        session_id=session_id,
        project_path="/tmp/project",
        age="05:32",
        command="python -m integrations.headless.generic_acp",
    )


def _patch_scan(
    monkeypatch: pytest.MonkeyPatch, agents: list[RunningAgent] | Exception
) -> None:
    def _fake() -> list[RunningAgent]:
        if isinstance(agents, Exception):
            raise agents
        return agents

    monkeypatch.setattr("vicoa.agent_processes.list_running_agents", _fake)


class TestSessionProcessDetection:
    def test_detects_a_running_process_for_the_instance(
        self, daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_scan(monkeypatch, [_running(_INSTANCE_ID)])

        assert daemon._session_process_is_running(_INSTANCE_ID) is True

    def test_ignores_processes_for_other_instances(
        self, daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_scan(monkeypatch, [_running("some-other-session")])

        assert daemon._session_process_is_running(_INSTANCE_ID) is False

    def test_ignores_processes_with_no_session_id(
        self, daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A TUI session the scanner couldn't attribute must not block an
        unrelated resume."""
        _patch_scan(monkeypatch, [_running(None)])

        assert daemon._session_process_is_running(_INSTANCE_ID) is False

    def test_no_processes_at_all(
        self, daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_scan(monkeypatch, [])

        assert daemon._session_process_is_running(_INSTANCE_ID) is False

    def test_a_broken_scan_allows_the_spawn(
        self, daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missed duplicate is recoverable; blocking every resume because
        `ps` failed is not."""
        _patch_scan(monkeypatch, RuntimeError("ps unavailable"))

        assert daemon._session_process_is_running(_INSTANCE_ID) is False


class TestResumeRefusesADuplicate:
    def _frame(self, **resume: Any) -> dict[str, Any]:
        return {
            "params": {
                "directory": "/tmp/project",
                "agent": "kimi",
                "resume": {"agent_instance_id": _INSTANCE_ID, **resume},
            }
        }

    def test_resume_reopens_instead_of_spawning_a_duplicate(
        self, daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_scan(monkeypatch, [_running(_INSTANCE_ID)])
        # Fail loudly if the guard doesn't short-circuit before launching.
        monkeypatch.setattr(
            daemon,
            "_check_agent_installation",
            lambda _agent: pytest.fail("spawn proceeded past the duplicate guard"),
        )
        reopened: list[tuple[str, str]] = []
        monkeypatch.setattr(
            daemon,
            "_update_instance_status",
            lambda iid, status: reopened.append((iid, status)),
        )

        result = daemon.spawn_session_rpc(self._frame())

        # Success, not an error — the running agent is usable.
        assert result.get("error") is None
        assert result.get("agent_instance_id") == _INSTANCE_ID
        assert result.get("already_running") is True
        # And the archived row is reopened so the client shows it as active.
        assert reopened == [(_INSTANCE_ID, "AWAITING_INPUT")]

    def test_a_plain_spawn_is_unaffected_by_a_running_session(
        self, daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The guard is scoped to resume. A new session mints its own id, so a
        running agent for a different instance is irrelevant."""
        _patch_scan(monkeypatch, [_running(_INSTANCE_ID)])
        calls: list[str] = []
        monkeypatch.setattr(
            daemon, "_check_agent_installation", lambda agent: calls.append(agent)
        )
        # Stop before any filesystem or process side effects.
        monkeypatch.setattr(
            daemon,
            "_build_headless_command",
            lambda **_kw: (_ for _ in ()).throw(RuntimeError("stop here")),
        )

        result = daemon.spawn_session_rpc(
            {"params": {"directory": "/tmp/project", "agent": "kimi"}}
        )

        assert calls == ["kimi"], "installation check should have run"
        assert "already running" not in str(result.get("error", "")).lower()
