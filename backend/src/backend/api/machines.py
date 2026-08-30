"""Machine and remote session endpoints for web/app clients."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session, attributes

from shared.database import (
    Machine,
    MachineAgentModels,
    MachineSpawnRequest,
    AgentStatus,
)
from shared.database.models import User
from shared.database.session import get_db
from shared.database.agent_instances import create_agent_instance
from shared.websocket import after_commit, build_machine_update

from ..auth.dependencies import get_current_user
from ..broadcast_bridge import post_broadcast
from ..models import (
    MachineAgentModelsResponse,
    MachineListResponse,
    MachineSummary,
    RenameMachineRequest,
    SpawnSessionRequest,
    SpawnSessionResponse,
    SpawnRequestSummary,
)

router = APIRouter(tags=["remote-sessions"])
logger = logging.getLogger(__name__)


def _validated_display_name(raw: str | None) -> str:
    """Trim and validate a machine display name (D15).

    Raises ValueError on an empty/whitespace-only or over-long (>255) name;
    the PATCH endpoint translates that into a 400.
    """
    name = (raw or "").strip()
    if not name:
        raise ValueError("Machine name must not be empty")
    if len(name) > 255:
        raise ValueError("Machine name must be 255 characters or fewer")
    return name


def _get_machine_for_user(db: Session, machine_id: str, user_id: UUID) -> Machine:
    try:
        machine_uuid = UUID(machine_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid machine identifier",
        ) from exc

    machine = (
        db.query(Machine)
        .filter(Machine.id == machine_uuid, Machine.user_id == user_id)
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
    recent_dirs: list[str] = []
    if metadata and isinstance(metadata.get("recent_directories"), list):
        recent_dirs = [str(item) for item in metadata.get("recent_directories", [])]

    return MachineSummary(
        machine_id=str(machine.id),
        display_name=machine.display_name,
        hostname=machine.hostname,
        platform=machine.platform,
        home_dir=machine.home_dir,
        last_heartbeat_at=machine.last_heartbeat_at,
        metadata=metadata,
        recent_directories=recent_dirs[:10],
    )


@router.get("/machines", response_model=MachineListResponse)
def list_machines_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> MachineListResponse:
    machines = (
        db.query(Machine)
        .filter(Machine.user_id == current_user.id)
        .order_by(Machine.created_at.desc())
        .all()
    )

    return MachineListResponse(
        machines=[_machine_summary(machine) for machine in machines]
    )


@router.delete(
    "/machines/{machine_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_machine_endpoint(
    machine_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> Response:
    """Forget a machine (D6). Hard delete: the DB cascades its spawn_requests
    and SET-NULLs its sessions' machine_id (D7), so live sessions survive as
    "machine removed". The machine reappears only if its daemon re-registers.
    """
    machine = _get_machine_for_user(db, machine_id, current_user.id)
    db.delete(machine)
    db.commit()
    logger.info("Machine %s removed by user %s", machine_id, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/machines/{machine_id}", response_model=MachineSummary)
def get_machine_endpoint(
    machine_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> MachineSummary:
    """Fetch one machine by id — the deep-link target opened from the session
    info sheet's "Machine" row (D14)."""
    machine = _get_machine_for_user(db, machine_id, current_user.id)
    return _machine_summary(machine)


@router.get(
    "/machines/{machine_id}/agent-models",
    response_model=MachineAgentModelsResponse,
)
def get_machine_agent_models_endpoint(
    machine_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> MachineAgentModelsResponse:
    """Cached available model lists per agent for a machine, so the new-session
    picker can show real models before a session starts. Populated
    write-on-change from the ACP wrapper's session/new report; empty until an
    ACP agent has run at least once on this machine."""
    machine = _get_machine_for_user(db, machine_id, current_user.id)
    rows = (
        db.query(MachineAgentModels)
        .filter(MachineAgentModels.machine_id == machine.id)
        .all()
    )
    return MachineAgentModelsResponse(
        agent_models={row.agent_type: row.models for row in rows}
    )


@router.patch("/machines/{machine_id}", response_model=MachineSummary)
def rename_machine_endpoint(
    machine_id: str,
    request: RenameMachineRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> MachineSummary:
    """Rename a machine (D15) and broadcast `machine-update` so connected
    clients re-render the new name live."""
    machine = _get_machine_for_user(db, machine_id, current_user.id)
    try:
        machine.display_name = _validated_display_name(request.display_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    machine.updated_at = datetime.now(timezone.utc)

    db.flush()
    summary = _machine_summary(machine)
    # Snapshot the envelope before commit so the after-commit callback closes
    # over plain data, never an expired ORM row (websocket-migration §2.7).
    payload = build_machine_update(machine)
    user_id_str = str(current_user.id)
    room = f"user:{user_id_str}:user-scoped"
    after_commit(db, lambda: post_broadcast(user_id_str, payload, [room]))
    db.commit()
    return summary


@router.post(
    "/machines/{machine_id}/spawn-requests",
    response_model=SpawnSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_spawn_request_endpoint(
    machine_id: str,
    request: SpawnSessionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> SpawnSessionResponse:
    agent_instance_id = uuid4()
    machine = _get_machine_for_user(db, machine_id, current_user.id)
    instance = create_agent_instance(
        db,
        current_user.id,
        agent_name=(request.agent or "claude"),
        instance_id=agent_instance_id,
        name=request.metadata.get("name")
        if isinstance(request.metadata, dict)
        else None,
        instance_metadata={"spawn_starting": True},
        machine_id=machine.id,
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
        requested_by_user_id=current_user.id,
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

    machine.last_heartbeat_at = machine.last_heartbeat_at or datetime.now(timezone.utc)
    machine.updated_at = datetime.now(timezone.utc)

    db.add(spawn_request)
    db.flush()

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

    # Snapshot the id before commit — ORM attribute access is unsafe after
    # commit when expire_on_commit is on (§2.7).
    spawn_request_id_str = str(spawn_request.id)
    db.commit()

    logger.info(
        "Spawn request %s queued for machine %s", spawn_request_id_str, machine_id
    )
    return SpawnSessionResponse(
        request_id=spawn_request_id_str,
        agent_instance_id=str(agent_instance_id),
    )


@router.get(
    "/machines/{machine_id}/spawn-requests/{request_id}",
    response_model=SpawnRequestSummary,
)
def get_spawn_request_endpoint(
    machine_id: str,
    request_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> SpawnRequestSummary:
    """Get details of a specific spawn request."""
    machine = _get_machine_for_user(db, machine_id, current_user.id)

    try:
        request_uuid = UUID(request_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid spawn request identifier",
        ) from exc

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

    return SpawnRequestSummary(
        request_id=str(spawn_request.id),
        machine_id=str(spawn_request.machine_id),
        directory=spawn_request.directory,
        agent=spawn_request.agent,
        status=spawn_request.status,
        message=spawn_request.message,
        agent_instance_id=str(spawn_request.agent_instance_id)
        if spawn_request.agent_instance_id
        else None,
        created_at=spawn_request.created_at,
        claimed_at=spawn_request.claimed_at,
        completed_at=spawn_request.completed_at,
        metadata=spawn_request.request_metadata,
    )
