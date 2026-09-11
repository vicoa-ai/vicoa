"""The authz matrix (collaboration plan §4): every (standing × endpoint) pair.

One world — an owner with a project, a task on it, a session in it, a
machine, an automation and an API key — and a *subject* who holds exactly one
kind of standing towards that owner. For every endpoint the human dashboard
exposes, the matrix asserts what that subject gets:

* ``invisible`` — 404, or a list that does not contain the object. The
  subject cannot tell the object exists.
* ``forbidden``  — 403. The subject can see it but their role is too low.
* ``allowed``    — 2xx.

A missed enforcement point is a cross-tenant data leak, so this is the single
test that must go red when a query forgets its lens. It deliberately drives
the real HTTP surface, not the query layer.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.auth.dependencies import (
    get_current_claims,
    get_current_user,
    get_optional_current_user,
)
from backend.main import app
from shared import access, storage
from shared.auth.tokens import TokenClaims
from shared.database import (
    AgentInstance,
    AgentType,
    APIKey,
    Automation,
    Machine,
    Message,
    Project,
    ProjectGrant,
    SenderType,
    Task,
    Team,
    TeamMember,
    User,
    UserInstanceAccess,
    get_or_create_inbox,
)
from shared.database.enums import AgentStatus, InstanceAccessLevel

# ---------------------------------------------------------------------------
# Subjects: every distinct standing a second user can have towards the owner.
#
# `tasks` / `sessions` are the effective role the subject should resolve to
# in each area (None = invisible). `project` is the role for project-level
# settings, which any grant scope confers.
# ---------------------------------------------------------------------------

Standing = tuple[str | None, str | None, str | None]  # (tasks, sessions, project)

SUBJECTS: dict[str, Standing] = {
    "stranger": (None, None, None),
    "viewer": ("viewer", "viewer", "viewer"),
    "commenter": ("commenter", "commenter", "commenter"),
    "editor": ("editor", "editor", "editor"),
    "admin": ("admin", "admin", "admin"),
    "owner": ("owner", "owner", "owner"),
    # A grant held by a team the subject is an ACTIVE member of.
    "team_grant_editor": ("editor", "editor", "editor"),
    # The same grant, but the subject's membership is still pending / was removed.
    "team_grant_editor_invited": (None, None, None),
    "team_grant_editor_removed": (None, None, None),
    # The project is team-owned; the subject's team role maps onto it.
    "team_project_member": ("editor", "editor", "editor"),
    "team_project_admin": ("admin", "admin", "admin"),
    "team_project_owner": ("owner", "owner", "owner"),
    # Scoped grants: one area is invisible, the other resolves normally.
    "sessions_only_editor": (None, "editor", "editor"),
    "tasks_only_admin": ("admin", None, "admin"),
    # Legacy per-session share: READ ⇒ viewer on that session only, no project.
    "session_share_read": (None, "viewer", None),
    "session_share_write": (None, "editor", None),
}

RANK = access.ROLE_RANK


def expected_outcome(subject_role: str | None, minimum: str) -> str:
    if subject_role is None:
        return "invisible"
    if RANK[subject_role] < RANK[minimum]:
        return "forbidden"
    return "allowed"


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


@dataclass
class World:
    owner: User
    subject: User
    project: Project
    task: Task
    instance: AgentInstance
    queued_message: Message
    owner_machine: Machine
    subject_machine: Machine
    automation: Automation
    api_key: APIKey
    share: UserInstanceAccess  # an existing share row on the instance, for DELETE


def _user(db, email: str, name: str) -> User:
    user = User(
        id=uuid4(),
        email=email,
        display_name=name,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    return user


def _machine(db, user: User, name: str) -> Machine:
    machine = Machine(user_id=user.id, display_name=name, hostname=f"{name}.local")
    db.add(machine)
    db.flush()
    return machine


def _team(db, name: str, members: list[tuple[User, str, str]]) -> Team:
    team = Team(name=name, slug=name.lower().replace(" ", "-"))
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
                joined_at=datetime.now(timezone.utc) if status == "active" else None,
            )
        )
    db.flush()
    return team


def _grant(
    db,
    project: Project,
    *,
    principal_type: str,
    principal_id: UUID,
    role: str,
    scopes: list[str] | None = None,
    granted_by: User,
) -> None:
    db.add(
        ProjectGrant(
            project_id=project.id,
            principal_type=principal_type,
            principal_id=principal_id,
            role=role,
            scopes=scopes or ["tasks", "sessions"],
            granted_by_user_id=granted_by.id,
        )
    )
    db.flush()


@pytest.fixture
def world(test_db, test_user, request) -> World:
    """Build the owner's world and give `subject` the standing named by the
    parametrized `subject` id."""
    subject_kind: str = request.param
    db = test_db
    owner = test_user
    get_or_create_inbox(db, owner.id)

    project = Project(
        user_id=owner.id,
        name="Shared Board",
        key="SHB",
        task_counter=1,
        # So GET /icon has bytes to serve (storage is stubbed below).
        icon_image_uri="/api/v1/projects/x/icon",
        icon_source="user",
    )
    db.add(project)
    db.flush()
    task = Task(user_id=owner.id, project_id=project.id, number=1, title="Do the thing")
    db.add(task)

    agent_type = AgentType(user_id=owner.id, name="claude code", is_active=True)
    db.add(agent_type)
    db.flush()
    instance = AgentInstance(
        agent_type_id=agent_type.id,
        user_id=owner.id,
        project_id=project.id,
        status=AgentStatus.ACTIVE,
        started_at=datetime.now(timezone.utc),
    )
    db.add(instance)
    db.flush()
    queued = Message(
        agent_instance_id=instance.id,
        sender_type=SenderType.USER,
        sender_user_id=owner.id,
        content="queued",
        requires_user_input=False,
        message_metadata={"queue": {"status": "queued"}},
    )
    db.add(queued)

    owner_machine = _machine(db, owner, "owner-box")
    automation = Automation(
        user_id=owner.id,
        title="nightly",
        prompt="do it",
        machine_id=owner_machine.id,
        directory="/tmp",
        session_config={"agent": "claude"},
        schedule_kind="once",
    )
    db.add(automation)
    api_key = APIKey(
        user_id=owner.id, name="cli", api_key_hash="hash", api_key="unused"
    )
    db.add(api_key)

    # A pre-existing share on the instance, so DELETE .../access/{id} has a
    # target for every subject.
    bystander = _user(db, "bystander@example.com", "Bystander")
    share = UserInstanceAccess(
        agent_instance_id=instance.id,
        shared_email=bystander.email,
        user_id=bystander.id,
        access=InstanceAccessLevel.READ,
        granted_by_user_id=owner.id,
    )
    db.add(share)

    if subject_kind == "owner":
        subject = owner
    else:
        subject = _user(db, "subject@example.com", "Subject")
    subject_machine = _machine(db, subject, "subject-box")

    if subject_kind in ("viewer", "commenter", "editor", "admin"):
        _grant(
            db,
            project,
            principal_type="user",
            principal_id=subject.id,
            role=subject_kind,
            granted_by=owner,
        )
    elif subject_kind == "sessions_only_editor":
        _grant(
            db,
            project,
            principal_type="user",
            principal_id=subject.id,
            role="editor",
            scopes=["sessions"],
            granted_by=owner,
        )
    elif subject_kind == "tasks_only_admin":
        _grant(
            db,
            project,
            principal_type="user",
            principal_id=subject.id,
            role="admin",
            scopes=["tasks"],
            granted_by=owner,
        )
    elif subject_kind.startswith("team_grant_editor"):
        status = {"": "active", "_invited": "invited", "_removed": "removed"}[
            subject_kind.removeprefix("team_grant_editor")
        ]
        team = _team(db, "Grantees", [(subject, "member", status)])
        _grant(
            db,
            project,
            principal_type="team",
            principal_id=team.id,
            role="editor",
            granted_by=owner,
        )
    elif subject_kind.startswith("team_project_"):
        subject_role = subject_kind.removeprefix("team_project_")
        owner_role = "member" if subject_role == "owner" else "owner"
        team = _team(
            db,
            "Crew",
            [(owner, owner_role, "active"), (subject, subject_role, "active")],
        )
        project.team_id = team.id
    elif subject_kind.startswith("session_share_"):
        level = (
            InstanceAccessLevel.WRITE
            if subject_kind.endswith("write")
            else InstanceAccessLevel.READ
        )
        db.add(
            UserInstanceAccess(
                agent_instance_id=instance.id,
                shared_email=subject.email,
                user_id=subject.id,
                access=level,
                granted_by_user_id=owner.id,
            )
        )
    elif subject_kind not in ("stranger", "owner"):
        raise AssertionError(f"unknown subject {subject_kind}")

    db.commit()
    for obj in (project, task, instance, queued, share):
        db.refresh(obj)
    return World(
        owner=owner,
        subject=subject,
        project=project,
        task=task,
        instance=instance,
        queued_message=queued,
        owner_machine=owner_machine,
        subject_machine=subject_machine,
        automation=automation,
        api_key=api_key,
        share=share,
    )


@pytest.fixture
def subject_client(client, world) -> Iterator[TestClient]:
    """`client` authenticated as the world's subject."""
    subject = world.subject

    def override_user():
        return subject

    def override_claims():
        return TokenClaims(
            user_id=subject.id, email=subject.email, display_name=subject.display_name
        )

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_optional_current_user] = override_user
    app.dependency_overrides[get_current_claims] = override_claims
    try:
        yield client
    finally:
        for dep in (get_current_user, get_optional_current_user, get_current_claims):
            app.dependency_overrides.pop(dep, None)


@pytest.fixture(autouse=True)
def _quiet_side_effects(monkeypatch):
    """Broadcasts and S3 are out of scope here; make them inert."""
    monkeypatch.setattr("backend.api.agents.post_broadcast", lambda *a, **k: None)
    monkeypatch.setattr(storage, "delete_object", lambda key: None)
    monkeypatch.setattr(storage, "download_object", lambda key: (b"png", "image/png"))
    monkeypatch.setattr(
        "backend.api.agents.update_session_title_if_needed", lambda **k: None
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Endpoint:
    name: str
    area: str  # 'tasks' | 'sessions' | 'project' | 'owner_only'
    minimum: str
    call: Callable[[TestClient, World], httpx.Response]
    # For list endpoints: extract the ids the response exposes so "invisible"
    # can be asserted as absence rather than as a 404.
    listed_ids: Callable[[httpx.Response], set[str]] | None = None


def _ids(key: str = "id") -> Callable[[httpx.Response], set[str]]:
    def extract(response: httpx.Response) -> set[str]:
        body = response.json()
        items = body["items"] if isinstance(body, dict) and "items" in body else body
        return {str(item[key]) for item in items}

    return extract


ENDPOINTS: list[Endpoint] = [
    # --- project ------------------------------------------------------------
    Endpoint(
        "GET /projects",
        "project",
        "viewer",
        lambda c, w: c.get("/api/v1/projects"),
        listed_ids=_ids(),
    ),
    Endpoint(
        "PATCH /projects/{id}",
        "project",
        "admin",
        lambda c, w: c.patch(
            f"/api/v1/projects/{w.project.id}", json={"name": "Renamed"}
        ),
    ),
    Endpoint(
        "DELETE /projects/{id}",
        "project",
        "owner",
        lambda c, w: c.delete(f"/api/v1/projects/{w.project.id}"),
    ),
    Endpoint(
        "PUT /projects/{id}/directories",
        "project",
        "admin",
        lambda c, w: c.put(
            f"/api/v1/projects/{w.project.id}/directories",
            json={"machine_id": str(w.subject_machine.id), "local_path": "/src"},
        ),
    ),
    Endpoint(
        "DELETE /projects/{id}/directories/{machine}",
        "project",
        "admin",
        lambda c, w: c.delete(
            f"/api/v1/projects/{w.project.id}/directories/{w.subject_machine.id}"
        ),
    ),
    Endpoint(
        "GET /projects/{id}/icon",
        "project",
        "viewer",
        lambda c, w: c.get(f"/api/v1/projects/{w.project.id}/icon"),
    ),
    Endpoint(
        "DELETE /projects/{id}/icon",
        "project",
        "admin",
        lambda c, w: c.delete(f"/api/v1/projects/{w.project.id}/icon"),
    ),
    # --- tasks ------------------------------------------------------------------
    Endpoint(
        "GET /task-labels?project_id",
        "tasks",
        "viewer",
        lambda c, w: c.get(f"/api/v1/task-labels?project_id={w.project.id}"),
    ),
    Endpoint(
        "GET /tasks",
        "tasks",
        "viewer",
        lambda c, w: c.get("/api/v1/tasks"),
        listed_ids=_ids(),
    ),
    Endpoint(
        "GET /tasks/{id}",
        "tasks",
        "viewer",
        lambda c, w: c.get(f"/api/v1/tasks/{w.task.id}"),
    ),
    Endpoint(
        "GET /tasks/{identifier}",
        "tasks",
        "viewer",
        lambda c, w: c.get("/api/v1/tasks/SHB-1"),
    ),
    Endpoint(
        "GET /tasks/{id}/timeline",
        "tasks",
        "viewer",
        lambda c, w: c.get(f"/api/v1/tasks/{w.task.id}/timeline"),
    ),
    Endpoint(
        "GET /tasks/{id}/sessions",
        "tasks",
        "viewer",
        lambda c, w: c.get(f"/api/v1/tasks/{w.task.id}/sessions"),
    ),
    Endpoint(
        "POST /tasks {project_id}",
        "tasks",
        "editor",
        lambda c, w: c.post(
            "/api/v1/tasks", json={"title": "New", "project_id": str(w.project.id)}
        ),
    ),
    Endpoint(
        "PATCH /tasks/{id}",
        "tasks",
        "editor",
        lambda c, w: c.patch(f"/api/v1/tasks/{w.task.id}", json={"title": "Edited"}),
    ),
    Endpoint(
        "DELETE /tasks/{id}",
        "tasks",
        "editor",
        lambda c, w: c.delete(f"/api/v1/tasks/{w.task.id}"),
    ),
    Endpoint(
        "POST /tasks/{id}/comments",
        "tasks",
        "commenter",
        lambda c, w: c.post(f"/api/v1/tasks/{w.task.id}/comments", json={"body": "hi"}),
    ),
    Endpoint(
        "PUT /tasks/{id}/reactions",
        "tasks",
        "commenter",
        lambda c, w: c.put(
            f"/api/v1/tasks/{w.task.id}/reactions",
            json={"target_type": "task", "target_id": str(w.task.id), "emoji": "👍"},
        ),
    ),
    # --- sessions -----------------------------------------------------------
    Endpoint(
        "GET /agent-instances?scope=all",
        "sessions",
        "viewer",
        lambda c, w: c.get("/api/v1/agent-instances?scope=all"),
        listed_ids=_ids(),
    ),
    Endpoint(
        "GET /agent-instances/{id}",
        "sessions",
        "viewer",
        lambda c, w: c.get(f"/api/v1/agent-instances/{w.instance.id}"),
    ),
    Endpoint(
        "GET /agent-instances/{id}/messages",
        "sessions",
        "viewer",
        lambda c, w: c.get(f"/api/v1/agent-instances/{w.instance.id}/messages"),
    ),
    Endpoint(
        "POST /agent-instances/{id}/messages",
        "sessions",
        "editor",
        lambda c, w: c.post(
            f"/api/v1/agent-instances/{w.instance.id}/messages",
            json={"content": "go on"},
        ),
    ),
    Endpoint(
        "POST /agent-instances/{id}/messages/{mid}/cancel",
        "sessions",
        "editor",
        lambda c, w: c.post(
            f"/api/v1/agent-instances/{w.instance.id}/messages/{w.queued_message.id}/cancel"
        ),
    ),
    Endpoint(
        "PATCH /agent-instances/{id} name",
        "sessions",
        "admin",
        lambda c, w: c.patch(
            f"/api/v1/agent-instances/{w.instance.id}", json={"name": "Renamed"}
        ),
    ),
    Endpoint(
        "PATCH /agent-instances/{id} pinned",
        "sessions",
        "admin",
        lambda c, w: c.patch(
            f"/api/v1/agent-instances/{w.instance.id}", json={"pinned": True}
        ),
    ),
    Endpoint(
        "PUT /agent-instances/{id}/status",
        "sessions",
        "admin",
        lambda c, w: c.put(
            f"/api/v1/agent-instances/{w.instance.id}/status",
            json={"status": "COMPLETED"},
        ),
    ),
    Endpoint(
        "DELETE /agent-instances/{id}",
        "sessions",
        "admin",
        lambda c, w: c.delete(f"/api/v1/agent-instances/{w.instance.id}"),
    ),
    Endpoint(
        "GET /agent-instances/{id}/access",
        "sessions",
        "admin",
        lambda c, w: c.get(f"/api/v1/agent-instances/{w.instance.id}/access"),
    ),
    Endpoint(
        "POST /agent-instances/{id}/access",
        "sessions",
        "admin",
        lambda c, w: c.post(
            f"/api/v1/agent-instances/{w.instance.id}/access",
            json={"email": "third@example.com", "access": "READ"},
        ),
    ),
    Endpoint(
        "DELETE /agent-instances/{id}/access/{aid}",
        "sessions",
        "admin",
        lambda c, w: c.delete(
            f"/api/v1/agent-instances/{w.instance.id}/access/{w.share.id}"
        ),
    ),
    # --- owner-only, permanently (§4 / §10.6) --------------------------------
    # Automations, machines and API keys are never reachable through a grant
    # of any kind — an automation is "run an agent with my credentials on my
    # machine"; sharing it is an authorization trap.
    Endpoint(
        "GET /automations/{id}",
        "owner_only",
        "owner",
        lambda c, w: c.get(f"/api/v1/automations/{w.automation.id}"),
    ),
    Endpoint(
        "GET /automations",
        "owner_only",
        "owner",
        lambda c, w: c.get("/api/v1/automations"),
        listed_ids=_ids(),
    ),
    Endpoint(
        "GET /machines/{id}",
        "owner_only",
        "owner",
        lambda c, w: c.get(f"/api/v1/machines/{w.owner_machine.id}"),
    ),
    Endpoint(
        "DELETE /auth/api-keys/{id}",
        "owner_only",
        "owner",
        lambda c, w: c.delete(f"/api/v1/auth/api-keys/{w.api_key.id}"),
    ),
]

# What each list endpoint should (not) contain for the world's object.
_LISTED_OBJECT: dict[str, Callable[[World], str]] = {
    "GET /projects": lambda w: str(w.project.id),
    "GET /tasks": lambda w: str(w.task.id),
    "GET /agent-instances?scope=all": lambda w: str(w.instance.id),
    "GET /automations": lambda w: str(w.automation.id),
}


def _standing_for(endpoint: Endpoint, standing: Standing) -> str | None:
    tasks, sessions, project = standing
    if endpoint.area == "tasks":
        return tasks
    if endpoint.area == "sessions":
        return sessions
    if endpoint.area == "project":
        return project
    # owner_only: only the literal owner ever resolves — every grant-derived
    # standing, including team-project 'owner', is invisible here.
    return None


@pytest.mark.parametrize("world", list(SUBJECTS), indirect=True, ids=list(SUBJECTS))
@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=[e.name for e in ENDPOINTS])
def test_authz_matrix(
    world: World, subject_client: TestClient, endpoint: Endpoint, request
):
    subject_kind = request.node.callspec.params["world"]
    standing = SUBJECTS[subject_kind]
    if endpoint.area == "owner_only":
        role = "owner" if subject_kind == "owner" else None
    else:
        role = _standing_for(endpoint, standing)
    expected = expected_outcome(role, endpoint.minimum)

    response = endpoint.call(subject_client, world)
    status = response.status_code
    detail = f"{subject_kind} on {endpoint.name}: {status} {response.text}"

    if endpoint.listed_ids is not None:
        assert status == 200, detail
        target = _LISTED_OBJECT[endpoint.name](world)
        present = target in endpoint.listed_ids(response)
        # A list never 403s; a role below the floor still sees the row.
        assert present == (expected != "invisible"), detail
        return

    if expected == "invisible":
        assert status == 404, detail
    elif expected == "forbidden":
        assert status == 403, detail
    else:
        assert 200 <= status < 300, detail


def test_every_dashboard_route_is_in_the_matrix_or_owner_only():
    """A new route on the tasks/agents routers must be classified here. This is
    the guard against "added an endpoint, forgot the lens"."""
    covered = {e.name.split(" ")[1].split("?")[0] for e in ENDPOINTS}
    # Paths on the dashboard routers that carry a project/task/session id and
    # therefore need a standing decision. Anything new lands here → fails.
    from backend.api import agents, tasks

    def paths(router):
        for route in router.routes:
            path = getattr(route, "path", "")
            methods = getattr(route, "methods", set())
            for method in methods:
                yield method, path

    expected_uncovered = {
        # Icon upload needs a multipart body + S3; it shares its guard
        # (`get_accessible_project(minimum="admin")`) with DELETE /icon.
        ("PUT", "/projects/{project_id}/icon"),
        # Create is personal (no target object); labels are checked on their
        # own row's visibility in test_access.py.
        ("POST", "/projects"),
        ("POST", "/task-labels"),
        ("PATCH", "/task-labels/{label_id}"),
        ("DELETE", "/task-labels/{label_id}"),
        # Comment edit/delete are author-only on top of `commenter` on the task
        # (test_task_timeline.py); the task floor is what this matrix checks.
        ("PATCH", "/tasks/{task_id}/comments/{comment_id}"),
        ("DELETE", "/tasks/{task_id}/comments/{comment_id}"),
        # Per-user catalogues, not per-object.
        ("GET", "/agent-types"),
        ("GET", "/agent-types/{type_id}/instances"),
        ("GET", "/agent-catalog"),
        ("GET", "/agent-summary"),
        ("GET", "/agent-instances/stream"),
        ("GET", "/agent-instances/{instance_id}/messages/stream"),
    }
    normalise = {
        "/projects/{project_id}": "/projects/{id}",
        "/projects/{project_id}/directories": "/projects/{id}/directories",
        "/projects/{project_id}/directories/{machine_id}": "/projects/{id}/directories/{machine}",
        "/projects/{project_id}/icon": "/projects/{id}/icon",
        "/tasks/{task_id}": "/tasks/{id}",
        "/tasks/{task_id}/sessions": "/tasks/{id}/sessions",
        "/tasks/{task_id}/timeline": "/tasks/{id}/timeline",
        "/tasks/{task_id}/comments": "/tasks/{id}/comments",
        "/tasks/{task_id}/reactions": "/tasks/{id}/reactions",
        "/agent-instances/{instance_id}": "/agent-instances/{id}",
        "/agent-instances/{instance_id}/messages": "/agent-instances/{id}/messages",
        "/agent-instances/{instance_id}/messages/{message_id}/cancel": "/agent-instances/{id}/messages/{mid}/cancel",
        "/agent-instances/{instance_id}/status": "/agent-instances/{id}/status",
        "/agent-instances/{instance_id}/access": "/agent-instances/{id}/access",
        "/agent-instances/{instance_id}/access/{access_id}": "/agent-instances/{id}/access/{aid}",
    }
    missing = []
    for router in (tasks.router, agents.router):
        for method, path in paths(router):
            if (method, path) in expected_uncovered:
                continue
            if normalise.get(path, path) not in covered:
                missing.append((method, path))
    assert not missing, f"routes without a matrix row: {missing}"
