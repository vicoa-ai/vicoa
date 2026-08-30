"""add home_dir to agent_instances

Revision ID: c1d2e3f4g5h6
Revises: b7c8d9e0f1a2
Create Date: 2025-12-16 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4g5h6"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_instances",
        sa.Column("home_dir", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_instances", "home_dir")
