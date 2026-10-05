"""Collaborators read automations through the project they are filed under.

The authz matrix pins who gets 200 / 403 / 404 on every automation route. This
module covers what the matrix cannot see: what a collaborator's row carries
(and what it is stripped of), which project an automation's folder files it
under, the `automations` scope (on grants, for grant administrators, and on
share links), the run-history redaction, and the "started by" link on a
session.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.auth.dependencies import (
    get_current_claims,
    get_current_user,
    get_optional_current_user,
)
from backend.main import app
from shared.auth.tokens import TokenClaims
from shared.database import (
    GRANT_SCOPES,
    AgentInstance,
    AgentType,
    Automation,
    AutomationRun,
    Machine,
    Project,
    ProjectDirectory,
    ProjectGrant,
    User,
    UserInstanceAccess,
)
from shared.database.enums import AgentStatus, InstanceAccessLevel


@contextmanager
def _as(client: TestClient, user: User) -> Iterator[TestClient]:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_optional_current_user] = lambda: user
    app.dependency_overrides[get_current_claims] = lambda: TokenClaims(
        user_id=user.id, email=user.email, display_name=user.display_name
    )
    try:
        yield client
    finally:
        for dep in (get_current_user, get_optional_current_user, get_current_claims):
            app.dependency_overrides.pop(dep, None)


def _user(db, name: str) -> User:
    user = User(
        id=uuid4(),
        email=f"{name.lower()}@example.com",
        display_name=name,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    return user


def _machine(db, user: User, *, home_dir: str | None = None) -> Machine:
    machine = Machine(
        user_id=user.id, display_name="box", hostname="box.local", home_dir=home_dir
    )
    db.add(machine)
    db.flush()
    return machine


def _project(db, owner: User, name: str = "Shared Board") -> Project:
    project = Project(user_id=owner.id, name=name)
    db.add(project)
    db.flush()
    return project


def _link(db, user: User, project: Project, machine: Machine, path: str) -> None:
    db.add(
        ProjectDirectory(
            user_id=user.id,
            project_id=project.id,
            machine_id=machine.id,
            local_path=path,
        )
    )
    db.flush()


def _grant(
    db,
    project: Project,
    grantee: User,
    role: str,
    *,
    by: User,
    scopes: list[str] | None = None,
) -> ProjectGrant:
    grant = ProjectGrant(
        project_id=project.id,
        principal_type="user",
        principal_id=grantee.id,
        role=role,
        scopes=scopes or list(GRANT_SCOPES),
        granted_by_user_id=by.id,
    )
    db.add(grant)
    db.flush()
    return grant


def _automation(
    db, author: User, machine: Machine, directory: str, **extra
) -> Automation:
    fields = {
        "title": "Nightly sweep",
        "prompt": "sweep the queue",
        "session_config": {"agent": "claude", "model": "opus", "cwd": "/secret"},
        "schedule_kind": "recurring",
        "frequency": {"kind": "daily", "time": "09:00"},
        "timezone": "UTC",
    }
    fields.update(extra)
    automation = Automation(
        user_id=author.id, machine_id=machine.id, directory=directory, **fields
    )
    db.add(automation)
    db.flush()
    return automation


def _session(db, owner: User, project: Project | None) -> AgentInstance:
    agent_type = AgentType(user_id=owner.id, name=f"claude code {uuid4()}")
    db.add(agent_type)
    db.flush()
    instance = AgentInstance(
        agent_type_id=agent_type.id,
        user_id=owner.id,
        project_id=project.id if project else None,
        status=AgentStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
    )
    db.add(instance)
    db.flush()
    return instance


def _run(db, automation: Automation, instance: AgentInstance | None, **extra):
    run = AutomationRun(
        automation_id=automation.id,
        user_id=automation.user_id,
        agent_instance_id=instance.id if instance else None,
        status=extra.pop("status", "fired"),
        fired_at=datetime.now(timezone.utc),
        **extra,
    )
    db.add(run)
    db.flush()
    return run


def _ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [row["id"] for row in response.json()]


class TestCollaboratorRow:
    def test_viewer_reads_the_automation_without_anything_that_locates_the_machine(
        self, client, test_db, test_user
    ):
        owner = test_user
        viewer = _user(test_db, "Viewer")
        project = _project(test_db, owner)
        machine = _machine(test_db, owner)
        _link(test_db, owner, project, machine, "/Users/owner/code/widget")
        automation = _automation(
            test_db,
            owner,
            machine,
            "/Users/owner/code/widget",
            worktree={"mode": "existing", "path": "/Users/owner/wt/widget-fix"},
        )
        _grant(test_db, project, viewer, "viewer", by=owner)
        test_db.commit()

        with _as(client, viewer) as c:
            body = c.get(f"/api/v1/automations/{automation.id}").json()

        assert body["title"] == "Nightly sweep"
        assert body["prompt"] == "sweep the queue"
        assert body["owner"]["name"] == "Test User"
        assert "email" not in body["owner"]
        assert body["viewer_role"] == "viewer"
        assert body["project_id"] == str(project.id)
        # Nothing to aim a spawn or RPC at, and no path that leads to it.
        assert body["machine_id"] is None
        assert body["directory"] == "widget"
        assert body["worktree"] == {"mode": "existing"}
        assert body["session_config"] == {"agent": "claude", "model": "opus"}
        assert body["agent_profile_id"] is None

    def test_owner_row_is_untouched(self, authenticated_client, test_db, test_user):
        project = _project(test_db, test_user)
        machine = _machine(test_db, test_user)
        _link(test_db, test_user, project, machine, "/repo")
        automation = _automation(test_db, test_user, machine, "/repo")
        test_db.commit()

        body = authenticated_client.get(f"/api/v1/automations/{automation.id}").json()

        assert body["machine_id"] == str(machine.id)
        assert body["directory"] == "/repo"
        assert body["owner"] is None
        assert body["viewer_role"] is None
        # Every dashboard row says where it is filed; the web filters on it.
        assert body["project_id"] == str(project.id)

    def test_a_project_lists_everyones_automations_filed_in_it(
        self, client, test_db, test_user
    ):
        owner, editor = test_user, _user(test_db, "Editor")
        project = _project(test_db, owner)
        elsewhere = _project(test_db, editor, "Elsewhere")
        owner_box = _machine(test_db, owner)
        editor_box = _machine(test_db, editor)
        _link(test_db, owner, project, owner_box, "/repo")
        _link(test_db, editor, project, editor_box, "/src/repo")
        _link(test_db, editor, elsewhere, editor_box, "/src/other")
        _grant(test_db, project, editor, "editor", by=owner)
        mine = _automation(test_db, editor, editor_box, "/src/repo", title="mine")
        other = _automation(test_db, editor, editor_box, "/src/other", title="other")
        theirs = _automation(test_db, owner, owner_box, "/repo", title="theirs")
        test_db.commit()

        with _as(client, editor) as c:
            # The default list: my own, wherever they are filed.
            assert set(_ids(c.get("/api/v1/automations"))) == {
                str(mine.id),
                str(other.id),
            }
            rows = c.get(f"/api/v1/automations?project_id={project.id}").json()

        by_id = {r["id"]: r for r in rows}
        assert set(by_id) == {str(mine.id), str(theirs.id)}
        # Mine stays mine (editable, unredacted); theirs is read-only.
        assert by_id[str(mine.id)]["owner"] is None
        assert by_id[str(mine.id)]["machine_id"] == str(editor_box.id)
        assert by_id[str(theirs.id)]["viewer_role"] == "editor"
        assert by_id[str(theirs.id)]["machine_id"] is None
        assert {r["project_id"] for r in rows} == {str(project.id)}

    def test_scope_all_is_mine_everywhere_plus_what_projects_share(
        self, client, test_db, test_user
    ):
        """The dashboard's default view: every one of mine (filed or not),
        plus collaborators' in projects shared with me with the scope, never
        those in a project shared without it."""
        owner, editor = test_user, _user(test_db, "Editor")
        shared = _project(test_db, owner, "Shared")
        narrow = _project(test_db, owner, "Narrow")
        owner_box = _machine(test_db, owner)
        editor_box = _machine(test_db, editor)
        _link(test_db, owner, shared, owner_box, "/repo")
        _link(test_db, owner, narrow, owner_box, "/narrow")
        _grant(test_db, shared, editor, "editor", by=owner)
        _grant(
            test_db, narrow, editor, "editor", by=owner, scopes=["tasks", "sessions"]
        )
        mine = _automation(test_db, editor, editor_box, "/scratch", title="mine")
        theirs = _automation(test_db, owner, owner_box, "/repo", title="theirs")
        _automation(test_db, owner, owner_box, "/narrow", title="hidden")
        test_db.commit()

        with _as(client, editor) as c:
            rows = c.get("/api/v1/automations?scope=all").json()

        by_title = {r["title"]: r for r in rows}
        assert set(by_title) == {"mine", "theirs"}
        assert by_title["mine"]["project_id"] is None
        assert by_title["mine"]["owner"] is None
        assert by_title["theirs"]["project_id"] == str(shared.id)
        assert by_title["theirs"]["viewer_role"] == "editor"
        assert by_title["theirs"]["machine_id"] is None
        assert {by_title["mine"]["id"], by_title["theirs"]["id"]} == {
            str(mine.id),
            str(theirs.id),
        }

    def test_a_grant_without_the_automations_scope_hides_them(
        self, client, test_db, test_user
    ):
        """Grants made before the scope existed, or with it unticked, carry
        the board and the sessions but not the automations."""
        owner, viewer = test_user, _user(test_db, "Viewer")
        project = _project(test_db, owner)
        machine = _machine(test_db, owner)
        _link(test_db, owner, project, machine, "/repo")
        automation = _automation(test_db, owner, machine, "/repo")
        instance = _session(test_db, owner, project)
        _run(test_db, automation, instance)
        _grant(
            test_db, project, viewer, "viewer", by=owner, scopes=["tasks", "sessions"]
        )
        test_db.commit()

        with _as(client, viewer) as c:
            assert _ids(c.get(f"/api/v1/automations?project_id={project.id}")) == []
            assert c.get(f"/api/v1/automations/{automation.id}").status_code == 404
            # The run's session is still theirs to read; its automation is not.
            detail = c.get(f"/api/v1/agent-instances/{instance.id}").json()
        assert detail["automation"] is None

    def test_a_collaborators_write_is_refused_and_changes_nothing(
        self, client, test_db, test_user
    ):
        owner, editor = test_user, _user(test_db, "Editor")
        project = _project(test_db, owner)
        machine = _machine(test_db, owner)
        _link(test_db, owner, project, machine, "/repo")
        automation = _automation(test_db, owner, machine, "/repo")
        _grant(test_db, project, editor, "editor", by=owner)
        test_db.commit()

        with _as(client, editor) as c:
            patched = c.patch(
                f"/api/v1/automations/{automation.id}",
                json={"prompt": "rm -rf ~", "enabled": False},
            )
            ran = c.post(
                f"/api/v1/automations/{automation.id}/run", json={"status": "fired"}
            )
            deleted = c.delete(f"/api/v1/automations/{automation.id}")

        assert (patched.status_code, ran.status_code, deleted.status_code) == (
            403,
            403,
            403,
        )
        test_db.refresh(automation)
        assert automation.prompt == "sweep the queue"
        assert automation.enabled is True
        assert test_db.query(AutomationRun).count() == 0


class TestWhichProjectFilesAnAutomation:
    def test_a_project_owner_sees_an_editors_automation_as_admin(
        self, client, test_db, test_user
    ):
        owner, editor = test_user, _user(test_db, "Editor")
        project = _project(test_db, owner)
        editor_box = _machine(test_db, editor)
        _link(test_db, editor, project, editor_box, "/src/repo")
        _grant(test_db, project, editor, "editor", by=owner)
        automation = _automation(test_db, editor, editor_box, "/src/repo/pkg")
        test_db.commit()

        with _as(client, owner) as c:
            rows = c.get(f"/api/v1/automations?project_id={project.id}").json()

        assert [(r["id"], r["viewer_role"]) for r in rows] == [
            (str(automation.id), "admin")
        ]

    def test_a_viewers_automation_never_lands_on_the_project(
        self, client, test_db, test_user
    ):
        """Attaching is contributing: a viewer's folder link does not file
        their automation under someone else's project, so the project's
        people never see it."""
        owner, viewer = test_user, _user(test_db, "Viewer")
        project = _project(test_db, owner)
        viewer_box = _machine(test_db, viewer)
        _link(test_db, viewer, project, viewer_box, "/src/repo")
        _grant(test_db, project, viewer, "viewer", by=owner)
        automation = _automation(test_db, viewer, viewer_box, "/src/repo")
        test_db.commit()

        with _as(client, owner) as c:
            assert _ids(c.get(f"/api/v1/automations?project_id={project.id}")) == []
            assert c.get(f"/api/v1/automations/{automation.id}").status_code == 404

    def test_revoking_the_grant_takes_the_automation_off_the_project(
        self, client, test_db, test_user
    ):
        owner, editor = test_user, _user(test_db, "Editor")
        project = _project(test_db, owner)
        editor_box = _machine(test_db, editor)
        _link(test_db, editor, project, editor_box, "/src/repo")
        grant = _grant(test_db, project, editor, "editor", by=owner)
        automation = _automation(test_db, editor, editor_box, "/src/repo")
        test_db.commit()

        with _as(client, owner) as c:
            assert _ids(c.get(f"/api/v1/automations?project_id={project.id}")) == [
                str(automation.id)
            ]
            test_db.delete(grant)
            test_db.commit()
            # The editor's folder link outlives the grant; it must stop counting.
            assert _ids(c.get(f"/api/v1/automations?project_id={project.id}")) == []

    def test_the_deepest_link_wins(self, client, test_db, test_user):
        """A private project linked inside the shared checkout claims the
        automations under it, so the shared project's people don't see them."""
        owner, editor = test_user, _user(test_db, "Editor")
        shared = _project(test_db, owner)
        private = _project(test_db, editor, "Scratch")
        box = _machine(test_db, editor)
        _link(test_db, editor, shared, box, "/src/repo")
        _link(test_db, editor, private, box, "/src/repo/scratch")
        _grant(test_db, shared, editor, "editor", by=owner)
        filed = _automation(test_db, editor, box, "/src/repo/app", title="filed")
        _automation(test_db, editor, box, "/src/repo/scratch/x", title="private")
        test_db.commit()

        with _as(client, owner) as c:
            assert _ids(c.get(f"/api/v1/automations?project_id={shared.id}")) == [
                str(filed.id)
            ]

    def test_a_link_on_another_machine_does_not_file_it(
        self, client, test_db, test_user
    ):
        owner, editor = test_user, _user(test_db, "Editor")
        project = _project(test_db, owner)
        laptop, desktop = _machine(test_db, editor), _machine(test_db, editor)
        _link(test_db, editor, project, laptop, "/src/repo")
        _grant(test_db, project, editor, "editor", by=owner)
        _automation(test_db, editor, desktop, "/src/repo")
        test_db.commit()

        with _as(client, owner) as c:
            assert _ids(c.get(f"/api/v1/automations?project_id={project.id}")) == []

    def test_tilde_and_absolute_paths_compare_with_the_machines_home(
        self, client, test_db, test_user
    ):
        owner, editor = test_user, _user(test_db, "Editor")
        project = _project(test_db, owner)
        box = _machine(test_db, editor, home_dir="/home/editor")
        _link(test_db, editor, project, box, "~/src/repo")
        _grant(test_db, project, editor, "editor", by=owner)
        automation = _automation(test_db, editor, box, "/home/editor/src/repo")
        test_db.commit()

        with _as(client, owner) as c:
            assert _ids(c.get(f"/api/v1/automations?project_id={project.id}")) == [
                str(automation.id)
            ]

    def test_a_sessions_only_share_is_not_enough(self, client, test_db, test_user):
        """A per-session share opens one transcript, not the schedule behind
        it — even when that session is one of the automation's runs."""
        owner, guest = test_user, _user(test_db, "Guest")
        project = _project(test_db, owner)
        machine = _machine(test_db, owner)
        _link(test_db, owner, project, machine, "/repo")
        automation = _automation(test_db, owner, machine, "/repo")
        instance = _session(test_db, owner, project)
        _run(test_db, automation, instance)
        test_db.add(
            UserInstanceAccess(
                agent_instance_id=instance.id,
                shared_email=guest.email,
                user_id=guest.id,
                access=InstanceAccessLevel.READ,
                granted_by_user_id=owner.id,
            )
        )
        test_db.commit()

        with _as(client, guest) as c:
            assert _ids(c.get(f"/api/v1/automations?project_id={project.id}")) == []
            assert c.get(f"/api/v1/automations/{automation.id}").status_code == 404
            detail = c.get(f"/api/v1/agent-instances/{instance.id}").json()
        assert detail["automation"] is None


class TestRunHistory:
    def test_collaborator_runs_drop_detail_and_unopenable_sessions(
        self, client, test_db, test_user
    ):
        owner, viewer = test_user, _user(test_db, "Viewer")
        project = _project(test_db, owner)
        machine = _machine(test_db, owner)
        _link(test_db, owner, project, machine, "/repo")
        automation = _automation(test_db, owner, machine, "/repo")
        _grant(test_db, project, viewer, "viewer", by=owner)
        in_project = _session(test_db, owner, project)
        unfiled = _session(test_db, owner, None)
        _run(test_db, automation, in_project)
        _run(test_db, automation, unfiled)
        _run(test_db, automation, None, status="failed", detail="/Users/owner: boom")
        test_db.commit()

        with _as(client, viewer) as c:
            runs = c.get(f"/api/v1/automations/{automation.id}/runs").json()
        with _as(client, owner) as c:
            owner_runs = c.get(f"/api/v1/automations/{automation.id}/runs").json()

        assert len(runs) == 3
        assert {r["agent_instance_id"] for r in runs} == {str(in_project.id), None}
        assert all(r["detail"] is None for r in runs)
        assert {r["agent_instance_id"] for r in owner_runs} == {
            str(in_project.id),
            str(unfiled.id),
            None,
        }
        assert "/Users/owner: boom" in {r["detail"] for r in owner_runs}


class TestStartedByOnTheSession:
    def test_the_session_names_its_automation_for_owner_and_collaborator(
        self, client, test_db, test_user
    ):
        owner, viewer = test_user, _user(test_db, "Viewer")
        project = _project(test_db, owner)
        machine = _machine(test_db, owner)
        _link(test_db, owner, project, machine, "/repo")
        automation = _automation(test_db, owner, machine, "/repo")
        _grant(test_db, project, viewer, "viewer", by=owner)
        instance = _session(test_db, owner, project)
        _run(test_db, automation, instance)
        test_db.commit()

        expected = {"id": str(automation.id), "title": "Nightly sweep"}
        for user in (owner, viewer):
            with _as(client, user) as c:
                detail = c.get(f"/api/v1/agent-instances/{instance.id}").json()
            assert detail["automation"] == expected, user.display_name

    def test_a_hand_started_session_names_none(
        self, authenticated_client, test_db, test_user
    ):
        instance = _session(test_db, test_user, None)
        test_db.commit()

        detail = authenticated_client.get(
            f"/api/v1/agent-instances/{instance.id}"
        ).json()

        assert detail["automation"] is None


class TestShareLinkCarriesAutomations:
    def _world(self, db, owner: User) -> tuple[Project, Automation]:
        project = _project(db, owner)
        machine = _machine(db, owner)
        _link(db, owner, project, machine, "/Users/owner/code/widget")
        automation = _automation(db, owner, machine, "/Users/owner/code/widget")
        db.commit()
        return project, automation

    def _link_token(self, c: TestClient, project: Project, scopes: list[str]) -> str:
        response = c.post(
            "/api/v1/shares",
            json={"kind": "project", "project_id": str(project.id), "scopes": scopes},
        )
        assert response.status_code == 201, response.text
        return response.json()["token"]

    def test_a_link_with_the_scope_shows_what_runs_and_when_only(
        self, client, test_db, test_user
    ):
        project, automation = self._world(test_db, test_user)
        with _as(client, test_user) as c:
            token = self._link_token(c, project, ["tasks", "automations"])

        body = client.get(f"/api/v1/public/shares/{token}/automations").json()

        [row] = body["items"]
        assert row["id"] == str(automation.id)
        assert row["title"] == "Nightly sweep"
        assert row["prompt"] == "sweep the queue"
        assert row["session_config"] == {"agent": "claude", "model": "opus"}
        # Never the author, the machine or the folder.
        assert not {"owner", "machine_id", "directory", "worktree"} & set(row)

    def test_a_link_without_the_scope_shows_none(self, client, test_db, test_user):
        project, _ = self._world(test_db, test_user)
        with _as(client, test_user) as c:
            token = self._link_token(c, project, ["tasks", "sessions"])

        body = client.get(f"/api/v1/public/shares/{token}/automations").json()

        assert body == {"items": []}

    def test_publishing_them_needs_admin_over_them(self, client, test_db, test_user):
        project, _ = self._world(test_db, test_user)
        legacy = _user(test_db, "Legacy")
        _grant(
            test_db,
            project,
            legacy,
            "admin",
            by=test_user,
            scopes=["tasks", "sessions"],
        )
        test_db.commit()

        with _as(client, legacy) as c:
            refused = c.post(
                "/api/v1/shares",
                json={
                    "kind": "project",
                    "project_id": str(project.id),
                    "scopes": ["automations"],
                },
            )
            allowed = c.post(
                "/api/v1/shares",
                json={
                    "kind": "project",
                    "project_id": str(project.id),
                    "scopes": ["tasks"],
                },
            )

        # A scope the caller cannot see is an invisible target to a link, the
        # same 404 a tasks-only admin gets for a sessions link.
        assert refused.status_code == 404
        assert allowed.status_code == 201


class TestGrantAdministrationWithTheNewScope:
    """An admin whose grant predates `automations` keeps managing people over
    tasks and sessions, but can neither hand out nor take back access to the
    automations, which they do not administer."""

    def _setup(self, db, owner: User) -> tuple[Project, User]:
        project = _project(db, owner)
        legacy = _user(db, "Legacy")
        _grant(db, project, legacy, "admin", by=owner, scopes=["tasks", "sessions"])
        db.commit()
        return project, legacy

    def test_an_omitted_scope_list_grants_what_the_granter_administers(
        self, client, test_db, test_user
    ):
        project, legacy = self._setup(test_db, test_user)
        url = f"/api/v1/projects/{project.id}/grants"

        with _as(client, legacy) as c:
            by_legacy = c.post(url, json={"email": "a@example.com", "role": "viewer"})
        with _as(client, test_user) as c:
            by_owner = c.post(url, json={"email": "b@example.com", "role": "viewer"})

        assert by_legacy.status_code == 201, by_legacy.text
        assert by_owner.status_code == 201, by_owner.text
        assert by_legacy.json()["scopes"] == ["tasks", "sessions"]
        assert by_owner.json()["scopes"] == list(GRANT_SCOPES)

    def test_the_legacy_admin_cannot_hand_out_or_revoke_automations(
        self, client, test_db, test_user
    ):
        project, legacy = self._setup(test_db, test_user)
        other = _user(test_db, "Other")
        carrying = _grant(test_db, project, other, "viewer", by=test_user)
        test_db.commit()
        url = f"/api/v1/projects/{project.id}/grants"

        with _as(client, legacy) as c:
            handed = c.post(
                url,
                json={
                    "email": "c@example.com",
                    "role": "viewer",
                    "scopes": ["automations"],
                },
            )
            widened = c.patch(f"{url}/{carrying.id}", json={"role": "commenter"})
            revoked = c.delete(f"{url}/{carrying.id}")
        with _as(client, test_user) as c:
            by_owner = c.delete(f"{url}/{carrying.id}")

        assert (handed.status_code, widened.status_code, revoked.status_code) == (
            403,
            403,
            403,
        )
        assert by_owner.status_code == 204
