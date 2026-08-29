"""Projects & tasks API (tasks-and-projects plan §3).

Human-authored task tracker: issue-style tasks grouped by project. Distinct
from agent sessions — the Kanban tab is sessions; this is the human backlog.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from shared.database.models import User
from shared.database.session import get_db

from ..auth.dependencies import get_current_user
from ..db import task_queries
from ..db.queries import list_task_instances
from ..db.task_queries import (
    InboxImmutableError,
    LabelNotFoundError,
    MachineNotFoundError,
    ParentTaskError,
    ProjectNotFoundError,
)
from ..models import (
    AgentInstanceResponse,
    CreateProjectRequest,
    CreateTaskLabelRequest,
    CreateTaskRequest,
    ProjectResponse,
    SetProjectDirectoryRequest,
    TaskLabelResponse,
    TaskPriorityLiteral,
    TaskResponse,
    TaskStatusLiteral,
    UpdateProjectRequest,
    UpdateTaskLabelRequest,
    UpdateTaskRequest,
)

router = APIRouter(tags=["tasks"])


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects_endpoint(
    include_archived: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProjectResponse]:
    projects = task_queries.list_projects(db, current_user.id, include_archived)
    return [ProjectResponse.model_validate(p) for p in projects]


@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project_endpoint(
    request: CreateProjectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    project = task_queries.create_project(
        db,
        current_user.id,
        name=request.name,
        color=request.color,
        icon=request.icon,
        git_remote_url=request.git_remote_url,
    )
    return ProjectResponse.model_validate(project)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project_endpoint(
    project_id: UUID,
    request: UpdateProjectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    fields = request.model_dump(exclude_unset=True)
    try:
        project = task_queries.update_project(db, current_user.id, project_id, fields)
    except InboxImmutableError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return ProjectResponse.model_validate(project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_endpoint(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        deleted = task_queries.delete_project(db, current_user.id, project_id)
    except InboxImmutableError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )


@router.put("/projects/{project_id}/directories", response_model=ProjectResponse)
def set_project_directory_endpoint(
    project_id: UUID,
    request: SetProjectDirectoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Link the project to a path on one machine (upsert on that machine)."""
    try:
        project = task_queries.set_project_directory(
            db,
            current_user.id,
            project_id,
            machine_id=request.machine_id,
            local_path=request.local_path.strip(),
        )
    except InboxImmutableError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except MachineNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return ProjectResponse.model_validate(project)


@router.delete(
    "/projects/{project_id}/directories/{machine_id}",
    response_model=ProjectResponse,
)
def delete_project_directory_endpoint(
    project_id: UUID,
    machine_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Unlink a machine. Idempotent — unlinking twice is not an error."""
    project = task_queries.delete_project_directory(
        db, current_user.id, project_id, machine_id
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return ProjectResponse.model_validate(project)


@router.get("/task-labels", response_model=list[TaskLabelResponse])
def list_labels_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TaskLabelResponse]:
    labels = task_queries.list_labels(db, current_user.id)
    return [TaskLabelResponse.model_validate(label) for label in labels]


@router.post(
    "/task-labels",
    response_model=TaskLabelResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_label_endpoint(
    request: CreateTaskLabelRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskLabelResponse:
    label = task_queries.create_label(
        db, current_user.id, name=request.name, color=request.color
    )
    return TaskLabelResponse.model_validate(label)


@router.patch("/task-labels/{label_id}", response_model=TaskLabelResponse)
def update_label_endpoint(
    label_id: UUID,
    request: UpdateTaskLabelRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskLabelResponse:
    label = task_queries.update_label(
        db, current_user.id, label_id, request.model_dump(exclude_unset=True)
    )
    if label is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Label not found"
        )
    return TaskLabelResponse.model_validate(label)


@router.delete("/task-labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_label_endpoint(
    label_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not task_queries.delete_label(db, current_user.id, label_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Label not found"
        )


def _raise_task_ref_errors(exc: Exception) -> None:
    """Map task-reference validation errors onto HTTP statuses."""
    if isinstance(exc, ProjectNotFoundError) or isinstance(exc, LabelNotFoundError):
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


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks_endpoint(
    project_id: UUID | None = None,
    task_status: TaskStatusLiteral | None = Query(default=None, alias="status"),
    task_priority: TaskPriorityLiteral | None = Query(default=None, alias="priority"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TaskResponse]:
    tasks = task_queries.list_tasks(
        db,
        current_user.id,
        project_id=project_id,
        status=task_status,
        priority=task_priority,
    )
    return [TaskResponse.model_validate(t) for t in tasks]


@router.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task_endpoint(
    request: CreateTaskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskResponse:
    try:
        task = task_queries.create_task(
            db,
            current_user.id,
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


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task_endpoint(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskResponse:
    task = task_queries.get_task(db, current_user.id, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return TaskResponse.model_validate(task)


@router.get("/tasks/{task_id}/sessions", response_model=list[AgentInstanceResponse])
def list_task_sessions_endpoint(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AgentInstanceResponse]:
    """Agent sessions started from this task, most recent first."""
    if task_queries.get_task(db, current_user.id, task_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return list_task_instances(db, current_user.id, task_id)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task_endpoint(
    task_id: UUID,
    request: UpdateTaskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskResponse:
    fields = request.model_dump(exclude_unset=True)
    try:
        task = task_queries.update_task(db, current_user.id, task_id, fields)
    except (ProjectNotFoundError, LabelNotFoundError, ParentTaskError) as exc:
        _raise_task_ref_errors(exc)
        raise  # unreachable; keeps the type checker satisfied
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return TaskResponse.model_validate(task)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task_endpoint(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not task_queries.delete_task(db, current_user.id, task_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
