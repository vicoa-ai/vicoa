"""Bring a session started outside Vicoa into Vicoa (issue #235).

A coding agent run in a terminal, a desktop app or an editor keeps its own
transcript on the machine. The machine daemon (or ``vicoa session import``)
reads that transcript and posts it here, and from then on it is an ordinary
Vicoa session: listed in the sidebar, shareable, and continued with the
existing Resume, which relaunches the agent with its native session handle.

Two endpoints, both agent-facing and owner-only like the rest of this server:

* ``POST /agent-instances/native-lookup`` answers "which of these native
  sessions are already in Vicoa?" so the import list can mark them instead of
  offering a second copy.
* ``POST /agent-instances/import`` creates the session and its history in one
  transaction. It is idempotent per (user, machine, agent, native id): a retry,
  or two devices importing the same session at once, end on the same row.

No column of its own: a native id is found where Resume already reads it. For
Claude that is the instance id itself (Vicoa pins Claude's session id to it);
for every other agent it is the handle key in ``instance_metadata``
(``shared.session_resume.native_handle_keys``).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from protocol.agent_catalog import AGENT_CATALOG
from shared.database.agent_instances import create_agent_instance
from shared.database.enums import AgentStatus, SenderType
from shared.database.models import AgentInstance, Message
from shared.database.project_matching import resolve_or_create_project_id_for_session
from shared.database.session import get_db
from shared.session_resume import native_handle_key, native_handle_keys

from .auth import get_current_user_id
from .routers import _broadcast_instance_update, _resolve_owned_machine_id

logger = logging.getLogger(__name__)

import_router = APIRouter(tags=["imports"])

#: Agents the daemon can read sessions for (``vicoa.local_sessions``). An
#: agent is added here once its source exists and Resume of an imported row has
#: been checked for it; until then its imports are refused.
IMPORTABLE_AGENTS = frozenset({"claude", "codex"})

#: Upper bounds that keep one request sane. A longer session keeps its most
#: recent messages (the daemon trims, and says so in the first message).
MAX_IMPORTED_MESSAGES = 5000
MAX_MESSAGE_CHARS = 32_000
MAX_LOOKUP_IDS = 500
MAX_NAME_CHARS = 255


class ImportedMessage(BaseModel):
    sender: Literal["user", "agent"]
    content: str
    created_at: datetime
    message_metadata: dict[str, Any] | None = None


class ImportSessionRequest(BaseModel):
    machine_id: str
    agent: str
    native_session_id: str = Field(min_length=1, max_length=256)
    project: str = Field(
        min_length=1,
        max_length=4096,
        description="The session's working directory on the machine.",
    )
    home_dir: str | None = None
    name: str | None = None
    source: str | None = Field(
        default=None,
        max_length=100,
        description="Where the native session was started, as the agent recorded it "
        "(Claude `entrypoint`, Codex `originator`).",
    )
    source_label: str | None = Field(default=None, max_length=100)
    started_at: datetime | None = None
    worktree_name: str | None = None
    repo_root: str | None = None
    git_remote_url: str | None = None
    messages: list[ImportedMessage] = Field(
        default_factory=list, max_length=MAX_IMPORTED_MESSAGES
    )


class ImportSessionResponse(BaseModel):
    agent_instance_id: str
    created: bool
    message_count: int


class NativeLookupRequest(BaseModel):
    machine_id: str
    agent: str
    native_session_ids: list[str] = Field(max_length=MAX_LOOKUP_IDS)


class NativeLookupResponse(BaseModel):
    #: native session id -> Vicoa instance id, only for the ids already in Vicoa.
    matches: dict[str, str]


def _agent_label(agent: str) -> str:
    for entry in AGENT_CATALOG["agents"]:
        if entry.get("id") == agent:
            return str(entry.get("label") or agent)
    return agent


def _as_utc(value: datetime) -> datetime:
    """Aware UTC: the messages table stores what every other writer stores."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _lock_native_session(db: Session, user_id: UUID, key_source: str) -> None:
    """Serialize imports of one native session for one user.

    Same transaction-scoped advisory lock as project auto-creation
    (``project_matching._advisory_lock``): the loser blocks until the winner
    commits, then its re-lookup finds the winner's row. No-op off Postgres.
    """
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    digest = hashlib.sha256(f"import:{user_id}:{key_source}".encode()).digest()
    key = int.from_bytes(digest[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})


def find_linked_sessions(
    db: Session,
    user_id: UUID,
    machine_id: UUID,
    agent: str,
    native_ids: list[str],
) -> dict[str, str]:
    """Map each native id that already has a live Vicoa session to its id.

    Claude: the instance id *is* the native id, so this is a primary-key read
    and needs no machine filter (it also catches old rows with no machine link).
    Other agents: the handle keys Resume reads, on this user's sessions on this
    machine. A deleted session doesn't count, so it can be imported again.
    """
    wanted = {i for i in native_ids if i}
    if not wanted:
        return {}

    if agent == "claude":
        uuids: list[UUID] = []
        for raw in wanted:
            try:
                uuids.append(UUID(raw))
            except ValueError:
                continue
        if not uuids:
            return {}
        rows = (
            db.query(AgentInstance.id)
            .filter(
                AgentInstance.user_id == user_id,
                AgentInstance.status != AgentStatus.DELETED,
                AgentInstance.id.in_(uuids),
            )
            .all()
        )
        return {str(row.id): str(row.id) for row in rows}

    keys = native_handle_keys(agent)
    if not keys:
        return {}
    rows = (
        db.query(AgentInstance.id, AgentInstance.instance_metadata)
        .filter(
            AgentInstance.user_id == user_id,
            AgentInstance.machine_id == machine_id,
            AgentInstance.status != AgentStatus.DELETED,
            or_(*(AgentInstance.instance_metadata[k].astext.in_(wanted) for k in keys)),
        )
        .all()
    )
    matches: dict[str, str] = {}
    for row in rows:
        metadata = row.instance_metadata or {}
        for key in keys:
            value = metadata.get(key)
            if isinstance(value, str) and value in wanted:
                matches.setdefault(value, str(row.id))
    return matches


def _owned_machine_or_404(db: Session, raw_machine_id: str, user_id: str) -> UUID:
    machine_uuid = _resolve_owned_machine_id(db, raw_machine_id, user_id)
    if machine_uuid is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found"
        )
    return machine_uuid


@import_router.post(
    "/agent-instances/native-lookup", response_model=NativeLookupResponse
)
def native_lookup_endpoint(
    request: NativeLookupRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> NativeLookupResponse:
    """Which of these native sessions on this machine are already in Vicoa."""
    machine_uuid = _owned_machine_or_404(db, request.machine_id, user_id)
    matches = find_linked_sessions(
        db,
        UUID(user_id),
        machine_uuid,
        request.agent.strip().lower(),
        request.native_session_ids,
    )
    return NativeLookupResponse(matches=matches)


def _ordered_messages(
    messages: list[ImportedMessage],
) -> list[tuple[ImportedMessage, datetime]]:
    """Sort by time and make the times strictly increasing.

    The transcript is ordered by ``created_at``; two rows with the same
    timestamp would come back in arbitrary order, so ties are nudged apart by
    a microsecond while keeping the order they were sent in.
    """
    indexed = sorted(
        enumerate(messages), key=lambda pair: (_as_utc(pair[1].created_at), pair[0])
    )
    ordered: list[tuple[ImportedMessage, datetime]] = []
    previous: datetime | None = None
    for _, message in indexed:
        at = _as_utc(message.created_at)
        if previous is not None and at <= previous:
            at = previous + timedelta(microseconds=1)
        ordered.append((message, at))
        previous = at
    return ordered


@import_router.post(
    "/agent-instances/import",
    response_model=ImportSessionResponse,
    status_code=status.HTTP_200_OK,
)
def import_session_endpoint(
    request: ImportSessionRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> ImportSessionResponse:
    """Create a Vicoa session for a native session, with its history."""
    agent = request.agent.strip().lower()
    if agent not in IMPORTABLE_AGENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Importing {agent} sessions isn't supported yet",
        )
    native_id = request.native_session_id.strip()
    user_uuid = UUID(user_id)
    machine_uuid = _owned_machine_or_404(db, request.machine_id, user_id)

    instance_uuid: UUID | None = None
    if agent == "claude":
        # Resume names Claude's transcript by the instance id, so the row must
        # carry the native id as its own.
        try:
            instance_uuid = UUID(native_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A Claude session id is a UUID",
            ) from exc

    _lock_native_session(db, user_uuid, f"{machine_uuid}:{agent}:{native_id}")
    existing = find_linked_sessions(db, user_uuid, machine_uuid, agent, [native_id])
    if native_id in existing:
        db.rollback()  # releases the advisory lock
        return ImportSessionResponse(
            agent_instance_id=existing[native_id], created=False, message_count=0
        )
    deleted_row: AgentInstance | None = None
    if instance_uuid is not None:
        holder = db.get(AgentInstance, instance_uuid)
        if holder is not None and holder.user_id != user_uuid:
            # Another account on the same machine already imported it.
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This session can't be imported into this account",
            )
        # A live row of this user was matched above, so a remaining holder is
        # one they deleted: its messages are gone and the row only keeps the
        # id. Reuse it rather than refuse the import forever.
        deleted_row = holder

    ordered = _ordered_messages(request.messages)
    started_at = (
        _as_utc(request.started_at)
        if request.started_at is not None
        else (ordered[0][1] if ordered else datetime.now(timezone.utc))
    )
    imported_from: dict[str, Any] = {
        "agent": agent,
        "native_session_id": native_id,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    if request.source:
        imported_from["source"] = request.source
    if request.source_label:
        imported_from["source_label"] = request.source_label
    # `source: "app"` because from here on the daemon's headless runner drives
    # the session (Resume); clients key permission-mode behaviour off it. Where
    # the session came from lives in `imported_from`.
    metadata: dict[str, Any] = {"source": "app", "imported_from": imported_from}
    handle_key = native_handle_key(agent)
    if handle_key is not None:
        metadata[handle_key] = native_id
    for key in ("worktree_name", "repo_root", "git_remote_url"):
        value = getattr(request, key)
        if value:
            metadata[key] = value

    name = (request.name or "").strip() or None
    if name and len(name) > MAX_NAME_CHARS:
        name = name[: MAX_NAME_CHARS - 1].rstrip() + "…"

    project_id = resolve_or_create_project_id_for_session(
        db,
        user_uuid,
        machine_uuid,
        request.project,
        git_remote_url=request.git_remote_url,
        repo_root=request.repo_root,
        home_dir=request.home_dir,
    )
    # Idle with no agent attached: shown as not running, with Resume.
    # (COMPLETED would file it under Archived.)
    initial_status = AgentStatus.AWAITING_INPUT
    if deleted_row is not None:
        instance = deleted_row
        instance.name = name
        instance.instance_metadata = metadata
        instance.project = request.project
        instance.project_id = project_id
        instance.home_dir = request.home_dir
        instance.machine_id = machine_uuid
        instance.status = initial_status
        instance.session_config = {"agent": agent}
        instance.ended_at = None
        instance.last_heartbeat_at = None
        instance.last_read_message_id = None
        instance.pinned_at = None
        instance.task_id = None
    else:
        instance = create_agent_instance(
            db,
            user_uuid,
            agent_name=_agent_label(agent),
            instance_id=instance_uuid,
            name=name,
            instance_metadata=metadata,
            project=request.project,
            project_id=project_id,
            home_dir=request.home_dir,
            machine_id=machine_uuid,
            status=initial_status,
            session_config={"agent": agent},
        )
    instance.started_at = started_at

    rows = [
        Message(
            agent_instance_id=instance.id,
            sender_type=SenderType.USER
            if message.sender == "user"
            else SenderType.AGENT,
            content=message.content[:MAX_MESSAGE_CHARS],
            created_at=at,
            requires_user_input=False,
            message_metadata=message.message_metadata or None,
        )
        for message, at in ordered
    ]
    if rows:
        db.add_all(rows)
        db.flush()
        # Everything imported has been "read": none of the user's old prompts
        # may come back as a new one for the agent once the session resumes.
        instance.last_read_message_id = rows[-1].id

    _broadcast_instance_update(db, instance, user_id, created=True)
    db.commit()
    logger.info(
        "imported %s session %s as %s (%d messages)",
        agent,
        native_id,
        instance.id,
        len(rows),
    )
    return ImportSessionResponse(
        agent_instance_id=str(instance.id), created=True, message_count=len(rows)
    )
