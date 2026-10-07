"""task session provenance: tasks.created_in_instance_id, task_comments.agent_instance_id

Where a task or a comment came from. ``vicoa task create`` and ``vicoa task
comment`` run inside a Vicoa session already know that session (the CLI has it
as ``VICOA_AGENT_INSTANCE_ID``); these columns keep it, so the task page can say
"Created in <session>" / "via <session>" and a session page can list the tasks
it created. Provenance only — neither column ever moves a task's status, unlike
``agent_instances.task_id``. Both are nullable FKs to ``agent_instances`` with
ON DELETE SET NULL, each with a partial index (most rows are NULL) that backs
the session page's lookup and the FK's SET NULL. Additive only; existing rows
stay NULL.

Revision ID: 232c080acf7c
Revises: 2818ec8831de
Create Date: 2026-10-08 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "232c080acf7c"
down_revision: Union[str, None] = "2818ec8831de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "created_in_instance_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.create_foreign_key(
        "tasks_created_in_instance_id_fkey",
        "tasks",
        "agent_instances",
        ["created_in_instance_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_tasks_created_in_instance",
        "tasks",
        ["created_in_instance_id"],
        postgresql_where=sa.text("created_in_instance_id IS NOT NULL"),
    )

    op.add_column(
        "task_comments",
        sa.Column("agent_instance_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "task_comments_agent_instance_id_fkey",
        "task_comments",
        "agent_instances",
        ["agent_instance_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_task_comments_agent_instance",
        "task_comments",
        ["agent_instance_id"],
        postgresql_where=sa.text("agent_instance_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_task_comments_agent_instance", table_name="task_comments")
    op.drop_constraint(
        "task_comments_agent_instance_id_fkey", "task_comments", type_="foreignkey"
    )
    op.drop_column("task_comments", "agent_instance_id")

    op.drop_index("ix_tasks_created_in_instance", table_name="tasks")
    op.drop_constraint("tasks_created_in_instance_id_fkey", "tasks", type_="foreignkey")
    op.drop_column("tasks", "created_in_instance_id")
