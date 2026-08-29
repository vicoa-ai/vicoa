"""Make message_attachments width/height nullable for non-image files

Revision ID: b7c4e9f21a35
Revises: e3f9a2b4d6c8
Create Date: 2026-07-27 00:00:00.000000

File upload extends attachments beyond images. Non-image files have no pixel
dimensions, so width/height must accept NULL.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b7c4e9f21a35"
down_revision: Union[str, None] = "e3f9a2b4d6c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "message_attachments", "width", existing_type=sa.Integer(), nullable=True
    )
    op.alter_column(
        "message_attachments", "height", existing_type=sa.Integer(), nullable=True
    )


def downgrade() -> None:
    # Non-image rows have no dimensions; 0 is the only safe sentinel to let the
    # NOT NULL constraint be re-applied.
    op.execute("UPDATE message_attachments SET width = 0 WHERE width IS NULL")
    op.execute("UPDATE message_attachments SET height = 0 WHERE height IS NULL")
    op.alter_column(
        "message_attachments", "width", existing_type=sa.Integer(), nullable=False
    )
    op.alter_column(
        "message_attachments", "height", existing_type=sa.Integer(), nullable=False
    )
