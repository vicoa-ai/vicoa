"""automation structured frequency + worktree

Replace the raw-cron column on `automations` with a structured `frequency` JSONB
(shared/scheduling/frequency.py) so schedules can express "every N days/weeks/
months"; add `anchor_at` (interval phase reference) and an optional `worktree`
spec. Plain DDL only.

Revision ID: e2c7b9d4a1f3
Revises: d5f8a2c1b9e4
Create Date: 2026-08-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e2c7b9d4a1f3"
down_revision: Union[str, None] = "d5f8a2c1b9e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "automations",
        sa.Column("worktree", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "automations",
        sa.Column("frequency", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "automations",
        sa.Column("anchor_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_column("automations", "cron_expression")


def downgrade() -> None:
    op.add_column(
        "automations",
        sa.Column("cron_expression", sa.Text(), nullable=True),
    )
    op.drop_column("automations", "anchor_at")
    op.drop_column("automations", "frequency")
    op.drop_column("automations", "worktree")
