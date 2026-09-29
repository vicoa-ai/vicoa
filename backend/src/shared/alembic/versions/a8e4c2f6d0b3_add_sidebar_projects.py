"""add sidebar_projects (shared projects a viewer added to their own list)

A project shared with you can be added to your sidebar's
project list, where it and its sessions show the way your own projects do,
instead of only under "Shared with me". One row per (viewer, project) added.
Its own table rather than a flag on ``project_positions``: that table is
rewritten whole on every drag, and being in the list has to survive a
reorder. Rows cascade with both the user and the project. Additive only.

Revision ID: a8e4c2f6d0b3
Revises: c3d9e5a7b1f4
Create Date: 2026-09-29 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a8e4c2f6d0b3"
down_revision: Union[str, None] = "c3d9e5a7b1f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sidebar_projects",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "project_id"),
    )
    op.create_index("ix_sidebar_projects_project", "sidebar_projects", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_sidebar_projects_project", table_name="sidebar_projects")
    op.drop_table("sidebar_projects")
