"""Push "assigned you a task" to the assignee's phone.

Called from the task query layer, inside the request's transaction, by both
server processes: the dashboard API (a teammate assigns you) and the agent
API (an agent hands you a task it needs you for). The push goes out after the
commit, from a short-lived thread with its own event loop and session, so a
slow or failing push never holds the request or its transaction — the same
"never break the write for a notification" rule as the message pushes.

Not routed through `task_subscribers`: being assigned is addressed to one
person, and the push goes straight to them.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from uuid import UUID

from sqlalchemy.orm import Session

from shared.database import Project, Task
from shared.database.actor import session_actor
from shared.database.agent_profile_models import AgentProfile
from shared.database.models import User
from shared.database.session import SessionLocal
from shared.database.task_identity import format_task_identifier
from shared.websocket.in_tx import after_commit

logger = logging.getLogger(__name__)

PUSH_TYPE = "task_assigned"


def _assigner_name(db: Session) -> str:
    actor = session_actor(db)
    if actor is None or actor.id is None:
        return "Someone"
    if actor.type == "agent":
        name = db.query(AgentProfile.name).filter(AgentProfile.id == actor.id).scalar()
        return name or "An agent"
    name = db.query(User.display_name).filter(User.id == actor.id).scalar()
    return name or "Someone"


def _task_ref(db: Session, task: Task) -> str | None:
    if task.project_id is None or task.number is None:
        return None
    key = db.query(Project.key).filter(Project.id == task.project_id).scalar()
    return format_task_identifier(key, task.number)


async def _send(user_id: UUID, title: str, body: str, data: dict[str, str]) -> None:
    from servers.shared.fcm_service import fcm_service

    with SessionLocal() as db:
        await fcm_service.send_notification(
            db=db, user_id=user_id, title=title, body=body, data=data
        )


def _send_in_thread(user_id: UUID, title: str, body: str, data: dict[str, str]) -> None:
    def run() -> None:
        try:
            asyncio.run(_send(user_id, title, body, data))
        except Exception:  # noqa: BLE001 — a push must never surface as an error
            logger.exception("task-assigned push to %s failed", user_id)

    threading.Thread(target=run, name="task-assigned-push", daemon=True).start()


def notify_task_assigned_after_commit(
    db: Session, task: Task, *, assignee_user_id: UUID
) -> None:
    """Queue the push for after this transaction commits (never on rollback)."""
    ref = _task_ref(db, task)
    who = _assigner_name(db)
    title = f"{who} assigned you {ref}" if ref else f"{who} assigned you a task"
    body = task.title if len(task.title) <= 100 else task.title[:97] + "..."
    data = {"type": PUSH_TYPE, "taskId": str(task.id)}
    if ref:
        data["identifier"] = ref
    after_commit(db, lambda: _send_in_thread(assignee_user_id, title, body, data))
