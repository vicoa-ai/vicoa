"""Read-only project API for the agent-facing server.

Three CLI flags take a project (``task ls|create|update --project``,
``agent add --project``) and until now nothing on this server could say what
the projects *are* — the dashboard's ``GET /projects`` takes an IdP token, not
an API key. This exposes the list and a single-project read to CLI agents
(``vicoa project ls`` / ``vicoa project get``), reusing ``backend.db.task_queries``
verbatim, the same servers→backend precedent as ``tasks.py``.

Owner-only by design (AGENTS.md "Extension points"): ``sharing=False`` in the
query layer, so a grantee's or a team's projects never appear here. That is
also what lets ``/projects/{ref}`` take a task key ("VIC") — keys are unique
per owner, not globally.

Read-only: creating, renaming, archiving, icons and directory links stay on
the human API. ``task_count`` is filled here because a terminal listing needs
it and the dashboard has a sidebar for it.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from shared.database.session import get_db
from shared.database.task_models import Project

# Reused human-facing query layer + DTOs. See module docstring for why this
# servers→backend import is deliberate rather than a duplicate implementation.
from backend.db import task_queries
from backend.models import ProjectResponse

from .auth import get_current_user_id

project_router = APIRouter(tags=["projects"])


def _user_uuid(user_id: str) -> UUID:
    """Coerce the token's ``sub`` (a string) to the UUID the queries expect."""
    try:
        return UUID(user_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject is not a valid user id",
        ) from exc


def _owner_response(project: Project, task_count: int | None = None) -> ProjectResponse:
    """Serialize for the owner. `role`/`scopes` describe the caller and default
    to least privilege on the model; on this owner-only surface the caller is
    the owner of everything it can see, so say so rather than under-report."""
    response = ProjectResponse.model_validate(project)
    response.role = "owner"
    response.scopes = ["tasks", "sessions"]
    response.task_count = task_count
    return response


@project_router.get("/projects", response_model=list[ProjectResponse])
def list_projects_endpoint(
    user_id: Annotated[str, Depends(get_current_user_id)],
    include_archived: bool = False,
    db: Session = Depends(get_db),
) -> list[ProjectResponse]:
    """The caller's own projects in the dashboard's order (manual rank, then
    most recent session activity), each with its open-task count."""
    resolved = _user_uuid(user_id)
    rows = task_queries.list_projects(db, resolved, include_archived)
    counts = task_queries.task_counts_by_project(
        db, resolved, [project.id for project, _, _ in rows]
    )
    out: list[ProjectResponse] = []
    for project, last_activity_at, position in rows:
        response = _owner_response(project, counts.get(project.id, 0))
        response.last_activity_at = last_activity_at
        response.position = position
        out.append(response)
    return out


@project_router.get("/projects/{ref}", response_model=ProjectResponse)
def get_project_endpoint(
    ref: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """One project by UUID or task key ("VIC"); 404 for anything the caller
    does not own, an unknown key included — never 422, the route takes
    whatever was typed."""
    resolved = _user_uuid(user_id)
    project = task_queries.resolve_project(db, resolved, ref)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    counts = task_queries.task_counts_by_project(db, resolved, [project.id])
    return _owner_response(project, counts.get(project.id, 0))
