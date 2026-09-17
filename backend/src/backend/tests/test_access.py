"""`shared.access` — the resolver — plus the capability seam, grant creation,
label visibility and account-deletion sweeps (collaboration §4, §6, §3.3).

The HTTP-level behaviour is pinned by `test_authz_matrix.py`; this file pins
the resolver's own semantics so a future refactor can be checked against them
without going through FastAPI.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from backend.db import collab_queries, task_queries
from backend.db.collab_queries import GrantError
from backend.db.queries import delete_user_account
from shared import access, hooks
from shared.access import AccessDenied
from shared.database import (
    AgentInstance,
    AgentType,
    Project,
    ProjectGrant,
    Task,
    TaskLabel,
    Team,
    TeamInvite,
    TeamMember,
    User,
    UserInstanceAccess,
    get_or_create_inbox,
)
from shared.database.enums import AgentStatus, InstanceAccessLevel


def _user(db, email: str) -> User:
    user = User(
        id=uuid4(),
        email=email,
        display_name=email.split("@")[0],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    return user


def _team(db, *members: tuple[User, str, str]) -> Team:
    team = Team(name="T", slug=f"t-{uuid4().hex[:8]}")
    db.add(team)
    db.flush()
    for user, role, status in members:
        db.add(
            TeamMember(
                team_id=team.id,
                user_id=user.id,
                invited_email=user.email,
                role=role,
                status=status,
            )
        )
    db.commit()
    return team


def _grant(
    db,
    project: Project,
    principal_type: str,
    principal_id: UUID,
    role: str,
    scopes=None,
):
    db.add(
        ProjectGrant(
            project_id=project.id,
            principal_type=principal_type,
            principal_id=principal_id,
            role=role,
            scopes=scopes or ["tasks", "sessions"],
        )
    )
    db.commit()


@pytest.fixture
def other(test_db) -> User:
    return _user(test_db, "other@example.com")


@pytest.fixture
def project(test_db, test_user) -> Project:
    return task_queries.create_project(test_db, test_user.id, name="Board")


@pytest.fixture(autouse=True)
def _no_capability_hooks(monkeypatch):
    monkeypatch.setattr(hooks, "_capability_hooks", [])


class TestRoleLadder:
    def test_require(self):
        assert access.require("editor", "viewer") == "editor"
        assert access.require("owner", "owner") == "owner"
        with pytest.raises(AccessDenied) as exc:
            access.require("commenter", "editor")
        assert exc.value.minimum == "editor"
        with pytest.raises(AccessDenied):
            access.require(None, "viewer")

    def test_max_role(self):
        assert access.max_role(None, "viewer", "admin", "editor") == "admin"
        assert access.max_role(None, None) is None


class TestProjectRole:
    def test_owner_and_stranger(self, test_db, test_user, other, project):
        assert access.project_role(test_db, test_user.id, project) == "owner"
        assert access.project_role(test_db, other.id, project) is None
        assert access.project_role(test_db, other.id, uuid4()) is None

    def test_inbox_is_never_grantable(self, test_db, test_user, other):
        inbox = get_or_create_inbox(test_db, test_user.id)
        _grant(test_db, inbox, "user", other.id, "admin")
        assert access.project_role(test_db, other.id, inbox) is None
        assert inbox.id not in access.visible_project_ids(test_db, other.id)

    def test_direct_grant_and_scopes(self, test_db, other, project):
        _grant(test_db, project, "user", other.id, "editor", scopes=["sessions"])
        assert access.project_role(test_db, other.id, project) == "editor"
        assert (
            access.project_role(test_db, other.id, project, grant_scope="sessions")
            == "editor"
        )
        assert (
            access.project_role(test_db, other.id, project, grant_scope="tasks") is None
        )
        assert access.project_access(
            test_db, other.id, project
        ) == access.ProjectAccess("editor", ("sessions",))

    def test_grants_merge_strongest_role_and_union_of_scopes(
        self, test_db, other, project
    ):
        team = _team(test_db, (other, "member", "active"))
        _grant(test_db, project, "user", other.id, "viewer", scopes=["tasks"])
        _grant(test_db, project, "team", team.id, "editor", scopes=["sessions"])
        assert access.project_access(
            test_db, other.id, project
        ) == access.ProjectAccess("editor", ("tasks", "sessions"))

    def test_team_grant_needs_active_membership(self, test_db, other, project):
        team = _team(test_db, (other, "member", "invited"))
        _grant(test_db, project, "team", team.id, "admin")
        assert access.project_role(test_db, other.id, project) is None
        row = test_db.query(TeamMember).filter(TeamMember.user_id == other.id).one()
        row.status = "active"
        test_db.commit()
        assert access.project_role(test_db, other.id, project) == "admin"
        row.status = "removed"
        test_db.commit()
        assert access.project_role(test_db, other.id, project) is None

    def test_team_owned_project_maps_team_roles(
        self, test_db, test_user, other, project
    ):
        stranger = _user(test_db, "s@example.com")
        team = _team(
            test_db, (test_user, "member", "active"), (other, "admin", "active")
        )
        project.team_id = team.id
        test_db.commit()
        # The creator demotes to their team role; the team admin is admin.
        assert access.project_role(test_db, test_user.id, project) == "editor"
        assert access.project_role(test_db, other.id, project) == "admin"
        assert access.project_role(test_db, stranger.id, project) is None
        # Deleting the team demotes the project back to personal (SET NULL).
        test_db.delete(team)
        test_db.commit()
        test_db.refresh(project)
        assert project.team_id is None
        assert access.project_role(test_db, test_user.id, project) == "owner"
        assert access.project_role(test_db, other.id, project) is None

    def test_visible_project_ids_scopes(self, test_db, test_user, other, project):
        mine = task_queries.create_project(test_db, other.id, name="Mine")
        _grant(test_db, project, "user", other.id, "viewer")
        team = _team(test_db, (other, "member", "active"))
        team_owned = task_queries.create_project(test_db, test_user.id, name="Team")
        team_owned.team_id = team.id
        test_db.commit()

        assert access.visible_project_ids(test_db, other.id, scope="me") == {mine.id}
        assert access.visible_project_ids(test_db, other.id, scope="shared") == {
            project.id,
            team_owned.id,
        }
        assert access.visible_project_ids(test_db, other.id) == {
            mine.id,
            project.id,
            team_owned.id,
        }
        # min_role drops grants below the floor but keeps team-owned (editor).
        assert access.visible_project_ids(test_db, other.id, min_role="editor") == {
            mine.id,
            team_owned.id,
        }


class TestInstanceAccess:
    @pytest.fixture
    def instance(self, test_db, test_user, project) -> AgentInstance:
        agent_type = AgentType(user_id=test_user.id, name="claude code", is_active=True)
        test_db.add(agent_type)
        test_db.flush()
        instance = AgentInstance(
            agent_type_id=agent_type.id,
            user_id=test_user.id,
            project_id=project.id,
            status=AgentStatus.ACTIVE,
            started_at=datetime.now(timezone.utc),
        )
        test_db.add(instance)
        test_db.commit()
        return instance

    def test_owner_write_stranger_none(self, test_db, test_user, other, instance):
        assert access.instance_role(test_db, test_user.id, instance) == "owner"
        assert (
            access.instance_access(test_db, test_user.id, instance)
            == InstanceAccessLevel.WRITE
        )
        assert access.instance_role(test_db, other.id, instance) is None
        assert access.instance_access(test_db, other.id, instance) is None

    def test_project_term_extends_session_share(
        self, test_db, test_user, other, project, instance
    ):
        # Session share READ alone ⇒ viewer / READ.
        test_db.add(
            UserInstanceAccess(
                agent_instance_id=instance.id,
                shared_email=other.email,
                user_id=other.id,
                access=InstanceAccessLevel.READ,
                granted_by_user_id=test_user.id,
            )
        )
        test_db.commit()
        assert access.instance_role(test_db, other.id, instance) == "viewer"
        assert (
            access.instance_access(test_db, other.id, instance)
            == InstanceAccessLevel.READ
        )
        # A project grant covering sessions lifts it.
        _grant(test_db, project, "user", other.id, "editor")
        assert access.instance_role(test_db, other.id, instance) == "editor"
        assert (
            access.instance_access(test_db, other.id, instance)
            == InstanceAccessLevel.WRITE
        )

    def test_tasks_only_grant_does_not_reach_sessions(
        self, test_db, other, project, instance
    ):
        _grant(test_db, project, "user", other.id, "admin", scopes=["tasks"])
        assert access.instance_role(test_db, other.id, instance) is None
        assert (
            set(
                r[0]
                for r in test_db.execute(access.shared_instance_select(other.id)).all()
            )
            == set()
        )

    def test_commenter_reads_only(self, test_db, other, project, instance):
        _grant(test_db, project, "user", other.id, "commenter")
        assert (
            access.instance_access(test_db, other.id, instance)
            == InstanceAccessLevel.READ
        )

    def test_deleted_session_invisible_to_non_owner(
        self, test_db, test_user, other, project, instance
    ):
        _grant(test_db, project, "user", other.id, "admin")
        instance.status = AgentStatus.DELETED
        test_db.commit()
        assert access.instance_role(test_db, other.id, instance) is None
        assert access.instance_role(test_db, test_user.id, instance) == "owner"
        assert instance.id not in {
            r[0] for r in test_db.execute(access.shared_instance_select(other.id)).all()
        }

    def test_shared_instance_select_excludes_own(
        self, test_db, test_user, other, project, instance
    ):
        _grant(test_db, project, "user", other.id, "viewer")
        assert {
            r[0] for r in test_db.execute(access.shared_instance_select(other.id)).all()
        } == {instance.id}
        assert {
            r[0]
            for r in test_db.execute(access.shared_instance_select(test_user.id)).all()
        } == set()


class TestCapabilityHook:
    def test_empty_registry_allows(self, test_db):
        hooks.check_capability(test_db, uuid4(), "collab.team_seat", {})

    def test_denial_reason_propagates(self, test_db, monkeypatch):
        calls = []

        def hook(db, user_id, capability, context):
            calls.append((capability, context))
            return "nope" if capability == "collab.grant_write" else None

        monkeypatch.setattr(hooks, "_capability_hooks", [hook])
        hooks.check_capability(test_db, uuid4(), "collab.team_seat", {"seats": 1})
        with pytest.raises(hooks.CapabilityDenied) as exc:
            hooks.check_capability(test_db, uuid4(), "collab.grant_write", {})
        assert exc.value.reason == "nope"
        assert exc.value.capability == "collab.grant_write"
        assert len(calls) == 2

    def test_raising_hook_fails_closed(self, test_db, monkeypatch):
        def broken(db, user_id, capability, context):
            raise RuntimeError("billing is down")

        monkeypatch.setattr(hooks, "_capability_hooks", [broken])
        with pytest.raises(hooks.CapabilityDenied):
            hooks.check_capability(test_db, uuid4(), "collab.team_seat", {})

    def test_database_error_is_not_a_billing_answer(self, test_db, monkeypatch):
        """A transient DB error must not become 402. It still denies the action
        (the request aborts), but as `503 + Retry-After` via main.py's handler
        — telling a *paying* customer to upgrade because flycast blipped is
        both wrong and unretryable."""
        from sqlalchemy.exc import OperationalError

        def flaky(db, user_id, capability, context):
            raise OperationalError("SELECT 1", {}, Exception("connection lost"))

        monkeypatch.setattr(hooks, "_capability_hooks", [flaky])
        with pytest.raises(OperationalError):
            hooks.check_capability(test_db, uuid4(), "collab.team_seat", {})

    def test_other_errors_still_fail_closed_as_denial(self, test_db, monkeypatch):
        """Narrowing the catch must not reopen the fail-open hole: anything
        that is not a database error is still a denial, never a free seat."""

        def broken(db, user_id, capability, context):
            raise ValueError("bad plan data")

        monkeypatch.setattr(hooks, "_capability_hooks", [broken])
        with pytest.raises(hooks.CapabilityDenied):
            hooks.check_capability(test_db, uuid4(), "collab.team_seat", {})

    def test_register_returns_fn(self, monkeypatch):
        monkeypatch.setattr(hooks, "_capability_hooks", [])

        @hooks.register_capability_hook
        def hook(db, user_id, capability, context):
            return None

        assert hooks._capability_hooks == [hook]


class TestProjectGrants:
    def test_only_admins_grant(self, test_db, test_user, other, project):
        with pytest.raises(AccessDenied):
            collab_queries.create_project_grant(
                test_db,
                other.id,
                project,
                principal_type="user",
                principal_id=other.id,
                role="viewer",
            )
        grant = collab_queries.create_project_grant(
            test_db,
            test_user.id,
            project,
            principal_type="user",
            principal_id=other.id,
            role="admin",
        )
        assert grant.scopes == ["tasks", "sessions"]
        # An admin grantee can grant too.
        third = _user(test_db, "third@example.com")
        collab_queries.create_project_grant(
            test_db,
            other.id,
            project,
            principal_type="user",
            principal_id=third.id,
            role="viewer",
            scopes=["tasks"],
        )
        assert (
            access.project_role(test_db, third.id, project, grant_scope="tasks")
            == "viewer"
        )
        assert (
            access.project_role(test_db, third.id, project, grant_scope="sessions")
            is None
        )
        assert (
            len(collab_queries.list_project_grants(test_db, test_user.id, project)) == 2
        )

    def test_validation(self, test_db, test_user, other, project):
        inbox = get_or_create_inbox(test_db, test_user.id)
        with pytest.raises(GrantError):
            collab_queries.create_project_grant(
                test_db,
                test_user.id,
                inbox,
                principal_type="user",
                principal_id=other.id,
                role="viewer",
            )
        with pytest.raises(GrantError):
            collab_queries.create_project_grant(
                test_db,
                test_user.id,
                project,
                principal_type="user",
                principal_id=test_user.id,
                role="viewer",
            )
        with pytest.raises(GrantError):
            collab_queries.create_project_grant(
                test_db,
                test_user.id,
                project,
                principal_type="user",
                principal_id=other.id,
                role="viewer",
                scopes=["nope"],
            )
        with pytest.raises(GrantError):
            collab_queries.create_project_grant(
                test_db,
                test_user.id,
                project,
                principal_type="team",
                principal_id=uuid4(),
                role="viewer",
            )
        collab_queries.create_project_grant(
            test_db,
            test_user.id,
            project,
            principal_type="user",
            principal_id=other.id,
            role="viewer",
        )
        with pytest.raises(GrantError):  # duplicate
            collab_queries.create_project_grant(
                test_db,
                test_user.id,
                project,
                principal_type="user",
                principal_id=other.id,
                role="editor",
            )

    def test_write_grants_are_metered_read_grants_are_free(
        self, test_db, test_user, other, project, monkeypatch
    ):
        seen = []
        monkeypatch.setattr(
            hooks,
            "_capability_hooks",
            [lambda db, u, cap, ctx: seen.append((u, cap, ctx)) or "seat required"],
        )
        # viewer / commenter: never metered (D-A).
        collab_queries.create_project_grant(
            test_db,
            test_user.id,
            project,
            principal_type="user",
            principal_id=other.id,
            role="commenter",
        )
        assert seen == []
        third = _user(test_db, "third@example.com")
        with pytest.raises(hooks.CapabilityDenied):
            collab_queries.create_project_grant(
                test_db,
                test_user.id,
                project,
                principal_type="user",
                principal_id=third.id,
                role="editor",
            )
        (payer, capability, context) = seen[0]
        assert payer == test_user.id  # owner-pays
        assert capability == hooks.CAPABILITY_GRANT_WRITE
        assert context["role"] == "editor"
        # A team principal rides on its team's seats: not metered here.
        team = _team(test_db, (test_user, "owner", "active"))
        collab_queries.create_project_grant(
            test_db,
            test_user.id,
            project,
            principal_type="team",
            principal_id=team.id,
            role="editor",
        )
        assert len(seen) == 1

    def test_email_grant_attaches_at_signup(self, test_db, test_user, project):
        grant = collab_queries.create_project_grant(
            test_db,
            test_user.id,
            project,
            principal_type="user",
            invited_email="Later@Example.com",
            role="viewer",
        )
        assert grant.principal_id is None
        newcomer = _user(test_db, "later@example.com")
        assert access.project_role(test_db, newcomer.id, project) is None
        assert collab_queries.attach_pending_grants(test_db, newcomer) == 1
        assert access.project_role(test_db, newcomer.id, project) == "viewer"

    def test_delete_grant(self, test_db, test_user, other, project):
        grant = collab_queries.create_project_grant(
            test_db,
            test_user.id,
            project,
            principal_type="user",
            principal_id=other.id,
            role="viewer",
        )
        with pytest.raises(AccessDenied):
            collab_queries.delete_project_grant(test_db, other.id, project, grant.id)
        assert collab_queries.delete_project_grant(
            test_db, test_user.id, project, grant.id
        )
        assert access.project_role(test_db, other.id, project) is None


class TestLabelsAndTasksUnderTheLens:
    def test_label_visibility_and_vocabulary(self, test_db, test_user, other, project):
        mine = task_queries.create_label(test_db, test_user.id, "mine", "#ff0000")
        theirs = task_queries.create_label(test_db, other.id, "theirs", "#00ff00")
        team = _team(test_db, (other, "member", "active"))
        team_label = task_queries.create_label(
            test_db, other.id, "team", "#0000ff", team_id=team.id
        )
        with pytest.raises(task_queries.TeamNotFoundError):
            task_queries.create_label(
                test_db, test_user.id, "x", "#000000", team_id=team.id
            )

        # Sharing lens: personal + my teams'.
        assert {
            label.id
            for label in task_queries.list_labels(test_db, other.id, sharing=True)
        } == {theirs.id, team_label.id}
        # Owner-only lens: personal only.
        assert {label.id for label in task_queries.list_labels(test_db, other.id)} == {
            theirs.id
        }
        # A project's vocabulary is its owner's, visible to any viewer of it.
        _grant(test_db, project, "user", other.id, "viewer")
        assert {
            label.id
            for label in task_queries.list_labels(
                test_db, other.id, sharing=True, project_id=project.id
            )
        } == {mine.id}
        with pytest.raises(task_queries.ProjectNotFoundError):
            task_queries.list_labels(
                test_db,
                _user(test_db, "x@example.com").id,
                sharing=True,
                project_id=project.id,
            )
        # Editing: mine, or my team's; never another user's personal label.
        assert (
            task_queries.update_label(
                test_db, other.id, mine.id, {"name": "n"}, sharing=True
            )
            is None
        )
        assert (
            task_queries.update_label(
                test_db, other.id, team_label.id, {"name": "n"}, sharing=True
            )
            is not None
        )
        assert (
            task_queries.delete_label(
                test_db, test_user.id, team_label.id, sharing=True
            )
            is False
        )

    def test_editor_attaches_owner_vocabulary(self, test_db, test_user, other, project):
        mine = task_queries.create_label(test_db, test_user.id, "mine", "#ff0000")
        theirs = task_queries.create_label(test_db, other.id, "theirs", "#00ff00")
        _grant(test_db, project, "user", other.id, "editor")
        task = task_queries.create_task(
            test_db,
            other.id,
            "t",
            project_id=project.id,
            label_ids=[mine.id, theirs.id],
            sharing=True,
        )
        assert {label.id for label in task.labels} == {mine.id, theirs.id}
        # The task belongs to the project owner, whoever created it.
        assert task.user_id == test_user.id
        # …so the owner's own (owner-only) lens still sees it.
        assert task_queries.get_task(test_db, test_user.id, task.id) is not None
        # and the CLI lens for the editor does NOT (sharing-unaware).
        assert task_queries.get_task(test_db, other.id, task.id) is None

    def test_owner_only_lens_never_widens(self, test_db, test_user, other, project):
        _grant(test_db, project, "user", other.id, "admin")
        task = task_queries.create_task(
            test_db, test_user.id, "t", project_id=project.id
        )
        assert task_queries.list_tasks(test_db, other.id) == []
        assert task_queries.resolve_task(test_db, other.id, str(task.id)) is None
        with pytest.raises(task_queries.ProjectNotFoundError):
            task_queries.create_task(test_db, other.id, "x", project_id=project.id)
        assert (
            task_queries.update_task(test_db, other.id, task.id, {"title": "x"}) is None
        )
        assert task_queries.delete_task(test_db, other.id, task.id) is False
        assert (
            task_queries.update_project(test_db, other.id, project.id, {"name": "x"})
            is None
        )
        assert project.id not in {
            p.id for p in task_queries.list_projects(test_db, other.id)
        }

    def test_identifier_prefers_own_project(self, test_db, test_user, other):
        mine = task_queries.create_project(test_db, other.id, name="Vicoa")
        theirs = task_queries.create_project(test_db, test_user.id, name="Vicoa")
        my_task = task_queries.create_task(test_db, other.id, "a", project_id=mine.id)
        their_task = task_queries.create_task(
            test_db, test_user.id, "b", project_id=theirs.id
        )
        assert mine.key == theirs.key == "VIC"  # separate owner namespaces
        _grant(test_db, theirs, "user", other.id, "viewer")
        found = task_queries.resolve_task(test_db, other.id, "VIC-1", sharing=True)
        assert found is not None and found.id == my_task.id
        found = task_queries.resolve_task(
            test_db, other.id, str(their_task.id), sharing=True
        )
        assert found is not None and found.id == their_task.id

    def test_move_between_owners_reassigns_owner(
        self, test_db, test_user, other, project
    ):
        _grant(test_db, project, "user", other.id, "editor")
        theirs = task_queries.create_project(test_db, other.id, name="Theirs")
        task = task_queries.create_task(test_db, other.id, "t", project_id=theirs.id)
        assert task.user_id == other.id
        moved = task_queries.update_task(
            test_db, other.id, task.id, {"project_id": project.id}, sharing=True
        )
        assert moved is not None
        assert moved.user_id == test_user.id
        assert moved.project_id == project.id
        # Moving *to* a project you can only view is refused.
        viewer_only = task_queries.create_project(test_db, test_user.id, name="RO")
        _grant(test_db, viewer_only, "user", other.id, "viewer")
        with pytest.raises(AccessDenied):
            task_queries.update_task(
                test_db,
                other.id,
                moved.id,
                {"project_id": viewer_only.id},
                sharing=True,
            )

    def test_assignee_must_have_standing(self, test_db, test_user, other, project):
        stranger = _user(test_db, "stranger@example.com")
        task = task_queries.create_task(
            test_db, test_user.id, "t", project_id=project.id
        )
        with pytest.raises(task_queries.AssigneeNotFoundError):
            task_queries.update_task(
                test_db,
                test_user.id,
                task.id,
                {"assignee_type": "user", "assignee_id": other.id},
                sharing=True,
            )
        _grant(test_db, project, "user", other.id, "viewer")
        task_queries.update_task(
            test_db,
            test_user.id,
            task.id,
            {"assignee_type": "user", "assignee_id": other.id},
            sharing=True,
        )
        with pytest.raises(task_queries.AssigneeNotFoundError):
            task_queries.update_task(
                test_db,
                test_user.id,
                task.id,
                {"assignee_type": "user", "assignee_id": stranger.id},
                sharing=True,
            )

    def test_team_key_namespace_is_separate(self, test_db, test_user, other):
        team = _team(
            test_db, (test_user, "owner", "active"), (other, "member", "active")
        )
        personal = task_queries.create_project(test_db, test_user.id, name="Vicoa")
        task_queries.create_task(test_db, test_user.id, "a", project_id=personal.id)
        team_project = task_queries.create_project(test_db, test_user.id, name="Vicoa")
        team_project.team_id = team.id
        test_db.commit()
        task_queries.create_task(
            test_db, other.id, "b", project_id=team_project.id, sharing=True
        )
        assert personal.key == "VIC"
        assert team_project.key == "VIC"  # a different owner ⇒ no collision


class TestAccountDeletionSweeps:
    def test_grants_to_user_and_sole_member_teams_go(
        self, test_db, test_user, other, project
    ):
        _grant(test_db, project, "user", other.id, "viewer")
        solo = _team(test_db, (other, "owner", "active"))
        shared = _team(
            test_db, (other, "owner", "active"), (test_user, "member", "active")
        )
        _grant(test_db, project, "team", solo.id, "viewer")
        solo_project = task_queries.create_project(test_db, other.id, name="SoloTeam")
        solo_project.team_id = solo.id
        test_db.commit()

        # Snapshot ids: the ORM instances expire on commit and the rows are
        # about to be gone.
        other_id, solo_id, shared_id = other.id, solo.id, shared.id
        delete_user_account(test_db, other_id)

        assert (
            test_db.query(ProjectGrant)
            .filter(ProjectGrant.principal_id == other_id)
            .count()
            == 0
        )
        assert (
            test_db.query(ProjectGrant)
            .filter(ProjectGrant.principal_id == solo_id)
            .count()
            == 0
        )
        assert test_db.query(Team).filter(Team.id == solo_id).count() == 0
        # A team with someone else still in it survives; only the row goes.
        assert test_db.query(Team).filter(Team.id == shared_id).count() == 1
        assert (
            test_db.query(TeamMember).filter(TeamMember.user_id == other_id).count()
            == 0
        )
        # The deleted user's own rows cascade as before.
        assert test_db.query(Project).filter(Project.user_id == other_id).count() == 0
        assert test_db.query(Task).filter(Task.user_id == other_id).count() == 0
        assert (
            test_db.query(TaskLabel).filter(TaskLabel.user_id == other_id).count() == 0
        )


# --- Regressions ---------------------------------------------------------------
#
# One class per defect found reviewing the access-core PR. Each test fails on
# the pre-fix code.


class TestOwnershipChangingMoveNeedsOwner:
    """An `editor` grantee must not be able to move a task off the owner's
    board and onto their own — ownership follows the project, so the task and
    its whole history would leave the owner's `visible_project_select` for
    good."""

    def test_editor_cannot_move_task_into_own_inbox(
        self, test_db, test_user, other, project
    ):
        _grant(test_db, project, "user", other.id, "editor")
        task = task_queries.create_task(
            test_db, test_user.id, project_id=project.id, title="Mine", sharing=False
        )
        with pytest.raises(AccessDenied):
            task_queries.update_task(
                test_db, other.id, task.id, {"project_id": None}, sharing=True
            )
        test_db.expire_all()
        assert test_db.get(Task, task.id).user_id == test_user.id

    def test_editor_cannot_move_task_into_own_project(
        self, test_db, test_user, other, project
    ):
        """`editor` on the *destination* is satisfied trivially by any project
        the grantee owns, so the inbox is not the only route."""
        _grant(test_db, project, "user", other.id, "editor")
        mine = task_queries.create_project(test_db, other.id, name="Bob's board")
        task = task_queries.create_task(
            test_db, test_user.id, project_id=project.id, title="Mine", sharing=False
        )
        with pytest.raises(AccessDenied):
            task_queries.update_task(
                test_db, other.id, task.id, {"project_id": mine.id}, sharing=True
            )
        test_db.expire_all()
        assert test_db.get(Task, task.id).project_id == project.id

    def test_owner_can_still_move_their_own_task_to_inbox(
        self, test_db, test_user, project
    ):
        task = task_queries.create_task(
            test_db, test_user.id, project_id=project.id, title="Mine", sharing=False
        )
        moved = task_queries.update_task(
            test_db, test_user.id, task.id, {"project_id": None}, sharing=True
        )
        assert moved is not None
        assert moved.project_id == get_or_create_inbox(test_db, test_user.id).id

    def test_editor_can_still_move_within_the_owners_projects(
        self, test_db, test_user, other, project
    ):
        """The ownership boundary is the line, not the move itself."""
        second = task_queries.create_project(test_db, test_user.id, name="Other board")
        _grant(test_db, project, "user", other.id, "editor")
        _grant(test_db, second, "user", other.id, "editor")
        task = task_queries.create_task(
            test_db, test_user.id, project_id=project.id, title="Mine", sharing=False
        )
        moved = task_queries.update_task(
            test_db, other.id, task.id, {"project_id": second.id}, sharing=True
        )
        assert moved is not None
        assert moved.project_id == second.id
        assert moved.user_id == test_user.id


class TestBlankEmailIsNeverAPrincipal:
    """`users.email` is uniquely indexed, so at most one account can carry a
    blank address (prod: exactly one of 19,681). That incidental uniqueness on
    *another table* is the only thing standing between a blank
    `invited_email` and one account resolving to another's membership row, so
    the blank is refused at the writer and at the schema instead."""

    def test_create_team_stores_null_not_blank_for_a_blank_email_owner(self, test_db):
        owner = _user(test_db, "")
        team = collab_queries.create_team(test_db, owner, name="Relay")
        row = (
            test_db.query(TeamMember)
            .filter(TeamMember.team_id == team.id, TeamMember.user_id == owner.id)
            .one()
        )
        assert row.invited_email is None

    def test_grant_rejects_a_whitespace_only_email(self, test_db, test_user, project):
        """`not "   "` is False, so this used to pass the "principal required"
        guard and then be stored as '' by `.strip()`."""
        with pytest.raises(GrantError):
            collab_queries.create_project_grant(
                test_db,
                test_user.id,
                project,
                principal_type="user",
                invited_email="   ",
                role="viewer",
            )

    def test_blank_email_account_claims_no_pending_grants(
        self, test_db, test_user, project
    ):
        blank = _user(test_db, "")
        test_db.add(
            ProjectGrant(
                project_id=project.id,
                principal_type="user",
                principal_id=None,
                invited_email="someone@example.com",
                role="viewer",
                scopes=["tasks"],
            )
        )
        test_db.commit()
        assert collab_queries.attach_pending_grants(test_db, blank) == 0

    def test_schema_refuses_a_blank_invited_email(self, test_db, test_user, project):
        from sqlalchemy.exc import IntegrityError

        team = collab_queries.create_team(test_db, test_user, name="Guarded")
        test_db.add(
            TeamMember(
                team_id=team.id,
                user_id=None,
                invited_email="  ",
                role="member",
                status="invited",
            )
        )
        with pytest.raises(IntegrityError):
            test_db.commit()
        test_db.rollback()

    def test_schema_refuses_a_principal_less_grant(self, test_db, project):
        from sqlalchemy.exc import IntegrityError

        test_db.add(
            ProjectGrant(
                project_id=project.id,
                principal_type="user",
                principal_id=None,
                invited_email=None,
                role="viewer",
                scopes=["tasks"],
            )
        )
        with pytest.raises(IntegrityError):
            test_db.commit()
        test_db.rollback()


class TestSurvivingTeamKeepsAnOwner:
    """`delete_user_account` must not leave a team alive without an active
    owner: `_payer_id` has nobody to bill and `require_team(minimum="owner")`
    can never be satisfied, so the team is unadministerable for good."""

    def test_last_owner_leaving_promotes_the_longest_standing_member(
        self, test_db, test_user
    ):
        alice, bob = _user(test_db, "a@example.com"), _user(test_db, "b@example.com")
        team = _team(test_db, (alice, "owner", "active"), (bob, "member", "active"))
        team_id = team.id
        delete_user_account(test_db, alice.id)

        assert test_db.query(Team).filter(Team.id == team_id).count() == 1
        survivor = test_db.query(TeamMember).filter(TeamMember.team_id == team_id).one()
        assert survivor.user_id == bob.id
        assert survivor.role == "owner"

    def test_promotion_prefers_an_admin_over_a_member(self, test_db):
        alice = _user(test_db, "a@example.com")
        member = _user(test_db, "m@example.com")
        admin = _user(test_db, "adm@example.com")
        team = _team(
            test_db,
            (alice, "owner", "active"),
            (member, "member", "active"),
            (admin, "admin", "active"),
        )
        team_id, admin_id = team.id, admin.id
        delete_user_account(test_db, alice.id)

        owners = (
            test_db.query(TeamMember)
            .filter(TeamMember.team_id == team_id, TeamMember.role == "owner")
            .all()
        )
        assert [o.user_id for o in owners] == [admin_id]

    def test_an_existing_co_owner_is_left_alone(self, test_db):
        alice, bob = _user(test_db, "a@example.com"), _user(test_db, "b@example.com")
        carol = _user(test_db, "c@example.com")
        team = _team(
            test_db,
            (alice, "owner", "active"),
            (bob, "owner", "active"),
            (carol, "member", "active"),
        )
        team_id, bob_id = team.id, bob.id
        delete_user_account(test_db, alice.id)

        owners = (
            test_db.query(TeamMember)
            .filter(TeamMember.team_id == team_id, TeamMember.role == "owner")
            .all()
        )
        assert [o.user_id for o in owners] == [bob_id]

    def test_team_whose_only_other_member_never_accepted_is_deleted(self, test_db):
        """An `invited` member is not an active one: keeping the team would
        leave it ownerless. It goes, and the invite with it."""
        alice, bob = _user(test_db, "a@example.com"), _user(test_db, "b@example.com")
        team = _team(test_db, (alice, "owner", "active"), (bob, "member", "invited"))
        team_id = team.id
        delete_user_account(test_db, alice.id)

        assert test_db.query(Team).filter(Team.id == team_id).count() == 0
        assert (
            test_db.query(TeamMember).filter(TeamMember.team_id == team_id).count() == 0
        )

    def test_a_team_you_were_removed_from_is_not_yours_to_delete(self, test_db):
        alice, bob = _user(test_db, "a@example.com"), _user(test_db, "b@example.com")
        team = _team(test_db, (bob, "owner", "removed"), (alice, "member", "removed"))
        # Nobody active at all, but Alice was removed — the team is not hers.
        team_id = team.id
        delete_user_account(test_db, alice.id)
        assert test_db.query(Team).filter(Team.id == team_id).count() == 1


class TestPayerResolution:
    def test_ownerless_team_raises_instead_of_asserting(self, test_db, test_user):
        """A bare `assert` here is stripped under `python -O`, which would hand
        `None` to `check_capability` as the payer id — a silent mis-meter."""
        team = Team(name="Orphan", slug=f"orphan-{uuid4().hex[:8]}")
        team.created_by_user_id = None
        test_db.add(team)
        test_db.commit()
        with pytest.raises(collab_queries.TeamStateError):
            collab_queries._payer_id(test_db, team)

    def test_payer_still_resolves_after_the_owner_deletes_their_account(self, test_db):
        """The promotion above is what keeps this answerable."""
        alice, bob = _user(test_db, "a@example.com"), _user(test_db, "b@example.com")
        team = _team(test_db, (alice, "owner", "active"), (bob, "member", "active"))
        team_id, bob_id = team.id, bob.id
        delete_user_account(test_db, alice.id)

        test_db.expire_all()
        assert collab_queries._payer_id(test_db, test_db.get(Team, team_id)) == bob_id


class TestInviteLinkRedemptionIsSerialized:
    def test_one_use_link_admits_exactly_one_of_two_racing_clients(
        self, test_db, test_user, monkeypatch
    ):
        """Two real sessions, two threads, one `max_uses=1` link.

        `_seat_count` is slowed to widen the read-check-write window: without
        the row lock both clients read `uses = 0`, both pass, and both join.
        """
        import threading
        import time

        from sqlalchemy.orm import sessionmaker

        team = collab_queries.create_team(test_db, test_user, name="Race")
        invite = collab_queries.create_invite_link(
            test_db, test_user.id, team.id, role="member", max_uses=1
        )
        token, invite_id = invite.token, invite.id
        racers = [
            _user(test_db, "racer-a@example.com").id,
            _user(test_db, "racer-b@example.com").id,
        ]

        real_seat_count = collab_queries._seat_count

        def slow_seat_count(db, team_id):
            time.sleep(0.4)
            return real_seat_count(db, team_id)

        monkeypatch.setattr(collab_queries, "_seat_count", slow_seat_count)

        Session = sessionmaker(bind=test_db.get_bind())
        outcomes: list[str] = []
        guard = threading.Lock()

        def redeem(user_id):
            session = Session()
            try:
                racer = session.get(User, user_id)
                assert racer is not None
                collab_queries.accept_invite_link(session, racer, token)
                result = "joined"
            except collab_queries.InviteNotFoundError:
                result = "rejected"
            finally:
                session.close()
            with guard:
                outcomes.append(result)

        threads = [threading.Thread(target=redeem, args=(u,)) for u in racers]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert sorted(outcomes) == ["joined", "rejected"]
        test_db.expire_all()
        assert test_db.get(TeamInvite, invite_id).uses == 1
        assert (
            test_db.query(TeamMember)
            .filter(TeamMember.team_id == team.id, TeamMember.status == "active")
            .count()
            == 2  # the owner plus exactly one racer
        )

    def test_uses_increments_per_redemption(self, test_db, test_user):
        """SQL-side increment: a Python-side `uses + 1` writes back a stale
        read and silently under-counts."""
        team = collab_queries.create_team(test_db, test_user, name="Counted")
        invite = collab_queries.create_invite_link(
            test_db, test_user.id, team.id, role="member", max_uses=3
        )
        invite_id = invite.token, invite.id
        for email in ("one@example.com", "two@example.com"):
            collab_queries.accept_invite_link(
                test_db, _user(test_db, email), invite.token
            )
        test_db.expire_all()
        assert test_db.get(TeamInvite, invite_id[1]).uses == 2


class TestGrantAdminIsNotPerScope:
    """A `tasks`-only admin must not be able to administer grants — otherwise
    it writes itself a second grant with `scopes=["sessions"]` and reads every
    session on the board, which is the boundary the two-lens design rests on."""

    def test_scope_limited_admin_cannot_widen_its_own_scope(
        self, test_db, test_user, other, project
    ):
        _grant(test_db, project, "user", other.id, "admin", scopes=["tasks"])
        with pytest.raises(AccessDenied):
            collab_queries.create_project_grant(
                test_db,
                other.id,
                project,
                principal_type="user",
                principal_id=other.id,
                role="admin",
                scopes=["sessions"],
            )

    def test_scope_limited_admin_cannot_list_or_delete_grants(
        self, test_db, test_user, other, project
    ):
        _grant(test_db, project, "user", other.id, "admin", scopes=["tasks"])
        with pytest.raises(AccessDenied):
            collab_queries.list_project_grants(test_db, other.id, project)

    def test_unrestricted_admin_still_manages_grants(
        self, test_db, test_user, other, project
    ):
        _grant(test_db, project, "user", other.id, "admin")
        third = _user(test_db, "third@example.com")
        grant = collab_queries.create_project_grant(
            test_db,
            other.id,
            project,
            principal_type="user",
            principal_id=third.id,
            role="viewer",
        )
        assert grant.principal_id == third.id
        assert collab_queries.list_project_grants(test_db, other.id, project)

    def test_owner_is_unaffected(self, test_db, test_user, other, project):
        grant = collab_queries.create_project_grant(
            test_db,
            test_user.id,
            project,
            principal_type="user",
            principal_id=other.id,
            role="editor",
        )
        assert grant.role == "editor"
