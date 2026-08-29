"""add agent_instances.rate_limited_until

Revision ID: b2d4f6a8c0e1
Revises: d9e4c2a7f1b8
Branch Labels: None
Depends On: None

Create Date: 2026-08-20

Server-projected column marking a session as blocked by a time-window rate limit
until a binding reset instant (NULL = not blocked). Projected from the
instance_metadata.usage blob the daemon already PATCHes each turn; set and
cleared by the same projection. Deliberately a nullable timestamp, not an
AgentStatus value — see plans/todos/auto-continue-rate-limited-sessions.md.

The partial index keeps the rate-limit sweep/filter (`?rate_limited_only=true`)
scanning only the currently-blocked rows rather than the whole table. The sweep
also excludes automation-spawned sessions via a NOT EXISTS against
automation_runs.agent_instance_id, so this migration adds an index on that
(previously unindexed) FK column — otherwise the anti-join seq-scans
automation_runs (which grows one row per dispatch), and the ON DELETE SET NULL
FK already seq-scans it on every agent_instance delete. Plain DDL; inert until
code reads the column, so safe to ship ahead of the CLI/automation.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b2d4f6a8c0e1"
down_revision: Union[str, None] = "d9e4c2a7f1b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_instances",
        sa.Column("rate_limited_until", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_agent_instances_rate_limited_until",
        "agent_instances",
        ["rate_limited_until"],
        postgresql_where=sa.text("rate_limited_until IS NOT NULL"),
    )
    # Reverse-lookup index for the sweep's anti-join and the SET NULL FK.
    op.create_index(
        "ix_automation_runs_agent_instance",
        "automation_runs",
        ["agent_instance_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_automation_runs_agent_instance",
        table_name="automation_runs",
    )
    op.drop_index(
        "ix_agent_instances_rate_limited_until",
        table_name="agent_instances",
    )
    op.drop_column("agent_instances", "rate_limited_until")
