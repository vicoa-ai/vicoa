"""DB queries for the projects & tasks tracker (tasks-and-projects plan §3).

All queries are user-scoped. The Inbox project is the per-user "No project"
bucket: lazily created, never archivable or deletable.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session, selectinload

from shared.database import (
    Machine,
    Project,
    ProjectDirectory,
    Task,
    TaskLabel,
    get_or_create_inbox,
)
from shared.database.project_matching import backfill_project_id_for_directory


class InboxImmutableError(Exception):
    """Raised when a request tries to archive or delete the Inbox project."""


class MachineNotFoundError(Exception):
    """Raised when a referenced machine doesn't exist or isn't the user's."""


class ProjectNotFoundError(Exception):
    """Raised when a referenced project doesn't exist or isn't the user's."""


class LabelNotFoundError(Exception):
    """Raised when a referenced label doesn't exist or isn't the user's."""


class ParentTaskError(Exception):
    """Raised when a parent_task_id is missing, foreign, or would cycle.

    `not_found` distinguishes 404 (unknown/foreign task) from 400
    (self-parent or cycle)."""

    def __init__(self, message: str, not_found: bool = False):
        super().__init__(message)
        self.not_found = not_found


def list_projects(
    db: Session, user_id: UUID, include_archived: bool = False
) -> list[Project]:
    """All the user's projects, Inbox first then by name.

    Lazily creates the Inbox so clients always have the "No project" bucket
    to group by.
    """
    get_or_create_inbox(db, user_id)
    db.commit()

    query = db.query(Project).filter(Project.user_id == user_id)
    if not include_archived:
        query = query.filter(Project.is_archived.is_(False))
    return query.order_by(Project.is_inbox.desc(), Project.name.asc()).all()


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


def _get_project(db: Session, user_id: UUID, project_id: UUID) -> Project | None:
    return (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == user_id)
        .first()
    )


def update_project(
    db: Session, user_id: UUID, project_id: UUID, fields: dict
) -> Project | None:
    """Apply the explicitly-sent PATCH fields. None when not found/not owned."""
    project = _get_project(db, user_id, project_id)
    if project is None:
        return None
    if project.is_inbox and fields.get("is_archived"):
        raise InboxImmutableError("The Inbox project cannot be archived")

    if "is_archived" in fields:
        archived = bool(fields.pop("is_archived"))
        if archived != project.is_archived:
            project.is_archived = archived
            project.archived_at = datetime.now(timezone.utc) if archived else None
    for key in ("name", "color", "icon", "git_remote_url"):
        if key in fields:
            setattr(project, key, fields[key])
    db.commit()
    return project


def delete_project(db: Session, user_id: UUID, project_id: UUID) -> bool:
    """Delete a project; its tasks go with it (FK CASCADE). False = not found."""
    project = _get_project(db, user_id, project_id)
    if project is None:
        return False
    if project.is_inbox:
        raise InboxImmutableError("The Inbox project cannot be deleted")
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
) -> Project | None:
    """Link (or relink) a project to a path on one machine.

    Upsert on (project_id, machine_id) — the table allows one row per pair, so
    re-linking a machine overwrites its path instead of adding a second row.
    Returns the refreshed project, or None when the project isn't the user's.
    """
    project = _get_project(db, user_id, project_id)
    if project is None:
        return None
    # Inbox is the "No project" bucket for unfiled tasks; a directory there
    # would silently attach itself to every task the user never filed.
    if project.is_inbox:
        raise InboxImmutableError("The Inbox project cannot be linked to a directory")

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
    db: Session, user_id: UUID, project_id: UUID, machine_id: UUID
) -> Project | None:
    """Unlink a machine from a project. None when the project isn't the user's."""
    project = _get_project(db, user_id, project_id)
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
        db.delete(row)
        db.commit()
        db.refresh(project)
    return project


# --- Labels ---------------------------------------------------------------


def list_labels(db: Session, user_id: UUID) -> list[TaskLabel]:
    return (
        db.query(TaskLabel)
        .filter(TaskLabel.user_id == user_id)
        .order_by(TaskLabel.name.asc())
        .all()
    )


def create_label(db: Session, user_id: UUID, name: str, color: str) -> TaskLabel:
    label = TaskLabel(user_id=user_id, name=name, color=color)
    db.add(label)
    db.commit()
    return label


def update_label(
    db: Session, user_id: UUID, label_id: UUID, fields: dict
) -> TaskLabel | None:
    label = (
        db.query(TaskLabel)
        .filter(TaskLabel.id == label_id, TaskLabel.user_id == user_id)
        .first()
    )
    if label is None:
        return None
    for key in ("name", "color"):
        if key in fields and fields[key] is not None:
            setattr(label, key, fields[key])
    db.commit()
    return label


def delete_label(db: Session, user_id: UUID, label_id: UUID) -> bool:
    label = (
        db.query(TaskLabel)
        .filter(TaskLabel.id == label_id, TaskLabel.user_id == user_id)
        .first()
    )
    if label is None:
        return False
    db.delete(label)
    db.commit()
    return True


def _resolve_labels(
    db: Session, user_id: UUID, label_ids: list[UUID]
) -> list[TaskLabel]:
    if not label_ids:
        return []
    labels = (
        db.query(TaskLabel)
        .filter(TaskLabel.id.in_(label_ids), TaskLabel.user_id == user_id)
        .all()
    )
    if len(labels) != len(set(label_ids)):
        raise LabelNotFoundError("Label not found")
    return labels


def _validate_parent(
    db: Session, user_id: UUID, task_id: UUID | None, parent_id: UUID
) -> None:
    """Parent must be the user's own task; reject self-parenting and cycles."""
    if task_id is not None and parent_id == task_id:
        raise ParentTaskError("A task cannot be its own parent")
    parent = get_task(db, user_id, parent_id)
    if parent is None:
        raise ParentTaskError("Parent task not found", not_found=True)
    # Walk up the ancestor chain; hitting task_id means the new edge closes
    # a cycle. Bounded by the chain length (no cycles exist beforehand).
    seen: set[UUID] = set()
    current = parent.parent_task_id
    while current is not None and current not in seen:
        if task_id is not None and current == task_id:
            raise ParentTaskError("This would create a sub-task cycle")
        seen.add(current)
        row = (
            db.query(Task.parent_task_id)
            .filter(Task.id == current, Task.user_id == user_id)
            .first()
        )
        current = row[0] if row else None


# --- Tasks ------------------------------------------------------------------


def list_tasks(
    db: Session,
    user_id: UUID,
    project_id: UUID | None = None,
    status: str | None = None,
    priority: str | None = None,
) -> list[Task]:
    """The user's tasks ordered by position (board/list order), then age."""
    query = (
        db.query(Task)
        .options(selectinload(Task.labels))
        .filter(Task.user_id == user_id)
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
) -> Task:
    """Create a task; without an explicit project it lands in the Inbox."""
    if project_id is None:
        project = get_or_create_inbox(db, user_id)
    else:
        project = _get_project(db, user_id, project_id)
        if project is None:
            raise ProjectNotFoundError("Project not found")

    if parent_task_id is not None:
        _validate_parent(db, user_id, None, parent_task_id)

    task = Task(
        user_id=user_id,
        project_id=project.id,
        title=title,
        description=description,
        status=status,
        priority=priority,
        position=position,
        parent_task_id=parent_task_id,
        start_date=start_date,
        due_date=due_date,
    )
    if label_ids:
        task.labels = _resolve_labels(db, user_id, label_ids)
    db.add(task)
    db.commit()
    return task


def get_task(db: Session, user_id: UUID, task_id: UUID) -> Task | None:
    return (
        db.query(Task)
        .options(selectinload(Task.labels))
        .filter(Task.id == task_id, Task.user_id == user_id)
        .first()
    )


def update_task(db: Session, user_id: UUID, task_id: UUID, fields: dict) -> Task | None:
    """Apply the explicitly-sent PATCH fields. None when not found/not owned."""
    task = get_task(db, user_id, task_id)
    if task is None:
        return None

    if "project_id" in fields:
        project_id = fields.pop("project_id")
        if project_id is None:
            project = get_or_create_inbox(db, user_id)
        else:
            project = _get_project(db, user_id, project_id)
            if project is None:
                raise ProjectNotFoundError("Project not found")
        task.project_id = project.id

    if "parent_task_id" in fields:
        parent_id = fields.pop("parent_task_id")
        if parent_id is not None:
            _validate_parent(db, user_id, task.id, parent_id)
        task.parent_task_id = parent_id

    if "label_ids" in fields:
        label_ids = fields.pop("label_ids") or []
        task.labels = _resolve_labels(db, user_id, label_ids)

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


def delete_task(db: Session, user_id: UUID, task_id: UUID) -> bool:
    task = get_task(db, user_id, task_id)
    if task is None:
        return False
    db.delete(task)
    db.commit()
    return True
