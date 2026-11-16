"""task dispatches: hand a task or a comment to an agent profile

``task_dispatches`` is the queue a person fills by assigning a task to an agent
profile or commenting where an agent should answer, and the record shown on the
task while it waits or after it fails (plans/todos/task-assignment-agents.md).
``agent_profiles.max_concurrent_sessions`` caps how many of a profile's task
sessions may be mid-turn at once (default 2).

Additive only: a new table and a defaulted column; no trigger, no NOTIFY.

Revision ID: 7d4e2a9c5b31
Revises: 9c3e5a7b1d24
Create Date: 2026-11-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7d4e2a9c5b31"
down_revision: Union[str, None] = "9c3e5a7b1d24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_profiles",
        sa.Column(
            "max_concurrent_sessions",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("2"),
        ),
    )

    op.create_table(
        "task_dispatches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("trigger_comment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("machine_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("directory", sa.Text(), nullable=True),
        sa.Column("worktree", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("agent_instance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mode IN ('ownership', 'reply')", name="ck_task_dispatches_mode"
        ),
        sa.CheckConstraint(
            "trigger IN ('assigned', 'unblocked', 'mentioned', 'replied', 'commented')",
            name="ck_task_dispatches_trigger",
        ),
        sa.CheckConstraint(
            "state IN ('queued', 'dispatching', 'delivered', 'resumed', 'started',"
            " 'failed', 'cancelled')",
            name="ck_task_dispatches_state",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["agent_profile_id"], ["agent_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["trigger_comment_id"], ["task_comments.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["machine_id"], ["machines.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["agent_instance_id"], ["agent_instances.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_dispatches_task", "task_dispatches", ["task_id", "created_at"]
    )
    op.create_index(
        "ix_task_dispatches_due",
        "task_dispatches",
        ["next_attempt_at"],
        postgresql_where=sa.text("state = 'queued'"),
    )
    op.create_index(
        "uq_task_dispatches_queued",
        "task_dispatches",
        ["task_id", "agent_profile_id"],
        unique=True,
        postgresql_where=sa.text("state = 'queued'"),
    )


def downgrade() -> None:
    op.drop_index("uq_task_dispatches_queued", table_name="task_dispatches")
    op.drop_index("ix_task_dispatches_due", table_name="task_dispatches")
    op.drop_index("ix_task_dispatches_task", table_name="task_dispatches")
    op.drop_table("task_dispatches")
    op.drop_column("agent_profiles", "max_concurrent_sessions")
