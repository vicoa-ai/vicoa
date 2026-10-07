"""Task-tracker DB helpers shared by both server processes.

Holds the instance-status → task-status linkage (tasks-and-projects plan §4).
"No project" is simply ``tasks.project_id IS NULL`` — there is no Inbox row.
"""

import logging
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.orm import Session, attributes

from .actor import Actor, register_activity_override
from .enums import AgentStatus
from .models import AgentInstance
from .task_models import Task, TaskActivity

logger = logging.getLogger(__name__)

# Literal mapping chosen by Nick (plan §4). Because vicoa's lifecycle runs
# ACTIVE → COMPLETED → REVIEWED, a review after completion moves the task
# backward done → in_review — accepted, documented in the plan.
AGENT_TO_TASK_STATUS: dict[AgentStatus, str] = {
    AgentStatus.ACTIVE: "in_progress",
    AgentStatus.COMPLETED: "done",
    AgentStatus.REVIEWED: "in_review",
}

# The status a task must be in for the sync to move it on its own say-so.
# Anything else was chosen — in the UI, or by an agent with `vicoa task update`
# — and a session starting, finishing or being reviewed must not overwrite it:
# an agent that marks its task blocked and then exits leaves it blocked. The
# one way past this is a status the sync wrote itself (`_status_set_by_sync`),
# which is what lets a session's own in_progress → done → in_review chain run,
# and a resumed session reopen the `done` it set.
SYNC_MAY_MOVE_FROM: dict[AgentStatus, frozenset[str]] = {
    # Starting work picks up a task nobody has started.
    AgentStatus.ACTIVE: frozenset({"backlog", "todo"}),
    # Finishing closes a task that is in progress, whoever put it there.
    AgentStatus.COMPLETED: frozenset({"in_progress"}),
    # REVIEWED fires when the user merely switches away from a finished session,
    # so it only ever follows the sync's own `done`, never one a person chose.
    AgentStatus.REVIEWED: frozenset(),
}


def _status_set_by_sync(session: Session, task_id: UUID) -> bool:
    """Whether the task's current status was written by this sync.

    Read off the latest `status_changed` row: the sync's carry the session's
    `agent_instance_id` and no `direct` flag. A change made in the UI carries
    no session, and one an agent made with `vicoa task update` is `direct`.
    A task whose status never changed (still the one it was created with)
    has no row, which counts as chosen.
    """
    row = (
        session.query(TaskActivity.details)
        .filter(
            TaskActivity.task_id == task_id,
            TaskActivity.action == "status_changed",
        )
        .order_by(TaskActivity.created_at.desc())
        .first()
    )
    details = (row[0] if row is not None else None) or {}
    return "agent_instance_id" in details and not details.get("direct")


def _sync_task_status_before_flush(session: Session, flush_context, instances) -> None:
    """Drive a linked task's status from its run's status (plan §4).

    Instance status is written from ~10 call sites across both server
    processes (REST, WS, daemon, web review flow); the flush is the single
    point they all pass through, so the linkage lives here rather than in
    each caller. Fires when a linked instance's status changes into a mapped
    state, and when task_id is stamped late (§8b: the web PATCH that links a
    spawned instance can land after the instance already went ACTIVE). A status
    someone chose wins over the mapping; see `SYNC_MAY_MOVE_FROM`.
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
            if task.status not in SYNC_MAY_MOVE_FROM[
                obj.status
            ] and not _status_set_by_sync(session, task.id):
                logger.info(
                    "task status sync: instance %s went %s, task %s keeps its "
                    "chosen status %s",
                    obj.id,
                    obj.status.value,
                    task.id,
                    task.status,
                )
                continue
        logger.info(
            "task status sync: instance %s went %s -> task %s becomes %s",
            obj.id,
            obj.status.value,
            task.id,
            mapped,
        )
        # Attribute the move to the agent, not to whoever's request happened to
        # carry the status update — the daemon posts it authenticated as the
        # user, but the thing that moved the task is the session. Carrying the
        # instance id lets the task timeline fold this session's status hops
        # into its session card rather than listing each one.
        register_activity_override(
            session,
            task.id,
            Actor(
                type="agent" if obj.agent_profile_id else "system",
                id=obj.agent_profile_id,
                agent_instance_id=obj.id,
            ),
        )
        task.status = mapped


event.listen(Session, "before_flush", _sync_task_status_before_flush)
