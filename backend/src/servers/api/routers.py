"""API routes for agent and machine operations."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Annotated, AsyncGenerator
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    status,
    Response,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError as SAIntegrityError
from sqlalchemy.exc import OperationalError as SAOperationalError
from sqlalchemy.orm import Session, attributes, joinedload

from shared import storage
from shared.database.errors import is_db_disconnect
import json
import base64
import binascii

from shared.database.session import get_db, SessionLocal
from shared.pg_listener import get_hub
from shared.sse_helpers import signal_sse_generator, sse_response
from shared.database import (
    Message,
    AgentInstance,
    SenderType,
    AgentStatus,
    Machine,
    MachineSpawnRequest,
    SlashCommands,
    FileMentions,
)
from shared.database.agent_instances import create_agent_instance
from shared.database.project_matching import (
    resolve_or_create_project_id_for_session,
)
from integrations.headless.usage import project_rate_limited_until
from shared.websocket.connection_manager import connection_manager
from shared.websocket.envelope import (
    build_instance_created_update,
    build_instance_update,
    build_machine_update,
    build_message_update,
    build_new_message_update,
    build_spawn_request_update,
)
from shared.websocket.in_tx import after_commit
from shared.websocket.rpc import RpcError, rpc_router
from servers.shared.db import (
    send_agent_message,
    end_session,
    get_agent_instance,
    get_attachment_for_agent,
    get_or_create_agent_instance,
    get_queued_user_messages,
    get_user_messages_after_id,
    get_latest_message_id_for_instance,
    create_user_message,
    mark_message_consumed,
    push_recent_directory_after_spawn,
    update_session_title_if_needed,
    upsert_machine_agent_models,
)
from servers.shared.notification_utils import send_message_notifications
from .auth import get_current_user_id
from .models import (
    CreateMessageRequest,
    CreateMessageResponse,
    CreateUserMessageRequest,
    CreateUserMessageResponse,
    EndSessionRequest,
    EndSessionResponse,
    GetMessagesResponse,
    MessageResponse,
    RegisterAgentInstanceRequest,
    RegisterAgentInstanceResponse,
    RegisterMachineRequest,
    RegisterMachineResponse,
    HeartbeatMachineRequest,
    MachineRpcRequest,
    UpdateMachineRecentDirectoryRequest,
    MachineListResponse,
    SpawnSessionRequest,
    SpawnSessionResponse,
    NextSpawnRequestResponse,
    UpdateSpawnRequestRequest,
    MachineSummary,
    VerifyAuthResponse,
    SyncCommandsRequest,
    SyncCommandsResponse,
    SyncFilesRequest,
    SyncFilesResponse,
    UpdateAgentInstanceRequest,
)

agent_router = APIRouter(tags=["agents"])
logger = logging.getLogger(__name__)


def _maybe_decode_base64(value: str | None) -> str | None:
    """Decode base64 strings if they look like base64; otherwise return as-is.

    Uses strict validation to avoid mis-detecting plain text. If decoding
    succeeds, returns the UTF-8 decoded text (with replacement for any invalid
    sequences). If decoding fails, returns the original value.
    """
    if value is None:
        return None
    try:
        decoded = base64.b64decode(value, validate=True)
        try:
            return decoded.decode("utf-8")
        except UnicodeDecodeError:
            return decoded.decode("utf-8", errors="replace")
    except (binascii.Error, ValueError):
        return value


def _get_machine_for_user(db: Session, machine_id: str, user_id: str) -> Machine:
    try:
        machine_uuid = UUID(machine_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid machine identifier",
        ) from exc

    user_uuid = UUID(user_id)

    machine = (
        db.query(Machine)
        .filter(Machine.id == machine_uuid, Machine.user_id == user_uuid)
        .first()
    )

    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machine not found",
        )

    return machine


def _machine_summary(machine: Machine) -> MachineSummary:
    metadata = (
        machine.machine_metadata if isinstance(machine.machine_metadata, dict) else None
    )
    raw_dirs = []
    if metadata and isinstance(metadata.get("recent_directories"), list):
        raw_dirs = [str(item) for item in metadata.get("recent_directories", [])]

    return MachineSummary(
        machine_id=str(machine.id),
        display_name=machine.display_name,
        hostname=machine.hostname,
        platform=machine.platform,
        home_dir=machine.home_dir,
        last_heartbeat_at=machine.last_heartbeat_at,
        metadata=metadata,
        recent_directories=raw_dirs[:10],
    )


@agent_router.get("/machines", response_model=MachineListResponse)
def list_machines_endpoint(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> MachineListResponse:
    user_uuid = UUID(user_id)
    machines = (
        db.query(Machine)
        .filter(Machine.user_id == user_uuid)
        .order_by(Machine.created_at.desc())
        .all()
    )

    summaries = [_machine_summary(machine) for machine in machines]
    return MachineListResponse(machines=summaries)


def _broadcast_instance_update(
    db: Session,
    instance: AgentInstance,
    user_id: str,
    *,
    created: bool = False,
) -> None:
    """Emit an instance update after commit (§2.5).

    Call before `db.commit()`: the envelope is snapshotted now so the
    `after_commit` callback closes over plain data (§2.7). A creation goes
    to the user-scoped room; an update also goes to the session room.
    """
    if created:
        payload = build_instance_created_update(instance)
        rooms = [f"user:{user_id}:user-scoped"]
    else:
        payload = build_instance_update(instance)
        rooms = [
            f"user:{user_id}:user-scoped",
            f"user:{user_id}:session:{instance.id}",
        ]
    after_commit(
        db, lambda: connection_manager.broadcast_update(user_id, payload, rooms)
    )


def _broadcast_new_message(db: Session, message: Message, user_id: str) -> None:
    """Emit a `new-message` update after commit (§2.5).

    User messages fan out to both the user-scoped room (web/mobile chat
    surfaces) and the session-scoped room (CLI wrapper, which forwards the
    content into the PTY). Agent messages go to user-scoped only — the
    wrapper *produces* them, and re-broadcasting into its session room would
    be received by `session_ws_client` as a fresh `new-message` body and
    injected back into Claude as if the user had typed it. Mirrors the
    `include_agent_messages=False` default that `fetch_session_messages`
    already applies to session-scoped catch-up.

    Call before `db.commit()` — the envelope is snapshotted now.
    """
    payload = build_new_message_update(message)
    rooms = [f"user:{user_id}:user-scoped"]
    if message.sender_type == SenderType.USER:
        rooms.append(f"user:{user_id}:session:{message.agent_instance_id}")
    after_commit(
        db, lambda: connection_manager.broadcast_update(user_id, payload, rooms)
    )


def _broadcast_message_update(db: Session, message: Message, user_id: str) -> None:
    """Emit a `message-update` after commit (§2.5) for a metadata-only patch.

    Unlike `_broadcast_new_message` (append, new row), this is for changes to
    an existing row's `message_metadata` — currently the queue lifecycle's
    `consumed` stamp. User-scoped only: the session room is for the wrapper's
    PTY-forwarding of user messages, which this is not.

    Call before committing — the envelope is snapshotted now.
    """
    payload = build_message_update(message)
    rooms = [f"user:{user_id}:user-scoped"]
    after_commit(
        db, lambda: connection_manager.broadcast_update(user_id, payload, rooms)
    )


def _broadcast_machine_update(db: Session, machine: Machine, user_id: str) -> None:
    """Emit a `machine-update` to the user-scoped room after commit (§2.5).

    Call before `db.commit()`: the envelope is snapshotted now, so the
    `after_commit` callback closes over plain data, never an expired ORM row
    (§2.7).
    """
    payload = build_machine_update(machine)
    room = f"user:{user_id}:user-scoped"
    after_commit(
        db, lambda: connection_manager.broadcast_update(user_id, payload, [room])
    )


@agent_router.post("/machines/register", response_model=RegisterMachineResponse)
def register_machine_endpoint(
    request: RegisterMachineRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> RegisterMachineResponse:
    user_uuid = UUID(user_id)

    machine: Machine | None = None
    requested_machine_uuid: UUID | None = None

    # Validate the supplied id up front so a malformed one still 400s even when
    # the hardware_id dedup below ends up winning.
    if request.machine_id:
        try:
            requested_machine_uuid = UUID(request.machine_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid machine identifier",
            ) from exc

    # Identity anchor: dedup on (user_id, hardware_id) FIRST. The client-derived
    # machine_id folds in the API key, so a re-auth mints a different id; keying
    # on the stable hardware id resolves it back to the same row regardless of
    # the supplied machine_id.
    if request.hardware_id:
        machine = (
            db.query(Machine)
            .filter(
                Machine.user_id == user_uuid,
                Machine.hardware_id == request.hardware_id,
            )
            .first()
        )

    # Fall back to the supplied machine_id (legacy daemons / first register on
    # this host / hosts with no readable hardware id).
    if machine is None and requested_machine_uuid is not None:
        machine = db.query(Machine).filter(Machine.id == requested_machine_uuid).first()
        if machine is not None and machine.user_id != user_uuid:
            # The supplied id belongs to a different account — e.g. this host
            # was first registered under another login, or a stale machine_id is
            # cached in ~/.vicoa/daemon_state.json from a previous account. Don't
            # hard-fail: a 403 here propagates through register_machine and
            # crashes the daemon, blocking desktop setup entirely. The id simply
            # isn't ours, so drop it and mint a fresh row for the current user
            # below. Never adopt another user's row (that would leak their
            # machine/sessions). The daemon persists the returned machine_id, so
            # it stops resending the stale one on the next register.
            machine = None
            requested_machine_uuid = None

    if machine is None:
        machine = Machine(
            id=requested_machine_uuid or uuid4(),
            user_id=user_uuid,
        )
        db.add(machine)

    # Persist / backfill the hardware anchor on the resolved row so subsequent
    # re-auths dedup (including legacy rows first seen before this column).
    if request.hardware_id:
        machine.hardware_id = request.hardware_id

    machine.hostname = request.hostname
    machine.platform = request.platform
    if request.home_dir is not None:
        machine.home_dir = request.home_dir
    if request.display_name is not None:
        machine.display_name = request.display_name

    metadata: dict = (
        machine.machine_metadata if isinstance(machine.machine_metadata, dict) else {}
    )
    extras = request.metadata or {}
    if extras:
        metadata.update(extras)

    # If cwd is provided in metadata, add it to recent_directories
    if extras and "cwd" in extras:
        cwd = str(extras["cwd"])
        recent_dirs = []
        if isinstance(metadata.get("recent_directories"), list):
            recent_dirs = [str(item) for item in metadata["recent_directories"]]
        if cwd not in recent_dirs:
            recent_dirs = [cwd] + recent_dirs
        metadata["recent_directories"] = recent_dirs[:10]

    machine.machine_metadata = metadata or None
    attributes.flag_modified(machine, "machine_metadata")

    now = datetime.now(timezone.utc)
    machine.last_heartbeat_at = now
    machine.updated_at = now

    db.flush()
    summary = _machine_summary(machine)
    _broadcast_machine_update(db, machine, user_id)
    db.commit()

    return RegisterMachineResponse(
        machine_id=summary.machine_id,
        display_name=summary.display_name,
        hostname=summary.hostname,
        platform=summary.platform,
        home_dir=summary.home_dir,
        last_heartbeat_at=summary.last_heartbeat_at,
        metadata=summary.metadata,
    )


@agent_router.post(
    "/machines/{machine_id}/heartbeat",
    response_model=RegisterMachineResponse,
)
def heartbeat_machine_endpoint(
    machine_id: str,
    request: HeartbeatMachineRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> RegisterMachineResponse:
    machine = _get_machine_for_user(db, machine_id, user_id)

    now = datetime.now(timezone.utc)
    machine.last_heartbeat_at = now
    machine.updated_at = now

    if request.metadata:
        metadata = (
            machine.machine_metadata
            if isinstance(machine.machine_metadata, dict)
            else {}
        )
        if metadata is None:
            metadata = {}
        metadata.update(request.metadata)
        machine.machine_metadata = metadata

    db.flush()
    summary = _machine_summary(machine)
    _broadcast_machine_update(db, machine, user_id)
    db.commit()
    return RegisterMachineResponse(
        machine_id=summary.machine_id,
        display_name=summary.display_name,
        hostname=summary.hostname,
        platform=summary.platform,
        home_dir=summary.home_dir,
        last_heartbeat_at=summary.last_heartbeat_at,
        metadata=summary.metadata,
    )


@agent_router.patch(
    "/machines/{machine_id}/recent-directories",
    response_model=RegisterMachineResponse,
)
def update_machine_recent_directories_endpoint(
    machine_id: str,
    request: UpdateMachineRecentDirectoryRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> RegisterMachineResponse:
    machine = _get_machine_for_user(db, machine_id, user_id)

    metadata: dict = (
        machine.machine_metadata if isinstance(machine.machine_metadata, dict) else {}
    ) or {}

    recent_dirs: list[str] = []
    if isinstance(metadata.get("recent_directories"), list):
        recent_dirs = [str(item) for item in metadata["recent_directories"]]

    recent_dirs = [request.cwd] + [path for path in recent_dirs if path != request.cwd]
    metadata["recent_directories"] = recent_dirs[:10]

    if request.cli_version is not None:
        metadata["cli_version"] = request.cli_version
    if request.python_version is not None:
        metadata["python_version"] = request.python_version

    machine.machine_metadata = metadata
    attributes.flag_modified(machine, "machine_metadata")
    machine.updated_at = datetime.now(timezone.utc)

    db.flush()
    summary = _machine_summary(machine)
    _broadcast_machine_update(db, machine, user_id)
    db.commit()
    return RegisterMachineResponse(
        machine_id=summary.machine_id,
        display_name=summary.display_name,
        hostname=summary.hostname,
        platform=summary.platform,
        home_dir=summary.home_dir,
        last_heartbeat_at=summary.last_heartbeat_at,
        metadata=summary.metadata,
    )


@agent_router.post(
    "/machines/{machine_id}/spawn-requests",
    response_model=SpawnSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_spawn_request_endpoint(
    machine_id: str,
    request: SpawnSessionRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> SpawnSessionResponse:
    machine = _get_machine_for_user(db, machine_id, user_id)
    user_uuid = UUID(user_id)

    agent_instance_id = uuid4()
    instance = create_agent_instance(
        db,
        user_uuid,
        agent_name=(request.agent or "claude"),
        instance_id=agent_instance_id,
        name=request.metadata.get("name")
        if isinstance(request.metadata, dict)
        else None,
        instance_metadata={"spawn_starting": True},
        status=AgentStatus.STARTING,
    )

    request_metadata = (
        dict(request.metadata) if isinstance(request.metadata, dict) else {}
    )
    # Only forward a prompt if the client actually sent one. Empty/missing
    # means the session starts blank and waits for input — see headless
    # runners' ``initialize()`` and ``machine_daemon._extract_prompt``.
    if request.prompt and request.prompt.strip():
        request_metadata["prompt"] = request.prompt
    else:
        request_metadata.pop("prompt", None)

    spawn_request = MachineSpawnRequest(
        id=uuid4(),
        machine_id=machine.id,
        requested_by_user_id=user_uuid,
        directory=request.directory,
        agent=(request.agent or "claude"),
        agent_instance_id=instance.id,
        request_metadata=request_metadata,
    )

    machine_metadata = (
        machine.machine_metadata if isinstance(machine.machine_metadata, dict) else {}
    )
    if machine_metadata is None:
        machine_metadata = {}
    recent_dirs = []
    if isinstance(machine_metadata.get("recent_directories"), list):
        recent_dirs = [str(item) for item in machine_metadata["recent_directories"]]

    recent_dirs = [request.directory] + [
        path for path in recent_dirs if path != request.directory
    ]
    machine_metadata["recent_directories"] = recent_dirs[:10]
    machine.machine_metadata = machine_metadata
    attributes.flag_modified(machine, "machine_metadata")

    db.add(spawn_request)
    db.flush()

    # Legacy NOTIFY: safety net for the still-alive spawn-requests SSE
    # stream and old daemons (websocket-migration §4 Phase 2).
    notify_payload = json.dumps(
        {
            "request_id": str(spawn_request.id),
            "directory": spawn_request.directory,
            "agent": spawn_request.agent,
            "agent_instance_id": str(spawn_request.agent_instance_id),
            "metadata": spawn_request.request_metadata,
            "requested_at": spawn_request.created_at.isoformat() + "Z",
        }
    )
    channel = f"machine_spawn_{machine_id}"
    db.execute(text(f'NOTIFY "{channel}", :payload'), {"payload": notify_payload})

    # WebSocket spawn-request update to the machine room (§2.5). The
    # envelope is snapshotted to primitives before commit; the after_commit
    # callback closes over plain data, never the ORM row.
    spawn_payload = build_spawn_request_update(spawn_request)
    machine_room = f"user:{user_id}:machine:{machine_id}"
    after_commit(
        db,
        lambda: connection_manager.broadcast_update(
            user_id, spawn_payload, [machine_room]
        ),
    )

    response = SpawnSessionResponse(
        request_id=str(spawn_request.id),
        agent_instance_id=str(agent_instance_id),
    )
    db.commit()

    return response


@agent_router.get("/machines/{machine_id}/spawn-requests/stream")
async def stream_spawn_requests(
    request: Request,
    machine_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> StreamingResponse:
    """Stream spawn requests for a machine using Server-Sent Events.

    The daemon opens this once on startup. When a spawn request is created,
    the backend fires a NOTIFY on ``machine_spawn_{machine_id}`` and the event
    is pushed down this connection instantly.
    """
    with SessionLocal() as db:
        _get_machine_for_user(db, machine_id, user_id)

    return sse_response(
        signal_sse_generator(
            request=request,
            channel=f"machine_spawn_{machine_id}",
            connected_event={"machine_id": machine_id},
            # The daemon expects the raw payload pass-through under event_type
            # ``spawn_request``; the payload itself is treated as opaque here.
            payload_to_event=lambda payload: ("spawn_request", payload),
        )
    )


@agent_router.post(
    "/machines/{machine_id}/spawn-requests/next",
    response_model=NextSpawnRequestResponse,
)
def claim_next_spawn_request_endpoint(
    machine_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> Response | NextSpawnRequestResponse:
    # SELECT FOR UPDATE SKIP LOCKED + the status UPDATE run in the
    # request-scoped session transaction so both atomically commit together.
    machine = _get_machine_for_user(db, machine_id, user_id)

    pending_request = (
        db.query(MachineSpawnRequest)
        .filter(
            MachineSpawnRequest.machine_id == machine.id,
            MachineSpawnRequest.status == "pending",
        )
        .order_by(MachineSpawnRequest.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )

    if not pending_request:
        db.rollback()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    pending_request.status = "claimed"
    pending_request.claimed_at = datetime.now(timezone.utc)

    # Snapshot for the response before commit — expire_on_commit makes ORM
    # access after commit unsafe (§2.7).
    response = NextSpawnRequestResponse(
        request_id=str(pending_request.id),
        directory=pending_request.directory,
        agent=pending_request.agent,
        agent_instance_id=(
            str(pending_request.agent_instance_id)
            if pending_request.agent_instance_id
            else None
        ),
        metadata=pending_request.request_metadata,
        requested_at=pending_request.created_at,
    )
    db.commit()

    return response


@agent_router.patch(
    "/machines/{machine_id}/spawn-requests/{request_id}",
)
def update_spawn_request_endpoint(
    machine_id: str,
    request_id: str,
    update: UpdateSpawnRequestRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
):
    try:
        request_uuid = UUID(request_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid spawn request identifier",
        ) from exc

    agent_uuid: UUID | None = None
    if update.agent_instance_id:
        try:
            agent_uuid = UUID(update.agent_instance_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid agent_instance_id",
            ) from exc

    # spawn-request UPDATE + the (optional) orphan AgentInstance.status flip
    # commit atomically in the request-scoped session transaction.
    machine = _get_machine_for_user(db, machine_id, user_id)

    spawn_request = (
        db.query(MachineSpawnRequest)
        .filter(
            MachineSpawnRequest.id == request_uuid,
            MachineSpawnRequest.machine_id == machine.id,
        )
        .first()
    )

    if not spawn_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Spawn request not found",
        )

    spawn_request.message = update.message

    agent_instance: AgentInstance | None = None
    if agent_uuid is not None:
        agent_instance = (
            db.query(AgentInstance)
            .filter(
                AgentInstance.id == agent_uuid,
                AgentInstance.user_id == machine.user_id,
            )
            .first()
        )

        if not agent_instance:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="agent_instance_id not found",
            )

    if update.status == "started":
        if agent_instance is None or agent_uuid is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="agent_instance_id is required when marking as started",
            )

        spawn_request.status = "started"
        spawn_request.agent_instance_id = agent_uuid
        spawn_request.completed_at = None
    else:
        # Terminal states: success or error
        if update.status == "success":
            # Prefer the provided agent instance but fall back to existing value.
            if agent_instance is not None and agent_uuid is not None:
                spawn_request.agent_instance_id = agent_uuid
            elif spawn_request.agent_instance_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="agent_instance_id is required for successful completion",
                )
        elif update.status == "error":
            # Allow retaining existing agent instance reference, or update if supplied.
            if agent_instance is not None and agent_uuid is not None:
                spawn_request.agent_instance_id = agent_uuid

        spawn_request.status = update.status
        spawn_request.completed_at = datetime.now(timezone.utc)

        if update.status == "error" and spawn_request.agent_instance_id:
            orphan = (
                db.query(AgentInstance)
                .filter(
                    AgentInstance.id == spawn_request.agent_instance_id,
                    AgentInstance.status == AgentStatus.STARTING,
                )
                .first()
            )
            if orphan:
                orphan.status = AgentStatus.FAILED

    db.commit()
    return {"success": True}


@agent_router.post("/machines/{machine_id}/rpc")
async def machine_rpc_endpoint(
    machine_id: str,
    request: MachineRpcRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict:
    """REST fallback for RPC (websocket-migration §2.8): route a call over the
    target daemon's WebSocket and return its result.

    The routing key `(user_id, machine_id, method)` is the cross-user isolation
    — a caller targeting a machine they do not own simply finds no handler and
    gets `no_handler`, so no separate ownership check is needed.
    """
    try:
        result = await rpc_router.call(
            user_id, machine_id, request.method, request.params
        )
    except RpcError as exc:
        http_status = {
            "no_handler": status.HTTP_404_NOT_FOUND,
            "target_disconnected": status.HTTP_503_SERVICE_UNAVAILABLE,
            "timeout": status.HTTP_504_GATEWAY_TIMEOUT,
        }.get(exc.code, status.HTTP_502_BAD_GATEWAY)
        raise HTTPException(status_code=http_status, detail=exc.code) from exc
    # Mirror the WS handler's post-spawn side effect so REST clients see the
    # same recent_directories update.
    if (
        request.method == "spawn-session"
        and isinstance(result, dict)
        and not result.get("error")
    ):
        directory = request.params.get("directory")
        if isinstance(directory, str) and directory.strip():
            try:
                push_recent_directory_after_spawn(
                    user_id, machine_id, directory.strip()
                )
            except Exception:
                logger.exception(
                    "failed to update recent_directories after REST spawn-session"
                )
    return {"result": result}


def _set_transport_metadata(instance: AgentInstance, transport: str | None) -> None:
    """Ensure instance metadata only includes transport details when provided."""
    if transport:
        metadata = (
            dict(instance.instance_metadata)
            if isinstance(instance.instance_metadata, dict)
            else {}
        )
        metadata["transport"] = transport
        instance.instance_metadata = metadata
        return

    if isinstance(instance.instance_metadata, dict):
        metadata = dict(instance.instance_metadata)
        metadata.pop("transport", None)
        instance.instance_metadata = metadata or None
    else:
        instance.instance_metadata = None


def _resolve_owned_machine_id(
    db: Session, raw_machine_id: str | None, user_id: str
) -> UUID | None:
    """Resolve a client-supplied machine_id to an owned machine, else None.

    Never raises (machine-management D8): an unparseable id, an unknown
    machine, or one owned by a different user all resolve to None so a stale
    or spoofed machine_id degrades the session's machine link rather than
    blocking session creation.
    """
    if not raw_machine_id:
        return None
    try:
        machine_uuid = UUID(raw_machine_id)
    except (ValueError, TypeError):
        return None
    owned = (
        db.query(Machine.id)
        .filter(Machine.id == machine_uuid, Machine.user_id == UUID(user_id))
        .first()
    )
    return machine_uuid if owned is not None else None


def _resolve_owned_task_id(db: Session, raw_task_id: str, user_id: str) -> UUID:
    """Parse and ownership-check a task_id for linking, or raise.

    Unlike ``_resolve_owned_machine_id`` (which degrades a bad id to None), an
    explicit task link is a deliberate request: a malformed id is a 400 and a
    missing/foreign task is a 404, so the caller learns the link did not happen
    rather than silently getting an unlinked session. Reuses the human-facing
    ``get_task`` — the same servers→backend query reuse as ``instances.py`` —
    so ownership scoping can never drift from the web.
    """
    from backend.db.task_queries import get_task

    try:
        task_uuid = UUID(raw_task_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid task_id"
        ) from exc
    if get_task(db, UUID(user_id), task_uuid) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return task_uuid


def _format_agent_instance(instance: AgentInstance) -> RegisterAgentInstanceResponse:
    metadata = (
        dict(instance.instance_metadata)
        if isinstance(instance.instance_metadata, dict)
        else None
    )
    status_value = (
        instance.status.value
        if hasattr(instance.status, "value")
        else str(instance.status)
    )
    agent_type_id = str(instance.user_agent_id) if instance.user_agent_id else None
    agent_type_name = (
        instance.user_agent.name if getattr(instance, "user_agent", None) else None
    )
    session_config = (
        dict(instance.session_config)
        if isinstance(instance.session_config, dict)
        else None
    )
    return RegisterAgentInstanceResponse(
        agent_instance_id=str(instance.id),
        agent_type_id=agent_type_id,
        agent_type_name=agent_type_name,
        status=status_value,
        name=instance.name,
        instance_metadata=metadata,
        project=instance.project,
        project_id=str(instance.project_id) if instance.project_id else None,
        home_dir=instance.home_dir,
        machine_id=str(instance.machine_id) if instance.machine_id else None,
        session_config=session_config,
    )


@agent_router.post(
    "/agent-instances",
    response_model=RegisterAgentInstanceResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_agent_instance_endpoint(
    request: RegisterAgentInstanceRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> RegisterAgentInstanceResponse:
    """Create a dedicated agent instance for relay-backed sessions."""

    instance_uuid: UUID | None = None
    if request.agent_instance_id:
        try:
            instance_uuid = UUID(request.agent_instance_id)
        except ValueError as exc:  # pragma: no cover - defensive validation
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid agent_instance_id",
            ) from exc

    # Validate the optional spawn-time task link up front (400/404) so we never
    # create the instance and then fail to link it. Stamped on the row below in
    # whichever branch runs; the before_flush sync flips the task on commit.
    task_uuid = (
        _resolve_owned_task_id(db, request.task_id, user_id)
        if request.task_id
        else None
    )

    try:
        existing: AgentInstance | None = None
        if instance_uuid is not None:
            existing = (
                db.query(AgentInstance)
                .filter(
                    AgentInstance.id == instance_uuid,
                    AgentInstance.status != AgentStatus.DELETED,
                )
                .first()
            )

        if existing is not None:
            if str(existing.user_id) != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Agent instance belongs to another user",
                )
            if not (
                existing.status == AgentStatus.STARTING
                and existing.instance_metadata
                and existing.instance_metadata.get("spawn_starting")
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Agent instance already exists",
                )
            # Pre-allocated by a spawn request — activate it.
            existing.status = AgentStatus.ACTIVE
            metadata = dict(existing.instance_metadata)
            metadata.pop("spawn_starting", None)
            if request.transport:
                metadata["transport"] = request.transport
            else:
                metadata.pop("transport", None)
            # Only stamp when the wrapper reported one. An older wrapper omits
            # the field entirely, and a session that moved out of a worktree
            # can't happen (cwd is fixed for the instance's life), so there is
            # nothing to clear.
            if request.worktree_name:
                metadata["worktree_name"] = request.worktree_name
            # Git identity probed by the SDK from the session cwd; stored like
            # worktree_name and used below to attribute the session to a project
            # (a linked worktree needs its repo root/remote — its cwd sits
            # outside the repo).
            if request.repo_root:
                metadata["repo_root"] = request.repo_root
            if request.git_remote_url:
                metadata["git_remote_url"] = request.git_remote_url
            existing.instance_metadata = metadata or None
            attributes.flag_modified(existing, "instance_metadata")
            if request.name:
                existing.name = request.name
            if request.project:
                existing.project = request.project
                # Now that the wrapper has reported its real cwd (+ repo
                # root/remote for worktrees), attach the session to a project
                # set up for that checkout — auto-creating one if this is the
                # first session in an unseen dir/repo (plan §4a), or None for
                # paths not worth a project (home dir, etc.).
                existing.project_id = resolve_or_create_project_id_for_session(
                    db,
                    UUID(user_id),
                    existing.machine_id,
                    request.project,
                    git_remote_url=request.git_remote_url,
                    repo_root=request.repo_root,
                    home_dir=request.home_dir or existing.home_dir,
                )
            if request.home_dir:
                existing.home_dir = request.home_dir
            # `session_config` is overwritten only when the wrapper explicitly
            # sent the field (incl. explicit null). Absent in the JSON =
            # preserve any value pre-staged by an earlier code path (see
            # plans/session-config-storage.md §5.2). model_fields_set carries
            # the wire-level "did this key appear" signal that a default
            # `None` would otherwise erase.
            if "session_config" in request.model_fields_set:
                existing.session_config = (
                    dict(request.session_config)
                    if request.session_config is not None
                    else None
                )
                attributes.flag_modified(existing, "session_config")
            # Link a spawn-time task, if one was requested and validated above.
            # Only stamp when present so a plain wrapper re-registration never
            # clears a link the spawn request pre-staged.
            if task_uuid is not None:
                existing.task_id = task_uuid
            db.flush()
            response = _format_agent_instance(existing)
            _broadcast_instance_update(db, existing, user_id)
        else:
            # Record transport and start source (app vs terminal) so an
            # app-initiated instance is distinguishable without a
            # machine_spawn_requests row (Phase 5 — no audit row).
            metadata: dict[str, str] = {}
            if request.transport:
                metadata["transport"] = request.transport
            if request.source:
                metadata["source"] = request.source
            if request.worktree_name:
                metadata["worktree_name"] = request.worktree_name
            if request.repo_root:
                metadata["repo_root"] = request.repo_root
            if request.git_remote_url:
                metadata["git_remote_url"] = request.git_remote_url
            instance_metadata = metadata or None
            resolved_machine_id = _resolve_owned_machine_id(
                db, request.machine_id, user_id
            )
            instance = create_agent_instance(
                db,
                UUID(user_id),
                agent_name=request.agent_type,
                instance_id=instance_uuid,
                name=request.name,
                instance_metadata=instance_metadata,
                project=request.project,
                project_id=resolve_or_create_project_id_for_session(
                    db,
                    UUID(user_id),
                    resolved_machine_id,
                    request.project,
                    git_remote_url=request.git_remote_url,
                    repo_root=request.repo_root,
                    home_dir=request.home_dir,
                ),
                home_dir=request.home_dir,
                machine_id=resolved_machine_id,
                session_config=request.session_config,
            )
            _set_transport_metadata(instance, request.transport)
            if task_uuid is not None:
                instance.task_id = task_uuid
            db.flush()
            response = _format_agent_instance(instance)
            _broadcast_instance_update(db, instance, user_id, created=True)

        db.commit()
        return response
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except SAIntegrityError:
        # *_user_id_fkey -> 401 via app-level handler. See companion sites.
        raise
    except Exception as exc:  # pragma: no cover - unexpected failure
        logger.error("Failed to register agent instance: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create agent instance",
        ) from exc


@agent_router.get("/auth/verify", response_model=VerifyAuthResponse)
def verify_auth_endpoint(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> VerifyAuthResponse:
    """Verify API key authentication.

    This endpoint is used by n8n and other integrations to test credentials.
    Returns basic information about the authenticated user and API key.
    """
    from shared.database import User

    try:
        # Get user information
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Get API key information (optional - just to show which key is being used)
        # Note: We can't identify the specific key from the JWT, but we know it's valid
        # if we got this far

        return VerifyAuthResponse(
            success=True,
            user_id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            message="Authentication successful",
        )
    except HTTPException:
        raise
    except SAIntegrityError:
        # Don't swallow FK violations as "Internal server error" — the
        # *_user_id_fkey case (a still-running CLI whose owning user was
        # deleted) is converted to 401 by the app-level handler in
        # ``servers/app.py`` (PR #45's reactive bouncer). Re-raise so it
        # reaches that handler instead of being caught below.
        raise
    except Exception as e:
        logger.error(f"Error in verify_auth_endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@agent_router.get(
    "/agent-instances/{instance_id}", response_model=RegisterAgentInstanceResponse
)
def get_agent_instance_endpoint(
    instance_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> RegisterAgentInstanceResponse:
    """Get an agent instance by ID."""
    try:
        instance = get_agent_instance(db, instance_id)
        if not instance or str(instance.user_id) != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent instance not found",
            )
        return _format_agent_instance(instance)
    except HTTPException:
        raise
    except SAIntegrityError:
        # Don't swallow FK violations as "Internal server error" — the
        # *_user_id_fkey case (a still-running CLI whose owning user was
        # deleted) is converted to 401 by the app-level handler in
        # ``servers/app.py`` (PR #45's reactive bouncer). Re-raise so it
        # reaches that handler instead of being caught below.
        raise
    except Exception as e:
        logger.error(f"Error getting agent instance: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@agent_router.put("/agent-instances/{instance_id}/status")
def update_agent_instance_status_endpoint(
    instance_id: UUID,
    status_data: dict,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> dict:
    """Update an agent instance status.

    Currently supports updating the status field of an agent instance.
    Used for resuming sessions (setting status to ACTIVE).
    """
    # Imported here to avoid a circular import at module load.
    from backend.db.queries import _notify_terminate, _TERMINAL_STATUSES

    try:
        user_uuid = UUID(user_id)

        # Validate status field is provided
        if "status" not in status_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status field is required",
            )

        new_status = status_data["status"]

        # Validate status value
        try:
            status_enum = AgentStatus(new_status)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status value: {new_status}",
            ) from e

        instance = (
            db.query(AgentInstance)
            .filter(
                AgentInstance.id == instance_id,
                AgentInstance.user_id == user_uuid,
            )
            .first()
        )
        # A DELETED instance stays deleted — treated as not found.
        if instance is None or instance.status == AgentStatus.DELETED:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent instance not found",
            )

        instance.status = status_enum
        if status_enum == AgentStatus.COMPLETED:
            instance.ended_at = datetime.now(timezone.utc)
        # Legacy NOTIFY: wakes a listening headless process to exit
        # (websocket-migration §2.7 safety net, alive through Wave B).
        if status_enum in _TERMINAL_STATUSES:
            _notify_terminate(db, instance_id)

        db.flush()
        _broadcast_instance_update(db, instance, user_id)
        db.commit()

        return {
            "success": True,
            "instance_id": str(instance_id),
            "status": status_enum.value,
        }

    except HTTPException:
        raise
    except SAIntegrityError:
        # Don't swallow FK violations as "Internal server error" — the
        # *_user_id_fkey case (a still-running CLI whose owning user was
        # deleted) is converted to 401 by the app-level handler in
        # ``servers/app.py`` (PR #45's reactive bouncer). Re-raise so it
        # reaches that handler instead of being caught below.
        raise
    except Exception as e:
        logger.error(f"Error updating agent instance status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e


@agent_router.patch(
    "/agent-instances/{instance_id}", response_model=RegisterAgentInstanceResponse
)
def update_agent_instance_endpoint(
    instance_id: UUID,
    update_data: UpdateAgentInstanceRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> RegisterAgentInstanceResponse:
    """Update agent instance metadata (currently only name/title)."""

    try:
        user_uuid = UUID(user_id)

        instance = (
            db.query(AgentInstance)
            .filter(
                AgentInstance.id == instance_id,
                AgentInstance.user_id == user_uuid,
            )
            .options(joinedload(AgentInstance.user_agent))
            .first()
        )
        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent instance not found",
            )

        fields = update_data.model_fields_set
        if "name" in fields:
            instance.name = update_data.name
        if "session_config" in fields:
            # Partial merge — keys present in the request overwrite, keys
            # absent are preserved. Starts from {} on a null column so a
            # legacy row gets initialized on the first PATCH. JSONB needs
            # flag_modified because dict-in-place mutation isn't tracked
            # by SQLAlchemy's change detection.
            merged = dict(instance.session_config or {})
            if update_data.session_config is not None:
                merged.update(update_data.session_config)
            instance.session_config = merged or None
            attributes.flag_modified(instance, "session_config")

            # Cache the machine's live model list (write-on-change) so the
            # new-session picker can show real models before a session starts.
            # Best-effort: isolate in a SAVEPOINT so a cache failure can't fail
            # the user-facing PATCH.
            incoming = update_data.session_config or {}
            agent_type = (merged or {}).get("agent")
            if "available_models" in incoming and instance.machine_id and agent_type:
                try:
                    with db.begin_nested():
                        upsert_machine_agent_models(
                            db,
                            machine_id=instance.machine_id,
                            agent_type=str(agent_type),
                            user_id=instance.user_id,
                            models=incoming.get("available_models"),
                        )
                except Exception:
                    logger.warning(
                        "Failed to cache machine_agent_models", exc_info=True
                    )
        if "instance_metadata" in fields:
            # Same partial-merge + flag_modified pattern as session_config: the
            # headless runners PATCH {"usage": {...}} each turn without touching
            # sibling keys (spawn_starting, source, ...).
            merged_meta = dict(instance.instance_metadata or {})
            if update_data.instance_metadata is not None:
                merged_meta.update(update_data.instance_metadata)
            instance.instance_metadata = merged_meta or None
            attributes.flag_modified(instance, "instance_metadata")
            # Project the rate-limit flag only when this PATCH carried usage, so
            # an unrelated metadata write (spawn_starting, source, ...) can't
            # clobber it. Same one-liner sets and clears: a recovering turn's
            # usage (windows back under 100%) projects None. See
            # plans/todos/auto-continue-rate-limited-sessions.md §2.
            if (
                update_data.instance_metadata
                and "usage" in update_data.instance_metadata
            ):
                instance.rate_limited_until = project_rate_limited_until(
                    merged_meta.get("usage")
                )
        if "task_id" in fields:
            # Field-present semantics (like the human-facing PATCH): a UUID
            # links (ownership-checked → 400/404), an explicit null unlinks.
            # Either way the before_flush sync re-derives the task's status on
            # the flush below, so a link onto a running session flips its task
            # to in_progress with no extra call.
            instance.task_id = (
                _resolve_owned_task_id(db, update_data.task_id, user_id)
                if update_data.task_id is not None
                else None
            )
        db.flush()
        response = _format_agent_instance(instance)
        _broadcast_instance_update(db, instance, user_id)
        db.commit()

        return response
    except HTTPException:
        raise
    except SAIntegrityError:
        # Don't swallow FK violations as "Internal server error" — the
        # *_user_id_fkey case (a still-running CLI whose owning user was
        # deleted) is converted to 401 by the app-level handler in
        # ``servers/app.py`` (PR #45's reactive bouncer). Re-raise so it
        # reaches that handler instead of being caught below.
        raise
    except Exception as e:
        logger.error(f"Error updating agent instance: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e


@agent_router.post("/messages/agent", response_model=CreateMessageResponse)
async def create_agent_message_endpoint(
    request: CreateMessageRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> CreateMessageResponse:
    """Create a new agent message.

    This endpoint:
    - Creates or retrieves an agent instance
    - Creates a new message
    - Returns the message ID and any queued user messages
    - Sends notifications if requested
    """

    try:
        decoded_git_diff = _maybe_decode_base64(request.git_diff)

        # Use the unified send_agent_message function
        instance_id, message_id, queued_messages = await send_agent_message(
            db=db,
            agent_instance_id=request.agent_instance_id,
            content=request.content,
            user_id=user_id,
            agent_type=request.agent_type,
            requires_user_input=request.requires_user_input,
            git_diff=decoded_git_diff,
            message_metadata=request.message_metadata,
        )
        db.flush()
        message_responses = [
            MessageResponse(
                id=str(msg.id),
                content=msg.content,
                sender_type=msg.sender_type.value,
                created_at=msg.created_at.isoformat(),
                requires_user_input=msg.requires_user_input,
                message_metadata=msg.message_metadata,
            )
            for msg in queued_messages
        ]
        # The agent posted a message and its instance's status/git_diff
        # changed — broadcast both (§2.5).
        message = db.get(Message, UUID(message_id))
        if message is not None:
            _broadcast_new_message(db, message, user_id)
        instance = db.get(AgentInstance, UUID(instance_id))
        if instance is not None:
            _broadcast_instance_update(db, instance, user_id)
        db.commit()

        # Send notifications if requested, after the write commits.
        await send_message_notifications(
            db=db,
            instance_id=UUID(instance_id),
            content=request.content,
            requires_user_input=request.requires_user_input,
            send_email=request.send_email,
            send_sms=request.send_sms,
            send_push=request.send_push,
        )

        return CreateMessageResponse(
            success=True,
            agent_instance_id=instance_id,
            message_id=message_id,
            queued_user_messages=message_responses,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise  # Re-raise HTTPExceptions as-is
    except SAIntegrityError:
        # See companion comments above — let the app-level handler
        # convert *_user_id_fkey to 401 instead of swallowing as 500.
        raise
    except Exception as e:
        logger.error(f"Error in create_agent_message_endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@agent_router.post("/messages/user", response_model=CreateUserMessageResponse)
def create_user_message_endpoint(
    request: CreateUserMessageRequest,
    background_tasks: BackgroundTasks,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> CreateUserMessageResponse:
    """Create a user message.

    This endpoint:
    - Creates a user message for an existing agent instance
    - Optionally marks it as read (updates last_read_message_id)
    - Returns the message ID
    - Triggers any waiting webhooks (e.g., n8n workflows)
    - Generates session title if needed (in background)
    """

    try:
        result = create_user_message(
            db=db,
            agent_instance_id=request.agent_instance_id,
            content=request.content,
            user_id=user_id,
            mark_as_read=request.mark_as_read,
        )
        message = db.get(Message, UUID(result["id"]))
        if message is not None:
            _broadcast_new_message(db, message, user_id)
        db.commit()

        # Add background task to update session title if needed
        def update_title_with_session():
            with SessionLocal() as db_session:
                update_session_title_if_needed(
                    db=db_session,
                    instance_id=UUID(result["instance_id"]),
                    user_message=request.content,
                )

        background_tasks.add_task(update_title_with_session)

        return CreateUserMessageResponse(
            success=True,
            message_id=result["id"],
            marked_as_read=result["marked_as_read"],
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except SAIntegrityError:
        db.rollback()
        # *_user_id_fkey -> 401 via app-level handler (see imports above).
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@agent_router.post("/agents/instances/{agent_instance_id}/heartbeat")
def heartbeat_instance(
    agent_instance_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> dict:
    """Record a heartbeat for an agent instance.

    - Verifies the instance belongs to the authenticated user
    - Updates last_heartbeat_at to now()
    - Returns the updated timestamp
    """
    from datetime import datetime, timezone

    try:
        instance = (
            db.query(AgentInstance)
            .filter(
                AgentInstance.id == agent_instance_id,
                AgentInstance.user_id == user_id,
            )
            .first()
        )
        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent instance not found",
            )

        heartbeat_at = datetime.now(timezone.utc)
        instance.last_heartbeat_at = heartbeat_at
        db.flush()
        _broadcast_instance_update(db, instance, user_id)
        db.commit()

        # Legacy NOTIFY: safety net for SSE clients (websocket-migration §2.7,
        # alive through Wave B). Runs in its own transaction so a NOTIFY
        # failure doesn't roll back the heartbeat write above, matching the
        # original "NOTIFY is best-effort" semantics.
        try:
            channel_name = f"message_channel_{agent_instance_id}"
            payload = json.dumps(
                {
                    "event_type": "agent_heartbeat",
                    "instance_id": str(agent_instance_id),
                    "last_heartbeat_at": heartbeat_at.isoformat() + "Z",
                }
            )
            # Quote channel due to hyphens in UUID
            db.execute(text(f'NOTIFY "{channel_name}", :payload'), {"payload": payload})
            db.commit()
        except Exception as notify_err:
            db.rollback()
            logger.warning(
                f"Failed to send agent_heartbeat NOTIFY for {agent_instance_id}: {notify_err}"
            )

        return {
            "agent_instance_id": str(agent_instance_id),
            "last_heartbeat_at": heartbeat_at.isoformat() + "Z",
        }
    except HTTPException:
        raise
    except SAIntegrityError:
        db.rollback()
        # *_user_id_fkey -> 401 via app-level handler.
        raise
    except SAOperationalError as exc:
        # Transient flycast disconnect — let the global handler convert
        # to 503 + Retry-After so the daemon retries naturally.
        db.rollback()
        if is_db_disconnect(exc):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(exc)}",
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@agent_router.get("/messages/pending", response_model=GetMessagesResponse)
def get_pending_messages(
    agent_instance_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    last_read_message_id: str | None = None,
    db: Session = Depends(get_db),
) -> GetMessagesResponse:
    """Get pending user messages for an agent instance.

    This endpoint:
    - Returns all user messages since the provided last_read_message_id
    - Updates the last_read_message_id to the latest message
    - Returns None status if another process has already read the messages
    """

    try:
        # Parse last_read_message_id if provided
        last_read_uuid = UUID(last_read_message_id) if last_read_message_id else None

        # Validate access (agent_instance_id is required here)
        instance = get_or_create_agent_instance(db, agent_instance_id, user_id)

        # Get queued messages
        messages = get_queued_user_messages(db, instance.id, last_read_uuid)

        # If messages is None, another process has read the messages
        if messages is None:
            db.commit()  # commit get_or_create_agent_instance write even on stale return
            return GetMessagesResponse(
                agent_instance_id=agent_instance_id,
                messages=[],
                status="stale",
            )

        # Snapshot response before commit — expire_on_commit makes ORM access
        # unsafe after commit (§2.7). Build MessageResponses first.
        message_responses = [
            MessageResponse(
                id=str(msg.id),
                content=msg.content,
                sender_type=msg.sender_type.value,
                created_at=msg.created_at.isoformat(),
                requires_user_input=msg.requires_user_input,
                message_metadata=msg.message_metadata,
            )
            for msg in messages
        ]
        db.commit()

        return GetMessagesResponse(
            agent_instance_id=agent_instance_id,
            messages=message_responses,
            status="ok",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except SAIntegrityError:
        # *_user_id_fkey -> 401 via app-level handler.
        raise
    except SAOperationalError as exc:
        # Transient flycast disconnect — propagate so global handler 503s it.
        if is_db_disconnect(exc):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(exc)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@agent_router.get("/attachments/{attachment_id}")
def download_attachment_endpoint(
    attachment_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
):
    """Serve attachment bytes to agent processes (wrappers/daemons)."""
    attachment = get_attachment_for_agent(db, attachment_id, UUID(user_id))
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found"
        )

    try:
        data = storage.download_attachment(attachment.s3_key)
    except Exception as e:
        logger.exception("attachment download from S3 failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to fetch file"
        ) from e

    return Response(
        content=data,
        media_type=attachment.mime_type,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@agent_router.patch("/messages/{message_id}/request-input")
async def request_user_input_endpoint(
    message_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> dict:
    """Update an agent message to request user input.

    This endpoint:
    - Updates the requires_user_input field from false to true
    - Only works on agent messages that don't already require input
    - Returns any queued user messages since this message
    - Triggers a notification via the database trigger
    """

    try:
        # Find the message; verify it is the user's own agent message.
        message = (
            db.query(Message)
            .join(AgentInstance, Message.agent_instance_id == AgentInstance.id)
            .filter(
                Message.id == message_id,
                Message.sender_type == SenderType.AGENT,
                AgentInstance.user_id == user_id,
            )
            .first()
        )
        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent message not found or access denied",
            )
        if message.requires_user_input:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message already requires user input",
            )

        message.requires_user_input = True
        agent_instance_id = message.agent_instance_id
        notify_content = message.content

        queued_messages = get_queued_user_messages(db, agent_instance_id, message_id)
        should_notify = not queued_messages
        if should_notify:
            agent_instance = (
                db.query(AgentInstance)
                .filter(AgentInstance.id == agent_instance_id)
                .first()
            )
            if agent_instance:
                agent_instance.status = AgentStatus.AWAITING_INPUT
                db.flush()
                _broadcast_instance_update(db, agent_instance, user_id)

        message_responses = [
            MessageResponse(
                id=str(msg.id),
                content=msg.content,
                sender_type=msg.sender_type.value,
                created_at=msg.created_at.isoformat(),
                requires_user_input=msg.requires_user_input,
                message_metadata=msg.message_metadata,
            )
            for msg in (queued_messages or [])
        ]
        response_status = "ok" if queued_messages is not None else "stale"
        db.commit()  # commit before FCM: WS broadcast already landed, FCM failure must not roll back DB

        if should_notify:
            await send_message_notifications(
                db=db,
                instance_id=agent_instance_id,
                content=notify_content,
                requires_user_input=True,
            )

        return {
            "success": True,
            "message_id": str(message_id),
            "agent_instance_id": str(agent_instance_id),
            "messages": message_responses,
            "status": response_status,
        }
    except HTTPException:
        raise
    except SAIntegrityError:
        # Don't swallow FK violations as "Internal server error" — the
        # *_user_id_fkey case (a still-running CLI whose owning user was
        # deleted) is converted to 401 by the app-level handler in
        # ``servers/app.py`` (PR #45's reactive bouncer). Re-raise so it
        # reaches that handler instead of being caught below.
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@agent_router.patch("/messages/{message_id}/consumed")
async def mark_message_consumed_endpoint(
    message_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> dict:
    """Mark a queued message as consumed by the wrapper picking it up.

    Completes the queue lifecycle's queued -> consumed transition (the
    `queued` stamp is written in `backend/api/agents.py` when a message
    arrives while the agent is ACTIVE). Idempotent: calling this again on an
    already-consumed message just re-stamps `consumed_at`. Skips messages
    already `cancelled` (`mark_message_consumed`'s WHERE clause) so a
    user-initiated cancel racing the wrapper's pickup always wins.
    """
    message = (
        db.query(Message)
        .join(AgentInstance, Message.agent_instance_id == AgentInstance.id)
        .filter(Message.id == message_id, AgentInstance.user_id == user_id)
        .first()
    )
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    updated = mark_message_consumed(db, message_id)
    if updated is not None:
        _broadcast_message_update(db, updated, user_id)
    db.commit()
    return {"success": True, "message_id": str(message_id)}


@agent_router.post("/sessions/end", response_model=EndSessionResponse)
def end_session_endpoint(
    request: EndSessionRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> EndSessionResponse:
    """End an agent session and mark it as completed.

    This endpoint:
    - Marks the agent instance as COMPLETED
    - Sets the session end time
    """

    try:
        instance_id, final_status = end_session(
            db=db,
            agent_instance_id=request.agent_instance_id,
            user_id=user_id,
        )
        instance = db.get(AgentInstance, UUID(instance_id))
        if instance is not None:
            db.flush()
            _broadcast_instance_update(db, instance, user_id)
        db.commit()

        return EndSessionResponse(
            success=True,
            agent_instance_id=instance_id,
            final_status=final_status,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    except HTTPException:
        raise
    except SAIntegrityError:
        # Don't swallow FK violations as "Internal server error" — the
        # *_user_id_fkey case (a still-running CLI whose owning user was
        # deleted) is converted to 401 by the app-level handler in
        # ``servers/app.py`` (PR #45's reactive bouncer). Re-raise so it
        # reaches that handler instead of being caught below.
        raise
    except Exception as e:
        logger.error(f"Error ending session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e


@agent_router.post("/commands/sync", response_model=SyncCommandsResponse)
def sync_commands_endpoint(
    request: SyncCommandsRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> SyncCommandsResponse:
    """Sync slash commands from CLI.

    This endpoint:
    - Receives commands from CLI (e.g. .claude/commands or .opencode/commands)
    - Replaces all commands for the given agent_type
    - Stores only command names and descriptions (not content)
    """

    try:
        user_uuid = UUID(user_id)
        # Replace commands entirely; concurrent syncs for the same
        # (user_id, agent_type) must not race the existence check (FLASK-1Q).
        stmt = pg_insert(SlashCommands).values(
            user_id=user_uuid,
            agent_type=request.agent_type,
            commands=request.commands,
            updated_at=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "agent_type"],
            set_={
                "commands": stmt.excluded.commands,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        db.execute(stmt)
        db.commit()

        return SyncCommandsResponse(
            success=True,
            synced_count=len(request.commands),
            agent_type=request.agent_type,
        )
    except SAIntegrityError:
        # *_user_id_fkey -> 401 via app-level handler.
        raise
    except Exception as e:
        logger.error(f"Error syncing commands: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync commands: {str(e)}",
        )


@agent_router.post("/files/sync", response_model=SyncFilesResponse)
def sync_files_endpoint(
    request: SyncFilesRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> SyncFilesResponse:
    """Sync project files from CLI for @ mention autocomplete.

    This endpoint:
    - Receives files from CLI (scanned from project directory)
    - Replaces all files for the given project_path
    - Stores relative file paths for autocomplete
    """

    try:
        user_uuid = UUID(user_id)
        # Replace files entirely; concurrent syncs for the same
        # (user_id, project_path) must not race the existence check (FLASK-21).
        stmt = pg_insert(FileMentions).values(
            user_id=user_uuid,
            project_path=request.project_path,
            files=request.files,
            file_count=len(request.files),
            updated_at=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "project_path"],
            set_={
                "files": stmt.excluded.files,
                "file_count": stmt.excluded.file_count,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        db.execute(stmt)
        db.commit()

        return SyncFilesResponse(
            success=True,
            synced_count=len(request.files),
            project_path=request.project_path,
        )
    except SAIntegrityError:
        # *_user_id_fkey -> 401 via app-level handler.
        raise
    except Exception as e:
        logger.error(f"Error syncing files: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync files: {str(e)}",
        )


@agent_router.get("/agents/instances/{agent_instance_id}/stream")
async def stream_instance_messages(
    request: Request,
    agent_instance_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    last_message_id: UUID | None = None,
) -> StreamingResponse:
    """Stream user messages for a CLI wrapper using Server-Sent Events.

    Listens on ``message_channel_{agent_instance_id}`` and forwards only
    ``sender_type=USER`` message inserts so the wrapper receives new user
    input instantly without polling.  Agent messages (written by the wrapper
    itself) are filtered out to prevent echo loops.
    """
    # Verify the instance belongs to the authenticated agent
    with SessionLocal() as db:
        instance = (
            db.query(AgentInstance)
            .filter(
                AgentInstance.id == agent_instance_id,
                AgentInstance.user_id == user_id,
            )
            .first()
        )
        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent instance not found",
            )

    _TERMINAL_STATUS_VALUES = frozenset(
        s.value
        for s in (
            AgentStatus.COMPLETED,
            AgentStatus.FAILED,
            AgentStatus.KILLED,
            AgentStatus.DISCONNECTED,
            AgentStatus.DELETED,
        )
    )

    async def user_message_generator() -> AsyncGenerator[str, None]:
        channel_name = f"message_channel_{agent_instance_id}"
        last_delivered_message_id: UUID | None = last_message_id

        def _cursor_query() -> list[dict]:
            if last_delivered_message_id is None:
                return []
            try:
                with SessionLocal() as db:
                    return get_user_messages_after_id(
                        db, agent_instance_id, last_delivered_message_id
                    )
            except Exception:
                logger.exception(
                    "SSE: cursor query failed for instance %s", agent_instance_id
                )
                return []

        def _init_cursor() -> UUID | None:
            """Anchor the cursor at the latest existing message on first connect."""
            try:
                with SessionLocal() as db:
                    return get_latest_message_id_for_instance(db, agent_instance_id)
            except Exception:
                logger.exception(
                    "SSE: failed to init cursor for instance %s", agent_instance_id
                )
                return None

        try:
            async with get_hub().subscribe(channel_name) as (
                wake_event,
                signal_queue,
            ):
                loop = asyncio.get_running_loop()
                yield f"event: connected\ndata: {json.dumps({'instance_id': str(agent_instance_id)})}\n\n"
                last_emit_at = loop.time()

                if last_delivered_message_id is None:
                    last_delivered_message_id = await asyncio.to_thread(_init_cursor)

                # Eager catch-up: deliver any messages written between client disconnect
                # and this subscription being established (avoids waiting up to 15s).
                if last_delivered_message_id is not None:
                    catchup = await asyncio.to_thread(_cursor_query)
                    for msg in catchup:
                        last_delivered_message_id = UUID(msg["id"])
                        yield f"event: user_message\ndata: {json.dumps(msg)}\n\n"
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

                    new_messages = await asyncio.to_thread(_cursor_query)
                    for msg in new_messages:
                        last_delivered_message_id = UUID(msg["id"])
                        yield f"event: user_message\ndata: {json.dumps(msg)}\n\n"
                        last_emit_at = loop.time()

                    # Drain signal queue and check for terminal status.
                    should_terminate = False
                    terminate_status: str | None = None
                    for sig_payload in signal_queue.drain_nowait():
                        try:
                            sig_data = json.loads(sig_payload)
                            sig_type = sig_data.get("event_type", "")
                            if (
                                sig_type == "status_update"
                                and sig_data.get("status") in _TERMINAL_STATUS_VALUES
                            ):
                                should_terminate = True
                                terminate_status = sig_data.get("status")
                        except Exception:
                            logger.exception(
                                "SSE: error processing signal event on %s",
                                channel_name,
                            )

                    if should_terminate:
                        yield f"event: terminate\ndata: {json.dumps({'event_type': 'terminate', 'instance_id': str(agent_instance_id), 'status': terminate_status})}\n\n"
                        break

                    # Time-based heartbeat. The previous condition only fired
                    # on a 15s wait_for timeout — but this stream is
                    # USER-filtered, so AGENT-message NOTIFYs constantly set
                    # wake_event while the cursor query returns nothing
                    # visible. The branch was never reached on a busy agent,
                    # the client's sock_read=30s timeout tripped, and the
                    # wrapper logged "Timeout on reading data from socket"
                    # every ~30s. Capping at 10s of true silence keeps us
                    # comfortably under the client window.
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
            logger.exception(
                "stream_instance_messages crashed on channel=%s", channel_name
            )
            raise

    return StreamingResponse(
        user_message_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
