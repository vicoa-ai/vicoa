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


class TestIdentifierRefs:
    """Every route takes "VIC-42" as readily as a UUID.

    It matters most on this router: the CLI is an agent's only task entrypoint,
    and the identifier is what both the agent and the human instructing it can
    see. Asking either for a UUID asks for something neither has.
    """

    @pytest.fixture
    def keyed(self, client):
        """A task whose project got a key allocated on its first task."""
        return client.post("/api/v1/tasks", json={"title": "Ship it"}).json()

    def test_get_by_identifier(self, client, keyed):
        assert keyed["identifier"]
        resp = client.get(f"/api/v1/tasks/{keyed['identifier']}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == keyed["id"]

    def test_patch_by_identifier(self, client, keyed):
        resp = client.patch(
            f"/api/v1/tasks/{keyed['identifier']}", json={"status": "done"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "done"
        assert resp.json()["id"] == keyed["id"]

    def test_comment_by_identifier(self, client, keyed):
        resp = client.post(
            f"/api/v1/tasks/{keyed['identifier']}/comments", json={"body": "done"}
        )
        assert resp.status_code == 201, resp.text
        assert [c["body"] for c in resp.json()["comments"]] == ["done"]

    def test_unknown_identifier_is_404_not_422(self, client):
        """The route takes whatever the user typed, so a typo has to land as
        "not found" rather than as a validation error about UUIDs."""
        assert client.get("/api/v1/tasks/NOPE-99").status_code == 404
        assert client.get("/api/v1/tasks/not-a-ref-at-all").status_code == 404

    def test_delete_by_identifier(self, client, keyed):
        assert client.delete(f"/api/v1/tasks/{keyed['identifier']}").status_code == 204
        assert client.get(f"/api/v1/tasks/{keyed['id']}").status_code == 404

    def test_another_users_identifier_does_not_resolve(self, test_db, client, keyed):
        stranger_client = _make_client(test_db, uuid4())
        assert (
            stranger_client.get(f"/api/v1/tasks/{keyed['identifier']}").status_code
            == 404
        )


class TestComments:
    """`vicoa task comment` — the agent's half of the task timeline."""

    @pytest.fixture
    def task(self, client):
        return client.post("/api/v1/tasks", json={"title": "Ship it"}).json()

    def test_post_and_read_back(self, client, task):
        resp = client.post(
            f"/api/v1/tasks/{task['id']}/comments",
            json={"body": "ran the tests, all green"},
        )
        assert resp.status_code == 201, resp.text
        assert [c["body"] for c in resp.json()["comments"]] == [
            "ran the tests, all green"
        ]

        timeline = client.get(f"/api/v1/tasks/{task['id']}/timeline")
        assert timeline.status_code == 200
        assert len(timeline.json()["comments"]) == 1

    def test_reply_threads_under_its_root(self, client, task):
        root = client.post(
            f"/api/v1/tasks/{task['id']}/comments", json={"body": "why?"}
        ).json()["comments"][0]
        replied = client.post(
            f"/api/v1/tasks/{task['id']}/comments",
            json={"body": "because", "parent_comment_id": root["id"]},
        )
        assert replied.status_code == 201, replied.text
        comments = replied.json()["comments"]
        assert [c["parent_comment_id"] for c in comments] == [None, root["id"]]

    def test_unknown_parent_is_404(self, client, task):
        resp = client.post(
            f"/api/v1/tasks/{task['id']}/comments",
            json={"body": "orphan", "parent_comment_id": str(uuid4())},
        )
        assert resp.status_code == 404

    def test_comment_is_authored_by_the_calling_sessions_agent_profile(
        self, test_db, test_user, client, task
    ):
        """The only path that ever produces `author_type='agent'`: the CLI
        passes its `VICOA_AGENT_INSTANCE_ID`, and a session started from a
        profile speaks in that profile's name."""
        from shared.database.agent_profile_models import AgentProfile
        from shared.database.models import AgentInstance, AgentType

        profile = AgentProfile(
            user_id=test_user.id, name="Reviewer", agent="claude", emoji="🤖"
        )
        test_db.add(profile)
        test_db.flush()
        instance = AgentInstance(
            user_id=test_user.id,
            agent_type_id=test_db.query(AgentType).first().id,
            agent_profile_id=profile.id,
        )
        test_db.add(instance)
        test_db.commit()

        resp = client.post(
            f"/api/v1/tasks/{task['id']}/comments",
            json={"body": "reviewed", "agent_instance_id": str(instance.id)},
        )
        assert resp.status_code == 201, resp.text
        author = resp.json()["comments"][0]["author"]
        assert author["type"] == "agent"
        assert author["name"] == "Reviewer"

    def test_a_foreign_session_does_not_lend_its_agents_name(
        self, test_db, test_user, client, task
    ):
        """Naming someone else's session must not borrow their agent's byline —
        and must not fail the write either: losing the byline beats losing the
        comment."""
        resp = client.post(
            f"/api/v1/tasks/{task['id']}/comments",
            json={"body": "hello", "agent_instance_id": str(uuid4())},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["comments"][0]["author"]["type"] == "user"

    def test_other_user_cannot_comment(self, test_db, test_user, task):
        stranger_client = _make_client(test_db, uuid4())
        resp = stranger_client.post(
            f"/api/v1/tasks/{task['id']}/comments", json={"body": "sneaking in"}
        )
        assert resp.status_code == 404
        assert (
            stranger_client.get(f"/api/v1/tasks/{task['id']}/timeline").status_code
            == 404
        )
