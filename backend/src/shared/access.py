"""Access resolution — one module, every surface (collaboration plan §4).

The Project is the access anchor (§2). Effective access to anything is

    max(ownership, project grant, session grant, link capability)

where ownership is `projects.team_id` (NULL ⇒ `projects.user_id` owns it, SET ⇒
the team does), a project grant is a `project_grants` row held by the user or
by one of their active teams, a session grant is the pre-existing
`user_instance_access` / `team_instance_access`, and the link capability is P4.

Lives in `shared/` because both server processes need it, and it depends only
on the models. Two lenses run through it:

* the **sharing** lens (the human dashboard) resolves the full ladder;
* the **owner-only** lens (`servers/api/instances.py`, the CLI) never calls
  in here at all — daemons and CLI wrappers stay sharing-unaware permanently.
  That is an invariant, not a TODO.

Roles form a ladder, `viewer < commenter < editor < admin < owner`; `require`
is the one place a "not enough" turns into a 403. Anything that resolves to
None is *invisible* to the caller and should 404, never 403 — a 403 confirms
the resource exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal
from uuid import UUID

from sqlalchemy import Select, and_, or_, select, union
from sqlalchemy.orm import Session

from shared.database.collab_models import (
    GRANT_SCOPES,
    ProjectGrant,
    TeamMember,
)
from shared.database.enums import AgentStatus, InstanceAccessLevel
from shared.database.models import (
    AgentInstance,
    TeamInstanceAccess,
    UserInstanceAccess,
)
from shared.database.share_models import ShareLink
from shared.database.task_models import Project, Task

Role = Literal["viewer", "commenter", "editor", "admin", "owner"]
GrantScope = Literal["tasks", "sessions"]
OwnershipScope = Literal["me", "shared", "all"]

ROLE_RANK: dict[str, int] = {
    "viewer": 1,
    "commenter": 2,
    "editor": 3,
    "admin": 4,
    "owner": 5,
}

# What standing in a team confers on a project the team owns. A team `owner`
# is the project's owner (can delete it); an `admin` runs it; a plain `member`
# works in it. Team-owned projects arrive with P7 — the mapping is fixed now so
# the resolver is complete on day one.
TEAM_ROLE_TO_PROJECT_ROLE: dict[str, Role] = {
    "owner": "owner",
    "admin": "admin",
    "member": "editor",
}

_ACCESS_PRIORITY = {InstanceAccessLevel.READ: 1, InstanceAccessLevel.WRITE: 2}


class AccessDenied(Exception):
    """The caller can see the resource but their role is below the floor.

    Mapped to HTTP 403 by an app-level handler in both server processes, so a
    query function can raise it without every route needing a try/except.
    """

    def __init__(self, minimum: str, actual: str | None = None) -> None:
        super().__init__(f"Requires {minimum} access")
        self.minimum = minimum
        self.actual = actual


def role_at_least(role: str | None, minimum: str) -> bool:
    return role is not None and ROLE_RANK[role] >= ROLE_RANK[minimum]


def max_role(*roles: str | None) -> Role | None:
    best: str | None = None
    for role in roles:
        if role is not None and (best is None or ROLE_RANK[role] > ROLE_RANK[best]):
            best = role
    return best  # type: ignore[return-value]


def require(role: str | None, minimum: str) -> Role:
    """Assert `role` reaches `minimum`; raise `AccessDenied` (→ 403) otherwise.

    Callers that got `None` back from a resolver should 404 *before* reaching
    here — see the module docstring. `require(None, …)` still denies safely.
    """
    if not role_at_least(role, minimum):
        raise AccessDenied(minimum, role)
    return role  # type: ignore[return-value]


@dataclass(frozen=True)
class ProjectAccess:
    """A resolved standing on one project: the role and which areas it covers.

    Ownership and team membership cover every scope; a grant covers what its
    `scopes` say. Serialized onto `ProjectResponse` so the UI can hide the
    board from a sessions-only grantee without a second round trip.
    """

    role: Role
    scopes: tuple[str, ...] = field(default_factory=lambda: tuple(GRANT_SCOPES))

    def covers(self, grant_scope: str | None) -> bool:
        return grant_scope is None or grant_scope in self.scopes


# --- teams --------------------------------------------------------------------


def active_team_ids_select(user_id: UUID) -> Select[tuple[UUID]]:
    """Teams `user_id` is an *active* member of. Invited and removed rows
    confer nothing — the whole access model keys off this one predicate."""
    return select(TeamMember.team_id).where(
        TeamMember.user_id == user_id, TeamMember.status == "active"
    )


def active_team_ids(db: Session, user_id: UUID) -> set[UUID]:
    return {row[0] for row in db.execute(active_team_ids_select(user_id)).all()}


def team_role(db: Session, user_id: UUID, team_id: UUID) -> str | None:
    """'owner' | 'admin' | 'member' when `user_id` is an active member, else None."""
    row = db.execute(
        select(TeamMember.role).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
            TeamMember.status == "active",
        )
    ).first()
    return row[0] if row else None


def _active_team_roles(db: Session, user_id: UUID) -> dict[UUID, str]:
    rows = db.execute(
        select(TeamMember.team_id, TeamMember.role).where(
            TeamMember.user_id == user_id, TeamMember.status == "active"
        )
    ).all()
    return {row[0]: row[1] for row in rows}


# --- projects -----------------------------------------------------------------


def _grant_principal_predicate(user_id: UUID):
    teams = active_team_ids_select(user_id)
    return or_(
        and_(
            ProjectGrant.principal_type == "user",
            ProjectGrant.principal_id == user_id,
        ),
        and_(
            ProjectGrant.principal_type == "team",
            ProjectGrant.principal_id.in_(teams),
        ),
    )


def _roles_at_least(minimum: str) -> list[str]:
    return [r for r, rank in ROLE_RANK.items() if rank >= ROLE_RANK[minimum]]


def visible_project_select(
    user_id: UUID,
    *,
    scope: OwnershipScope = "all",
    grant_scope: GrantScope | None = None,
    min_role: str = "viewer",
) -> Select[tuple[UUID]]:
    """Project ids `user_id` can see, as a SELECT for use in `.in_()`.

    `scope` is ownership: 'me' = personal projects I own; 'shared' = everything
    else I can see (team-owned where I'm a member, plus grants); 'all' = both.
    `grant_scope` narrows grants to those covering that area ('tasks' for the
    board, 'sessions' for the transcript list); ownership and team membership
    always cover both. `min_role` drops grants below a floor — e.g. WRITE
    access to a session needs `editor`.
    """
    own = select(Project.id).where(
        Project.user_id == user_id, Project.team_id.is_(None)
    )
    if scope == "me":
        return own

    team_roles = [
        t
        for t, role in TEAM_ROLE_TO_PROJECT_ROLE.items()
        if ROLE_RANK[role] >= ROLE_RANK[min_role]
    ]
    team_owned = select(Project.id).where(
        Project.team_id.in_(
            select(TeamMember.team_id).where(
                TeamMember.user_id == user_id,
                TeamMember.status == "active",
                TeamMember.role.in_(team_roles),
            )
        )
    )
    grant_filters = [
        _grant_principal_predicate(user_id),
        ProjectGrant.role.in_(_roles_at_least(min_role)),
    ]
    if grant_scope is not None:
        grant_filters.append(ProjectGrant.scopes.contains([grant_scope]))
    # A grant on a project I own is meaningless; and the Inbox is never
    # grantable — it is the per-user "No project" bucket, not a board.
    granted = (
        select(ProjectGrant.project_id)
        .join(Project, Project.id == ProjectGrant.project_id)
        .where(*grant_filters, Project.is_inbox.is_(False))
    )
    if scope == "shared":
        shared = union(team_owned, granted).subquery()
        return select(shared.c.id).where(shared.c.id.not_in(own))
    return select(union(own, team_owned, granted).subquery().c.id)


def visible_project_ids(
    db: Session,
    user_id: UUID,
    *,
    scope: OwnershipScope = "all",
    grant_scope: GrantScope | None = None,
    min_role: str = "viewer",
) -> set[UUID]:
    stmt = visible_project_select(
        user_id, scope=scope, grant_scope=grant_scope, min_role=min_role
    )
    return {row[0] for row in db.execute(stmt).all()}


def project_accesses(
    db: Session, user_id: UUID, projects: Iterable[Project]
) -> dict[UUID, ProjectAccess]:
    """Resolve the caller's standing on many projects in three queries.

    Ownership first, then team membership, then the best grant. A project the
    caller cannot see at all is simply absent from the result.
    """
    projects = list(projects)
    if not projects:
        return {}
    out: dict[UUID, ProjectAccess] = {}
    team_roles = _active_team_roles(db, user_id)
    unresolved: list[Project] = []
    for project in projects:
        if project.team_id is None:
            if project.user_id == user_id:
                out[project.id] = ProjectAccess("owner")
                continue
        else:
            trole = team_roles.get(project.team_id)
            if trole is not None:
                out[project.id] = ProjectAccess(TEAM_ROLE_TO_PROJECT_ROLE[trole])
                continue
        # The Inbox is never reachable by anyone but its owner.
        if not project.is_inbox:
            unresolved.append(project)
    if not unresolved:
        return out

    rows = db.execute(
        select(ProjectGrant.project_id, ProjectGrant.role, ProjectGrant.scopes).where(
            ProjectGrant.project_id.in_([p.id for p in unresolved]),
            _grant_principal_predicate(user_id),
        )
    ).all()
    # Several grants can reach one user (direct + via a team). The strongest
    # role wins and the scopes are the union of all of them — a viewer-on-tasks
    # plus an editor-on-sessions is an editor on both, the least surprising
    # reading of "I was given both".
    best_role: dict[UUID, str] = {}
    covered: dict[UUID, set[str]] = {}
    for project_id, role, scopes in rows:
        best_role[project_id] = max_role(best_role.get(project_id), role) or role
        covered.setdefault(project_id, set()).update(scopes or [])
    for project_id, role in best_role.items():
        out[project_id] = ProjectAccess(
            role,  # type: ignore[arg-type]
            tuple(s for s in GRANT_SCOPES if s in covered[project_id]),
        )
    return out


def project_access(
    db: Session, user_id: UUID, project: Project | UUID
) -> ProjectAccess | None:
    """The caller's standing on one project, or None when invisible."""
    if not isinstance(project, Project):
        row = db.get(Project, project)
        if row is None:
            return None
        project = row
    return project_accesses(db, user_id, [project]).get(project.id)


def project_role(
    db: Session,
    user_id: UUID,
    project: Project | UUID,
    *,
    grant_scope: GrantScope | None = None,
) -> Role | None:
    """The caller's role on `project` for `grant_scope`, or None when invisible.

    A grant that does not cover `grant_scope` counts for nothing there: an
    editor-on-sessions grant makes the board invisible, not read-only.
    """
    access = project_access(db, user_id, project)
    if access is None or not access.covers(grant_scope):
        return None
    return access.role


# --- tasks --------------------------------------------------------------------


def task_role(db: Session, user_id: UUID, task: Task | UUID) -> Role | None:
    """Delegates to the task's project with the 'tasks' scope."""
    if not isinstance(task, Task):
        row = db.get(Task, task)
        if row is None:
            return None
        task = row
    return project_role(db, user_id, task.project_id, grant_scope="tasks")


# --- sessions (agent instances) -----------------------------------------------


def session_share_access(
    db: Session, instance: AgentInstance, user_id: UUID
) -> InstanceAccessLevel | None:
    """The pre-P3 resolver, unchanged: owner ⇒ WRITE, else the strongest of a
    direct `user_instance_access` and any `team_instance_access` reachable
    through an *active* team membership. `instance_access` folds the project
    term in on top of this; it is kept as the inner call on purpose so the
    message-send path that already enforced it keeps its exact semantics."""
    if instance.user_id == user_id:
        return InstanceAccessLevel.WRITE

    access_levels: list[InstanceAccessLevel] = []

    direct_access = (
        db.query(UserInstanceAccess.access)
        .filter(
            UserInstanceAccess.agent_instance_id == instance.id,
            UserInstanceAccess.user_id == user_id,
        )
        .first()
    )
    if direct_access and direct_access.access:
        access_levels.append(direct_access.access)

    team_access_rows = (
        db.query(TeamInstanceAccess.access)
        .join(TeamMember, TeamMember.team_id == TeamInstanceAccess.team_id)
        .filter(
            TeamInstanceAccess.agent_instance_id == instance.id,
            TeamMember.user_id == user_id,
            TeamMember.status == "active",
        )
        .all()
    )
    for row in team_access_rows:
        if row.access:
            access_levels.append(row.access)

    if not access_levels:
        return None

    return max(access_levels, key=lambda level: _ACCESS_PRIORITY[level])


def _level_to_role(level: InstanceAccessLevel | None) -> Role | None:
    if level is None:
        return None
    return "editor" if level == InstanceAccessLevel.WRITE else "viewer"


def instance_role(db: Session, user_id: UUID, instance: AgentInstance) -> Role | None:
    """The caller's role on a session: 'owner' for the owner; otherwise the
    stronger of the session share (READ ⇒ viewer, WRITE ⇒ editor) and the
    project role with the 'sessions' scope. A DELETED session is invisible to
    everyone but its owner (§10.9)."""
    if instance.user_id == user_id:
        return "owner"
    if instance.status == AgentStatus.DELETED:
        return None
    role = _level_to_role(session_share_access(db, instance, user_id))
    if instance.project_id is not None:
        role = max_role(
            role,
            project_role(db, user_id, instance.project_id, grant_scope="sessions"),
        )
    return role


def instance_access(
    db: Session, user_id: UUID, instance: AgentInstance
) -> InstanceAccessLevel | None:
    """READ / WRITE / None on a session — the legacy two-level view of
    `instance_role`, for the paths that still speak that vocabulary.
    `editor` and above can prompt (WRITE); `viewer` and `commenter` read."""
    role = instance_role(db, user_id, instance)
    if role is None:
        return None
    return (
        InstanceAccessLevel.WRITE
        if role_at_least(role, "editor")
        else InstanceAccessLevel.READ
    )


def shared_instance_select(user_id: UUID) -> Select[tuple[UUID]]:
    """Ids of sessions shared *to* `user_id` by any path — direct share, team
    session share, or a project grant covering sessions. Excludes the caller's
    own sessions (those are the 'me' scope) and DELETED ones."""
    direct = select(UserInstanceAccess.agent_instance_id).where(
        UserInstanceAccess.user_id == user_id
    )
    via_team = (
        select(TeamInstanceAccess.agent_instance_id)
        .select_from(TeamInstanceAccess)
        .join(TeamMember, TeamMember.team_id == TeamInstanceAccess.team_id)
        .where(TeamMember.user_id == user_id, TeamMember.status == "active")
    )
    via_project = select(AgentInstance.id).where(
        AgentInstance.project_id.in_(
            visible_project_select(user_id, scope="shared", grant_scope="sessions")
        )
    )
    ids = union(direct, via_team, via_project).subquery()
    return select(AgentInstance.id).where(
        AgentInstance.id.in_(select(ids.c.agent_instance_id)),
        AgentInstance.user_id != user_id,
        AgentInstance.status != AgentStatus.DELETED,
    )


# --- share links (P4) ---------------------------------------------------------


@dataclass(frozen=True)
class ShareGrant:
    """What a live share-link token confers (§3.4).

    Always a read. `allow_comments` is the single write a URL can carry, and
    only for a signed-in visitor (whatever the link's audience) — the resolver
    hands it back as a fact; the comment endpoint is where it is enforced.
    The visible-sessions predicate lives in `share_queries` because it needs
    the per-scope filters; this object just says what the link points at.

    `scopes` is which halves of a project the link carries ('tasks',
    'sessions'); empty for a session link. Every project-shaped endpoint asks
    `covers()` first, so a link that carries only tasks 404s on sessions the
    same way an unknown token does.
    """

    link: ShareLink
    kind: str
    audience: str
    allow_comments: bool
    scopes: frozenset[str]
    filters: dict
    instance_id: UUID | None
    project_id: UUID | None

    @property
    def id(self) -> UUID:
        return self.link.id

    def covers(self, scope: str) -> bool:
        return scope in self.scopes

    def scope_filters(self, scope: str) -> dict:
        """The narrowing for one scope; `{}` when the link sets none."""
        value = self.filters.get(scope)
        return dict(value) if isinstance(value, dict) else {}


def resolve_share(
    db: Session, token: str, *, user_id: UUID | None = None
) -> ShareGrant | None:
    """Resolve a share-link token to its capability, or None (§3.4, §10.5).

    None for every way a token can fail — unknown, revoked, expired, wrong
    audience for this visitor, or a target that no longer exists / is DELETED
    — so the public API can answer one identical 404 and the token space is
    not an oracle. `user_id` is the signed-in visitor, if any; an
    `authenticated` link resolves to nothing for an anonymous one.
    """
    if not token or len(token) > 43:
        return None
    link = db.execute(
        select(ShareLink).where(ShareLink.token == token)
    ).scalar_one_or_none()
    if link is None or not link.is_live:
        return None
    if link.audience == "authenticated" and user_id is None:
        return None
    if link.kind == "session":
        instance = db.get(AgentInstance, link.agent_instance_id)
        if instance is None or instance.status == AgentStatus.DELETED:
            return None
    else:
        if link.project_id is None or db.get(Project, link.project_id) is None:
            return None
    return ShareGrant(
        link=link,
        kind=link.kind,
        audience=link.audience,
        allow_comments=bool(link.allow_comments and user_id is not None),
        scopes=frozenset(link.scopes or ()),
        filters=dict(link.filters) if isinstance(link.filters, dict) else {},
        instance_id=link.agent_instance_id,
        project_id=link.project_id,
    )
