"""add_agent_instances_updated_at

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Branch Labels: None
Depends On: None

Create Date: 2026-05-20

The WebSocket migration (websocket-migration plan §2.6) needs a monotonic
last-modified marker on agent_instances: it is the watermark for
fetch_instances_request catch-up and the field the mutable-entity merge rule
compares. The table had started_at / ended_at / last_heartbeat_at but no
general updated_at. Existing rows are backfilled from started_at.

Also adds the (user_id, updated_at) composite indexes that the catch-up
watermark queries plan against, for both agent_instances and machines
(plan §3.2 — machines previously had only ix_machines_user_id).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_instances",
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.execute("UPDATE agent_instances SET updated_at = started_at")
    op.alter_column("agent_instances", "updated_at", nullable=False)

    op.create_index(
        "ix_agent_instances_user_updated",
        "agent_instances",
        ["user_id", "updated_at"],
    )
    op.create_index(
        "ix_machines_user_updated",
        "machines",
        ["user_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_machines_user_updated", table_name="machines")
    op.drop_index("ix_agent_instances_user_updated", table_name="agent_instances")
    op.drop_column("agent_instances", "updated_at")
