from enum import Enum
from uuid import UUID
import json
import logging
from typing import AsyncGenerator
import asyncio

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    BackgroundTasks,
    Query,
)
from fastapi.responses import Response, StreamingResponse
from shared.agent_catalog import AGENT_CATALOG_ETAG, AGENT_CATALOG_JSON
from shared.database.models import AgentInstance, Message, User
from shared.database.session import get_db, SessionLocal
from shared.database.enums import AgentStatus, InstanceAccessLevel
from sqlalchemy.orm import Session, attributes

from ..auth.dependencies import get_current_user
from shared.auth import verify_user_token
from shared.pg_listener import get_hub
from shared.sse_helpers import signal_sse_generator, sse_response
from ..db import (
    TERMINAL_STATUS_VALUES,
    get_agent_instance_detail,
    get_agent_type_instances,
    get_agent_summary,
    get_all_agent_instances,
    get_all_agent_types_with_instances,
    delete_agent_instance,
    update_agent_instance_name,
    update_agent_instance_pinned,
    link_instance_to_task,
    get_messages_after_id,
    get_latest_message_id,
    get_instance_messages,
    get_instance_git_diff,
    get_instance_shares,
    add_instance_share,
    remove_instance_share,
)
from ..models import (
    AgentInstanceDetail,
    PaginatedAgentInstanceResponse,
    AgentInstanceResponse,
    AgentTypeOverview,
    MessageResponse,
    UserMessageRequest,
    InstanceShareCreateRequest,
    InstanceShareResponse,
)
from servers.shared.db import update_session_title_if_needed
from shared.websocket import (
    after_commit,
    build_instance_update,
    build_message_update,
    build_new_message_update,
)
from ..broadcast_bridge import post_broadcast
from ..db.queries import (
    bind_attachments_to_message,
    cancel_user_message,
    create_user_message_with_access,
    get_instance_and_access,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"])


@router.get("/agent-types", response_model=list[AgentTypeOverview])
def list_agent_types(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all agent types with their instances for the current user"""
    agent_types = get_all_agent_types_with_instances(db, current_user.id)
    return agent_types


@router.get("/agent-catalog")
def get_agent_catalog(
    current_user: User = Depends(get_current_user),
    if_none_match: str | None = Header(default=None),
) -> Response:
    """Return the static agent / model / permission catalog.

    Public-cache-safe: the same payload is served to every authenticated user,
    so we ETag it and honour conditional GET. Auth is required only to gate
    behind a logged-in session (no user-scoping in the body).
    See plans/new-session-model-selection.md §3.1, §3.11, §5.2.
    """
    if if_none_match == AGENT_CATALOG_ETAG:
        return Response(status_code=304)
    return Response(
        content=AGENT_CATALOG_JSON,
        media_type="application/json",
        headers={
            "ETag": AGENT_CATALOG_ETAG,
            "Cache-Control": "private, max-age=3600",
        },
    )


class AgentInstanceScope(str, Enum):
    ME = "me"
    SHARED = "shared"
    ALL = "all"


@router.get("/agent-instances", response_model=PaginatedAgentInstanceResponse)
def list_all_agent_instances(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    scope: AgentInstanceScope = AgentInstanceScope.ME,
    active_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get agent instances visible to the current user"""
    instances, total = get_all_agent_instances(
        db,
        current_user.id,
        limit=limit,
        offset=offset,
        scope=scope.value,
        active_only=active_only,
    )
    return PaginatedAgentInstanceResponse(
        items=instances,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(instances) < total,
    )


@router.get("/agent-instances/stream")
async def stream_agent_instances(
    request: Request,
    token: str | None = None,
):
    """Stream agent instance list events using Server-Sent Events.

    Listens on the per-user channel ``user_instances_channel_{user_id}`` and
    forwards ``instance_created`` / ``instance_updated`` events so web and app
    clients can keep their instance lists up-to-date without polling.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Token required for SSE")

    try:
        # Verification is local for a configured provider, but the Supabase
        # provider still has a network fallback — and blocking here would freeze
        # every other SSE generator and /health check on this single-CPU worker.
        user_id = (await asyncio.to_thread(verify_user_token, token)).user_id
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

    return sse_response(
        signal_sse_generator(
            request=request,
            channel=f"user_instances_channel_{user_id}",
            connected_event={"user_id": str(user_id)},
            default_event_type="instance_updated",
        )
    )


@router.get("/agent-summary")
def get_all_agent_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get lightweight summary of agent counts for dashboard KPIs"""
    summary = get_agent_summary(db, current_user.id)
    return summary


@router.get(
    "/agent-types/{type_id}/instances", response_model=list[AgentInstanceResponse]
)
def get_type_instances(
    type_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all instances for a specific agent type for the current user"""
    result = get_agent_type_instances(db, type_id, current_user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Agent type not found")
    return result


@router.get("/agent-instances/{instance_id}", response_model=AgentInstanceDetail)
def get_instance_detail(
    instance_id: UUID,
    message_limit: int = 50,
    before_message_id: UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get detailed information about a specific agent instance for the current user with cursor-based message pagination"""
    result = get_agent_instance_detail(
        db,
        instance_id,
        current_user.id,
        message_limit=message_limit,
        before_message_id=before_message_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Agent instance not found")
    return result


@router.get("/agent-instances/{instance_id}/messages")
def get_instance_messages_paginated(
    instance_id: UUID,
    limit: int = 50,
    before_message_id: UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get paginated messages for an agent instance using cursor-based pagination"""
    messages = get_instance_messages(
        db,
        instance_id,
        current_user.id,
        limit=limit,
        before_message_id=before_message_id,
    )
    if messages is None:
        raise HTTPException(status_code=404, detail="Agent instance not found")
    # Return just the messages array
    return messages


@router.get(
    "/agent-instances/{instance_id}/access",
    response_model=list[InstanceShareResponse],
)
def list_instance_access(
    instance_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List users who have access to this agent instance"""
    try:
        return get_instance_shares(db, instance_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.post(
    "/agent-instances/{instance_id}/access",
    response_model=InstanceShareResponse,
)
def add_instance_access(
    instance_id: UUID,
    request: InstanceShareCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Grant access to an agent instance for another user"""
    try:
        share = add_instance_share(
            db,
            instance_id=instance_id,
            user_id=current_user.id,
            email=request.email,
            access_level=request.access,
        )
        db.commit()
        return share
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.delete("/agent-instances/{instance_id}/access/{access_id}")
def remove_instance_access(
    instance_id: UUID,
    access_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke shared access from a user"""
    try:
        remove_instance_share(db, instance_id, current_user.id, access_id)
        db.commit()
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.post("/agent-instances/{instance_id}/messages", response_model=MessageResponse)
def create_user_message_endpoint(
    instance_id: UUID,
    request: UserMessageRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a message to an agent instance (answers questions or provides feedback)"""
    user_id = current_user.id
    try:
        attachment_uuids = [UUID(a) for a in request.attachment_ids]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid attachment id")
    try:
        # `create_user_message_with_access` unconditionally flips the
        # instance to ACTIVE as part of creating the message (see below), so
        # the pre-existing status must be captured *before* that call — it's
        # the only way to tell whether the agent was already busy (this
        # message queues behind its current turn) or idle/awaiting input
        # (this message becomes the next thing it processes).
        prior_status = (
            db.query(AgentInstance.status)
            .filter(AgentInstance.id == instance_id)
            .scalar()
        )
        message = create_user_message_with_access(
            db=db,
            instance_id=instance_id,
            user_id=user_id,
            content=request.content,
            mark_as_read=False,
        )
        if attachment_uuids:
            # Stamps message_metadata["attachments"] pre-commit so the
            # response and broadcast envelope below both carry it.
            bind_attachments_to_message(
                db=db,
                attachment_ids=attachment_uuids,
                user_id=user_id,
                message=message,
            )
        if prior_status == AgentStatus.ACTIVE:
            md = dict(message.message_metadata or {})
            md["queue"] = {"status": "queued"}
            message.message_metadata = md
            attributes.flag_modified(message, "message_metadata")
        # Snapshot all ORM attributes before commit — expire_on_commit makes
        # attribute access after commit unsafe (§2.7).
        response = MessageResponse(
            id=str(message.id),
            content=message.content,
            sender_type=message.sender_type.value,
            sender_user_id=str(user_id),
            sender_user_email=current_user.email,
            sender_user_display_name=current_user.display_name,
            created_at=message.created_at,
            requires_user_input=message.requires_user_input,
            message_metadata=message.message_metadata,
        )
        payload = build_new_message_update(message)
        rooms = [
            f"user:{user_id}:session:{instance_id}",
            f"user:{user_id}:user-scoped",
        ]
        after_commit(db, lambda: post_broadcast(str(user_id), payload, rooms))
        db.commit()

        def update_title_with_session():
            with SessionLocal() as db_session:
                update_session_title_if_needed(
                    db=db_session,
                    instance_id=instance_id,
                    user_message=request.content,
                )

        background_tasks.add_task(update_title_with_session)

        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Internal server error: {str(e)}"
        ) from e


@router.post("/agent-instances/{instance_id}/messages/{message_id}/cancel")
def cancel_queued_message_endpoint(
    instance_id: UUID,
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel a user message still sitting in `queue.status=queued`.

    Access check mirrors `create_user_message_endpoint`'s
    `create_user_message_with_access` (`get_instance_and_access` + a WRITE
    floor), not raw `AgentInstance.user_id` ownership — a collaborator with
    WRITE access via `UserInstanceAccess`/`TeamInstanceAccess` (instance
    sharing / teams) can cancel a message the same way they're allowed to
    send one. `cancel_user_message` is the atomic guard: it is a no-op
    (returns False, no broadcast) once the agent has already consumed the
    message — the consume/cancel race must resolve in favor of whichever
    happened first.
    """
    user_id = current_user.id
    instance, access = get_instance_and_access(db, instance_id, user_id)
    if not instance or access != InstanceAccessLevel.WRITE:
        raise HTTPException(status_code=404, detail="Agent instance not found")

    message = (
        db.query(Message)
        .filter(
            Message.id == message_id,
            Message.agent_instance_id == instance_id,
        )
        .first()
    )
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    cancelled = cancel_user_message(db, message_id)
    if cancelled:
        fresh = db.query(Message).filter(Message.id == message_id).first()
        # `cancelled` True means the UPDATE matched this exact id, so the row
        # cannot have vanished between the two queries in the same
        # transaction — the `is not None` narrowing is for pyright.
        assert fresh is not None
        payload = build_message_update(fresh)
        rooms = [
            f"user:{user_id}:user-scoped",
            f"user:{user_id}:session:{instance_id}",
        ]
        after_commit(db, lambda: post_broadcast(str(user_id), payload, rooms))
    db.commit()
    return {"cancelled": cancelled}


@router.get("/agent-instances/{instance_id}/messages/stream")
async def stream_messages(
    request: Request,
    instance_id: UUID,
    token: str | None = None,
    last_message_id: UUID | None = None,
):
    """Stream new messages for an agent instance using Server-Sent Events"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required for SSE")

    try:
        # Verification is local for a configured provider, but the Supabase
        # provider still has a network fallback — and blocking here would freeze
        # every other SSE generator and /health check on this single-CPU worker.
        user_id = (await asyncio.to_thread(verify_user_token, token)).user_id
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

    with SessionLocal() as db:
        instance = get_agent_instance_detail(db, instance_id, user_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Agent instance not found")

    async def message_generator() -> AsyncGenerator[str, None]:
        channel_name = f"message_channel_{instance_id}"
        last_delivered_message_id: UUID | None = last_message_id

        def _cursor_query() -> list[dict]:
            try:
                with SessionLocal() as db:
                    return get_messages_after_id(
                        db, instance_id, user_id, last_delivered_message_id
                    )
            except Exception:
                logger.exception(
                    "SSE: cursor query failed for instance %s", instance_id
                )
                return []

        def _git_diff_query(iid: UUID) -> dict | None:
            with SessionLocal() as db:
                return get_instance_git_diff(db, iid, user_id)

        def _init_cursor() -> UUID | None:
            """Anchor the cursor at the latest existing message on first connect."""
            try:
                with SessionLocal() as db:
                    return get_latest_message_id(db, instance_id, user_id)
            except Exception:
                logger.exception(
                    "SSE: failed to init cursor for instance %s", instance_id
                )
                return None

        try:
            async with get_hub().subscribe(channel_name) as (
                wake_event,
                signal_queue,
            ):
                loop = asyncio.get_running_loop()
                yield f"event: connected\ndata: {json.dumps({'instance_id': str(instance_id)})}\n\n"
                last_emit_at = loop.time()

                # If no cursor was provided, initialize from the DB latest message so
                # subsequent NOTIFY wakes can deliver new rows correctly.
                # This runs inside the subscribe block so the LISTEN is already active;
                # any NOTIFY fired after this point will set wake_event.
                if last_delivered_message_id is None:
                    last_delivered_message_id = await asyncio.to_thread(_init_cursor)

                # Eager catch-up: deliver any messages written between the cursor and
                # when this subscription was established (avoids waiting up to 15s).
                if last_delivered_message_id is not None:
                    catchup = await asyncio.to_thread(_cursor_query)
                    for msg in catchup:
                        last_delivered_message_id = UUID(msg["id"])
                        yield f"event: message\ndata: {json.dumps(msg)}\n\n"
                        last_emit_at = loop.time()

                while True:
                    try:
                        await asyncio.wait_for(
                            wake_event.wait_and_clear(), timeout=15.0
                        )
                    except asyncio.TimeoutError:
                        pass

                    if await request.is_disconnected():
                        break

                    # Cursor query: sweeps up every committed row since last delivery.
                    # Same code path for both NOTIFY wake and 15s keepalive.
                    new_messages = await asyncio.to_thread(_cursor_query)
                    for msg in new_messages:
                        last_delivered_message_id = UUID(msg["id"])
                        yield f"event: message\ndata: {json.dumps(msg)}\n\n"
                        last_emit_at = loop.time()

                    # Drain signal events accumulated since last wake.
                    should_terminate = False
                    terminate_status: str | None = None
                    for sig_payload in signal_queue.drain_nowait():
                        try:
                            sig_data = json.loads(sig_payload)
                            sig_type = sig_data.get("event_type", "")
                            if (
                                sig_type == "status_update"
                                and sig_data.get("status") in TERMINAL_STATUS_VALUES
                            ):
                                should_terminate = True
                                terminate_status = sig_data.get("status")
                            if sig_type == "git_diff_update":
                                iid_str = sig_data.get("instance_id")
                                if iid_str:
                                    diff = await asyncio.to_thread(
                                        _git_diff_query, UUID(iid_str)
                                    )
                                    if diff:
                                        sig_data["git_diff"] = diff["git_diff"]
                            if sig_type:
                                yield f"event: {sig_type}\ndata: {json.dumps(sig_data)}\n\n"
                                last_emit_at = loop.time()
                        except Exception:
                            logger.exception(
                                "SSE: error processing signal event on %s",
                                channel_name,
                            )

                    if should_terminate:
                        yield f"event: terminate\ndata: {json.dumps({'event_type': 'terminate', 'instance_id': str(instance_id), 'status': terminate_status})}\n\n"
                        break

                    # Time-based heartbeat — see comment in
                    # servers/api/routers.py:stream_instance_messages for the
                    # rationale. This stream is less prone to silence than the
                    # USER-filtered wrapper one (it yields signal events too),
                    # but the same wake-without-emit race exists, so cap idle
                    # at 10s for symmetry.
                    now = loop.time()
                    if now - last_emit_at >= 10.0:
                        yield f"event: heartbeat\ndata: {json.dumps({'timestamp': now})}\n\n"
                        last_emit_at = now
        except asyncio.CancelledError:
            raise
        except BaseException:
            # Surface the real cause; otherwise uvicorn only logs "ASGI
            # callable returned without completing response" with no
            # traceback, hiding the actual fault.
            logger.exception("stream_messages crashed on channel=%s", channel_name)
            raise

    return StreamingResponse(
        message_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _bridge_instance_update(db: Session, instance_id: UUID, user_id: UUID) -> None:
    """Deliver an `instance-update` over the §2.11 bridge after a committed write.

    These endpoints delegate to query functions that own their own commit, so
    the broadcast is issued post-commit (the row is already durable) rather
    than via `after_commit`. `post_broadcast` is fire-and-forget (§2.11).
    """
    instance = db.get(AgentInstance, instance_id)
    if instance is None:
        return
    payload = build_instance_update(instance)
    rooms = [
        f"user:{user_id}:user-scoped",
        f"user:{user_id}:session:{instance_id}",
    ]
    post_broadcast(str(user_id), payload, rooms)


@router.put(
    "/agent-instances/{instance_id}/status",
    response_model=AgentInstanceResponse,
)
def update_agent_status(
    instance_id: UUID,
    status_update: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an agent instance status for the current user"""
    from ..db import update_instance_status

    # Validate status field is provided
    if "status" not in status_update:
        raise HTTPException(status_code=400, detail="Status field is required")

    new_status = status_update.get("status")

    # Validate status value
    try:
        status_enum = AgentStatus(new_status)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid status value: {new_status}"
        )

    # Use the unified database function
    result = update_instance_status(db, instance_id, current_user.id, status_enum)

    if not result:
        raise HTTPException(status_code=404, detail="Agent instance not found")

    _bridge_instance_update(db, instance_id, current_user.id)
    return result


@router.delete("/agent-instances/{instance_id}")
def delete_agent_instance_endpoint(
    instance_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an agent instance"""
    result = delete_agent_instance(db, instance_id, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Agent instance not found")
    _bridge_instance_update(db, instance_id, current_user.id)
    return {"message": "Agent instance deleted successfully"}


ALLOWED_INSTANCE_PATCH_FIELDS = {"name", "pinned", "task_id"}


@router.patch("/agent-instances/{instance_id}", response_model=AgentInstanceResponse)
def update_agent_instance_endpoint(
    instance_id: UUID,
    update_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an agent instance. Supports `name`, `pinned` and `task_id`."""
    unknown = set(update_data.keys()) - ALLOWED_INSTANCE_PATCH_FIELDS
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported fields: {sorted(unknown)}",
        )
    if not update_data:
        raise HTTPException(status_code=400, detail="No update fields provided")

    result = None
    if "task_id" in update_data:
        raw_task_id = update_data["task_id"]
        try:
            task_id = UUID(str(raw_task_id)) if raw_task_id is not None else None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid task_id") from exc
        result = link_instance_to_task(db, instance_id, current_user.id, task_id)
        if not result:
            raise HTTPException(
                status_code=404, detail="Agent instance or task not found"
            )
    if "name" in update_data:
        result = update_agent_instance_name(
            db, instance_id, current_user.id, update_data["name"]
        )
    if "pinned" in update_data:
        result = update_agent_instance_pinned(
            db, instance_id, current_user.id, bool(update_data["pinned"])
        )
    if not result:
        raise HTTPException(status_code=404, detail="Agent instance not found")

    _bridge_instance_update(db, instance_id, current_user.id)
    return result
