"""Add agent_instances.machine_id FK to machines (SET NULL)

Revision ID: 155cea2a21b0
Revises: 455a49fd3c90
Create Date: 2026-06-03 10:04:06.619547

Links a session to the machine it was spawned on (machine-management D7).
SET NULL on delete so removing a machine degrades its sessions to
"machine removed" rather than cascading the delete.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "155cea2a21b0"
down_revision: Union[str, None] = "455a49fd3c90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_instances", sa.Column("machine_id", sa.UUID(), nullable=True))
    op.create_index(
        "ix_agent_instances_machine_id",
        "agent_instances",
        ["machine_id"],
        unique=False,
    )
    op.create_foreign_key(
        "agent_instances_machine_id_fkey",
        "agent_instances",
        "machines",
        ["machine_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "agent_instances_machine_id_fkey", "agent_instances", type_="foreignkey"
    )
    op.drop_index("ix_agent_instances_machine_id", table_name="agent_instances")
    op.drop_column("agent_instances", "machine_id")
