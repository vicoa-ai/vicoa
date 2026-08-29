"""add slash_commands table

Revision ID: a1b2c3d4e5f6
Revises: 90043c6e8914
Create Date: 2025-12-06 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "90043c6e8914"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "slash_commands",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_type", sa.String(length=50), nullable=False),
        sa.Column("commands", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "agent_type"),
    )
    op.create_index(
        "ix_slash_commands_user_agent",
        "slash_commands",
        ["user_id", "agent_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_slash_commands_user_agent", table_name="slash_commands")
    op.drop_table("slash_commands")
