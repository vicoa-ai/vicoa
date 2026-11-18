"""Task-tracker REST API for the agent-facing server.

The human dashboard (``backend`` process, Supabase JWT) has owned the task
tracker so far. This module exposes the same CRUD to CLI agents, which
authenticate against *this* server with their RS256 API-key JWT
(``get_current_user_id``). The business logic is reused verbatim from
``backend.db.task_queries`` — the same servers→backend reuse precedent as
``routers.py`` importing ``backend.db.queries`` — so the agent-facing and
human-facing task surfaces can never drift.

Tasks are user-scoped, not session-scoped: an agent acting for a user sees and
mutates that user's whole backlog, exactly as the user's web session would. The
task timeline (comments + activity) is exposed here too, read and write, so an
agent can report back on the task it was started from instead of only in a
transcript the user has to go looking for.

Kept in its own file to avoid bloating ``routers.py``.
"""

# NB: no ``from __future__ import annotations`` — it would stringify the
# ``-> None`` on the 204 DELETE, which FastAPI then resolves to ``NoneType``
# (truthy) and rejects as "204 must not have a response body".

from typing import Annotated, NamedTuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from sqlalchemy import case, func

from shared import access
from shared.database.actor import Actor, set_session_actor
from shared.database.agent_profile_models import AgentProfile
from shared.database.models import AgentInstance, User
from shared.database.session import get_db
from shared.database.task_dispatch_models import TaskDispatch
from shared.database.task_models import Task
from shared.database.task_wakeup_models import TaskWakeup

# Reused human-facing query layer + DTOs. See module docstring for why this
# servers→backend import is deliberate rather than a duplicate implementation.
from backend.db import task_queries, task_timeline_queries
from backend.db.task_serializers import serialize_task, serialize_tasks
from backend.db.task_queries import (
    AssigneeNotFoundError,
    LabelNotFoundError,
    ParentTaskError,
    ProjectNotFoundError,
)
from backend.models import (
    TASK_RUN_FIELDS,
    CreateAgentTaskCommentRequest,
    TaskAskRequest,
    CreateAgentTaskRequest,
    CreateTaskLabelRequest,
    TaskLabelResponse,
    TaskPriorityLiteral,
    TaskResponse,
    TaskStatusLiteral,
    TaskTimelineResponse,
    UpdateAgentTaskRequest,
)

from .auth import get_current_user_id

task_router = APIRouter(tags=["tasks"])


def _user_uuid(user_id: str) -> UUID:
    """Coerce the token's ``sub`` (a string) to the UUID the queries expect."""
    try:
        return UUID(user_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject is not a valid user id",
        ) from exc


def _raise_task_ref_errors(exc: Exception) -> None:
    """Map task-reference validation errors onto HTTP statuses.

    Mirrors ``backend/api/tasks.py`` so the CLI sees identical error codes
    whether it ever talked to the human-facing API or this one.
    """
    if isinstance(
        exc, (ProjectNotFoundError, LabelNotFoundError, AssigneeNotFoundError)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    if isinstance(exc, ParentTaskError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND
            if exc.not_found
            else status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    raise exc


@task_router.get("/tasks", response_model=list[TaskResponse])
def list_tasks_endpoint(
    user_id: Annotated[str, Depends(get_current_user_id)],
    project_id: UUID | None = None,
    unfiled: bool = False,
    task_status: TaskStatusLiteral | None = Query(default=None, alias="status"),
    task_priority: TaskPriorityLiteral | None = Query(default=None, alias="priority"),
    label_id: Annotated[list[UUID] | None, Query()] = None,
    created_in_instance_id: UUID | None = None,
    assignee: str | None = Query(default=None, max_length=64),
    waiting_on: str | None = Query(default=None, max_length=320),
    db: Session = Depends(get_db),
) -> list[TaskResponse]:
    """``unfiled`` selects No-project tasks (``vicoa task ls --project none``);
    it cannot be combined with ``project_id``. ``label_id`` may repeat — a task
    must carry every one given. ``created_in_instance_id`` keeps the tasks
    created in that session. ``assignee`` takes the same shorthand as
    ``vicoa task update --assignee`` (``me``, ``none``, an agent's name or an
    id); ``self`` is not accepted here (a listing names no session).
    ``waiting_on`` keeps the tasks with an open question to a person: ``me``,
    an email, a user id, or the display name of someone asked on your tasks."""
    if unfiled and project_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pass either project_id or unfiled, not both",
        )
    resolved = _user_uuid(user_id)
    assignee_id: UUID | None = None
    unassigned = False
    if assignee is not None and assignee.strip():
        kind, assignee_id = _resolve_assignee(db, resolved, None, assignee)
        unassigned = kind is None
    waiting_on_id: UUID | None = None
    if waiting_on is not None and waiting_on.strip():
        waiting_on_id = _waiting_on_user_id(db, resolved, waiting_on)
        if waiting_on_id is None:
            # Nobody by that name or address is asked anything here. An empty
            # list, not a 404: whether an address has an account is not this
            # listing's to say.
            return []
    tasks = task_queries.list_tasks(
        db,
        resolved,
        project_id=project_id,
        status=task_status,
        priority=task_priority,
        unfiled=unfiled,
        label_ids=label_id,
        created_in_instance_id=created_in_instance_id,
        assignee_id=assignee_id,
        unassigned=unassigned,
        waiting_on_user_id=waiting_on_id,
    )
    return serialize_tasks(db, tasks)


def _user_by_email(db: Session, email: str) -> UUID | None:
    return (
        db.query(User.id)
        .filter(func.lower(User.email) == email.strip().lower())
        .scalar()
    )


def _waiting_on_user_id(db: Session, user_id: UUID, value: str) -> UUID | None:
    """``task ls --waiting-on`` → a user id, or None when it names nobody."""
    raw = value.strip()
    if raw.lower() == "me":
        return user_id
    try:
        return UUID(raw)
    except ValueError:
        pass
    if "@" in raw:
        return _user_by_email(db, raw)
    # A name: only among the people asked something on the caller's own tasks,
    # so a listing never resolves an arbitrary account by its display name.
    return (
        db.query(User.id)
        .join(TaskWakeup, TaskWakeup.wait_for_user_id == User.id)
        .join(Task, Task.id == TaskWakeup.task_id)
        .filter(
            task_queries.owned_task_filter(user_id),
            TaskWakeup.kind == "reply",
            TaskWakeup.state == "waiting",
            func.lower(User.display_name) == raw.lower(),
        )
        .limit(1)
        .scalar()
    )


def _resolve_assignee(
    db: Session,
    user_id: UUID,
    calling: "_CallingSession | None",
    value: str,
) -> tuple[str | None, UUID | None]:
    """The CLI's ``--assignee`` shorthand → (assignee_type, assignee_id).

    ``me`` is the key's user; ``self`` the calling session's agent profile;
    ``none`` clears it; anything else is one of the user's own (personal,
    unarchived) agent profiles by name, case-insensitively, or an id.
    """
    raw = value.strip()
    lowered = raw.lower()
    if lowered == "me":
        return "user", user_id
    if lowered in ("none", "nobody", ""):
        return None, None
    if lowered == "self":
        if calling is None or calling.agent_profile_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="--assignee self needs a session started from an agent",
            )
        return "agent", calling.agent_profile_id
    try:
        as_id = UUID(raw)
    except ValueError:
        as_id = None
    if as_id is not None and as_id == user_id:
        return "user", user_id
    query = db.query(AgentProfile.id).filter(
        AgentProfile.user_id == user_id,
        AgentProfile.team_id.is_(None),
        AgentProfile.is_archived.is_(False),
    )
    if as_id is not None:
        query = query.filter(AgentProfile.id == as_id)
    else:
        query = query.filter(func.lower(AgentProfile.name) == lowered)
    row = query.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No agent named {raw!r} (see `vicoa agent ls`)",
        )
    return "agent", row[0]


def _assignee_fields(
    db: Session,
    user_id: UUID,
    calling: "_CallingSession | None",
    request: CreateAgentTaskRequest | UpdateAgentTaskRequest,
) -> dict:
    """The assignee pair to apply, from the shorthand or the explicit pair."""
    if request.assignee is None:
        return {}
    if (
        "assignee_type" in request.model_fields_set
        or "assignee_id" in request.model_fields_set
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pass assignee or assignee_type/assignee_id, not both",
        )
    kind, principal = _resolve_assignee(db, user_id, calling, request.assignee)
    return {"assignee_type": kind, "assignee_id": principal}


@task_router.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task_endpoint(
    request: CreateAgentTaskRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> TaskResponse:
    resolved = _user_uuid(user_id)
    calling = _calling_session(db, resolved, request.agent_instance_id)
    _attribute_to_session(db, resolved, calling)
    assignee = _assignee_fields(db, resolved, calling, request) or {
        "assignee_type": request.assignee_type,
        "assignee_id": request.assignee_id,
    }
    try:
        task = task_queries.create_task(
            db,
            resolved,
            title=request.title,
            description=request.description,
            project_id=request.project_id,
            status=request.status,
            priority=request.priority,
            position=request.position,
            parent_task_id=request.parent_task_id,
            label_ids=request.label_ids,
            start_date=request.start_date,
            due_date=request.due_date,
            assignee_type=assignee["assignee_type"],
            assignee_id=assignee["assignee_id"],
            creator_type=_author(resolved, calling)[0],
            created_in_instance_id=calling.id if calling is not None else None,
            run_options=request.run_options(),
        )
    except (
        ProjectNotFoundError,
        LabelNotFoundError,
        ParentTaskError,
        AssigneeNotFoundError,
    ) as exc:
        _raise_task_ref_errors(exc)
        raise  # unreachable; keeps the type checker satisfied
    return serialize_task(db, task)


@task_router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task_endpoint(
    task_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> TaskResponse:
    return serialize_task(db, _require_task(db, _user_uuid(user_id), task_id))


@task_router.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task_endpoint(
    task_id: str,
    request: UpdateAgentTaskRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> TaskResponse:
    fields = request.model_dump(
        exclude_unset=True,
        exclude={"agent_instance_id", "assignee", *TASK_RUN_FIELDS},
    )
    resolved = _user_uuid(user_id)
    existing = _require_task(db, resolved, task_id)
    calling = _calling_session(db, resolved, request.agent_instance_id)
    _attribute_to_session(db, resolved, calling)
    fields.update(_assignee_fields(db, resolved, calling, request))
    try:
        task = task_queries.update_task(
            db, resolved, existing.id, fields, run_options=request.run_options()
        )
    except (
        ProjectNotFoundError,
        LabelNotFoundError,
        ParentTaskError,
        AssigneeNotFoundError,
    ) as exc:
        _raise_task_ref_errors(exc)
        raise  # unreachable; keeps the type checker satisfied
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return serialize_task(db, task)


@task_router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task_endpoint(
    task_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> None:
    resolved = _user_uuid(user_id)
    task = _require_task(db, resolved, task_id)
    if not task_queries.delete_task(db, resolved, task.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )


# ---------------------------------------------------------------------------
# Labels — the caller's own vocabulary (`vicoa label ls` / `--label`)
#
# List and create only: the owner-only lens sees personal labels, never a
# team's, and renaming/recolouring/deleting a label stays a Settings-page act.
# ---------------------------------------------------------------------------


@task_router.get("/task-labels", response_model=list[TaskLabelResponse])
def list_labels_endpoint(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> list[TaskLabelResponse]:
    labels = task_queries.list_labels(db, _user_uuid(user_id))
    return [TaskLabelResponse.model_validate(label) for label in labels]


@task_router.post(
    "/task-labels",
    response_model=TaskLabelResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_label_endpoint(
    request: CreateTaskLabelRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> TaskLabelResponse:
    if request.team_id is not None:
        # A team vocabulary is a sharing-lens concept; this surface is owner-only.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Team labels are managed from the dashboard",
        )
    label = task_queries.create_label(
        db, _user_uuid(user_id), name=request.name, color=request.color
    )
    return TaskLabelResponse.model_validate(label)


# ---------------------------------------------------------------------------
# Comments — the agent's half of the task timeline (`vicoa task comment`)
#
# Read and write only. Editing, deleting and reacting stay human-facing: an
# agent revising or removing its own words after the fact is a rewrite of the
# record the human is reading, and a reaction from an agent is noise.
# ---------------------------------------------------------------------------


def _require_task(db: Session, user_id: UUID, task_id: str):
    """The user-scoped resolve every task route here starts from.

    Takes a UUID *or* a "VIC-42" identifier. That matters most on this router:
    the CLI is an agent's only task entrypoint, and both the agent and the human
    instructing it see the identifier — asking either of them for a UUID means
    asking for something neither has.

    It is also what keeps `task_comments` scoped, since that table carries no
    `user_id` of its own (the author need not be the task's owner once sharing
    lands) — exactly as in `backend/api/tasks.py`.
    """
    task = task_queries.resolve_task(db, user_id, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return task


class _CallingSession(NamedTuple):
    id: UUID
    agent_profile_id: UUID | None


def _calling_session(
    db: Session, user_id: UUID, agent_instance_id: UUID | None
) -> _CallingSession | None:
    """The caller's own session the request names, if any.

    `vicoa task create|update|comment` run inside a Vicoa session names it
    (from `VICOA_AGENT_INSTANCE_ID`). Scoped by `user_id`: naming someone
    else's session must not borrow their agent's name or put their session on
    your task. An unknown or foreign id is ignored rather than refused — a
    stale environment must not cost the write itself.
    """
    if agent_instance_id is None:
        return None
    row = (
        db.query(AgentInstance.id, AgentInstance.agent_profile_id)
        .filter(
            AgentInstance.id == agent_instance_id,
            AgentInstance.user_id == user_id,
        )
        .first()
    )
    return _CallingSession(row[0], row[1]) if row is not None else None


def _author(user_id: UUID, calling: _CallingSession | None) -> tuple[str, UUID]:
    """Whose name goes on the write.

    The user's, unless the calling session was started from an agent profile —
    then the profile's, so the timeline can say "Claude commented" instead of
    attributing the agent's words to the human.
    """
    if calling is not None and calling.agent_profile_id is not None:
        return ("agent", calling.agent_profile_id)
    return ("user", user_id)


def _attribute_to_session(
    db: Session, user_id: UUID, calling: _CallingSession | None
) -> None:
    """Attribute the activity this request generates to the calling session,
    marked `direct`: the session changed the task itself, as opposed to the
    task following the session's status (`shared/database/tasks.py`)."""
    if calling is None:
        return
    actor_type, actor_id = _author(user_id, calling)
    set_session_actor(
        db,
        Actor(
            type=actor_type,
            id=actor_id,
            agent_instance_id=calling.id,
            direct=True,
        ),
    )


@task_router.get("/tasks/{task_id}/timeline", response_model=TaskTimelineResponse)
def get_task_timeline_endpoint(
    task_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> TaskTimelineResponse:
    """Comments and activity together — the same payload the web detail page
    renders, so an agent reads exactly what its user sees."""
    resolved = _user_uuid(user_id)
    task = _require_task(db, resolved, task_id)
    return task_timeline_queries.build_timeline(db, task, resolved)


@task_router.post(
    "/tasks/{task_id}/comments",
    response_model=TaskTimelineResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task_comment_endpoint(
    task_id: str,
    request: CreateAgentTaskCommentRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> TaskTimelineResponse:
    resolved = _user_uuid(user_id)
    task = _require_task(db, resolved, task_id)
    calling = _calling_session(db, resolved, request.agent_instance_id)
    ask_user_id = (
        _addressee(db, resolved, task, calling, request.ask)
        if request.ask is not None
        else None
    )
    try:
        task_timeline_queries.create_comment(
            db,
            task,
            resolved,
            request.body,
            parent_comment_id=request.parent_comment_id,
            author=_author(resolved, calling),
            agent_instance_id=calling.id if calling is not None else None,
            ask_user_id=ask_user_id,
        )
    except task_timeline_queries.CommentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return task_timeline_queries.build_timeline(db, task, resolved)


def _requester_of_run(
    db: Session, task: Task, calling: _CallingSession, audience: set[UUID]
) -> UUID | None:
    """The person whose action started the calling session's current run: the
    requester of the newest dispatch delivered into it, one on this task first.
    Only someone who can still see the task."""
    rows = (
        db.query(TaskDispatch.requested_by_user_id)
        .filter(
            TaskDispatch.agent_instance_id == calling.id,
            TaskDispatch.requested_by_user_id.isnot(None),
        )
        .order_by(
            case((TaskDispatch.task_id == task.id, 0), else_=1),
            TaskDispatch.created_at.desc(),
        )
        .limit(5)
        .all()
    )
    for (person,) in rows:
        if person in audience:
            return person
    return None


def _addressee(
    db: Session,
    user_id: UUID,
    task: Task,
    calling: _CallingSession | None,
    ask: TaskAskRequest,
) -> UUID:
    """Whom `vicoa task comment --ask [--to …]` asks (task-questions plan, Q2-Q4).

    Only an agent asks: the calling session must be one started from an agent
    profile. ``to`` is ``me`` (the key's user), an email, a user id, or a display
    name, and must be someone who can see the task; otherwise a 400 that lists
    who can be asked, by name and id (never by address). Without ``to``: the
    person whose action started this run, else the session's owner."""
    if calling is None or calling.agent_profile_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="--ask needs a session started from an agent",
        )
    audience = access.task_audience(db, task)
    if ask.to is None or not ask.to.strip():
        return _requester_of_run(db, task, calling, audience) or user_id
    raw = ask.to.strip()
    person: UUID | None = None
    if raw.lower() == "me":
        person = user_id
    else:
        try:
            person = UUID(raw)
        except ValueError:
            if "@" in raw:
                person = _user_by_email(db, raw)
            else:
                named = [
                    row[0]
                    for row in db.query(User.id)
                    .filter(
                        User.id.in_(audience),
                        func.lower(User.display_name) == raw.lower(),
                    )
                    .all()
                ]
                person = named[0] if len(named) == 1 else None
    if person is not None and person in audience:
        return person
    names = [
        f"{row[1] or 'Unnamed'} ({row[0]})"
        for row in db.query(User.id, User.display_name)
        .filter(User.id.in_(audience))
        .order_by(func.lower(User.display_name))
        .all()
    ]
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Can't ask {raw!r}: only someone who can see this task can be asked. "
            f"Pass --to with one of: {', '.join(names)}"
        ),
    )
