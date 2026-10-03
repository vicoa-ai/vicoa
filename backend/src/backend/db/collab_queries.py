"""Teams, memberships, invite links and project grants — the write side of
`shared.access` (collaboration §3.2, §3.3, §6).

Same division of labour as `task_queries`: the router validates and maps
errors, this module owns the transaction. Everything here commits.

Seat gating never lives here. The metered actions call
`shared.hooks.check_capability` with a context the closed overlay can price;
in the open build the registry is empty and every check passes.
"""

import logging
import re
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TypeAlias
from uuid import UUID

from sqlalchemy import and_, case, delete, func, insert, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from shared import access

from .access_events import notify_access_changed, principal_user_ids, team_member_ids
from shared.database import (
    GRANT_ROLES,
    GRANT_SCOPES,
    TEAM_SEAT_ROLES,
    AgentInstance,
    Project,
    ProjectGrant,
    Task,
    TaskLabel,
    Team,
    TeamInvite,
    TeamMember,
    User,
    UserInstanceAccess,
)
from shared.database.agent_profile_models import AgentProfile
from shared.database.enums import AgentStatus, InstanceAccessLevel
from shared.database.task_identity import key_is_taken, suggest_free_key
from shared.database.task_models import task_label_links
from shared.hooks import (
    CAPABILITY_GRANT_WRITE,
    CAPABILITY_TEAM_OWN,
    CAPABILITY_TEAM_SEAT,
    check_capability,
)

logger = logging.getLogger(__name__)


class TeamNotFoundError(Exception):
    """No such team, or the caller is not an active member of it (→ 404)."""


class TeamPermissionError(Exception):
    """The caller is a member but their role doesn't allow this (→ 403)."""


class TeamConflictError(Exception):
    """The request contradicts the team's current state (→ 409)."""


class InviteNotFoundError(Exception):
    """Unknown, revoked, expired or exhausted invite — one error for all four,
    so the token space is not an oracle (→ 404)."""


class GrantError(Exception):
    """A grant request that cannot be honoured as stated (→ 400)."""


class GrantConflictError(GrantError):
    """The request contradicts the grants already in place (→ 409)."""


class GrantNotFoundError(GrantError):
    """No such grant on this project (→ 404)."""


class TeamStateError(Exception):
    """The team is in a state no request can be served from — no active owner
    and no surviving creator, so there is nobody to bill or to administer it
    (→ 409). `delete_user_account` promotes a new owner rather than leaving a
    team like this, so reaching here means an invariant broke upstream."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _email_key(email: str | None) -> str | None:
    """The address to match an invite on, lowercased, or None when there is
    nothing usable to match on.

    Load-bearing: ~710 Apple-Sign-In accounts have ``users.email = ''`` (the
    relay address was withheld at signup). An empty string compares *equal* to
    another empty string, so matching invites on a raw email makes every one of
    those accounts the same principal — one of them would resolve to another's
    membership row. A blank address must therefore drop out of the predicate
    entirely rather than compare equal to anything, and must never be stored.
    Identity is ``users.id``; an email is only the stand-in for an account that
    does not exist yet.
    """
    if email is None:
        return None
    return email.strip().lower() or None


# --- Slugs (D-D) ----------------------------------------------------------------
#
# Reserved now, exposed later. Auto-derived, never user-picked, and nothing
# public resolves one, so the only thing this buys today is that a team created
# now keeps its name when team pages ship. The reserved list is the set of path
# segments a future `/t/<slug>` route would collide with.

MAX_SLUG_LENGTH = 48
FALLBACK_SLUG_BASE = "team"
RESERVED_SLUGS = frozenset(
    {
        "admin",
        "api",
        "app",
        "auth",
        "billing",
        "blog",
        "dashboard",
        "docs",
        "help",
        "invite",
        "invites",
        "login",
        "logout",
        "me",
        "new",
        "pricing",
        "s",
        "settings",
        "signup",
        "support",
        "t",
        "team",
        "teams",
        "u",
        "user",
        "users",
        "vicoa",
        "www",
    }
)
_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def derive_slug_base(name: str) -> str:
    """Lowercase ASCII, runs of anything else collapsed to one hyphen."""
    base = _SLUG_NON_ALNUM.sub("-", (name or "").lower()).strip("-")
    base = base[:MAX_SLUG_LENGTH].rstrip("-")
    if len(base) < 2 or base in RESERVED_SLUGS:
        return FALLBACK_SLUG_BASE
    return base


def next_free_slug(db: Session, name: str, *, attempt: int = 0) -> str:
    base = derive_slug_base(name)
    taken = {
        row[0] for row in db.query(Team.slug).filter(Team.slug.like(f"{base}%")).all()
    }
    if attempt == 0 and base not in taken:
        return base
    suffix = max(attempt, 1) + 1
    while True:
        candidate = f"{base}-{suffix}"
        if candidate not in taken:
            return candidate
        suffix += 1


SLUG_ALLOCATION_ATTEMPTS = 5


# --- Teams --------------------------------------------------------------------


def _membership(db: Session, team_id: UUID, user_id: UUID) -> TeamMember | None:
    return (
        db.query(TeamMember)
        .filter(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
            TeamMember.status == "active",
        )
        .first()
    )


def require_team(
    db: Session, user_id: UUID, team_id: UUID, *, minimum: str = "viewer"
) -> tuple[Team, TeamMember]:
    """The team and the caller's active membership, or the matching error.

    `minimum` is a team role ('viewer' < 'member' < 'admin' < 'owner'); the
    default lets in anyone on the team."""
    membership = _membership(db, team_id, user_id)
    if membership is None:
        raise TeamNotFoundError("Team not found")
    if _TEAM_RANK[membership.role] < _TEAM_RANK[minimum]:
        raise TeamPermissionError(f"Requires team {minimum}")
    team = db.get(Team, team_id)
    assert team is not None  # FK
    return team, membership


_TEAM_RANK = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}


def _require_grant_admin(db: Session, user_id: UUID, project: Project) -> None:
    """Managing grants needs admin on *every* scope, not just one.

    `project_role` answers per scope, so a grantee holding
    `role=admin, scopes=["tasks"]` is admin as far as a single unscoped check
    can tell — and could therefore write itself a second grant with
    `scopes=["sessions"]` and read every session on the board. That is the
    boundary the two-lens design rests on, so grant administration is not a
    per-scope power: you cannot hand out, list, or revoke access on a scope you
    do not yourself administer. Owners and team members cover both scopes and
    are unaffected.
    """
    for scope in GRANT_SCOPES:
        access.require(
            access.project_role(db, user_id, project, grant_scope=scope), "admin"
        )


def _seat_count(db: Session, team_id: UUID) -> int:
    """Members who occupy a seat: everyone not removed in a role that edits,
    pending invites included — an invite is a promise of a seat. Viewers are
    free."""
    return (
        db.query(func.count(TeamMember.id))
        .filter(
            TeamMember.team_id == team_id,
            TeamMember.status != "removed",
            TeamMember.role.in_(TEAM_SEAT_ROLES),
        )
        .scalar()
        or 0
    )


# --- Seats (D-C) ----------------------------------------------------------------
#
# The open core counts, the overlay prices. Every metered action hands
# `check_capability` the size the payer's seat set would be *after* it, and the
# overlay compares that with the subscription. Nothing in the open core knows a
# price or a limit; with no hook registered the count is simply never read.
#
# "Every editor needs a seat" (§6, Team tier): everyone in a team the payer
# owns in a role that edits (invited or active — an invite is a promise of a
# seat), plus anyone holding editor/admin on the payer's work as a *user* (a
# project grant, or a WRITE share of one session). Viewers and commenters
# never appear, team viewers included. A team principal holding a grant rides
# on that team's own seats, so it is not counted again here.
#
# The core says *who*; whether someone's own subscription already covers them
# (their own Pro takes no seat on someone else's plan) is the overlay's call,
# which is why the capability context carries the keys and not only a count.

_PAID_GRANT_ROLES = ("editor", "admin")


def seat_key(user_id: UUID | None, email: str | None) -> str | None:
    """One person, however they were reached: their account, or — for an
    invite with no account behind it yet — the address it was sent to."""
    if user_id is not None:
        return f"user:{user_id}"
    key = _email_key(email)
    return f"email:{key}" if key is not None else None


def _paid_team_ids(db: Session, payer_id: UUID) -> set[UUID]:
    """Teams whose seats `payer_id` pays for: the ones they own (a team has
    exactly one owner until transfer ships in P7)."""
    rows = db.query(TeamMember.team_id).filter(
        TeamMember.user_id == payer_id,
        TeamMember.role == "owner",
        TeamMember.status == "active",
    )
    return {row[0] for row in rows}


def seat_keys(db: Session, payer_id: UUID) -> set[str]:
    """Everyone `payer_id`'s subscription covers, the payer included."""
    keys = {f"user:{payer_id}"}
    team_ids = _paid_team_ids(db, payer_id)

    def add(user_id: UUID | None, email: str | None) -> None:
        key = seat_key(user_id, email)
        if key is not None:
            keys.add(key)

    if team_ids:
        for user_id, email in db.query(
            TeamMember.user_id, TeamMember.invited_email
        ).filter(
            TeamMember.team_id.in_(team_ids),
            TeamMember.status != "removed",
            TeamMember.role.in_(TEAM_SEAT_ROLES),
        ):
            add(user_id, email)

    paid_projects = _paid_projects_select(payer_id, team_ids)
    for principal_id, email in db.query(
        ProjectGrant.principal_id, ProjectGrant.invited_email
    ).filter(
        ProjectGrant.principal_type == "user",
        ProjectGrant.role.in_(_PAID_GRANT_ROLES),
        ProjectGrant.project_id.in_(paid_projects),
    ):
        add(principal_id, email)

    for user_id, email in (
        db.query(UserInstanceAccess.user_id, UserInstanceAccess.shared_email)
        .join(AgentInstance, AgentInstance.id == UserInstanceAccess.agent_instance_id)
        .filter(
            AgentInstance.user_id == payer_id,
            AgentInstance.status != AgentStatus.DELETED,
            UserInstanceAccess.access == InstanceAccessLevel.WRITE,
        )
    ):
        add(user_id, email)
    return keys


def check_seat(
    db: Session,
    payer_id: UUID,
    capability: str,
    new_key: str | None,
    context: dict,
) -> None:
    """Ask the capability hooks whether `payer_id` may take on `new_key`.

    The context always carries `seats` (the seat set's size after the action)
    and `new_seat` (whether this action grows it). An action that reaches
    someone who already holds a seat reports `new_seat=False`, so a payer who
    is over their limit — a downgrade, say — can still reshuffle the people
    they already pay for.
    """
    check_seats(db, payer_id, capability, [new_key], context)


def check_seats(
    db: Session,
    payer_id: UUID,
    capability: str,
    new_keys: Iterable[str | None],
    context: dict,
) -> None:
    """`check_seat` for an action that can bring several people at once —
    moving a project (its outside editors come with it) or handing a team to
    a new owner (the whole team comes with it). Same context contract."""
    keys = seat_keys(db, payer_id)
    added = {key for key in new_keys if key is not None} - keys
    after = keys | added
    check_capability(
        db,
        payer_id,
        capability,
        {
            **context,
            "seats": len(after),
            "new_seat": bool(added),
            "seat_keys": sorted(after),
            "new_keys": sorted(added),
        },
    )


def _paid_grant_keys(db: Session, project_ids: Iterable[UUID]) -> set[str]:
    """Seat keys of the outside editors/admins on these projects — who comes
    along, seat-wise, when the projects change payer."""
    ids = list(project_ids)
    if not ids:
        return set()
    keys: set[str] = set()
    for principal_id, email in db.query(
        ProjectGrant.principal_id, ProjectGrant.invited_email
    ).filter(
        ProjectGrant.principal_type == "user",
        ProjectGrant.role.in_(_PAID_GRANT_ROLES),
        ProjectGrant.project_id.in_(ids),
    ):
        key = seat_key(principal_id, email)
        if key is not None:
            keys.add(key)
    return keys


def seat_usage(db: Session, payer_id: UUID) -> int:
    """How many seats `payer_id` currently pays for, themselves included —
    the number the billing page shows next to what their plan includes."""
    return len(seat_keys(db, payer_id))


# --- Lapsed seats (§6, Team tier) -------------------------------------------------
#
# When a Team subscription ends, the people it paid a seat for drop to read and
# comment until seats return; nothing is deleted. Each row keeps what it held
# (`lapsed_role` / `lapsed_at`) so editing comes back as it was. Which people
# lapse or come back is the overlay's decision (it knows the plan and who has
# their own Pro); the core only says who the payer's seat holders are and
# flips their rows.

_LAPSED_TEAM_ROLE = "viewer"
_LAPSED_GRANT_ROLE = "commenter"

SeatRow: TypeAlias = TeamMember | ProjectGrant | UserInstanceAccess


@dataclass(frozen=True)
class SeatHolder:
    """One person the payer's seats cover now (`live`) or did until they
    lapsed (`lapsed`). Someone reached several ways is one holder and can be
    both: a lapsed grant beside a membership the owner already restored."""

    key: str
    user_id: UUID | None
    since: datetime
    live: bool
    lapsed: bool


def _paid_projects_select(payer_id: UUID, team_ids: set[UUID]):
    return select(Project.id).where(
        or_(
            and_(Project.team_id.is_(None), Project.user_id == payer_id),
            Project.team_id.in_(team_ids),
        )
    )


def _seat_rows(db: Session, payer_id: UUID) -> list[tuple[str, SeatRow, bool]]:
    """(key, row, lapsed) for every row through which `payer_id` pays — or
    paid, before a lapse — for someone other than themselves."""
    team_ids = _paid_team_ids(db, payer_id)
    payer_key = f"user:{payer_id}"
    out: list[tuple[str, SeatRow, bool]] = []

    def keep(key: str | None, row: SeatRow, lapsed: bool) -> None:
        if key is not None and key != payer_key:
            out.append((key, row, lapsed))

    if team_ids:
        for member in db.query(TeamMember).filter(
            TeamMember.team_id.in_(team_ids),
            TeamMember.status != "removed",
            or_(
                TeamMember.role.in_(("admin", "member")),
                TeamMember.lapsed_role.is_not(None),
            ),
        ):
            keep(
                seat_key(member.user_id, member.invited_email),
                member,
                member.lapsed_role is not None,
            )
    for grant in db.query(ProjectGrant).filter(
        ProjectGrant.principal_type == "user",
        ProjectGrant.project_id.in_(_paid_projects_select(payer_id, team_ids)),
        or_(
            ProjectGrant.role.in_(_PAID_GRANT_ROLES),
            ProjectGrant.lapsed_role.is_not(None),
        ),
    ):
        keep(
            seat_key(grant.principal_id, grant.invited_email),
            grant,
            grant.lapsed_role is not None,
        )
    for share in (
        db.query(UserInstanceAccess)
        .join(AgentInstance, AgentInstance.id == UserInstanceAccess.agent_instance_id)
        .filter(
            AgentInstance.user_id == payer_id,
            AgentInstance.status != AgentStatus.DELETED,
            or_(
                UserInstanceAccess.access == InstanceAccessLevel.WRITE,
                UserInstanceAccess.lapsed_at.is_not(None),
            ),
        )
    ):
        keep(
            seat_key(share.user_id, share.shared_email),
            share,
            share.lapsed_at is not None,
        )
    return out


def _row_user_id(row: SeatRow) -> UUID | None:
    if isinstance(row, ProjectGrant):
        return row.principal_id
    return row.user_id


def seat_holders(db: Session, payer_id: UUID) -> list[SeatHolder]:
    """Everyone `payer_id`'s seats cover or covered, the payer left out,
    longest-standing first — the order a lapse keeps people in and a restore
    brings them back."""
    by_key: dict[str, SeatHolder] = {}
    for key, row, lapsed in _seat_rows(db, payer_id):
        current = by_key.get(key)
        since = row.created_at
        user_id = _row_user_id(row)
        if current is None:
            by_key[key] = SeatHolder(key, user_id, since, not lapsed, lapsed)
        else:
            by_key[key] = SeatHolder(
                key,
                current.user_id or user_id,
                min(current.since, since, key=_aware),
                current.live or not lapsed,
                current.lapsed or lapsed,
            )
    return sorted(by_key.values(), key=lambda h: (_aware(h.since), h.key))


def _aware(value: datetime) -> datetime:
    """`user_instance_access` timestamps are naive (UTC); the collab tables'
    are aware. Compare them as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def lapse_seats(db: Session, payer_id: UUID, keys: Iterable[str]) -> int:
    """Drop these holders to read-and-comment on everything `payer_id` pays
    for, remembering what each row held. Returns how many rows changed."""
    wanted = set(keys)
    if not wanted:
        return 0
    changed = 0
    affected: set[UUID | None] = set()
    for key, row, lapsed in _seat_rows(db, payer_id):
        if key not in wanted or lapsed:
            continue
        if isinstance(row, TeamMember):
            row.lapsed_role = row.role
            row.role = _LAPSED_TEAM_ROLE
        elif isinstance(row, ProjectGrant):
            row.lapsed_role = row.role
            row.role = _LAPSED_GRANT_ROLE
        else:
            row.lapsed_at = _utcnow()
            row.access = InstanceAccessLevel.READ
        changed += 1
        affected.add(_row_user_id(row))
    if changed:
        logger.info("lapsed %d seat row(s) paid by %s", changed, payer_id)
        notify_access_changed(db, affected)
        db.commit()
    return changed


def restore_seats(db: Session, payer_id: UUID, keys: Iterable[str]) -> int:
    """Give these holders back what they held before their seat lapsed.
    Returns how many rows changed."""
    wanted = set(keys)
    if not wanted:
        return 0
    changed = 0
    affected: set[UUID | None] = set()
    for key, row, lapsed in _seat_rows(db, payer_id):
        if key not in wanted or not lapsed:
            continue
        if isinstance(row, TeamMember):
            row.role = row.lapsed_role or "member"
            row.lapsed_role = None
        elif isinstance(row, ProjectGrant):
            row.role = row.lapsed_role or "editor"
            row.lapsed_role = None
        else:
            row.access = InstanceAccessLevel.WRITE
            row.lapsed_at = None
        changed += 1
        affected.add(_row_user_id(row))
    if changed:
        logger.info("restored %d seat row(s) paid by %s", changed, payer_id)
        notify_access_changed(db, affected)
        db.commit()
    return changed


def lapsed_payer_ids(db: Session, user_id: UUID) -> set[UUID]:
    """Payers holding a lapsed seat row for `user_id` — whose pools to look at
    again when this person gets a Pro of their own."""
    payers: set[UUID] = set()
    team_ids = [
        row[0]
        for row in db.query(TeamMember.team_id).filter(
            TeamMember.user_id == user_id,
            TeamMember.status != "removed",
            TeamMember.lapsed_role.is_not(None),
        )
    ]
    for team in db.query(Team).filter(Team.id.in_(team_ids)) if team_ids else []:
        payer = team_payer_id(db, team)
        if payer is not None:
            payers.add(payer)
    for project in (
        db.query(Project)
        .join(ProjectGrant, ProjectGrant.project_id == Project.id)
        .filter(
            ProjectGrant.principal_type == "user",
            ProjectGrant.principal_id == user_id,
            ProjectGrant.lapsed_role.is_not(None),
        )
    ):
        if project.team_id is None:
            payers.add(project.user_id)
        else:
            team = db.get(Team, project.team_id)
            payer = team_payer_id(db, team) if team is not None else None
            if payer is not None:
                payers.add(payer)
    for row in (
        db.query(AgentInstance.user_id)
        .join(
            UserInstanceAccess,
            UserInstanceAccess.agent_instance_id == AgentInstance.id,
        )
        .filter(
            UserInstanceAccess.user_id == user_id,
            UserInstanceAccess.lapsed_at.is_not(None),
        )
    ):
        payers.add(row[0])
    payers.discard(user_id)
    return payers


def _payer_id(db: Session, team: Team) -> UUID:
    """Whose subscription covers the team's seats: the owner member (D-C,
    owner-pays), falling back to the creator if the owner row is gone."""
    owner = (
        db.query(TeamMember.user_id)
        .filter(
            TeamMember.team_id == team.id,
            TeamMember.role == "owner",
            TeamMember.status == "active",
            TeamMember.user_id.is_not(None),
        )
        .order_by(TeamMember.created_at.asc())
        .first()
    )
    if owner is not None and owner[0] is not None:
        return owner[0]
    if team.created_by_user_id is not None:
        return team.created_by_user_id
    # Never `assert`: under `python -O` the check vanishes and this returns
    # None, which would reach `check_capability` as the payer id and silently
    # meter the wrong account. Fail loudly instead.
    raise TeamStateError("Team has no owner to bill")


def team_payer_id(db: Session, team: Team) -> UUID | None:
    """`_payer_id` for callers outside a request (the billing overlay working
    out whose seats cover someone): None instead of raising for a team in a
    state nobody can be billed from."""
    try:
        return _payer_id(db, team)
    except TeamStateError:
        return None


def list_user_teams(db: Session, user_id: UUID) -> list[tuple[Team, str, int]]:
    """(team, my role, member count) for every team the caller is active in —
    everyone not removed, viewers and pending invites included."""
    rows = (
        db.query(Team, TeamMember.role)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .filter(TeamMember.user_id == user_id, TeamMember.status == "active")
        .order_by(Team.name.asc())
        .all()
    )
    if not rows:
        return []
    counts: dict[UUID, int] = {
        row[0]: int(row[1])
        for row in db.query(TeamMember.team_id, func.count(TeamMember.id))
        .filter(
            TeamMember.team_id.in_([team.id for team, _ in rows]),
            TeamMember.status != "removed",
        )
        .group_by(TeamMember.team_id)
        .all()
    }
    return [(team, str(role), counts.get(team.id, 0)) for team, role in rows]


def create_team(db: Session, owner: User, name: str) -> Team:
    """Create a team with `owner` as its active owner. The owner edits
    everything the team owns, so owning one is asked of the capability hooks
    first (`collab.team_own`): a plan may require more than Free for it."""
    check_capability(
        db,
        owner.id,
        CAPABILITY_TEAM_OWN,
        {"action": "create_team", "team_id": None, "acting_user_id": str(owner.id)},
    )
    for attempt in range(SLUG_ALLOCATION_ATTEMPTS):
        nested = db.begin_nested()
        team = Team(
            name=name.strip(),
            slug=next_free_slug(db, name, attempt=attempt),
            created_by_user_id=owner.id,
        )
        db.add(team)
        try:
            db.flush()
            nested.commit()
            break
        except IntegrityError:
            nested.rollback()
            logger.info("team slug race for %r (attempt %d)", name, attempt + 1)
    else:
        raise TeamConflictError("Could not allocate a team slug")
    db.add(
        TeamMember(
            team_id=team.id,
            user_id=owner.id,
            # `_email_key`, not the raw address: an Apple-relay account has
            # `email = ''`, and storing that blank here is what let one such
            # account resolve to another's membership row.
            invited_email=_email_key(owner.email),
            role="owner",
            status="active",
            joined_at=_utcnow(),
        )
    )
    db.commit()
    db.refresh(team)
    return team


def update_team(db: Session, user_id: UUID, team_id: UUID, *, name: str) -> Team:
    team, _ = require_team(db, user_id, team_id, minimum="admin")
    team.name = name.strip()
    db.commit()
    return team


def set_team_avatar(
    db: Session, user_id: UUID, team_id: UUID, *, avatar_image_uri: str | None
) -> Team:
    """Point the team at its uploaded picture, or clear it (admin+).

    Mirrors the agent-profile avatar rather than the user one: a team has no
    IdP to re-seed it from, so clearing goes back to NULL instead of pinning
    `avatar_source='user'`. `updated_at` moves either way — clients
    cache-bust the stable served URL on it."""
    team, _ = require_team(db, user_id, team_id, minimum="admin")
    team.avatar_image_uri = avatar_image_uri
    team.avatar_source = "user" if avatar_image_uri else None
    team.updated_at = _utcnow()
    db.commit()
    db.refresh(team)
    return team


def transfer_team_ownership(
    db: Session, acting_user_id: UUID, team_id: UUID, member_id: UUID
) -> TeamMember:
    """Hand the team to another active member; the old owner stays on as admin.

    The owner is the payer (D-C, owner-pays), so the new owner has to be
    allowed to own a team at all (`collab.team_own`) and their plan has to
    cover what the team brings: its editing members and the outside editors on
    its projects (`collab.team_seat`). Both are asked of the new owner before
    anything changes, so a denial leaves the team exactly as it was."""
    team, acting = require_team(db, acting_user_id, team_id, minimum="owner")
    member = (
        db.query(TeamMember)
        .options(joinedload(TeamMember.user))
        .filter(
            TeamMember.id == member_id,
            TeamMember.team_id == team.id,
            TeamMember.status != "removed",
        )
        .first()
    )
    if member is None:
        raise TeamNotFoundError("Member not found")
    if member.id == acting.id:
        return member
    if member.status != "active" or member.user_id is None:
        raise TeamConflictError("Only someone who has joined can own the team")

    check_capability(
        db,
        member.user_id,
        CAPABILITY_TEAM_OWN,
        {
            "action": "transfer_ownership",
            "team_id": str(team.id),
            "acting_user_id": str(acting_user_id),
        },
    )
    brought = {
        seat_key(user_id, email)
        for user_id, email in db.query(
            TeamMember.user_id, TeamMember.invited_email
        ).filter(
            TeamMember.team_id == team.id,
            TeamMember.status != "removed",
            TeamMember.role.in_(TEAM_SEAT_ROLES),
        )
    }
    team_projects = [
        row[0] for row in db.query(Project.id).filter(Project.team_id == team.id)
    ]
    brought |= _paid_grant_keys(db, team_projects)
    check_seats(
        db,
        member.user_id,
        CAPABILITY_TEAM_SEAT,
        brought,
        {
            "team_id": str(team.id),
            "action": "transfer_ownership",
            "acting_user_id": str(acting_user_id),
        },
    )
    acting.role = "admin"
    member.role = "owner"
    member.lapsed_role = None
    notify_access_changed(db, [acting.user_id, member.user_id])
    db.commit()
    db.refresh(member)
    return member


def delete_team(db: Session, user_id: UUID, team_id: UUID) -> None:
    """Owner only. Members and invites cascade; projects and labels the team
    owned demote to personal (SET NULL); grants *to* the team are swept here
    because `principal_id` is polymorphic and has no FK."""
    team, _ = require_team(db, user_id, team_id, minimum="owner")
    notify_access_changed(db, team_member_ids(db, team.id))
    db.query(ProjectGrant).filter(
        ProjectGrant.principal_type == "team", ProjectGrant.principal_id == team.id
    ).delete(synchronize_session=False)
    release_team_rows(db, [team.id])
    db.delete(team)
    db.commit()


def reassign_team_rows_from(db: Session, user_id: UUID) -> None:
    """Hand the team-owned rows `user_id` created to each team's owner, ahead
    of deleting the account.

    On a team's project, label or agent, `user_id` only records who created
    it — but the column's FK CASCADEs, so deleting the creator's account would
    take the team's work with it (and every task on the project, since
    `tasks.user_id` is the project's `user_id`). Each row moves to its team's
    active owner instead; `delete_user_account` runs this after promoting an
    heir, so every surviving team has one. A team with nobody left is being
    deleted anyway (`release_team_rows` handles its rows).
    """
    team_ids = {
        row[0]
        for model in (Project, TaskLabel, AgentProfile)
        for row in db.query(model.team_id).filter(
            model.user_id == user_id, model.team_id.is_not(None)
        )
    }
    for team_id in team_ids:
        owner = (
            db.query(TeamMember.user_id)
            .filter(
                TeamMember.team_id == team_id,
                TeamMember.role == "owner",
                TeamMember.status == "active",
                TeamMember.user_id.is_not(None),
                TeamMember.user_id != user_id,
            )
            .order_by(TeamMember.created_at.asc())
            .first()
        )
        if owner is None:
            continue
        heir = owner[0]
        project_ids = [
            row[0]
            for row in db.query(Project.id).filter(
                Project.team_id == team_id, Project.user_id == user_id
            )
        ]
        if project_ids:
            db.query(Project).filter(Project.id.in_(project_ids)).update(
                {"user_id": heir}, synchronize_session=False
            )
            # `tasks.user_id` is always the owning project's `user_id`.
            db.query(Task).filter(Task.project_id.in_(project_ids)).update(
                {"user_id": heir}, synchronize_session=False
            )
        for model in (TaskLabel, AgentProfile):
            db.query(model).filter(
                model.team_id == team_id, model.user_id == user_id
            ).update({"user_id": heir}, synchronize_session=False)


_MAX_AGENT_NAME = 64


def release_team_rows(db: Session, team_ids: Iterable[UUID]) -> None:
    """Hand a team's projects and agents back to their creators ahead of the
    team's deletion, making room for them first.

    `ON DELETE SET NULL` is the right demotion (§3.3: deleting a team never
    destroys work), but it lands each row in its creator's personal space,
    where a project key or an agent name may already be taken — and one
    unique-index violation would fail the whole delete. So each row is
    demoted here, explicitly: a clashing key gets the next free one (VIC →
    VIC2, as on a move), a clashing agent is renamed "Name (Team)". Labels
    need nothing: their names are not unique."""
    ids = list(team_ids)
    if not ids:
        return
    for project in (
        db.query(Project)
        .filter(Project.team_id.in_(ids))
        .order_by(Project.created_at.asc())
        .all()
    ):
        if project.key and key_is_taken(db, project.user_id, project.key):
            project.key = suggest_free_key(db, project.user_id, project.key)
        project.team_id = None
        # So the next project's check sees this one in its new namespace.
        db.flush()

    team_names = {
        team.id: team.name for team in db.query(Team).filter(Team.id.in_(ids))
    }
    for profile in (
        db.query(AgentProfile)
        .filter(AgentProfile.team_id.in_(ids), AgentProfile.is_archived.is_(False))
        .order_by(AgentProfile.created_at.asc())
        .all()
    ):
        taken = {
            row[0]
            for row in db.query(func.lower(AgentProfile.name)).filter(
                AgentProfile.user_id == profile.user_id,
                AgentProfile.team_id.is_(None),
                AgentProfile.is_archived.is_(False),
            )
        }
        if profile.name.lower() in taken:
            team_name = (
                team_names.get(profile.team_id) if profile.team_id else None
            ) or "team"
            base = f"{profile.name} ({team_name})"
            candidate, suffix = base[:_MAX_AGENT_NAME], 2
            while candidate.lower() in taken:
                tail = f" {suffix}"
                candidate = base[: _MAX_AGENT_NAME - len(tail)] + tail
                suffix += 1
            profile.name = candidate
        profile.team_id = None
        db.flush()


def list_members(db: Session, team: Team) -> list[TeamMember]:
    """Everyone on the team — active and invited, viewers included — oldest
    first."""
    return (
        db.query(TeamMember)
        .options(joinedload(TeamMember.user))
        .filter(TeamMember.team_id == team.id, TeamMember.status != "removed")
        .order_by(TeamMember.created_at.asc())
        .all()
    )


def invite_member(
    db: Session,
    acting_user_id: UUID,
    team_id: UUID,
    *,
    email: str,
    role: str = "member",
) -> TeamMember:
    """Invite by email. Owner/admin; only the owner hands out `admin`.

    If the address already belongs to an account the row is attached to it
    immediately but stays `invited` until that person accepts — being added
    to a team is a thing you agree to. A previously removed member is revived
    in place rather than duplicated (the (team, user) uniqueness). A `viewer`
    takes no seat, so inviting one is never metered.
    """
    team, acting = require_team(db, acting_user_id, team_id, minimum="admin")
    if role == "owner":
        raise TeamConflictError("A team has one owner")
    if role == "admin" and acting.role != "owner":
        raise TeamPermissionError("Only the team owner can invite admins")

    normalized = email.strip().lower()
    if not normalized:
        raise TeamConflictError("Email is required")
    target = db.query(User).filter(func.lower(User.email) == normalized).first()

    match = [func.lower(TeamMember.invited_email) == normalized]
    if target is not None:
        match.append(TeamMember.user_id == target.id)
    existing = (
        db.query(TeamMember).filter(TeamMember.team_id == team.id, or_(*match)).first()
    )
    if existing is not None and existing.status != "removed":
        raise TeamConflictError("That person is already on the team")

    if role in TEAM_SEAT_ROLES:
        check_seat(
            db,
            _payer_id(db, team),
            CAPABILITY_TEAM_SEAT,
            seat_key(target.id if target else None, normalized),
            {
                "team_id": str(team.id),
                "team_seats": _seat_count(db, team.id) + 1,
                "role": role,
                "acting_user_id": str(acting_user_id),
            },
        )

    if existing is not None:
        member = existing
        member.status = "invited"
        member.role = role
        member.lapsed_role = None
        member.invited_email = email.strip()
        member.user_id = target.id if target else None
        member.invited_by_user_id = acting_user_id
        member.joined_at = None
    else:
        member = TeamMember(
            team_id=team.id,
            user_id=target.id if target else None,
            invited_email=email.strip(),
            role=role,
            status="invited",
            invited_by_user_id=acting_user_id,
        )
        db.add(member)
    db.commit()
    db.refresh(member)
    return member


def _pending_filter(user: User):
    """Match a membership row to this person: by account always, by email only
    when they actually have one (`_email_key`). A blank address must not widen
    the predicate."""
    terms = [TeamMember.user_id == user.id]
    key = _email_key(user.email)
    if key is not None:
        terms.append(func.lower(TeamMember.invited_email) == key)
    return or_(*terms)


def list_pending_invitations(db: Session, user: User) -> list[TeamMember]:
    """Invites waiting on this person — matched by account or by email, so an
    invite sent before they signed up is found the moment they do."""
    return (
        db.query(TeamMember)
        .options(joinedload(TeamMember.team))
        .filter(TeamMember.status == "invited", _pending_filter(user))
        .order_by(TeamMember.created_at.asc())
        .all()
    )


def accept_invitation(db: Session, user: User, team_id: UUID) -> TeamMember:
    member = (
        db.query(TeamMember)
        .filter(
            TeamMember.team_id == team_id,
            TeamMember.status == "invited",
            _pending_filter(user),
        )
        .first()
    )
    if member is None:
        raise TeamNotFoundError("No pending invitation")
    member.user_id = user.id
    member.status = "active"
    member.joined_at = _utcnow()
    notify_access_changed(db, [user.id])
    db.commit()
    db.refresh(member)
    return member


def decline_invitation(db: Session, user: User, team_id: UUID) -> None:
    member = (
        db.query(TeamMember)
        .filter(
            TeamMember.team_id == team_id,
            TeamMember.status == "invited",
            _pending_filter(user),
        )
        .first()
    )
    if member is None:
        raise TeamNotFoundError("No pending invitation")
    db.delete(member)
    db.commit()


def update_member_role(
    db: Session, acting_user_id: UUID, team_id: UUID, member_id: UUID, *, role: str
) -> TeamMember:
    """Owner only; the owner row itself is immutable here (ownership moves
    through `transfer_team_ownership`). Making a viewer an admin or member is
    metered like inviting one; anything else stays inside what is paid for. An
    explicit role also ends a lapse: the owner has decided."""
    team, _ = require_team(db, acting_user_id, team_id, minimum="owner")
    member = (
        db.query(TeamMember)
        .options(joinedload(TeamMember.user))
        .filter(
            TeamMember.id == member_id,
            TeamMember.team_id == team.id,
            TeamMember.status != "removed",
        )
        .first()
    )
    if member is None:
        raise TeamNotFoundError("Member not found")
    if member.role == "owner" or role == "owner":
        raise TeamConflictError("Ownership cannot be changed here")
    if role in TEAM_SEAT_ROLES and member.role not in TEAM_SEAT_ROLES:
        check_seat(
            db,
            _payer_id(db, team),
            CAPABILITY_TEAM_SEAT,
            seat_key(member.user_id, member.invited_email),
            {
                "team_id": str(team.id),
                "team_seats": _seat_count(db, team.id) + 1,
                "role": role,
                "acting_user_id": str(acting_user_id),
            },
        )
    member.role = role
    member.lapsed_role = None
    notify_access_changed(db, [member.user_id])
    db.commit()
    db.refresh(member)
    return member


def remove_member(
    db: Session, acting_user_id: UUID, team_id: UUID, member_id: UUID
) -> None:
    """Owner/admin remove others; anyone but the owner may remove themselves.
    Admins cannot remove other admins. The row is kept as `removed`."""
    team, acting = require_team(db, acting_user_id, team_id)
    member = (
        db.query(TeamMember)
        .filter(
            TeamMember.id == member_id,
            TeamMember.team_id == team.id,
            TeamMember.status != "removed",
        )
        .first()
    )
    if member is None:
        raise TeamNotFoundError("Member not found")
    if member.role == "owner":
        raise TeamConflictError("The team owner cannot be removed")
    is_self = member.id == acting.id
    if not is_self:
        if acting.role in ("member", "viewer"):
            raise TeamPermissionError("Only owners or admins can remove members")
        if acting.role == "admin" and member.role == "admin":
            raise TeamPermissionError("Admins can only remove members or themselves")
    member.status = "removed"
    notify_access_changed(db, [member.user_id])
    db.commit()


# --- Invite links -------------------------------------------------------------


def create_invite_link(
    db: Session,
    acting_user_id: UUID,
    team_id: UUID,
    *,
    role: str = "member",
    expires_in_days: int | None = 7,
    max_uses: int | None = None,
) -> TeamInvite:
    team, acting = require_team(db, acting_user_id, team_id, minimum="admin")
    if role == "owner":
        raise TeamConflictError("A team has one owner")
    if role == "admin" and acting.role != "owner":
        raise TeamPermissionError("Only the team owner can create admin invites")
    invite = TeamInvite(
        team_id=team.id,
        token=secrets.token_urlsafe(32),
        role=role,
        expires_at=(
            _utcnow() + timedelta(days=expires_in_days)
            if expires_in_days is not None
            else None
        ),
        max_uses=max_uses,
        created_by_user_id=acting_user_id,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


def list_invite_links(
    db: Session, acting_user_id: UUID, team_id: UUID
) -> list[TeamInvite]:
    team, _ = require_team(db, acting_user_id, team_id, minimum="admin")
    return (
        db.query(TeamInvite)
        .filter(TeamInvite.team_id == team.id, TeamInvite.revoked_at.is_(None))
        .order_by(TeamInvite.created_at.desc())
        .all()
    )


def revoke_invite_link(
    db: Session, acting_user_id: UUID, team_id: UUID, invite_id: UUID
) -> None:
    team, _ = require_team(db, acting_user_id, team_id, minimum="admin")
    invite = (
        db.query(TeamInvite)
        .filter(TeamInvite.id == invite_id, TeamInvite.team_id == team.id)
        .first()
    )
    if invite is None:
        raise InviteNotFoundError("Invite not found")
    if invite.revoked_at is None:
        invite.revoked_at = _utcnow()
        db.commit()


def _invite_is_spent(invite: TeamInvite) -> bool:
    """Revoked, expired or used up. Shared by `resolve_invite_link` and the
    re-check `accept_invite_link` runs under the row lock, so the two can never
    disagree about what "live" means."""
    return (
        invite.revoked_at is not None
        or (invite.expires_at is not None and invite.expires_at <= _utcnow())
        or (invite.max_uses is not None and invite.uses >= invite.max_uses)
    )


def resolve_invite_link(db: Session, token: str) -> TeamInvite:
    """The live invite behind `token`, or `InviteNotFoundError` — the same
    error whether the token is unknown, revoked, expired or used up."""
    invite = (
        db.query(TeamInvite)
        .options(joinedload(TeamInvite.team))
        .filter(TeamInvite.token == token)
        .first()
    )
    if invite is None or _invite_is_spent(invite):
        raise InviteNotFoundError("Invite not found")
    return invite


def accept_invite_link(db: Session, user: User, token: str) -> TeamMember:
    """Redeem a join link. An already-active member is simply returned; a
    pending or removed row is activated in place."""
    invite = resolve_invite_link(db, token)
    # Serialize concurrent redemptions of this team's links. Both the
    # exhaustion check above and the seat count below are read-check-write, so
    # without this two people clicking a `max_uses=1` link at the same instant
    # each see room for one more and both get in. The lock is on the *team*,
    # not the invite row, because `_seat_count` aggregates over `team_members`
    # — locking only the invite would still let two different links race the
    # same seat limit.
    db.query(Team).filter(Team.id == invite.team_id).with_for_update().one()
    # Re-read under the lock: whoever we queued behind has committed by now.
    db.refresh(invite)
    if _invite_is_spent(invite):
        raise InviteNotFoundError("Invite not found")

    team = invite.team
    member = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team.id, _pending_filter(user))
        # An account row and an email row can both match; the account row is
        # the authoritative one, so make the pick deterministic instead of
        # leaving it to scan order.
        .order_by(
            case((TeamMember.user_id == user.id, 0), else_=1),
            TeamMember.created_at.asc(),
        )
        .first()
    )
    if member is not None and member.status == "active":
        return member

    # A viewer link takes no seat. A pending row in a seat role already holds
    # its seat (under the address it was sent to), so redeeming a link on top
    # of one adds nobody.
    if invite.role in TEAM_SEAT_ROLES:
        holds_seat = (
            member is not None
            and member.status == "invited"
            and member.role in TEAM_SEAT_ROLES
        )
        check_seat(
            db,
            _payer_id(db, team),
            CAPABILITY_TEAM_SEAT,
            None if holds_seat else seat_key(user.id, None),
            {
                "team_id": str(team.id),
                "team_seats": _seat_count(db, team.id) + (0 if holds_seat else 1),
                "role": invite.role,
                "acting_user_id": str(user.id),
            },
        )
    if member is None:
        member = TeamMember(
            team_id=team.id,
            user_id=user.id,
            invited_email=user.email,
            role=invite.role,
            invited_by_user_id=invite.created_by_user_id,
        )
        db.add(member)
    else:
        member.user_id = user.id
        member.role = invite.role
        member.lapsed_role = None
    member.status = "active"
    member.joined_at = _utcnow()
    # SQL-side increment. `invite.uses + 1` in Python emits `SET uses = <n>`
    # from the value we happened to read, which loses a concurrent increment
    # even when the lock above serialises the decision.
    invite.uses = TeamInvite.uses + 1
    notify_access_changed(db, [user.id])
    db.commit()
    db.refresh(member)
    return member


# --- Project ownership --------------------------------------------------------
#
# `projects.team_id` NULL ⇒ personal, SET ⇒ team-owned (§2 layer 2). Moving a
# project changes who owns it, not what it holds: tasks, sessions, grants and
# share links all stay attached by id. What does have to follow is everything
# keyed by the *owner* — the task key namespace (§3.5), the label vocabulary
# (§3.3) and the payer's seats (§6).


class ProjectKeyConflictError(Exception):
    """The project's task key is already held in the destination's key
    namespace (→ 409). Keys are unique within the owner (§3.5), so a move can
    collide where the project never did; the caller picks a new key, and
    `suggested_key` is one that is free there."""

    def __init__(self, key: str, suggested_key: str) -> None:
        super().__init__(f"Another project there already uses the key {key}")
        self.key = key
        self.suggested_key = suggested_key


def _carry_labels(
    db: Session,
    project: Project,
    *,
    team_id: UUID | None,
    owner_user_id: UUID,
    acting_user_id: UUID,
) -> None:
    """Re-point the project's task labels into the new owner's vocabulary.

    Labels are owner-scoped (one vocabulary per person or team, never per
    project), so a label from the old owner's set would stay on its tasks but
    drop out of every picker on the board — and `_resolve_labels` would then
    refuse the task's own labels on the next edit. Each such label is matched
    by name in the destination vocabulary, or copied into it (name and colour)
    when there is no match. The old labels are left where they are: they
    still belong to their owner's other projects.
    """
    links = db.execute(
        select(task_label_links.c.task_id, task_label_links.c.label_id)
        .join(Task, Task.id == task_label_links.c.task_id)
        .where(Task.project_id == project.id)
    ).all()
    if not links:
        return

    def in_destination(label: TaskLabel) -> bool:
        if team_id is not None:
            return label.team_id == team_id
        return label.team_id is None and label.user_id == owner_user_id

    labels = (
        db.query(TaskLabel)
        .filter(TaskLabel.id.in_({label_id for _, label_id in links}))
        .all()
    )
    foreign = [label for label in labels if not in_destination(label)]
    if not foreign:
        return

    destination = (
        TaskLabel.team_id == team_id
        if team_id is not None
        else and_(TaskLabel.user_id == owner_user_id, TaskLabel.team_id.is_(None))
    )
    by_name = {
        label.name.strip().lower(): label
        for label in db.query(TaskLabel).filter(destination)
    }
    replacement: dict[UUID, UUID] = {}
    for label in foreign:
        match = by_name.get(label.name.strip().lower())
        if match is None:
            match = TaskLabel(
                user_id=acting_user_id if team_id is not None else owner_user_id,
                team_id=team_id,
                name=label.name,
                color=label.color,
            )
            db.add(match)
            db.flush()
            by_name[label.name.strip().lower()] = match
        replacement[label.id] = match.id

    present = {(task_id, label_id) for task_id, label_id in links}
    for task_id, label_id in links:
        new_id = replacement.get(label_id)
        if new_id is None:
            continue
        db.execute(
            delete(task_label_links).where(
                task_label_links.c.task_id == task_id,
                task_label_links.c.label_id == label_id,
            )
        )
        if (task_id, new_id) not in present:
            db.execute(
                insert(task_label_links).values(task_id=task_id, label_id=new_id)
            )
            present.add((task_id, new_id))


def transfer_project(
    db: Session,
    user: User,
    project: Project,
    *,
    team_id: UUID | None,
    key: str | None = None,
) -> Project:
    """Move a project into a team (`team_id`), or out of one into the caller's
    personal space (`team_id=None`).

    Owner only: the personal owner, or the owner of the team that owns it —
    the same floor as deleting it, since both end the current owner's hold on
    the project. Moving *into* a team needs an active membership there; a
    plain member may bring their own project in, becoming an editor of it the
    moment it lands (the team's role map, §4 as-built).

    `key` replaces the task key on the way (§3.5). When the project's key is
    already held in the destination and no new one is given, this raises
    `ProjectKeyConflictError` with a free suggestion and changes nothing.

    Seats (§6): the destination's payer takes on the project's outside
    editors, so that is asked of `collab.grant_write` before anything moves.
    """
    target_team: Team | None = None
    if team_id is not None:
        trole = access.team_role(db, user.id, team_id)
        if trole is None:
            raise TeamNotFoundError("Team not found")
        if not access.can_edit_in_team(trole):
            raise TeamPermissionError("Viewers can't move projects into the team")
        target_team = db.get(Team, team_id)
        assert target_team is not None  # an active membership implies the row
    if project.team_id == team_id and (
        team_id is not None or project.user_id == user.id
    ):
        if key is None or key == project.key:
            return project

    # Serialize concurrent moves of one project; the key check below is
    # read-check-write against the destination namespace.
    db.query(Project).filter(Project.id == project.id).with_for_update().one()
    new_owner_id = user.id if team_id is None else project.user_id

    wanted = key or project.key
    moving = project.team_id != team_id or project.user_id != new_owner_id
    if wanted is not None and (moving or wanted != project.key):
        if key_is_taken(db, new_owner_id, wanted, team_id=team_id):
            raise ProjectKeyConflictError(
                wanted, suggest_free_key(db, new_owner_id, wanted, team_id=team_id)
            )

    if moving:
        payer_id = _payer_id(db, target_team) if target_team is not None else user.id
        brought = _paid_grant_keys(db, [project.id])
        if team_id is None:
            # A grant to the new personal owner is dropped below, so it
            # brings no one.
            brought.discard(f"user:{new_owner_id}")
        check_seats(
            db,
            payer_id,
            CAPABILITY_GRANT_WRITE,
            brought,
            {
                "project_id": str(project.id),
                "action": "transfer_project",
                "team_id": str(team_id) if team_id else None,
                "acting_user_id": str(user.id),
            },
        )

    old_team_id, old_owner_id = project.team_id, project.user_id
    project.key = wanted
    if moving:
        project.team_id = team_id
        project.user_id = new_owner_id
        if new_owner_id != old_owner_id:
            # `tasks.user_id` is always the owning project's `user_id` (the
            # task_queries module invariant), so the owner-only lens keeps
            # seeing every task on the board it now owns.
            db.query(Task).filter(Task.project_id == project.id).update(
                {"user_id": new_owner_id}, synchronize_session=False
            )
        _carry_labels(
            db,
            project,
            team_id=team_id,
            owner_user_id=new_owner_id,
            acting_user_id=user.id,
        )
        # A grant to whoever now owns the project confers nothing on top of
        # ownership; leaving it would make them a "collaborator" on their own
        # project in the People list.
        redundant = (
            and_(
                ProjectGrant.principal_type == "team",
                ProjectGrant.principal_id == team_id,
            )
            if team_id is not None
            else and_(
                ProjectGrant.principal_type == "user",
                ProjectGrant.principal_id == new_owner_id,
            )
        )
        db.query(ProjectGrant).filter(
            ProjectGrant.project_id == project.id, redundant
        ).delete(synchronize_session=False)
        notify_access_changed(
            db,
            {old_owner_id, new_owner_id}
            | team_member_ids(db, old_team_id)
            | team_member_ids(db, team_id),
            project_id=project.id,
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if wanted is None:
            raise
        # Lost a race for the key in the destination namespace — the only
        # unique constraint a move can trip.
        raise ProjectKeyConflictError(
            wanted, suggest_free_key(db, new_owner_id, wanted, team_id=team_id)
        ) from exc
    db.refresh(project)
    return project


# --- Project grants -----------------------------------------------------------
#
# The People tab (§8.4). Listing and writing both need admin on *both* scopes
# (`_require_grant_admin`), so everyone who can see a grant's address is the
# audience §10.4 allows. One exception: `leave_project` lets a grantee drop
# their own direct grant, the way out of a project someone shared with them.


def list_project_grants(
    db: Session, user_id: UUID, project: Project
) -> list[ProjectGrant]:
    _require_grant_admin(db, user_id, project)
    return (
        db.query(ProjectGrant)
        .filter(ProjectGrant.project_id == project.id)
        .order_by(ProjectGrant.created_at.asc())
        .all()
    )


def _check_grant_seat(
    db: Session,
    acting_user_id: UUID,
    project: Project,
    *,
    role: str,
    principal_id: UUID | None,
    invited_email: str | None,
) -> None:
    """`collab.grant_write` for an editor/admin *user* grant (D-C). Viewers
    and commenters are free (D-A) and a team principal rides on its team's
    seats, so neither reaches here. The payer is whoever pays for the project:
    its personal owner, or the owner of the team that owns it."""
    team = db.get(Team, project.team_id) if project.team_id is not None else None
    payer_id = _payer_id(db, team) if team is not None else project.user_id
    check_seat(
        db,
        payer_id,
        CAPABILITY_GRANT_WRITE,
        seat_key(principal_id, invited_email),
        {
            "project_id": str(project.id),
            "role": role,
            "principal_type": "user",
            "principal_id": str(principal_id) if principal_id else None,
            "acting_user_id": str(acting_user_id),
        },
    )


def create_project_grant(
    db: Session,
    granter_user_id: UUID,
    project: Project,
    *,
    principal_type: str,
    principal_id: UUID | None = None,
    invited_email: str | None = None,
    role: str,
    scopes: list[str] | None = None,
) -> ProjectGrant:
    """Grant `role` on `project` to a user, a pending email, or a team.

    Admin+ on the project. `viewer` / `commenter` are always free (D-A); an
    `editor` / `admin` grant to someone outside the owner's teams is what the
    `collab.grant_write` capability meters (D-C) — team principals are already
    covered by their team's seats.
    """
    _require_grant_admin(db, granter_user_id, project)
    if role not in GRANT_ROLES:
        raise GrantError("Unknown role")
    scopes = list(scopes) if scopes is not None else list(GRANT_SCOPES)
    if not scopes or any(s not in GRANT_SCOPES for s in scopes):
        raise GrantError("scopes must be a non-empty subset of tasks/sessions")
    # Normalise before the emptiness check below: `not "   "` is False, so a
    # whitespace-only address used to pass the guard and then be stored as ''
    # by `.strip()`, where `claim_pending_invites` would hand it to the next
    # blank-email signup.
    invited_email = _email_key(invited_email)

    if principal_type == "team":
        if (
            principal_id is None
            or access.team_role(db, granter_user_id, principal_id) is None
        ):
            raise GrantError("Team not found")
        invited_email = None
    elif principal_type == "user":
        if principal_id is None and invited_email:
            target = (
                db.query(User).filter(func.lower(User.email) == invited_email).first()
            )
            principal_id = target.id if target else None
        if principal_id is None and not invited_email:
            raise GrantError("A user id or email is required")
        if principal_id == project.user_id and project.team_id is None:
            raise GrantError("The owner already has full access")
    else:
        raise GrantError("Unknown principal type")

    if principal_type == "user" and access.role_at_least(role, "editor"):
        _check_grant_seat(
            db,
            granter_user_id,
            project,
            role=role,
            principal_id=principal_id,
            invited_email=invited_email,
        )

    grant = ProjectGrant(
        project_id=project.id,
        principal_type=principal_type,
        principal_id=principal_id,
        invited_email=invited_email,
        role=role,
        scopes=scopes,
        granted_by_user_id=granter_user_id,
    )
    db.add(grant)
    notify_access_changed(
        db, principal_user_ids(db, principal_type, principal_id), project_id=project.id
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise GrantConflictError(
            "That person or team already has access to this project"
        ) from exc
    return grant


def _project_grant(db: Session, project: Project, grant_id: UUID) -> ProjectGrant:
    grant = (
        db.query(ProjectGrant)
        .filter(ProjectGrant.id == grant_id, ProjectGrant.project_id == project.id)
        .first()
    )
    if grant is None:
        raise GrantNotFoundError("Grant not found")
    return grant


def update_project_grant(
    db: Session,
    user_id: UUID,
    project: Project,
    grant_id: UUID,
    *,
    role: str | None = None,
    scopes: list[str] | None = None,
) -> ProjectGrant:
    """Change a grant's role and/or scopes. Admin on both scopes, like every
    other grant write. Moving a user grant *into* editor/admin is metered the
    same way creating one is; a change that stays inside the paid roles (or
    only touches scopes) never is, so a payer over their limit can still
    reshape the access they already pay for."""
    _require_grant_admin(db, user_id, project)
    grant = _project_grant(db, project, grant_id)
    if role is not None:
        if role not in GRANT_ROLES:
            raise GrantError("Unknown role")
        becomes_paid = access.role_at_least(role, "editor") and not (
            access.role_at_least(grant.role, "editor")
        )
        if grant.principal_type == "user" and becomes_paid:
            _check_grant_seat(
                db,
                user_id,
                project,
                role=role,
                principal_id=grant.principal_id,
                invited_email=grant.invited_email,
            )
        grant.role = role
        # An explicit role ends a lapse: whoever administers it has decided.
        grant.lapsed_role = None
    if scopes is not None:
        if not scopes or any(s not in GRANT_SCOPES for s in scopes):
            raise GrantError("scopes must be a non-empty subset of tasks/sessions")
        grant.scopes = [s for s in GRANT_SCOPES if s in scopes]
    notify_access_changed(
        db,
        principal_user_ids(db, grant.principal_type, grant.principal_id),
        project_id=project.id,
    )
    db.commit()
    return grant


def delete_project_grant(
    db: Session, user_id: UUID, project: Project, grant_id: UUID
) -> bool:
    _require_grant_admin(db, user_id, project)
    grant = (
        db.query(ProjectGrant)
        .filter(ProjectGrant.id == grant_id, ProjectGrant.project_id == project.id)
        .first()
    )
    if grant is None:
        return False
    notify_access_changed(
        db,
        principal_user_ids(db, grant.principal_type, grant.principal_id),
        project_id=project.id,
    )
    db.delete(grant)
    db.commit()
    return True


def leave_project(db: Session, user: User, project: Project) -> None:
    """Drop the caller's own grant on a project shared with them.

    Only a direct user grant can be left this way. Access that arrives through
    a team is the team's to give up (leave the team instead), and an owner
    cannot leave what they own — both answer `GrantError` (→ 409) rather than
    silently succeeding and leaving the project in the sidebar.
    """
    if project.team_id is None and project.user_id == user.id:
        raise GrantConflictError("You own this project")
    deleted = (
        db.query(ProjectGrant)
        .filter(
            ProjectGrant.project_id == project.id,
            ProjectGrant.principal_type == "user",
            ProjectGrant.principal_id == user.id,
        )
        .delete(synchronize_session=False)
    )
    if not deleted:
        raise GrantConflictError("Your access to this project comes from a team")
    notify_access_changed(db, [user.id], project_id=project.id)
    db.commit()


def claim_pending_invites(db: Session, user: User) -> int:
    """Attach everything addressed to this account's email before the account
    could hold it: project grants and per-session shares. Team invites need no
    such step — they are matched by email when read, and joining is an
    explicit accept.

    Runs at signup and again whenever the account menu loads invitations
    (`GET /teams/invitations`), so an account first created by another path
    — the billing webhook's `sync_user_from_provider`, say, which discards
    `created` — or one whose address changed still converges without a query
    on every request. Idempotent: a second run finds nothing.
    """
    key = _email_key(user.email)
    if key is None:
        # An account with no usable address (Apple relay withheld) can claim
        # nothing by email — and must not, or it would claim every grant left
        # blank by some other writer.
        return 0
    claimed = 0

    grants = (
        db.query(ProjectGrant)
        .filter(
            ProjectGrant.principal_type == "user",
            ProjectGrant.principal_id.is_(None),
            func.lower(ProjectGrant.invited_email) == key,
        )
        .all()
    )
    if grants:
        already = {
            row[0]
            for row in db.query(ProjectGrant.project_id).filter(
                ProjectGrant.project_id.in_([g.project_id for g in grants]),
                ProjectGrant.principal_type == "user",
                ProjectGrant.principal_id == user.id,
            )
        }
        for grant in grants:
            # A grant reached this account by id since the email one was
            # sent; the (project, principal) uniqueness allows one. Keep the
            # explicit one and drop the stale invite.
            if grant.project_id in already:
                db.delete(grant)
            else:
                grant.principal_id = user.id
                claimed += 1

    shares = (
        db.query(UserInstanceAccess)
        .filter(
            UserInstanceAccess.user_id.is_(None),
            func.lower(UserInstanceAccess.shared_email) == key,
        )
        .all()
    )
    if shares:
        already = {
            row[0]
            for row in db.query(UserInstanceAccess.agent_instance_id).filter(
                UserInstanceAccess.agent_instance_id.in_(
                    [s.agent_instance_id for s in shares]
                ),
                UserInstanceAccess.user_id == user.id,
            )
        }
        for share in shares:
            if share.agent_instance_id in already:
                db.delete(share)
            else:
                share.user_id = user.id
                claimed += 1

    if grants or shares:
        if claimed:
            notify_access_changed(db, [user.id])
        db.commit()
    return claimed
