"""add machines.hardware_id

Stable per-host token (SHA-256 of the OS hardware id) the CLI sends on
register. Combined with a partial unique index on (user_id, hardware_id), it
lets the register endpoint dedup a machine to a stable row so re-auth / key
rotation (which change the client-derived machine_id) resolve to the same
machine instead of provisioning a duplicate.

Revision ID: 8b066f39526b
Revises: a3f2c9d41e88
Create Date: 2026-07-13 12:41:10.623525

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "8b066f39526b"
down_revision: Union[str, None] = "a3f2c9d41e88"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "machines", sa.Column("hardware_id", sa.String(length=64), nullable=True)
    )
    # One machine row per (user, physical host). Partial so the many legacy
    # rows with hardware_id IS NULL are exempt and never collide.
    op.create_index(
        "uq_machines_user_hardware",
        "machines",
        ["user_id", "hardware_id"],
        unique=True,
        postgresql_where=sa.text("hardware_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_machines_user_hardware", table_name="machines")
    op.drop_column("machines", "hardware_id")
