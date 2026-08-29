"""add activation_nudges

Ledger for the signup-anchored activation re-engagement drip
(plans/todos/activation-improvement-roadmap.md §B; model in
shared/database/activation_models.py). One row per push/email touch, uniquely
keyed by (user_id, channel, step) so a touch sends at most once and the sweep is
safe across overlapping runs / backend replicas (claimed via INSERT ... ON
CONFLICT DO NOTHING). channel/status are varchar + CHECK (task_models style);
timestamps are timestamptz. Plain DDL only.

Revision ID: d9e4c2a7f1b8
Revises: c8d1f4a7b2e6
Create Date: 2026-08-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d9e4c2a7f1b8"
down_revision: Union[str, None] = "c8d1f4a7b2e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activation_nudges",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "channel",
            "step",
            name="uq_activation_nudges_user_channel_step",
        ),
        sa.CheckConstraint(
            "channel IN ('push','email')", name="ck_activation_nudges_channel"
        ),
        sa.CheckConstraint(
            "status IN ('pending','sent','failed','skipped')",
            name="ck_activation_nudges_status",
        ),
    )
    op.create_index("ix_activation_nudges_user", "activation_nudges", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_activation_nudges_user", table_name="activation_nudges")
    op.drop_table("activation_nudges")
