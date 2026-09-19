"""Tests for projects & tasks (plans/todos/tasks-and-projects-feature.md).

Covers the projects/tasks REST API (user scoping, the No-project default,
status/priority validation), project deletion filing work under No project,
and the instance-status → task-status linkage.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from shared.database import (
    Machine,
    Project,
    ProjectDirectory,
    ProjectGrant,
    Task,
    User,
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


class TestProjectsAPI:
    def test_list_projects_starts_empty(self, authenticated_client):
        """No hidden Inbox row: a fresh user has no projects at all."""
        resp = authenticated_client.get("/api/v1/projects")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_project_and_list(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/v1/projects", json={"name": "Alpha", "color": "#ff0000"}
        )
        assert resp.status_code == 201
        created = resp.json()
        assert created["name"] == "Alpha"
        assert created["color"] == "#ff0000"
        assert created["is_inbox"] is False
        assert created["last_activity_at"] is None

        listed = authenticated_client.get("/api/v1/projects").json()
        assert [p["name"] for p in listed] == ["Alpha"]

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

    def test_member_links_own_machine_owner_unlinks_it(
        self, authenticated_client, test_db, test_user, other_user
    ):
        """An editor grantee links THEIR machine to the shared project (that
        is how a team shares one project across laptops); a viewer may not;
        the owner can unlink the member's row, the member cannot unlink the
        owner's."""
        from backend.db import task_queries
        from shared.access import AccessDenied

        project = authenticated_client.post(
            "/api/v1/projects", json={"name": "Alpha"}
        ).json()
        owner_machine = _make_machine(test_db, test_user.id, "Owner box")
        authenticated_client.put(
            f"/api/v1/projects/{project['id']}/directories",
            json={"machine_id": str(owner_machine.id), "local_path": "/owner/alpha"},
        )
        member_machine = _make_machine(test_db, other_user.id, "Member box")
        grant = ProjectGrant(
            project_id=project["id"],
            principal_type="user",
            principal_id=other_user.id,
            role="viewer",
            scopes=["tasks", "sessions"],
        )
        test_db.add(grant)
        test_db.commit()

        with pytest.raises(AccessDenied):
            task_queries.set_project_directory(
                test_db,
                other_user.id,
                project["id"],
                member_machine.id,
                "/member/alpha",
                sharing=True,
            )
        grant.role = "editor"
        test_db.commit()
        linked = task_queries.set_project_directory(
            test_db,
            other_user.id,
            project["id"],
            member_machine.id,
            "/member/alpha",
            sharing=True,
        )
        assert linked is not None
        rows = {d.machine_id: d for d in linked.directories}
        assert rows[member_machine.id].user_id == other_user.id
        assert rows[owner_machine.id].user_id == test_user.id

        # The member may not unlink the owner's machine...
        with pytest.raises(AccessDenied):
            task_queries.delete_project_directory(
                test_db, other_user.id, project["id"], owner_machine.id, sharing=True
            )
        # ...but the owner may unlink the member's.
        resp = authenticated_client.delete(
            f"/api/v1/projects/{project['id']}/directories/{member_machine.id}"
        )
        assert resp.status_code == 200
        assert [d["machine_id"] for d in resp.json()["directories"]] == [
            str(owner_machine.id)
        ]

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

    def test_deleting_project_files_tasks_and_sessions_under_no_project(
        self, authenticated_client, test_db, test_user, test_agent_instance
    ):
        """Nothing cascades: tasks lose their identifier and go unfiled, the
        session stays and goes unfiled, comments/activity follow the task."""
        project = authenticated_client.post(
            "/api/v1/projects", json={"name": "Alpha"}
        ).json()
        task = authenticated_client.post(
            "/api/v1/tasks", json={"title": "keep me", "project_id": project["id"]}
        ).json()
        assert task["identifier"] is not None
        authenticated_client.post(
            f"/api/v1/tasks/{task['id']}/comments", json={"body": "a note"}
        )
        test_agent_instance.project_id = project["id"]
        test_db.commit()

        summary = authenticated_client.get(
            f"/api/v1/projects/{project['id']}/summary"
        ).json()
        assert summary == {
            "task_count": 1,
            "session_count": 1,
            "active_session_count": 1,
        }

        assert (
            authenticated_client.delete(f"/api/v1/projects/{project['id']}").status_code
            == 204
        )
        test_db.expire_all()

        after = authenticated_client.get(f"/api/v1/tasks/{task['id']}").json()
        assert after["project_id"] is None
        assert after["number"] is None
        assert after["identifier"] is None
        assert after["title"] == "keep me"
        timeline = authenticated_client.get(
            f"/api/v1/tasks/{task['id']}/timeline"
        ).json()
        assert [c["body"] for c in timeline["comments"]] == ["a note"]
        row = test_db.get(Task, task["id"])
        assert row is not None and row.user_id == test_user.id

        instance = test_db.get(type(test_agent_instance), test_agent_instance.id)
        assert instance is not None and instance.project_id is None
        assert (
            authenticated_client.get(
                f"/api/v1/projects/{project['id']}/summary"
            ).status_code
            == 404
        )

    def test_deleting_archived_project_is_allowed(self, authenticated_client):
        project = authenticated_client.post(
            "/api/v1/projects", json={"name": "Alpha"}
        ).json()
        authenticated_client.patch(
            f"/api/v1/projects/{project['id']}", json={"is_archived": True}
        )
        assert (
            authenticated_client.delete(f"/api/v1/projects/{project['id']}").status_code
            == 204
        )
        assert (
            authenticated_client.get("/api/v1/projects?include_archived=true").json()
            == []
        )


class TestTasksAPI:
    def test_create_task_defaults_to_no_project(self, authenticated_client):
        """Without a project the task is unfiled: NULL project, no identifier,
        and no project row gets minted behind the scenes."""
        resp = authenticated_client.post("/api/v1/tasks", json={"title": "Fix the bug"})
        assert resp.status_code == 201
        task = resp.json()
        assert task["title"] == "Fix the bug"
        assert task["status"] == "backlog"
        assert task["priority"] == "none"
        assert task["project_id"] is None
        assert task["number"] is None
        assert task["identifier"] is None

        assert authenticated_client.get("/api/v1/projects").json() == []
        listed = authenticated_client.get("/api/v1/tasks").json()
        assert [t["title"] for t in listed] == ["Fix the bug"]

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
        authenticated_client.post("/api/v1/tasks", json={"title": "unfiled-task"})

        all_tasks = authenticated_client.get("/api/v1/tasks").json()
        assert {t["title"] for t in all_tasks} == {
            "second",
            "first",
            "done-task",
            "unfiled-task",
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

        foreign_task = Task(user_id=other_user.id, project_id=None, title="theirs")
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
        foreign_task = Task(user_id=other_user.id, project_id=None, title="theirs")
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
        foreign = Task(user_id=other_user.id, project_id=None, title="x")
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
        foreign_task = Task(user_id=other_user.id, project_id=None, title="theirs")
        test_db.add(foreign_task)
        test_db.commit()

        resp = authenticated_client.patch(
            f"/api/v1/agent-instances/{test_agent_instance.id}",
            json={"task_id": str(foreign_task.id)},
        )
        assert resp.status_code == 404
        test_db.refresh(test_agent_instance)
        assert test_agent_instance.task_id is None

    def test_patch_instance_project_id_files_and_unfiles(
        self, authenticated_client, test_db, test_agent_instance, other_user
    ):
        """`project_id` on the session PATCH: file onto an own project (which
        also un-archives it), refuse a foreign one, and `null` unfiles."""
        project = authenticated_client.post(
            "/api/v1/projects", json={"name": "Alpha"}
        ).json()
        authenticated_client.patch(
            f"/api/v1/projects/{project['id']}", json={"is_archived": True}
        )

        resp = authenticated_client.patch(
            f"/api/v1/agent-instances/{test_agent_instance.id}",
            json={"project_id": project["id"]},
        )
        assert resp.status_code == 200
        assert resp.json()["project_id"] == project["id"]
        test_db.expire_all()
        assert test_db.get(Project, project["id"]).is_archived is False

        foreign = Project(user_id=other_user.id, name="Theirs")
        test_db.add(foreign)
        test_db.commit()
        resp = authenticated_client.patch(
            f"/api/v1/agent-instances/{test_agent_instance.id}",
            json={"project_id": str(foreign.id)},
        )
        assert resp.status_code == 404
        test_db.refresh(test_agent_instance)
        assert str(test_agent_instance.project_id) == project["id"]

        resp = authenticated_client.patch(
            f"/api/v1/agent-instances/{test_agent_instance.id}",
            json={"project_id": None},
        )
        assert resp.status_code == 200
        assert resp.json()["project_id"] is None


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
        foreign_task = Task(user_id=other_user.id, project_id=None, title="theirs")
        test_db.add(foreign_task)
        test_db.commit()

        resp = authenticated_client.get(f"/api/v1/tasks/{foreign_task.id}/sessions")
        assert resp.status_code == 404


class TestStatusLinkage:
    """Instance-status → task-status auto-linkage (plan §4, literal mapping)."""

    @pytest.fixture
    def linked_task(self, test_db, test_user, test_agent_instance):
        task = Task(user_id=test_user.id, project_id=None, title="linked")
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
        self, test_db, test_user, test_agent_type
    ):
        """§8b mitigation: the PATCH that stamps task_id lands after the
        instance already went ACTIVE — linking must still sync the task."""
        from shared.database import AgentInstance

        task = Task(user_id=test_user.id, project_id=None, title="late-link")
        instance = AgentInstance(
            id=uuid4(),
            agent_type_id=test_agent_type.id,
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
        foreign_task = Task(user_id=other_user.id, project_id=None, title="theirs")
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
        agent_type_id,
        machine_id,
        project,
        project_id=None,
        metadata=None,
    ):
        from shared.database import AgentInstance

        inst = AgentInstance(
            id=uuid4(),
            agent_type_id=agent_type_id,
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
        self, test_db, test_user, test_agent_type
    ):
        from shared.database.project_matching import backfill_project_id_for_directory

        machine = _make_machine(test_db, test_user.id)
        project = Project(user_id=test_user.id, name="Alpha")
        other = Project(user_id=test_user.id, name="Other")
        test_db.add_all([project, other])
        test_db.flush()

        under = self._instance(
            test_db, test_user.id, test_agent_type.id, machine.id, "/home/nick/alpha/x"
        )
        already = self._instance(
            test_db,
            test_user.id,
            test_agent_type.id,
            machine.id,
            "/home/nick/alpha/y",
            project_id=other.id,
        )
        elsewhere = self._instance(
            test_db, test_user.id, test_agent_type.id, machine.id, "/home/nick/beta"
        )
        # A worktree session: cwd outside the repo, repo_root in metadata.
        worktree = self._instance(
            test_db,
            test_user.id,
            test_agent_type.id,
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


class TestProjectAutoCreate:
    """Match-or-create + self-heal (resolve_or_create_project_id_for_session)."""

    def _count(self, db, user_id):
        return db.query(Project).filter(Project.user_id == user_id).count()

    def test_new_git_repo_creates_project_and_directory(self, test_db, test_user):
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        machine = _make_machine(test_db, test_user.id)
        pid = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            machine.id,
            "/home/nick/alpha",
            git_remote_url="git@github.com:vicoa-ai/alpha.git",
            repo_root="/home/nick/alpha",
            home_dir="/home/nick",
        )
        test_db.commit()
        assert pid is not None
        project = test_db.get(Project, pid)
        assert project.name == "alpha"  # repo basename
        assert project.git_remote_url == "git@github.com:vicoa-ai/alpha.git"
        assert not project.is_archived
        dirs = (
            test_db.query(ProjectDirectory)
            .filter(ProjectDirectory.project_id == pid)
            .all()
        )
        assert len(dirs) == 1
        assert dirs[0].machine_id == machine.id
        assert dirs[0].local_path == "/home/nick/alpha"

    def test_second_call_same_repo_is_idempotent(self, test_db, test_user):
        """A repeat register (incl. the concurrent-race re-check path) reuses it."""
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        machine = _make_machine(test_db, test_user.id)
        args = dict(
            git_remote_url="git@github.com:vicoa-ai/alpha.git",
            repo_root="/home/nick/alpha",
            home_dir="/home/nick",
        )
        first = resolve_or_create_project_id_for_session(
            test_db, test_user.id, machine.id, "/home/nick/alpha", **args
        )
        test_db.commit()
        second = resolve_or_create_project_id_for_session(
            test_db, test_user.id, machine.id, "/home/nick/alpha", **args
        )
        test_db.commit()
        assert first == second
        assert self._count(test_db, test_user.id) == 1

    def test_register_into_archived_project_unarchives(self, test_db, test_user):
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        machine = _make_machine(test_db, test_user.id)
        project = Project(
            user_id=test_user.id,
            name="alpha",
            git_remote_url="git@github.com:vicoa-ai/alpha.git",
            is_archived=True,
            archived_at=datetime.now(timezone.utc),
        )
        test_db.add(project)
        test_db.commit()

        pid = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            machine.id,
            "/home/nick/alpha",
            git_remote_url="git@github.com:vicoa-ai/alpha.git",
            repo_root="/home/nick/alpha",
        )
        test_db.commit()
        assert pid == project.id  # matched, not duplicated
        test_db.refresh(project)
        assert not project.is_archived and project.archived_at is None
        assert self._count(test_db, test_user.id) == 1

    def test_second_machine_same_remote_reuses_project(self, test_db, test_user):
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        machine_a = _make_machine(test_db, test_user.id, display_name="A")
        machine_b = _make_machine(test_db, test_user.id, display_name="B")
        remote = "git@github.com:vicoa-ai/alpha.git"
        pid_a = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            machine_a.id,
            "/a/alpha",
            git_remote_url=remote,
            repo_root="/a/alpha",
        )
        test_db.commit()
        pid_b = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            machine_b.id,
            "/b/alpha",
            git_remote_url=remote,
            repo_root="/b/alpha",
        )
        test_db.commit()
        assert pid_a == pid_b
        assert self._count(test_db, test_user.id) == 1
        dirs = (
            test_db.query(ProjectDirectory)
            .filter(ProjectDirectory.project_id == pid_a)
            .all()
        )
        assert {d.machine_id for d in dirs} == {machine_a.id, machine_b.id}

    def test_non_git_scratch_folder_creates_named_project(self, test_db, test_user):
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        machine = _make_machine(test_db, test_user.id)
        pid = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            machine.id,
            "/home/nick/scratch",
            home_dir="/home/nick",
        )
        test_db.commit()
        assert pid is not None
        assert test_db.get(Project, pid).name == "scratch"

    def test_home_dir_is_not_a_project(self, test_db, test_user):
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        machine = _make_machine(test_db, test_user.id)
        pid = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            machine.id,
            "/home/nick",
            home_dir="/home/nick",
        )
        test_db.commit()
        assert pid is None
        assert self._count(test_db, test_user.id) == 0

    def test_existing_broad_link_not_narrowed_by_subdir(self, test_db, test_user):
        """A session in a subdir of a linked repo keeps the broad link intact."""
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        machine = _make_machine(test_db, test_user.id)
        project = Project(user_id=test_user.id, name="alpha")
        test_db.add(project)
        test_db.flush()
        test_db.add(
            ProjectDirectory(
                user_id=test_user.id,
                project_id=project.id,
                machine_id=machine.id,
                local_path="/home/nick/alpha",
            )
        )
        test_db.commit()

        pid = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            machine.id,
            "/home/nick/alpha/src/lib",
        )
        test_db.commit()
        assert pid == project.id
        dirs = (
            test_db.query(ProjectDirectory)
            .filter(ProjectDirectory.project_id == project.id)
            .all()
        )
        assert len(dirs) == 1
        assert dirs[0].local_path == "/home/nick/alpha"  # not narrowed


class TestProjectMatchMachineless:
    """Registrations without a machine (no daemon yet, old client, container).

    Such a session can never get a directory row, so a path-only project
    minted for it would be an orphan — unreachable by any later match, and the
    next machine-less session in the same folder would mint another (prod had
    51 of these across 26 users before this rule). Instead: match by path on
    any of the user's machines, create only when there is a remote to match by
    later, else leave the session unfiled.
    """

    def _count(self, db, user_id):
        return db.query(Project).filter(Project.user_id == user_id).count()

    def _link(self, db, user_id, machine_id, local_path, name="Proj", **kw):
        project = Project(user_id=user_id, name=name, **kw)
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

    def test_no_machine_no_remote_no_match_stays_unfiled(self, test_db, test_user):
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        pid = resolve_or_create_project_id_for_session(
            test_db, test_user.id, None, "~/work/scratch", home_dir="/home/nick"
        )
        test_db.commit()
        assert pid is None
        assert self._count(test_db, test_user.id) == 0

    def test_no_machine_with_remote_creates_remote_keyed_project(
        self, test_db, test_user
    ):
        """A remote makes the project reachable again (tier 1), so create it —
        but with no machine there is no directory row to write."""
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        remote = "git@github.com:vicoa-ai/alpha.git"
        pid = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            None,
            "/tmp/alpha",
            git_remote_url=remote,
            repo_root="/tmp/alpha",
        )
        test_db.commit()
        assert pid is not None
        project = test_db.get(Project, pid)
        assert project.git_remote_url == remote
        assert (
            test_db.query(ProjectDirectory)
            .filter(ProjectDirectory.project_id == pid)
            .count()
            == 0
        )
        # …and a later daemon-backed session in the same repo lands on it.
        machine = _make_machine(test_db, test_user.id)
        again = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            machine.id,
            "~/alpha",
            git_remote_url=remote,
            repo_root="~/alpha",
            home_dir="/home/nick",
        )
        test_db.commit()
        assert again == pid
        assert self._count(test_db, test_user.id) == 1

    def test_no_machine_matches_path_on_any_machine(self, test_db, test_user):
        """The plugin on a box whose daemon is registered elsewhere: the same
        ~-relative folder is the same project."""
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        machine = _make_machine(test_db, test_user.id)
        project = self._link(test_db, test_user.id, machine.id, "~/work/wedding")

        pid = resolve_or_create_project_id_for_session(
            test_db, test_user.id, None, "~/work/wedding/site", home_dir="/root"
        )
        test_db.commit()
        assert pid == project.id
        assert self._count(test_db, test_user.id) == 1

    def test_no_machine_tie_across_machines_picks_oldest(self, test_db, test_user):
        from shared.database.project_matching import resolve_project_id_for_session

        machine_a = _make_machine(test_db, test_user.id, display_name="A")
        machine_b = _make_machine(test_db, test_user.id, display_name="B")
        older = self._link(test_db, test_user.id, machine_a.id, "~/x", name="older")
        older.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        newer = self._link(test_db, test_user.id, machine_b.id, "~/x", name="newer")
        newer.created_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
        test_db.commit()

        assert (
            resolve_project_id_for_session(test_db, test_user.id, None, "~/x/sub")
            == older.id
        )

    def test_with_machine_path_match_stays_per_machine(self, test_db, test_user):
        """The cross-machine lookup is only for sessions without a machine."""
        from shared.database.project_matching import resolve_project_id_for_session

        machine_a = _make_machine(test_db, test_user.id, display_name="A")
        machine_b = _make_machine(test_db, test_user.id, display_name="B")
        self._link(test_db, test_user.id, machine_a.id, "~/x")

        assert (
            resolve_project_id_for_session(test_db, test_user.id, machine_b.id, "~/x")
            is None
        )


class TestProjectMatchPathForms:
    """Both sides of a path comparison are canonicalized (~, \\, trailing /)."""

    def _link(self, db, user_id, machine_id, local_path, name="Proj", **kw):
        project = Project(user_id=user_id, name=name, **kw)
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

    def test_absolute_session_path_matches_tilde_row(self, test_db, test_user):
        """A wrapper whose HOME differs from the daemon's (e2e, containers)
        reports absolute paths; the linked row is ~-form. Same folder."""
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        machine = _make_machine(test_db, test_user.id)
        project = self._link(test_db, test_user.id, machine.id, "~/projects/vicoa")

        pid = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            machine.id,
            "/Users/nick/vicoa/workspaces/vicoa-worktrees/x/vicoa/backend",
            git_remote_url="git@github.com:vicoa-ai/vicoa.git",
            repo_root="/Users/nick/projects/vicoa",
            home_dir="/Users/nick",
        )
        test_db.commit()
        assert pid == project.id
        assert (
            test_db.query(Project).filter(Project.user_id == test_user.id).count() == 1
        )

    def test_tilde_session_path_matches_absolute_row(self, test_db, test_user):
        from shared.database.project_matching import resolve_project_id_for_session

        machine = _make_machine(test_db, test_user.id)
        project = self._link(test_db, test_user.id, machine.id, "/home/nick/alpha")
        assert (
            resolve_project_id_for_session(
                test_db, test_user.id, machine.id, "~/alpha/src", home_dir="/home/nick"
            )
            == project.id
        )

    def test_windows_backslash_paths(self, test_db, test_user):
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        machine = _make_machine(test_db, test_user.id)
        pid = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            machine.id,
            "~\\cp-pilot",
            home_dir="C:\\Users\\hans",
        )
        test_db.commit()
        assert pid is not None
        assert test_db.get(Project, pid).name == "cp-pilot"  # not "~\\cp-pilot"
        # A session in a subfolder, reported with backslashes, matches it.
        again = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            machine.id,
            "~\\cp-pilot\\src",
            home_dir="C:\\Users\\hans",
        )
        test_db.commit()
        assert again == pid

    def test_tilde_home_is_not_a_project(self, test_db, test_user):
        """Wrappers collapse HOME to ``~``; that is the home dir, not a repo
        called ``~`` (prod grew ~10 of those)."""
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        machine = _make_machine(test_db, test_user.id)
        for cwd, home in (
            ("~", "/home/nick"),
            ("~/", "/home/nick"),
            ("~", None),
            ("~\\", "C:\\Users\\hans"),
            ("C:\\", "C:\\Users\\hans"),
        ):
            assert (
                resolve_or_create_project_id_for_session(
                    test_db, test_user.id, machine.id, cwd, home_dir=home
                )
                is None
            ), cwd
        test_db.commit()
        assert (
            test_db.query(Project).filter(Project.user_id == test_user.id).count() == 0
        )


class TestProjectRemoteBackfill:
    """A folder-linked project learns its remote from the first session that
    reports one, so identity (tier 1) finds it from then on."""

    def _link(self, db, user_id, machine_id, local_path, name="Proj", **kw):
        project = Project(user_id=user_id, name=name, **kw)
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

    def test_repo_root_equals_linked_folder_stamps_remote(self, test_db, test_user):
        """The prod case: a hand-made 'Vicoa' linked to ~/projects/vicoa with
        no remote; a session there reports the remote → stamped, and a later
        machine-less worktree session finds it by identity instead of minting
        a twin."""
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        machine = _make_machine(test_db, test_user.id)
        project = self._link(test_db, test_user.id, machine.id, "~/projects/vicoa")
        remote = "git@github.com:vicoa-ai/vicoa.git"

        pid = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            machine.id,
            "~/projects/vicoa",
            git_remote_url=remote,
            repo_root="~/projects/vicoa",
            home_dir="/Users/nick",
        )
        test_db.commit()
        assert pid == project.id
        test_db.refresh(project)
        assert project.git_remote_url == remote

        twin = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            None,
            "/Users/nick/vicoa/workspaces/vicoa-worktrees/x/vicoa",
            git_remote_url=remote,
            repo_root="/Users/nick/projects/vicoa",
            home_dir="/var/folders/tmp",
        )
        test_db.commit()
        assert twin == project.id
        assert (
            test_db.query(Project).filter(Project.user_id == test_user.id).count() == 1
        )

    def test_parent_folder_link_is_not_stamped(self, test_db, test_user):
        """An umbrella folder linked as a project holds many repos; a session
        in one of them must not brand the umbrella with that repo's remote."""
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        machine = _make_machine(test_db, test_user.id)
        umbrella = self._link(test_db, test_user.id, machine.id, "~/projects")

        pid = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            machine.id,
            "~/projects/vicoa",
            git_remote_url="git@github.com:vicoa-ai/vicoa.git",
            repo_root="~/projects/vicoa",
            home_dir="/Users/nick",
        )
        test_db.commit()
        assert pid == umbrella.id  # longest link still wins for attribution…
        test_db.refresh(umbrella)
        assert umbrella.git_remote_url is None  # …but its identity is untouched

    def test_existing_remote_is_never_overwritten(self, test_db, test_user):
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        machine = _make_machine(test_db, test_user.id)
        project = self._link(
            test_db,
            test_user.id,
            machine.id,
            "~/alpha",
            git_remote_url="git@github.com:vicoa-ai/alpha.git",
        )
        # Same folder, a different remote reported (e.g. the user re-pointed
        # origin): tier 1 misses, tier 2 hits — the stored remote stays.
        pid = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            machine.id,
            "~/alpha",
            git_remote_url="git@github.com:fork/alpha.git",
            repo_root="~/alpha",
            home_dir="/home/nick",
        )
        test_db.commit()
        assert pid == project.id
        test_db.refresh(project)
        assert project.git_remote_url == "git@github.com:vicoa-ai/alpha.git"

    def test_shared_project_is_not_stamped_by_a_member(
        self, test_db, test_user, other_user
    ):
        """A member's clone matching the team project by folder must not
        rewrite the team project's identity."""
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        team_project = Project(user_id=other_user.id, name="team")
        test_db.add(team_project)
        test_db.flush()
        test_db.add(
            ProjectGrant(
                project_id=team_project.id,
                principal_type="user",
                principal_id=test_user.id,
                role="editor",
                scopes=["tasks", "sessions"],
            )
        )
        member_machine = _make_machine(test_db, test_user.id)
        test_db.add(
            ProjectDirectory(
                user_id=test_user.id,
                project_id=team_project.id,
                machine_id=member_machine.id,
                local_path="~/team",
            )
        )
        test_db.commit()

        pid = resolve_or_create_project_id_for_session(
            test_db,
            test_user.id,
            member_machine.id,
            "~/team",
            git_remote_url="git@github.com:team/team.git",
            repo_root="~/team",
            home_dir="/home/member",
        )
        test_db.commit()
        assert pid == team_project.id
        test_db.refresh(team_project)
        assert team_project.git_remote_url is None


class TestSharedProjectMatching:
    """A member's session lands on the project shared with them, not on a
    private twin — and never on one they may only view."""

    REMOTE = "git@github.com:vicoa-ai/alpha.git"

    def _shared_project(self, db, owner_id, member_id, role):
        project = Project(user_id=owner_id, name="alpha", git_remote_url=self.REMOTE)
        db.add(project)
        db.flush()
        db.add(
            ProjectGrant(
                project_id=project.id,
                principal_type="user",
                principal_id=member_id,
                role=role,
                scopes=["tasks", "sessions"],
            )
        )
        db.commit()
        return project

    def _register(self, db, user_id, machine_id, path="/home/bob/alpha"):
        from shared.database.project_matching import (
            resolve_or_create_project_id_for_session,
        )

        pid = resolve_or_create_project_id_for_session(
            db,
            user_id,
            machine_id,
            path,
            git_remote_url=self.REMOTE,
            repo_root=path,
            home_dir="/home/bob",
        )
        db.commit()
        return pid

    def test_editor_clone_on_own_machine_joins_the_shared_project(
        self, test_db, test_user, other_user
    ):
        shared = self._shared_project(test_db, test_user.id, other_user.id, "editor")
        machine = _make_machine(test_db, other_user.id, "bob-laptop")

        pid = self._register(test_db, other_user.id, machine.id)

        assert pid == shared.id
        # No private twin, and the member's machine is now linked (their row).
        assert (
            test_db.query(Project).filter(Project.user_id == other_user.id).count() == 0
        )
        row = (
            test_db.query(ProjectDirectory)
            .filter(
                ProjectDirectory.project_id == shared.id,
                ProjectDirectory.machine_id == machine.id,
            )
            .one()
        )
        assert row.user_id == other_user.id
        assert row.local_path == "/home/bob/alpha"

        # Second session: the path tier now hits the member's own row.
        again = self._register(test_db, other_user.id, machine.id, "/home/bob/alpha/x")
        assert again == shared.id

    def test_own_project_beats_a_shared_one_with_the_same_remote(
        self, test_db, test_user, other_user
    ):
        shared = self._shared_project(test_db, test_user.id, other_user.id, "editor")
        mine = Project(user_id=other_user.id, name="alpha", git_remote_url=self.REMOTE)
        test_db.add(mine)
        test_db.commit()
        machine = _make_machine(test_db, other_user.id, "bob-laptop")

        assert self._register(test_db, other_user.id, machine.id) == mine.id
        assert shared.id != mine.id

    def test_viewer_gets_a_private_project_not_the_shared_one(
        self, test_db, test_user, other_user
    ):
        shared = self._shared_project(test_db, test_user.id, other_user.id, "viewer")
        machine = _make_machine(test_db, other_user.id, "bob-laptop")

        pid = self._register(test_db, other_user.id, machine.id)

        assert pid is not None and pid != shared.id
        assert test_db.get(Project, pid).user_id == other_user.id

    def test_revoked_grant_stops_the_path_tier_from_attaching(
        self, test_db, test_user, other_user
    ):
        shared = self._shared_project(test_db, test_user.id, other_user.id, "editor")
        machine = _make_machine(test_db, other_user.id, "bob-laptop")
        assert self._register(test_db, other_user.id, machine.id) == shared.id

        test_db.query(ProjectGrant).filter(
            ProjectGrant.project_id == shared.id
        ).delete()
        test_db.commit()

        from shared.database.project_matching import resolve_project_id_for_session

        assert (
            resolve_project_id_for_session(
                test_db, other_user.id, machine.id, "/home/bob/alpha/sub"
            )
            is None
        )
