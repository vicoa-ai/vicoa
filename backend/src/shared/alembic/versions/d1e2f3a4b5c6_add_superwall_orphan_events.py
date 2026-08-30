"""add superwall_orphan_events

Revision ID: d1e2f3a4b5c6
Revises: f7a8b9c0d1e2
Branch Labels: None
Depends On: None

Create Date: 2026-05-30

Stores Superwall webhook events that arrive before the buyer has an account
(pre-signup onboarding-paywall purchases). They are keyed by the normalized
alias `lookup_id` and replayed at `/superwall/reconcile` once the user signs
up, so a pre-signup purchase is recovered from the webhook we already received
rather than racing Superwall's eventually-consistent summary API.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "superwall_orphan_events",
        sa.Column("id", PostgresUUID(as_uuid=True), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=True),
        sa.Column("lookup_id", sa.String(length=255), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=True),
        sa.Column("event_name", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("consumed_user_id", PostgresUUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["consumed_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_event_id"),
    )
    op.create_index(
        "ix_superwall_orphan_events_lookup_id",
        "superwall_orphan_events",
        ["lookup_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_superwall_orphan_events_lookup_id",
        table_name="superwall_orphan_events",
    )
    op.drop_table("superwall_orphan_events")
