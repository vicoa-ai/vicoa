"""Add STARTING status to AgentStatus enum

Revision ID: a3f9b2c1d4e5
Revises: e1a42f472efc
Create Date: 2026-04-25 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a3f9b2c1d4e5"
down_revision: Union[str, None] = "e1a42f472efc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE agentstatus ADD VALUE IF NOT EXISTS 'STARTING'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; handle manually if needed
    pass
