"""Task-tracker DB helpers shared by both server processes.

Holds the Inbox auto-create helper and the instance-status → task-status
linkage (tasks-and-projects plan §4).
"""

import logging
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, attributes

from .enums import AgentStatus
from .models import AgentInstance
from .task_models import Project, Task

logger = logging.getLogger(__name__)

INBOX_PROJECT_NAME = "Inbox"

# Literal mapping chosen by Nick (plan §4). Because vicoa's lifecycle runs
# ACTIVE → COMPLETED → REVIEWED, a review after completion moves the task
# backward done → in_review — accepted, documented in the plan.
AGENT_TO_TASK_STATUS: dict[AgentStatus, str] = {
    AgentStatus.ACTIVE: "in_progress",
    AgentStatus.COMPLETED: "done",
    AgentStatus.REVIEWED: "in_review",
}


def get_or_create_inbox(db: Session, user_id: UUID) -> Project:
    """Return the user's Inbox project, lazily creating it on first use.

    The Inbox is the "No project" bucket that keeps tasks.project_id NOT NULL.
    Idempotent and race-safe: the partial unique index uq_projects_user_inbox
    allows one is_inbox row per user, and losing a concurrent insert falls
    back to re-reading the winner.
    """

    def _existing() -> Project | None:
        return (
            db.query(Project)
            .filter(Project.user_id == user_id, Project.is_inbox.is_(True))
            .first()
        )

    inbox = _existing()
    if inbox is not None:
        return inbox

    inbox = Project(user_id=user_id, name=INBOX_PROJECT_NAME, is_inbox=True)
    nested = db.begin_nested()
    try:
        db.add(inbox)
        db.flush()
        nested.commit()
    except IntegrityError:
        nested.rollback()
        db.expunge(inbox)
        winner = _existing()
        if winner is None:  # pragma: no cover - only under pathological races
            raise
        logger.info("inbox create raced for user %s; reusing existing", user_id)
        return winner
    return inbox


def _sync_task_status_before_flush(session: Session, flush_context, instances) -> None:
    """Drive a linked task's status from its run's status (plan §4).

    Instance status is written from ~10 call sites across both server
    processes (REST, WS, daemon, web review flow); the flush is the single
    point they all pass through, so the linkage lives here rather than in
    each caller. Fires when a linked instance's status changes into a mapped
    state, and when task_id is stamped late (§8b: the web PATCH that links a
    spawned instance can land after the instance already went ACTIVE).
    """
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, AgentInstance) or obj.task_id is None:
            continue
        is_new = obj in session.new
        status_changed = is_new or attributes.get_history(obj, "status").has_changes()
        newly_linked = is_new or attributes.get_history(obj, "task_id").has_changes()
        if not (status_changed or newly_linked):
            continue
        mapped = AGENT_TO_TASK_STATUS.get(obj.status)
        if mapped is None:
            continue
        with session.no_autoflush:
            task = session.get(Task, obj.task_id)
        if task is None or task.user_id != obj.user_id or task.status == mapped:
            continue
        logger.info(
            "task status sync: instance %s went %s -> task %s becomes %s",
            obj.id,
            obj.status.value,
            task.id,
            mapped,
        )
        task.status = mapped


event.listen(Session, "before_flush", _sync_task_status_before_flush)
