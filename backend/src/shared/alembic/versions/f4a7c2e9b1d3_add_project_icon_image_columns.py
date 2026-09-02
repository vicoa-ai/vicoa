"""add project icon image columns

Adds the image-icon fields for the project-identity-unification plan (§4d):
``icon_image_uri`` (a served URL pointing at our own storage, never an external
hot-link) and ``icon_source`` ('user' | 'git' | NULL). The existing emoji
``icon`` + ``color`` stay as the lightweight default; ``icon_source`` governs
precedence (user upload wins) and re-seed safety.

Revision ID: f4a7c2e9b1d3
Revises: b2f6a1c8e4d7
Create Date: 2026-09-02 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f4a7c2e9b1d3"
down_revision: Union[str, None] = "b2f6a1c8e4d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects", sa.Column("icon_image_uri", sa.Text(), nullable=True)
    )
    op.add_column(
        "projects", sa.Column("icon_source", sa.String(length=16), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("projects", "icon_source")
    op.drop_column("projects", "icon_image_uri")
