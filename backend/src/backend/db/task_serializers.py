"""TaskResponse assembly — the fields a task can't answer alone.

`identifier` and `project_name` need the project row, `parent_title` needs the
parent row, and `assignee` needs a users/agent_profiles lookup. Doing those per
task would be three extra queries per row, so everything here is batched: one
pass over a whole list costs three queries total, and the single-task path is
the same function with a list of one.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from shared.database import Project, Task
from shared.database.task_identity import format_task_identifier

from ..models import TaskResponse
from .task_timeline_queries import PrincipalRef, resolve_principals


def serialize_tasks(db: Session, tasks: list[Task]) -> list[TaskResponse]:
    if not tasks:
        return []

    project_ids = {t.project_id for t in tasks if t.project_id is not None}
    projects: dict[UUID, tuple[str | None, str]] = (
        {
            row[0]: (row[1], row[2])
            for row in db.query(Project.id, Project.key, Project.name)
            .filter(Project.id.in_(project_ids))
            .all()
        }
        if project_ids
        else {}
    )

    parent_ids = {t.parent_task_id for t in tasks if t.parent_task_id is not None}
    parent_titles: dict[UUID, str] = {
        row[0]: row[1]
        for row in (
            db.query(Task.id, Task.title).filter(Task.id.in_(parent_ids)).all()
            if parent_ids
            else []
        )
    }

    refs: set[PrincipalRef] = {
        (t.assignee_type, t.assignee_id)
        for t in tasks
        if t.assignee_type is not None and t.assignee_id is not None
    }
    principals = resolve_principals(db, refs) if refs else {}

    out: list[TaskResponse] = []
    for task in tasks:
        response = TaskResponse.model_validate(task)
        # An unfiled task has no key to scope a number under: no identifier.
        if task.project_id is not None:
            project = projects.get(task.project_id)
            response.identifier = format_task_identifier(
                project[0] if project else None, task.number
            )
            response.project_name = project[1] if project else None
        else:
            response.identifier = None
        if task.parent_task_id is not None:
            response.parent_title = parent_titles.get(task.parent_task_id)
        if task.assignee_type is not None and task.assignee_id is not None:
            response.assignee = principals.get((task.assignee_type, task.assignee_id))
        out.append(response)
    return out


def serialize_task(db: Session, task: Task) -> TaskResponse:
    return serialize_tasks(db, [task])[0]
