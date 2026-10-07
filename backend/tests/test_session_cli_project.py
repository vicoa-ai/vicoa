"""Unit tests for ``vicoa session update --project``.

The PATCH itself is covered in ``test_session_project_patch.py``; here, how
the CLI turns a project reference into ``project_id`` (key/name/id through
the same lookup ``task --project`` uses, ``none`` = No project) and how it
tells an older server that ignored the field from a real move.
"""

from __future__ import annotations

import types

import pytest

from vicoa.commands import instance as I
from vicoa.commands import project as P

_PROJECTS = [
    {"id": "p-app", "key": "APP", "name": "app", "is_archived": False},
    {"id": "p-web", "key": "WEB", "name": "alpha-web", "is_archived": False},
]


def _args(**over):
    base = {
        "session_id": "s-1",
        "json": False,
        "api_key": "k",
        "base_url": None,
        "title": None,
        "task": None,
        "unlink_task": False,
        "worktree": None,
        "project": None,
    }
    base.update(over)
    return types.SimpleNamespace(**base)


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """A current server: lists the projects and echoes the row it wrote."""
    sent: list[tuple] = []

    def fake_request(args, api_key, method, endpoint, *, params=None, json=None):
        sent.append((method, endpoint, json))
        if method == "GET" and endpoint == "/api/v1/projects":
            return _PROJECTS
        return {"agent_instance_id": "s-1", "project_id": json["project_id"]}

    monkeypatch.setattr(I, "request", fake_request)
    monkeypatch.setattr(P, "request", fake_request)
    monkeypatch.setattr(I, "_require_session_id", lambda ref: "s-1")
    return sent


def test_project_key_is_resolved_and_patched(server, capsys) -> None:
    assert I._cmd_update(_args(project="web"), "k") == 0
    method, endpoint, body = server[-1]
    assert (method, endpoint) == ("PATCH", "/api/v1/agent-instances/s-1")
    assert body == {"project_id": "p-web"}
    assert "filed under project alpha-web" in capsys.readouterr().out


def test_project_name_works_too(server) -> None:
    assert I._cmd_update(_args(project="app"), "k") == 0
    assert server[-1][2] == {"project_id": "p-app"}


def test_none_files_under_no_project_without_a_lookup(server, capsys) -> None:
    assert I._cmd_update(_args(project="none"), "k") == 0
    assert [call[0] for call in server] == ["PATCH"]
    assert server[-1][2] == {"project_id": None}
    assert "filed under No project" in capsys.readouterr().out


def test_unknown_project_exits_before_patching(server) -> None:
    with pytest.raises(SystemExit) as exc:
        I._cmd_update(_args(project="nope"), "k")
    assert exc.value.code == 2
    assert "PATCH" not in [call[0] for call in server]


def test_combines_with_a_rename(server) -> None:
    assert I._cmd_update(_args(project="WEB", title="Auth"), "k") == 0
    assert server[-1][2] == {"name": "Auth", "project_id": "p-web"}


def test_server_that_ignored_project_id_is_reported(monkeypatch, capsys) -> None:
    """An older server drops unknown PATCH keys and answers 200 with the row
    as it was; the CLI must not call that a move."""

    def fake_request(args, api_key, method, endpoint, *, params=None, json=None):
        if method == "GET":
            return _PROJECTS
        return {"agent_instance_id": "s-1", "project_id": "p-app"}

    monkeypatch.setattr(I, "request", fake_request)
    monkeypatch.setattr(P, "request", fake_request)
    monkeypatch.setattr(I, "_require_session_id", lambda ref: "s-1")

    assert I._cmd_update(_args(project="web"), "k") == 1
    out = capsys.readouterr()
    assert "predates `--project`" in out.err
    assert "filed under" not in out.out


def test_nothing_to_update_mentions_project(capsys) -> None:
    assert I._cmd_update(_args(), "k") == 2
    assert "--project" in capsys.readouterr().err
