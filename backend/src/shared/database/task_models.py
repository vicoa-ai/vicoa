"""Projects & tasks — the human-authored task tracker.

Schema per vicoa-backend/plans/projects-tasks-db-design.md and
plans/todos/tasks-and-projects-feature.md. Task status/priority are
varchar + CHECK (multica style) rather than native PG enums so the
vocabulary can grow without an enum migration; timestamps are timestamptz
(new-table convention from the DB design doc).
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Double,
    ForeignKey,
    Index,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .models import Base

if TYPE_CHECKING:
    from .models import Machine

TASK_STATUSES = (
    "backlog",
    "todo",
    "in_progress",
    "in_review",
    "done",
    "blocked",
    "cancelled",
)
TASK_PRIORITIES = ("urgent", "high", "medium", "low", "none")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_user", "user_id"),
        # Soft auto-match on remote URL (not unique — forks/local-only break that).
        Index("ix_projects_user_remote", "user_id", "git_remote_url"),
        # One Inbox per user, enforced in the DB so lazy auto-create is race-safe.
        Index(
            "uq_projects_user_inbox",
            "user_id",
            unique=True,
            postgresql_where=text("is_inbox"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    name: Mapped[str] = mapped_column(String(255))
    # Soft grouping hint for future session↔project auto-match; never unique.
    git_remote_url: Mapped[str | None] = mapped_column(Text, default=None)
    # Default agent/model/effort/mode for sessions started from this project.
    default_session_config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    color: Mapped[str | None] = mapped_column(String(16), default=None)
    icon: Mapped[str | None] = mapped_column(String(64), default=None)
    # The per-user "No project" bucket; non-archivable, non-deletable.
    is_inbox: Mapped[bool] = mapped_column(default=False)
    is_archived: Mapped[bool] = mapped_column(default=False)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Eager-loaded: every ProjectResponse carries them, and the lists are tiny
    # (one row per machine the project is checked out on).
    directories: Mapped[list["ProjectDirectory"]] = relationship(
        "ProjectDirectory",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="ProjectDirectory.created_at",
    )


class ProjectDirectory(Base):
    """Where a project's code lives on a given machine.

    A project can be checked out on several machines (laptop, desktop, cloud
    box) at different paths, so the link is per (project, machine) rather than
    a column on `projects`. At most one row per pair: the new-session directory
    resolver picks the row matching the selected machine, and two rows for one
    machine would make that ambiguous (same invariant multica enforces on its
    `local_directory` project resources).
    """

    __tablename__ = "project_directories"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "machine_id", name="uq_project_directories_project_machine"
        ),
        Index("ix_project_directories_project", "project_id"),
        Index("ix_project_directories_user", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
    )
    machine_id: Mapped[UUID] = mapped_column(
        ForeignKey("machines.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
    )
    local_path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # lazy="joined" so serializing a project's directories never fans out into
    # one SELECT per machine just to read the label below.
    machine: Mapped["Machine"] = relationship("Machine", lazy="joined")

    @property
    def machine_name(self) -> str | None:
        """Display label for the machine, mirroring the web machine picker."""
        if self.machine is None:
            return None
        return self.machine.display_name or self.machine.hostname


class TaskLabel(Base):
    """User-scoped label vocabulary (multica issue_label)."""

    __tablename__ = "task_labels"
    __table_args__ = (Index("ix_task_labels_user", "user_id"),)

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    name: Mapped[str] = mapped_column(String(100))
    # Pinned to #rrggbb by the API layer — LabelChip injects this into an
    # inline style, so the format must never loosen (multica's invariant).
    color: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


# Join table (multica issue_to_label): plain many-to-many, no payload.
task_label_links = Table(
    "task_label_links",
    Base.metadata,
    Column(
        "task_id",
        PostgresUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "label_id",
        PostgresUUID(as_uuid=True),
        ForeignKey("task_labels.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('backlog','todo','in_progress','in_review','done','blocked','cancelled')",
            name="ck_tasks_status",
        ),
        CheckConstraint(
            "priority IN ('urgent','high','medium','low','none')",
            name="ck_tasks_priority",
        ),
        CheckConstraint(
            "assignee_type IS NULL OR assignee_type IN ('user','agent')",
            name="ck_tasks_assignee_type",
        ),
        CheckConstraint(
            "creator_type IN ('user','agent')",
            name="ck_tasks_creator_type",
        ),
        Index("ix_tasks_user", "user_id"),
        Index("ix_tasks_project", "project_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    # NOT NULL — a task without an explicit project lands in the user's Inbox.
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
    )

    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)

    status: Mapped[str] = mapped_column(String(20), default="backlog")
    priority: Mapped[str] = mapped_column(String(10), default="none")
    position: Mapped[float] = mapped_column(Double, default=0)

    # Kept per DB design for the automation step; no UI in v1.
    assignee_type: Mapped[str | None] = mapped_column(String(10), default=None)
    assignee_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), default=None
    )
    creator_type: Mapped[str] = mapped_column(String(10), default="user")
    parent_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        default=None,
    )

    start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    labels: Mapped[list["TaskLabel"]] = relationship(
        "TaskLabel", secondary=task_label_links, order_by="TaskLabel.name"
    )
