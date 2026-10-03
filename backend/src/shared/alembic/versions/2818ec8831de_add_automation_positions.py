"""add automation_positions (per-viewer manual automation order)

The automations page listed rows newest first with no way to rearrange
them. Each viewer's drag order is now a table: one row per (user,
automation) the user has ranked, ``position`` ascending. Per viewer rather
than a column on ``automations`` for the reason ``project_positions`` is:
a project's automations are shared with its collaborators, and one
person's arrangement must not move anyone else's. Unranked automations
sort first, newest first, so lists look exactly as before until someone
drags. Rows cascade with both the user and the automation. Additive only.

Revision ID: 2818ec8831de
Revises: c4a9e2f7b1d3
Create Date: 2026-10-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "2818ec8831de"
down_revision: Union[str, None] = "c4a9e2f7b1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "automation_positions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("automation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["automation_id"], ["automations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "automation_id"),
    )
    op.create_index(
        "ix_automation_positions_automation",
        "automation_positions",
        ["automation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_automation_positions_automation", table_name="automation_positions"
    )
    op.drop_table("automation_positions")
