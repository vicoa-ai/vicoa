"""Tests for projects & tasks (plans/todos/tasks-and-projects-feature.md).

Covers the Inbox helper, the projects/tasks REST API (user scoping, Inbox
default, status/priority validation), and the instance-status → task-status
linkage.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from shared.database import (
    Machine,
    Project,
    ProjectDirectory,
    Task,
    User,
    get_or_create_inbox,
)
from shared.database.enums import AgentStatus


def _make_machine(db, user_id, display_name="Laptop"):
    machine = Machine(user_id=user_id, display_name=display_name, hostname="host.local")
    db.add(machine)
    db.commit()
    return machine


@pytest.fixture
def other_user(test_db):
    """A second user for cross-user scoping tests."""
    user = User(
        id=uuid4(),
        email="other@example.com",
        display_name="Other User",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    test_db.add(user)
    test_db.commit()
    return user


class TestInboxHelper:
    def test_creates_inbox_once(self, test_db, test_user):
        inbox = get_or_create_inbox(test_db, test_user.id)
        assert inbox.name == "Inbox"
        assert inbox.is_inbox is True
        assert inbox.user_id == test_user.id

        again = get_or_create_inbox(test_db, test_user.id)
        assert again.id == inbox.id


class TestProjectsAPI:
    def test_list_projects_lazily_includes_inbox(self, authenticated_client):
        resp = authenticated_client.get("/api/v1/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["is_inbox"] is True
        assert data[0]["name"] == "Inbox"

    def test_create_project_and_list_orders_inbox_first(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/v1/projects", json={"name": "Alpha", "color": "#ff0000"}
        )
        assert resp.status_code == 201
        created = resp.json()
        assert created["name"] == "Alpha"
        assert created["color"] == "#ff0000"
        assert created["is_inbox"] is False

        listed = authenticated_client.get("/api/v1/projects").json()
        assert [p["name"] for p in listed] == ["Inbox", "Alpha"]

    def test_update_and_archive_project(self, authenticated_client):
        project = authenticated_client.post(
            "/api/v1/projects", json={"name": "Alpha"}
        ).json()

        resp = authenticated_client.patch(
            f"/api/v1/projects/{project['id']}", json={"name": "Beta"}
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Beta"

        resp = authenticated_client.patch(
            f"/api/v1/projects/{project['id']}", json={"is_archived": True}
        )
        assert resp.status_code == 200
        assert resp.json()["is_archived"] is True
        assert resp.json()["archived_at"] is not None

        names = [p["name"] for p in authenticated_client.get("/api/v1/projects").json()]
        assert "Beta" not in names
        with_archived = [
            p["name"]
            for p in authenticated_client.get(
                "/api/v1/projects?include_archived=true"
            ).json()
        ]
        assert "Beta" in with_archived

    def test_inbox_cannot_be_archived_or_deleted(self, authenticated_client):
        inbox = authenticated_client.get("/api/v1/projects").json()[0]
        assert inbox["is_inbox"] is True

        resp = authenticated_client.patch(
            f"/api/v1/projects/{inbox['id']}", json={"is_archived": True}
        )
        assert resp.status_code == 400

        resp = authenticated_client.delete(f"/api/v1/projects/{inbox['id']}")
        assert resp.status_code == 400

    def test_projects_are_user_scoped(self, authenticated_client, test_db, other_user):
        foreign = Project(user_id=other_user.id, name="Theirs")
        test_db.add(foreign)
        test_db.commit()

        names = [p["name"] for p in authenticated_client.get("/api/v1/projects").json()]
        assert "Theirs" not in names

        resp = authenticated_client.patch(
            f"/api/v1/projects/{foreign.id}", json={"name": "Hijacked"}
        )
        assert resp.status_code == 404
        resp = authenticated_client.delete(f"/api/v1/projects/{foreign.id}")
        assert resp.status_code == 404


class TestProjectDirectoriesAPI:
    def test_link_relink_and_unlink(self, authenticated_client, test_db, test_user):
        machine = _make_machine(test_db, test_user.id)
        project = authenticated_client.post(
            "/api/v1/projects", json={"name": "Alpha"}
        ).json()

        resp = authenticated_client.put(
            f"/api/v1/projects/{project['id']}/directories",
            json={"machine_id": str(machine.id), "local_path": "/home/nick/alpha"},
        )
        assert resp.status_code == 200
        dirs = resp.json()["directories"]
        assert len(dirs) == 1
        assert dirs[0]["local_path"] == "/home/nick/alpha"
        assert dirs[0]["machine_id"] == str(machine.id)
        assert dirs[0]["machine_name"] == "Laptop"

        # Re-linking the same machine overwrites rather than adding a row.
        resp = authenticated_client.put(
            f"/api/v1/projects/{project['id']}/directories",
            json={"machine_id": str(machine.id), "local_path": "/home/nick/alpha2"},
        )
        assert resp.status_code == 200
        dirs = resp.json()["directories"]
        assert len(dirs) == 1
        assert dirs[0]["local_path"] == "/home/nick/alpha2"

        resp = authenticated_client.delete(
            f"/api/v1/projects/{project['id']}/directories/{machine.id}"
        )
        assert resp.status_code == 200
        assert resp.json()["directories"] == []

        # Unlinking twice is a no-op, not an error.
        resp = authenticated_client.delete(
            f"/api/v1/projects/{project['id']}/directories/{machine.id}"
        )
        assert resp.status_code == 200

    def test_one_directory_per_machine_two_machines_ok(
        self, authenticated_client, test_db, test_user
    ):
        laptop = _make_machine(test_db, test_user.id, "Laptop")
        desktop = _make_machine(test_db, test_user.id, "Desktop")
        project = authenticated_client.post(
            "/api/v1/projects", json={"name": "Alpha"}
        ).json()

        for machine, path in ((laptop, "/laptop/alpha"), (desktop, "/desktop/alpha")):
            resp = authenticated_client.put(
                f"/api/v1/projects/{project['id']}/directories",
                json={"machine_id": str(machine.id), "local_path": path},
            )
            assert resp.status_code == 200

        listed = authenticated_client.get("/api/v1/projects").json()
        alpha = next(p for p in listed if p["name"] == "Alpha")
        assert {d["local_path"] for d in alpha["directories"]} == {
            "/laptop/alpha",
            "/desktop/alpha",
        }

    def test_inbox_cannot_be_linked(self, authenticated_client, test_db, test_user):
        machine = _make_machine(test_db, test_user.id)
        inbox = authenticated_client.get("/api/v1/projects").json()[0]
        assert inbox["is_inbox"] is True

        resp = authenticated_client.put(
            f"/api/v1/projects/{inbox['id']}/directories",
            json={"machine_id": str(machine.id), "local_path": "/home/nick"},
        )
        assert resp.status_code == 400

    def test_foreign_machine_and_project_rejected(
        self, authenticated_client, test_db, test_user, other_user
    ):
        project = authenticated_client.post(
            "/api/v1/projects", json={"name": "Alpha"}
        ).json()
        foreign_machine = _make_machine(test_db, other_user.id, "Theirs")

        resp = authenticated_client.put(
            f"/api/v1/projects/{project['id']}/directories",
            json={"machine_id": str(foreign_machine.id), "local_path": "/x"},
        )
        assert resp.status_code == 404

        foreign_project = Project(user_id=other_user.id, name="Theirs")
        test_db.add(foreign_project)
        test_db.commit()
        own_machine = _make_machine(test_db, test_user.id, "Mine")
        resp = authenticated_client.put(
            f"/api/v1/projects/{foreign_project.id}/directories",
            json={"machine_id": str(own_machine.id), "local_path": "/x"},
        )
        assert resp.status_code == 404

    def test_deleting_project_removes_its_directories(
        self, authenticated_client, test_db, test_user
    ):
        machine = _make_machine(test_db, test_user.id)
        project = authenticated_client.post(
            "/api/v1/projects", json={"name": "Alpha"}
        ).json()
        authenticated_client.put(
            f"/api/v1/projects/{project['id']}/directories",
            json={"machine_id": str(machine.id), "local_path": "/home/nick/alpha"},
        )

        assert (
            authenticated_client.delete(f"/api/v1/projects/{project['id']}").status_code
            == 204
        )
        remaining = (
            test_db.query(ProjectDirectory)
            .filter(ProjectDirectory.project_id == project["id"])
            .count()
        )
        assert remaining == 0


class TestTasksAPI:
    def test_create_task_defaults_to_inbox(self, authenticated_client):
        resp = authenticated_client.post("/api/v1/tasks", json={"title": "Fix the bug"})
        assert resp.status_code == 201
        task = resp.json()
        assert task["title"] == "Fix the bug"
        assert task["status"] == "backlog"
        assert task["priority"] == "none"

        inbox = authenticated_client.get("/api/v1/projects").json()[0]
        assert inbox["is_inbox"] is True
        assert task["project_id"] == inbox["id"]

    def test_create_task_rejects_unknown_status_and_priority(
        self, authenticated_client
    ):
        resp = authenticated_client.post(
            "/api/v1/tasks", json={"title": "x", "status": "doing"}
        )
        assert resp.status_code == 422
        resp = authenticated_client.post(
            "/api/v1/tasks", json={"title": "x", "priority": "asap"}
        )
        assert resp.status_code == 422

    def test_list_tasks_filters_and_orders_by_position(self, authenticated_client):
        project = authenticated_client.post(
            "/api/v1/projects", json={"name": "Alpha"}
        ).json()

        def make(title, position, **extra):
            body = {
                "title": title,
                "project_id": project["id"],
                "position": position,
                **extra,
            }
            return authenticated_client.post("/api/v1/tasks", json=body).json()

        make("second", 2.0)
        make("first", 1.0)
        make("done-task", 0.5, status="done")
        authenticated_client.post("/api/v1/tasks", json={"title": "inbox-task"})

        all_tasks = authenticated_client.get("/api/v1/tasks").json()
        assert {t["title"] for t in all_tasks} == {
            "second",
            "first",
            "done-task",
            "inbox-task",
        }

        in_project = authenticated_client.get(
            f"/api/v1/tasks?project_id={project['id']}"
        ).json()
        assert [t["title"] for t in in_project] == ["done-task", "first", "second"]

        done_only = authenticated_client.get(
            f"/api/v1/tasks?project_id={project['id']}&status=done"
        ).json()
        assert [t["title"] for t in done_only] == ["done-task"]

    def test_update_task_fields_and_clear_due_date(self, authenticated_client):
        task = authenticated_client.post(
            "/api/v1/tasks",
            json={"title": "t", "due_date": "2026-08-01T00:00:00Z"},
        ).json()
        assert task["due_date"] is not None

        resp = authenticated_client.patch(
            f"/api/v1/tasks/{task['id']}",
            json={
                "title": "renamed",
                "status": "in_progress",
                "priority": "high",
                "position": 3.5,
            },
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["title"] == "renamed"
        assert updated["status"] == "in_progress"
        assert updated["priority"] == "high"
        assert updated["position"] == 3.5

        # Explicit null clears the date; omitting the field leaves it alone.
        resp = authenticated_client.patch(
            f"/api/v1/tasks/{task['id']}", json={"due_date": None}
        )
        assert resp.json()["due_date"] is None

    def test_move_task_to_project_validates_ownership(
        self, authenticated_client, test_db, other_user
    ):
        task = authenticated_client.post("/api/v1/tasks", json={"title": "t"}).json()
        mine = authenticated_client.post(
            "/api/v1/projects", json={"name": "Mine"}
        ).json()

        resp = authenticated_client.patch(
            f"/api/v1/tasks/{task['id']}", json={"project_id": mine["id"]}
        )
        assert resp.status_code == 200
        assert resp.json()["project_id"] == mine["id"]

        foreign = Project(user_id=other_user.id, name="Theirs")
        test_db.add(foreign)
        test_db.commit()
        resp = authenticated_client.patch(
            f"/api/v1/tasks/{task['id']}", json={"project_id": str(foreign.id)}
        )
        assert resp.status_code == 404

    def test_get_single_task(self, authenticated_client, test_db, other_user):
        task = authenticated_client.post("/api/v1/tasks", json={"title": "t"}).json()
        resp = authenticated_client.get(f"/api/v1/tasks/{task['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == task["id"]

        foreign_inbox = get_or_create_inbox(test_db, other_user.id)
        foreign_task = Task(
            user_id=other_user.id, project_id=foreign_inbox.id, title="theirs"
        )
        test_db.add(foreign_task)
        test_db.commit()
        assert (
            authenticated_client.get(f"/api/v1/tasks/{foreign_task.id}").status_code
            == 404
        )

    def test_delete_task(self, authenticated_client):
        task = authenticated_client.post("/api/v1/tasks", json={"title": "t"}).json()
        resp = authenticated_client.delete(f"/api/v1/tasks/{task['id']}")
        assert resp.status_code == 204
        assert authenticated_client.get("/api/v1/tasks").json() == []

    def test_tasks_are_user_scoped(self, authenticated_client, test_db, other_user):
        foreign_project = get_or_create_inbox(test_db, other_user.id)
        foreign_task = Task(
            user_id=other_user.id, project_id=foreign_project.id, title="theirs"
        )
        test_db.add(foreign_task)
        test_db.commit()

        assert authenticated_client.get("/api/v1/tasks").json() == []
        resp = authenticated_client.patch(
            f"/api/v1/tasks/{foreign_task.id}", json={"title": "hijack"}
        )
        assert resp.status_code == 404
        resp = authenticated_client.delete(f"/api/v1/tasks/{foreign_task.id}")
        assert resp.status_code == 404


class TestLabelsAPI:
    def test_label_crud_and_scoping(self, authenticated_client, test_db, other_user):
        resp = authenticated_client.post(
            "/api/v1/task-labels", json={"name": "bug", "color": "#ef4444"}
        )
        assert resp.status_code == 201
        label = resp.json()
        assert label["name"] == "bug"
        assert label["color"] == "#ef4444"

        resp = authenticated_client.patch(
            f"/api/v1/task-labels/{label['id']}", json={"name": "defect"}
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "defect"

        from shared.database import TaskLabel

        foreign = TaskLabel(user_id=other_user.id, name="theirs", color="#3b82f6")
        test_db.add(foreign)
        test_db.commit()

        names = [
            label["name"]
            for label in authenticated_client.get("/api/v1/task-labels").json()
        ]
        assert names == ["defect"]
        assert (
            authenticated_client.delete(f"/api/v1/task-labels/{foreign.id}").status_code
            == 404
        )
        assert (
            authenticated_client.delete(
                f"/api/v1/task-labels/{label['id']}"
            ).status_code
            == 204
        )
        assert authenticated_client.get("/api/v1/task-labels").json() == []

    def test_label_color_is_pinned_to_hex(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/v1/task-labels", json={"name": "x", "color": "url(javascript:1)"}
        )
        assert resp.status_code == 422

    def test_task_labels_attach_replace_and_detach_on_delete(
        self, authenticated_client
    ):
        bug = authenticated_client.post(
            "/api/v1/task-labels", json={"name": "bug", "color": "#ef4444"}
        ).json()
        ui = authenticated_client.post(
            "/api/v1/task-labels", json={"name": "ui", "color": "#3b82f6"}
        ).json()

        task = authenticated_client.post(
            "/api/v1/tasks", json={"title": "t", "label_ids": [bug["id"]]}
        ).json()
        assert [label["name"] for label in task["labels"]] == ["bug"]

        # PATCH replaces the whole set.
        task = authenticated_client.patch(
            f"/api/v1/tasks/{task['id']}", json={"label_ids": [ui["id"]]}
        ).json()
        assert [label["name"] for label in task["labels"]] == ["ui"]

        # Deleting a label detaches it from tasks.
        authenticated_client.delete(f"/api/v1/task-labels/{ui['id']}")
        fetched = authenticated_client.get(f"/api/v1/tasks/{task['id']}").json()
        assert fetched["labels"] == []

    def test_task_rejects_foreign_labels(
        self, authenticated_client, test_db, other_user
    ):
        from shared.database import TaskLabel

        foreign = TaskLabel(user_id=other_user.id, name="theirs", color="#3b82f6")
        test_db.add(foreign)
        test_db.commit()

        resp = authenticated_client.post(
            "/api/v1/tasks", json={"title": "t", "label_ids": [str(foreign.id)]}
        )
        assert resp.status_code == 404


class TestSubtasks:
    def test_create_and_clear_subtask(self, authenticated_client):
        parent = authenticated_client.post("/api/v1/tasks", json={"title": "p"}).json()
        child = authenticated_client.post(
            "/api/v1/tasks", json={"title": "c", "parent_task_id": parent["id"]}
        ).json()
        assert child["parent_task_id"] == parent["id"]

        cleared = authenticated_client.patch(
            f"/api/v1/tasks/{child['id']}", json={"parent_task_id": None}
        ).json()
        assert cleared["parent_task_id"] is None

    def test_parent_cycle_and_self_rejected(self, authenticated_client):
        a = authenticated_client.post("/api/v1/tasks", json={"title": "a"}).json()
        b = authenticated_client.post(
            "/api/v1/tasks", json={"title": "b", "parent_task_id": a["id"]}
        ).json()

        resp = authenticated_client.patch(
            f"/api/v1/tasks/{a['id']}", json={"parent_task_id": b["id"]}
        )
        assert resp.status_code == 400
        resp = authenticated_client.patch(
            f"/api/v1/tasks/{a['id']}", json={"parent_task_id": a["id"]}
        )
        assert resp.status_code == 400

    def test_parent_must_be_own_task(self, authenticated_client, test_db, other_user):
        foreign_inbox = get_or_create_inbox(test_db, other_user.id)
        foreign = Task(user_id=other_user.id, project_id=foreign_inbox.id, title="x")
        test_db.add(foreign)
        test_db.commit()

        resp = authenticated_client.post(
            "/api/v1/tasks", json={"title": "t", "parent_task_id": str(foreign.id)}
        )
        assert resp.status_code == 404


class TestInstanceTaskLink:
    """§8b: web stamps task_id onto the spawned instance via PATCH."""

    def test_patch_instance_with_task_id_links_and_syncs(
        self, authenticated_client, test_db, test_agent_instance
    ):
        task = authenticated_client.post("/api/v1/tasks", json={"title": "t"}).json()
        resp = authenticated_client.patch(
            f"/api/v1/agent-instances/{test_agent_instance.id}",
            json={"task_id": task["id"]},
        )
        assert resp.status_code == 200

        test_db.refresh(test_agent_instance)
        assert str(test_agent_instance.task_id) == task["id"]
        # The instance is already ACTIVE, so linking syncs the task (plan §8b).
        fetched = authenticated_client.get(f"/api/v1/tasks/{task['id']}").json()
        assert fetched["status"] == "in_progress"

    def test_patch_instance_rejects_foreign_task(
        self, authenticated_client, test_db, test_agent_instance, other_user
    ):
        foreign_inbox = get_or_create_inbox(test_db, other_user.id)
        foreign_task = Task(
            user_id=other_user.id, project_id=foreign_inbox.id, title="theirs"
        )
        test_db.add(foreign_task)
        test_db.commit()

        resp = authenticated_client.patch(
            f"/api/v1/agent-instances/{test_agent_instance.id}",
            json={"task_id": str(foreign_task.id)},
        )
        assert resp.status_code == 404
        test_db.refresh(test_agent_instance)
        assert test_agent_instance.task_id is None


class TestTaskSessions:
    """GET /tasks/{id}/sessions — the reverse of the §8b task_id link."""

    def test_lists_linked_sessions(
        self, authenticated_client, test_db, test_agent_instance
    ):
        task = authenticated_client.post("/api/v1/tasks", json={"title": "t"}).json()
        # No sessions yet.
        empty = authenticated_client.get(f"/api/v1/tasks/{task['id']}/sessions")
        assert empty.status_code == 200
        assert empty.json() == []

        # Link the instance, then it shows up.
        authenticated_client.patch(
            f"/api/v1/agent-instances/{test_agent_instance.id}",
            json={"task_id": task["id"]},
        )
        resp = authenticated_client.get(f"/api/v1/tasks/{task['id']}/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert [s["id"] for s in data] == [str(test_agent_instance.id)]

    def test_unknown_task_is_404(self, authenticated_client):
        resp = authenticated_client.get(f"/api/v1/tasks/{uuid4()}/sessions")
        assert resp.status_code == 404

    def test_foreign_task_is_404(self, authenticated_client, test_db, other_user):
        foreign_inbox = get_or_create_inbox(test_db, other_user.id)
        foreign_task = Task(
            user_id=other_user.id, project_id=foreign_inbox.id, title="theirs"
        )
        test_db.add(foreign_task)
        test_db.commit()

        resp = authenticated_client.get(f"/api/v1/tasks/{foreign_task.id}/sessions")
        assert resp.status_code == 404


class TestStatusLinkage:
    """Instance-status → task-status auto-linkage (plan §4, literal mapping)."""

    @pytest.fixture
    def linked_task(self, test_db, test_user, test_agent_instance):
        inbox = get_or_create_inbox(test_db, test_user.id)
        task = Task(user_id=test_user.id, project_id=inbox.id, title="linked")
        test_db.add(task)
        test_db.flush()
        test_agent_instance.task_id = task.id
        test_db.commit()
        return task

    def test_mapped_statuses_drive_task_status(
        self, test_db, test_agent_instance, linked_task
    ):
        for agent_status, expected in [
            (AgentStatus.ACTIVE, "in_progress"),
            (AgentStatus.COMPLETED, "done"),
            # Literal mapping accepted by Nick: REVIEWED after COMPLETED moves
            # the task backward done -> in_review (plan §4 caveat).
            (AgentStatus.REVIEWED, "in_review"),
        ]:
            test_agent_instance.status = agent_status
            test_db.commit()
            test_db.refresh(linked_task)
            assert linked_task.status == expected, agent_status

    def test_unmapped_statuses_leave_task_alone(
        self, test_db, test_agent_instance, linked_task
    ):
        linked_task.status = "todo"
        test_db.commit()

        for agent_status in [
            AgentStatus.AWAITING_INPUT,
            AgentStatus.PAUSED,
            AgentStatus.FAILED,
            AgentStatus.KILLED,
        ]:
            test_agent_instance.status = agent_status
            test_db.commit()
            test_db.refresh(linked_task)
            assert linked_task.status == "todo", agent_status

    def test_late_task_id_stamp_reevaluates_current_status(
        self, test_db, test_user, test_user_agent
    ):
        """§8b mitigation: the PATCH that stamps task_id lands after the
        instance already went ACTIVE — linking must still sync the task."""
        from shared.database import AgentInstance

        inbox = get_or_create_inbox(test_db, test_user.id)
        task = Task(user_id=test_user.id, project_id=inbox.id, title="late-link")
        instance = AgentInstance(
            id=uuid4(),
            user_agent_id=test_user_agent.id,
            user_id=test_user.id,
            status=AgentStatus.ACTIVE,
        )
        test_db.add_all([task, instance])
        test_db.commit()
        assert task.status == "backlog"

        instance.task_id = task.id
        test_db.commit()
        test_db.refresh(task)
        assert task.status == "in_progress"

    def test_no_sync_across_users(self, test_db, test_agent_instance, other_user):
        foreign_inbox = get_or_create_inbox(test_db, other_user.id)
        foreign_task = Task(
            user_id=other_user.id, project_id=foreign_inbox.id, title="theirs"
        )
        test_db.add(foreign_task)
        test_db.flush()

        test_agent_instance.task_id = foreign_task.id
        test_agent_instance.status = AgentStatus.COMPLETED
        test_db.commit()
        test_db.refresh(foreign_task)
        assert foreign_task.status == "backlog"

    def test_web_review_flow_marks_task(
        self, test_db, test_user, test_agent_instance, linked_task
    ):
        """The real backend path web uses (update_instance_status) syncs too."""
        from backend.db.queries import update_instance_status

        update_instance_status(
            test_db, test_agent_instance.id, test_user.id, AgentStatus.COMPLETED
        )
        test_db.refresh(linked_task)
        assert linked_task.status == "done"


class TestProjectAutoMatch:
    """Session ↔ project auto-match (shared/database/project_matching.py)."""

    def _link(self, db, user_id, machine_id, local_path, name="Proj"):
        project = Project(user_id=user_id, name=name)
        db.add(project)
        db.flush()
        db.add(
            ProjectDirectory(
                user_id=user_id,
                project_id=project.id,
                machine_id=machine_id,
                local_path=local_path,
            )
        )
        db.commit()
        return project

    def _instance(
        self,
        db,
        user_id,
        user_agent_id,
        machine_id,
        project,
        project_id=None,
        metadata=None,
    ):
        from shared.database import AgentInstance

        inst = AgentInstance(
            id=uuid4(),
            user_agent_id=user_agent_id,
            user_id=user_id,
            status=AgentStatus.ACTIVE,
            machine_id=machine_id,
            project=project,
            project_id=project_id,
            instance_metadata=metadata or {},
        )
        db.add(inst)
        db.commit()
        return inst

    def test_no_match_when_nothing_linked(self, test_db, test_user):
        from shared.database.project_matching import resolve_project_id_for_session

        machine = _make_machine(test_db, test_user.id)
        assert (
            resolve_project_id_for_session(
                test_db, test_user.id, machine.id, "/home/nick/alpha"
            )
            is None
        )

    def test_exact_and_child_path_match(self, test_db, test_user):
        from shared.database.project_matching import resolve_project_id_for_session

        machine = _make_machine(test_db, test_user.id)
        project = self._link(test_db, test_user.id, machine.id, "/home/nick/alpha")

        assert (
            resolve_project_id_for_session(
                test_db, test_user.id, machine.id, "/home/nick/alpha"
            )
            == project.id
        )
        assert (
            resolve_project_id_for_session(
                test_db, test_user.id, machine.id, "/home/nick/alpha/src/lib"
            )
            == project.id
        )

    def test_path_boundary_is_respected(self, test_db, test_user):
        """A sibling like /home/nick/alphabet must not match a link to /alpha."""
        from shared.database.project_matching import resolve_project_id_for_session

        machine = _make_machine(test_db, test_user.id)
        self._link(test_db, test_user.id, machine.id, "/home/nick/alpha")
        assert (
            resolve_project_id_for_session(
                test_db, test_user.id, machine.id, "/home/nick/alphabet"
            )
            is None
        )

    def test_longest_prefix_wins(self, test_db, test_user):
        from shared.database.project_matching import resolve_project_id_for_session

        machine = _make_machine(test_db, test_user.id)
        self._link(test_db, test_user.id, machine.id, "/home/nick", name="Broad")
        inner = self._link(
            test_db, test_user.id, machine.id, "/home/nick/alpha", name="Inner"
        )
        assert (
            resolve_project_id_for_session(
                test_db, test_user.id, machine.id, "/home/nick/alpha/x"
            )
            == inner.id
        )

    def test_machine_scoped(self, test_db, test_user):
        from shared.database.project_matching import resolve_project_id_for_session

        machine_a = _make_machine(test_db, test_user.id, display_name="A")
        machine_b = _make_machine(test_db, test_user.id, display_name="B")
        self._link(test_db, test_user.id, machine_a.id, "/home/nick/alpha")
        assert (
            resolve_project_id_for_session(
                test_db, test_user.id, machine_b.id, "/home/nick/alpha"
            )
            is None
        )

    def test_user_scoped(self, test_db, test_user, other_user):
        from shared.database.project_matching import resolve_project_id_for_session

        machine = _make_machine(test_db, other_user.id)
        self._link(test_db, other_user.id, machine.id, "/home/nick/alpha")
        # test_user querying the same machine/path sees nothing of other_user's.
        assert (
            resolve_project_id_for_session(
                test_db, test_user.id, machine.id, "/home/nick/alpha"
            )
            is None
        )

    def test_worktree_matched_by_repo_root(self, test_db, test_user):
        """A worktree's cwd sits outside the repo; its repo_root attributes it."""
        from shared.database.project_matching import resolve_project_id_for_session

        machine = _make_machine(test_db, test_user.id)
        project = self._link(test_db, test_user.id, machine.id, "/home/nick/alpha")
        worktree_cwd = "/home/nick/vicoa/workspaces/alpha-worktrees/feat/alpha"
        # cwd alone → no match (outside the linked checkout)…
        assert (
            resolve_project_id_for_session(
                test_db, test_user.id, machine.id, worktree_cwd
            )
            is None
        )
        # …but the reported repo root (the main checkout) attributes it.
        assert (
            resolve_project_id_for_session(
                test_db,
                test_user.id,
                machine.id,
                worktree_cwd,
                repo_root="/home/nick/alpha",
            )
            == project.id
        )

    def test_remote_tier_matches_across_paths(self, test_db, test_user):
        from shared.database.project_matching import resolve_project_id_for_session

        machine = _make_machine(test_db, test_user.id)
        project = Project(
            user_id=test_user.id,
            name="Remote",
            git_remote_url="git@github.com:vicoa-ai/vicoa.git",
        )
        test_db.add(project)
        test_db.commit()
        # No linked directory at all — remote identity alone resolves it.
        assert (
            resolve_project_id_for_session(
                test_db,
                test_user.id,
                machine.id,
                "/some/unlinked/path",
                git_remote_url="git@github.com:vicoa-ai/vicoa.git",
            )
            == project.id
        )

    def test_backfill_fills_nulls_without_stealing(
        self, test_db, test_user, test_user_agent
    ):
        from shared.database.project_matching import backfill_project_id_for_directory

        machine = _make_machine(test_db, test_user.id)
        project = Project(user_id=test_user.id, name="Alpha")
        other = Project(user_id=test_user.id, name="Other")
        test_db.add_all([project, other])
        test_db.flush()

        under = self._instance(
            test_db, test_user.id, test_user_agent.id, machine.id, "/home/nick/alpha/x"
        )
        already = self._instance(
            test_db,
            test_user.id,
            test_user_agent.id,
            machine.id,
            "/home/nick/alpha/y",
            project_id=other.id,
        )
        elsewhere = self._instance(
            test_db, test_user.id, test_user_agent.id, machine.id, "/home/nick/beta"
        )
        # A worktree session: cwd outside the repo, repo_root in metadata.
        worktree = self._instance(
            test_db,
            test_user.id,
            test_user_agent.id,
            machine.id,
            "/home/nick/vicoa/workspaces/alpha-worktrees/feat/alpha",
            metadata={"repo_root": "/home/nick/alpha"},
        )

        stamped = backfill_project_id_for_directory(
            test_db,
            user_id=test_user.id,
            project_id=project.id,
            machine_id=machine.id,
            local_path="/home/nick/alpha",
        )
        test_db.commit()
        assert stamped == 2  # `under` (cwd) + `worktree` (repo_root)
        for inst in (under, already, elsewhere, worktree):
            test_db.refresh(inst)
        assert under.project_id == project.id
        assert worktree.project_id == project.id  # matched by repo_root
        assert already.project_id == other.id  # not stolen
        assert elsewhere.project_id is None
