"""add machine_agent_models

Revision ID: b2c3d4e5f6a7
Revises: 155cea2a21b0
Branch Labels: None
Depends On: None

Create Date: 2026-06-15

Per-machine, per-agent cache of an ACP agent's available model list, written
write-on-change from the available_models a headless wrapper reports onto
agent_instances.session_config on session/new. Lets the new-session picker show
a machine's REAL model list before a session starts (the catalog only ships
static defaults; the live list is account/version/config-specific).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "155cea2a21b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "machine_agent_models",
        sa.Column("machine_id", PostgresUUID(as_uuid=True), nullable=False),
        sa.Column("agent_type", sa.String(length=64), nullable=False),
        sa.Column("user_id", PostgresUUID(as_uuid=True), nullable=False),
        sa.Column("models", JSONB(), nullable=False),
        sa.Column("models_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["machine_id"], ["machines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("machine_id", "agent_type"),
    )
    op.create_index(
        "ix_machine_agent_models_user",
        "machine_agent_models",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_machine_agent_models_user",
        table_name="machine_agent_models",
    )
    op.drop_table("machine_agent_models")
