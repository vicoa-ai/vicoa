"""Task dispatches — a person handed a task, or a comment on it, to an agent.

A `TaskDispatch` is one request for an agent profile to act on a task: it was
assigned the task (Ownership mode) or a person's comment is waiting for its
answer (Reply mode). The server-side dispatcher (`servers/scheduler/
task_dispatcher.py`) claims queued rows and delivers each into the task's
session for that profile: a message when the agent is live, a resume when it
stopped, a new session when there is none or it can't be resumed.

The row is the queue *and* the record a person reads on the task ("queued",
"waiting for machine", "failed: …"), which is why it is a table rather than
something derived from tasks and messages: a dispatch that failed has to stay
visible, with its reason, until someone looks.

At most one row per (task, profile) is `queued` at a time (partial unique
index): a second trigger before the first is delivered merges into it. What is
delivered is a pointer ("new comments on VIC-12, read the thread"), never the
comment text, so merging loses nothing — the agent reads the thread as it
stands when its turn comes.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base

# Ownership: the agent was assigned the task and owns its status. Reply: answer
# the comment(s) addressed to it, leaving assignee and status alone.
TASK_DISPATCH_MODES = ("ownership", "reply")
# What a person did. `assigned`: assigned the task to the agent (or handed it
# back). `unblocked`: moved an agent-owned task out of backlog. The rest are
# comment routes (plans/todos/task-assignment-agents.md, C1); `answered` is a
# comment by the person a question of the agent's asked
# (plans/todos/task-questions-waiting-on.md).
TASK_DISPATCH_TRIGGERS = (
    "assigned",
    "unblocked",
    "mentioned",
    "replied",
    "commented",
    "answered",
)
# queued → dispatching → delivered | resumed | started | failed; queued → cancelled.
TASK_DISPATCH_STATES = (
    "queued",
    "dispatching",
    "delivered",
    "resumed",
    "started",
    "failed",
    "cancelled",
)
# States after which nothing else happens to the row.
TASK_DISPATCH_FINAL_STATES = ("delivered", "resumed", "started", "failed", "cancelled")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class TaskDispatch(Base):
    __tablename__ = "task_dispatches"
    __table_args__ = (
        CheckConstraint(
            f"mode IN ({_in(TASK_DISPATCH_MODES)})", name="ck_task_dispatches_mode"
        ),
        CheckConstraint(
            f"trigger IN ({_in(TASK_DISPATCH_TRIGGERS)})",
            name="ck_task_dispatches_trigger",
        ),
        CheckConstraint(
            f"state IN ({_in(TASK_DISPATCH_STATES)})", name="ck_task_dispatches_state"
        ),
        # The task's latest dispatch (its chip), and its history.
        Index("ix_task_dispatches_task", "task_id", "created_at"),
        # The sweep: queued rows that are due. Partial — almost every row is final.
        Index(
            "ix_task_dispatches_due",
            "next_attempt_at",
            postgresql_where=text("state = 'queued'"),
        ),
        # One pending delivery per (task, agent): a later trigger merges into it.
        Index(
            "uq_task_dispatches_queued",
            "task_id",
            "agent_profile_id",
            unique=True,
            postgresql_where=text("state = 'queued'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    # The profile's owner: whose machine runs the session and whose session it
    # is. Every query on this table filters by it.
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    agent_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
    )
    mode: Mapped[str] = mapped_column(String(16))
    trigger: Mapped[str] = mapped_column(String(16))
    # The newest comment that asked for this (Reply mode); NULL for an assignment.
    trigger_comment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("task_comments.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        default=None,
    )
    # Who asked. Not always `user_id`: a team member can comment on a board.
    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        default=None,
    )
    # Where a new session starts, chosen in the assign dialog. NULL = resolve at
    # dispatch time (profile default machine, then the project's directory).
    machine_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("machines.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        default=None,
    )
    directory: Mapped[str | None] = mapped_column(Text, default=None)
    # {"mode": "new"} | {"mode": "none"} — the automation worktree spec.
    worktree: Mapped[dict | None] = mapped_column(JSONB, default=None)

    state: Mapped[str] = mapped_column(String(16), default="queued")
    # The session it was delivered into or started.
    agent_instance_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        default=None,
    )
    # Why it is waiting or why it failed, in words a person reads on the task.
    detail: Mapped[str | None] = mapped_column(Text, default=None)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
