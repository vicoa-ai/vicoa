"""superwall_orphan_events consumed_user_id ON DELETE CASCADE

Revision ID: 41f641820d6a
Revises: b2c3d4e5f6a7
Create Date: 2026-06-17 09:43:35.767826

The original migration `d1e2f3a4b5c6_add_superwall_orphan_events` defined the
`consumed_user_id` FK without an `ON DELETE` clause (defaults to NO ACTION),
so any consumed orphan event blocks user deletion with a
`superwall_orphan_events_consumed_user_id_fkey` violation — reproduced when
a Superwall-purchased user runs `DELETE /api/v1/auth/me` (500). Cascade
deletion is the right semantics: once the user is gone, the row is inert
(`consumed_at` is already set, blocking re-application), so keeping it
serves no purpose. Matches how `billing_events`, `subscription`, and the
other user-FK tables already behave. See
plans/bugs/p0-agent-jwt-no-db-validation.md for the broader bug family.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "41f641820d6a"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CONSTRAINT = "superwall_orphan_events_consumed_user_id_fkey"
_TABLE = "superwall_orphan_events"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="foreignkey")
    op.create_foreign_key(
        _CONSTRAINT,
        _TABLE,
        "users",
        ["consumed_user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="foreignkey")
    op.create_foreign_key(
        _CONSTRAINT,
        _TABLE,
        "users",
        ["consumed_user_id"],
        ["id"],
    )
