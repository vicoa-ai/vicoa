"""add automations.agent_instance_id (run every fire in one existing session)

An automation always started a new session per run. ``agent_instance_id``
points it at one of the author's sessions instead: each run posts the prompt
into that session, resuming it first when its agent isn't running. NULL keeps
today's behaviour, so every existing row is unchanged. CASCADE with the
session, like ``machine_id`` with its machine. Additive only.

Revision ID: 9c3e5a7b1d24
Revises: 232c080acf7c
Create Date: 2026-10-08 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9c3e5a7b1d24"
down_revision: Union[str, None] = "232c080acf7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "automations",
        sa.Column("agent_instance_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "automations_agent_instance_id_fkey",
        "automations",
        "agent_instances",
        ["agent_instance_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_automations_agent_instance", "automations", ["agent_instance_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_automations_agent_instance", table_name="automations")
    op.drop_constraint(
        "automations_agent_instance_id_fkey", "automations", type_="foreignkey"
    )
    op.drop_column("automations", "agent_instance_id")
