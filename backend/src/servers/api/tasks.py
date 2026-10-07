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

from shared.database.actor import Actor, set_session_actor
from shared.database.models import AgentInstance
from shared.database.session import get_db

# Reused human-facing query layer + DTOs. See module docstring for why this
# servers→backend import is deliberate rather than a duplicate implementation.
from backend.db import task_queries, task_timeline_queries
from backend.db.task_serializers import serialize_task, serialize_tasks
from backend.db.task_queries import (
    LabelNotFoundError,
    ParentTaskError,
    ProjectNotFoundError,
)
from backend.models import (
    CreateAgentTaskCommentRequest,
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
    if isinstance(exc, (ProjectNotFoundError, LabelNotFoundError)):
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
    db: Session = Depends(get_db),
) -> list[TaskResponse]:
    """``unfiled`` selects No-project tasks (``vicoa task ls --project none``);
    it cannot be combined with ``project_id``. ``label_id`` may repeat — a task
    must carry every one given. ``created_in_instance_id`` keeps the tasks
    created in that session."""
    if unfiled and project_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pass either project_id or unfiled, not both",
        )
    tasks = task_queries.list_tasks(
        db,
        _user_uuid(user_id),
        project_id=project_id,
        status=task_status,
        priority=task_priority,
        unfiled=unfiled,
        label_ids=label_id,
        created_in_instance_id=created_in_instance_id,
    )
    return serialize_tasks(db, tasks)


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
            creator_type=_author(resolved, calling)[0],
            created_in_instance_id=calling.id if calling is not None else None,
        )
    except (ProjectNotFoundError, LabelNotFoundError, ParentTaskError) as exc:
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
    fields = request.model_dump(exclude_unset=True, exclude={"agent_instance_id"})
    resolved = _user_uuid(user_id)
    existing = _require_task(db, resolved, task_id)
    _attribute_to_session(
        db, resolved, _calling_session(db, resolved, request.agent_instance_id)
    )
    try:
        task = task_queries.update_task(db, resolved, existing.id, fields)
    except (ProjectNotFoundError, LabelNotFoundError, ParentTaskError) as exc:
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
    try:
        task_timeline_queries.create_comment(
            db,
            task,
            resolved,
            request.body,
            parent_comment_id=request.parent_comment_id,
            author=_author(resolved, calling),
            agent_instance_id=calling.id if calling is not None else None,
        )
    except task_timeline_queries.CommentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return task_timeline_queries.build_timeline(db, task, resolved)
