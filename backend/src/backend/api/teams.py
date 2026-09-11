"""Teams API (collaboration §3.2).

A team is a principal — a reusable bag of people that can hold a project grant
and, later, own projects — not a tenant. This router covers the team itself,
its members (email invites, accept/decline, roles, removal) and shareable
join links. Seat gating is not here: the query layer asks
`shared.hooks.check_capability`, and the app-level handler turns a denial
into 402.

Deliberately absent (D-D): no slug availability check and no public route
that resolves a slug. The invite-link preview resolves a 256-bit *token*, is
authenticated, and fails identically for unknown / revoked / expired /
exhausted tokens.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from shared.database import Team, TeamInvite, TeamMember, User
from shared.database.session import get_db

from ..auth.dependencies import get_current_user
from ..db import collab_queries
from ..db.collab_queries import (
    InviteNotFoundError,
    TeamConflictError,
    TeamNotFoundError,
    TeamPermissionError,
)
from ..models import (
    TeamCreateRequest,
    TeamDetailResponse,
    TeamInvitationResponse,
    TeamInviteCreateRequest,
    TeamInvitePreviewResponse,
    TeamInviteResponse,
    TeamMemberInviteRequest,
    TeamMemberResponse,
    TeamMemberRoleUpdateRequest,
    TeamSummary,
    TeamUpdateRequest,
)

router = APIRouter(prefix="/teams", tags=["teams"])
invite_router = APIRouter(prefix="/team-invites", tags=["teams"])


# --- serializers --------------------------------------------------------------


def _summary(team: Team, role: str, member_count: int) -> TeamSummary:
    return TeamSummary(
        id=team.id,
        name=team.name,
        slug=team.slug,
        avatar_image_uri=team.avatar_image_uri,
        role=role,  # type: ignore[arg-type]
        member_count=member_count,
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


def _member(member: TeamMember, *, show_email: bool) -> TeamMemberResponse:
    user = member.user
    return TeamMemberResponse(
        id=member.id,
        user_id=member.user_id,
        # Email is identity only for a pending invite with no account yet;
        # otherwise it is shown to owners/admins alone (§10.4).
        email=(
            (user.email if user else member.invited_email)
            if show_email or (user is None and member.status == "invited")
            else None
        ),
        display_name=user.display_name if user else None,
        avatar_image_uri=user.avatar_image_uri if user else None,
        role=member.role,  # type: ignore[arg-type]
        status=member.status,  # type: ignore[arg-type]
        joined_at=member.joined_at,
        created_at=member.created_at,
    )


def _detail(db: Session, team: Team, membership: TeamMember) -> TeamDetailResponse:
    members = collab_queries.list_members(db, team)
    show_email = membership.role in ("owner", "admin")
    return TeamDetailResponse(
        **_summary(team, membership.role, len(members)).model_dump(),
        members=[_member(m, show_email=show_email) for m in members],
    )


def _invite(invite: TeamInvite) -> TeamInviteResponse:
    return TeamInviteResponse(
        id=invite.id,
        token=invite.token,
        role=invite.role,  # type: ignore[arg-type]
        expires_at=invite.expires_at,
        max_uses=invite.max_uses,
        uses=invite.uses,
        created_at=invite.created_at,
    )


def _team_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TeamNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, TeamPermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, TeamConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, InviteNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    raise exc


# --- teams --------------------------------------------------------------------


@router.get("", response_model=list[TeamSummary])
def list_teams(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TeamSummary]:
    return [
        _summary(team, role, count)
        for team, role, count in collab_queries.list_user_teams(db, current_user.id)
    ]


@router.post("", response_model=TeamDetailResponse, status_code=status.HTTP_201_CREATED)
def create_team_endpoint(
    request: TeamCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamDetailResponse:
    try:
        team = collab_queries.create_team(db, current_user, request.name)
        _, membership = collab_queries.require_team(db, current_user.id, team.id)
    except (TeamConflictError, TeamNotFoundError) as exc:
        raise _team_error(exc) from exc
    return _detail(db, team, membership)


@router.get("/invitations", response_model=list[TeamInvitationResponse])
def list_invitations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TeamInvitationResponse]:
    """Email invites waiting on the caller."""
    out: list[TeamInvitationResponse] = []
    for member in collab_queries.list_pending_invitations(db, current_user):
        inviter = (
            db.get(User, member.invited_by_user_id)
            if member.invited_by_user_id
            else None
        )
        out.append(
            TeamInvitationResponse(
                team_id=member.team.id,
                name=member.team.name,
                slug=member.team.slug,
                avatar_image_uri=member.team.avatar_image_uri,
                role=member.role,  # type: ignore[arg-type]
                invited_by_display_name=inviter.display_name if inviter else None,
                created_at=member.created_at,
            )
        )
    return out


@router.get("/{team_id}", response_model=TeamDetailResponse)
def get_team_endpoint(
    team_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamDetailResponse:
    try:
        team, membership = collab_queries.require_team(db, current_user.id, team_id)
    except TeamNotFoundError as exc:
        raise _team_error(exc) from exc
    return _detail(db, team, membership)


@router.patch("/{team_id}", response_model=TeamSummary)
def update_team_endpoint(
    team_id: UUID,
    request: TeamUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamSummary:
    try:
        team = collab_queries.update_team(
            db, current_user.id, team_id, name=request.name
        )
        _, membership = collab_queries.require_team(db, current_user.id, team_id)
    except (TeamNotFoundError, TeamPermissionError) as exc:
        raise _team_error(exc) from exc
    return _summary(team, membership.role, len(collab_queries.list_members(db, team)))


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team_endpoint(
    team_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        collab_queries.delete_team(db, current_user.id, team_id)
    except (TeamNotFoundError, TeamPermissionError) as exc:
        raise _team_error(exc) from exc


# --- members ------------------------------------------------------------------


@router.post(
    "/{team_id}/members",
    response_model=TeamMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def invite_member_endpoint(
    team_id: UUID,
    request: TeamMemberInviteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamMemberResponse:
    try:
        member = collab_queries.invite_member(
            db, current_user.id, team_id, email=request.email, role=request.role
        )
    except (TeamNotFoundError, TeamPermissionError, TeamConflictError) as exc:
        raise _team_error(exc) from exc
    return _member(member, show_email=True)


@router.post("/{team_id}/members/accept", response_model=TeamSummary)
def accept_invitation_endpoint(
    team_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamSummary:
    try:
        collab_queries.accept_invitation(db, current_user, team_id)
        team, membership = collab_queries.require_team(db, current_user.id, team_id)
    except TeamNotFoundError as exc:
        raise _team_error(exc) from exc
    return _summary(team, membership.role, len(collab_queries.list_members(db, team)))


@router.post("/{team_id}/members/decline", status_code=status.HTTP_204_NO_CONTENT)
def decline_invitation_endpoint(
    team_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        collab_queries.decline_invitation(db, current_user, team_id)
    except TeamNotFoundError as exc:
        raise _team_error(exc) from exc


@router.patch("/{team_id}/members/{member_id}", response_model=TeamMemberResponse)
def update_member_role_endpoint(
    team_id: UUID,
    member_id: UUID,
    request: TeamMemberRoleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamMemberResponse:
    try:
        member = collab_queries.update_member_role(
            db, current_user.id, team_id, member_id, role=request.role
        )
    except (TeamNotFoundError, TeamPermissionError, TeamConflictError) as exc:
        raise _team_error(exc) from exc
    return _member(member, show_email=True)


@router.delete("/{team_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member_endpoint(
    team_id: UUID,
    member_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        collab_queries.remove_member(db, current_user.id, team_id, member_id)
    except (TeamNotFoundError, TeamPermissionError, TeamConflictError) as exc:
        raise _team_error(exc) from exc


# --- invite links -------------------------------------------------------------


@router.get("/{team_id}/invites", response_model=list[TeamInviteResponse])
def list_invites_endpoint(
    team_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TeamInviteResponse]:
    try:
        invites = collab_queries.list_invite_links(db, current_user.id, team_id)
    except (TeamNotFoundError, TeamPermissionError) as exc:
        raise _team_error(exc) from exc
    return [_invite(i) for i in invites]


@router.post(
    "/{team_id}/invites",
    response_model=TeamInviteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_invite_endpoint(
    team_id: UUID,
    request: TeamInviteCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamInviteResponse:
    try:
        invite = collab_queries.create_invite_link(
            db,
            current_user.id,
            team_id,
            role=request.role,
            expires_in_days=request.expires_in_days,
            max_uses=request.max_uses,
        )
    except (TeamNotFoundError, TeamPermissionError, TeamConflictError) as exc:
        raise _team_error(exc) from exc
    return _invite(invite)


@router.delete("/{team_id}/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite_endpoint(
    team_id: UUID,
    invite_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        collab_queries.revoke_invite_link(db, current_user.id, team_id, invite_id)
    except (TeamNotFoundError, TeamPermissionError, InviteNotFoundError) as exc:
        raise _team_error(exc) from exc


@invite_router.get("/{token}", response_model=TeamInvitePreviewResponse)
def preview_invite_endpoint(
    token: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamInvitePreviewResponse:
    """What the join page shows before the visitor commits. Authenticated —
    a token is a capability to *join*, not a public page."""
    del current_user
    try:
        invite = collab_queries.resolve_invite_link(db, token)
    except InviteNotFoundError as exc:
        raise _team_error(exc) from exc
    return TeamInvitePreviewResponse(
        team_id=invite.team.id,
        name=invite.team.name,
        avatar_image_uri=invite.team.avatar_image_uri,
        role=invite.role,  # type: ignore[arg-type]
        member_count=len(collab_queries.list_members(db, invite.team)),
    )


@invite_router.post("/{token}/accept", response_model=TeamSummary)
def accept_invite_endpoint(
    token: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamSummary:
    try:
        member = collab_queries.accept_invite_link(db, current_user, token)
        team, membership = collab_queries.require_team(
            db, current_user.id, member.team_id
        )
    except (InviteNotFoundError, TeamNotFoundError) as exc:
        raise _team_error(exc) from exc
    return _summary(team, membership.role, len(collab_queries.list_members(db, team)))
