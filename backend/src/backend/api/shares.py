"""Share links (collaboration §3.4, P4): owner-side management and the public
token-authorized viewer API.

Two routers on purpose:

* ``router`` — ``/shares``: signed-in, ``admin`` on the target (the same floor
  as the per-email session shares). Create / list / revoke.
* ``public_router`` — ``/public/shares/{token}/…``: **no auth dependency**. The
  token is the capability. ``get_optional_current_user`` is consulted only so
  an ``authenticated``-audience link can tell a signed-in visitor from an
  anonymous one, so a comment is attributed to a real account, and so the
  owner can be told apart from a visitor when the link hides them.

Public-surface rules (§10.5), all enforced here rather than left to callers:
uniform ``404 {"detail": "Share not found"}`` for unknown / revoked / expired
/ wrong-audience tokens and for any id the link does not cover;
``Cache-Control: private, no-store`` and ``X-Robots-Tag: noindex`` on every
response; a per-client token bucket (``shared.ratelimit``); view accounting
off the request path, once per client per ~10 minutes.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy.orm import Session

from shared import access, storage
from shared.database.actor import Actor, set_session_actor
from shared.database.models import User
from shared.database.session import get_db
from shared.ratelimit import client_ip, public_share_rate_limit

from ..auth.dependencies import get_current_user, get_optional_current_user
from ..db import share_queries, task_timeline_queries
from ..db.share_queries import ShareTargetNotFoundError
from ..models import (
    CreateShareLinkRequest,
    CreateTaskCommentRequest,
    PublicBoardResponse,
    PublicMessagesPage,
    PublicSessionsPage,
    PublicSessionSummary,
    PublicShareResponse,
    ShareLinkResponse,
    TaskTimelineResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["shares"])


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/shares", response_model=ShareLinkResponse, status_code=status.HTTP_201_CREATED
)
def create_share_link_endpoint(
    request: CreateShareLinkRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShareLinkResponse:
    try:
        return share_queries.create_share_link(
            db,
            current_user,
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
        raise _not_found(exc) from exc


@router.get("/shares", response_model=list[ShareLinkResponse])
def list_share_links_endpoint(
    agent_instance_id: UUID | None = None,
    project_id: UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ShareLinkResponse]:
    """Live links on one target — pass exactly one of the two ids."""
    if (agent_instance_id is None) == (project_id is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pass exactly one of agent_instance_id or project_id",
        )
    try:
        return share_queries.list_share_links(
            db,
            current_user.id,
            agent_instance_id=agent_instance_id,
            project_id=project_id,
        )
    except ShareTargetNotFoundError as exc:
        raise _not_found(exc) from exc


@router.delete("/shares/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share_link_endpoint(
    link_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        share_queries.revoke_share_link(db, current_user.id, link_id)
    except ShareTargetNotFoundError as exc:
        raise _not_found(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

_SHARE_NOT_FOUND = "Share not found"

public_router = APIRouter(
    prefix="/public/shares",
    tags=["public-shares"],
    dependencies=[Depends(public_share_rate_limit)],
)


# A token-in-URL page must never land in a shared cache, and a page whose
# existence is the secret must never be indexed. Set on the success path
# through the injected `Response` and carried on the 404 explicitly, since an
# HTTPException builds its own response.
_PUBLIC_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Robots-Tag": "noindex, nofollow",
}


def _share_not_found() -> HTTPException:
    """The one 404 every public failure collapses to (§10.5)."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_SHARE_NOT_FOUND,
        headers=dict(_PUBLIC_HEADERS),
    )


def _public_headers(response: Response) -> None:
    for name, value in _PUBLIC_HEADERS.items():
        response.headers[name] = value


async def resolve_grant(
    token: str,
    response: Response,
    viewer: User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> access.ShareGrant:
    """Token → grant, or the uniform 404. Every public route hangs off this."""
    _public_headers(response)
    grant = access.resolve_share(
        db, token, user_id=viewer.id if viewer is not None else None
    )
    if grant is None:
        raise _share_not_found()
    return grant


def _count_view(
    background_tasks: BackgroundTasks, request: Request, grant: access.ShareGrant
) -> None:
    if share_queries.should_count_view(grant.id, client_ip(request)):
        background_tasks.add_task(share_queries.record_share_view, grant.id)


@public_router.get("/{token}", response_model=PublicShareResponse)
def get_public_share(
    request: Request,
    background_tasks: BackgroundTasks,
    grant: access.ShareGrant = Depends(resolve_grant),
    viewer: User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> PublicShareResponse:
    """Share meta + target summary — the viewer page's first fetch, and what
    the server component reads for OG tags."""
    try:
        meta = share_queries.public_share(db, grant, viewer)
    except ShareTargetNotFoundError:
        raise _share_not_found() from None
    _count_view(background_tasks, request, grant)
    return meta


@public_router.get("/{token}/sessions", response_model=PublicSessionsPage)
def list_public_sessions(
    limit: int = Query(default=50, ge=1, le=share_queries.MAX_PUBLIC_SESSION_PAGE),
    offset: int = Query(default=0, ge=0),
    grant: access.ShareGrant = Depends(resolve_grant),
    db: Session = Depends(get_db),
) -> PublicSessionsPage:
    """The sessions this link covers, newest first. A session link answers its
    one session; a project link that does not carry `sessions` answers an
    empty page."""
    return share_queries.public_sessions(db, grant, limit=limit, offset=offset)


@public_router.get(
    "/{token}/sessions/{instance_id}", response_model=PublicSessionSummary
)
def get_public_session(
    instance_id: UUID,
    grant: access.ShareGrant = Depends(resolve_grant),
    db: Session = Depends(get_db),
) -> PublicSessionSummary:
    """One covered session's summary (title, status, config) — polled so the
    header's status badge tracks a live session."""
    instance = share_queries.covered_instance(db, grant, instance_id)
    if instance is None:
        raise _share_not_found()
    return share_queries.public_session_summary(db, grant, instance)


@public_router.get(
    "/{token}/sessions/{instance_id}/messages", response_model=PublicMessagesPage
)
def get_public_messages(
    instance_id: UUID,
    after: UUID | None = None,
    before: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=share_queries.MAX_PUBLIC_MESSAGE_PAGE),
    grant: access.ShareGrant = Depends(resolve_grant),
    db: Session = Depends(get_db),
) -> PublicMessagesPage:
    """Transcript page. `after=` is the poll watermark (§9); `before=` pages
    older history; neither returns the newest `limit` rows."""
    if after is not None and before is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pass at most one of after / before",
        )
    page = share_queries.public_messages(
        db, grant, instance_id, after=after, before=before, limit=limit
    )
    if page is None:
        raise _share_not_found()
    return page


# Raster types render inline; everything else downloads (mirrors
# api/attachments.py — a scriptable image type must not execute top-level).
_INLINE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


@public_router.get("/{token}/attachments/{attachment_id}")
def get_public_attachment(
    attachment_id: UUID,
    grant: access.ShareGrant = Depends(resolve_grant),
    db: Session = Depends(get_db),
) -> Response:
    """Attachment bytes, iff the attachment's session is covered by the link."""
    attachment = share_queries.public_attachment(db, grant, attachment_id)
    if attachment is None:
        raise _share_not_found()
    try:
        data = storage.download_attachment(attachment.s3_key)
    except Exception as exc:
        logger.exception("public attachment download from S3 failed")
        raise HTTPException(status_code=502, detail="Failed to fetch file") from exc
    headers = {**_PUBLIC_HEADERS, "X-Content-Type-Options": "nosniff"}
    if attachment.mime_type not in _INLINE_IMAGE_TYPES:
        headers["Content-Disposition"] = "attachment"
    return Response(content=data, media_type=attachment.mime_type, headers=headers)


@public_router.get("/{token}/users/{user_id}/avatar")
def get_public_user_avatar(
    user_id: UUID,
    grant: access.ShareGrant = Depends(resolve_grant),
    viewer: User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """A user's avatar bytes, iff the page under this link shows that user.

    The dashboard's `/users/{id}/avatar` needs a signed-in caller, which a
    public page's anonymous visitor is not — so without this the owner card
    and every assignee/author slot fell back to initials. Same shape as the
    attachment route: the token, not a cookie, authorizes it, and the answer
    for anyone the link does not show is the uniform 404.
    """
    user = share_queries.public_avatar_user(db, grant, user_id, viewer)
    if user is None:
        raise _share_not_found()
    try:
        data, content_type = storage.download_object(
            storage.user_avatar_key(str(user_id))
        )
    except Exception as exc:
        logger.exception("public avatar download from S3 failed")
        raise HTTPException(status_code=502, detail="Failed to fetch image") from exc
    if content_type not in _INLINE_IMAGE_TYPES:
        content_type = "application/octet-stream"
    return Response(
        content=data,
        media_type=content_type,
        headers={**_PUBLIC_HEADERS, "X-Content-Type-Options": "nosniff"},
    )


@public_router.get("/{token}/board", response_model=PublicBoardResponse)
def get_public_board(
    request: Request,
    background_tasks: BackgroundTasks,
    grant: access.ShareGrant = Depends(resolve_grant),
    db: Session = Depends(get_db),
) -> PublicBoardResponse:
    """A project link carrying `tasks`: the project, its visible tasks, its
    labels. Any other link 404s, like an unknown token."""
    try:
        board = share_queries.public_board(db, grant)
    except ShareTargetNotFoundError:
        raise _share_not_found() from None
    _count_view(background_tasks, request, grant)
    return board


def _covered_task(db: Session, grant: access.ShareGrant, task_id: UUID):
    task = share_queries.covered_task(db, grant, task_id)
    if task is None:
        raise _share_not_found()
    return task


@public_router.get(
    "/{token}/tasks/{task_id}/timeline", response_model=TaskTimelineResponse
)
def get_public_task_timeline(
    task_id: UUID,
    grant: access.ShareGrant = Depends(resolve_grant),
    viewer: User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> TaskTimelineResponse:
    """A covered task's comments + activity. Reactions report `reacted` for the
    signed-in visitor; an anonymous one simply never has any."""
    task = _covered_task(db, grant, task_id)
    viewer_id = viewer.id if viewer is not None else UUID(int=0)
    return share_queries.public_timeline(
        task_timeline_queries.build_timeline(db, task, viewer_id), grant
    )


@public_router.post(
    "/{token}/tasks/{task_id}/comments",
    response_model=TaskTimelineResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_public_task_comment(
    task_id: UUID,
    request: CreateTaskCommentRequest,
    grant: access.ShareGrant = Depends(resolve_grant),
    viewer: User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> TaskTimelineResponse:
    """The ONLY write a link can carry (§3.4): a signed-in visitor, on a board
    link with `allow_comments`, posting a comment attributed to their own
    account. No grant row is created; revoking the link ends it instantly.

    Comments do not depend on the audience: a public link can allow them, and
    then an anonymous reader gets a 401 here — "this link could take your
    comment if you signed in", which is what the composer's sign-in prompt
    needs to know — while a 403 means the link simply does not allow comments.
    """
    if viewer is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to comment"
        )
    if not grant.allow_comments:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This link does not allow comments",
        )
    task = _covered_task(db, grant, task_id)
    # `get_optional_current_user` does not stamp the actor the way the hard
    # dependency does; the activity listener needs it to attribute the row.
    set_session_actor(db, Actor(type="user", id=viewer.id))
    try:
        task_timeline_queries.create_comment(
            db,
            task,
            viewer.id,
            request.body,
            parent_comment_id=request.parent_comment_id,
        )
    except task_timeline_queries.CommentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return share_queries.public_timeline(
        task_timeline_queries.build_timeline(db, task, viewer.id), grant
    )
