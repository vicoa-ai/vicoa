"""`vicoa ls` prints full session ids and `vicoa stop <id>` takes only those.

A prefix is not an identity, so `stop` no longer expands one: whatever `ls`
prints is what `stop` takes, exactly.
"""

import types

import pytest

from vicoa import agent_processes
from vicoa.agent_processes import RunningAgent
from vicoa.commands import stop
from vicoa.commands.ls import cmd_ls

SESSION = "3f9c1a2b-0000-4000-8000-000000000000"


def _agent(session_id: str | None = SESSION, pid: int = 4242) -> RunningAgent:
    return RunningAgent(
        pid=pid,
        agent="claude",
        kind="headless",
        session_id=session_id,
        project_path="/x/proj",
        age="05:32",
        command="vicoa headless",
    )


@pytest.fixture
def stopped(monkeypatch) -> list[int]:
    pids: list[int] = []

    def fake_stop(pid, timeout=10.0):
        pids.append(pid)
        return True, "stopped"

    monkeypatch.setattr(agent_processes, "list_running_agents", lambda: [_agent()])
    monkeypatch.setattr(agent_processes, "stop_pid", fake_stop)
    return pids


def test_ls_prints_the_full_session_id(monkeypatch, capsys):
    monkeypatch.delenv("VICOA_API_KEY", raising=False)
    monkeypatch.setattr(
        agent_processes,
        "list_running_agents",
        lambda: [_agent(), _agent(session_id=None, pid=7)],
    )
    cmd_ls(types.SimpleNamespace(json=False, base_url=None))
    out = capsys.readouterr().out
    assert SESSION in out
    assert "pid:7" in out


def test_stop_takes_the_full_id_in_any_case(stopped):
    stop._stop_session_by_id(SESSION.upper(), assume_yes=True)
    assert stopped == [4242]


def test_stop_refuses_a_prefix(stopped, capsys):
    with pytest.raises(SystemExit) as exc:
        stop._stop_session_by_id(SESSION[:8], assume_yes=True)
    assert exc.value.code == 1
    assert stopped == []
    assert "full id" in capsys.readouterr().out
