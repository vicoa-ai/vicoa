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
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
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

# Task-depth vocabularies (collaboration plan §3.5).
COMMENT_AUTHOR_TYPES = ("user", "agent")
COMMENT_KINDS = ("comment", "system")
REACTION_TARGET_TYPES = ("task", "comment")
ACTIVITY_ACTOR_TYPES = ("user", "agent", "system")
SUBSCRIBER_REASONS = ("creator", "assignee", "commenter", "mentioned", "manual")

# Reactions are open-ended: the client offers a curated set plus the full
# Unicode picker, so an allowlist here would only be a second, staler list to
# keep in step. What IS enforced (`shared.database.reactions.is_emoji`) is that
# the value is an emoji at all — the column is a free varchar, and letting
# arbitrary text through would make it a junk-data and rendering vector.

# Every `action` the activity listener can emit. Kept as a tuple (not a CHECK)
# because the vocabulary grows with the UI and a stale CHECK would 500 a write
# rather than degrade to an unrendered row.
ACTIVITY_ACTIONS = (
    "created",
    "status_changed",
    "priority_changed",
    "assigned",
    "title_changed",
    "description_changed",
    "label_added",
    "label_removed",
    "due_date_set",
    "start_date_set",
    "project_changed",
    "parent_changed",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_user", "user_id"),
        # Soft auto-match on remote URL (not unique — forks/local-only break that).
        Index("ix_projects_user_remote", "user_id", "git_remote_url"),
        # DEPRECATED: the per-user Inbox row is gone ("No project" is NULL —
        # see the tasks_no_project migration). The column and this index stay
        # one release so clients that still read `is_inbox` see `false`; both
        # are dropped in a follow-up migration.
        Index(
            "uq_projects_user_inbox",
            "user_id",
            unique=True,
            postgresql_where=text("is_inbox"),
        ),
        # The task key namespace (§3.5 / D-B): "VIC" makes tasks read "VIC-42".
        # Unique within the OWNER, never globally — a global key namespace would
        # re-import the squatting/enumeration problems §3.2 avoids for team slugs.
        # The owner is the user for a personal project and the team for a
        # team-owned one, hence two partial indexes over the same expression.
        Index(
            "uq_projects_user_key",
            "user_id",
            func.upper(text("key")),
            unique=True,
            postgresql_where=text("key IS NOT NULL AND team_id IS NULL"),
        ),
        Index(
            "uq_projects_team_key",
            "team_id",
            func.upper(text("key")),
            unique=True,
            postgresql_where=text("key IS NOT NULL AND team_id IS NOT NULL"),
        ),
        Index(
            "ix_projects_team",
            "team_id",
            postgresql_where=text("team_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    # Ownership (collaboration §2, layer 2). NULL ⇒ personal, owned by
    # `user_id`. SET ⇒ team-owned: access derives from team membership and
    # `user_id` degrades to "created by". ON DELETE SET NULL, so deleting a team
    # demotes its projects back to the creator's personal space rather than
    # destroying work. Nothing sets it before P7; the resolver honours it now.
    team_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
        default=None,
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
    # Image icon (project-identity-unification §4d): a served URL pointing at
    # OUR storage (never an external hot-link), plus who set it. icon_source
    # governs precedence and re-seed safety: 'user' (uploaded) always wins over
    # 'git' (owner avatar seeded from the remote); NULL ⇒ fall back to the emoji
    # `icon`/`color` default. The S3 object is keyed by project_id alone (not
    # user_id) so a project can later move to a team without rekeying (§9).
    icon_image_uri: Mapped[str | None] = mapped_column(Text, default=None)
    icon_source: Mapped[str | None] = mapped_column(String(16), default=None)
    # Display prefix for this project's task identifiers ("VIC" -> "VIC-42").
    # Auto-derived from the name on create, user-editable afterwards. Renaming a
    # project deliberately does NOT re-derive it: the whole point of the key is
    # that "VIC-42" written in an old commit message keeps resolving.
    key: Mapped[str | None] = mapped_column(String(8), default=None)
    # High-water mark for `tasks.number` in this project. Bumped with
    # UPDATE ... RETURNING inside the insert transaction (a per-project sequence
    # is not an option; a counter row + row lock is). Never decremented — a
    # deleted or moved-away task does not free its number.
    task_counter: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # DEPRECATED, always False: "No project" is `tasks.project_id IS NULL` /
    # `agent_instances.project_id IS NULL`, not a hidden project row. Kept one
    # release for old clients; dropped in a follow-up migration.
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


class ProjectPosition(Base):
    """A viewer's manual ordering of the projects they can see.

    One row per (user, project) the user has dragged into place; a project
    with no row for the viewer is unranked and falls back to recency. It is
    per *viewer*, not a column on `projects`: a shared or team-owned project
    appears in several people's sidebars, and how one person arranges theirs
    must not rearrange anyone else's. Rows follow the project (deleting it
    drops the rank); a project the viewer loses access to keeps a stale row
    that the list query never joins and the next full rewrite discards.
    """

    __tablename__ = "project_positions"
    __table_args__ = (Index("ix_project_positions_project", "project_id"),)

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
        primary_key=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
        primary_key=True,
    )
    # 0-based rank within the viewer's ordered projects; contiguous after
    # every rewrite, but the reader only relies on ascending order.
    position: Mapped[int] = mapped_column(Integer)


class TaskLabel(Base):
    """Label vocabulary (multica issue_label).

    Visibility = (team_id IS NULL AND user_id = me) OR (team_id ∈ my active
    teams) — collaboration §3.3. Labels are the one place sharing forces an
    ownership change: a shared board otherwise ends up with N private
    vocabularies. Zero data migration: every existing label stays personal.
    """

    __tablename__ = "task_labels"
    __table_args__ = (
        Index("ix_task_labels_user", "user_id"),
        Index(
            "ix_task_labels_team",
            "team_id",
            postgresql_where=text("team_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    # NULL ⇒ personal (user_id's own vocabulary). SET ⇒ the team's vocabulary;
    # user_id then records who created it. Same NULL/SET pattern as projects.
    team_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
        default=None,
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
        # Per-project sequential identifier. Partial because rows created before
        # the backfill (and any row whose allocation lost a race) stay NULL and
        # simply render without an identifier rather than blocking the insert.
        Index(
            "uq_tasks_project_number",
            "project_id",
            "number",
            unique=True,
            postgresql_where=text("number IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    # NULL = "No project" — the same convention as agent_instances.project_id.
    # SET NULL so a raw project delete files its tasks rather than losing them;
    # `delete_project` does the same explicitly (and clears `number`) so the
    # move is one code path whether it runs through the ORM or the FK.
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
        default=None,
    )

    # Per-project sequential number; rendered as `{project.key}-{number}`.
    # Allocated from projects.task_counter in the insert transaction. NULL for
    # a task with no project (an identifier is project-scoped, so an unfiled
    # task has none until it is moved into a project), for rows that predate
    # the backfill, and transiently while one is being allocated.
    number: Mapped[int | None] = mapped_column(Integer, default=None)

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


# ---------------------------------------------------------------------------
# Task depth — comments, reactions, activity, subscribers (collaboration §3.5)
#
# None of these tables carries `user_id`. That is deliberate and does NOT break
# the "every query filters by user_id" house rule: a comment's author need not
# be the task's owner once sharing lands, so the row has no single owning user.
# Scoping runs through the task instead — resolve it with the user-scoped
# `get_task(db, user_id, task_id)` first, then query by `task_id`. `project_id`
# is denormalized onto the child rows so P3 can add a project-level predicate
# without a join; it MUST be kept in step when a task moves project.
# ---------------------------------------------------------------------------


class TaskComment(Base):
    """A markdown comment on a task, by a user or an agent.

    Comments thread **one level deep**: a comment is either a root or a reply to
    a root, never a reply to a reply. `create_comment` enforces that by
    re-pointing a reply-to-a-reply at the thread's root rather than rejecting it,
    which is what Slack and GitHub Discussions do and for the same reason — an
    arbitrarily deep tree has to be indent-capped somewhere in the UI anyway, and
    capping it in the data keeps every client (web, mobile, CLI) rendering the
    same shape instead of each inventing its own flattening rule.
    """

    __tablename__ = "task_comments"
    __table_args__ = (
        CheckConstraint(
            "author_type IN ('user','agent')", name="ck_task_comments_author_type"
        ),
        CheckConstraint("kind IN ('comment','system')", name="ck_task_comments_kind"),
        Index("ix_task_comments_task", "task_id", "created_at"),
        Index("ix_task_comments_project", "project_id"),
        # Partial: only replies carry a parent, and the lookup is always
        # "the replies under this root", never "the roots".
        Index(
            "ix_task_comments_parent",
            "parent_comment_id",
            postgresql_where=text("parent_comment_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    # Denormalized from the task (so the project access predicate needs no
    # join); NULL when the task has no project. Follows the task on a move.
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
        default=None,
    )
    # The root this comment answers, or NULL when it *is* a root. Always points
    # at a root (see the class docstring), so `parent_comment_id IS NULL` is the
    # whole test for "is a root" and no client ever walks a chain. CASCADE is
    # unreachable in practice — a comment is soft-deleted, so the only hard
    # delete is the task's — but it keeps replies from outliving their root if
    # one ever is purged.
    parent_comment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("task_comments.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
        default=None,
    )
    # Polymorphic author: users.id or agent_profiles.id. Not an FK — the two
    # targets are different tables and a deleted principal must leave the thread
    # readable ("Deleted agent said …"), which a CASCADE would not.
    author_type: Mapped[str] = mapped_column(String(8), default="user")
    author_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16), default="comment")
    # Soft delete: removing the row outright would strand replies and reactions
    # and leave a hole in a thread other comments refer to.
    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class TaskReaction(Base):
    """One emoji from one user on one task or comment."""

    __tablename__ = "task_reactions"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('task','comment')", name="ck_task_reactions_target_type"
        ),
        UniqueConstraint(
            "target_type",
            "target_id",
            "user_id",
            "emoji",
            name="uq_task_reactions_target_user_emoji",
        ),
        Index("ix_task_reactions_target", "target_type", "target_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    # Polymorphic target (task or comment), so no FK; both parents CASCADE from
    # the task, and orphan reactions are swept with the task delete.
    target_type: Mapped[str] = mapped_column(String(8))
    target_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True))
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    # Validated as *an emoji* at the API layer, not constrained to a list: the
    # offered set is a product choice that changes, and a CHECK would need a
    # migration each time while rejecting rows an older client legitimately
    # wrote. Long enough for a ZWJ sequence with skin-tone modifiers.
    emoji: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class TaskActivity(Base):
    """A machine-generated record of one task mutation.

    Written by the ``after_flush`` listener in ``shared/database/task_activity``
    — never by a call site. Task mutations arrive from the human REST API, the
    agent-facing REST API, the automation runner and the instance-status sync;
    the flush is the one point all of them pass through.
    """

    __tablename__ = "task_activity"
    __table_args__ = (
        CheckConstraint(
            "actor_type IS NULL OR actor_type IN ('user','agent','system')",
            name="ck_task_activity_actor_type",
        ),
        Index("ix_task_activity_task", "task_id", "created_at"),
        Index("ix_task_activity_project", "project_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    # Denormalized from the task (so the project access predicate needs no
    # join); NULL when the task has no project. Follows the task on a move.
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
        default=None,
    )
    # NULL when no actor could be resolved — a background sweep with no request
    # context. Renders as an unattributed line rather than being dropped.
    actor_type: Mapped[str | None] = mapped_column(String(8), default=None)
    actor_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), default=None
    )
    action: Mapped[str] = mapped_column(String(40))
    # {"from": ..., "to": ...} for a field change. Also carries
    # `agent_instance_id` when the change came from the instance-status sync, so
    # the task-detail timeline can fold a session's status churn into that
    # session's own card instead of listing it three times.
    details: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class TaskSubscriber(Base):
    """Who gets notified about a task. One row per (task, user)."""

    __tablename__ = "task_subscribers"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('creator','assignee','commenter','mentioned','manual')",
            name="ck_task_subscribers_reason",
        ),
        Index("ix_task_subscribers_user", "user_id"),
    )

    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
        primary_key=True,
    )
    # Why they are subscribed. First reason wins — an explicit 'manual' is not
    # downgraded by a later auto-subscribe.
    reason: Mapped[str] = mapped_column(String(16), default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
