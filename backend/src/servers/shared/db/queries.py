import asyncio
import hashlib
import json
import time
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from shared.database import (
    AgentInstance,
    AgentStatus,
    Machine,
    MachineAgentModels,
    Message,
    MessageAttachment,
    SenderType,
    UserAgent,
)
from shared.websocket import (
    build_instance_update,
    build_machine_update,
    build_new_message_update,
)
from shared.database.session import SessionLocal
from shared.database.utils import sanitize_git_diff
from shared.llms import generate_conversation_title
from sqlalchemy import case, cast, func, or_, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, attributes
from fastmcp import Context

logger = logging.getLogger(__name__)


def create_or_get_user_agent(db: Session, name: str, user_id: str) -> UserAgent:
    """Create or get a non-deleted user agent by name for a specific user"""
    # Normalize name to lowercase for consistent storage
    normalized_name = name.lower()

    # Only look for non-deleted user agents
    user_agent = (
        db.query(UserAgent)
        .filter(
            UserAgent.name == normalized_name,
            UserAgent.user_id == UUID(user_id),
            UserAgent.is_deleted.is_(False),
        )
        .first()
    )
    if not user_agent:
        user_agent = UserAgent(
            name=normalized_name,
            user_id=UUID(user_id),
            is_active=True,
            is_deleted=False,  # Explicitly set to False for new agents
        )
        db.add(user_agent)
        db.flush()  # Flush to get the user_agent ID
    return user_agent


def create_agent_instance(
    db: Session, user_agent_id: UUID | None, user_id: str
) -> AgentInstance:
    """Create a new agent instance"""
    instance = AgentInstance(
        user_agent_id=user_agent_id, user_id=UUID(user_id), status=AgentStatus.ACTIVE
    )
    db.add(instance)
    return instance


def get_agent_instance(db: Session, instance_id: str | UUID) -> AgentInstance | None:
    """Get an agent instance by ID"""
    return db.query(AgentInstance).filter(AgentInstance.id == instance_id).first()


def get_instance_status_by_id(db: Session, instance_id: UUID) -> str | None:
    """Return the current status string for an instance, or None if not found.

    No user-scoping — callers must have already verified ownership.
    Used by SSE generators to detect terminal states.
    """
    inst = (
        db.query(AgentInstance.status).filter(AgentInstance.id == instance_id).first()
    )
    if inst is None:
        return None
    s = inst.status
    return s.value if hasattr(s, "value") else str(s)


def get_latest_message_id_for_instance(
    db: Session,
    instance_id: UUID,
) -> UUID | None:
    """Return the ID of the most recent message for instance_id, or None.

    No user-scoping — callers must have already verified ownership.
    Used by SSE generators to initialise the cursor when the client connects
    without a prior ``last_message_id``.
    """
    row = (
        db.query(Message.id)
        .filter(Message.agent_instance_id == instance_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .first()
    )
    return row[0] if row else None


CATCHUP_MAX_USER_MESSAGES = 500


def get_user_messages_after_id(
    db: Session,
    instance_id: UUID,
    after_message_id: UUID,
) -> list[dict]:
    """Return USER messages newer than after_message_id for the CLI-wrapper SSE stream.

    Uses (created_at, id) cursor ordering to handle same-millisecond writes.
    Returns plain dicts detached from the session. No user-scoping — callers
    must have already verified ownership of the instance.
    """
    from sqlalchemy import or_

    cursor = (
        db.query(Message.created_at, Message.id)
        .filter(
            Message.id == after_message_id,
            Message.agent_instance_id == instance_id,
        )
        .first()
    )
    if not cursor:
        return []

    cursor_ts, cursor_id = cursor.created_at, cursor.id

    msgs = (
        db.query(Message)
        .filter(
            Message.agent_instance_id == instance_id,
            Message.sender_type == SenderType.USER,
            or_(
                Message.created_at > cursor_ts,
                (Message.created_at == cursor_ts) & (Message.id > cursor_id),
            ),
        )
        .order_by(Message.created_at.asc(), Message.id.asc())
        .limit(CATCHUP_MAX_USER_MESSAGES)
        .all()
    )
    return [
        {
            "id": str(m.id),
            "content": m.content,
            "sender_type": m.sender_type.value,
            "agent_instance_id": str(m.agent_instance_id),
            "created_at": m.created_at.isoformat() + "Z",
            "requires_user_input": m.requires_user_input,
        }
        for m in msgs
    ]


# Catch-up page size for `fetch_messages_request` (websocket-migration §2.6).
WS_FETCH_PAGE_LIMIT = 200
# The reconnect watermark re-fetches `created_at >= watermark - safety_window`
# because live frames arrive in commit order, which can lag `created_at` order
# (§2.6). Sized to the DB `statement_timeout` (session.py: 30s) — no message's
# create-to-commit gap can exceed it, so the window covers every inversion.
WS_FETCH_SAFETY_WINDOW = timedelta(seconds=30)


@dataclass
class FetchMessagesResult:
    """Outcome of a `fetch_messages_request` catch-up query.

    `rows` are message bodies in the exact `new-message` live-frame shape so the
    client merges catch-up and live updates by id. `resync_reason`, when set,
    means the cursor could not be served and the client must drop local state
    and re-fetch without a watermark (§2.6 resync escape hatch).
    """

    rows: list[dict]
    has_more: bool
    resync_reason: str | None = None


def fetch_session_messages(
    db: Session,
    instance_id: UUID,
    after: dict | None,
    *,
    include_agent_messages: bool = False,
    page_limit: int = WS_FETCH_PAGE_LIMIT,
) -> FetchMessagesResult:
    """Catch-up fetch of messages for a session (websocket-migration §2.6).

    `after` is the client's cursor: `{"created_at": iso, "id": uuid|None}`.
    With no `id` it is a reconnect watermark — the query re-fetches
    `created_at >= watermark - safety_window` and the client dedupes the
    overlap by id. With an `id` it is a pagination cursor continuing a
    `has_more` response — strict `(created_at, id) >`, no window re-fetch.
    No user-scoping here: the caller verifies instance ownership.

    `include_agent_messages` reflects the caller's scope: session-scoped
    (CLI wrapper) defaults to USER-only since the wrapper *produces* the
    AGENT messages and doesn't need them echoed back; user-scoped clients
    (web / mobile chat) need both to render the full conversation. Live
    `new-message` broadcasts already carry both — without this opt-in, a
    reconnect catch-up silently loses every AGENT message written during
    the disconnect window.
    """
    query = db.query(Message).filter(Message.agent_instance_id == instance_id)
    if not include_agent_messages:
        query = query.filter(Message.sender_type == SenderType.USER)

    if not after or after.get("created_at") is None:
        # No client watermark. User-scoped clients want the tail of history
        # (resync escape hatch §2.6). Session-scoped clients (CLI wrapper)
        # cannot replay already-processed user messages: a cold start or
        # `--resume` carries no in-memory watermark, but the wrapper has
        # been advancing `instance.last_read_message_id` server-side every
        # time it produced an agent reply. Falling back to that cursor
        # restores the legacy `/messages/pending` semantics — without it,
        # the wrapper would inject the entire user-message history into
        # the PTY on every reconnect, freezing Claude under the backlog.
        if not include_agent_messages:
            instance_last_read = (
                db.query(AgentInstance.last_read_message_id)
                .filter(AgentInstance.id == instance_id)
                .scalar()
            )
            if instance_last_read is not None:
                last_read_ts = (
                    db.query(Message.created_at)
                    .filter(Message.id == instance_last_read)
                    .scalar()
                )
                if last_read_ts is not None:
                    query = query.filter(Message.created_at > last_read_ts)
    elif after.get("id") is None:
        # Reconnect watermark: created_at only, widened by the safety window.
        watermark = datetime.fromisoformat(after["created_at"])
        query = query.filter(Message.created_at >= watermark - WS_FETCH_SAFETY_WINDOW)
    else:
        # Pagination cursor: strict (created_at, id) >. The cursor message is
        # looked up for its authoritative created_at; if it no longer exists
        # the client's catch-up state cannot be served — request a resync.
        cursor_id = UUID(after["id"])
        cursor = (
            db.query(Message.created_at)
            .filter(
                Message.id == cursor_id,
                Message.agent_instance_id == instance_id,
            )
            .first()
        )
        if cursor is None:
            return FetchMessagesResult(
                rows=[], has_more=False, resync_reason="missing_history"
            )
        cursor_ts = cursor[0]
        query = query.filter(
            or_(
                Message.created_at > cursor_ts,
                (Message.created_at == cursor_ts) & (Message.id > cursor_id),
            )
        )

    msgs = (
        query.order_by(Message.created_at.asc(), Message.id.asc())
        .limit(page_limit + 1)
        .all()
    )

    has_more = len(msgs) > page_limit
    rows = [build_new_message_update(m)["body"] for m in msgs[:page_limit]]
    return FetchMessagesResult(rows=rows, has_more=has_more)


def fetch_user_instances(
    db: Session, user_id: UUID, updated_after: str | None
) -> list[dict]:
    """Catch-up fetch of a user's agent instances (websocket-migration §2.6).

    `updated_after` is the client's `updated_at` watermark; the query widens it
    by the safety window because `updated_at` is set at flush time and commit
    order can lag it. The mutable-entity merge (replace-if-newer) makes the
    re-fetched overlap harmless. `None` = full fetch. Rows are envelope bodies.
    """
    query = db.query(AgentInstance).filter(AgentInstance.user_id == user_id)
    if updated_after is not None:
        floor = datetime.fromisoformat(updated_after) - WS_FETCH_SAFETY_WINDOW
        query = query.filter(AgentInstance.updated_at >= floor)
    instances = query.order_by(AgentInstance.updated_at.asc()).all()
    return [build_instance_update(inst)["body"] for inst in instances]


def fetch_user_machines(
    db: Session, user_id: UUID, updated_after: str | None
) -> list[dict]:
    """Catch-up fetch of a user's machines (websocket-migration §2.6).

    Same `updated_at` watermark + safety window as `fetch_user_instances`.
    """
    query = db.query(Machine).filter(Machine.user_id == user_id)
    if updated_after is not None:
        floor = datetime.fromisoformat(updated_after) - WS_FETCH_SAFETY_WINDOW
        query = query.filter(Machine.updated_at >= floor)
    machines = query.order_by(Machine.updated_at.asc()).all()
    return [build_machine_update(machine)["body"] for machine in machines]


def _normalize_agent_models(models: object) -> list[dict]:
    """Coerce a reported model list to ``[{"id","label"}]``, dropping junk."""
    out: list[dict] = []
    if not isinstance(models, list):
        return out
    for m in models:
        if isinstance(m, dict) and m.get("id"):
            out.append({"id": str(m["id"]), "label": str(m.get("label") or m["id"])})
    return out


def _agent_models_hash(normalized: list[dict]) -> str:
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upsert_machine_agent_models(
    db: Session,
    *,
    machine_id: UUID,
    agent_type: str,
    user_id: UUID,
    models: object,
) -> bool:
    """Cache an agent's available models for a machine, write-on-change.

    Skips empty lists (never clobbers a known-good list with nothing) and skips
    writes when the list is unchanged (the common case — the list is stable
    across sessions). Returns True iff a row was inserted/updated.
    """
    normalized = _normalize_agent_models(models)
    if not normalized:
        return False
    new_hash = _agent_models_hash(normalized)
    row = db.get(MachineAgentModels, (machine_id, agent_type))
    if row is not None and row.models_hash == new_hash:
        return False
    if row is None:
        db.add(
            MachineAgentModels(
                machine_id=machine_id,
                agent_type=agent_type,
                user_id=user_id,
                models=normalized,
                models_hash=new_hash,
            )
        )
    else:
        row.models = normalized
        row.models_hash = new_hash
        row.user_id = user_id
    return True


def push_recent_directory_after_spawn(
    user_id: str, machine_id: str, directory: str
) -> None:
    """Push `directory` to the front of the machine's `recent_directories`.

    Opens its own session: callers are RPC / HTTP handlers that don't already
    have one, and decoupling this side-effect write from the request
    transaction means a failed update here can't roll back the spawn itself.
    Capped at 10 entries to bound `machine_metadata` size.
    """
    try:
        owner_uuid = UUID(user_id)
        machine_uuid = UUID(machine_id)
    except (ValueError, TypeError):
        return
    with SessionLocal() as db:
        machine = (
            db.query(Machine)
            .filter(Machine.id == machine_uuid, Machine.user_id == owner_uuid)
            .first()
        )
        if machine is None:
            return
        metadata = (
            machine.machine_metadata
            if isinstance(machine.machine_metadata, dict)
            else {}
        ) or {}
        recent_dirs: list[str] = []
        if isinstance(metadata.get("recent_directories"), list):
            recent_dirs = [str(item) for item in metadata["recent_directories"]]
        recent_dirs = [directory] + [p for p in recent_dirs if p != directory]
        metadata["recent_directories"] = recent_dirs[:10]
        machine.machine_metadata = metadata
        attributes.flag_modified(machine, "machine_metadata")
        db.commit()


def get_or_create_agent_instance(
    db: Session,
    agent_instance_id: str,
    user_id: str,
    agent_type: str | None = None,
) -> AgentInstance:
    """Get an existing agent instance or create a new one.

    Args:
        db: Database session
        agent_instance_id: Agent instance ID (always required)
        user_id: User ID requesting access
        agent_type: Agent type name (required only when creating new instance)

    Returns:
        The agent instance (existing or newly created)

    Raises:
        ValueError: If instance not found, user doesn't have access, or agent_type missing when creating
    """
    # Try to get existing instance
    instance = get_agent_instance(db, agent_instance_id)

    if instance:
        # Validate access to existing instance
        if str(instance.user_id) != user_id:
            raise ValueError(
                "Access denied. Agent instance does not belong to authenticated user."
            )
        return instance
    else:
        # Create new instance with the provided ID
        if not agent_type:
            raise ValueError("agent_type is required when creating new instance")

        agent_type_obj = create_or_get_user_agent(db, agent_type, user_id)

        # Create instance with the specific ID
        instance = AgentInstance(
            id=UUID(agent_instance_id),
            user_agent_id=agent_type_obj.id,
            user_id=UUID(user_id),
            status=AgentStatus.ACTIVE,
        )
        db.add(instance)
        db.flush()  # Flush to ensure the instance is in the session with its ID
        return instance


def update_session_title_if_needed(
    db: Session,
    instance_id: UUID,
    user_message: str,
) -> None:
    """
    Update the session title if it's NULL by generating a title from the user message.

    This function:
    - Checks if the instance name is NULL
    - If NULL, generates a title using the LLM
    - Updates the instance name in the database
    - Handles errors gracefully

    Args:
        db: Database session
        instance_id: Agent instance ID
        user_message: The user's message content
    """
    try:
        # Get the instance and check if name is already set
        instance = (
            db.query(AgentInstance).filter(AgentInstance.id == instance_id).first()
        )
        if not instance:
            logger.warning(f"Instance {instance_id} not found for title generation")
            return

        if instance.name is not None:
            logger.debug(
                f"Instance {instance_id} already has a name, skipping title generation"
            )
            return

        # Generate the title using the LLM utility
        title = generate_conversation_title(user_message)

        if title:
            instance.name = title
            db.commit()
            logger.info(f"Updated instance {instance_id} with title: {title}")
        else:
            logger.debug(f"No title generated for instance {instance_id}")

    except Exception as e:
        logger.error(
            f"Failed to update session title for instance {instance_id}: {str(e)}"
        )
        try:
            db.rollback()
        except Exception:
            pass


def end_session(db: Session, agent_instance_id: str, user_id: str) -> tuple[str, str]:
    """End an agent session by marking it as completed.

    Args:
        db: Database session
        agent_instance_id: Agent instance ID to end
        user_id: Authenticated user ID

    Returns:
        Tuple of (agent_instance_id, final_status)
    """
    instance = get_or_create_agent_instance(db, agent_instance_id, user_id)

    # Don't overwrite DELETED status
    if instance.status != AgentStatus.DELETED:
        instance.status = AgentStatus.COMPLETED
        instance.ended_at = datetime.now(timezone.utc)
        instance.last_heartbeat_at = datetime.now(timezone.utc)

    return str(instance.id), instance.status.value


def create_agent_message(
    db: Session,
    instance_id: UUID,
    content: str,
    requires_user_input: bool = False,
    message_metadata: dict | None = None,
) -> Message:
    """Create a new agent message without committing"""
    instance = db.query(AgentInstance).filter(AgentInstance.id == instance_id).first()
    if instance and instance.status not in (AgentStatus.COMPLETED, AgentStatus.DELETED):
        if requires_user_input:
            instance.status = AgentStatus.AWAITING_INPUT
        else:
            instance.status = AgentStatus.ACTIVE
        # Stamp heartbeat for any agent activity
        instance.last_heartbeat_at = datetime.now(timezone.utc)

    message = Message(
        agent_instance_id=instance_id,
        sender_type=SenderType.AGENT,
        content=content,
        requires_user_input=requires_user_input,
        message_metadata=message_metadata,
    )
    db.add(message)
    db.flush()  # Flush to get the message ID

    # Update last read message
    if instance:
        instance.last_read_message_id = message.id

    return message


async def wait_for_answer(
    db: Session,
    question_id: UUID,
    timeout_seconds: int = 86400,  # 24 hours default
    tool_context: Context | None = None,
) -> str | None:
    """Wait for an answer to a question using polling"""
    start_time = time.time()
    last_progress_report = start_time
    total_minutes = timeout_seconds // 60

    # Get the question message
    question = db.query(Message).filter(Message.id == question_id).first()
    if not question or not question.requires_user_input:
        return None

    while time.time() - start_time < timeout_seconds:
        # Check if agent has moved on (last read message changed)
        instance = (
            db.query(AgentInstance)
            .filter(AgentInstance.id == question.agent_instance_id)
            .first()
        )

        # If last_read_message_id has changed from our question, agent has moved on
        if instance and instance.last_read_message_id != question_id:
            return None

        # Check for a user message after this question
        answer = (
            db.query(Message)
            .filter(
                Message.agent_instance_id == question.agent_instance_id,
                Message.sender_type == SenderType.USER,
                Message.created_at > question.created_at,
            )
            .order_by(Message.created_at)
            .first()
        )

        if answer:
            # Update last read message to this answer
            if instance:
                instance.last_read_message_id = answer.id

            if tool_context:
                await tool_context.report_progress(total_minutes, total_minutes)

            return answer.content

        # Report progress every minute if tool_context is provided
        current_time = time.time()
        if tool_context and (current_time - last_progress_report) >= 60:
            elapsed_minutes = int((current_time - start_time) / 60)
            await tool_context.report_progress(elapsed_minutes, total_minutes)
            last_progress_report = current_time

        await asyncio.sleep(1)

    return None


def get_attachment_for_agent(
    db: Session, attachment_id: UUID, user_id: UUID
) -> MessageAttachment | None:
    """Fetch an attachment an agent process may read, scoped to its user.

    Allowed when the agent's user uploaded it, or when it belongs to an
    instance that user owns (shared-access senders upload into the owner's
    instance, and the owner's agent must be able to read those).
    """
    attachment = (
        db.query(MessageAttachment)
        .filter(MessageAttachment.id == attachment_id)
        .first()
    )
    if not attachment:
        return None
    if attachment.user_id == user_id:
        return attachment
    instance = (
        db.query(AgentInstance)
        .filter(AgentInstance.id == attachment.agent_instance_id)
        .first()
    )
    if instance and instance.user_id == user_id:
        return attachment
    return None


def get_queued_user_messages(
    db: Session, instance_id: UUID, last_read_message_id: UUID | None = None
) -> list[Message] | None:
    """Get all user messages since the agent last read them.

    Args:
        db: Database session
        instance_id: Agent instance ID
        last_read_message_id: The message ID the agent last read (optional)

    Returns:
        - None if last_read_message_id doesn't match the instance's current last_read_message_id
        - Empty list if no new messages
        - List of messages if there are new user messages
    """
    # Get the agent instance to check last read message
    instance = db.query(AgentInstance).filter(AgentInstance.id == instance_id).first()
    if not instance:
        return []

    if (
        last_read_message_id is not None
        and instance.last_read_message_id != last_read_message_id
    ):
        return None

    # If no last read message, get all user messages
    if not instance.last_read_message_id:
        messages = (
            db.query(Message)
            .filter(
                Message.agent_instance_id == instance_id,
                Message.sender_type == SenderType.USER,
            )
            .order_by(Message.created_at)
            .all()
        )
    else:
        last_read_message = (
            db.query(Message)
            .filter(Message.id == instance.last_read_message_id)
            .first()
        )

        if not last_read_message:
            return []

        # Get all user messages after the last read message
        messages = (
            db.query(Message)
            .filter(
                Message.agent_instance_id == instance_id,
                Message.sender_type == SenderType.USER,
                Message.created_at > last_read_message.created_at,
            )
            .order_by(Message.created_at)
            .all()
        )

    # Update last_read_message_id if we have messages
    # This ensures subsequent polls don't return the same messages
    if messages:
        instance.last_read_message_id = messages[-1].id

    return messages


def mark_message_consumed(db: Session, message_id: UUID) -> Message | None:
    """Stamp `message_metadata["queue"]` as consumed, unless already cancelled.

    Server-side `jsonb_set` so concurrent writers never clobber each other's
    metadata keys outside `queue`. Skips the update (via the WHERE clause)
    when `queue.status` is already `"cancelled"` — a race between the user
    cancelling a queued message and the agent picking it up must leave the
    cancellation as the terminal state.

    `message_metadata` defaults to Python `None`, and this JSONB column does
    not set `none_as_null=True`, so "no metadata yet" is stored as the JSON
    scalar `null`, not SQL NULL — `coalesce()` alone does not catch that.
    `jsonb_typeof(...) == "object"` is the guard that works for both SQL NULL
    and JSON null (and any other non-object shape), falling back to `{}`
    before `jsonb_set` writes the `queue` key.

    Returns the refreshed row, or None if no message has this id.
    """
    now = datetime.now(timezone.utc).isoformat()
    stmt = (
        update(Message)
        .where(
            Message.id == message_id,
            Message.message_metadata[("queue", "status")].astext.is_distinct_from(
                "cancelled"
            ),
        )
        .values(
            message_metadata=func.jsonb_set(
                case(
                    (
                        func.jsonb_typeof(Message.message_metadata) == "object",
                        Message.message_metadata,
                    ),
                    else_=cast({}, JSONB),
                ),
                "{queue}",
                cast({"status": "consumed", "consumed_at": now}, JSONB),
            )
        )
    )
    db.execute(stmt)
    db.flush()
    return db.query(Message).filter(Message.id == message_id).first()


async def send_agent_message(
    db: Session,
    agent_instance_id: str,
    content: str,
    user_id: str,
    agent_type: str | None = None,
    requires_user_input: bool = False,
    git_diff: str | None = None,
    message_metadata: dict | None = None,
) -> tuple[str, str, list[Message]]:
    """High-level function to send an agent message and get queued user messages.

    This combines the common pattern of:
    1. Getting or creating an agent instance
    2. Validating access (if existing instance)
    3. Creating a message
    4. Updating git diff if provided
    5. Getting any queued user messages

    Args:
        db: Database session
        agent_instance_id: Agent instance ID (pass None to create new)
        content: Message content
        user_id: Authenticated user ID
        agent_type: Type of agent (required if creating new instance)
        requires_user_input: Whether this is a question requiring response
        git_diff: Optional git diff to update on the instance
        message_metadata: Optional metadata for the message

    Returns:
        Tuple of (agent_instance_id, message_id, list of queued user message contents)
    """
    # Get or create instance using the unified function
    instance = get_or_create_agent_instance(db, agent_instance_id, user_id, agent_type)

    # Update git diff if provided (but don't commit yet)
    if git_diff is not None:
        sanitized_diff = sanitize_git_diff(git_diff)
        if sanitized_diff is not None:  # Allow empty string (cleared diff)
            instance.git_diff = sanitized_diff
        else:
            logger.warning(
                f"Invalid git diff format for instance {instance.id}, skipping git diff update"
            )

    queued_messages = get_queued_user_messages(
        db, instance.id, instance.last_read_message_id
    )

    # Create the message (this will update last_read_message_id)
    message = create_agent_message(
        db=db,
        instance_id=instance.id,
        content=content,
        requires_user_input=requires_user_input,
        message_metadata=message_metadata,
    )

    # Handle the None case (shouldn't happen here since we just created the message)
    if queued_messages is None:
        queued_messages = []

    return str(instance.id), str(message.id), queued_messages


def create_user_message(
    db: Session,
    agent_instance_id: str,
    content: str,
    user_id: str,
    mark_as_read: bool = True,
) -> dict:
    """Create a user message for an agent instance.

    Args:
        db: Database session
        agent_instance_id: Agent instance ID to send the message to
        content: Message content
        user_id: Authenticated user ID
        mark_as_read: Whether to update last_read_message_id (default: True)

    Returns:
        Dictionary with message details:
        - id: Message ID
        - content: Message content
        - sender_type: "user"
        - created_at: Creation timestamp
        - requires_user_input: False
        - marked_as_read: Whether the message was marked as read
        - instance_id: The agent instance ID

    Raises:
        ValueError: If instance not found or user doesn't have access
    """
    instance = get_agent_instance(db, agent_instance_id)
    if not instance:
        raise ValueError("Agent instance not found")

    if str(instance.user_id) != user_id:
        raise ValueError("Agent instance not found")

    # Create the user message
    message = Message(
        agent_instance_id=UUID(agent_instance_id),
        sender_type=SenderType.USER,
        content=content,
        requires_user_input=False,
    )
    db.add(message)
    db.flush()  # Get the message ID
    db.refresh(message)  # Get database-computed values like created_at

    # Only reactivate if not in terminal state (DELETED)
    # It is ok to reactivate COMPLETED instances
    if instance.status != AgentStatus.DELETED:
        instance.status = AgentStatus.ACTIVE

    # Update last_read_message_id if requested
    if mark_as_read:
        instance.last_read_message_id = message.id

    # Trigger webhook if previous agent message was waiting for response
    # TODO: do this in a background task
    trigger_webhook_for_user_response(
        db=db,
        agent_instance_id=agent_instance_id,
        user_message_content=content,
        user_message_id=str(message.id),
        user_id=user_id,
    )

    return {
        "id": str(message.id),
        "content": message.content,
        "sender_type": message.sender_type.value,
        "created_at": message.created_at,
        "requires_user_input": message.requires_user_input,
        "marked_as_read": mark_as_read,
        "instance_id": agent_instance_id,
    }


def trigger_webhook_for_user_response(
    db: Session,
    agent_instance_id: UUID | str,
    user_message_content: str,
    user_message_id: str,
    user_id: str,
) -> None:
    """Trigger webhook if the last agent message was waiting for user input.

    This function checks if the previous agent message has a webhook URL in its
    metadata and triggers it with the user's response.
    """
    # Convert to UUID if string
    if isinstance(agent_instance_id, str):
        agent_instance_id = UUID(agent_instance_id)

    # Find the last agent message that requires user input
    last_agent_message = (
        db.query(Message)
        .filter(
            Message.agent_instance_id == agent_instance_id,
            Message.sender_type == SenderType.AGENT,
            Message.requires_user_input,
        )
        .order_by(Message.created_at.desc())
        .first()
    )

    if not last_agent_message:
        return

    # Check if it has a webhook URL in metadata
    if not last_agent_message.message_metadata:
        return

    webhook_url = last_agent_message.message_metadata.get("webhook_url")
    if not webhook_url:
        return

    # Check if webhook was already triggered
    if last_agent_message.message_metadata.get("webhook_triggered"):
        logger.info(f"Webhook already triggered for message {last_agent_message.id}")
        return

    # Prepare webhook payload
    webhook_payload = {
        "user_message": user_message_content,
        "user_id": user_id,
        "message_id": user_message_id,
        "agent_instance_id": str(agent_instance_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # TODO: call this in the background so user message doesn't hang
    try:
        with httpx.Client() as client:
            response = client.post(
                webhook_url,
                json=webhook_payload,
                timeout=10.0,  # 10 second timeout
                headers={
                    "Content-Type": "application/json",
                    "X-Vicoa-Webhook": "true",
                },
            )

            if response.status_code >= 200 and response.status_code < 300:
                logger.info(
                    f"Successfully triggered webhook for agent instance {agent_instance_id}"
                )
                # Mark webhook as triggered to prevent multiple triggers
                if not last_agent_message.message_metadata:
                    last_agent_message.message_metadata = {}
                last_agent_message.message_metadata["webhook_triggered"] = True
                last_agent_message.message_metadata["webhook_response_status"] = (
                    response.status_code
                )
            else:
                logger.warning(
                    f"Webhook returned non-success status {response.status_code} "
                    f"for agent instance {agent_instance_id}"
                )
    except Exception as e:
        logger.error(
            f"Failed to trigger webhook for agent instance {agent_instance_id}: {e}"
        )
