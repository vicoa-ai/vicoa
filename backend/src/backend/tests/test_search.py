"""Tests for workspace search (`GET /api/v1/search`, the cmd+K palette)."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

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

    def _garden_tasks(self, client, titles=("Seed calendar", "Compost tracker")):
        project = client.post(
            "/api/v1/projects", json={"name": "Garden Planner"}
        ).json()
        return [
            client.post(
                "/api/v1/tasks", json={"title": title, "project_id": project["id"]}
            ).json()
            for title in titles
        ]

    def test_finds_a_task_by_its_identifier(self, authenticated_client):
        """ "GAR-2" is how the task is named everywhere else, and it is
        nowhere in its text, so text matching alone came back empty."""
        self._garden_tasks(authenticated_client)

        for q in ("GAR-2", "gar-2"):
            tasks = authenticated_client.get("/api/v1/search", params={"q": q}).json()[
                "tasks"
            ]
            assert [t["identifier"] for t in tasks] == ["GAR-2"]
            assert tasks[0]["title"] == "Compost tracker"
            assert tasks[0]["match_source"] == "identifier"
            assert tasks[0]["snippet"] is None

    def test_a_partial_identifier_narrows_to_the_project(self, authenticated_client):
        self._garden_tasks(authenticated_client)

        tasks = authenticated_client.get("/api/v1/search", params={"q": "gar-"}).json()[
            "tasks"
        ]
        assert sorted(t["identifier"] for t in tasks) == ["GAR-1", "GAR-2"]

    def test_a_bare_key_is_text_not_an_identifier(self, authenticated_client):
        """Without the dash it is a text search: "gar" must not pull in every
        task of the GAR project, only the ones whose text says it."""
        self._garden_tasks(authenticated_client, ("Seed calendar", "Garlic bed"))

        tasks = authenticated_client.get("/api/v1/search", params={"q": "gar"}).json()[
            "tasks"
        ]
        assert [t["title"] for t in tasks] == ["Garlic bed"]
        assert tasks[0]["match_source"] == "title"

    def test_an_exact_identifier_leads_even_when_done(
        self, authenticated_client, test_db
    ):
        first, second = self._garden_tasks(authenticated_client)
        authenticated_client.patch(
            f"/api/v1/tasks/{first['id']}", json={"status": "done"}
        )
        # GAR-10 also starts with "GAR-1", and it's open.
        test_db.get(Task, UUID(second["id"])).number = 10
        test_db.commit()

        tasks = authenticated_client.get(
            "/api/v1/search", params={"q": "GAR-1"}
        ).json()["tasks"]
        assert [t["identifier"] for t in tasks] == ["GAR-1", "GAR-10"]

    def test_text_hits_carry_the_identifier(self, authenticated_client):
        self._garden_tasks(authenticated_client)

        tasks = authenticated_client.get(
            "/api/v1/search", params={"q": "compost"}
        ).json()["tasks"]
        assert [t["identifier"] for t in tasks] == ["GAR-2"]
        assert tasks[0]["match_source"] == "title"

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
