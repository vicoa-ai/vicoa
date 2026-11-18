"""TaskResponse assembly — the fields a task can't answer alone.

`identifier` and `project_name` need the project row, `parent_title` needs the
parent row, and `assignee` needs a users/agent_profiles lookup. Doing those per
task would be three extra queries per row, so everything here is batched: one
pass over a whole list costs three queries total, and the single-task path is
the same function with a list of one.
"""

import re
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from shared.database import AgentInstance, Project, Task, TaskActivity, TaskComment
from shared.database.task_identity import format_task_identifier
from shared.task_dispatch import latest_dispatches
from shared.task_wakeups import waiting_on_people

from ..models import (
    PrincipalResponse,
    TaskDispatchSummary,
    TaskQuestionResponse,
    TaskResponse,
)
from .task_timeline_queries import PrincipalRef, resolve_principals


def _latest_assignments(
    db: Session, tasks: list[Task]
) -> dict[UUID, tuple[datetime, PrincipalRef | None]]:
    """Each assigned task's latest `assigned` row: when, and by whom."""
    assigned = [t.id for t in tasks if t.assignee_id is not None]
    if not assigned:
        return {}
    rows = (
        db.query(
            TaskActivity.task_id,
            TaskActivity.created_at,
            TaskActivity.actor_type,
            TaskActivity.actor_id,
        )
        .filter(TaskActivity.task_id.in_(assigned), TaskActivity.action == "assigned")
        .distinct(TaskActivity.task_id)
        .order_by(TaskActivity.task_id, TaskActivity.created_at.desc())
        .all()
    )
    out: dict[UUID, tuple[datetime, PrincipalRef | None]] = {}
    for task_id, created_at, actor_type, actor_id in rows:
        ref: PrincipalRef | None = (
            (actor_type, actor_id)
            if actor_type in ("user", "agent") and actor_id is not None
            else None
        )
        out[task_id] = (created_at, ref)
    return out


_PREVIEW_CHARS = 280
# A list row shows the question as plain text: links keep their text (an
# `@agent` mention included), emphasis and code markers go.
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_MARKERS = re.compile(r"(\*\*|__|`+|~~)")
_MD_LINE_PREFIX = re.compile(r"(?m)^\s{0,3}(?:#{1,6}\s+|>\s?|[-*+]\s+)")


def _plain_preview(body: str | None) -> str:
    text = _MD_LINK.sub(r"\1", body or "")
    text = _MD_LINE_PREFIX.sub("", text)
    text = _MD_MARKERS.sub("", text)
    return " ".join(text.split())


# A question posted just before the reassignment (the usual order) still counts.
_PREVIEW_SLACK = timedelta(minutes=10)


def _assigner_comments(
    db: Session,
    tasks: list[Task],
    assignments: dict[UUID, tuple[datetime, PrincipalRef | None]],
) -> dict[UUID, tuple[UUID, str]]:
    """For tasks a principal assigned to a person: that principal's latest
    comment since (comment id, trimmed body)."""
    wanted: dict[UUID, tuple[datetime, PrincipalRef]] = {}
    for t in tasks:
        if t.assignee_type != "user":
            continue
        assignment = assignments.get(t.id)
        if assignment is None or assignment[1] is None:
            continue
        wanted[t.id] = (assignment[0], assignment[1])
    if not wanted:
        return {}
    since = min(at for at, _ in wanted.values()) - _PREVIEW_SLACK
    rows = (
        db.query(
            TaskComment.task_id,
            TaskComment.id,
            TaskComment.author_type,
            TaskComment.author_id,
            TaskComment.body,
            TaskComment.created_at,
        )
        .filter(
            TaskComment.task_id.in_(list(wanted)),
            TaskComment.deleted_at.is_(None),
            TaskComment.created_at >= since,
        )
        .order_by(TaskComment.created_at.desc())
        .all()
    )
    out: dict[UUID, tuple[UUID, str]] = {}
    for task_id, comment_id, author_type, author_id, body, created_at in rows:
        if task_id in out:
            continue
        at, by = wanted[task_id]
        if (author_type, author_id) != by or created_at < at - _PREVIEW_SLACK:
            continue
        text = _plain_preview(body)
        if len(text) > _PREVIEW_CHARS:
            text = text[: _PREVIEW_CHARS - 1] + "…"
        out[task_id] = (comment_id, text)
    return out


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

    assignments = _latest_assignments(db, tasks)
    assigner_comments = _assigner_comments(db, tasks, assignments)
    questions = waiting_on_people(db, [t.id for t in tasks])
    dispatches = latest_dispatches(db, [t.id for t in tasks])
    session_ids = {
        d.agent_instance_id for d in dispatches.values() if d.agent_instance_id
    }
    session_status: dict[UUID, str] = {
        row[0]: row[1].value if hasattr(row[1], "value") else str(row[1])
        for row in (
            db.query(AgentInstance.id, AgentInstance.status)
            .filter(AgentInstance.id.in_(session_ids))
            .all()
            if session_ids
            else []
        )
    }

    refs: set[PrincipalRef] = {
        (t.assignee_type, t.assignee_id)
        for t in tasks
        if t.assignee_type is not None and t.assignee_id is not None
    }
    refs |= {ref for _, ref in assignments.values() if ref is not None}
    for waiting in questions.values():
        for w in waiting:
            if w.wait_for_user_id is not None:
                refs.add(("user", w.wait_for_user_id))
            refs.add(("agent", w.agent_profile_id))
    principals: dict[PrincipalRef, PrincipalResponse] = (
        resolve_principals(db, refs) if refs else {}
    )

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
            assignment = assignments.get(task.id)
            if assignment is not None:
                response.assigned_at = assignment[0]
                if assignment[1] is not None:
                    response.assigned_by = principals.get(assignment[1])
            preview = assigner_comments.get(task.id)
            if preview is not None:
                response.assigner_comment_id, response.assigner_comment = preview
        # A reply wakeup still waiting is a question someone hasn't answered.
        response.open_questions = [
            TaskQuestionResponse(
                comment_id=w.source_comment_id,
                addressee=principals[("user", w.wait_for_user_id)],
                asked_by=principals[("agent", w.agent_profile_id)],
                asked_at=w.created_at,
            )
            for w in questions.get(task.id, ())
            if w.wait_for_user_id is not None and w.source_comment_id is not None
        ]
        dispatch = dispatches.get(task.id)
        if dispatch is not None:
            summary = TaskDispatchSummary.model_validate(dispatch)
            if dispatch.agent_instance_id is not None:
                summary.session_status = session_status.get(dispatch.agent_instance_id)
            response.dispatch = summary
        out.append(response)
    return out


def serialize_task(db: Session, task: Task) -> TaskResponse:
    return serialize_tasks(db, [task])[0]
