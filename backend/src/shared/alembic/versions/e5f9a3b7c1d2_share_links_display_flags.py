"""Share links: per-link display flags (show_owner, show_branch)

Collaboration §3.4 (P4 follow-up). Two nullable-free booleans, both false by
default, so every existing link keeps behaving as before: the viewer page
stops showing the owner's name and the branch until a link opts in.

Revision ID: e5f9a3b7c1d2
Revises: d4e8f1a2b6c9
Create Date: 2026-09-18

Additive; run ``alembic upgrade head`` BEFORE the backend deploy (§10.10).
"""

import sqlalchemy as sa
from alembic import op

revision = "e5f9a3b7c1d2"
down_revision = "d4e8f1a2b6c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "share_links",
        sa.Column(
            "show_owner",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "share_links",
        sa.Column(
            "show_branch",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("share_links", "show_branch")
    op.drop_column("share_links", "show_owner")
