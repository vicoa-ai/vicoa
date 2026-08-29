"""Read-only agent-instance API for the agent-facing server.

The human dashboard (``backend`` process, Supabase JWT) owns the rich
instance/message reads. This module exposes the same reads to CLI agents, which
authenticate against *this* server with their RS256 API-key JWT
(``get_current_user_id``). The business logic is reused verbatim from
``backend.db.queries`` — the same servers→backend reuse precedent as
``tasks.py`` (and ``routers.py`` importing ``backend.db.queries``) — so the
agent-facing and human-facing instance surfaces can never drift.

Scope is the caller's own sessions (``scope="me"``): an agent acting for a user
lists and reads that user's sessions, exactly as ``vicoa session ls`` /
``vicoa session get`` need. Sharing/teams stay a web concern.

Read-only by design. Instance mutation (rename, delete, status) stays on the
human API and the existing ``routers.py`` write paths; these endpoints only
add the *list* and *messages* reads the CLI was missing (the single-instance
GET already lives in ``routers.py``). Kept in its own file to avoid bloating
``routers.py``.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from shared.database.session import get_db

# Reused human-facing query layer + DTOs. See module docstring for why this
# servers→backend import is deliberate rather than a duplicate implementation.
from backend.db import get_all_agent_instances, get_instance_messages
from backend.models import MessageResponse, PaginatedAgentInstanceResponse

from .auth import get_current_user_id

instance_router = APIRouter(tags=["instances"])


def _user_uuid(user_id: str) -> UUID:
    """Coerce the token's ``sub`` (a string) to the UUID the queries expect."""
    try:
        return UUID(user_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject is not a valid user id",
        ) from exc


@instance_router.get("/agent-instances", response_model=PaginatedAgentInstanceResponse)
def list_agent_instances_endpoint(
    user_id: Annotated[str, Depends(get_current_user_id)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    active_only: bool = Query(default=False),
    rate_limited_only: bool = Query(default=False),
    caller_instance_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PaginatedAgentInstanceResponse:
    """List the caller's agent sessions, newest first.

    Unlike ``vicoa ls`` (agent processes running on the caller's machine) this
    reads the backend, so it spans every machine, cloud/mobile-started sessions,
    and finished ones. ``active_only`` drops closed sessions;
    ``rate_limited_only`` keeps just the sessions a time-window rate limit is
    currently blocking (what the auto-continue automation queries).
    ``caller_instance_id`` (the CLI fills it from ``VICOA_AGENT_INSTANCE_ID``)
    lets the rate-limit sweep exclude the *calling automation's own* sessions so
    it can't flag-and-continue its own runs; taken as a free-form string so a
    non-UUID session id can never 422 the list.
    """
    instances, total = get_all_agent_instances(
        db,
        _user_uuid(user_id),
        limit=limit,
        offset=offset,
        scope="me",
        active_only=active_only,
        rate_limited_only=rate_limited_only,
        caller_instance_id=caller_instance_id,
    )
    return PaginatedAgentInstanceResponse(
        items=instances,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(instances) < total,
    )


@instance_router.get(
    "/agent-instances/{instance_id}/messages",
    response_model=list[MessageResponse],
)
def list_instance_messages_endpoint(
    instance_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    limit: int = Query(default=50, ge=1, le=500),
    before_message_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> list[MessageResponse]:
    """Return one page of a session's transcript, oldest-first.

    Cursor-paginated exactly like the human API: the newest ``limit`` messages
    by default; pass ``before_message_id`` (the oldest id you already hold) to
    walk further back. 404 when the session is missing or not the caller's.
    """
    messages = get_instance_messages(
        db,
        instance_id,
        _user_uuid(user_id),
        limit=limit,
        before_message_id=before_message_id,
    )
    if messages is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent instance not found",
        )
    return messages
