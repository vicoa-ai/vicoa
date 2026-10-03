"""Project People — who can reach one project (collaboration §3.3, §8.4).

The REST surface of `project_grants`: list, grant, change role or scopes,
revoke, and leave. Mounted on the human dashboard only; the agent-facing app
never learns grants exist (§4's owner-only lens is an invariant).

Every route first resolves the project through
`task_queries.get_accessible_project(sharing=True)`, so an invisible project
404s before any grant logic runs. The query layer's `_require_grant_admin`
then raises `AccessDenied` for a visible caller who is not admin on both
scopes, which the app handler turns into 403. An editor/admin grant to a user
asks the `collab.grant_write` capability; a denial is a 402.
"""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.database import Project, ProjectGrant, Team, TeamMember, User
from shared.database.session import get_db

from ..auth.dependencies import get_current_user
from ..db import collab_queries, task_queries
from ..db.collab_queries import GrantConflictError, GrantError, GrantNotFoundError
from ..email_service import email_is_configured, send_project_invite_email, web_url
from ..models import (
    ProjectGrantCreateRequest,
    ProjectGrantCreateResponse,
    ProjectGrantUpdateRequest,
    ProjectPersonResponse,
    PrincipalResponse,
)

router = APIRouter(tags=["sharing"])

_BOTH_SCOPES = ["tasks", "sessions"]


def _visible_project(db: Session, user_id: UUID, project_id: UUID) -> Project:
    project = task_queries.get_accessible_project(db, user_id, project_id, sharing=True)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return project


def _grant_error(exc: GrantError) -> HTTPException:
    if isinstance(exc, GrantNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, GrantConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# --- serialization ------------------------------------------------------------


def _user_principal(user: User) -> PrincipalResponse:
    return PrincipalResponse(
        type="user",
        id=user.id,
        # display_name only; the address rides beside the principal (§10.4).
        name=user.display_name,
        avatar_image_uri=user.avatar_image_uri,
        emoji=user.avatar_emoji,
        updated_at=user.updated_at,
    )


def _team_principal(team: Team) -> PrincipalResponse:
    return PrincipalResponse(
        type="team",
        id=team.id,
        name=team.name,
        avatar_image_uri=team.avatar_image_uri,
        updated_at=team.updated_at,
    )


def _people(
    db: Session, caller_id: UUID, project: Project, grants: list[ProjectGrant]
) -> list[ProjectPersonResponse]:
    """The owner row, then every grant — three queries for the whole list."""
    user_ids = {
        g.principal_id
        for g in grants
        if g.principal_type == "user" and g.principal_id is not None
    }
    team_ids = {
        g.principal_id
        for g in grants
        if g.principal_type == "team" and g.principal_id is not None
    }
    if project.team_id is not None:
        team_ids.add(project.team_id)
    else:
        user_ids.add(project.user_id)
    users = (
        {u.id: u for u in db.query(User).filter(User.id.in_(user_ids))}
        if user_ids
        else {}
    )
    teams = (
        {t.id: t for t in db.query(Team).filter(Team.id.in_(team_ids))}
        if team_ids
        else {}
    )
    counts: dict[UUID, int] = (
        {
            team_id: int(n)
            for team_id, n in db.query(TeamMember.team_id, func.count(TeamMember.id))
            .filter(TeamMember.team_id.in_(team_ids), TeamMember.status != "removed")
            .group_by(TeamMember.team_id)
        }
        if team_ids
        else {}
    )

    out: list[ProjectPersonResponse] = []
    owner_team = teams.get(project.team_id) if project.team_id else None
    owner_user = users.get(project.user_id) if project.team_id is None else None
    if owner_team is not None:
        out.append(
            ProjectPersonResponse(
                principal=_team_principal(owner_team),
                role="owner",
                scopes=_BOTH_SCOPES,  # type: ignore[arg-type]
                member_count=counts.get(owner_team.id, 0),
                is_owner=True,
            )
        )
    elif owner_user is not None:
        out.append(
            ProjectPersonResponse(
                principal=_user_principal(owner_user),
                email=owner_user.email or None,
                role="owner",
                scopes=_BOTH_SCOPES,  # type: ignore[arg-type]
                is_owner=True,
                is_self=owner_user.id == caller_id,
            )
        )

    for grant in grants:
        out.append(_person(grant, users, teams, counts, caller_id))
    return out


def _person(
    grant: ProjectGrant,
    users: dict[UUID, User],
    teams: dict[UUID, Team],
    counts: dict[UUID, int],
    caller_id: UUID,
) -> ProjectPersonResponse:
    scopes = [s for s in _BOTH_SCOPES if s in (grant.scopes or [])]
    if grant.principal_type == "team":
        team = teams.get(grant.principal_id) if grant.principal_id else None
        principal = (
            _team_principal(team)
            if team is not None
            else PrincipalResponse(type="team", name="Deleted team")
        )
        return ProjectPersonResponse(
            id=grant.id,
            principal=principal,
            role=grant.role,  # type: ignore[arg-type]
            scopes=scopes,  # type: ignore[arg-type]
            member_count=counts.get(grant.principal_id, 0)
            if grant.principal_id
            else None,
            created_at=grant.created_at,
        )
    user = users.get(grant.principal_id) if grant.principal_id else None
    return ProjectPersonResponse(
        id=grant.id,
        principal=_user_principal(user)
        if user is not None
        else PrincipalResponse(type="user"),
        email=(user.email if user is not None else None) or grant.invited_email,
        pending=grant.principal_id is None,
        role=grant.role,  # type: ignore[arg-type]
        scopes=scopes,  # type: ignore[arg-type]
        lapsed_role=grant.lapsed_role,  # type: ignore[arg-type]
        is_self=grant.principal_id == caller_id,
        created_at=grant.created_at,
    )


def _one(db: Session, caller_id: UUID, project: Project, grant: ProjectGrant):
    rows = _people(db, caller_id, project, [grant])
    return rows[-1]


# --- routes -------------------------------------------------------------------


@router.get("/projects/{project_id}/grants", response_model=list[ProjectPersonResponse])
def list_project_people(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProjectPersonResponse]:
    """The owner and every grant. Admin on both scopes — the same floor as
    granting, so the addresses on this list only reach people who could add
    them in the first place (§10.4)."""
    project = _visible_project(db, current_user.id, project_id)
    grants = collab_queries.list_project_grants(db, current_user.id, project)
    return _people(db, current_user.id, project, grants)


@router.post(
    "/projects/{project_id}/grants",
    response_model=ProjectGrantCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project_grant_endpoint(
    project_id: UUID,
    request: ProjectGrantCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectGrantCreateResponse:
    project = _visible_project(db, current_user.id, project_id)
    try:
        grant = collab_queries.create_project_grant(
            db,
            current_user.id,
            project,
            principal_type="team" if request.team_id else "user",
            principal_id=request.team_id,
            invited_email=request.email,
            role=request.role,
            scopes=list(request.scopes),
        )
    except GrantError as exc:
        raise _grant_error(exc) from exc

    person = _one(db, current_user.id, project, grant)
    email_sent = False
    if grant.principal_type == "user" and person.email and email_is_configured():
        # Off the request path: the grant is real whether or not the mail
        # provider answers, and the dialog should not wait on it.
        background_tasks.add_task(
            send_project_invite_email,
            person.email,
            current_user.display_name or "",
            project.name,
            grant.role,
            web_url("/dashboard"),
        )
        email_sent = True
    return ProjectGrantCreateResponse(**person.model_dump(), email_sent=email_sent)


@router.patch(
    "/projects/{project_id}/grants/{grant_id}", response_model=ProjectPersonResponse
)
def update_project_grant_endpoint(
    project_id: UUID,
    grant_id: UUID,
    request: ProjectGrantUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectPersonResponse:
    project = _visible_project(db, current_user.id, project_id)
    try:
        grant = collab_queries.update_project_grant(
            db,
            current_user.id,
            project,
            grant_id,
            role=request.role,
            scopes=list(request.scopes) if request.scopes is not None else None,
        )
    except GrantError as exc:
        raise _grant_error(exc) from exc
    return _one(db, current_user.id, project, grant)


@router.delete(
    "/projects/{project_id}/grants/{grant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_project_grant_endpoint(
    project_id: UUID,
    grant_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    project = _visible_project(db, current_user.id, project_id)
    if not collab_queries.delete_project_grant(db, current_user.id, project, grant_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Grant not found"
        )


@router.post("/projects/{project_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_project_endpoint(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Drop the caller's own grant on a project someone shared with them.
    409 when the access is not theirs to drop — they own the project, or it
    comes through a team."""
    project = _visible_project(db, current_user.id, project_id)
    try:
        collab_queries.leave_project(db, current_user, project)
    except GrantError as exc:
        raise _grant_error(exc) from exc
