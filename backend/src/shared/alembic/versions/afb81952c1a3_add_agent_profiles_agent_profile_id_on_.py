"""Add agent_profiles + agent_profile_id on agent_instances/automations

Collaboration P1 (plans/todos/agent-profiles-p1.md §3). Creates the named
provider+model+config presets the UI calls "Agents", plus two nullable FKs:
provenance on a session, a live reference on an automation.

Hand-trimmed from autogenerate, which additionally proposed:
  * dropping `subscriptions` / `billing_events` / `superwall_orphan_events` —
    those live in the closed `cloud` overlay and are simply not on this
    metadata when the overlay is absent;
  * re-creating a handful of unrelated FKs (agent_types, api_keys, messages,
    push_tokens) that differ only in autogenerate's naming;
  * flipping `agent_instances.instance_metadata` JSON→JSONB.
None of those belong to this change, so all were removed.

Revision ID: afb81952c1a3
Revises: a3f1d95c7b02
Create Date: 2026-09-09 00:10:36.937850

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "afb81952c1a3"
down_revision: Union[str, None] = "a3f1d95c7b02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("avatar_image_uri", sa.Text(), nullable=True),
        sa.Column("avatar_source", sa.String(length=16), nullable=True),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("emoji", sa.String(length=16), nullable=True),
        sa.Column("agent", sa.String(length=64), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("default_machine_id", sa.UUID(), nullable=True),
        sa.Column("default_project_id", sa.UUID(), nullable=True),
        sa.Column("position", sa.Double(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["default_machine_id"], ["machines.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["default_project_id"], ["projects.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_profiles_user", "agent_profiles", ["user_id"], unique=False
    )
    op.create_index(
        "ix_agent_profiles_team",
        "agent_profiles",
        ["team_id"],
        unique=False,
        postgresql_where=sa.text("team_id IS NOT NULL"),
    )
    # Case-insensitive per user, archived rows excluded so archiving frees the name.
    op.create_index(
        "uq_agent_profiles_user_name",
        "agent_profiles",
        ["user_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("NOT is_archived"),
    )

    op.add_column(
        "agent_instances", sa.Column("agent_profile_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_agent_instances_agent_profile",
        "agent_instances",
        "agent_profiles",
        ["agent_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "automations", sa.Column("agent_profile_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_automations_agent_profile",
        "automations",
        "agent_profiles",
        ["agent_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_automations_agent_profile", "automations", type_="foreignkey"
    )
    op.drop_column("automations", "agent_profile_id")
    op.drop_constraint(
        "fk_agent_instances_agent_profile", "agent_instances", type_="foreignkey"
    )
    op.drop_column("agent_instances", "agent_profile_id")
    op.drop_index(
        "uq_agent_profiles_user_name",
        table_name="agent_profiles",
        postgresql_where=sa.text("NOT is_archived"),
    )
    op.drop_index(
        "ix_agent_profiles_team",
        table_name="agent_profiles",
        postgresql_where=sa.text("team_id IS NOT NULL"),
    )
    op.drop_index("ix_agent_profiles_user", table_name="agent_profiles")
    op.drop_table("agent_profiles")
