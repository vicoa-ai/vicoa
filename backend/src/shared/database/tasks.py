"""Task-tracker DB helpers shared by both server processes.

Holds the instance-status → task-status linkage (tasks-and-projects plan §4).
"No project" is simply ``tasks.project_id IS NULL`` — there is no Inbox row.
"""

import logging

from sqlalchemy import event
from sqlalchemy.orm import Session, attributes

from .actor import Actor, register_activity_override
from .enums import AgentStatus
from .models import AgentInstance
from .task_models import Task

logger = logging.getLogger(__name__)

# Literal mapping chosen by Nick (plan §4). Because vicoa's lifecycle runs
# ACTIVE → COMPLETED → REVIEWED, a review after completion moves the task
# backward done → in_review — accepted, documented in the plan.
AGENT_TO_TASK_STATUS: dict[AgentStatus, str] = {
    AgentStatus.ACTIVE: "in_progress",
    AgentStatus.COMPLETED: "done",
    AgentStatus.REVIEWED: "in_review",
}


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
