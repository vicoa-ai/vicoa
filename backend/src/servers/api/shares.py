"""Share links for the agent-facing server (``vicoa session share``).

An agent that just opened a pull request wants to attach the session that
produced it. The dashboard's ``/shares`` (``backend/api/shares.py``) takes an
IdP token; this is the same create / list / revoke for the API key the CLI
holds, reusing ``backend.db.share_queries`` verbatim so the two surfaces can
never drift on what a link is.

Owner-only, like every router on this server (AGENTS.md "Extension points").
The dashboard lets any ``admin`` on a target mint a link; here the caller
must *own* the session or project outright, checked before the query layer's
own admin floor. The query layer's check is then a no-op for an owner, but it
stays in the path so a link can never be minted on a target the resolver
would refuse. Anything the caller does not own is a uniform 404 — the
404-vs-403 rule from ``shared.access``.

The public viewer side (``/public/shares/{token}/…``) lives on the dashboard
app only; it is a browser surface, not an agent one.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from shared.database import AgentInstance, Project, ShareLink, User
from shared.database.enums import AgentStatus
from shared.database.session import get_db

# Reused human-facing query layer + DTOs. See module docstring for why this
# servers→backend import is deliberate rather than a duplicate implementation.
from backend.db import share_queries
from backend.db.share_queries import ShareTargetNotFoundError
from backend.models import CreateShareLinkRequest, ShareLinkResponse

from .auth import get_current_user_id

share_router = APIRouter(tags=["shares"])


def _user_uuid(user_id: str) -> UUID:
    """Coerce the token's ``sub`` (a string) to the UUID the queries expect."""
    try:
        return UUID(user_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject is not a valid user id",
        ) from exc


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _require_owned_target(
    db: Session,
    user_id: UUID,
    *,
    agent_instance_id: UUID | None,
    project_id: UUID | None,
) -> None:
    """404 unless the caller owns the target outright.

    A session: its ``user_id`` is the caller and it is not DELETED (a deleted
    session is not shareable even by its owner). A project: personal (no
    team) and the caller's — team projects are a sharing-lens concept.
    """
    if agent_instance_id is not None:
        instance = db.get(AgentInstance, agent_instance_id)
        if (
            instance is None
            or instance.user_id != user_id
            or instance.status == AgentStatus.DELETED
        ):
            raise _not_found("Agent instance not found")
        return
    project = db.get(Project, project_id) if project_id is not None else None
    if project is None or project.user_id != user_id or project.team_id is not None:
        raise _not_found("Project not found")


def _require_user(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    return user


@share_router.post(
    "/shares", response_model=ShareLinkResponse, status_code=status.HTTP_201_CREATED
)
def create_share_link_endpoint(
    request: CreateShareLinkRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> ShareLinkResponse:
    resolved = _user_uuid(user_id)
    _require_owned_target(
        db,
        resolved,
        agent_instance_id=request.agent_instance_id,
        project_id=request.project_id,
    )
    try:
        return share_queries.create_share_link(
            db,
            _require_user(db, resolved),
            kind=request.kind,
            agent_instance_id=request.agent_instance_id,
            project_id=request.project_id,
            scopes=request.scopes,
            audience=request.audience,
            filters=request.filters,
            allow_comments=request.allow_comments,
            show_owner=request.show_owner,
            show_branch=request.show_branch,
            expires_in_days=request.expires_in_days,
        )
    except ShareTargetNotFoundError as exc:
        raise _not_found(str(exc)) from exc


@share_router.get("/shares", response_model=list[ShareLinkResponse])
def list_share_links_endpoint(
    user_id: Annotated[str, Depends(get_current_user_id)],
    agent_instance_id: UUID | None = None,
    project_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> list[ShareLinkResponse]:
    """Live links on one target the caller owns — pass exactly one id."""
    if (agent_instance_id is None) == (project_id is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pass exactly one of agent_instance_id or project_id",
        )
    resolved = _user_uuid(user_id)
    _require_owned_target(
        db, resolved, agent_instance_id=agent_instance_id, project_id=project_id
    )
    try:
        return share_queries.list_share_links(
            db, resolved, agent_instance_id=agent_instance_id, project_id=project_id
        )
    except ShareTargetNotFoundError as exc:
        raise _not_found(str(exc)) from exc


@share_router.delete("/shares/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share_link_endpoint(
    link_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> Response:
    resolved = _user_uuid(user_id)
    link = db.get(ShareLink, link_id)
    if link is None:
        raise _not_found("Share link not found")
    try:
        _require_owned_target(
            db,
            resolved,
            agent_instance_id=link.agent_instance_id,
            project_id=link.project_id,
        )
    except HTTPException:
        # The target is not the caller's — so, as far as they can tell, there
        # is no such link either.
        raise _not_found("Share link not found") from None
    try:
        share_queries.revoke_share_link(db, resolved, link_id)
    except ShareTargetNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
