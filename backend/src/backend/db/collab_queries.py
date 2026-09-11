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

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from shared import access
from shared.database import (
    GRANT_ROLES,
    GRANT_SCOPES,
    Project,
    ProjectGrant,
    Team,
    TeamInvite,
    TeamMember,
    User,
)
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


def _seat_count(db: Session, team_id: UUID) -> int:
    """Members who occupy a seat: everyone not removed, pending invites
    included — an invite is a promise of a seat."""
    return (
        db.query(func.count(TeamMember.id))
        .filter(TeamMember.team_id == team_id, TeamMember.status != "removed")
        .scalar()
        or 0
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
    assert team.created_by_user_id is not None
    return team.created_by_user_id


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
    check_capability(db, owner.id, CAPABILITY_TEAM_SEAT, {"team_id": None, "seats": 1})
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
            invited_email=owner.email,
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

    check_capability(
        db,
        _payer_id(db, team),
        CAPABILITY_TEAM_SEAT,
        {
            "team_id": str(team.id),
            "seats": _seat_count(db, team.id) + 1,
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
    return or_(
        TeamMember.user_id == user.id,
        func.lower(TeamMember.invited_email) == user.email.lower(),
    )


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


def resolve_invite_link(db: Session, token: str) -> TeamInvite:
    """The live invite behind `token`, or `InviteNotFoundError` — the same
    error whether the token is unknown, revoked, expired or used up."""
    invite = (
        db.query(TeamInvite)
        .options(joinedload(TeamInvite.team))
        .filter(TeamInvite.token == token)
        .first()
    )
    if (
        invite is None
        or invite.revoked_at is not None
        or (invite.expires_at is not None and invite.expires_at <= _utcnow())
        or (invite.max_uses is not None and invite.uses >= invite.max_uses)
    ):
        raise InviteNotFoundError("Invite not found")
    return invite


def accept_invite_link(db: Session, user: User, token: str) -> TeamMember:
    """Redeem a join link. An already-active member is simply returned; a
    pending or removed row is activated in place."""
    invite = resolve_invite_link(db, token)
    team = invite.team
    member = (
        db.query(TeamMember)
        .filter(
            TeamMember.team_id == team.id,
            or_(
                TeamMember.user_id == user.id,
                func.lower(TeamMember.invited_email) == user.email.lower(),
            ),
        )
        .first()
    )
    if member is not None and member.status == "active":
        return member

    check_capability(
        db,
        _payer_id(db, team),
        CAPABILITY_TEAM_SEAT,
        {
            "team_id": str(team.id),
            "seats": _seat_count(db, team.id) + (0 if member else 1),
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
    invite.uses = invite.uses + 1
    db.commit()
    db.refresh(member)
    return member


# --- Project grants -----------------------------------------------------------
#
# The write endpoints ship in P5 with the share dialog; the query functions
# live here now so the capability call site (`collab.grant_write`) is declared
# alongside the other one and the authz matrix can exercise grants end to end.


def list_project_grants(
    db: Session, user_id: UUID, project: Project
) -> list[ProjectGrant]:
    access.require(access.project_role(db, user_id, project), "admin")
    return (
        db.query(ProjectGrant)
        .filter(ProjectGrant.project_id == project.id)
        .order_by(ProjectGrant.created_at.asc())
        .all()
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
    access.require(access.project_role(db, granter_user_id, project), "admin")
    if project.is_inbox:
        raise GrantError("The Inbox cannot be shared")
    if role not in GRANT_ROLES:
        raise GrantError("Unknown role")
    scopes = list(scopes) if scopes is not None else list(GRANT_SCOPES)
    if not scopes or any(s not in GRANT_SCOPES for s in scopes):
        raise GrantError("scopes must be a non-empty subset of tasks/sessions")

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
                db.query(User)
                .filter(func.lower(User.email) == invited_email.strip().lower())
                .first()
            )
            principal_id = target.id if target else None
        if principal_id is None and not invited_email:
            raise GrantError("A user id or email is required")
        if principal_id == project.user_id and project.team_id is None:
            raise GrantError("The owner already has full access")
    else:
        raise GrantError("Unknown principal type")

    if principal_type == "user" and access.role_at_least(role, "editor"):
        check_capability(
            db,
            project.user_id,
            CAPABILITY_GRANT_WRITE,
            {
                "project_id": str(project.id),
                "role": role,
                "principal_type": principal_type,
                "principal_id": str(principal_id) if principal_id else None,
                "acting_user_id": str(granter_user_id),
            },
        )

    grant = ProjectGrant(
        project_id=project.id,
        principal_type=principal_type,
        principal_id=principal_id,
        invited_email=invited_email.strip() if invited_email else None,
        role=role,
        scopes=scopes,
        granted_by_user_id=granter_user_id,
    )
    db.add(grant)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise GrantError("That principal already has a grant on this project") from exc
    return grant


def delete_project_grant(
    db: Session, user_id: UUID, project: Project, grant_id: UUID
) -> bool:
    access.require(access.project_role(db, user_id, project), "admin")
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


def attach_pending_grants(db: Session, user: User) -> int:
    """Turn email-addressed grants into user grants for a freshly created
    account. Called once, from the signup path; the resolver only ever reads
    `principal_id`, so a grant stays inert until this runs."""
    rows = (
        db.query(ProjectGrant)
        .filter(
            ProjectGrant.principal_type == "user",
            ProjectGrant.principal_id.is_(None),
            func.lower(ProjectGrant.invited_email) == user.email.lower(),
        )
        .all()
    )
    for grant in rows:
        grant.principal_id = user.id
    if rows:
        db.commit()
    return len(rows)
