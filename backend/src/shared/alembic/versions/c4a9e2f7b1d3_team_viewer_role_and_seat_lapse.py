"""team viewer role; remember what a lapsed seat held

The Team tier (collaboration §6) needs two things from the schema.

* A free ``viewer`` team role: it sees and comments on the team's work but
  cannot edit or prompt, so it takes no seat. ``team_members.role`` and
  ``team_invites.role`` are varchar + CHECK, so this only widens the CHECKs.
* When a Team subscription ends, everyone it paid a seat for (and who has no
  Pro of their own) drops to read-and-comment until seats return. Nothing is
  deleted, so each row remembers what it held:
  ``team_members.lapsed_role`` (admin/member, while ``role`` reads viewer),
  ``project_grants.lapsed_role`` (editor/admin, while ``role`` reads
  commenter) and ``user_instance_access.lapsed_at`` (a WRITE share reading
  READ). All nullable and additive; no existing row changes.

Downgrade puts every viewer back to the role it lapsed from, else member,
since the old schema has no read-only team role; viewer invite links are
revoked rather than turned into member links.

Revision ID: c4a9e2f7b1d3
Revises: e7b3d1f9a2c5
Create Date: 2026-10-03 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c4a9e2f7b1d3"
down_revision: Union[str, None] = "e7b3d1f9a2c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_team_members_role", "team_members", type_="check")
    op.create_check_constraint(
        "ck_team_members_role",
        "team_members",
        "role IN ('owner','admin','member','viewer')",
    )
    op.drop_constraint("ck_team_invites_role", "team_invites", type_="check")
    op.create_check_constraint(
        "ck_team_invites_role",
        "team_invites",
        "role IN ('owner','admin','member','viewer')",
    )

    op.add_column(
        "team_members", sa.Column("lapsed_role", sa.String(16), nullable=True)
    )
    op.create_check_constraint(
        "ck_team_members_lapsed_role",
        "team_members",
        "lapsed_role IS NULL OR lapsed_role IN ('admin','member')",
    )
    op.add_column(
        "project_grants", sa.Column("lapsed_role", sa.String(16), nullable=True)
    )
    op.create_check_constraint(
        "ck_project_grants_lapsed_role",
        "project_grants",
        "lapsed_role IS NULL OR lapsed_role IN ('editor','admin')",
    )
    op.add_column(
        "user_instance_access",
        sa.Column("lapsed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.execute(
        "UPDATE user_instance_access SET access = 'WRITE' WHERE lapsed_at IS NOT NULL"
    )
    op.drop_column("user_instance_access", "lapsed_at")
    op.execute(
        "UPDATE project_grants SET role = lapsed_role WHERE lapsed_role IS NOT NULL"
    )
    op.drop_constraint("ck_project_grants_lapsed_role", "project_grants", type_="check")
    op.drop_column("project_grants", "lapsed_role")

    op.execute(
        "UPDATE team_members SET role = COALESCE(lapsed_role, 'member') "
        "WHERE role = 'viewer'"
    )
    # A viewer link must not start handing out edit access: revoke it.
    op.execute(
        "UPDATE team_invites SET role = 'member', revoked_at = now() "
        "WHERE role = 'viewer'"
    )
    op.drop_constraint("ck_team_members_lapsed_role", "team_members", type_="check")
    op.drop_column("team_members", "lapsed_role")

    op.drop_constraint("ck_team_invites_role", "team_invites", type_="check")
    op.create_check_constraint(
        "ck_team_invites_role", "team_invites", "role IN ('owner','admin','member')"
    )
    op.drop_constraint("ck_team_members_role", "team_members", type_="check")
    op.create_check_constraint(
        "ck_team_members_role", "team_members", "role IN ('owner','admin','member')"
    )
