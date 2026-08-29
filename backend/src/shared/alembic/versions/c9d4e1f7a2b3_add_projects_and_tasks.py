"""add projects and tasks

Human-authored task tracker (plans/todos/tasks-and-projects-feature.md):
projects + tasks tables, and agent_instances.task_id backpointer so a run
of a task is an agent_instance. Status/priority are varchar + CHECK
(multica style); timestamps are timestamptz per the DB design doc.

Revision ID: c9d4e1f7a2b3
Revises: 8b066f39526b
Create Date: 2026-07-23 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c9d4e1f7a2b3"
down_revision: Union[str, None] = "8b066f39526b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("git_remote_url", sa.Text(), nullable=True),
        sa.Column(
            "default_session_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("icon", sa.String(length=64), nullable=True),
        sa.Column(
            "is_inbox", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_user", "projects", ["user_id"], unique=False)
    op.create_index(
        "ix_projects_user_remote",
        "projects",
        ["user_id", "git_remote_url"],
        unique=False,
    )
    # One Inbox per user — makes lazy auto-create race-safe.
    op.create_index(
        "uq_projects_user_inbox",
        "projects",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_inbox"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="backlog",
        ),
        sa.Column(
            "priority",
            sa.String(length=10),
            nullable=False,
            server_default="none",
        ),
        sa.Column("position", sa.Double(), nullable=False, server_default=sa.text("0")),
        sa.Column("assignee_type", sa.String(length=10), nullable=True),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "creator_type",
            sa.String(length=10),
            nullable=False,
            server_default="user",
        ),
        sa.Column("parent_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('backlog','todo','in_progress','in_review','done','blocked','cancelled')",
            name="ck_tasks_status",
        ),
        sa.CheckConstraint(
            "priority IN ('urgent','high','medium','low','none')",
            name="ck_tasks_priority",
        ),
        sa.CheckConstraint(
            "assignee_type IS NULL OR assignee_type IN ('user','agent')",
            name="ck_tasks_assignee_type",
        ),
        sa.CheckConstraint(
            "creator_type IN ('user','agent')",
            name="ck_tasks_creator_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_user", "tasks", ["user_id"], unique=False)
    op.create_index("ix_tasks_project", "tasks", ["project_id", "status"], unique=False)

    op.add_column(
        "agent_instances",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_instances_task_id",
        "agent_instances",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_agent_instances_task", "agent_instances", ["task_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_agent_instances_task", table_name="agent_instances")
    op.drop_constraint(
        "fk_agent_instances_task_id", "agent_instances", type_="foreignkey"
    )
    op.drop_column("agent_instances", "task_id")
    op.drop_index("ix_tasks_project", table_name="tasks")
    op.drop_index("ix_tasks_user", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("uq_projects_user_inbox", table_name="projects")
    op.drop_index("ix_projects_user_remote", table_name="projects")
    op.drop_index("ix_projects_user", table_name="projects")
    op.drop_table("projects")
