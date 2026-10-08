"""Dispatch for an automation that runs in one existing session.

Set by `automations.agent_instance_id`. Instead of spawning a new session, each
run delivers its prompt into that session:

- its agent holds a socket → post the prompt as a user message, exactly what
  typing it into the composer does (queued behind a turn already running)
- otherwise → resume the session on its machine with the prompt: the same
  `spawn-session` + `resume` the Resume button sends, and every wrapper posts
  a launch prompt as the session's next user message, resumed or not
- the daemon finds the agent running after all (`already_running`) → post it

Each message carries `automation_id` in its metadata, so a run can tell that
this automation's previous prompt is still waiting in the queue and skip
rather than stack another behind it.
"""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import joinedload

from shared.database import AgentInstance, Message
from shared.database.enums import AgentStatus, SenderType
from shared.database.session import SessionLocal
from shared.session_resume import (
    agent_session_handle,
    expand_project_path,
    resume_agent_slug,
)
from shared.websocket.connection_manager import connection_manager
from shared.websocket.envelope import build_new_message_update
from shared.websocket.in_tx import after_commit
from shared.websocket.protocol import watcher_room
from shared.websocket.rpc import RpcError, rpc_router

from .dispatch import DispatchResult, to_spawn_metadata

# Queue states that mean the prompt hasn't reached the agent yet.
_WAITING_QUEUE_STATES = ("queued", "steer")


@dataclass(frozen=True)
class _Target:
    machine_id: UUID | None
    directory: str | None
    session_config: dict
    agent_session_id: str | None


def _load_target_blocking(user_id: UUID, instance_id: UUID) -> _Target | None:
    """The session as it is now (it may have moved since the automation
    snapshotted it). None when it is gone, deleted, or not the author's."""
    with SessionLocal() as db:
        instance = (
            db.query(AgentInstance)
            .options(joinedload(AgentInstance.agent_type))
            .filter(
                AgentInstance.id == instance_id,
                AgentInstance.user_id == user_id,
                AgentInstance.status != AgentStatus.DELETED,
            )
            .first()
        )
        if instance is None:
            return None
        config = dict(instance.session_config or {})
        config["agent"] = resume_agent_slug(
            instance.session_config, instance.agent_type.name
        )
        return _Target(
            machine_id=instance.machine_id,
            directory=(
                expand_project_path(instance.project, instance.home_dir)
                if instance.project
                else None
            ),
            session_config=config,
            agent_session_id=agent_session_handle(instance.instance_metadata),
        )


def _post_prompt_blocking(
    user_id: UUID, automation_id: UUID, instance_id: UUID, prompt: str
) -> DispatchResult:
    """Post the prompt as the author's message, the way the composer does
    (`create_user_message_endpoint`), and fan it out to the session's agent and
    open dashboards."""
    linked = str(instance_id)
    with SessionLocal() as db:
        instance = (
            db.query(AgentInstance)
            .filter(
                AgentInstance.id == instance_id,
                AgentInstance.user_id == user_id,
                AgentInstance.status != AgentStatus.DELETED,
            )
            .first()
        )
        if instance is None:
            return DispatchResult(status="failed", detail="session deleted")

        still_waiting = (
            db.query(Message.id)
            .filter(
                Message.agent_instance_id == instance_id,
                Message.sender_type == SenderType.USER,
                Message.message_metadata["automation_id"].astext == str(automation_id),
                Message.message_metadata[("queue", "status")].astext.in_(
                    _WAITING_QUEUE_STATES
                ),
            )
            .first()
        )
        if still_waiting is not None:
            return DispatchResult(
                status="skipped",
                agent_instance_id=linked,
                detail="previous run still queued",
            )

        metadata: dict = {"automation_id": str(automation_id)}
        if instance.status == AgentStatus.ACTIVE:
            # Mid-turn: it waits its turn, and the composer shows it queued.
            metadata["queue"] = {"status": "queued"}
        message = Message(
            agent_instance_id=instance_id,
            sender_type=SenderType.USER,
            sender_user_id=user_id,
            content=prompt,
            requires_user_input=False,
            message_metadata=metadata,
        )
        db.add(message)
        db.flush()
        db.refresh(message)
        # Only reached while the agent holds its socket, so something is there
        # to work on it.
        instance.status = AgentStatus.ACTIVE

        payload = build_new_message_update(message)
        rooms = [
            f"user:{user_id}:session:{instance_id}",
            f"user:{user_id}:user-scoped",
            watcher_room(str(instance_id)),
        ]
        after_commit(
            db,
            lambda: connection_manager.broadcast_update(str(user_id), payload, rooms),
        )
        db.commit()
    return DispatchResult(status="fired", agent_instance_id=linked)


async def dispatch_to_session(
    *, user_id: UUID, automation_id: UUID, instance_id: UUID, prompt: str
) -> DispatchResult:
    """Deliver one run's prompt into the automation's session.

    - session gone or deleted → ``failed`` with ``disable`` set
    - agent running → message posted → ``fired`` (``skipped`` if this
      automation's last prompt is still queued)
    - agent stopped → resumed with the prompt → ``fired``
    - machine offline → ``missed_offline``; daemon error → ``failed``
    """
    target = await asyncio.to_thread(_load_target_blocking, user_id, instance_id)
    if target is None:
        return DispatchResult(status="failed", detail="session deleted", disable=True)

    if connection_manager.is_session_connected(str(instance_id)):
        return await asyncio.to_thread(
            _post_prompt_blocking, user_id, automation_id, instance_id, prompt
        )

    if target.machine_id is None or not target.directory:
        return DispatchResult(
            status="failed",
            agent_instance_id=str(instance_id),
            detail="session has no computer or folder to resume in",
        )

    resume: dict = {"agent_instance_id": str(instance_id)}
    if target.agent_session_id:
        resume["agent_session_id"] = target.agent_session_id
    params = {
        "directory": target.directory,
        "agent": target.session_config["agent"],
        "resume": resume,
        "metadata": to_spawn_metadata(target.session_config, prompt),
    }
    try:
        result = await rpc_router.call(
            str(user_id), str(target.machine_id), "spawn-session", params
        )
    except RpcError as exc:
        status = "missed_offline" if exc.code == "no_handler" else "failed"
        detail = "machine offline" if exc.code == "no_handler" else exc.code
        return DispatchResult(
            status=status, agent_instance_id=str(instance_id), detail=detail
        )

    if isinstance(result, dict) and result.get("error"):
        return DispatchResult(
            status="failed",
            agent_instance_id=str(instance_id),
            detail=str(result["error"]),
        )
    if isinstance(result, dict) and result.get("already_running"):
        # The daemon reopened a live agent instead of launching one, and a
        # reopen ignores the launch prompt: deliver it as a message instead.
        return await asyncio.to_thread(
            _post_prompt_blocking, user_id, automation_id, instance_id, prompt
        )
    return DispatchResult(status="fired", agent_instance_id=str(instance_id))
