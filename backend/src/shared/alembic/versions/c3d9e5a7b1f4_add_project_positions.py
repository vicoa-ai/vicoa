"""add project_positions (per-viewer manual project order)

The sidebar's drag-and-drop project order used to live in each device's
local preferences, so it never followed the user to another browser or to
mobile. It is now a per-viewer table: one row per (user, project) the user
has ranked, ``position`` ascending. Per viewer rather than a column on
``projects`` because a shared or team-owned project sits in several people's
sidebars and one person's arrangement must not move anyone else's. Rows
cascade with both the user and the project.

Revision ID: c3d9e5a7b1f4
Revises: f50917844822
Create Date: 2026-09-20 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3d9e5a7b1f4"
down_revision: Union[str, None] = "f50917844822"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_positions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "project_id"),
    )
    op.create_index("ix_project_positions_project", "project_positions", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_project_positions_project", table_name="project_positions")
    op.drop_table("project_positions")
