"""add project_follows (shared projects a user follows into their own list)

A project shared with you can be followed: it moves from "Shared with me" into
your own project list, other people's sessions in it under its Team row. One
row per (user, project) followed; your own projects never need one. Its own
table rather than a flag on ``project_positions``: that table is rewritten
whole on every drag, and following has to survive a reorder. Rows cascade
with both the user and the project. Additive only.

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
        "project_follows",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "project_id"),
    )
    op.create_index("ix_project_follows_project", "project_follows", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_project_follows_project", table_name="project_follows")
    op.drop_table("project_follows")
