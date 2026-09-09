"""Agent profiles — named provider + model + config presets (collaboration P1).

Schema per `plans/todos/agent-profiles-p1.md` §3 (parent: collaboration-teams-sharing
§3.6/§5). An `AgentProfile` is the user-facing "Agent": a saved provider + model +
config + instructions, with a name and an avatar. It is picked in one click when
starting a session, referenced by an automation, and — from P2 — assignable to a
task (`tasks.assignee_type='agent'`, whose CHECK already permits it).

Do not confuse this with `agent_types` (`shared/database/models.py`), which means
*agent type* ("claude code", "codex") and is auto-created on session registration.
The rename that freed the word "Agent" for this table shipped as PR #39.

Two invariants worth stating because code elsewhere leans on them:

* ``config`` is the **verbatim** shape of ``apps/web/lib/agent-catalog.ts::SessionConfig``
  (agent, model, thinking_effort, reasoning_effort, permission_mode, opencode_mode) —
  identical to what ``agent_instances.session_config`` and ``automations.session_config``
  already store. That is what lets the web client run ``reconcileAgainst(config, catalog)``
  over a profile and get stale-model repair for free, with no new code.
* ``agent`` is a real column as well as a ``config`` key. The column is authoritative
  (it is indexable and validated against the catalog server-side); the API forces
  ``config['agent']`` to match it on every write.

``team_id`` follows the same NULL-means-personal pattern as ``projects.team_id`` and is
unused until P7 — it is here so a profile can move to a team without a second migration.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Double,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentProfile(Base):
    __tablename__ = "agent_profiles"
    __table_args__ = (
        Index("ix_agent_profiles_user", "user_id"),
        Index(
            "ix_agent_profiles_team",
            "team_id",
            postgresql_where=text("team_id IS NOT NULL"),
        ),
        # Names are how the CLI (`--agent-profile <name>`) and the picker address a
        # profile, so they must be unique per user — case-insensitively, since
        # "Reviewer" and "reviewer" would be indistinguishable in the UI. Archived
        # rows are excluded so archiving frees the name for reuse.
        Index(
            "uq_agent_profiles_user_name",
            "user_id",
            func.lower(text("name")),
            unique=True,
            postgresql_where=text("NOT is_archived"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    # NULL ⇒ personal (owned by user_id). Set ⇒ team-owned, and user_id degrades to
    # "created_by" — the same three-layer ownership model as `projects` (parent plan §2).
    team_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        default=None,
    )

    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text, default=None)

    # Identity, mirroring users.avatar_* as-built (collab P0, shared/avatars.py):
    # a *served* URL into our own storage, never an external hot-link, so a shared
    # surface leaks no request to a third party. avatar_source is 'user' or NULL —
    # unlike a user there is no IdP to seed an agent from.
    avatar_image_uri: Mapped[str | None] = mapped_column(Text, default=None)
    avatar_source: Mapped[str | None] = mapped_column(String(16), default=None)
    # Generated-fallback seeds for <PrincipalAvatar>, same role as projects.color/icon.
    color: Mapped[str | None] = mapped_column(String(16), default=None)
    emoji: Mapped[str | None] = mapped_column(String(16), default=None)

    # Catalog agent id ('claude' | 'codex' | 'opencode' | 'omp' | …). Validated
    # against the server-side catalog on write; authoritative over config['agent'].
    agent: Mapped[str] = mapped_column(String(64))
    config: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'")
    )
    # Optional instructions prepended at spawn. Delivery is per-provider (plan §5):
    # a native in-process channel where one exists, else a per-turn prompt prefix.
    # No provider writes this to disk.
    system_prompt: Mapped[str | None] = mapped_column(Text, default=None)

    # Prefills for the new-session flow; SET NULL so removing a machine or project
    # degrades the preset rather than breaking it.
    default_machine_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("machines.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        default=None,
    )
    default_project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        default=None,
    )

    position: Mapped[float] = mapped_column(
        Double, default=0.0, server_default=text("0")
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
