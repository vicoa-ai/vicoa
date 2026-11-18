"""Turning a person's action on a task into work for an agent.

plans/todos/task-assignment-agents.md. Two entry points feed the queue
(`task_dispatches`), both called inside the request's transaction, before its
commit, by the task query layer every surface already goes through:

* `on_assignee_changed` / `on_status_changed` — assigning a task to an agent
  profile, or moving an agent's task out of backlog, asks it to take the task
  over (Ownership mode).
* `on_comment_created` — a person's comment the agent should answer (Reply
  mode), routed by `route_comment`. That includes the answer to a question the
  agent asked them, which fires its wakeup (`shared/task_wakeups.py`).

The server-side dispatcher (`servers/scheduler/task_dispatcher.py`) delivers
the queue. This module only decides *whether* and *what*; it never talks to a
daemon, so both server processes can call it.

**Only a person starts a run.** A person is an actor of type ``user``: someone
in the dashboard, the CLI outside a session, or a session with no agent profile
(whose writes are already signed as the user). A session started from an agent
profile acts as that profile (``agent``), and every session this feature starts
is one, so nothing a dispatched agent does can dispatch another agent. That is
what rules out agent-to-agent loops: by construction, not by asking the agents
to behave.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.database.actor import Actor, session_actor
from shared.database.agent_profile_models import AgentProfile
from shared.database.enums import AgentStatus
from shared.database.liveness import machine_is_online
from shared.database.models import AgentInstance, Machine
from shared.database.task_dispatch_models import TaskDispatch
from shared.database.task_models import ProjectDirectory, Task, TaskComment
from shared.task_wakeups import agents_waiting_on

logger = logging.getLogger(__name__)

# A comment starting with this is a note between people: it wakes nobody.
NOTE_PREFIX = "/note"
# What the composer's @ picker inserts: `[@Name](vicoa://agent/<profile id>)`.
# Plain typed "@name" is deliberately not a mention — a name can collide, and a
# mention starts a run on someone's machine.
_AGENT_MENTION_RE = re.compile(
    r"\(vicoa://agent/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\)"
)
# A person, the same way: `[@Name](vicoa://user/<user id>)`. It tells them (a
# push), and nothing else: it never wakes an agent and never makes a question.
_USER_MENTION_RE = re.compile(
    r"\(vicoa://user/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\)"
)
# A task in these states is never started by an assignment.
_NO_START_STATUSES = frozenset({"backlog", "done", "cancelled"})
_CLOSED_STATUSES = frozenset({"done", "cancelled"})


def runs_on_closed_task(mode: str, trigger: str) -> bool:
    """What may still run on a Done or Cancelled task: an @mention's reply."""
    return mode == "reply" and trigger == "mentioned"


_NOTE_RE = re.compile(r"/note(?:\s|:|$)", re.IGNORECASE)


def is_note(body: str | None) -> bool:
    """`/note` as a word at the very start ("/notebook" is not a note)."""
    return _NOTE_RE.match((body or "").lstrip()) is not None


def _mentioned(pattern: re.Pattern[str], body: str | None) -> list[UUID]:
    seen: list[UUID] = []
    for match in pattern.finditer(body or ""):
        principal_id = UUID(match.group(1))
        if principal_id not in seen:
            seen.append(principal_id)
    return seen


def mentioned_profile_ids(body: str | None) -> list[UUID]:
    """Agent profiles a comment @mentions, in order, each once."""
    return _mentioned(_AGENT_MENTION_RE, body)


def mentioned_user_ids(body: str | None) -> list[UUID]:
    """People a comment @mentions, in order, each once."""
    return _mentioned(_USER_MENTION_RE, body)


def is_person(actor: Actor | None) -> bool:
    return actor is not None and actor.type == "user" and actor.id is not None


# --- Who may start a profile --------------------------------------------------


@dataclass(frozen=True)
class StartCheck:
    profile: AgentProfile | None
    # Why `profile` can't be started by this person, in words for the task chip.
    reason: str | None = None


def check_can_start(
    db: Session, profile_id: UUID, person_id: UUID, *, invited: bool = False
) -> StartCheck:
    """Whether `person_id` may start `profile_id` on its owner's machine.

    A personal profile: only its owner, unless the agent `invited` this
    person's comment by asking them a question; then their answer may wake it,
    since the agent (on its owner's behalf) is the one who asked. A team's
    profile has no single machine it belongs to yet, so v1 lets it be assigned
    but not started.
    """
    profile = db.get(AgentProfile, profile_id)
    if profile is None:
        return StartCheck(None, "agent not found")
    if profile.is_archived:
        return StartCheck(profile, "this agent is archived")
    if profile.team_id is not None:
        return StartCheck(profile, "team agents can't start runs yet")
    if profile.user_id != person_id and not invited:
        return StartCheck(profile, "only the agent's owner can start it")
    return StartCheck(profile)


# --- Where a new session runs --------------------------------------------------


@dataclass(frozen=True)
class Placement:
    machine_id: UUID | None
    directory: str | None
    machine_name: str | None = None
    online: bool = False
    # Set when no usable machine/folder was found.
    reason: str | None = None


def _machine_label(machine: Machine) -> str:
    return machine.display_name or machine.hostname or "computer"


def resolve_placement(
    db: Session,
    profile: AgentProfile,
    task: Task,
    *,
    machine_id: UUID | None = None,
    directory: str | None = None,
) -> Placement:
    """The machine and folder a new task session for `profile` starts in.

    Explicit choices (the assign dialog) win. Otherwise the profile's default
    machine, else the machine holding this task's project folder (the most
    recently seen one when there are several). The folder is the project's
    folder on that machine, else the profile's default project's.
    """
    owner = profile.user_id
    machine: Machine | None = None
    chosen = machine_id or profile.default_machine_id
    if chosen is not None:
        machine = (
            db.query(Machine)
            .filter(Machine.id == chosen, Machine.user_id == owner)
            .first()
        )
    if machine is None and task.project_id is not None:
        machine = (
            db.query(Machine)
            .join(ProjectDirectory, ProjectDirectory.machine_id == Machine.id)
            .filter(
                ProjectDirectory.project_id == task.project_id,
                ProjectDirectory.user_id == owner,
                Machine.user_id == owner,
            )
            .order_by(Machine.last_heartbeat_at.desc().nullslast())
            .first()
        )
    if machine is None:
        return Placement(
            None,
            None,
            reason="no computer: set one on the agent or add this project's folder",
        )

    folder = (directory or "").strip() or None
    if folder is None:
        for project_id in (task.project_id, profile.default_project_id):
            if project_id is None:
                continue
            row = (
                db.query(ProjectDirectory.local_path)
                .filter(
                    ProjectDirectory.project_id == project_id,
                    ProjectDirectory.machine_id == machine.id,
                    ProjectDirectory.user_id == owner,
                )
                .first()
            )
            if row is not None:
                folder = row[0]
                break
    label = _machine_label(machine)
    online = machine_is_online(machine.last_heartbeat_at)
    if folder is None:
        return Placement(
            machine.id,
            None,
            machine_name=label,
            online=online,
            reason=f"no folder for this project on {label}",
        )
    return Placement(machine.id, folder, machine_name=label, online=online)


@dataclass(frozen=True)
class MachineOption:
    machine_id: UUID
    name: str
    online: bool
    directory: str | None


def machine_options(
    db: Session, profile: AgentProfile, task: Task
) -> list[MachineOption]:
    """Every computer of the profile's owner, each with this task's project
    folder on it (if any) — the assign dialog's alternatives."""
    owner = profile.user_id
    folders: dict[UUID, str] = {}
    if task.project_id is not None:
        folders = {
            row[0]: row[1]
            for row in db.query(
                ProjectDirectory.machine_id, ProjectDirectory.local_path
            )
            .filter(
                ProjectDirectory.project_id == task.project_id,
                ProjectDirectory.user_id == owner,
            )
            .all()
        }
    machines = (
        db.query(Machine)
        .filter(Machine.user_id == owner)
        .order_by(Machine.last_heartbeat_at.desc().nullslast())
        .all()
    )
    return [
        MachineOption(
            machine_id=m.id,
            name=_machine_label(m),
            online=machine_is_online(m.last_heartbeat_at),
            directory=folders.get(m.id),
        )
        for m in machines
    ]


# --- The task session ---------------------------------------------------------


def task_session(
    db: Session, *, owner_id: UUID, task_id: UUID, profile_id: UUID
) -> AgentInstance | None:
    """The (profile, task) session later triggers go into: the newest one."""
    return (
        db.query(AgentInstance)
        .filter(
            AgentInstance.user_id == owner_id,
            AgentInstance.task_id == task_id,
            AgentInstance.agent_profile_id == profile_id,
            AgentInstance.status != AgentStatus.DELETED,
        )
        .order_by(AgentInstance.started_at.desc())
        .first()
    )


# --- The queue ----------------------------------------------------------------


@dataclass(frozen=True)
class RunOptions:
    """What the assign dialog (or `vicoa task update --no-start`) adds
    to an assignment. Not task fields: they shape the run it starts."""

    start: bool = True
    machine_id: UUID | None = None
    directory: str | None = None
    # "new" | "none"; None = the default (a new worktree).
    worktree: str | None = None


def _worktree_spec(choice: str | None) -> dict | None:
    if choice == "none":
        return {"mode": "none"}
    if choice in (None, "new"):
        return {"mode": "new"}
    return None


def _merge(
    row: TaskDispatch,
    *,
    mode: str,
    trigger: str,
    comment_id: UUID | None,
    requested_by: UUID | None,
    options: RunOptions | None,
) -> None:
    """Fold a later trigger into a still-queued dispatch. Ownership wins over
    Reply (an assignment is the bigger ask); the newest comment and the latest
    explicit choices win; nothing already chosen is cleared."""
    if mode == "ownership" and row.mode != "ownership":
        row.mode = "ownership"
        row.trigger = trigger
    elif row.mode == mode:
        row.trigger = trigger
    if comment_id is not None:
        row.trigger_comment_id = comment_id
    if requested_by is not None:
        row.requested_by_user_id = requested_by
    if options is not None:
        if options.machine_id is not None:
            row.machine_id = options.machine_id
        if options.directory:
            row.directory = options.directory
        if options.worktree is not None:
            row.worktree = _worktree_spec(options.worktree)
    row.detail = None
    row.next_attempt_at = datetime.now(timezone.utc)


def enqueue(
    db: Session,
    *,
    task: Task,
    profile: AgentProfile,
    mode: str,
    trigger: str,
    requested_by: UUID | None,
    comment_id: UUID | None = None,
    options: RunOptions | None = None,
) -> TaskDispatch:
    """Queue (or merge into the queued) dispatch for (task, profile)."""
    existing = (
        db.query(TaskDispatch)
        .filter(
            TaskDispatch.task_id == task.id,
            TaskDispatch.agent_profile_id == profile.id,
            TaskDispatch.state == "queued",
        )
        .with_for_update()
        .first()
    )
    if existing is not None:
        _merge(
            existing,
            mode=mode,
            trigger=trigger,
            comment_id=comment_id,
            requested_by=requested_by,
            options=options,
        )
        return existing

    row = TaskDispatch(
        user_id=profile.user_id,
        task_id=task.id,
        agent_profile_id=profile.id,
        mode=mode,
        trigger=trigger,
        trigger_comment_id=comment_id,
        requested_by_user_id=requested_by,
        machine_id=options.machine_id if options else None,
        directory=(options.directory or None) if options else None,
        worktree=_worktree_spec(options.worktree if options else None),
        state="queued",
        next_attempt_at=datetime.now(timezone.utc),
    )
    savepoint = db.begin_nested()
    try:
        db.add(row)
        db.flush()
        savepoint.commit()
        return row
    except IntegrityError:
        # A concurrent trigger queued one first (uq_task_dispatches_queued):
        # merge into that one instead.
        savepoint.rollback()
        winner = (
            db.query(TaskDispatch)
            .filter(
                TaskDispatch.task_id == task.id,
                TaskDispatch.agent_profile_id == profile.id,
                TaskDispatch.state == "queued",
            )
            .with_for_update()
            .one()
        )
        _merge(
            winner,
            mode=mode,
            trigger=trigger,
            comment_id=comment_id,
            requested_by=requested_by,
            options=options,
        )
        return winner


def record_refusal(
    db: Session,
    *,
    task: Task,
    profile: AgentProfile,
    mode: str,
    trigger: str,
    requested_by: UUID | None,
    reason: str,
) -> None:
    """A failed dispatch row, so an assignment that can't start says why on the
    task instead of silently doing nothing."""
    db.add(
        TaskDispatch(
            user_id=profile.user_id,
            task_id=task.id,
            agent_profile_id=profile.id,
            mode=mode,
            trigger=trigger,
            requested_by_user_id=requested_by,
            state="failed",
            detail=reason,
            next_attempt_at=datetime.now(timezone.utc),
        )
    )


def cancel_queued(
    db: Session, task_id: UUID, *, reason: str, profile_id: UUID | None = None
) -> int:
    """Cancel the task's waiting dispatches (all, or one profile's). Never
    touches a session that is already running: that is the Stop button's job."""
    query = db.query(TaskDispatch).filter(
        TaskDispatch.task_id == task_id, TaskDispatch.state == "queued"
    )
    if profile_id is not None:
        query = query.filter(TaskDispatch.agent_profile_id == profile_id)
    return query.update(
        {
            "state": "cancelled",
            "detail": reason,
            "updated_at": datetime.now(timezone.utc),
        },
        synchronize_session=False,
    )


def release_ownership(db: Session, task_id: UUID, profile_id: UUID) -> None:
    """The agent is no longer the assignee. What it was waiting to *take over*
    is cancelled; a comment it was asked to answer still deserves its answer,
    so a queued row carrying one becomes a plain Reply instead."""
    now = datetime.now(timezone.utc)
    rows = (
        db.query(TaskDispatch)
        .filter(
            TaskDispatch.task_id == task_id,
            TaskDispatch.agent_profile_id == profile_id,
            TaskDispatch.state == "queued",
        )
        .with_for_update()
        .all()
    )
    for row in rows:
        if row.trigger_comment_id is not None:
            if row.mode == "ownership":
                row.mode = "reply"
                row.trigger = "commented"
            continue
        row.state = "cancelled"
        row.detail = "unassigned"
        row.updated_at = now


# --- Hooks the task query layer calls -----------------------------------------


def _start_ownership(
    db: Session,
    task: Task,
    *,
    actor: Actor,
    trigger: str,
    options: RunOptions | None,
) -> None:
    if actor.id is None or task.assignee_id is None:
        return
    check = check_can_start(db, task.assignee_id, actor.id)
    if check.profile is None:
        return
    if check.reason is not None:
        record_refusal(
            db,
            task=task,
            profile=check.profile,
            mode="ownership",
            trigger=trigger,
            requested_by=actor.id,
            reason=check.reason,
        )
        return
    enqueue(
        db,
        task=task,
        profile=check.profile,
        mode="ownership",
        trigger=trigger,
        requested_by=actor.id,
        options=options,
    )


def on_assignee_changed(
    db: Session,
    task: Task,
    *,
    old_type: str | None,
    old_id: UUID | None,
    options: RunOptions | None = None,
) -> None:
    """The assignee moved (or was set on create). Cancel what the previous
    agent was still waiting to do; if a person handed the task to an agent and
    the task is live, ask the agent to take it over."""
    if (
        old_type == "agent"
        and old_id is not None
        and (task.assignee_type != "agent" or task.assignee_id != old_id)
    ):
        release_ownership(db, task.id, old_id)

    if task.assignee_type != "agent" or task.assignee_id is None:
        return
    if task.assignee_type == old_type and task.assignee_id == old_id:
        return
    if options is not None and not options.start:
        return
    if task.status in _NO_START_STATUSES:
        return
    actor = session_actor(db)
    if not is_person(actor):
        return
    assert actor is not None
    _start_ownership(db, task, actor=actor, trigger="assigned", options=options)


def on_status_changed(db: Session, task: Task, *, old_status: str) -> None:
    """Closing a task cancels its waiting dispatches. Moving an agent's task out
    of backlog starts it, unless the agent already has a session on it."""
    if task.status in _CLOSED_STATUSES:
        cancel_queued(db, task.id, reason=f"task {task.status}")
        return
    if old_status != "backlog" or task.status == "backlog":
        return
    if task.assignee_type != "agent" or task.assignee_id is None:
        return
    actor = session_actor(db)
    if not is_person(actor):
        return
    assert actor is not None
    profile = db.get(AgentProfile, task.assignee_id)
    if profile is None:
        return
    if task_session(
        db, owner_id=profile.user_id, task_id=task.id, profile_id=profile.id
    ):
        return
    _start_ownership(db, task, actor=actor, trigger="unblocked", options=None)


def route_comment(
    db: Session, task: Task, comment: TaskComment
) -> list[tuple[UUID, str]]:
    """Which agent profiles a person's comment is for, and why.

    Always: the agents waiting for its author's reply on this task
    (`answered`). Any comment of theirs fires those wakeups
    (`task_wakeups.on_comment_created`), so each agent that asked hears it,
    wherever on the task it was written. Then the first rule that applies:

    1. It @mentions agents → those.
    2. It replies in a thread an agent has written in → the latest such agent.
       (A reply in a thread with no agent in it stays between people.)
    3. It is top level on a task assigned to an agent → that agent.
    """
    routes: dict[UUID, str] = {
        profile_id: "answered"
        for profile_id in agents_waiting_on(db, task, comment.author_id)
    }
    for profile_id, trigger in _addressed_to(db, task, comment):
        routes.setdefault(profile_id, trigger)
    return list(routes.items())


def _addressed_to(
    db: Session, task: Task, comment: TaskComment
) -> list[tuple[UUID, str]]:
    """Rules 1-3 of `route_comment`."""
    mentioned = mentioned_profile_ids(comment.body)
    if mentioned:
        return [(profile_id, "mentioned") for profile_id in mentioned]
    if comment.parent_comment_id is not None:
        root = comment.parent_comment_id
        agent_author = (
            db.query(TaskComment.author_id)
            .filter(
                TaskComment.task_id == task.id,
                or_(TaskComment.id == root, TaskComment.parent_comment_id == root),
                TaskComment.author_type == "agent",
                TaskComment.deleted_at.is_(None),
                TaskComment.id != comment.id,
            )
            .order_by(TaskComment.created_at.desc())
            .first()
        )
        return [(agent_author[0], "replied")] if agent_author else []
    if task.assignee_type == "agent" and task.assignee_id is not None:
        return [(task.assignee_id, "commented")]
    return []


def on_comment_created(
    db: Session, task: Task, comment: TaskComment
) -> dict[UUID, TaskDispatch]:
    """A person commented: queue a Reply-mode dispatch for each agent it is for.
    Returns them by agent profile.

    On a Done or Cancelled task only an explicit @mention starts anything: a
    mention is a deliberate pick, while a comment or a reply there is usually
    people talking about finished work."""
    queued: dict[UUID, TaskDispatch] = {}
    if comment.author_type != "user" or is_note(comment.body):
        return queued
    person = comment.author_id
    routes = route_comment(db, task, comment)
    if task.status in _CLOSED_STATUSES:
        routes = [route for route in routes if route[1] == "mentioned"]
    for profile_id, trigger in routes:
        check = check_can_start(db, profile_id, person, invited=trigger == "answered")
        if check.profile is None or check.reason is not None:
            # A mention the person can't run is still a mention: the comment
            # posts, nothing starts. The composer's hint already said so.
            continue
        queued[profile_id] = enqueue(
            db,
            task=task,
            profile=check.profile,
            mode="reply",
            trigger=trigger,
            requested_by=person,
            comment_id=comment.id,
        )
    return queued


# --- What the task shows ------------------------------------------------------


def latest_dispatches(db: Session, task_ids: list[UUID]) -> dict[UUID, TaskDispatch]:
    """Each task's newest dispatch (its chip)."""
    if not task_ids:
        return {}
    rows = (
        db.query(TaskDispatch)
        .filter(TaskDispatch.task_id.in_(task_ids))
        .distinct(TaskDispatch.task_id)
        .order_by(TaskDispatch.task_id, TaskDispatch.created_at.desc())
        .all()
    )
    return {row.task_id: row for row in rows}


def busy_sessions(db: Session, *, owner_id: UUID, profile_id: UUID) -> int:
    """The profile's task sessions mid-turn now, plus dispatches being started
    — what the concurrency cap counts."""
    active = (
        db.query(AgentInstance.id)
        .filter(
            AgentInstance.user_id == owner_id,
            AgentInstance.agent_profile_id == profile_id,
            AgentInstance.task_id.isnot(None),
            AgentInstance.status == AgentStatus.ACTIVE,
        )
        .count()
    )
    starting = (
        db.query(TaskDispatch.id)
        .filter(
            and_(
                TaskDispatch.user_id == owner_id,
                TaskDispatch.agent_profile_id == profile_id,
                TaskDispatch.state == "dispatching",
            )
        )
        .count()
    )
    return active + starting
