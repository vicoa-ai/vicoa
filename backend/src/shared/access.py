"""Access resolution — one module, every surface (collaboration plan §4).

The Project is the access anchor (§2). Effective access to anything is

    max(ownership, project grant, session grant, link capability)

where ownership is `projects.team_id` (NULL ⇒ `projects.user_id` owns it, SET ⇒
the team does), a project grant is a `project_grants` row held by the user or
by one of their active teams, a session grant is the pre-existing
`user_instance_access` / `team_instance_access`, and the link capability is P4.
Automations are read-only to everyone but their author, through the project
their folder files them under and its `automations` scope
(`foreign_automation_role`).

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
GrantScope = Literal["tasks", "sessions", "automations"]
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
# works in it; a `viewer` (the free team role, §6 Team tier) reads and
# comments on it but cannot edit or prompt.
TEAM_ROLE_TO_PROJECT_ROLE: dict[str, Role] = {
    "owner": "owner",
    "admin": "admin",
    "member": "editor",
    "viewer": "commenter",
}

# A team viewer reads and comments, whatever reaches them through the team: a
# grant made *to* the team, or a session shared with it, is capped here too —
# otherwise an editor grant to the team would make its viewers editors.
TEAM_VIEWER_ROLE = "viewer"
_TEAM_VIEWER_CAP: Role = "commenter"


def _cap_for_team_viewer(role: str) -> str:
    return _TEAM_VIEWER_CAP if ROLE_RANK[role] > ROLE_RANK[_TEAM_VIEWER_CAP] else role


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
    """'owner' | 'admin' | 'member' | 'viewer' when `user_id` is an active
    member, else None."""
    row = db.execute(
        select(TeamMember.role).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
            TeamMember.status == "active",
        )
    ).first()
    return row[0] if row else None


def team_roles(db: Session, user_id: UUID) -> dict[UUID, str]:
    """{team_id: role} for every team `user_id` is an active member of."""
    return _active_team_roles(db, user_id)


def can_edit_in_team(role: str | None) -> bool:
    """Whether a team role works in the team (edits its projects, labels and
    agents) rather than only reading: every role but `viewer`."""
    return role is not None and role != TEAM_VIEWER_ROLE


def editing_team_ids_select(user_id: UUID) -> Select[tuple[UUID]]:
    """Teams `user_id` is an active member of in a role that edits — the
    write-side twin of `active_team_ids_select`."""
    return select(TeamMember.team_id).where(
        TeamMember.user_id == user_id,
        TeamMember.status == "active",
        TeamMember.role != TEAM_VIEWER_ROLE,
    )


def _active_team_roles(db: Session, user_id: UUID) -> dict[UUID, str]:
    rows = db.execute(
        select(TeamMember.team_id, TeamMember.role).where(
            TeamMember.user_id == user_id, TeamMember.status == "active"
        )
    ).all()
    return {row[0]: row[1] for row in rows}


# --- projects -----------------------------------------------------------------


def _grant_principal_predicate(user_id: UUID, *, editing: bool = False):
    """Grants held by `user_id` or one of their active teams. `editing` drops
    teams where they are only a viewer: a team grant reaches a viewer capped
    at commenter, so it can never satisfy an editor floor."""
    teams = (
        editing_team_ids_select(user_id) if editing else active_team_ids_select(user_id)
    )
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


def team_project_select(
    user_id: UUID, *, min_role: str = "viewer"
) -> Select[tuple[UUID]]:
    """Ids of projects owned by a team `user_id` is an active member of, at a
    team role that confers at least `min_role` on the team's projects."""
    team_roles = [
        t
        for t, role in TEAM_ROLE_TO_PROJECT_ROLE.items()
        if ROLE_RANK[role] >= ROLE_RANK[min_role]
    ]
    return select(Project.id).where(
        Project.team_id.in_(
            select(TeamMember.team_id).where(
                TeamMember.user_id == user_id,
                TeamMember.status == "active",
                TeamMember.role.in_(team_roles),
            )
        )
    )


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

    team_owned = team_project_select(user_id, min_role=min_role)
    grant_filters = [
        _grant_principal_predicate(
            user_id, editing=ROLE_RANK[min_role] > ROLE_RANK[_TEAM_VIEWER_CAP]
        ),
        ProjectGrant.role.in_(_roles_at_least(min_role)),
    ]
    if grant_scope is not None:
        grant_filters.append(ProjectGrant.scopes.contains([grant_scope]))
    # A grant on a project I own is meaningless (it is unioned with `own`
    # anyway); nothing else to exclude.
    granted = select(ProjectGrant.project_id).where(*grant_filters)
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
        unresolved.append(project)
    if not unresolved:
        return out

    rows = db.execute(
        select(
            ProjectGrant.project_id,
            ProjectGrant.role,
            ProjectGrant.scopes,
            ProjectGrant.principal_type,
            ProjectGrant.principal_id,
        ).where(
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
    for project_id, role, scopes, principal_type, principal_id in rows:
        if (
            principal_type == "team"
            and team_roles.get(principal_id) == TEAM_VIEWER_ROLE
        ):
            role = _cap_for_team_viewer(role)
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
    """Delegates to the task's project with the 'tasks' scope. An unfiled task
    (no project) has no board to be shared through: its owner alone, as owner."""
    if not isinstance(task, Task):
        row = db.get(Task, task)
        if row is None:
            return None
        task = row
    if task.project_id is None:
        return "owner" if task.user_id == user_id else None
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
        db.query(TeamInstanceAccess.access, TeamMember.role)
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
            # A team viewer reads a session shared with the team, never writes.
            access_levels.append(
                InstanceAccessLevel.READ if row.role == TEAM_VIEWER_ROLE else row.access
            )

    if not access_levels:
        return None

    return max(access_levels, key=lambda level: _ACCESS_PRIORITY[level])


def _level_to_role(level: InstanceAccessLevel | None) -> Role | None:
    if level is None:
        return None
    return "editor" if level == InstanceAccessLevel.WRITE else "viewer"


def _foreign_session_role(role: Role | None) -> Role | None:
    """A project role as it applies to a session someone else started there.

    'owner' on a session means it is yours — the relay keys "already in your
    own rooms, never a watcher" on it — so owning the *project* makes you an
    admin of a collaborator's session in it, not its owner."""
    return "admin" if role == "owner" else role


def instance_role(db: Session, user_id: UUID, instance: AgentInstance) -> Role | None:
    """The caller's role on a session: 'owner' for the owner; otherwise the
    stronger of the session share (READ ⇒ viewer, WRITE ⇒ editor) and the
    project role with the 'sessions' scope, capped at 'admin'. A DELETED
    session is invisible to everyone but its owner (§10.9)."""
    if instance.user_id == user_id:
        return "owner"
    if instance.status == AgentStatus.DELETED:
        return None
    role = _level_to_role(session_share_access(db, instance, user_id))
    if instance.project_id is not None:
        role = max_role(
            role,
            _foreign_session_role(
                project_role(db, user_id, instance.project_id, grant_scope="sessions")
            ),
        )
    return role


def instance_roles(
    db: Session, user_id: UUID, instances: Iterable[AgentInstance]
) -> dict[UUID, Role | None]:
    """`instance_role` for many sessions in four queries, not four per row.

    Same answer as calling `instance_role` on each: owner for your own, None
    for DELETED, else the stronger of the session share (direct or via an
    active team) and the project role with the 'sessions' scope. The shared
    session list polls this, so it must not scale with the page size.
    """
    instances = list(instances)
    out: dict[UUID, Role | None] = {}
    foreign: list[AgentInstance] = []
    for instance in instances:
        if instance.user_id == user_id:
            out[instance.id] = "owner"
        elif instance.status == AgentStatus.DELETED:
            out[instance.id] = None
        else:
            foreign.append(instance)
    if not foreign:
        return out

    ids = [i.id for i in foreign]
    levels: dict[UUID, list[InstanceAccessLevel]] = {}
    for iid, level in db.execute(
        select(UserInstanceAccess.agent_instance_id, UserInstanceAccess.access).where(
            UserInstanceAccess.agent_instance_id.in_(ids),
            UserInstanceAccess.user_id == user_id,
        )
    ).all():
        levels.setdefault(iid, []).append(level)
    for iid, level, trole in db.execute(
        select(
            TeamInstanceAccess.agent_instance_id,
            TeamInstanceAccess.access,
            TeamMember.role,
        )
        .join(TeamMember, TeamMember.team_id == TeamInstanceAccess.team_id)
        .where(
            TeamInstanceAccess.agent_instance_id.in_(ids),
            TeamMember.user_id == user_id,
            TeamMember.status == "active",
        )
    ).all():
        if level and trole == TEAM_VIEWER_ROLE:
            level = InstanceAccessLevel.READ
        levels.setdefault(iid, []).append(level)

    project_ids = {i.project_id for i in foreign if i.project_id is not None}
    projects = (
        db.execute(select(Project).where(Project.id.in_(project_ids))).scalars().all()
        if project_ids
        else []
    )
    standings = project_accesses(db, user_id, projects)

    for instance in foreign:
        share_levels = [lvl for lvl in levels.get(instance.id, []) if lvl]
        role = _level_to_role(
            max(share_levels, key=lambda lvl: _ACCESS_PRIORITY[lvl])
            if share_levels
            else None
        )
        standing = standings.get(instance.project_id) if instance.project_id else None
        if standing is not None and standing.covers("sessions"):
            role = max_role(role, _foreign_session_role(standing.role))
        out[instance.id] = role
    return out


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
    """Ids of other people's sessions `user_id` can see, by any path — direct
    share, team session share, or a project they can see the sessions of:
    shared to them, team-owned, or their own (a collaborator's session filed
    into a project you own is visible to you, as `instance_role` says).
    Excludes the caller's own sessions (those are the 'me' scope) and DELETED
    ones."""
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
            visible_project_select(user_id, scope="all", grant_scope="sessions")
        )
    )
    ids = union(direct, via_team, via_project).subquery()
    return select(AgentInstance.id).where(
        AgentInstance.id.in_(select(ids.c.agent_instance_id)),
        AgentInstance.user_id != user_id,
        AgentInstance.status != AgentStatus.DELETED,
    )


# --- automations --------------------------------------------------------------


def foreign_automation_role(standing: ProjectAccess | None) -> Role | None:
    """A collaborator's role on someone else's automation, given their standing
    on the project the automation's folder files it under (§10.6).

    Only the 'automations' scope counts — its own toggle on a grant, so whoever
    shares a project decides whether its automations go with it (owners and
    team members always cover it). A per-session share confers nothing here; it
    opens one transcript, not the schedule behind it. Capped at 'admin' like a
    session: 'owner' of an automation means its author, and editing, running
    and deleting stay the author's alone, because an automation runs an agent
    unattended on the author's machine with the author's credentials.
    """
    if standing is None or not standing.covers("automations"):
        return None
    return _foreign_session_role(standing.role)


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
