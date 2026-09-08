"""add user avatar columns

Identity foundation for collaboration (P0). Mirrors the project-icon columns:
``avatar_image_uri`` is a served URL into our own storage (never an external
hot-link) and ``avatar_source`` is 'user' | 'oauth' | NULL, which is what makes
the OAuth seed safe to re-run — only a NULL source is eligible, so a user's own
upload is never clobbered.

Revision ID: c9e4b7d13f28
Revises: f4a7c2e9b1d3
Create Date: 2026-09-08 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c9e4b7d13f28"
down_revision: Union[str, None] = "f4a7c2e9b1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_image_uri", sa.Text(), nullable=True))
    op.add_column(
        "users", sa.Column("avatar_source", sa.String(length=16), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "avatar_source")
    op.drop_column("users", "avatar_image_uri")
