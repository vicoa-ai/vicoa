"""Tests for workspace search (`GET /api/v1/search`, the cmd+K palette)."""

from datetime import datetime, timezone
from uuid import uuid4

from shared.database import AgentInstance, Automation, Machine, Message, Task, User
from shared.database.enums import AgentStatus, SenderType


def _make_user(db, email):
    user = User(
        id=uuid4(),
        email=email,
        display_name="Other",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    return user


class TestSearchAPI:
    def test_unfiled_task_matches(self, authenticated_client):
        """A task under No project (NULL project_id) is a valid hit. Requiring
        the id on the result model used to 500 every search that matched one."""
        resp = authenticated_client.post(
            "/api/v1/tasks", json={"title": "Fix the flaky search"}
        )
        assert resp.status_code == 201

        resp = authenticated_client.get("/api/v1/search", params={"q": "flaky"})
        assert resp.status_code == 200
        body = resp.json()
        assert [t["title"] for t in body["tasks"]] == ["Fix the flaky search"]
        assert body["tasks"][0]["project_id"] is None
        assert body["tasks"][0]["match_source"] == "title"

    def test_filed_task_carries_project_id(self, authenticated_client):
        project = authenticated_client.post(
            "/api/v1/projects", json={"name": "Alpha"}
        ).json()
        authenticated_client.post(
            "/api/v1/tasks",
            json={"title": "Wire the palette", "project_id": project["id"]},
        )

        body = authenticated_client.get(
            "/api/v1/search", params={"q": "palette"}
        ).json()
        assert [t["project_id"] for t in body["tasks"]] == [project["id"]]

    def test_groups_sessions_tasks_automations(
        self, authenticated_client, test_db, test_user, test_agent_type
    ):
        instance = AgentInstance(
            id=uuid4(),
            agent_type_id=test_agent_type.id,
            user_id=test_user.id,
            status=AgentStatus.ACTIVE,
            started_at=datetime.now(timezone.utc),
            name="Rotate the widget",
        )
        test_db.add(instance)
        test_db.add(
            Message(
                agent_instance_id=instance.id,
                sender_type=SenderType.AGENT,
                content="rotated the widget by ninety degrees",
                requires_user_input=False,
            )
        )
        machine = Machine(user_id=test_user.id, display_name="box", hostname="h")
        test_db.add(machine)
        test_db.flush()
        test_db.add(
            Automation(
                user_id=test_user.id,
                title="Nightly widget check",
                prompt="check it",
                machine_id=machine.id,
                directory="/tmp",
                session_config={"agent": "claude"},
                schedule_kind="once",
            )
        )
        test_db.add(Task(user_id=test_user.id, project_id=None, title="Widget bug"))
        test_db.commit()

        body = authenticated_client.get("/api/v1/search", params={"q": "widget"}).json()
        assert body["query"] == "widget"
        assert [s["name"] for s in body["sessions"]] == ["Rotate the widget"]
        assert body["sessions"][0]["match_source"] == "name"
        assert [t["title"] for t in body["tasks"]] == ["Widget bug"]
        assert [a["title"] for a in body["automations"]] == ["Nightly widget check"]

    def test_message_tier_fills_remaining_slots(
        self, authenticated_client, test_db, test_user, test_agent_type
    ):
        instance = AgentInstance(
            id=uuid4(),
            agent_type_id=test_agent_type.id,
            user_id=test_user.id,
            status=AgentStatus.ACTIVE,
            started_at=datetime.now(timezone.utc),
            name="unrelated name",
        )
        test_db.add(instance)
        test_db.add(
            Message(
                agent_instance_id=instance.id,
                sender_type=SenderType.AGENT,
                content="the needle is buried in this haystack of text",
                requires_user_input=False,
            )
        )
        test_db.commit()

        body = authenticated_client.get("/api/v1/search", params={"q": "needle"}).json()
        assert [s["id"] for s in body["sessions"]] == [str(instance.id)]
        hit = body["sessions"][0]
        assert hit["match_source"] == "message"
        assert "needle" in hit["snippet"]

    def test_scoped_to_current_user(
        self, authenticated_client, test_db, test_agent_type
    ):
        other = _make_user(test_db, "other@example.com")
        test_db.add(Task(user_id=other.id, project_id=None, title="secret task"))
        test_db.add(
            AgentInstance(
                id=uuid4(),
                agent_type_id=test_agent_type.id,
                user_id=other.id,
                status=AgentStatus.ACTIVE,
                started_at=datetime.now(timezone.utc),
                name="secret session",
            )
        )
        test_db.commit()

        body = authenticated_client.get("/api/v1/search", params={"q": "secret"}).json()
        assert body == {
            "query": "secret",
            "sessions": [],
            "tasks": [],
            "automations": [],
        }

    def test_blank_query_rejected(self, authenticated_client):
        assert (
            authenticated_client.get("/api/v1/search", params={"q": ""}).status_code
            == 422
        )
        resp = authenticated_client.get("/api/v1/search", params={"q": "   "})
        assert resp.status_code == 200
        assert resp.json()["tasks"] == []

    def test_requires_auth(self, client):
        assert client.get("/api/v1/search", params={"q": "x"}).status_code == 401
