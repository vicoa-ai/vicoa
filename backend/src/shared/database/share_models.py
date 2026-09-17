"""Share links (collaboration §3.4, P4) — the capability a URL carries.

A share link is the third and narrowest layer of the access model (§2): an
anonymous or link-scoped *read* of one session, of a project's sessions, or
of a project's task board. The token is the capability itself — 256-bit
urlsafe, so the row never needs to know who will open it — and the only write
it can ever confer is `allow_comments`: a signed-in visitor, comments only,
attributed to their real account, no grant row created, dead the instant the
link is revoked. Editing tasks and prompting sessions are never reachable
through a link, and nothing here can make them so.

Conventions follow `collab_models.py`: `timestamptz`, `varchar + CHECK` rather
than native PG enums, UUID PKs. Revocation sets `revoked_at` and keeps the row
for audit; the public API answers an identical 404 for unknown, revoked,
expired and wrong-audience tokens so the token space is not an oracle. This
module is side-effect-imported in `alembic/env.py`.
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
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .models import Base

if TYPE_CHECKING:
    from .models import AgentInstance, User
    from .task_models import Project

# 'session' shares one transcript; the two 'project_*' kinds share a project's
# sessions list (with transcripts) or its task board.
SHARE_KINDS = ("session", "project_sessions", "project_board")
# 'public' = anyone with the link, no account; 'authenticated' = any signed-in
# Vicoa user (the option for owners who want to know *who* is looking).
SHARE_AUDIENCES = ("public", "authenticated")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ShareLink(Base):
    __tablename__ = "share_links"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('session','project_sessions','project_board')",
            name="ck_share_links_kind",
        ),
        CheckConstraint(
            "audience IN ('public','authenticated')",
            name="ck_share_links_audience",
        ),
        # Exactly one target, and the right one for the kind.
        CheckConstraint(
            "(kind = 'session') = (agent_instance_id IS NOT NULL)",
            name="ck_share_links_session_target",
        ),
        CheckConstraint(
            "(kind <> 'session') = (project_id IS NOT NULL)",
            name="ck_share_links_project_target",
        ),
        # Comments are attributed to a real account, so they need one.
        CheckConstraint(
            "NOT allow_comments OR audience = 'authenticated'",
            name="ck_share_links_comments_need_auth",
        ),
        Index(
            "ix_share_links_instance",
            "agent_instance_id",
            postgresql_where=text("agent_instance_id IS NOT NULL"),
        ),
        Index(
            "ix_share_links_project",
            "project_id",
            postgresql_where=text("project_id IS NOT NULL"),
        ),
        Index("ix_share_links_created_by", "created_by_user_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    # secrets.token_urlsafe(32) → 43 chars. Unique index doubles as the lookup.
    token: Mapped[str] = mapped_column(String(43), unique=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    kind: Mapped[str] = mapped_column(String(24))
    agent_instance_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
        default=None,
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
        default=None,
    )
    audience: Mapped[str] = mapped_column(String(16), default="public")
    # Kind-specific narrowing, evaluated at view time so a link keeps matching
    # what arrives later (that is the point of sharing a project):
    #   project_board:    {label_ids: [uuid], statuses: [str], assignee_ids: [uuid]}
    #   project_sessions: {date_from, date_to, machine_ids: [uuid],
    #                      agent_types: [str], statuses: [str]}
    filters: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    allow_comments: Mapped[bool] = mapped_column(
        default=False, server_default=text("false")
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    view_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_user_id])
    instance: Mapped["AgentInstance | None"] = relationship(
        "AgentInstance", foreign_keys=[agent_instance_id]
    )
    project: Mapped["Project | None"] = relationship(
        "Project", foreign_keys=[project_id]
    )

    @property
    def is_live(self) -> bool:
        """Not revoked and not past its expiry. Audience is checked by the
        resolver, since it depends on who is asking."""
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= _utcnow():
            return False
        return True
