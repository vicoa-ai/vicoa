"""Projects & tasks API (tasks-and-projects plan §3).

Human-authored task tracker: issue-style tasks grouped by project. Distinct
from agent sessions — the Kanban tab is sessions; this is the human backlog.
"""

import logging
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response
from sqlalchemy.orm import Session

from shared import project_icons, storage
from shared.database.models import User
from shared.database.session import get_db
from shared.images import InvalidImageError, process_image

from ..auth.dependencies import get_current_user
from ..db import task_queries, task_timeline_queries
from ..db.queries import list_task_instances
from ..db.task_serializers import serialize_task, serialize_tasks
from ..db.task_queries import (
    AssigneeNotFoundError,
    InboxImmutableError,
    LabelNotFoundError,
    ProjectKeyTakenError,
    MachineNotFoundError,
    ParentTaskError,
    ProjectNotFoundError,
)
from ..models import (
    AgentInstanceResponse,
    CreateTaskCommentRequest,
    ToggleTaskReactionRequest,
    TaskTimelineResponse,
    UpdateTaskCommentRequest,
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

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks"])

# Bounds the request body for an icon upload; decode memory is bounded
# separately by shared.images.MAX_PIXELS.
MAX_ICON_UPLOAD_BYTES = 8 * 1024 * 1024
# The raster types process_image emits — served inline; anything else is a bug.
_INLINE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects_endpoint(
    background_tasks: BackgroundTasks,
    include_archived: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProjectResponse]:
    projects = task_queries.list_projects(db, current_user.id, include_archived)
    # Lazy, best-effort default-icon seed (§4e): first fetch of a git-backed
    # project with no icon set kicks off a background owner-avatar seed. The
    # task re-checks eligibility, so duplicate enqueues are harmless.
    for project in projects:
        if (
            not project.is_inbox
            and project.git_remote_url
            and project.icon_source is None
            and not project.icon_image_uri
            # An emoji is an explicit choice — never overwrite it with a git seed.
            and not project.icon
        ):
            background_tasks.add_task(project_icons.seed_project_icon, project.id)
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
    except ProjectKeyTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
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


@router.put("/projects/{project_id}/icon", response_model=ProjectResponse)
def upload_project_icon_endpoint(
    project_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Set a project's image icon from an upload (§4d). 'user' beats a git seed."""
    project = task_queries.get_accessible_project(db, current_user.id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    raw = file.file.read(MAX_ICON_UPLOAD_BYTES + 1)
    if len(raw) > MAX_ICON_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds {MAX_ICON_UPLOAD_BYTES // (1024 * 1024)}MB limit",
        )
    if not raw:
        raise HTTPException(status_code=400, detail="File is empty")
    try:
        processed = process_image(raw)
    except InvalidImageError as exc:
        raise HTTPException(
            status_code=400, detail="Not a valid image in a supported format"
        ) from exc

    key = storage.project_icon_key(str(project_id))
    try:
        storage.upload_attachment(key, processed.data, processed.mime_type)
    except Exception as exc:
        logger.exception("project icon upload to S3 failed")
        raise HTTPException(status_code=502, detail="Failed to store image") from exc

    updated = task_queries.set_project_icon(
        db,
        current_user.id,
        project_id,
        icon_image_uri=project_icons.icon_served_url(project_id),
        icon_source="user",
    )
    assert updated is not None  # access re-checked above under the same session
    return ProjectResponse.model_validate(updated)


@router.get("/projects/{project_id}/icon")
def get_project_icon_endpoint(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Serve a project's icon bytes (uploaded or git-seeded)."""
    project = task_queries.get_accessible_project(db, current_user.id, project_id)
    if project is None or not project.icon_image_uri:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project icon not found"
        )
    try:
        data, content_type = storage.download_object(
            storage.project_icon_key(str(project_id))
        )
    except Exception as exc:
        logger.exception("project icon download from S3 failed")
        raise HTTPException(status_code=502, detail="Failed to fetch image") from exc
    if content_type not in _INLINE_IMAGE_TYPES:
        content_type = "application/octet-stream"
    return Response(
        content=data,
        media_type=content_type,
        headers={
            # Short-lived: the URL is stable across replacements, so clients
            # cache-bust with the project's updated_at instead of relying on this.
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/projects/{project_id}/icon", response_model=ProjectResponse)
def delete_project_icon_endpoint(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Reset the icon to the generated default (drops the image AND emoji, and
    pins icon_source so the git seed does not re-add an image)."""
    project = task_queries.get_accessible_project(db, current_user.id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    if project.icon_image_uri:
        try:
            storage.delete_object(storage.project_icon_key(str(project_id)))
        except Exception:
            # Orphaned S3 object is harmless; never fail the reset on it.
            logger.warning("project icon S3 delete failed for %s", project_id)
    updated = task_queries.reset_project_icon(db, current_user.id, project_id)
    assert updated is not None
    return ProjectResponse.model_validate(updated)


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
    return serialize_tasks(db, tasks)


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
            assignee_type=request.assignee_type,
            assignee_id=request.assignee_id,
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
    return serialize_task(db, task)


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


# ---------------------------------------------------------------------------
# Task timeline — comments, reactions, activity (collaboration §3.5)
#
# There is no WebSocket channel for tasks in this phase, by decision (§9):
# comments ride refresh-on-focus plus a short SWR interval on an open task.
# Polling hits this stateless, horizontally scalable app; the relay is pinned to
# workers=1 and already carries every daemon socket.
# ---------------------------------------------------------------------------


def _require_task(db: Session, user_id: UUID, task_id: UUID):
    """The user-scoped resolve every timeline route starts from.

    The timeline tables carry no `user_id` of their own, so this is what keeps
    them scoped: nothing below reaches a comment or activity row except through
    a task this user owns.
    """
    task = task_queries.get_task(db, user_id, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return task


@router.get("/tasks/{task_id}/timeline", response_model=TaskTimelineResponse)
def get_task_timeline_endpoint(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskTimelineResponse:
    """Comments and activity together — one round trip, one SWR key."""
    task = _require_task(db, current_user.id, task_id)
    return task_timeline_queries.build_timeline(db, task, current_user.id)


@router.post(
    "/tasks/{task_id}/comments",
    response_model=TaskTimelineResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task_comment_endpoint(
    task_id: UUID,
    request: CreateTaskCommentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskTimelineResponse:
    """Post a comment and return the whole timeline.

    Returning the timeline rather than the one new comment costs nothing (the
    caller was about to revalidate anyway) and closes the window where an
    optimistic append and a background poll disagree about ordering.
    """
    task = _require_task(db, current_user.id, task_id)
    task_timeline_queries.create_comment(db, task, current_user.id, request.body)
    return task_timeline_queries.build_timeline(db, task, current_user.id)


@router.patch(
    "/tasks/{task_id}/comments/{comment_id}", response_model=TaskTimelineResponse
)
def update_task_comment_endpoint(
    task_id: UUID,
    comment_id: UUID,
    request: UpdateTaskCommentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskTimelineResponse:
    task = _require_task(db, current_user.id, task_id)
    try:
        task_timeline_queries.update_comment(
            db, task, comment_id, current_user.id, request.body
        )
    except task_timeline_queries.CommentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return task_timeline_queries.build_timeline(db, task, current_user.id)


@router.delete(
    "/tasks/{task_id}/comments/{comment_id}", response_model=TaskTimelineResponse
)
def delete_task_comment_endpoint(
    task_id: UUID,
    comment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskTimelineResponse:
    task = _require_task(db, current_user.id, task_id)
    try:
        task_timeline_queries.delete_comment(db, task, comment_id, current_user.id)
    except task_timeline_queries.CommentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return task_timeline_queries.build_timeline(db, task, current_user.id)


@router.put("/tasks/{task_id}/reactions", response_model=TaskTimelineResponse)
def toggle_task_reaction_endpoint(
    task_id: UUID,
    request: ToggleTaskReactionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskTimelineResponse:
    """Add or remove one emoji. PUT, not POST: the operation is idempotent per
    (user, target, emoji) — clicking twice lands back where it started."""
    task = _require_task(db, current_user.id, task_id)
    if request.target_type == "task" and request.target_id != task.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_id must be this task",
        )
    try:
        task_timeline_queries.toggle_reaction(
            db,
            current_user.id,
            request.target_type,
            request.target_id,
            request.emoji,
        )
    except task_timeline_queries.UnknownReactionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported reaction",
        ) from exc
    return task_timeline_queries.build_timeline(db, task, current_user.id)
