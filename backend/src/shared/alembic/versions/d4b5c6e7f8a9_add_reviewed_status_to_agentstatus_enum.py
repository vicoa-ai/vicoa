"""Add REVIEWED status to AgentStatus enum

Revision ID: d4b5c6e7f8a9
Revises: c1d2e3f4g5h6
Create Date: 2025-08-14 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d4b5c6e7f8a9"
down_revision: Union[str, None] = "c1d2e3f4g5h6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE agentstatus ADD VALUE IF NOT EXISTS 'REVIEWED'")


def downgrade() -> None:
    # PostgreSQL enum values are not safely removable without recreating the type.
    pass
