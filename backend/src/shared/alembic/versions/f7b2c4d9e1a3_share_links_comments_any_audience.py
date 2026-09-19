"""Share links: comments no longer require the authenticated audience

Collaboration §3.4 (P4 follow-up). Whether a link is readable anonymously and
whether signed-in visitors may comment on it are two separate choices: a
public board link can take comments — from visitors who sign in — and the
resolver already grants ``allow_comments`` to a signed-in visitor only. The
check constraint that tied the two together goes; nothing else changes.

Revision ID: f7b2c4d9e1a3
Revises: e5f9a3b7c1d2
Create Date: 2026-09-18

Additive (a constraint drop); run ``alembic upgrade head`` BEFORE the backend
deploy (§10.10).
"""

from alembic import op

revision = "f7b2c4d9e1a3"
down_revision = "e5f9a3b7c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_share_links_comments_need_auth", "share_links", type_="check"
    )


def downgrade() -> None:
    # Re-tightening would reject rows minted in between; clear the flag on
    # those first so the constraint can be put back.
    op.execute(
        "UPDATE share_links SET allow_comments = false "
        "WHERE allow_comments AND audience <> 'authenticated'"
    )
    op.create_check_constraint(
        "ck_share_links_comments_need_auth",
        "share_links",
        "NOT allow_comments OR audience = 'authenticated'",
    )
