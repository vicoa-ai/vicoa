"""Teams, memberships, invite links and project grants (collaboration §3.2, §3.3).

The access model is *project-anchored* (§2): a Team is a principal — a reusable
bag of people that can hold a grant and, optionally, own a project — never a
tenant every row has to carry. Ownership is `projects.team_id` (NULL ⇒
personal); standing access is a `project_grants` row; the effective role is
resolved in `shared.access`.

Conventions follow `task_models.py`: `timestamptz`, `varchar + CHECK` rather
than native PG enums (the vocabularies can grow without an enum migration),
UUID PKs. This module is side-effect-imported in `alembic/env.py`.

Rebuilt from scratch in P3: the previous `teams` / `team_memberships` tables
were never wired to any UI and held only two enumeration-test artifacts
(verified in production 2026-09-07, D-F), so the migration deletes them and
needs no preservation path.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .models import Base

if TYPE_CHECKING:
    from .models import TeamInstanceAccess, User

TEAM_ROLES = ("owner", "admin", "member")
TEAM_MEMBER_STATUSES = ("invited", "active", "removed")
GRANT_PRINCIPAL_TYPES = ("user", "team")
# The grantable ladder (§2). 'owner' exists as a *resolved* role in
# `shared.access` but is never stored — ownership is a column, not a grant.
GRANT_ROLES = ("viewer", "commenter", "editor", "admin")
# What a grant can cover — the "share tasks / sessions / both" toggle.
GRANT_SCOPES = ("tasks", "sessions")


def all_grant_scopes() -> list[str]:
    return list(GRANT_SCOPES)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(255))
    # Globally unique, RESERVED NOW, EXPOSED LATER (D-D). Auto-derived from the
    # name on create — never user-picked — and nothing public resolves it: there
    # is no availability-check endpoint and no `/t/<slug>` route. Enumeration is
    # a property of a public route, not of this column; squatting only gets
    # worse the longer the namespace stays open. Renaming is a later,
    # authenticated, rate-limited team-settings action.
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    # Mirrors `users.avatar_*` (§3.1 as-built): a served URL into OUR storage,
    # never a hot-link; `avatar_source` is 'user' | NULL — there is no IdP to
    # seed a team from. Upload/serve endpoints land with the team UI (P7).
    avatar_image_uri: Mapped[str | None] = mapped_column(Text, default=None)
    avatar_source: Mapped[str | None] = mapped_column(String(16), default=None)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    members: Mapped[list["TeamMember"]] = relationship(
        "TeamMember",
        back_populates="team",
        cascade="all, delete-orphan",
        order_by="TeamMember.created_at",
    )
    invites: Mapped[list["TeamInvite"]] = relationship(
        "TeamInvite", back_populates="team", cascade="all, delete-orphan"
    )
    instance_accesses: Mapped[list["TeamInstanceAccess"]] = relationship(
        "TeamInstanceAccess",
        back_populates="team",
        cascade="all, delete-orphan",
    )


class TeamMember(Base):
    """One person's standing in one team.

    `user_id` is NULL until an emailed invite is accepted by an account —
    invite-before-signup, the same pattern as `user_instance_access`. A
    `removed` row is kept for audit and revived in place on re-invite, which is
    why the uniqueness is on (team, user) rather than (team, user, status).
    """

    __tablename__ = "team_members"
    __table_args__ = (
        CheckConstraint(
            "role IN ('owner','admin','member')", name="ck_team_members_role"
        ),
        CheckConstraint(
            "status IN ('invited','active','removed')",
            name="ck_team_members_status",
        ),
        # '' = '' would make every blank-email account the same principal when
        # an invite is matched by address — see `collab_queries._email_key`.
        CheckConstraint(
            "invited_email IS NULL OR btrim(invited_email) <> ''",
            name="ck_team_members_invited_email_not_blank",
        ),
        Index("ix_team_members_team", "team_id"),
        Index(
            "ix_team_members_user",
            "user_id",
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_team_members_team_user",
            "team_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_team_members_team_email",
            "team_id",
            func.lower(text("invited_email")),
            unique=True,
            postgresql_where=text("invited_email IS NOT NULL"),
        ),
        # Email-only lookup (GET /teams/invitations, signup); the unique index
        # above leads with team_id so it cannot serve it.
        Index(
            "ix_team_members_invited_email",
            func.lower(text("invited_email")),
            postgresql_where=text("invited_email IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
    )
    invited_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="member")
    status: Mapped[str] = mapped_column(String(16), default="invited")
    invited_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
    )
    joined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    team: Mapped["Team"] = relationship("Team", back_populates="members")
    user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[user_id], back_populates="team_members"
    )


class TeamInvite(Base):
    """A shareable join link — distinct from a per-email invite.

    The token *is* the capability (256-bit urlsafe), so the row never needs to
    know who will redeem it. Revoked / expired / exhausted / unknown all fail
    identically at the API so the token space is not an oracle.
    """

    __tablename__ = "team_invites"
    __table_args__ = (
        CheckConstraint(
            "role IN ('owner','admin','member')", name="ck_team_invites_role"
        ),
        Index("ix_team_invites_team", "team_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    token: Mapped[str] = mapped_column(String(43), unique=True)
    role: Mapped[str] = mapped_column(String(16), default="member")
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    max_uses: Mapped[int | None] = mapped_column(Integer, default=None)
    uses: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    team: Mapped["Team"] = relationship("Team", back_populates="invites")


class ProjectGrant(Base):
    """Standing access to one project for one principal (§3.3) — the primary
    grant. Session-level shares (`user_instance_access` / `team_instance_access`)
    and link capabilities (P4) are the other two layers `shared.access` folds in.

    `principal_id` is polymorphic (users.id or teams.id) and therefore not an
    FK; `delete_user_account` and team deletion sweep their grants explicitly.
    """

    __tablename__ = "project_grants"
    __table_args__ = (
        CheckConstraint(
            "principal_type IN ('user','team')", name="ck_project_grants_principal"
        ),
        CheckConstraint(
            "role IN ('viewer','commenter','editor','admin')",
            name="ck_project_grants_role",
        ),
        # Invariants that used to live only in `create_project_grant`'s Python
        # branches. Both partial unique indexes below are `WHERE ... IS NOT
        # NULL`, so a principal-less row is unique-index-invisible as well as
        # meaningless; and a blank `invited_email` collides with every
        # blank-email account (see `collab_queries._email_key`).
        CheckConstraint(
            "principal_id IS NOT NULL OR invited_email IS NOT NULL",
            name="ck_project_grants_has_principal",
        ),
        CheckConstraint(
            "principal_type <> 'team' OR principal_id IS NOT NULL",
            name="ck_project_grants_team_has_id",
        ),
        CheckConstraint(
            "invited_email IS NULL OR btrim(invited_email) <> ''",
            name="ck_project_grants_invited_email_not_blank",
        ),
        Index("ix_project_grants_project", "project_id"),
        # Backs "projects shared with me" — the principal side of the lookup.
        Index("ix_project_grants_principal", "principal_type", "principal_id"),
        Index(
            "uq_project_grants_project_principal",
            "project_id",
            "principal_type",
            "principal_id",
            unique=True,
            postgresql_where=text("principal_id IS NOT NULL"),
        ),
        Index(
            "uq_project_grants_project_email",
            "project_id",
            func.lower(text("invited_email")),
            unique=True,
            postgresql_where=text("invited_email IS NOT NULL"),
        ),
        # Email-only lookup for attach_pending_grants at signup.
        Index(
            "ix_project_grants_invited_email",
            func.lower(text("invited_email")),
            postgresql_where=text("invited_email IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
    )
    principal_type: Mapped[str] = mapped_column(String(8))
    # NULL only while an emailed invite is pending (invite-before-signup).
    principal_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True, default=None
    )
    invited_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(16))
    scopes: Mapped[list[str]] = mapped_column(
        JSONB,
        default=all_grant_scopes,
        server_default='["tasks", "sessions"]',
    )
    granted_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
