"""add project column to agent_instances

Revision ID: 90043c6e8914
Revises: 8b7b1f0f1d23
Create Date: 2025-11-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "90043c6e8914"
down_revision: Union[str, None] = "8b7b1f0f1d23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add project column to agent_instances table
    # Can be a local directory path or remote git repository URL
    # Currently used for directory paths, designed to support git repos in the future
    op.add_column(
        "agent_instances",
        sa.Column("project", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    # Remove project column from agent_instances table
    op.drop_column("agent_instances", "project")
