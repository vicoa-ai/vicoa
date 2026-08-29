"""Task-tracker REST API for the agent-facing server.

The human dashboard (``backend`` process, Supabase JWT) has owned the task
tracker so far. This module exposes the same CRUD to CLI agents, which
authenticate against *this* server with their RS256 API-key JWT
(``get_current_user_id``). The business logic is reused verbatim from
``backend.db.task_queries`` — the same servers→backend reuse precedent as
``routers.py`` importing ``backend.db.queries`` — so the agent-facing and
human-facing task surfaces can never drift.

Tasks are user-scoped, not session-scoped: an agent acting for a user sees and
mutates that user's whole backlog, exactly as the user's web session would.
Kept in its own file to avoid bloating ``routers.py``.
"""

# NB: no ``from __future__ import annotations`` — it would stringify the
# ``-> None`` on the 204 DELETE, which FastAPI then resolves to ``NoneType``
# (truthy) and rejects as "204 must not have a response body".

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from shared.database.session import get_db

# Reused human-facing query layer + DTOs. See module docstring for why this
# servers→backend import is deliberate rather than a duplicate implementation.
from backend.db import task_queries
from backend.db.task_queries import (
    LabelNotFoundError,
    ParentTaskError,
    ProjectNotFoundError,
)
from backend.models import (
    CreateTaskRequest,
    TaskPriorityLiteral,
    TaskResponse,
    TaskStatusLiteral,
    UpdateTaskRequest,
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
    task_status: TaskStatusLiteral | None = Query(default=None, alias="status"),
    task_priority: TaskPriorityLiteral | None = Query(default=None, alias="priority"),
    db: Session = Depends(get_db),
) -> list[TaskResponse]:
    tasks = task_queries.list_tasks(
        db,
        _user_uuid(user_id),
        project_id=project_id,
        status=task_status,
        priority=task_priority,
    )
    return [TaskResponse.model_validate(t) for t in tasks]


@task_router.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task_endpoint(
    request: CreateTaskRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> TaskResponse:
    try:
        task = task_queries.create_task(
            db,
            _user_uuid(user_id),
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
        )
    except (ProjectNotFoundError, LabelNotFoundError, ParentTaskError) as exc:
        _raise_task_ref_errors(exc)
        raise  # unreachable; keeps the type checker satisfied
    return TaskResponse.model_validate(task)


@task_router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task_endpoint(
    task_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> TaskResponse:
    task = task_queries.get_task(db, _user_uuid(user_id), task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return TaskResponse.model_validate(task)


@task_router.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task_endpoint(
    task_id: UUID,
    request: UpdateTaskRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> TaskResponse:
    fields = request.model_dump(exclude_unset=True)
    try:
        task = task_queries.update_task(db, _user_uuid(user_id), task_id, fields)
    except (ProjectNotFoundError, LabelNotFoundError, ParentTaskError) as exc:
        _raise_task_ref_errors(exc)
        raise  # unreachable; keeps the type checker satisfied
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return TaskResponse.model_validate(task)


@task_router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task_endpoint(
    task_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> None:
    if not task_queries.delete_task(db, _user_uuid(user_id), task_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
