"""Share links: public / authenticated read links for sessions and projects

Collaboration plan §3.4 (P4). One new table, no changes to existing ones.

Revision ID: d4e8f1a2b6c9
Revises: b7c3e9a1d5f2
Create Date: 2026-09-17

Purely additive and touches no ORM model that existing queries enumerate, so
the deploy-time blast radius is nil either way — but keep the standing rule
(collaboration §10.10): run ``alembic upgrade head`` BEFORE the backend deploy.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4e8f1a2b6c9"
down_revision = "b7c3e9a1d5f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "share_links",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("token", sa.String(length=43), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("agent_instance_id", sa.UUID(), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("audience", sa.String(length=16), nullable=False),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "allow_comments",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('session','project_sessions','project_board')",
            name="ck_share_links_kind",
        ),
        sa.CheckConstraint(
            "audience IN ('public','authenticated')",
            name="ck_share_links_audience",
        ),
        sa.CheckConstraint(
            "(kind = 'session') = (agent_instance_id IS NOT NULL)",
            name="ck_share_links_session_target",
        ),
        sa.CheckConstraint(
            "(kind <> 'session') = (project_id IS NOT NULL)",
            name="ck_share_links_project_target",
        ),
        sa.CheckConstraint(
            "NOT allow_comments OR audience = 'authenticated'",
            name="ck_share_links_comments_need_auth",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["agent_instance_id"], ["agent_instances.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_share_links_token"),
    )
    op.create_index(
        "ix_share_links_instance",
        "share_links",
        ["agent_instance_id"],
        postgresql_where=sa.text("agent_instance_id IS NOT NULL"),
    )
    op.create_index(
        "ix_share_links_project",
        "share_links",
        ["project_id"],
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )
    op.create_index("ix_share_links_created_by", "share_links", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_share_links_created_by", table_name="share_links")
    op.drop_index(
        "ix_share_links_project",
        table_name="share_links",
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )
    op.drop_index(
        "ix_share_links_instance",
        table_name="share_links",
        postgresql_where=sa.text("agent_instance_id IS NOT NULL"),
    )
    op.drop_table("share_links")
