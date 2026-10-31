"""Task-tracker DB helpers shared by both server processes.

Holds the one way a session moves its task on its own (tasks-and-projects plan
§4, narrowed): starting work picks up a task nobody has started.
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

# A session moves its task in one case only: it starts running (ACTIVE) on a
# task nobody has started, which becomes in_progress. Its other statuses say
# whether the user has read it (REVIEWED) or put it away (COMPLETED, which is
# also what an agent's own end_session writes), not whether the work is
# finished, so they never touch the task. Finishing a task is always someone's
# explicit change: the user's in the UI (the web asks when a session is
# archived) or an agent's with `vicoa task update`.
SESSION_START_TASK_STATUS = "in_progress"
# Any other status was chosen, or is past starting, and a session waking up
# leaves it: an agent that marked its task blocked stays blocked when the
# user's reply wakes it, and a session resumed on a done task does not reopen it.
SESSION_START_MAY_MOVE_FROM: frozenset[str] = frozenset({"backlog", "todo"})


def _sync_task_status_before_flush(session: Session, flush_context, instances) -> None:
    """Move a linked task to in_progress when its session starts work (plan §4).

    Instance status is written from ~10 call sites across both server
    processes (REST, WS, daemon, web review flow); the flush is the single
    point they all pass through, so the linkage lives here rather than in
    each caller. Fires when a linked instance goes ACTIVE, and when task_id is
    stamped late (§8b: the web PATCH that links a spawned instance can land
    after the instance already went ACTIVE).
    """
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, AgentInstance) or obj.task_id is None:
            continue
        if obj.status != AgentStatus.ACTIVE:
            continue
        is_new = obj in session.new
        status_changed = is_new or attributes.get_history(obj, "status").has_changes()
        newly_linked = is_new or attributes.get_history(obj, "task_id").has_changes()
        if not (status_changed or newly_linked):
            continue
        with session.no_autoflush:
            task = session.get(Task, obj.task_id)
            if (
                task is None
                or task.user_id != obj.user_id
                or task.status == SESSION_START_TASK_STATUS
            ):
                continue
            if task.status not in SESSION_START_MAY_MOVE_FROM:
                logger.info(
                    "task status sync: instance %s started, task %s keeps %s",
                    obj.id,
                    task.id,
                    task.status,
                )
                continue
        logger.info(
            "task status sync: instance %s started -> task %s becomes %s",
            obj.id,
            task.id,
            SESSION_START_TASK_STATUS,
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
        task.status = SESSION_START_TASK_STATUS


event.listen(Session, "before_flush", _sync_task_status_before_flush)
