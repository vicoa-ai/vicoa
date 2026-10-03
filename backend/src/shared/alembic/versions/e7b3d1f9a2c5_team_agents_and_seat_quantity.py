"""team agents: per-owner name uniqueness; subscriptions.seat_quantity

Two small, independent changes that land together with team-owned projects.

* ``agent_profiles`` names were unique per ``user_id``. A team's agent keeps its
  creator in ``user_id``, so that index would make a team's "Reviewer" collide
  with its creator's own "Reviewer" (and with every other team's they created).
  Uniqueness is now per owner: per user among personal rows, per team among a
  team's rows. No existing row is team-owned, so the narrowed personal index
  holds exactly the rows the old one did.
* ``subscriptions.seat_quantity`` — the number of seats bought on a per-seat
  plan. NULL for every plan that includes a fixed number of seats (all rows
  today). Nullable and additive.

Revision ID: e7b3d1f9a2c5
Revises: 83319b5520d0
Create Date: 2026-09-29 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e7b3d1f9a2c5"
down_revision: Union[str, None] = "83319b5520d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("uq_agent_profiles_user_name", table_name="agent_profiles")
    op.create_index(
        "uq_agent_profiles_user_name",
        "agent_profiles",
        ["user_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("NOT is_archived AND team_id IS NULL"),
    )
    op.create_index(
        "uq_agent_profiles_team_name",
        "agent_profiles",
        ["team_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("NOT is_archived AND team_id IS NOT NULL"),
    )
    op.add_column(
        "subscriptions", sa.Column("seat_quantity", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "seat_quantity")
    op.drop_index("uq_agent_profiles_team_name", table_name="agent_profiles")
    op.drop_index("uq_agent_profiles_user_name", table_name="agent_profiles")
    op.create_index(
        "uq_agent_profiles_user_name",
        "agent_profiles",
        ["user_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("NOT is_archived"),
    )
