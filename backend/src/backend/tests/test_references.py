"""Tests for `#` composer references (`GET /api/v1/references`).

Covers the two things the picker promises — only live sessions, and an empty
query that still returns something useful — plus the expansion endpoint and
the owner scoping both share.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.db.reference_queries import slugify_token
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


def _make_instance(
    db,
    user_id,
    agent_type_id,
    *,
    name,
    status=AgentStatus.ACTIVE,
    project="~/projects/vicoa",
):
    instance = AgentInstance(
        id=uuid4(),
        agent_type_id=agent_type_id,
        user_id=user_id,
        status=status,
        started_at=datetime.now(timezone.utc),
        name=name,
        project=project,
    )
    db.add(instance)
    db.commit()
    return instance


def _make_automation(
    db, user_id, *, title, enabled=True, machine=None, directory="/tmp/repo"
):
    if machine is None:
        machine = Machine(user_id=user_id, display_name="box", hostname="h")
        db.add(machine)
        db.flush()
    automation = Automation(
        user_id=user_id,
        title=title,
        prompt="sweep the queue",
        machine_id=machine.id,
        directory=directory,
        session_config={"agent": "claude"},
        schedule_kind="recurring",
        frequency={"kind": "daily", "time": "09:00"},
        enabled=enabled,
    )
    db.add(automation)
    db.commit()
    return automation


def _kinds(body, kind):
    return [i for i in body["items"] if i["kind"] == kind]


class TestSlugifyToken:
    def test_multi_word_label_becomes_a_space_free_slug(self):
        assert slugify_token("Fix the diff editor", "x") == "fix-the-diff-editor"

    def test_punctuation_collapses_and_edges_are_trimmed(self):
        assert slugify_token("  Nightly: deps!! ", "x") == "nightly-deps"

    def test_unsluggable_label_falls_back(self):
        assert slugify_token("中文 ///", "session-abcd1234") == "session-abcd1234"

    def test_long_label_is_capped_without_a_trailing_dash(self):
        token = slugify_token("a" * 20 + " " + "b" * 40, "x")
        assert len(token) <= 32
        assert not token.endswith("-")


class TestReferenceCandidates:
    def test_empty_query_lists_live_sessions_open_tasks_and_enabled_automations(
        self, authenticated_client, test_db, test_user, test_agent_type
    ):
        live = _make_instance(
            test_db, test_user.id, test_agent_type.id, name="Rotate the widget"
        )
        _make_instance(
            test_db,
            test_user.id,
            test_agent_type.id,
            name="Old finished run",
            status=AgentStatus.COMPLETED,
        )
        test_db.add(Task(user_id=test_user.id, project_id=None, title="Open work"))
        test_db.add(
            Task(
                user_id=test_user.id,
                project_id=None,
                title="Shipped already",
                status="done",
            )
        )
        test_db.commit()
        _make_automation(test_db, test_user.id, title="Nightly sweep")
        _make_automation(test_db, test_user.id, title="Paused sweep", enabled=False)

        body = authenticated_client.get("/api/v1/references").json()

        assert [s["id"] for s in _kinds(body, "session")] == [str(live.id)]
        assert [t["label"] for t in _kinds(body, "task")] == ["Open work"]
        assert [a["label"] for a in _kinds(body, "automation")] == ["Nightly sweep"]

    def test_closed_sessions_stay_out_even_when_they_match(
        self, authenticated_client, test_db, test_user, test_agent_type
    ):
        _make_instance(
            test_db,
            test_user.id,
            test_agent_type.id,
            name="widget run",
            status=AgentStatus.KILLED,
        )
        body = authenticated_client.get(
            "/api/v1/references", params={"q": "widget"}
        ).json()
        assert _kinds(body, "session") == []

    def test_typed_query_widens_tasks_to_closed_ones(
        self, authenticated_client, test_db, test_user
    ):
        test_db.add(
            Task(
                user_id=test_user.id,
                project_id=None,
                title="Widget retrospective",
                status="done",
            )
        )
        test_db.commit()
        body = authenticated_client.get(
            "/api/v1/references", params={"q": "widget"}
        ).json()
        assert [t["label"] for t in _kinds(body, "task")] == ["Widget retrospective"]

    def test_identified_task_uses_its_identifier_as_the_token(
        self, authenticated_client
    ):
        project = authenticated_client.post(
            "/api/v1/projects", json={"name": "Vicoa"}
        ).json()
        created = authenticated_client.post(
            "/api/v1/tasks",
            json={"title": "Fix the diff editor", "project_id": project["id"]},
        ).json()
        # The project's key is allocated with its first task, so read the
        # identifier off the task rather than the (still keyless) project.
        assert created["identifier"].endswith("-1")

        body = authenticated_client.get(
            "/api/v1/references", params={"q": "diff"}
        ).json()
        task = _kinds(body, "task")[0]
        assert task["token"] == created["identifier"]
        assert task["label"] == "Fix the diff editor"

    def test_row_meta_is_the_folder_for_sessions_and_automations(
        self, authenticated_client, test_db, test_user, test_agent_type
    ):
        """The single row's trailing slot. A slug there would only echo the
        title next to it; the folder is what tells two runs apart."""
        _make_instance(
            test_db,
            test_user.id,
            test_agent_type.id,
            name="widget run",
            project="~/projects/vicoa",
        )
        _make_automation(test_db, test_user.id, title="widget sweep")

        body = authenticated_client.get(
            "/api/v1/references", params={"q": "widget"}
        ).json()
        assert _kinds(body, "session")[0]["meta"] == "~/projects/vicoa"
        assert _kinds(body, "session")[0]["identifier"] is None
        assert _kinds(body, "automation")[0]["meta"] == "/tmp/repo"

    def test_filed_session_shows_its_project_name_and_icon_payload(
        self, authenticated_client, test_db, test_user, test_agent_type
    ):
        """A path is the fallback, not the goal: once a session is filed under
        a project, the row names the project (and can draw its icon)."""
        project = authenticated_client.post(
            "/api/v1/projects", json={"name": "Vicoa"}
        ).json()
        instance = _make_instance(
            test_db,
            test_user.id,
            test_agent_type.id,
            name="widget run",
            project="~/projects/vicoa",
        )
        instance.project_id = UUID(project["id"])
        test_db.commit()

        row = _kinds(
            authenticated_client.get(
                "/api/v1/references", params={"q": "widget"}
            ).json(),
            "session",
        )[0]
        assert row["meta"] == "Vicoa"
        assert row["project"]["id"] == project["id"]
        assert row["project"]["name"] == "Vicoa"

    def test_automation_resolves_its_project_from_the_folder(
        self, authenticated_client, test_db, test_user
    ):
        """Automations carry no project_id, so the folder is matched against
        the machine's linked directories — the matcher's tier 2, by hand."""
        machine = Machine(user_id=test_user.id, display_name="box", hostname="h")
        test_db.add(machine)
        test_db.commit()
        project = authenticated_client.post(
            "/api/v1/projects", json={"name": "Vicoa"}
        ).json()
        assert (
            authenticated_client.put(
                f"/api/v1/projects/{project['id']}/directories",
                json={"machine_id": str(machine.id), "local_path": "/src/vicoa"},
            ).status_code
            == 200
        )
        _make_automation(
            test_db,
            test_user.id,
            title="widget sweep",
            machine=machine,
            directory="/src/vicoa/backend",
        )

        row = _kinds(
            authenticated_client.get(
                "/api/v1/references", params={"q": "widget"}
            ).json(),
            "automation",
        )[0]
        assert row["meta"] == "Vicoa"
        assert row["project"]["id"] == project["id"]

    def test_automation_on_an_unlinked_folder_keeps_the_path(
        self, authenticated_client, test_db, test_user
    ):
        _make_automation(test_db, test_user.id, title="widget sweep")
        row = _kinds(
            authenticated_client.get(
                "/api/v1/references", params={"q": "widget"}
            ).json(),
            "automation",
        )[0]
        assert row["meta"] == "/tmp/repo"
        assert row["project"] is None

    def test_task_row_carries_its_project_and_key(self, authenticated_client):
        project = authenticated_client.post(
            "/api/v1/projects", json={"name": "Vicoa"}
        ).json()
        created = authenticated_client.post(
            "/api/v1/tasks",
            json={"title": "Fix the widget", "project_id": project["id"]},
        ).json()

        body = authenticated_client.get(
            "/api/v1/references", params={"q": "widget"}
        ).json()
        task = _kinds(body, "task")[0]
        assert task["meta"] == "Vicoa"
        assert task["identifier"] == created["identifier"]

    def test_unfiled_task_has_no_key_to_show(self, authenticated_client):
        authenticated_client.post("/api/v1/tasks", json={"title": "Fix the widget"})
        body = authenticated_client.get(
            "/api/v1/references", params={"q": "widget"}
        ).json()
        task = _kinds(body, "task")[0]
        assert task["meta"] is None
        # The slug still fills `token` (what gets typed), just not the row.
        assert task["identifier"] is None
        assert task["token"] == "fix-the-widget"

    def test_unfiled_task_falls_back_to_a_slug_token(self, authenticated_client):
        authenticated_client.post("/api/v1/tasks", json={"title": "Fix the drift"})
        body = authenticated_client.get(
            "/api/v1/references", params={"q": "drift"}
        ).json()
        assert _kinds(body, "task")[0]["token"] == "fix-the-drift"

    def test_excludes_the_referencing_session_itself(
        self, authenticated_client, test_db, test_user, test_agent_type
    ):
        me = _make_instance(
            test_db, test_user.id, test_agent_type.id, name="widget here"
        )
        other = _make_instance(
            test_db, test_user.id, test_agent_type.id, name="widget there"
        )
        body = authenticated_client.get(
            "/api/v1/references",
            params={"q": "widget", "exclude_session_id": str(me.id)},
        ).json()
        assert [s["id"] for s in _kinds(body, "session")] == [str(other.id)]

    def test_scoped_to_the_caller(self, authenticated_client, test_db, test_agent_type):
        other = _make_user(test_db, "other@example.com")
        _make_instance(test_db, other.id, test_agent_type.id, name="secret session")
        test_db.add(Task(user_id=other.id, project_id=None, title="secret task"))
        test_db.commit()
        _make_automation(test_db, other.id, title="secret automation")

        body = authenticated_client.get("/api/v1/references").json()
        assert body["items"] == []


class TestReferenceExpansion:
    def test_task_block_carries_the_facts_and_the_description(
        self, authenticated_client
    ):
        project = authenticated_client.post(
            "/api/v1/projects", json={"name": "Vicoa"}
        ).json()
        task = authenticated_client.post(
            "/api/v1/tasks",
            json={
                "title": "Fix the diff editor",
                "project_id": project["id"],
                "description": "scanLimit collapses the file",
            },
        ).json()

        body = authenticated_client.get(f"/api/v1/references/task/{task['id']}").json()
        assert body["kind"] == "task"
        assert body["token"] == task["identifier"]
        assert f"Task {task['identifier']}: Fix the diff editor" in body["context"]
        assert "scanLimit collapses the file" in body["context"]
        assert f"vicoa task get {task['identifier']}" in body["context"]

    def test_session_block_is_a_pointer_not_a_transcript(
        self, authenticated_client, test_db, test_user, test_agent_type
    ):
        """Facts that identify the run, plus the way in. Deliberately NOT the
        newest message: that is whatever row landed last, so on a running
        session it is usually half a tool call, and it reads like a summary
        without being one."""
        instance = _make_instance(
            test_db, test_user.id, test_agent_type.id, name="Rotate the widget"
        )
        test_db.add(
            Message(
                agent_instance_id=instance.id,
                sender_type=SenderType.AGENT,
                content="rotated the widget by ninety degrees",
                requires_user_input=False,
            )
        )
        test_db.commit()

        body = authenticated_client.get(
            f"/api/v1/references/session/{instance.id}"
        ).json()
        assert body["token"] == "rotate-the-widget"
        assert 'Session "Rotate the widget"' in body["context"]
        assert "~/projects/vicoa" in body["context"]
        assert f"vicoa session get {instance.id}`" in body["context"]
        assert "rotated the widget by ninety degrees" not in body["context"]

    def test_automation_block_carries_the_prompt_and_schedule(
        self, authenticated_client, test_db, test_user
    ):
        automation = _make_automation(test_db, test_user.id, title="Nightly sweep")
        body = authenticated_client.get(
            f"/api/v1/references/automation/{automation.id}"
        ).json()
        assert "daily 09:00" in body["context"]
        assert "sweep the queue" in body["context"]

    def test_another_users_row_is_invisible(
        self, authenticated_client, test_db, test_agent_type
    ):
        other = _make_user(test_db, "other@example.com")
        instance = _make_instance(
            test_db, other.id, test_agent_type.id, name="secret session"
        )
        resp = authenticated_client.get(f"/api/v1/references/session/{instance.id}")
        assert resp.status_code == 404

    def test_unknown_kind_is_rejected(self, authenticated_client):
        resp = authenticated_client.get(f"/api/v1/references/project/{uuid4()}")
        assert resp.status_code == 422


class TestReferencedTaskLinksTheSession:
    """The session ↔ task half of `#`, on the column that already exists.

    No new table and no new endpoint: referencing a task from the composer is
    the same PATCH the tasks plan calls the §8b late link, so the task's
    Sessions list picks the session up.
    """

    def test_patching_task_id_files_the_session_under_the_task(
        self, authenticated_client, test_db, test_user, test_agent_type
    ):
        instance = _make_instance(
            test_db, test_user.id, test_agent_type.id, name="worker"
        )
        task = authenticated_client.post(
            "/api/v1/tasks", json={"title": "Fix the diff editor"}
        ).json()

        resp = authenticated_client.patch(
            f"/api/v1/agent-instances/{instance.id}", json={"task_id": task["id"]}
        )
        assert resp.status_code == 200
        assert resp.json()["task_id"] == task["id"]

        sessions = authenticated_client.get(
            f"/api/v1/tasks/{task['id']}/sessions"
        ).json()
        assert [s["id"] for s in sessions] == [str(instance.id)]

    def test_detail_exposes_the_link_so_the_composer_can_see_it(
        self, authenticated_client, test_db, test_user, test_agent_type
    ):
        instance = _make_instance(
            test_db, test_user.id, test_agent_type.id, name="worker"
        )
        detail = authenticated_client.get(
            f"/api/v1/agent-instances/{instance.id}"
        ).json()
        assert detail["task_id"] is None

        task = authenticated_client.post(
            "/api/v1/tasks", json={"title": "Fix the diff editor"}
        ).json()
        authenticated_client.patch(
            f"/api/v1/agent-instances/{instance.id}", json={"task_id": task["id"]}
        )
        detail = authenticated_client.get(
            f"/api/v1/agent-instances/{instance.id}"
        ).json()
        assert detail["task_id"] == task["id"]
