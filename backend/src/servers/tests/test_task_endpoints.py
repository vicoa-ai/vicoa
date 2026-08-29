"""Tests for the agent-facing task API (servers/api/tasks.py).

The human-facing equivalent is covered in backend/tests/test_tasks.py; this
suite proves the same CRUD works under the agent RS256-JWT auth used by the
CLI, including user scoping and the Inbox default.
"""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.database.models import User
from shared.database.session import get_db
from servers.api.auth import get_current_user_id
from servers.api.tasks import task_router


@pytest.fixture
def test_user(test_db):
    """The user seeded by the shared ``test_db`` fixture."""
    return test_db.query(User).first()


def _make_client(test_db, user_id):
    """A TestClient for a minimal app mounting only the task router.

    Avoids standing up the full unified server (MCP mount, websockets) — the
    router plus overridden ``get_db``/``get_current_user_id`` is all these
    endpoints touch.
    """
    app = FastAPI()
    app.include_router(task_router, prefix="/api/v1")

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = lambda: str(user_id)
    return TestClient(app)


@pytest.fixture
def client(test_db, test_user):
    return _make_client(test_db, test_user.id)


class TestTaskCrud:
    def test_create_defaults_to_inbox(self, client):
        resp = client.post("/api/v1/tasks", json={"title": "Write the CLI"})
        assert resp.status_code == 201, resp.text
        task = resp.json()
        assert task["title"] == "Write the CLI"
        assert task["status"] == "backlog"
        assert task["priority"] == "none"
        assert task["project_id"] is not None  # landed in the auto-created Inbox

    def test_create_with_fields(self, client):
        resp = client.post(
            "/api/v1/tasks",
            json={
                "title": "Urgent thing",
                "description": "do it",
                "status": "todo",
                "priority": "urgent",
            },
        )
        assert resp.status_code == 201, resp.text
        task = resp.json()
        assert task["status"] == "todo"
        assert task["priority"] == "urgent"
        assert task["description"] == "do it"

    def test_list_and_status_filter(self, client):
        client.post("/api/v1/tasks", json={"title": "A", "status": "todo"})
        client.post("/api/v1/tasks", json={"title": "B", "status": "done"})

        all_tasks = client.get("/api/v1/tasks").json()
        assert {t["title"] for t in all_tasks} == {"A", "B"}

        todo_only = client.get("/api/v1/tasks", params={"status": "todo"}).json()
        assert [t["title"] for t in todo_only] == ["A"]

    def test_list_priority_filter(self, client):
        client.post("/api/v1/tasks", json={"title": "A", "priority": "high"})
        client.post("/api/v1/tasks", json={"title": "B", "priority": "low"})

        high_only = client.get("/api/v1/tasks", params={"priority": "high"}).json()
        assert [t["title"] for t in high_only] == ["A"]

    def test_list_status_and_priority_filter_combine(self, client):
        client.post(
            "/api/v1/tasks", json={"title": "A", "status": "todo", "priority": "high"}
        )
        client.post(
            "/api/v1/tasks", json={"title": "B", "status": "todo", "priority": "low"}
        )
        client.post(
            "/api/v1/tasks", json={"title": "C", "status": "done", "priority": "high"}
        )

        urgent_todo = client.get(
            "/api/v1/tasks", params={"status": "todo", "priority": "high"}
        ).json()
        assert [t["title"] for t in urgent_todo] == ["A"]

    def test_invalid_priority_rejected(self, client):
        resp = client.get("/api/v1/tasks", params={"priority": "nonsense"})
        assert resp.status_code == 422

    def test_get_roundtrip(self, client):
        created = client.post("/api/v1/tasks", json={"title": "Fetch me"}).json()
        resp = client.get(f"/api/v1/tasks/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_update_only_touches_sent_fields(self, client):
        created = client.post(
            "/api/v1/tasks", json={"title": "Before", "priority": "low"}
        ).json()
        resp = client.patch(
            f"/api/v1/tasks/{created['id']}", json={"status": "in_progress"}
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()
        assert updated["status"] == "in_progress"
        assert updated["title"] == "Before"  # untouched
        assert updated["priority"] == "low"  # untouched

    def test_delete_then_404(self, client):
        created = client.post("/api/v1/tasks", json={"title": "Doomed"}).json()
        assert client.delete(f"/api/v1/tasks/{created['id']}").status_code == 204
        assert client.get(f"/api/v1/tasks/{created['id']}").status_code == 404

    def test_invalid_status_rejected(self, client):
        resp = client.post("/api/v1/tasks", json={"title": "Bad", "status": "nonsense"})
        assert resp.status_code == 422

    def test_unknown_project_is_404(self, client):
        resp = client.post(
            "/api/v1/tasks",
            json={"title": "Homeless", "project_id": str(uuid4())},
        )
        assert resp.status_code == 404


class TestScoping:
    def test_other_user_cannot_read_task(self, test_db, test_user):
        owner_client = _make_client(test_db, test_user.id)
        created = owner_client.post("/api/v1/tasks", json={"title": "Private"}).json()

        stranger_client = _make_client(test_db, uuid4())
        assert stranger_client.get(f"/api/v1/tasks/{created['id']}").status_code == 404
        assert stranger_client.get("/api/v1/tasks").json() == []
