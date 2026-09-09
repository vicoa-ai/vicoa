"""Generated task activity — one flush listener, never a call site (§3.5).

Task mutations reach the database from the human REST API, the agent-facing
REST API, the CLI, the automation runner and the instance-status sync. Writing
an activity row at each of those is how the log ends up with holes, so the diff
is taken where all of them converge: the flush. This is the same argument — and
the same shape — as `tasks.py::_sync_task_status_before_flush`.

**Why `after_flush` and not `before_flush`.** `Task.id` is a Python-side
`default=uuid4`, so it is still `None` while `before_flush` runs and a `created`
row would have nothing to point at. `after_flush` has the ids, still has full
attribute history (that is reset later, in `after_flush_postexec`), and objects
added to the session there are picked up by the flush loop `Session.commit()`
runs until the session is clean. The recursion that implies terminates on its
own: the second flush contains only `TaskActivity` rows, and this listener only
ever looks at `Task`.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.orm import Session, attributes

from .actor import session_actor, take_activity_override
from .task_models import Task, TaskActivity

logger = logging.getLogger(__name__)

# Scalar columns worth a timeline entry, mapped to the action they emit.
# `assignee_id` stands in for the (assignee_type, assignee_id) pair — they
# always move together and two rows for one edit reads as a bug.
WATCHED_COLUMNS: dict[str, str] = {
    "status": "status_changed",
    "priority": "priority_changed",
    "assignee_id": "assigned",
    "title": "title_changed",
    "description": "description_changed",
    "due_date": "due_date_set",
    "start_date": "start_date_set",
    "project_id": "project_changed",
    "parent_task_id": "parent_changed",
}

# Long free text is recorded as "changed", not as a before/after pair: a diff of
# two 4 kB descriptions is not something a timeline row can usefully render, and
# storing both copies on every keystroke-save would dwarf the table.
_OPAQUE_COLUMNS = frozenset({"title", "description"})


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def _changed(obj: Task, key: str) -> tuple[bool, Any, Any]:
    """(has_changes, old, new) for one attribute of `obj`."""
    history = attributes.get_history(obj, key)
    if not history.has_changes():
        return False, None, None
    old = history.deleted[0] if history.deleted else None
    new = history.added[0] if history.added else None
    if old == new:
        return False, None, None
    return True, old, new


def _activity(
    task: Task, action: str, details: dict[str, Any], db: Session
) -> TaskActivity:
    """Build one row, resolving the actor: per-task override first, then the
    session's request actor, then nothing (an unattributed line)."""
    actor = take_activity_override(db, task.id) or session_actor(db)
    payload = dict(details)
    if actor is not None and actor.agent_instance_id is not None:
        payload["agent_instance_id"] = str(actor.agent_instance_id)
    return TaskActivity(
        task_id=task.id,
        project_id=task.project_id,
        actor_type=actor.type if actor else None,
        actor_id=actor.id if actor else None,
        action=action,
        details=payload,
    )


def _label_events(task: Task, db: Session) -> list[TaskActivity]:
    history = attributes.get_history(task, "labels")
    if not history.has_changes():
        return []
    rows: list[TaskActivity] = []
    for label in history.added or ():
        rows.append(
            _activity(
                task,
                "label_added",
                {"label_id": str(label.id), "label": label.name},
                db,
            )
        )
    for label in history.deleted or ():
        rows.append(
            _activity(
                task,
                "label_removed",
                {"label_id": str(label.id), "label": label.name},
                db,
            )
        )
    return rows


def _record_task_activity(session: Session, flush_context) -> None:
    rows: list[TaskActivity] = []

    for obj in session.new:
        if isinstance(obj, Task):
            # One `created` row, never a field-change row per column: everything
            # about a brand-new task is part of creating it.
            rows.append(_activity(obj, "created", {}, session))

    for obj in session.dirty:
        if not isinstance(obj, Task):
            continue
        for key, action in WATCHED_COLUMNS.items():
            has_changes, old, new = _changed(obj, key)
            if not has_changes:
                continue
            if key in _OPAQUE_COLUMNS:
                details: dict[str, Any] = {}
            elif key == "assignee_id":
                details = {
                    "to": _jsonable(new),
                    "to_type": obj.assignee_type,
                    "from": _jsonable(old),
                }
            else:
                details = {"from": _jsonable(old), "to": _jsonable(new)}
            rows.append(_activity(obj, action, details, session))
        rows.extend(_label_events(obj, session))

    if rows:
        session.add_all(rows)


event.listen(Session, "after_flush", _record_task_activity)
