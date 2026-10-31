"""Task-tracker DB helpers shared by both server processes.

Holds the instance-status → task-status linkage (tasks-and-projects plan §4).
"No project" is simply ``tasks.project_id IS NULL`` — there is no Inbox row.
"""

import logging
from uuid import UUID

from sqlalchemy import event, func
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


# Statuses of a session that is still part of the work. A task is not finished
# while one of these is attached to it: another session on the same task is
# still running, or waiting on the user. REVIEWED (the user already looked and
# moved on) and the terminal statuses do not count.
OPEN_SESSION_STATUSES: frozenset[AgentStatus] = frozenset(
    {
        AgentStatus.STARTING,
        AgentStatus.ACTIVE,
        AgentStatus.AWAITING_INPUT,
        AgentStatus.PAUSED,
    }
)

# What the caller asking for a status change wants done to the linked task, for
# that one flush. The listener sees *that* an instance changed, never why, so
# the caller hands it the intent the same way it hands an activity actor.
#   skip   the task keeps whatever status it has.
#   force  move the task to the mapped status even where the sync would hold
#          back (another session still open, a status someone chose): the user
#          saw that and picked it.
SYNC_SKIP = "skip"
SYNC_FORCE = "force"
_DIRECTIVE_KEY = "vicoa_task_sync_directives"


def set_task_sync_directive(
    session: Session, instance_id: UUID, directive: str
) -> None:
    """Tell the next flush how to treat `instance_id`'s linked task."""
    session.info.setdefault(_DIRECTIVE_KEY, {})[instance_id] = directive


def _take_task_sync_directive(session: Session, instance_id: UUID) -> str | None:
    directives = session.info.get(_DIRECTIVE_KEY)
    if not directives:
        return None
    return directives.pop(instance_id, None)


def count_open_sibling_sessions(
    session: Session, task_id: UUID, instance_id: UUID
) -> int:
    """Other sessions on `task_id` that are still part of the work."""
    return (
        session.query(func.count(AgentInstance.id))
        .filter(
            AgentInstance.task_id == task_id,
            AgentInstance.id != instance_id,
            AgentInstance.status.in_(OPEN_SESSION_STATUSES),
        )
        .scalar()
        or 0
    )


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


def sync_target_status(
    session: Session,
    status: AgentStatus,
    instance_id: UUID,
    task: Task,
    *,
    ignore_open_sessions: bool = False,
) -> str | None:
    """The status the sync would move `task` to when `instance_id` goes to
    `status`, or None when it would leave the task alone.

    The one place the rules live, so the flush listener and the archive preview
    (which asks "what would happen if I archived this?" before anyone does)
    cannot disagree. A task is finished only when no other session on it is
    still part of the work; `ignore_open_sessions` answers the same question
    as if there were none.
    """
    mapped = AGENT_TO_TASK_STATUS.get(status)
    if mapped is None or task.status == mapped:
        return None
    if task.status not in SYNC_MAY_MOVE_FROM[status] and not _status_set_by_sync(
        session, task.id
    ):
        return None
    if (
        status is AgentStatus.COMPLETED
        and not ignore_open_sessions
        and count_open_sibling_sessions(session, task.id, instance_id) > 0
    ):
        return None
    return mapped


def _sync_task_status_before_flush(session: Session, flush_context, instances) -> None:
    """Drive a linked task's status from its run's status (plan §4).

    Instance status is written from ~10 call sites across both server
    processes (REST, WS, daemon, web review flow); the flush is the single
    point they all pass through, so the linkage lives here rather than in
    each caller. Fires when a linked instance's status changes into a mapped
    state, and when task_id is stamped late (§8b: the web PATCH that links a
    spawned instance can land after the instance already went ACTIVE). A status
    someone chose wins over the mapping; see `SYNC_MAY_MOVE_FROM`. A caller that
    knows better says so with `set_task_sync_directive`.
    """
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, AgentInstance) or obj.task_id is None:
            continue
        directive = _take_task_sync_directive(session, obj.id)
        is_new = obj in session.new
        status_changed = is_new or attributes.get_history(obj, "status").has_changes()
        newly_linked = is_new or attributes.get_history(obj, "task_id").has_changes()
        if not (status_changed or newly_linked):
            continue
        mapped = AGENT_TO_TASK_STATUS.get(obj.status)
        if mapped is None or directive == SYNC_SKIP:
            continue
        with session.no_autoflush:
            task = session.get(Task, obj.task_id)
            if task is None or task.user_id != obj.user_id or task.status == mapped:
                continue
            if directive != SYNC_FORCE and (
                sync_target_status(session, obj.status, obj.id, task) is None
            ):
                logger.info(
                    "task status sync: instance %s went %s, task %s stays %s",
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
