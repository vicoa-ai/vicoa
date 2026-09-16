"""Add users.avatar_emoji

Collaboration P1 follow-on. A user can already upload an avatar image; this lets
them pick an emoji instead, which `<PrincipalAvatar>` renders between the image
and the generated initial. Same column shape as `agent_profiles.emoji` and
`projects.icon`, so the three principals stay interchangeable in the UI.

Revision ID: d5b03ac71e64
Revises: afb81952c1a3
Create Date: 2026-09-09 10:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5b03ac71e64"
down_revision: Union[str, None] = "afb81952c1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("avatar_emoji", sa.String(length=16), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "avatar_emoji")
