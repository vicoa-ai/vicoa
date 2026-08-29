"""add automations and automation_runs

Scheduled agent runs (plans/todos/automation-scheduled-tasks.md): an automation
is a saved prompt + agent/model + machine/folder that fires an agent session on a
schedule (one-time or 5-field cron + IANA tz). automation_runs is the per-dispatch
history. Status/kind are varchar + CHECK (task_models style); timestamps are
timestamptz. Plain DDL only — realtime is delivered via the app-code WebSocket
path, never the database event bus (websocket-freeze).

Revision ID: d5f8a2c1b9e4
Revises: b7c4e9f21a35
Create Date: 2026-07-31 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d5f8a2c1b9e4"
down_revision: Union[str, None] = "b7c4e9f21a35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "automations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("machine_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("directory", sa.Text(), nullable=False),
        sa.Column(
            "session_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("schedule_kind", sa.String(length=20), nullable=False),
        sa.Column("cron_expression", sa.Text(), nullable=True),
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="UTC",
        ),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(length=20), nullable=True),
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
            "schedule_kind IN ('once','recurring')",
            name="ck_automations_schedule_kind",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["machine_id"], ["machines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automations_user", "automations", ["user_id"], unique=False)
    op.create_index(
        "ix_automations_next_run", "automations", ["next_run_at"], unique=False
    )

    op.create_table(
        "automation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("automation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_instance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("planned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fired_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('fired','missed_offline','failed','skipped')",
            name="ck_automation_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["automation_id"], ["automations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["agent_instance_id"], ["agent_instances.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_automation_runs_automation",
        "automation_runs",
        ["automation_id", "planned_at"],
        unique=False,
    )
    op.create_index(
        "ix_automation_runs_user", "automation_runs", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_automation_runs_user", table_name="automation_runs")
    op.drop_index("ix_automation_runs_automation", table_name="automation_runs")
    op.drop_table("automation_runs")
    op.drop_index("ix_automations_next_run", table_name="automations")
    op.drop_index("ix_automations_user", table_name="automations")
    op.drop_table("automations")
