"""add project directories

Links a project to where its code lives, per machine. One row per
(project, machine) so the new-session directory resolver has an unambiguous
answer for the selected machine; a project checked out on several machines
gets one row each.

Revision ID: e3f9a2b4d6c8
Revises: d2e8f3a1c5b7
Create Date: 2026-07-24 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e3f9a2b4d6c8"
down_revision: Union[str, None] = "d2e8f3a1c5b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_directories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("machine_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("local_path", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["machine_id"], ["machines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "machine_id", name="uq_project_directories_project_machine"
        ),
    )
    op.create_index(
        "ix_project_directories_project",
        "project_directories",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_directories_user",
        "project_directories",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_project_directories_user", table_name="project_directories")
    op.drop_index("ix_project_directories_project", table_name="project_directories")
    op.drop_table("project_directories")
