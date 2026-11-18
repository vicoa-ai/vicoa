"""task wakeups: an agent waits on a task until a person replies

``task_wakeups`` holds "wake this agent on this task when <condition>". v1 has
one kind, ``reply``: wait for one person's comment, which is what a question
(``vicoa task comment --ask``) registers and what "Waiting on <person>" reads.
A dispatch can now be triggered by that reply (``task_dispatches.trigger =
'answered'``). plans/todos/task-questions-waiting-on.md.

Additive only: a new table, partial indexes and a widened CHECK; no trigger, no
NOTIFY.

Revision ID: c4f7a2d9e8b1
Revises: 7d4e2a9c5b31
Create Date: 2026-11-18 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4f7a2d9e8b1"
down_revision: Union[str, None] = "7d4e2a9c5b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TRIGGERS_BEFORE = "'assigned', 'unblocked', 'mentioned', 'replied', 'commented'"
_TRIGGERS_AFTER = _TRIGGERS_BEFORE + ", 'answered'"


def upgrade() -> None:
    op.create_table(
        "task_wakeups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("wait_for_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_comment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_in_instance_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("ended_reason", sa.String(length=16), nullable=True),
        sa.Column("dispatch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fired_by_comment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('reply')", name="ck_task_wakeups_kind"),
        sa.CheckConstraint(
            "state IN ('waiting', 'fired', 'ended')", name="ck_task_wakeups_state"
        ),
        sa.CheckConstraint(
            "ended_reason IS NULL OR ended_reason IN "
            "('unblocked', 'delivered', 'task_closed', 'deleted')",
            name="ck_task_wakeups_ended_reason",
        ),
        sa.CheckConstraint(
            "kind <> 'reply' OR wait_for_user_id IS NOT NULL",
            name="ck_task_wakeups_reply_has_person",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["agent_profile_id"], ["agent_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["wait_for_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_comment_id"], ["task_comments.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_in_instance_id"], ["agent_instances.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["dispatch_id"], ["task_dispatches.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["fired_by_comment_id"], ["task_comments.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_wakeups_waiting_person",
        "task_wakeups",
        ["wait_for_user_id"],
        postgresql_where=sa.text("state = 'waiting'"),
    )
    op.create_index(
        "ix_task_wakeups_waiting_task",
        "task_wakeups",
        ["task_id"],
        postgresql_where=sa.text("state = 'waiting'"),
    )
    op.create_index(
        "ix_task_wakeups_source_comment",
        "task_wakeups",
        ["source_comment_id"],
        postgresql_where=sa.text("source_comment_id IS NOT NULL"),
    )

    op.drop_constraint("ck_task_dispatches_trigger", "task_dispatches", type_="check")
    op.create_check_constraint(
        "ck_task_dispatches_trigger",
        "task_dispatches",
        f"trigger IN ({_TRIGGERS_AFTER})",
    )


def downgrade() -> None:
    # An answer is a reply to the agent's question, as far as the older
    # vocabulary can say it.
    op.execute(
        "UPDATE task_dispatches SET trigger = 'replied' WHERE trigger = 'answered'"
    )
    op.drop_constraint("ck_task_dispatches_trigger", "task_dispatches", type_="check")
    op.create_check_constraint(
        "ck_task_dispatches_trigger",
        "task_dispatches",
        f"trigger IN ({_TRIGGERS_BEFORE})",
    )
    op.drop_index("ix_task_wakeups_source_comment", table_name="task_wakeups")
    op.drop_index("ix_task_wakeups_waiting_task", table_name="task_wakeups")
    op.drop_index("ix_task_wakeups_waiting_person", table_name="task_wakeups")
    op.drop_table("task_wakeups")
