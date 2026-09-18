"""DB queries for the projects & tasks tracker (tasks-and-projects plan §3).

Every function runs under one of two lenses (see `shared.access`):

* **owner-only** (`sharing=False`, the default): the caller sees exactly what
  they own — `projects.user_id = me AND team_id IS NULL`, `tasks.user_id = me`.
  This is what the agent-facing `servers` router and the CLI use, and it never
  widens: daemons and CLI wrappers stay sharing-unaware permanently.
* **sharing** (`sharing=True`): the human dashboard. Visibility is
  `access.visible_project_select` (own + team-owned + granted), writes are
  gated by `access.require` on the project role, and the `tasks` grant scope
  applies throughout.

Safe by default: a call site that forgets the flag gets the narrower lens.
Under the sharing lens a visible-but-insufficient role raises `AccessDenied`
(→ 403); an invisible resource is still `None` (→ 404), never 403.

"No project" is `tasks.project_id IS NULL` — the same convention as
`agent_instances.project_id`. There is no hidden Inbox row. An unfiled task is
visible to its owner alone under either lens, has no `KEY-n` identifier
(identifiers are project-scoped), and gets one when moved into a project.

Ownership invariant: `tasks.user_id` is always the owning project's `user_id`
— the project owner, not whoever created the task — so the owner-only lens
(CLI, automations) keeps seeing every task on its own boards, and a task that
moves project moves owner with it. An unfiled task is owned by whoever filed
it there (its creator, the caller who moved it out, or the owner of the project
that was deleted from under it). Who actually did what is `task_activity`'s
job, not this column's.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from shared import access
from shared.access import Role
from shared.database import (
    AgentInstance,
    Machine,
    Project,
    ProjectDirectory,
    Task,
    TaskActivity,
    TaskComment,
    TaskLabel,
)
from shared.database.agent_profile_models import AgentProfile
from shared.database.enums import AgentStatus
from shared.database.project_matching import backfill_project_id_for_directory
from shared.database.task_identity import (
    allocate_task_number,
    ensure_project_key_committed,
)

logger = logging.getLogger(__name__)

# A project with no session activity for this long — and no open tasks —
# auto-archives (project-identity-unification §4b), the counterweight to
# auto-create. A new session revives it instantly via the §4a self-heal rule.
STALE_PROJECT_DAYS = 30

# Tasks in these terminal states don't count as "open work" keeping a project
# alive for auto-archive purposes.
_CLOSED_TASK_STATUSES = ("done", "cancelled")


class MachineNotFoundError(Exception):
    """Raised when a referenced machine doesn't exist or isn't the user's."""


class ProjectNotFoundError(Exception):
    """Raised when a referenced project doesn't exist or isn't visible."""


class ProjectKeyTakenError(Exception):
    """Another of this owner's projects already holds that task key."""


class LabelNotFoundError(Exception):
    """Raised when a referenced label doesn't exist or isn't usable here."""


class AssigneeNotFoundError(Exception):
    """The assignee isn't a principal with standing on the task's project."""


class TeamNotFoundError(Exception):
    """A referenced team doesn't exist or the caller isn't an active member."""


class ParentTaskError(Exception):
    """Raised when a parent_task_id is missing, foreign, or would cycle.

    `not_found` distinguishes 404 (unknown/foreign task) from 400
    (self-parent or cycle)."""

    def __init__(self, message: str, not_found: bool = False):
        super().__init__(message)
        self.not_found = not_found


# --- The two lenses -----------------------------------------------------------


def _owner_only_project_filter(user_id: UUID):
    return and_(Project.user_id == user_id, Project.team_id.is_(None))


def _role_for(
    db: Session,
    user_id: UUID,
    project: Project,
    *,
    sharing: bool,
    grant_scope: access.GrantScope | None = None,
) -> Role | None:
    """The caller's role on `project` under the requested lens, or None."""
    if not sharing:
        if project.user_id == user_id and project.team_id is None:
            return "owner"
        return None
    return access.project_role(db, user_id, project, grant_scope=grant_scope)


def _get_project(
    db: Session,
    user_id: UUID,
    project_id: UUID,
    *,
    sharing: bool = False,
    grant_scope: access.GrantScope | None = None,
    minimum: str = "viewer",
) -> Project | None:
    """Load a project the caller can see; None if invisible.

    Raises `AccessDenied` when the project is visible but the caller's role is
    below `minimum` — the 404-vs-403 split from the `shared.access` docstring.
    """
    project = db.get(Project, project_id)
    if project is None:
        return None
    role = _role_for(db, user_id, project, sharing=sharing, grant_scope=grant_scope)
    if role is None:
        return None
    access.require(role, minimum)
    return project


def _latest_activity_subquery(db: Session, user_id: UUID):
    """Newest session start per project, for recency ordering / staleness."""
    return (
        db.query(
            AgentInstance.project_id.label("pid"),
            func.max(AgentInstance.started_at).label("last_at"),
        )
        .filter(AgentInstance.user_id == user_id)
        .group_by(AgentInstance.project_id)
        .subquery()
    )


def autoarchive_stale_projects(
    db: Session, user_id: UUID, days: int = STALE_PROJECT_DAYS
) -> int:
    """Archive projects idle for ``days`` with no open tasks (§4b).

    The counterweight to auto-create: touching a repo mints a project, so
    long-untouched ones fall out of the way on their own. Conservative —
    requires the project itself to predate the cutoff, its newest session (if
    any) to predate it, and no open tasks — and fully reversible via the §4a
    self-heal (a new session un-archives). Returns how many were archived.
    Only ever touches the caller's own personal projects.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    latest = _latest_activity_subquery(db, user_id)
    # `IS NOT NULL` is load-bearing: one NULL inside a `NOT IN (...)` subquery
    # makes the whole predicate unknown, and nothing would ever archive.
    open_task_projects = (
        select(Task.project_id)
        .where(
            Task.user_id == user_id,
            Task.project_id.isnot(None),
            Task.status.notin_(_CLOSED_TASK_STATUSES),
        )
        .distinct()
    )
    stale = (
        db.query(Project)
        .outerjoin(latest, latest.c.pid == Project.id)
        .filter(
            _owner_only_project_filter(user_id),
            Project.is_archived.is_(False),
            Project.created_at < cutoff,
            or_(latest.c.last_at.is_(None), latest.c.last_at < cutoff),
            Project.id.notin_(open_task_projects),
        )
        .all()
    )
    for project in stale:
        project.is_archived = True
        project.archived_at = now
    if stale:
        db.commit()
        logger.info(
            "auto-archived %d stale project(s) for user %s", len(stale), user_id
        )
    return len(stale)


def list_projects(
    db: Session,
    user_id: UUID,
    include_archived: bool = False,
    *,
    sharing: bool = False,
    machine_id: UUID | None = None,
) -> list[tuple[Project, datetime | None]]:
    """The projects the caller can see, each paired with its newest session
    start (``None`` when no session ever ran there): most-recent activity
    first, then name. Under the sharing lens that includes team-owned projects
    the caller is an active member of and projects granted to them or their
    teams. With ``machine_id``, only projects linked to a folder on that machine
    — what the new-session picker lists.

    Opportunistically auto-archives stale projects (on every fetch, including
    the sidebar's include_archived read) so the counterweight to auto-create
    needs no scheduler.
    """
    autoarchive_stale_projects(db, user_id)

    latest = _latest_activity_subquery(db, user_id)
    query = db.query(Project, latest.c.last_at).outerjoin(
        latest, latest.c.pid == Project.id
    )
    if sharing:
        query = query.filter(Project.id.in_(access.visible_project_select(user_id)))
    else:
        query = query.filter(_owner_only_project_filter(user_id))
    if not include_archived:
        query = query.filter(Project.is_archived.is_(False))
    if machine_id is not None:
        query = query.filter(
            Project.id.in_(
                select(ProjectDirectory.project_id).where(
                    ProjectDirectory.machine_id == machine_id
                )
            )
        )
    rows = query.order_by(
        latest.c.last_at.desc().nullslast(),
        Project.name.asc(),
    ).all()
    return [(project, last_at) for project, last_at in rows]


def create_project(
    db: Session,
    user_id: UUID,
    name: str,
    color: str | None = None,
    icon: str | None = None,
    git_remote_url: str | None = None,
) -> Project:
    project = Project(
        user_id=user_id,
        name=name,
        color=color,
        icon=icon,
        git_remote_url=git_remote_url,
    )
    db.add(project)
    db.commit()
    return project


def get_accessible_project(
    db: Session,
    user_id: UUID,
    project_id: UUID,
    *,
    sharing: bool = False,
    minimum: str = "viewer",
    grant_scope: access.GrantScope | None = None,
) -> Project | None:
    """The single project-access predicate (plan §9 constraint 3).

    Every project-scoped read that isn't already a list — icon serving/upload,
    settings — routes through here. None when invisible; `AccessDenied` when
    visible but below `minimum`. `grant_scope` narrows a grant to the area
    being touched ('sessions' for filing a session onto the project).
    """
    return _get_project(
        db,
        user_id,
        project_id,
        sharing=sharing,
        grant_scope=grant_scope,
        minimum=minimum,
    )


def set_project_icon(
    db: Session,
    user_id: UUID,
    project_id: UUID,
    *,
    icon_image_uri: str | None,
    icon_source: str | None,
    sharing: bool = False,
) -> Project | None:
    """Point a project at an uploaded/seeded icon (or clear it). Admin+."""
    project = _get_project(db, user_id, project_id, sharing=sharing, minimum="admin")
    if project is None:
        return None
    project.icon_image_uri = icon_image_uri
    project.icon_source = icon_source
    db.commit()
    db.refresh(project)
    return project


def reset_project_icon(
    db: Session, user_id: UUID, project_id: UUID, *, sharing: bool = False
) -> Project | None:
    """Reset to the generated default: drop the image AND emoji, and pin
    ``icon_source='user'`` so the git-avatar seed does NOT re-add an image on the
    next fetch. Renders as the generated initial-square. Admin+."""
    project = _get_project(db, user_id, project_id, sharing=sharing, minimum="admin")
    if project is None:
        return None
    project.icon_image_uri = None
    project.icon = None
    # Sentinel: an explicit user reset. NULL would make the project seed-eligible
    # again, which is exactly the "reset keeps turning back into the image" bug.
    project.icon_source = "user"
    db.commit()
    db.refresh(project)
    return project


def update_project(
    db: Session,
    user_id: UUID,
    project_id: UUID,
    fields: dict,
    *,
    sharing: bool = False,
) -> Project | None:
    """Apply the explicitly-sent PATCH fields. Project settings are admin+.
    None when not found / not visible."""
    project = _get_project(db, user_id, project_id, sharing=sharing, minimum="admin")
    if project is None:
        return None

    if "is_archived" in fields:
        archived = bool(fields.pop("is_archived"))
        if archived != project.is_archived:
            project.is_archived = archived
            project.archived_at = datetime.now(timezone.utc) if archived else None
    for field in ("name", "color", "icon", "git_remote_url", "key"):
        if field in fields:
            setattr(project, field, fields[field])
    try:
        db.commit()
    except IntegrityError as exc:
        # The only unique constraint reachable from here is the task key, which
        # is unique within the owner. Surface it as a conflict rather than a 500
        # so the settings form can say "that key is taken".
        db.rollback()
        raise ProjectKeyTakenError("That project key is already in use") from exc
    return project


def project_summary(
    db: Session, user_id: UUID, project_id: UUID, *, sharing: bool = False
) -> tuple[int, int, int] | None:
    """``(task_count, session_count, active_session_count)`` — what a delete
    would file under No project, for the confirm dialog. None when invisible."""
    project = _get_project(db, user_id, project_id, sharing=sharing)
    if project is None:
        return None
    task_count = (
        db.query(func.count(Task.id)).filter(Task.project_id == project.id).scalar()
        or 0
    )
    sessions = db.query(func.count(AgentInstance.id)).filter(
        AgentInstance.project_id == project.id,
        AgentInstance.status != AgentStatus.DELETED,
    )
    session_count = sessions.scalar() or 0
    active_count = (
        sessions.filter(AgentInstance.status == AgentStatus.ACTIVE).scalar() or 0
    )
    return task_count, session_count, active_count


def delete_project(
    db: Session, user_id: UUID, project_id: UUID, *, sharing: bool = False
) -> bool:
    """Delete a project. Nothing of the user's work cascades: its tasks (with
    their comments and activity) and its sessions are filed under **No
    project** — tasks lose their ``KEY-n`` (the number is project-scoped) and
    become the project owner's; sessions keep their owner. Directories, grants
    and share links do go with the row. Owner only — an admin grantee runs the
    project, the owner is the one who can end it. Allowed on an archived
    project. False = not found."""
    project = _get_project(db, user_id, project_id, sharing=sharing, minimum="owner")
    if project is None:
        return False
    # Explicit rather than leaning on the FK's SET NULL: the number must be
    # cleared with the project (a stale number would collide the next time the
    # task is filed), and the child rows' denormalized project_id follows the
    # task exactly as it does on a move.
    task_ids = select(Task.id).where(Task.project_id == project.id)
    for model in (TaskComment, TaskActivity):
        db.query(model).filter(model.task_id.in_(task_ids)).update(
            {"project_id": None}, synchronize_session=False
        )
    db.query(Task).filter(Task.project_id == project.id).update(
        {"project_id": None, "number": None, "user_id": project.user_id},
        synchronize_session=False,
    )
    db.query(AgentInstance).filter(AgentInstance.project_id == project.id).update(
        {"project_id": None}, synchronize_session=False
    )
    db.delete(project)
    db.commit()
    return True


# --- Project directories --------------------------------------------------


def set_project_directory(
    db: Session,
    user_id: UUID,
    project_id: UUID,
    machine_id: UUID,
    local_path: str,
    *,
    sharing: bool = False,
) -> Project | None:
    """Link (or relink) a project to a path on one machine.

    Upsert on (project_id, machine_id) — the table allows one row per pair, so
    re-linking a machine overwrites its path instead of adding a second row.
    The machine must be the caller's own (machines are never shared), so this
    is always "where *my* copy of this project lives": any member who may
    contribute (``editor`` on the project — a project-settings write, so any
    grant scope counts) can link their own machine — that is how a shared repo
    gets one project across the team's laptops. Re-linking the same path is
    also the way to re-run the adoption backfill below. Returns the refreshed
    project, or None when invisible.
    """
    project = _get_project(db, user_id, project_id, sharing=sharing, minimum="editor")
    if project is None:
        return None

    machine = (
        db.query(Machine)
        .filter(Machine.id == machine_id, Machine.user_id == user_id)
        .first()
    )
    if machine is None:
        raise MachineNotFoundError("Machine not found")

    existing = (
        db.query(ProjectDirectory)
        .filter(
            ProjectDirectory.project_id == project_id,
            ProjectDirectory.machine_id == machine_id,
        )
        .first()
    )
    if existing is None:
        db.add(
            ProjectDirectory(
                user_id=user_id,
                project_id=project_id,
                machine_id=machine_id,
                local_path=local_path,
            )
        )
    else:
        existing.local_path = local_path
    # Attach sessions that already ran under this path (or whose worktree's repo
    # root is this path) but predate the link. Only fills NULLs, never steals.
    backfill_project_id_for_directory(
        db,
        user_id=user_id,
        project_id=project_id,
        machine_id=machine_id,
        local_path=local_path,
    )
    db.commit()
    db.refresh(project)
    return project


def delete_project_directory(
    db: Session,
    user_id: UUID,
    project_id: UUID,
    machine_id: UUID,
    *,
    sharing: bool = False,
) -> Project | None:
    """Unlink a machine from a project. A member may unlink their own machine
    (``editor``); someone else's row takes ``admin``. None when invisible."""
    project = _get_project(db, user_id, project_id, sharing=sharing, minimum="editor")
    if project is None:
        return None
    row = (
        db.query(ProjectDirectory)
        .filter(
            ProjectDirectory.project_id == project_id,
            ProjectDirectory.machine_id == machine_id,
        )
        .first()
    )
    if row is not None:
        if row.user_id != user_id:
            access.require(
                _role_for(db, user_id, project, sharing=sharing),
                "admin",
            )
        db.delete(row)
        db.commit()
        db.refresh(project)
    return project


# --- Labels ---------------------------------------------------------------
#
# Visibility = (team_id IS NULL AND user_id = me) OR (team_id ∈ my active
# teams) — collaboration §3.3. A task additionally accepts any label from its
# project's *vocabulary* (the owner's personal labels, or the owning team's),
# so a grantee editing a shared board can apply the labels the board already
# uses without being able to enumerate the owner's other projects' labels.


def _personal_label_filter(user_id: UUID):
    return and_(TaskLabel.user_id == user_id, TaskLabel.team_id.is_(None))


def _visible_label_filter(user_id: UUID, *, sharing: bool):
    if not sharing:
        return _personal_label_filter(user_id)
    return or_(
        _personal_label_filter(user_id),
        TaskLabel.team_id.in_(access.active_team_ids_select(user_id)),
    )


def _project_vocabulary_filter(project: Project):
    if project.team_id is not None:
        return TaskLabel.team_id == project.team_id
    return _personal_label_filter(project.user_id)


def list_labels(
    db: Session,
    user_id: UUID,
    *,
    sharing: bool = False,
    project_id: UUID | None = None,
) -> list[TaskLabel]:
    """The caller's usable labels. With `project_id`, the vocabulary of that
    project instead (what a shared board's label picker needs); raises
    `ProjectNotFoundError` when the project isn't visible."""
    if project_id is not None:
        project = _get_project(
            db, user_id, project_id, sharing=sharing, grant_scope="tasks"
        )
        if project is None:
            raise ProjectNotFoundError("Project not found")
        predicate = _project_vocabulary_filter(project)
    else:
        predicate = _visible_label_filter(user_id, sharing=sharing)
    return db.query(TaskLabel).filter(predicate).order_by(TaskLabel.name.asc()).all()


def create_label(
    db: Session,
    user_id: UUID,
    name: str,
    color: str,
    *,
    team_id: UUID | None = None,
) -> TaskLabel:
    """A personal label, or — with `team_id` — one in a team's vocabulary,
    which needs an active membership of that team."""
    if team_id is not None and access.team_role(db, user_id, team_id) is None:
        raise TeamNotFoundError("Team not found")
    label = TaskLabel(user_id=user_id, team_id=team_id, name=name, color=color)
    db.add(label)
    db.commit()
    return label


def _get_editable_label(
    db: Session, user_id: UUID, label_id: UUID, *, sharing: bool
) -> TaskLabel | None:
    return (
        db.query(TaskLabel)
        .filter(
            TaskLabel.id == label_id, _visible_label_filter(user_id, sharing=sharing)
        )
        .first()
    )


def update_label(
    db: Session,
    user_id: UUID,
    label_id: UUID,
    fields: dict,
    *,
    sharing: bool = False,
) -> TaskLabel | None:
    label = _get_editable_label(db, user_id, label_id, sharing=sharing)
    if label is None:
        return None
    for key in ("name", "color"):
        if key in fields and fields[key] is not None:
            setattr(label, key, fields[key])
    db.commit()
    return label


def delete_label(
    db: Session, user_id: UUID, label_id: UUID, *, sharing: bool = False
) -> bool:
    label = _get_editable_label(db, user_id, label_id, sharing=sharing)
    if label is None:
        return False
    db.delete(label)
    db.commit()
    return True


def _resolve_labels(
    db: Session,
    user_id: UUID,
    label_ids: list[UUID],
    *,
    project: Project | None,
    sharing: bool,
) -> list[TaskLabel]:
    if not label_ids:
        return []
    usable = _visible_label_filter(user_id, sharing=sharing)
    if sharing and project is not None:
        usable = or_(usable, _project_vocabulary_filter(project))
    labels = db.query(TaskLabel).filter(TaskLabel.id.in_(label_ids), usable).all()
    if len(labels) != len(set(label_ids)):
        raise LabelNotFoundError("Label not found")
    return labels


def _validate_assignee(
    db: Session,
    user_id: UUID,
    project: Project | None,
    assignee_type: str | None,
    assignee_id: UUID | None,
    *,
    sharing: bool,
) -> None:
    """A task may only be assigned to a principal with standing on its project.

    A user assignee is the caller, or (sharing lens) anyone who can see the
    board — owner, team member or grantee. An agent assignee is one of the
    caller's own profiles, or (sharing lens) one belonging to the project's
    owner or owning team. An unfiled task (``project`` None) has no board for
    anyone else to stand on: the caller and the caller's own profiles only.
    """
    if assignee_type is None or assignee_id is None:
        return
    if assignee_type == "user":
        if assignee_id == user_id:
            return
        if (
            sharing
            and project is not None
            and access.project_role(db, assignee_id, project, grant_scope="tasks")
            is not None
        ):
            return
        raise AssigneeNotFoundError("Assignee not found")
    owners = [AgentProfile.user_id == user_id]
    if sharing and project is not None:
        if project.team_id is not None:
            owners.append(AgentProfile.team_id == project.team_id)
        else:
            owners.append(AgentProfile.user_id == project.user_id)
    owned = (
        db.query(AgentProfile.id)
        .filter(AgentProfile.id == assignee_id, or_(*owners))
        .first()
    )
    if owned is None:
        raise AssigneeNotFoundError("Assignee not found")


def _validate_parent(
    db: Session,
    user_id: UUID,
    task_id: UUID | None,
    parent_id: UUID,
    *,
    sharing: bool,
) -> None:
    """Parent must be a task the caller can see; reject self-parenting and cycles."""
    if task_id is not None and parent_id == task_id:
        raise ParentTaskError("A task cannot be its own parent")
    parent = get_task(db, user_id, parent_id, sharing=sharing)
    if parent is None:
        raise ParentTaskError("Parent task not found", not_found=True)
    # Walk up the ancestor chain; hitting task_id means the new edge closes
    # a cycle. Bounded by the chain length (no cycles exist beforehand). Reads
    # only parent ids, so no visibility filter is needed on the walk itself.
    seen: set[UUID] = set()
    current = parent.parent_task_id
    while current is not None and current not in seen:
        if task_id is not None and current == task_id:
            raise ParentTaskError("This would create a sub-task cycle")
        seen.add(current)
        row = db.query(Task.parent_task_id).filter(Task.id == current).first()
        current = row[0] if row else None


# --- Tasks ------------------------------------------------------------------


def _visible_task_filter(user_id: UUID, *, sharing: bool):
    if not sharing:
        return Task.user_id == user_id
    # An unfiled task has no project to be shared through: its owner alone.
    return or_(
        Task.project_id.in_(
            access.visible_project_select(user_id, grant_scope="tasks")
        ),
        and_(Task.project_id.is_(None), Task.user_id == user_id),
    )


def list_tasks(
    db: Session,
    user_id: UUID,
    project_id: UUID | None = None,
    status: str | None = None,
    priority: str | None = None,
    *,
    sharing: bool = False,
) -> list[Task]:
    """Visible tasks ordered by position (board/list order), then age."""
    query = (
        db.query(Task)
        .options(selectinload(Task.labels))
        .filter(_visible_task_filter(user_id, sharing=sharing))
    )
    if project_id is not None:
        query = query.filter(Task.project_id == project_id)
    if status is not None:
        query = query.filter(Task.status == status)
    if priority is not None:
        query = query.filter(Task.priority == priority)
    return query.order_by(Task.position.asc(), Task.created_at.asc()).all()


def create_task(
    db: Session,
    user_id: UUID,
    title: str,
    description: str | None = None,
    project_id: UUID | None = None,
    status: str = "backlog",
    priority: str = "none",
    position: float = 0,
    parent_task_id: UUID | None = None,
    label_ids: list[UUID] | None = None,
    start_date: datetime | None = None,
    due_date: datetime | None = None,
    assignee_type: str | None = None,
    assignee_id: UUID | None = None,
    *,
    sharing: bool = False,
) -> Task:
    """Create a task; without an explicit project it is unfiled (No project,
    owned by the caller, no identifier). Creating on someone else's project
    needs `editor`."""
    project: Project | None = None
    if project_id is not None:
        project = _get_project(
            db,
            user_id,
            project_id,
            sharing=sharing,
            grant_scope="tasks",
            minimum="editor",
        )
        if project is None:
            raise ProjectNotFoundError("Project not found")

    if parent_task_id is not None:
        _validate_parent(db, user_id, None, parent_task_id, sharing=sharing)
    _validate_assignee(
        db, user_id, project, assignee_type, assignee_id, sharing=sharing
    )
    # Resolve labels before taking a number: _resolve_labels raises on an
    # unknown label, and a rejected create should not burn an identifier.
    labels = _resolve_labels(
        db, user_id, label_ids or [], project=project, sharing=sharing
    )

    # Identity (§3.5). The key is allocated lazily, on the project's first task,
    # in its own savepoint; the number comes from UPDATE ... RETURNING on the
    # counter, whose row lock serializes concurrent inserts into this project.
    # An unfiled task has neither — identifiers are project-scoped.
    number: int | None = None
    if project is not None:
        ensure_project_key_committed(db, project)
        number = allocate_task_number(db, project)

    task = Task(
        # The project owner owns the task (module docstring), whoever created
        # it; an unfiled task is the caller's.
        user_id=project.user_id if project is not None else user_id,
        project_id=project.id if project is not None else None,
        number=number,
        title=title,
        description=description,
        status=status,
        priority=priority,
        position=position,
        parent_task_id=parent_task_id,
        start_date=start_date,
        due_date=due_date,
        assignee_type=assignee_type,
        assignee_id=assignee_id,
    )
    if labels:
        task.labels = labels
    db.add(task)
    db.commit()
    return task


def get_task(
    db: Session, user_id: UUID, task_id: UUID, *, sharing: bool = False
) -> Task | None:
    return (
        db.query(Task)
        .options(selectinload(Task.labels))
        .filter(Task.id == task_id, _visible_task_filter(user_id, sharing=sharing))
        .first()
    )


# "VIC-42" — a project key (2-8 chars, letter-led) and a per-project number.
# Deliberately not anchored to the key length the deriver produces: a key is
# user-editable, and a resolver that rejected what the editor accepted would be
# the worse of the two bugs.
_IDENTIFIER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]{1,7})-([0-9]+)$")


def resolve_task(
    db: Session, user_id: UUID, ref: str, *, sharing: bool = False
) -> Task | None:
    """Find a visible task by UUID **or** by its "VIC-42" identifier.

    Every surface where a person or an agent types a task reference goes through
    here, because the identifier is the only handle either of them can actually
    see: it is what the task-detail header shows, what `vicoa task ls` prints,
    and what someone says out loud. A UUID is an implementation detail that
    happens to be in a URL. Both are accepted — the web already holds UUIDs and
    should not have to translate.

    The key is matched case-insensitively. Keys are unique per *owner*, not
    globally, so under the sharing lens "VIC-1" can exist in two visible
    projects; the caller's own project wins, which keeps the identifier stable
    for the person who minted it.
    """
    ref = (ref or "").strip()
    try:
        return get_task(db, user_id, UUID(ref), sharing=sharing)
    except ValueError:
        pass
    match = _IDENTIFIER_RE.match(ref)
    if match is None:
        return None
    key, number = match.group(1), int(match.group(2))
    return (
        db.query(Task)
        .options(selectinload(Task.labels))
        .join(Project, Project.id == Task.project_id)
        .filter(
            _visible_task_filter(user_id, sharing=sharing),
            func.upper(Project.key) == key.upper(),
            Task.number == number,
        )
        .order_by(case((Project.user_id == user_id, 0), else_=1))
        .first()
    )


def _task_role(
    db: Session, user_id: UUID, task: Task, project: Project | None, *, sharing: bool
) -> Role | None:
    """The caller's role on the task: its project's role, or — for an unfiled
    task, which only its owner can see — ``owner``."""
    if project is None:
        return "owner" if task.user_id == user_id else None
    return _role_for(db, user_id, project, sharing=sharing, grant_scope="tasks")


def _require_task_editor(
    db: Session, user_id: UUID, task: Task, *, sharing: bool
) -> Project | None:
    """The task's project (None when unfiled), after asserting the caller may
    change the task."""
    project = db.get(Project, task.project_id) if task.project_id else None
    access.require(_task_role(db, user_id, task, project, sharing=sharing), "editor")
    return project


def update_task(
    db: Session,
    user_id: UUID,
    task_id: UUID,
    fields: dict,
    *,
    sharing: bool = False,
) -> Task | None:
    """Apply the explicitly-sent PATCH fields. None when not visible; editing
    needs `editor` on the task's project (and on the target project of a move)."""
    task = get_task(db, user_id, task_id, sharing=sharing)
    if task is None:
        return None
    project = _require_task_editor(db, user_id, task, sharing=sharing)

    if "project_id" in fields:
        project_id = fields.pop("project_id")
        target: Project | None = None
        if project_id is not None:
            target = _get_project(
                db,
                user_id,
                project_id,
                sharing=sharing,
                grant_scope="tasks",
                minimum="editor",
            )
            if target is None:
                raise ProjectNotFoundError("Project not found")
        # Unfiled = the caller's own; ownership follows the project otherwise.
        new_owner = target.user_id if target is not None else user_id
        if new_owner != task.user_id:
            # The move crosses an ownership boundary, and ownership follows the
            # project (below), so this hands the task to somebody else.
            #
            # `editor` is not enough. An editor grantee is trusted to
            # reorganise tasks *within* the boards they were given — but
            # `project_id: null` makes the task *their own* unfiled task, and
            # any project they own satisfies an `editor` floor trivially, so an
            # editor could otherwise pull someone else's task (plus its
            # comments and activity) onto a board the original owner cannot
            # see. The owner's `visible_project_select` would no longer match
            # it and the task would be gone for good.
            access.require(
                _task_role(db, user_id, task, project, sharing=sharing), "owner"
            )
        target_id = target.id if target is not None else None
        if target_id != task.project_id:
            # Moving a task reassigns BOTH halves of its identifier — GitHub does
            # the same on issue transfer, and D-B accepts the cost: "VIC-42"
            # written in an old comment goes stale. The number it vacates is
            # never reused; counters only ever climb. Moving OUT to No project
            # drops the identifier altogether (there is no project to scope it).
            #
            # The child rows carry a denormalized project_id (so the project
            # access predicate needs no join), so they have to move too — a
            # comment left pointing at the old project would be readable
            # through a grant on a project it no longer belongs to.
            if target is not None:
                ensure_project_key_committed(db, target)
            for model in (TaskComment, TaskActivity):
                db.query(model).filter(model.task_id == task.id).update(
                    {"project_id": target_id}, synchronize_session=False
                )
            task.project_id = target_id
            # Ownership follows the project (module docstring).
            task.user_id = new_owner
            task.number = (
                allocate_task_number(db, target) if target is not None else None
            )
            project = target

    if "parent_task_id" in fields:
        parent_id = fields.pop("parent_task_id")
        if parent_id is not None:
            _validate_parent(db, user_id, task.id, parent_id, sharing=sharing)
        task.parent_task_id = parent_id

    if "label_ids" in fields:
        label_ids = fields.pop("label_ids") or []
        task.labels = _resolve_labels(
            db, user_id, label_ids, project=project, sharing=sharing
        )

    # The assignee pair moves together (the request model enforces that both are
    # present or both null), so one branch applies both columns.
    if "assignee_type" in fields or "assignee_id" in fields:
        assignee_type = fields.pop("assignee_type", task.assignee_type)
        assignee_id = fields.pop("assignee_id", task.assignee_id)
        _validate_assignee(
            db, user_id, project, assignee_type, assignee_id, sharing=sharing
        )
        task.assignee_type = assignee_type
        task.assignee_id = assignee_id
        if assignee_type == "user" and assignee_id is not None:
            from .task_timeline_queries import subscribe

            subscribe(db, task.id, assignee_id, "assignee")

    for key in (
        "title",
        "description",
        "status",
        "priority",
        "position",
        "start_date",
        "due_date",
    ):
        if key in fields:
            setattr(task, key, fields[key])
    db.commit()
    return task


def delete_task(
    db: Session, user_id: UUID, task_id: UUID, *, sharing: bool = False
) -> bool:
    """Delete a visible task. Needs `editor` on its project."""
    task = get_task(db, user_id, task_id, sharing=sharing)
    if task is None:
        return False
    _require_task_editor(db, user_id, task, sharing=sharing)
    db.delete(task)
    db.commit()
    return True
