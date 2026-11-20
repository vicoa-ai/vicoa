"""Wakeups: an agent waiting on a task, and when the wait ends.

plans/todos/task-questions-waiting-on.md; the table is `task_wakeups`
(`shared/database/task_wakeup_models.py`). v1 has one kind, `reply`: an agent
asked a person a question (`vicoa task comment --ask`) and waits for them to
comment. While it waits, the task is "waiting on" that person: their board
shows it, their phone was told, and their answer wakes the agent.

Nobody ends a wakeup by hand, and having seen the question never counts. A
reply wakeup **fires** when a comment from the person it waits for reaches the
agent (`task_dispatch.route_comment`): a top-level comment, a reply in a thread
the agent wrote in last, or one that @mentions it. A comment that goes
elsewhere (a mention of another agent, a reply in another agent's thread or in
one between people, a `/note`) leaves it waiting, since the agent hasn't heard
an answer. It **ends** without firing when the agent no longer needs the answer
or can't get it:

* the task leaves `blocked` (`unblocked`) or enters `in_review` (`delivered`):
  the agent has what it needed, wherever it got it;
* the task becomes done or cancelled (`task_closed`);
* the question comment is deleted (`deleted`).

Called inside the request's transaction by the task query layer, beside
`task_dispatch`, so both routers get the same rules. Matching lives here
rather than in a database trigger: firing means queueing a dispatch, which is
Python (`task_dispatch.enqueue`), and every comment and status write already
passes through the query layer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from shared.database.task_dispatch_models import TaskDispatch
from shared.database.task_models import Task, TaskComment
from shared.database.task_wakeup_models import TaskWakeup

_CLOSED_STATUSES = frozenset({"done", "cancelled"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def waiting_on_task_ids(user_id: UUID) -> Select[tuple[UUID]]:
    """Ids of the tasks with a reply wakeup waiting on `user_id`, for `.in_()`."""
    return select(TaskWakeup.task_id).where(
        TaskWakeup.kind == "reply",
        TaskWakeup.state == "waiting",
        TaskWakeup.wait_for_user_id == user_id,
    )


def waiting_on_people(
    db: Session, task_ids: Sequence[UUID]
) -> dict[UUID, list[TaskWakeup]]:
    """Each task's reply wakeups still waiting, oldest first: whom it waits on.
    One query for a whole list."""
    if not task_ids:
        return {}
    rows = (
        db.execute(
            select(TaskWakeup)
            .where(
                TaskWakeup.task_id.in_(list(task_ids)),
                TaskWakeup.kind == "reply",
                TaskWakeup.state == "waiting",
            )
            .order_by(TaskWakeup.created_at.asc())
        )
        .scalars()
        .all()
    )
    out: dict[UUID, list[TaskWakeup]] = {}
    for row in rows:
        out.setdefault(row.task_id, []).append(row)
    return out


def questions_by_comment(
    db: Session, comment_ids: Sequence[UUID]
) -> dict[UUID, TaskWakeup]:
    """The reply wakeup each comment registered, if it was a question."""
    if not comment_ids:
        return {}
    rows = (
        db.execute(
            select(TaskWakeup).where(
                TaskWakeup.source_comment_id.in_(list(comment_ids)),
                TaskWakeup.kind == "reply",
            )
        )
        .scalars()
        .all()
    )
    return {row.source_comment_id: row for row in rows if row.source_comment_id}


def ask(
    db: Session,
    task: Task,
    *,
    agent_profile_id: UUID,
    person_id: UUID,
    comment: TaskComment,
    instance_id: UUID | None,
) -> TaskWakeup:
    """The agent that wrote `comment` waits for `person_id` to answer it."""
    wakeup = TaskWakeup(
        user_id=task.user_id,
        task_id=task.id,
        agent_profile_id=agent_profile_id,
        kind="reply",
        wait_for_user_id=person_id,
        source_comment_id=comment.id,
        created_in_instance_id=instance_id,
        state="waiting",
    )
    db.add(wakeup)
    return wakeup


def _waiting_for(db: Session, task: Task, person_id: UUID) -> list[TaskWakeup]:
    return list(
        db.execute(
            select(TaskWakeup)
            .where(
                TaskWakeup.task_id == task.id,
                TaskWakeup.kind == "reply",
                TaskWakeup.state == "waiting",
                TaskWakeup.wait_for_user_id == person_id,
            )
            .order_by(TaskWakeup.created_at.asc())
        )
        .scalars()
        .all()
    )


def agents_waiting_on(db: Session, task: Task, person_id: UUID) -> list[UUID]:
    """The agent profiles waiting for `person_id`'s comment on `task`, oldest
    wakeup first, each once: whom that person's next top-level comment is for."""
    return list(
        dict.fromkeys(w.agent_profile_id for w in _waiting_for(db, task, person_id))
    )


def on_comment_created(
    db: Session,
    task: Task,
    comment: TaskComment,
    reached: Mapping[UUID, TaskDispatch | None],
) -> None:
    """A person commented: fire the reply wakeups of the agents it reached.

    Called after the comment was routed (`task_dispatch.on_comment_created`,
    which read these wakeups to know whom the comment is for), with every
    agent it reached by profile and the dispatch each got (None: the person
    can't start that agent), so each wakeup records the run it started. The
    wakeups of agents it didn't reach keep waiting."""
    if not reached:
        return
    now = _now()
    for wakeup in _waiting_for(db, task, comment.author_id):
        if wakeup.agent_profile_id not in reached:
            continue
        dispatch = reached[wakeup.agent_profile_id]
        wakeup.state = "fired"
        wakeup.ended_at = now
        wakeup.fired_by_comment_id = comment.id
        wakeup.dispatch_id = dispatch.id if dispatch is not None else None


def _end(
    db: Session, task_id: UUID, reason: str, *, source_comment_id: UUID | None = None
) -> int:
    query = db.query(TaskWakeup).filter(
        TaskWakeup.task_id == task_id, TaskWakeup.state == "waiting"
    )
    if source_comment_id is not None:
        query = query.filter(TaskWakeup.source_comment_id == source_comment_id)
    return query.update(
        {"state": "ended", "ended_reason": reason, "ended_at": _now()},
        synchronize_session="fetch",
    )


def on_status_changed(db: Session, task: Task, *, old_status: str) -> None:
    """Closing the task, delivering it, or taking it out of `blocked` means the
    agent no longer waits for an answer."""
    if task.status in _CLOSED_STATUSES:
        reason = "task_closed"
    elif task.status == "in_review":
        reason = "delivered"
    elif old_status == "blocked" and task.status != "blocked":
        reason = "unblocked"
    else:
        return
    _end(db, task.id, reason)


def on_comment_deleted(db: Session, comment: TaskComment) -> None:
    """A deleted question asks nobody anything."""
    _end(db, comment.task_id, "deleted", source_comment_id=comment.id)
