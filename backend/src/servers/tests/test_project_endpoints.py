"""Tests for the agent-facing project API (servers/api/projects.py).

What `vicoa project ls` / `project get` rely on: the list is the caller's own
projects with an open-task count, and a single project resolves by UUID or
task key — never by a key that belongs to somebody else.
"""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.database.models import User
from shared.database.task_models import Project, Task
from shared.database.session import get_db
from servers.api.auth import get_current_user_id
from servers.api.projects import project_router


@pytest.fixture
def test_user(test_db):
    return test_db.query(User).first()


def _make_client(test_db, user_id):
    app = FastAPI()
    app.include_router(project_router, prefix="/api/v1")

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = lambda: str(user_id)
    return TestClient(app)


@pytest.fixture
def client(test_db, test_user):
    return _make_client(test_db, test_user.id)


def _project(db, user_id, name, key=None, **kw):
    project = Project(user_id=user_id, name=name, key=key, **kw)
    db.add(project)
    db.commit()
    return project


def _task(db, user_id, project, title, status="todo"):
    task = Task(user_id=user_id, project_id=project.id, title=title, status=status)
    db.add(task)
    db.commit()
    return task


class TestList:
    def test_lists_own_projects_with_open_task_counts(self, client, test_db, test_user):
        vicoa = _project(test_db, test_user.id, "Vicoa", key="VIC")
        empty = _project(test_db, test_user.id, "Empty")
        _task(test_db, test_user.id, vicoa, "open one")
        _task(test_db, test_user.id, vicoa, "open two", status="backlog")
        _task(test_db, test_user.id, vicoa, "closed", status="done")
        _task(test_db, test_user.id, vicoa, "dropped", status="cancelled")

        rows = client.get("/api/v1/projects").json()
        by_id = {row["id"]: row for row in rows}
        assert by_id[str(vicoa.id)]["task_count"] == 2
        assert by_id[str(vicoa.id)]["key"] == "VIC"
        assert by_id[str(empty.id)]["task_count"] == 0
        # Owner-only surface: the caller owns everything it can see.
        assert by_id[str(vicoa.id)]["role"] == "owner"
        assert sorted(by_id[str(vicoa.id)]["scopes"]) == ["sessions", "tasks"]

    def test_archived_hidden_unless_asked(self, client, test_db, test_user):
        _project(test_db, test_user.id, "Live")
        _project(test_db, test_user.id, "Old", is_archived=True)

        names = {row["name"] for row in client.get("/api/v1/projects").json()}
        assert names == {"Live"}
        names = {
            row["name"]
            for row in client.get(
                "/api/v1/projects", params={"include_archived": "true"}
            ).json()
        }
        assert names == {"Live", "Old"}

    def test_other_users_projects_are_invisible(self, test_db, test_user):
        _project(test_db, test_user.id, "Mine")
        stranger = _make_client(test_db, uuid4())
        assert stranger.get("/api/v1/projects").json() == []


class TestGet:
    def test_by_uuid(self, client, test_db, test_user):
        project = _project(test_db, test_user.id, "Vicoa", key="VIC")
        resp = client.get(f"/api/v1/projects/{project.id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Vicoa"
        assert resp.json()["task_count"] == 0

    def test_by_key_case_insensitive(self, client, test_db, test_user):
        project = _project(test_db, test_user.id, "Vicoa", key="VIC")
        assert client.get("/api/v1/projects/vic").json()["id"] == str(project.id)
        assert client.get("/api/v1/projects/VIC").json()["id"] == str(project.id)

    def test_unknown_ref_is_404_not_422(self, client):
        """The route takes whatever was typed: a wrong key is "not found"."""
        assert client.get("/api/v1/projects/NOPE").status_code == 404
        assert client.get(f"/api/v1/projects/{uuid4()}").status_code == 404

    def test_another_users_key_does_not_resolve(self, test_db, test_user):
        """Keys are unique per owner, not globally: the same key names a
        different project for each user, and never leaks across."""
        _project(test_db, test_user.id, "Mine", key="VIC")
        other_id = uuid4()
        other_user = User(id=other_id, email="other@example.com")
        test_db.add(other_user)
        test_db.commit()
        stranger = _make_client(test_db, other_id)
        assert stranger.get("/api/v1/projects/VIC").status_code == 404
        _project(test_db, other_id, "Theirs", key="VIC")
        assert stranger.get("/api/v1/projects/VIC").json()["name"] == "Theirs"
