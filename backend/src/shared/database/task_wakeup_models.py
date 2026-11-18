"""Task wakeups — an agent waiting on a task until something happens.

plans/todos/task-questions-waiting-on.md. A `TaskWakeup` says "wake this agent
on this task when <condition>". When the condition happens the wakeup *fires*:
it queues a dispatch (`task_dispatches`) into the agent's task session, the
same queue an assignment or a comment feeds, and stops waiting.

v1 has one kind, `reply`: wait for one person to comment on the task. It is
what `vicoa task comment --ask` creates beside the question comment, and the
only kind that means "waiting on a person": "Waiting on Nick", the push, and
the "Waiting on me" filter read reply wakeups only. A later kind (a time, a
sub-task finishing) is the agent waiting on something else, and must not show
there.

Matching happens in the task query layer (`shared/task_wakeups.py`), inside
the write's transaction, like every other dispatch trigger. A wakeup only ever
fires on a person's action, so nothing an agent does can wake an agent.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base

# What a wakeup waits for. `reply`: a comment by `wait_for_user_id`.
TASK_WAKEUP_KINDS = ("reply",)
# waiting → fired (its condition happened; the agent was asked to act)
# waiting → ended (it stopped waiting without firing; see the reasons)
TASK_WAKEUP_STATES = ("waiting", "fired", "ended")
# Why a wakeup ended without firing. `unblocked`: the task left `blocked`.
# `delivered`: it entered `in_review`. `task_closed`: done or cancelled.
# `deleted`: the comment that asked was deleted. In each the agent no longer
# needs the answer, or can't be given it.
TASK_WAKEUP_END_REASONS = ("unblocked", "delivered", "task_closed", "deleted")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class TaskWakeup(Base):
    __tablename__ = "task_wakeups"
    __table_args__ = (
        CheckConstraint(
            f"kind IN ({_in(TASK_WAKEUP_KINDS)})", name="ck_task_wakeups_kind"
        ),
        CheckConstraint(
            f"state IN ({_in(TASK_WAKEUP_STATES)})", name="ck_task_wakeups_state"
        ),
        CheckConstraint(
            f"ended_reason IS NULL OR ended_reason IN ({_in(TASK_WAKEUP_END_REASONS)})",
            name="ck_task_wakeups_ended_reason",
        ),
        CheckConstraint(
            "kind <> 'reply' OR wait_for_user_id IS NOT NULL",
            name="ck_task_wakeups_reply_has_person",
        ),
        # "Waiting on me": the reply wakeups still waiting on one person.
        # Partial, like every index here: a wakeup waits briefly and is then
        # history nobody looks up by person again.
        Index(
            "ix_task_wakeups_waiting_person",
            "wait_for_user_id",
            postgresql_where=text("state = 'waiting'"),
        ),
        # A task's waiting wakeups: what a comment or a status change matches.
        Index(
            "ix_task_wakeups_waiting_task",
            "task_id",
            postgresql_where=text("state = 'waiting'"),
        ),
        # Backs the FK's SET NULL, and the timeline's "is this comment a
        # question" lookup.
        Index(
            "ix_task_wakeups_source_comment",
            "source_comment_id",
            postgresql_where=text("source_comment_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    # The task's owner. Every query on this table filters by it or by a task
    # already resolved through the scoped task queries.
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    # The agent that waits, and that firing wakes.
    agent_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
    )
    kind: Mapped[str] = mapped_column(String(16), default="reply")
    # kind `reply`: whose comment it waits for. CASCADE: a deleted account
    # can't answer, so nothing waits on it.
    wait_for_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
        default=None,
    )
    # The comment that asked: the question, whose thread an answer belongs in.
    source_comment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("task_comments.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
        default=None,
    )
    # The session that registered it (`vicoa task comment --ask` inside it).
    created_in_instance_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
        default=None,
    )
    state: Mapped[str] = mapped_column(String(16), default="waiting")
    # Set when state is `ended`.
    ended_reason: Mapped[str | None] = mapped_column(String(16), default=None)
    # Set when it fired: the dispatch it queued. NULL when the agent could not
    # be started (archived, say): the condition still happened.
    dispatch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("task_dispatches.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
        default=None,
    )
    # kind `reply`, fired: the comment that answered.
    fired_by_comment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("task_comments.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    # When it stopped waiting, by firing or ending.
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
