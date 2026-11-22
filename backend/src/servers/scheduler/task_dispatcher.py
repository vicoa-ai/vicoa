"""The task dispatch sweep (plans/todos/task-assignment-agents.md).

Delivers `task_dispatches`: each queued row asks one agent profile to act on
one task. Like the automation sweep, it lives in the `server` process because
that is where the daemon RPC registry is.

One task session per (profile, task). A dispatch goes into it when it exists:
a message when its agent is live (queued behind a running turn), a resume on
its machine when it stopped. Only when there is no session, or it can't be
resumed, does a new one start — with a line telling the agent it starts fresh.
"The task session" is one filed under the task (`agent_instances.task_id`,
the **Linked** rows of the task's Sessions list), not a session that only
created, changed, commented on or referenced it. So an agent that asked its
question from an automation run gets the answer in a new session, and with no
Linked session on the task that new one has no pointer back to the run.
A new one starts in the task's folder: the worktree an earlier session on the
task worked in, else the project's own folder. Vicoa never makes a worktree
for it; the brief tells the agent to make one itself when the work changes code
in a git repository (`WORKTREE_RULE`).

The claim runs in one short transaction (`FOR UPDATE SKIP LOCKED`, so two
sweeps never take the same row): it checks the profile's concurrency cap,
works out where a new session would run and what the agent is told, and marks
the row `dispatching`. The RPC happens after commit; its outcome lands in a
second short transaction. A row left `dispatching` by a crash is failed after
`STALE_DISPATCHING`, visibly, rather than retried into a duplicate session.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, attributes

from backend.db.task_timeline_queries import resolve_principals
from shared.agent_profile_resolution import resolve_automation_config
from shared.config import settings
from shared.database import (
    AgentInstance,
    Project,
    Task,
    TaskActivity,
    TaskComment,
    TaskDispatch,
)
from shared.database.agent_profile_models import AgentProfile
from shared.database.enums import AgentStatus
from shared.database.session import SessionLocal
from shared.database.task_identity import format_task_identifier
from shared.task_dispatch import (
    busy_sessions,
    check_can_start,
    is_note,
    resolve_placement,
    runs_on_closed_task,
    task_session,
)
from shared.session_resume import expand_project_path
from shared.task_dispatch_prompts import (
    EarlierSession,
    QuotedComment,
    SinceHandover,
    ownership_prompt,
    reply_prompt,
    system_prompt_with_brief,
    task_brief,
    with_brief,
)
from shared.websocket.connection_manager import connection_manager
from shared.websocket.envelope import build_instance_update
from shared.websocket.in_tx import after_commit
from shared.websocket.protocol import watcher_room
from servers.profile_provenance import STAMP_DELAYS

from .dispatch import DispatchResult, dispatch_automation
from .session_dispatch import deliver_to_session

logger = logging.getLogger(__name__)

SWEEP_INTERVAL = 3.0  # seconds: a person is waiting on the other end
CLAIM_LIMIT = 20
# A profile at its cap, or a machine that's offline, is looked at again after:
BUSY_RETRY = timedelta(seconds=5)
OFFLINE_RETRY = timedelta(seconds=60)
STALE_DISPATCHING = timedelta(minutes=5)
# Comments a few seconds older than the dispatch still count as "since" it: the
# row is created in the comment's own transaction, a moment after its insert.
_SINCE_SLACK = timedelta(seconds=5)
# `instance_metadata` flag: this session has the task brief.
TASK_BRIEF_KEY = "task_brief"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _SpawnPlan:
    """One way to start a new session for the dispatch: where, and what it is told."""

    machine_id: UUID
    # Run in it as it is: never a new worktree.
    directory: str
    prompt: str


@dataclass
class _Claim:
    id: UUID
    user_id: UUID
    task_id: UUID
    profile_id: UUID
    # The (agent, task) session a prompt goes into first, and that prompt. A
    # resume carries the brief in `system_prompt`; a message into a live
    # session that never had it carries it in `message_prompt` instead.
    session_id: UUID | None
    prompt: str
    message_prompt: str
    session_config: dict
    # The profile's instructions plus the task brief, for resuming
    # `session_id`: with the worktree rule only if a dispatch started it.
    system_prompt: str
    # The same for a session started here, which always has the rule.
    spawn_system_prompt: str
    # How to start a new session when there is none or it can't be resumed,
    # tried in order: the task's own worktree first, then the project folder.
    spawns: list[_SpawnPlan]
    # Why there is nowhere to start one, when `spawns` is empty.
    placement_problem: str | None
    # What a new session is titled: the task, so no model has to name it.
    title: str


def _task_identifier(db: Session, task: Task) -> str | None:
    """ "VIC-42" for a task filed under a project, None for one that isn't."""
    if task.project_id is None or task.number is None:
        return None
    key = db.query(Project.key).filter(Project.id == task.project_id).scalar()
    return format_task_identifier(key, task.number) or None


def _task_ref(db: Session, task: Task) -> str:
    """How a message and its commands name the task."""
    return _task_identifier(db, task) or str(task.id)


def _session_title(db: Session, task: Task) -> str:
    """ "VIC-42: Fix the login" for a filed task, its title alone otherwise."""
    identifier = _task_identifier(db, task)
    return f"{identifier}: {task.title}" if identifier else task.title


def _pending_comments(
    db: Session, task_id: UUID, since: datetime, trigger_comment_id: UUID | None
) -> list[QuotedComment]:
    """People's comments since `since`, oldest first, with who wrote them. A
    trigger comment older than that (the dispatch was queued late) still counts."""
    rows = (
        db.query(TaskComment)
        .filter(
            TaskComment.task_id == task_id,
            TaskComment.author_type == "user",
            TaskComment.deleted_at.is_(None),
            or_(
                TaskComment.created_at >= since - _SINCE_SLACK,
                TaskComment.id == trigger_comment_id,
            ),
        )
        .order_by(TaskComment.created_at.asc())
        .all()
    )
    kept = [c for c in rows if not is_note(c.body)]
    refs = {("user", c.author_id) for c in kept}
    names = resolve_principals(db, refs) if refs else {}
    out: list[QuotedComment] = []
    for comment in kept:
        principal = names.get(("user", comment.author_id))
        out.append(
            QuotedComment(
                id=comment.id,
                thread_id=comment.parent_comment_id or comment.id,
                author=(principal.name if principal and principal.name else "Someone"),
                body=comment.body,
            )
        )
    return out


_EDIT_WORDS = {
    "description_changed": "the description was edited",
    "title_changed": "the title was changed",
}


def _since_handover(
    db: Session, task: Task, profile: AgentProfile
) -> SinceHandover | None:
    """What changed since this agent last handed the task over, or None when it
    never had it. Only people's doings count: the agent knows its own."""
    row = (
        db.query(TaskActivity.created_at)
        .filter(
            TaskActivity.task_id == task.id,
            TaskActivity.action == "assigned",
            TaskActivity.details["from"].astext == str(profile.id),
        )
        .order_by(TaskActivity.created_at.desc())
        .first()
    )
    if row is None:
        return None
    at: datetime = row[0]
    comments = _pending_comments(db, task.id, at + _SINCE_SLACK, None)
    edits: list[str] = []
    status_to: str | None = None
    for action, details in (
        db.query(TaskActivity.action, TaskActivity.details)
        .filter(
            TaskActivity.task_id == task.id,
            TaskActivity.created_at > at,
            TaskActivity.actor_type == "user",
            TaskActivity.action.in_(
                ["description_changed", "title_changed", "status_changed"]
            ),
        )
        .order_by(TaskActivity.created_at.asc())
        .all()
    ):
        if action == "status_changed":
            status_to = str((details or {}).get("to") or "") or status_to
        elif _EDIT_WORDS[action] not in edits:
            edits.append(_EDIT_WORDS[action])
    if status_to:
        edits.append(f"the status was changed to {status_to}")
    return SinceHandover(
        at=at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        comments=comments,
        edits=edits,
    )


def _latest_task_session(
    db: Session, task_id: UUID, owner_id: UUID
) -> AgentInstance | None:
    """The task's newest session by anyone's agent (or none)."""
    return (
        db.query(AgentInstance)
        .filter(
            AgentInstance.user_id == owner_id,
            AgentInstance.task_id == task_id,
            AgentInstance.status != AgentStatus.DELETED,
        )
        .order_by(AgentInstance.started_at.desc())
        .first()
    )


def _worktree_folder(instance: AgentInstance) -> tuple[UUID, str] | None:
    """(machine, folder) when the session ran in a worktree: the task's worktree,
    which a later session on the task continues in."""
    meta = instance.instance_metadata or {}
    if (
        not meta.get("worktree_name")
        or instance.machine_id is None
        or not instance.project
    ):
        return None
    return instance.machine_id, expand_project_path(instance.project, instance.home_dir)


def _plan(
    db: Session,
    row: TaskDispatch,
    task: Task,
    profile: AgentProfile,
    session: AgentInstance | None,
) -> tuple[str, list[_SpawnPlan], str | None]:
    """(prompt for the existing session, ways to start a new one, why none)."""
    ref = _task_ref(db, task)
    comments = _pending_comments(db, task.id, row.created_at, row.trigger_comment_id)
    since = _since_handover(db, task, profile) if row.mode == "ownership" else None
    assigned_by = None
    if row.requested_by_user_id is not None:
        ref_key = ("user", row.requested_by_user_id)
        principal = resolve_principals(db, {ref_key}).get(ref_key)
        assigned_by = principal.name if principal else None

    def build(*, continuity: bool, earlier: EarlierSession | None) -> str:
        if row.mode == "ownership":
            return ownership_prompt(
                ref=ref,
                title=task.title,
                assigned_by=assigned_by,
                comments=comments,
                since=since,
                earlier=earlier,
                continuity=continuity,
            )
        return reply_prompt(
            ref=ref,
            title=task.title,
            trigger=row.trigger,
            comments=comments,
            earlier=earlier,
            continuity=continuity,
        )

    prompt = build(continuity=False, earlier=None)
    # The work so far: this agent's own session, else whoever worked on it last.
    prior = session or _latest_task_session(db, task.id, profile.user_id)
    prior_agent = None
    if prior is not None and prior.agent_profile_id not in (None, profile.id):
        other = db.get(AgentProfile, prior.agent_profile_id)
        prior_agent = other.name if other is not None else None
    lost = session is not None  # a fresh start loses this agent's own context

    spawns: list[_SpawnPlan] = []
    # A computer or folder picked in the assign dialog beats the task's worktree.
    # (`row.worktree` is no longer read: Vicoa doesn't make task worktrees.)
    chose = row.machine_id is not None or bool(row.directory)
    folder = _worktree_folder(prior) if prior is not None and not chose else None
    if prior is not None and folder is not None:
        spawns.append(
            _SpawnPlan(
                machine_id=folder[0],
                directory=folder[1],
                prompt=build(
                    continuity=lost,
                    earlier=EarlierSession(prior.id, prior_agent, same_folder=True),
                ),
            )
        )
    placement = resolve_placement(
        db, profile, task, machine_id=row.machine_id, directory=row.directory
    )
    if placement.machine_id is not None and placement.directory:
        # The folder as it is. The agent makes a worktree itself if the work
        # changes code (`WORKTREE_RULE`); reading and answering need none.
        spawns.append(
            _SpawnPlan(
                machine_id=placement.machine_id,
                directory=placement.directory,
                prompt=build(
                    continuity=lost,
                    earlier=(
                        EarlierSession(prior.id, prior_agent, same_folder=False)
                        if prior is not None
                        else None
                    ),
                ),
            )
        )
    return prompt, spawns, placement.reason


def _fail_stale_blocking(db: Session, now: datetime) -> None:
    db.query(TaskDispatch).filter(
        TaskDispatch.state == "dispatching",
        TaskDispatch.updated_at < now - STALE_DISPATCHING,
    ).update(
        {
            "state": "failed",
            "detail": "interrupted while starting; assign again or comment to retry",
            "updated_at": now,
        },
        synchronize_session=False,
    )


def _claim_blocking() -> list[_Claim]:
    now = _utcnow()
    claims: list[_Claim] = []
    with SessionLocal() as db:
        _fail_stale_blocking(db, now)
        rows = (
            db.query(TaskDispatch)
            .filter(TaskDispatch.state == "queued", TaskDispatch.next_attempt_at <= now)
            .order_by(TaskDispatch.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(CLAIM_LIMIT)
            .all()
        )
        busy: dict[UUID, int] = {}
        for row in rows:
            task = db.get(Task, row.task_id)
            profile = db.get(AgentProfile, row.agent_profile_id)
            if task is None or profile is None:
                row.state, row.detail = "cancelled", "task or agent deleted"
                continue
            if task.status in ("done", "cancelled") and not runs_on_closed_task(
                row.mode, row.trigger
            ):
                row.state, row.detail = "cancelled", f"task {task.status}"
                continue
            check = check_can_start(db, profile.id, profile.user_id)
            if check.reason is not None:
                row.state, row.detail = "failed", check.reason
                continue

            session = task_session(
                db, owner_id=profile.user_id, task_id=task.id, profile_id=profile.id
            )
            if (
                session is not None
                and session.rate_limited_until is not None
                and session.rate_limited_until > now
            ):
                row.next_attempt_at = session.rate_limited_until
                row.detail = "waiting for the agent's rate limit to reset"
                continue
            # A message into a turn that is already running needs no slot: it
            # waits behind that turn in the same session.
            live_turn = (
                session is not None
                and session.status == AgentStatus.ACTIVE
                and connection_manager.is_session_connected(str(session.id))
            )
            if not live_turn:
                count = busy.get(profile.id)
                if count is None:
                    count = busy_sessions(
                        db, owner_id=profile.user_id, profile_id=profile.id
                    )
                cap = max(1, profile.max_concurrent_sessions)
                if count >= cap:
                    row.detail = f"queued: {count} of {cap} sessions busy"
                    row.next_attempt_at = now + BUSY_RETRY
                    busy[profile.id] = count
                    continue
                busy[profile.id] = count + 1

            prompt, spawns, problem = _plan(db, row, task, profile, session)
            resolved = resolve_automation_config(
                db,
                agent_profile_id=profile.id,
                session_config=None,
                owner_id=profile.user_id,
            )
            # A live session that was never given the brief gets it in front of
            # its first task message (its system prompt can't change mid-run).
            has_brief = session is not None and bool(
                (session.instance_metadata or {}).get(TASK_BRIEF_KEY)
            )
            # Resumed, a session keeps the brief it started with: the worktree
            # rule only if a dispatch started it, not a person.
            resume_brief = task_brief(
                dispatch_started=session is not None
                and started_by_dispatch(db, profile.user_id, session.id)
            )

            row.state = "dispatching"
            row.attempts = (row.attempts or 0) + 1
            row.detail = None
            claims.append(
                _Claim(
                    id=row.id,
                    user_id=profile.user_id,
                    task_id=task.id,
                    profile_id=profile.id,
                    session_id=session.id if session is not None else None,
                    prompt=prompt,
                    message_prompt=prompt if has_brief else with_brief(prompt),
                    session_config=resolved.session_config,
                    system_prompt=system_prompt_with_brief(
                        resolved.system_prompt, resume_brief
                    ),
                    spawn_system_prompt=system_prompt_with_brief(
                        resolved.system_prompt, task_brief(dispatch_started=True)
                    ),
                    spawns=spawns,
                    placement_problem=problem,
                    title=_session_title(db, task),
                )
            )
        db.commit()
    return claims


def _finish_blocking(
    dispatch_id: UUID,
    *,
    state: str,
    detail: str | None = None,
    instance_id: UUID | None = None,
) -> None:
    now = _utcnow()
    with SessionLocal() as db:
        row = db.get(TaskDispatch, dispatch_id)
        if row is None:
            return
        row.state = state
        row.detail = detail
        if instance_id is not None:
            row.agent_instance_id = instance_id
        if state in ("delivered", "resumed", "started"):
            row.delivered_at = now
            if instance_id is not None:
                _mark_brief(db, instance_id)
        db.commit()


def _mark_brief(db: Session, instance_id: UUID) -> None:
    """The session now has the task brief (system prompt, or its first task
    message): a manual resume re-attaches it (`brief_for_resume_blocking`)."""
    instance = db.get(AgentInstance, instance_id)
    if instance is None:
        return
    meta = dict(instance.instance_metadata or {})
    if meta.get(TASK_BRIEF_KEY):
        return
    meta[TASK_BRIEF_KEY] = True
    instance.instance_metadata = meta
    attributes.flag_modified(instance, "instance_metadata")


def _mark_brief_blocking(user_id: UUID, instance_id: UUID) -> bool:
    """Flag a registered session as carrying the brief; False while its row is
    still missing (the daemon returns the id before the agent registers)."""
    with SessionLocal() as db:
        found = (
            db.query(AgentInstance.id)
            .filter(AgentInstance.id == instance_id, AgentInstance.user_id == user_id)
            .first()
        )
        if found is None:
            return False
        _mark_brief(db, instance_id)
        db.commit()
        return True


_brief_stamps: set[asyncio.Task] = set()


async def _mark_brief_when_registered(user_id: UUID, instance_id: UUID) -> None:
    for delay in STAMP_DELAYS:
        try:
            if await asyncio.to_thread(_mark_brief_blocking, user_id, instance_id):
                return
        except Exception:  # noqa: BLE001 — never break a spawn over a flag
            logger.exception("failed to flag the task brief on %s", instance_id)
            return
        await asyncio.sleep(delay)


def mark_brief_in_background(user_id: UUID, instance_id: UUID) -> None:
    """A session started from a task (the task page's Start session) got the
    brief in its system prompt: flag it once it registers, so a later task
    message doesn't repeat the brief and a Resume brings it back."""
    task = asyncio.create_task(_mark_brief_when_registered(user_id, instance_id))
    _brief_stamps.add(task)
    task.add_done_callback(_brief_stamps.discard)


def task_visible_blocking(user_id: UUID, task_id: UUID) -> bool:
    """Whether the person starting a session can see the task it is for."""
    from backend.db.task_queries import get_task

    with SessionLocal() as db:
        return get_task(db, user_id, task_id, sharing=True) is not None


def brief_for_resume_blocking(user_id: UUID, instance_id: UUID) -> str | None:
    """The task brief, when the session being resumed carries one. Called by the
    spawn path a person's Resume goes through, so a task session never comes
    back without the rules it was started with."""
    with SessionLocal() as db:
        meta = (
            db.query(AgentInstance.instance_metadata)
            .filter(AgentInstance.id == instance_id, AgentInstance.user_id == user_id)
            .scalar()
        )
        if not (isinstance(meta, dict) and meta.get(TASK_BRIEF_KEY)):
            return None
        return task_brief(
            dispatch_started=started_by_dispatch(db, user_id, instance_id)
        )


def started_by_dispatch(db: Session, user_id: UUID, instance_id: UUID) -> bool:
    """Whether a dispatch started this session (rather than a person, from the
    task page or elsewhere): only such a session gets the worktree rule."""
    return (
        db.query(TaskDispatch.id)
        .filter(
            TaskDispatch.user_id == user_id,
            TaskDispatch.agent_instance_id == instance_id,
            TaskDispatch.state == "started",
        )
        .first()
        is not None
    )


def _requeue_blocking(dispatch_id: UUID, *, detail: str, delay: timedelta) -> None:
    """Back to `queued` to be tried again. If a newer trigger queued its own row
    for the same (task, agent) meanwhile, fold this one into it instead (the
    partial unique index allows one queued row per pair)."""
    now = _utcnow()
    with SessionLocal() as db:
        row = db.get(TaskDispatch, dispatch_id)
        if row is None:
            return
        row.state = "queued"
        row.detail = detail
        row.next_attempt_at = now + delay
        try:
            db.commit()
            return
        except IntegrityError:
            db.rollback()
        row = db.get(TaskDispatch, dispatch_id)
        if row is None:
            return
        newer = (
            db.query(TaskDispatch)
            .filter(
                TaskDispatch.task_id == row.task_id,
                TaskDispatch.agent_profile_id == row.agent_profile_id,
                TaskDispatch.state == "queued",
            )
            .with_for_update()
            .first()
        )
        if newer is not None and row.mode == "ownership" and newer.mode != "ownership":
            newer.mode, newer.trigger = "ownership", row.trigger
        row.state = "cancelled"
        row.detail = "merged into a newer request"
        db.commit()


def _stamp_task_session_blocking(
    owner_id: UUID,
    instance_id: UUID,
    profile_id: UUID,
    task_id: UUID,
    dispatch_id: UUID,
) -> bool:
    """Link a freshly spawned session to its agent and its task once its row
    exists. Linking the task is what makes it *the* task session later
    triggers go into, and what moves a todo task to in_progress
    (`shared/database/tasks.py`). False while the row is still missing."""
    with SessionLocal() as db:
        instance = (
            db.query(AgentInstance)
            .filter(AgentInstance.id == instance_id, AgentInstance.user_id == owner_id)
            .first()
        )
        if instance is None:
            return False
        instance.agent_profile_id = profile_id
        instance.task_id = task_id
        _mark_brief(db, instance_id)
        row = db.get(TaskDispatch, dispatch_id)
        if row is not None:
            row.agent_instance_id = instance_id
        db.flush()
        # The link lands seconds after the session appeared, so a page already
        # open on it learns its task from this frame, not from a reload.
        payload = build_instance_update(instance)
        rooms = [
            f"user:{owner_id}:user-scoped",
            f"user:{owner_id}:session:{instance_id}",
            watcher_room(str(instance_id)),
        ]
        after_commit(
            db,
            lambda: connection_manager.broadcast_update(str(owner_id), payload, rooms),
        )
        db.commit()
        return True


class TaskDispatcher:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._closed = False
        self._background: set[asyncio.Task] = set()

    async def start(self) -> None:
        if not settings.enable_websocket:
            logger.info("task dispatcher disabled (enable_websocket=false)")
            return
        if self._task is not None:
            return
        self._closed = False
        self._task = asyncio.create_task(self._run())
        logger.info("task dispatcher started (sweep=%.0fs)", SWEEP_INTERVAL)

    async def stop(self) -> None:
        self._closed = True
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 — never let shutdown raise
            logger.exception("task dispatcher shutdown error")
        self._task = None

    async def _run(self) -> None:
        while not self._closed:
            try:
                await self.sweep_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — one bad sweep must not kill the loop
                logger.exception("task dispatch sweep failed")
            await asyncio.sleep(SWEEP_INTERVAL)

    async def sweep_once(self) -> None:
        claims = await asyncio.to_thread(_claim_blocking)
        if claims:
            logger.info("task dispatch: delivering %d", len(claims))
            await asyncio.gather(
                *(self._process(claim) for claim in claims), return_exceptions=True
            )

    async def _process(self, claim: _Claim) -> None:
        try:
            await self._deliver(claim)
        except Exception as exc:  # noqa: BLE001 — record it on the task, don't lose it
            logger.exception("task dispatch %s failed", claim.id)
            await asyncio.to_thread(
                _finish_blocking, claim.id, state="failed", detail=f"error: {exc}"
            )

    async def _deliver(self, claim: _Claim) -> None:
        if claim.session_id is not None:
            result = await deliver_to_session(
                user_id=claim.user_id,
                instance_id=claim.session_id,
                prompt=claim.prompt,
                message_prompt=claim.message_prompt,
                system_prompt=claim.system_prompt,
                marker=("task_dispatch_id", str(claim.id)),
                extra_metadata={"task_id": str(claim.task_id)},
            )
            if result.status == "fired":
                await asyncio.to_thread(
                    _finish_blocking,
                    claim.id,
                    state="resumed" if result.via == "resume" else "delivered",
                    instance_id=claim.session_id,
                )
                return
            if result.status == "skipped":
                await asyncio.to_thread(
                    _finish_blocking,
                    claim.id,
                    state="delivered",
                    detail="merged into the message still waiting in the session",
                    instance_id=claim.session_id,
                )
                return
            if result.status == "missed_offline":
                await asyncio.to_thread(
                    _requeue_blocking,
                    claim.id,
                    detail="waiting for the computer to come online",
                    delay=OFFLINE_RETRY,
                )
                return
            # The session is gone or its agent refused the resume: start a new
            # one, which says so.
            logger.info(
                "task dispatch %s: session %s not resumable (%s); starting fresh",
                claim.id,
                claim.session_id,
                result.detail,
            )
        await self._spawn(claim)

    async def _spawn(self, claim: _Claim) -> None:
        if not claim.spawns:
            await asyncio.to_thread(
                _finish_blocking,
                claim.id,
                state="failed",
                detail=claim.placement_problem or "no computer or folder to run in",
            )
            return
        last: DispatchResult | None = None
        for plan in claim.spawns:
            result: DispatchResult = await dispatch_automation(
                user_id=claim.user_id,
                machine_id=plan.machine_id,
                directory=plan.directory,
                session_config=claim.session_config,
                prompt=plan.prompt,
                system_prompt=claim.spawn_system_prompt,
                title=claim.title,
            )
            if result.status == "fired":
                await asyncio.to_thread(_finish_blocking, claim.id, state="started")
                if result.agent_instance_id:
                    self._in_background(
                        self._stamp(claim, UUID(result.agent_instance_id))
                    )
                return
            if result.status == "missed_offline":
                await asyncio.to_thread(
                    _requeue_blocking,
                    claim.id,
                    detail="waiting for the computer to come online",
                    delay=OFFLINE_RETRY,
                )
                return
            # Refused (the task's worktree is gone, say): try the next way.
            logger.info(
                "task dispatch %s: start in %s refused (%s)",
                claim.id,
                plan.directory,
                result.detail,
            )
            last = result
        await asyncio.to_thread(
            _finish_blocking,
            claim.id,
            state="failed",
            detail=(last.detail if last else None)
            or "the computer refused to start the agent",
        )

    async def _stamp(self, claim: _Claim, instance_id: UUID) -> None:
        for delay in STAMP_DELAYS:
            try:
                if await asyncio.to_thread(
                    _stamp_task_session_blocking,
                    claim.user_id,
                    instance_id,
                    claim.profile_id,
                    claim.task_id,
                    claim.id,
                ):
                    return
            except Exception:  # noqa: BLE001 — never break the sweep over a stamp
                logger.exception("failed to link session %s to its task", instance_id)
                return
            await asyncio.sleep(delay)
        logger.warning(
            "task session %s never registered; task %s stays unlinked",
            instance_id,
            claim.task_id,
        )

    def _in_background(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
