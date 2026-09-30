"""Reads/writes against ``agent_profiles`` (collaboration P1).

Same division of labour as ``user_queries`` / ``task_queries``: the router
validates and shapes, this layer owns the transaction. Keeping ``db.commit()``
here rather than in ``backend/api/`` is also what keeps
``scripts/check_websocket_freeze.py`` happy.

Every function takes ``user_id`` and filters on it — house rule, and here it is
load-bearing twice over: a profile carries a ``system_prompt`` that is injected
into someone's agent process, so a cross-user read would be an instruction
-injection surface, not just a data leak.

Two lenses, as in ``task_queries``: the owner-only default sees the caller's
*personal* profiles (what the CLI mirror in ``servers`` serves); ``sharing=True``
— the dashboard — adds the agents of every team the caller is an active member
of (§3.6, ``team_id`` NULL ⇒ personal). A team agent is *used* by any member
and *edited* by the team's owner and admins only (``can_edit``): its
instructions run on every member's machine that picks it.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from shared import access
from shared.agent_profile_resolution import usable_profile_filter
from shared.database.agent_profile_models import AgentProfile


def _personal_filter(user_id: UUID):
    return and_(AgentProfile.user_id == user_id, AgentProfile.team_id.is_(None))


def _visible_filter(user_id: UUID, *, sharing: bool):
    return usable_profile_filter(user_id) if sharing else _personal_filter(user_id)


def list_agent_profiles(
    db: Session,
    user_id: UUID,
    *,
    include_archived: bool = False,
    sharing: bool = False,
) -> list[AgentProfile]:
    """The user's profiles in picker order: personal first, then each team's,
    each in position order (then creation)."""
    stmt = select(AgentProfile).where(_visible_filter(user_id, sharing=sharing))
    if not include_archived:
        stmt = stmt.where(AgentProfile.is_archived.is_(False))
    stmt = stmt.order_by(
        AgentProfile.team_id.asc().nullsfirst(),
        AgentProfile.position.asc(),
        AgentProfile.created_at.asc(),
    )
    return list(db.execute(stmt).scalars())


def get_agent_profile(
    db: Session, user_id: UUID, profile_id: UUID, *, sharing: bool = False
) -> AgentProfile | None:
    return db.execute(
        select(AgentProfile).where(
            AgentProfile.id == profile_id, _visible_filter(user_id, sharing=sharing)
        )
    ).scalar_one_or_none()


def can_edit(db: Session, user_id: UUID, profile: AgentProfile) -> bool:
    """Personal: its owner. Team: the team's owner or admins — a plain member
    can run a team agent but not rewrite what it tells everyone's agents."""
    if profile.team_id is None:
        return profile.user_id == user_id
    return access.team_role(db, user_id, profile.team_id) in ("owner", "admin")


def editable_team_ids(db: Session, user_id: UUID, team_ids: set[UUID]) -> set[UUID]:
    """Which of these teams the caller administers — `can_edit` for a whole
    list in one query."""
    if not team_ids:
        return set()
    roles = access.team_roles(db, user_id)
    return {t for t in team_ids if roles.get(t) in ("owner", "admin")}


def get_agent_profile_by_name(
    db: Session, user_id: UUID, name: str
) -> AgentProfile | None:
    """Resolve by name, case-insensitively — how the CLI addresses a profile.

    Matches the ``uq_agent_profiles_user_name`` predicate (non-archived only), so
    a name freed by archiving resolves to the live row that reused it.
    """
    return db.execute(
        select(AgentProfile).where(
            _personal_filter(user_id),
            AgentProfile.is_archived.is_(False),
            func.lower(AgentProfile.name) == name.strip().lower(),
        )
    ).scalar_one_or_none()


def next_position(db: Session, user_id: UUID, team_id: UUID | None = None) -> float:
    """Append-at-end position for a new profile in its owner's list."""
    owner = (
        AgentProfile.team_id == team_id
        if team_id is not None
        else _personal_filter(user_id)
    )
    highest = db.execute(select(func.max(AgentProfile.position)).where(owner)).scalar()
    return float(highest or 0.0) + 1.0


def create_agent_profile(db: Session, user_id: UUID, **fields) -> AgentProfile:
    profile = AgentProfile(user_id=user_id, **fields)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def update_agent_profile(
    db: Session, profile: AgentProfile, updates: dict
) -> AgentProfile:
    for key, value in updates.items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


def delete_agent_profile(db: Session, profile: AgentProfile) -> None:
    """Hard delete. Both referencing FKs are ``ON DELETE SET NULL``, so sessions
    keep their snapshot and automations fall back to theirs (see §4 of the plan)."""
    db.delete(profile)
    db.commit()


def set_agent_profile_avatar(
    db: Session, profile: AgentProfile, *, avatar_image_uri: str
) -> AgentProfile:
    profile.avatar_image_uri = avatar_image_uri
    profile.avatar_source = "user"
    db.commit()
    db.refresh(profile)
    return profile


def clear_agent_profile_avatar(db: Session, profile: AgentProfile) -> AgentProfile:
    """Drop the image so the profile renders as a generated initial square.

    Unlike a user, an agent has no IdP seed to guard against, so ``avatar_source``
    goes back to NULL rather than being pinned to ``'user'``.
    """
    profile.avatar_image_uri = None
    profile.avatar_source = None
    db.commit()
    db.refresh(profile)
    return profile


def count_automations_using(db: Session, profile_id: UUID) -> int:
    """How many automations reference this profile — the delete-warning number."""
    from shared.database.automation_models import Automation

    return int(
        db.execute(
            select(func.count())
            .select_from(Automation)
            .where(Automation.agent_profile_id == profile_id)
        ).scalar()
        or 0
    )


def session_stats_by_profile(
    db: Session, user_id: UUID, profile_ids: list[UUID]
) -> dict[UUID, tuple[int, datetime | None]]:
    """``{profile_id: (session_count, last_active_at)}`` — one grouped query.

    Powers the agent row's "N sessions" and "used 2h ago": the same two facts the
    Run history card spells out, condensed. Uses the partial
    ``ix_agent_instances_agent_profile`` index.

    Recency is ``max(updated_at)``, not ``max(started_at)``: "last used" should
    mean the last time the agent was *doing* something. ``updated_at`` is the
    monotonic last-modified marker the WebSocket catch-up already relies on, so
    it moves with status and message activity — whereas a start time would show
    a session opened three days ago and worked in five minutes ago as "3d ago".
    """
    from shared.database.agent_instances import AgentInstance
    from shared.database.enums import AgentStatus

    if not profile_ids:
        return {}
    rows = db.execute(
        select(
            AgentInstance.agent_profile_id,
            func.count(),
            func.max(AgentInstance.updated_at),
        )
        .where(
            AgentInstance.agent_profile_id.in_(profile_ids),
            AgentInstance.user_id == user_id,
            AgentInstance.status != AgentStatus.DELETED,
        )
        .group_by(AgentInstance.agent_profile_id)
    ).all()
    return {row[0]: (row[1], row[2]) for row in rows}
