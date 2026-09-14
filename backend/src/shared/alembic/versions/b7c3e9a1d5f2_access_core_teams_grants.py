"""Access core: rebuild teams, add project grants and project/label ownership

Collaboration plan §3.2 / §3.3 (P3). The project-anchored access model.

Revision ID: b7c3e9a1d5f2
Revises: a3f1c9e27b45
Create Date: 2026-09-11

**Teams are dropped and recreated**, not migrated. Verified in production on
2026-09-07 (read-only ``ai_agent_ro``): ``teams`` = 2 rows, ``team_memberships``
= 7 rows, all from a 2026-08-10 enumeration test, and ``team_instance_access``
= 0 — no share has ever been granted. Those 9 rows are deleted here; there is
no preservation or backfill path (D-F). ``team_instance_access`` itself
survives with its FK re-pointed at the new ``teams``.

Ships while every user is still solo: every existing project and label stays
personal (``team_id`` NULL), no grant exists, so behaviour is identical and the
deploy-time blast radius is zero — which is why this lands before any share
UI does.

Deploy order (collaboration §10.10): ``projects.team_id`` and
``task_labels.team_id`` land on the ORM models, so every ``db.query(Project)``
enumerates them. Run ``alembic upgrade head`` BEFORE the backend deploy or
every query touching those tables fails with ``UndefinedColumn``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b7c3e9a1d5f2"
down_revision = "a3f1c9e27b45"
branch_labels = None
depends_on = None


# Pre-P3 objects (23aa590c6a55) that referenced the old ``teams``.
_OLD_TEAM_ROLE_ENUM = "teamrole"
_AGENT_PROFILES_TEAM_FK = "agent_profiles_team_id_fkey"  # PG default name
_TEAM_INSTANCE_ACCESS_TEAM_FK = "fk_team_instance_access_team_id"


def upgrade() -> None:
    # --- 1. Detach everything that points at the old ``teams`` ---------------
    op.drop_constraint(_AGENT_PROFILES_TEAM_FK, "agent_profiles", type_="foreignkey")
    op.execute(sa.text("UPDATE agent_profiles SET team_id = NULL"))
    op.drop_constraint(
        _TEAM_INSTANCE_ACCESS_TEAM_FK, "team_instance_access", type_="foreignkey"
    )
    # 0 rows in production; whatever a dev DB holds would dangle.
    op.execute(sa.text("DELETE FROM team_instance_access"))

    # --- 2. Drop the old shape ------------------------------------------------
    op.drop_index(
        "uq_team_memberships_team_user",
        table_name="team_memberships",
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_team_memberships_team_email",
        table_name="team_memberships",
        postgresql_where=sa.text("invited_email IS NOT NULL"),
    )
    op.drop_index("ix_team_memberships_team_id", table_name="team_memberships")
    op.drop_table("team_memberships")
    op.drop_table("teams")
    sa.Enum(name=_OLD_TEAM_ROLE_ENUM).drop(op.get_bind(), checkfirst=True)

    # --- 3. teams -------------------------------------------------------------
    op.create_table(
        "teams",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("avatar_image_uri", sa.Text(), nullable=True),
        sa.Column("avatar_source", sa.String(length=16), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_teams_slug"),
    )

    # --- 4. team_members ------------------------------------------------------
    op.create_table(
        "team_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("invited_email", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("invited_by_user_id", sa.UUID(), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('owner','admin','member')", name="ck_team_members_role"
        ),
        sa.CheckConstraint(
            "status IN ('invited','active','removed')",
            name="ck_team_members_status",
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_team_members_team", "team_members", ["team_id"])
    op.create_index(
        "ix_team_members_user",
        "team_members",
        ["user_id"],
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_team_members_team_user",
        "team_members",
        ["team_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_team_members_team_email",
        "team_members",
        ["team_id", sa.text("lower(invited_email)")],
        unique=True,
        postgresql_where=sa.text("invited_email IS NOT NULL"),
    )
    # Email-only lookup: "which teams have invited this address?" runs on
    # every GET /teams/invitations and at signup. The unique index above leads
    # with team_id, so it cannot serve that query.
    op.create_index(
        "ix_team_members_invited_email",
        "team_members",
        [sa.text("lower(invited_email)")],
        postgresql_where=sa.text("invited_email IS NOT NULL"),
    )

    # --- 5. team_invites ------------------------------------------------------
    op.create_table(
        "team_invites",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("token", sa.String(length=43), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("uses", sa.Integer(), server_default="0", nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('owner','admin','member')", name="ck_team_invites_role"
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_team_invites_token"),
    )
    op.create_index("ix_team_invites_team", "team_invites", ["team_id"])

    # --- 6. Re-attach the survivors -------------------------------------------
    op.create_foreign_key(
        _AGENT_PROFILES_TEAM_FK,
        "agent_profiles",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        _TEAM_INSTANCE_ACCESS_TEAM_FK,
        "team_instance_access",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- 7. Ownership: projects.team_id, task_labels.team_id ------------------
    op.add_column("projects", sa.Column("team_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_projects_team_id",
        "projects",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_projects_team",
        "projects",
        ["team_id"],
        postgresql_where=sa.text("team_id IS NOT NULL"),
    )
    # The task-key namespace is per owner; the owner is now either the user
    # (personal) or the team, so the single index splits into two partials.
    op.drop_index(
        "uq_projects_user_key",
        table_name="projects",
        postgresql_where=sa.text("key IS NOT NULL"),
    )
    op.create_index(
        "uq_projects_user_key",
        "projects",
        ["user_id", sa.text("upper(key)")],
        unique=True,
        postgresql_where=sa.text("key IS NOT NULL AND team_id IS NULL"),
    )
    op.create_index(
        "uq_projects_team_key",
        "projects",
        ["team_id", sa.text("upper(key)")],
        unique=True,
        postgresql_where=sa.text("key IS NOT NULL AND team_id IS NOT NULL"),
    )

    op.add_column("task_labels", sa.Column("team_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_task_labels_team_id",
        "task_labels",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_task_labels_team",
        "task_labels",
        ["team_id"],
        postgresql_where=sa.text("team_id IS NOT NULL"),
    )

    # --- 8. project_grants ----------------------------------------------------
    op.create_table(
        "project_grants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("principal_type", sa.String(length=8), nullable=False),
        sa.Column("principal_id", sa.UUID(), nullable=True),
        sa.Column("invited_email", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='["tasks", "sessions"]',
            nullable=False,
        ),
        sa.Column("granted_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "principal_type IN ('user','team')", name="ck_project_grants_principal"
        ),
        sa.CheckConstraint(
            "role IN ('viewer','commenter','editor','admin')",
            name="ck_project_grants_role",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_grants_project", "project_grants", ["project_id"])
    op.create_index(
        "ix_project_grants_principal",
        "project_grants",
        ["principal_type", "principal_id"],
    )
    op.create_index(
        "uq_project_grants_project_principal",
        "project_grants",
        ["project_id", "principal_type", "principal_id"],
        unique=True,
        postgresql_where=sa.text("principal_id IS NOT NULL"),
    )
    op.create_index(
        "uq_project_grants_project_email",
        "project_grants",
        ["project_id", sa.text("lower(invited_email)")],
        unique=True,
        postgresql_where=sa.text("invited_email IS NOT NULL"),
    )
    # Email-only lookup for attach_pending_grants at signup (same reason as
    # ix_team_members_invited_email: the unique index leads with project_id).
    op.create_index(
        "ix_project_grants_invited_email",
        "project_grants",
        [sa.text("lower(invited_email)")],
        postgresql_where=sa.text("invited_email IS NOT NULL"),
    )


def downgrade() -> None:
    # Grants, ownership columns and the new team tables go; the old
    # (test-artifact-only) team rows are not restored.
    op.drop_index(
        "ix_project_grants_invited_email",
        table_name="project_grants",
        postgresql_where=sa.text("invited_email IS NOT NULL"),
    )
    op.drop_index(
        "uq_project_grants_project_email",
        table_name="project_grants",
        postgresql_where=sa.text("invited_email IS NOT NULL"),
    )
    op.drop_index(
        "uq_project_grants_project_principal",
        table_name="project_grants",
        postgresql_where=sa.text("principal_id IS NOT NULL"),
    )
    op.drop_index("ix_project_grants_principal", table_name="project_grants")
    op.drop_index("ix_project_grants_project", table_name="project_grants")
    op.drop_table("project_grants")

    op.drop_index(
        "ix_task_labels_team",
        table_name="task_labels",
        postgresql_where=sa.text("team_id IS NOT NULL"),
    )
    op.drop_constraint("fk_task_labels_team_id", "task_labels", type_="foreignkey")
    op.drop_column("task_labels", "team_id")

    op.drop_index(
        "uq_projects_team_key",
        table_name="projects",
        postgresql_where=sa.text("key IS NOT NULL AND team_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_projects_user_key",
        table_name="projects",
        postgresql_where=sa.text("key IS NOT NULL AND team_id IS NULL"),
    )
    op.create_index(
        "uq_projects_user_key",
        "projects",
        ["user_id", sa.text("upper(key)")],
        unique=True,
        postgresql_where=sa.text("key IS NOT NULL"),
    )
    op.drop_index(
        "ix_projects_team",
        table_name="projects",
        postgresql_where=sa.text("team_id IS NOT NULL"),
    )
    op.drop_constraint("fk_projects_team_id", "projects", type_="foreignkey")
    op.drop_column("projects", "team_id")

    op.drop_constraint(
        _TEAM_INSTANCE_ACCESS_TEAM_FK, "team_instance_access", type_="foreignkey"
    )
    op.execute(sa.text("DELETE FROM team_instance_access"))
    op.drop_constraint(_AGENT_PROFILES_TEAM_FK, "agent_profiles", type_="foreignkey")
    op.execute(sa.text("UPDATE agent_profiles SET team_id = NULL"))

    op.drop_index("ix_team_invites_team", table_name="team_invites")
    op.drop_table("team_invites")
    op.drop_index(
        "ix_team_members_invited_email",
        table_name="team_members",
        postgresql_where=sa.text("invited_email IS NOT NULL"),
    )
    op.drop_index(
        "uq_team_members_team_email",
        table_name="team_members",
        postgresql_where=sa.text("invited_email IS NOT NULL"),
    )
    op.drop_index(
        "uq_team_members_team_user",
        table_name="team_members",
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.drop_index(
        "ix_team_members_user",
        table_name="team_members",
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.drop_index("ix_team_members_team", table_name="team_members")
    op.drop_table("team_members")
    op.drop_table("teams")

    # Recreate the pre-P3 shape (23aa590c6a55), empty.
    team_role_enum = sa.Enum("OWNER", "ADMIN", "MEMBER", name=_OLD_TEAM_ROLE_ENUM)
    op.create_table(
        "teams",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "team_memberships",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("invited_email", sa.String(length=255), nullable=True),
        sa.Column("role", team_role_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name="fk_team_memberships_team_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_team_memberships_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_team_memberships_team_id", "team_memberships", ["team_id"])
    op.create_index(
        "uq_team_memberships_team_email",
        "team_memberships",
        ["team_id", "invited_email"],
        unique=True,
        postgresql_where=sa.text("invited_email IS NOT NULL"),
    )
    op.create_index(
        "uq_team_memberships_team_user",
        "team_memberships",
        ["team_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_foreign_key(
        _AGENT_PROFILES_TEAM_FK,
        "agent_profiles",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        _TEAM_INSTANCE_ACCESS_TEAM_FK,
        "team_instance_access",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
