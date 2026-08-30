"""Add pinned_at to agent_instances

Revision ID: 943422f9c33b
Revises: d1e2f3a4b5c6
Create Date: 2026-05-31 14:58:07.712149

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "943422f9c33b"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_instances",
        sa.Column("pinned_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_instances", "pinned_at")
