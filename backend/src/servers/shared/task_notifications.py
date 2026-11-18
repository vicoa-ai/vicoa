"""Task pushes addressed to one person: assigned, asked, mentioned.

* `task_assigned` — the task is now theirs.
* `task_question` — an agent asked them a question on it
  (plans/todos/task-questions-waiting-on.md).
* `task_mentioned` — someone @mentioned them in a comment.

Called from the task query layer, inside the request's transaction, by both
server processes: the dashboard API (a teammate assigns or mentions you) and
the agent API (an agent asks you something). The push goes out after the
commit, from a short-lived thread with its own event loop and session, so a
slow or failing push never holds the request or its transaction — the same
"never break the write for a notification" rule as the message pushes.

Not routed through `task_subscribers`: each of these is addressed to one
person, and the push goes straight to them.
"""

from __future__ import annotations

import asyncio
import logging
import re
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
QUESTION_PUSH_TYPE = "task_question"
MENTION_PUSH_TYPE = "task_mentioned"
_BODY_CHARS = 100


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
    kind = data.get("type", "task")

    def run() -> None:
        try:
            asyncio.run(_send(user_id, title, body, data))
        except Exception:  # noqa: BLE001 — a push must never surface as an error
            logger.exception("%s push to %s failed", kind, user_id)

    threading.Thread(target=run, name=f"{kind}-push", daemon=True).start()


def _clip(text: str) -> str:
    return text if len(text) <= _BODY_CHARS else text[: _BODY_CHARS - 3] + "..."


_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_MARKERS = re.compile(r"(\*\*|__|`+|~~)")
_MD_LINE_PREFIX = re.compile(r"^\s{0,3}(?:#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+)")


def first_line(body: str) -> str:
    """A comment's first non-blank line as plain text: what fits on a lock
    screen. Links keep their text, so `[@Ada](vicoa://user/…)` reads "@Ada"."""
    for line in body.splitlines():
        text = _MD_LINE_PREFIX.sub("", _MD_LINK.sub(r"\1", line))
        text = " ".join(_MD_MARKERS.sub("", text).split())
        if text:
            return text
    return ""


def _comment_push_body(ref: str | None, task: Task, body: str) -> str:
    line = first_line(body) or task.title
    return _clip(f"{ref}: {line}" if ref else line)


def _comment_data(
    kind: str, task: Task, comment_id: UUID, ref: str | None
) -> dict[str, str]:
    data = {"type": kind, "taskId": str(task.id), "commentId": str(comment_id)}
    if ref:
        data["identifier"] = ref
    return data


def notify_task_assigned_after_commit(
    db: Session, task: Task, *, assignee_user_id: UUID
) -> None:
    """Queue the push for after this transaction commits (never on rollback)."""
    ref = _task_ref(db, task)
    who = _assigner_name(db)
    title = f"{who} assigned you {ref}" if ref else f"{who} assigned you a task"
    body = _clip(task.title)
    data = {"type": PUSH_TYPE, "taskId": str(task.id)}
    if ref:
        data["identifier"] = ref
    after_commit(db, lambda: _send_in_thread(assignee_user_id, title, body, data))


def notify_task_question_after_commit(
    db: Session,
    task: Task,
    *,
    addressee_id: UUID,
    asker_name: str,
    comment_id: UUID,
    body: str,
) -> None:
    """Push 'asked you' to the person a question asks: "Claude asked you",
    "VIC-42: <the question's first line>"."""
    ref = _task_ref(db, task)
    title = f"{asker_name} asked you"
    text = _comment_push_body(ref, task, body)
    data = _comment_data(QUESTION_PUSH_TYPE, task, comment_id, ref)
    after_commit(db, lambda: _send_in_thread(addressee_id, title, text, data))


def notify_task_mentioned_after_commit(
    db: Session,
    task: Task,
    *,
    user_ids: list[UUID],
    author_name: str,
    comment_id: UUID,
    body: str,
) -> None:
    """Push 'mentioned you' to each person: "Ada mentioned you",
    "VIC-42: <the comment's first line>"."""
    if not user_ids:
        return
    ref = _task_ref(db, task)
    title = f"{author_name} mentioned you"
    text = _comment_push_body(ref, task, body)
    data = _comment_data(MENTION_PUSH_TYPE, task, comment_id, ref)
    people = list(user_ids)

    def send_all() -> None:
        for user_id in people:
            _send_in_thread(user_id, title, text, data)

    after_commit(db, send_all)
