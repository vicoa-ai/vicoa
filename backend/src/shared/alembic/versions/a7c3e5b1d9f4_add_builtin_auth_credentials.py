"""add user_credentials + auth_email_codes, index api_keys.api_key_hash

Backs the built-in auth provider (plans/todos/pluggable-auth-open-source.md
Phase B): with AUTH_PROVIDER=builtin a self-hosted deployment stores its own
passwords instead of delegating to Supabase. Both tables stay empty in a
Supabase-backed deployment.

The api_keys index is Phase A.4: every agent request now checks that the key's
row is still present and active, and that lookup is by hash — unindexed it would
be a sequential scan on the agent server's hottest path.

purpose is varchar + CHECK (task_models style); timestamps are timestamptz.
Plain DDL only.

Revision ID: a7c3e5b1d9f4
Revises: b2d4f6a8c0e1
Create Date: 2026-08-26 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a7c3e5b1d9f4"
down_revision: Union[str, None] = "b2d4f6a8c0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_credentials",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "auth_email_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "purpose IN ('verify_email', 'reset_password')",
            name="ck_auth_email_codes_purpose",
        ),
    )
    op.create_index(
        "ix_auth_email_codes_user_purpose",
        "auth_email_codes",
        ["user_id", "purpose"],
    )

    op.create_index("ix_api_keys_api_key_hash", "api_keys", ["api_key_hash"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_api_key_hash", table_name="api_keys")
    op.drop_index("ix_auth_email_codes_user_purpose", table_name="auth_email_codes")
    op.drop_table("auth_email_codes")
    op.drop_table("user_credentials")
