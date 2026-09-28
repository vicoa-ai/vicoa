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
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from shared import access
from shared.database import (
    GRANT_ROLES,
    GRANT_SCOPES,
    AgentInstance,
    Project,
    ProjectGrant,
    Team,
    TeamInvite,
    TeamMember,
    User,
    UserInstanceAccess,
)
from shared.database.enums import AgentStatus, InstanceAccessLevel
from shared.hooks import (
    CAPABILITY_GRANT_WRITE,
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
    db: Session, user_id: UUID, team_id: UUID, *, minimum: str = "member"
) -> tuple[Team, TeamMember]:
    """The team and the caller's active membership, or the matching error.

    `minimum` is a team role ('member' < 'admin' < 'owner')."""
    membership = _membership(db, team_id, user_id)
    if membership is None:
        raise TeamNotFoundError("Team not found")
    if _TEAM_RANK[membership.role] < _TEAM_RANK[minimum]:
        raise TeamPermissionError(f"Requires team {minimum}")
    team = db.get(Team, team_id)
    assert team is not None  # FK
    return team, membership


_TEAM_RANK = {"member": 1, "admin": 2, "owner": 3}


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
    """Members who occupy a seat: everyone not removed, pending invites
    included — an invite is a promise of a seat."""
    return (
        db.query(func.count(TeamMember.id))
        .filter(TeamMember.team_id == team_id, TeamMember.status != "removed")
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
# "A seat is for team members and for outside editors — never for a role by
# itself" (§6): everyone in a team the payer owns (invited or active — an
# invite is a promise of a seat), plus anyone holding editor/admin on the
# payer's work as a *user* (a project grant, or a WRITE share of one session).
# Viewers and commenters never appear. A team principal holding a grant rides
# on that team's own seats, so it is not counted again here.

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
        ).filter(TeamMember.team_id.in_(team_ids), TeamMember.status != "removed"):
            add(user_id, email)

    paid_projects = select(Project.id).where(
        or_(
            and_(Project.team_id.is_(None), Project.user_id == payer_id),
            Project.team_id.in_(team_ids),
        )
    )
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
    keys = seat_keys(db, payer_id)
    new_seat = new_key is not None and new_key not in keys
    if new_seat and new_key is not None:
        keys.add(new_key)
    check_capability(
        db,
        payer_id,
        capability,
        {**context, "seats": len(keys), "new_seat": new_seat},
    )


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


def list_user_teams(db: Session, user_id: UUID) -> list[tuple[Team, str, int]]:
    """(team, my role, seat count) for every team the caller is active in."""
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
    """Create a team with `owner` as its active owner. The owner is the first
    seat, so this is where the seat capability is first asked."""
    # Creating a team adds no one — the owner is already their own seat — but
    # it is still asked, so a plan without teams can refuse it up front.
    check_seat(
        db,
        owner.id,
        CAPABILITY_TEAM_SEAT,
        None,
        {"team_id": None, "acting_user_id": str(owner.id)},
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


def delete_team(db: Session, user_id: UUID, team_id: UUID) -> None:
    """Owner only. Members and invites cascade; projects and labels the team
    owned demote to personal (SET NULL); grants *to* the team are swept here
    because `principal_id` is polymorphic and has no FK."""
    team, _ = require_team(db, user_id, team_id, minimum="owner")
    db.query(ProjectGrant).filter(
        ProjectGrant.principal_type == "team", ProjectGrant.principal_id == team.id
    ).delete(synchronize_session=False)
    db.delete(team)
    db.commit()


def list_members(db: Session, team: Team) -> list[TeamMember]:
    """Everyone with a seat — active and invited — oldest first."""
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
    in place rather than duplicated (the (team, user) uniqueness).
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

    check_seat(
        db,
        _payer_id(db, team),
        CAPABILITY_TEAM_SEAT,
        seat_key(target.id if target else None, normalized),
        {
            "team_id": str(team.id),
            "team_seats": _seat_count(db, team.id) + 1,
            "acting_user_id": str(acting_user_id),
        },
    )

    if existing is not None:
        member = existing
        member.status = "invited"
        member.role = role
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
    """Owner only; the owner row itself is immutable here (transfer is P7)."""
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
    member.role = role
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
        if acting.role == "member":
            raise TeamPermissionError("Only owners or admins can remove members")
        if acting.role == "admin" and member.role == "admin":
            raise TeamPermissionError("Admins can only remove members or themselves")
    member.status = "removed"
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

    # A pending row already holds its seat (under the address it was sent
    # to), so redeeming a link on top of one adds nobody.
    check_seat(
        db,
        _payer_id(db, team),
        CAPABILITY_TEAM_SEAT,
        None if member else seat_key(user.id, None),
        {
            "team_id": str(team.id),
            "team_seats": _seat_count(db, team.id) + (0 if member else 1),
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
    member.status = "active"
    member.joined_at = _utcnow()
    # SQL-side increment. `invite.uses + 1` in Python emits `SET uses = <n>`
    # from the value we happened to read, which loses a concurrent increment
    # even when the lock above serialises the decision.
    invite.uses = TeamInvite.uses + 1
    db.commit()
    db.refresh(member)
    return member


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
    if scopes is not None:
        if not scopes or any(s not in GRANT_SCOPES for s in scopes):
            raise GrantError("scopes must be a non-empty subset of tasks/sessions")
        grant.scopes = [s for s in GRANT_SCOPES if s in scopes]
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
        db.commit()
    return claimed
