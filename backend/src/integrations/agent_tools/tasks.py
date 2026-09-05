"""Vicoa task-backlog tools: list, get, create, update, delete.

Backed by ``servers/api/tasks.py``, which exposes the same CRUD the dashboard
uses to an API-key caller. Tasks are user-scoped, not session-scoped: an agent
acting for a user sees that user's whole backlog, exactly as their web session
would.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from integrations.agent_tools.context import (
    AgentToolContext,
    AgentToolError,
    as_rows,
    optional_str,
    parse_positive_int,
    require_str,
)
from integrations.agent_tools.registry import AgentTool, ToolResult, object_schema


#: Mirrors ``TaskStatusLiteral`` / ``TaskPriorityLiteral`` in ``backend/models.py``.
#: Duplicated rather than imported: this module runs inside the wrapper process
#: on a user's machine, which has no reason to import the backend's API models.
TASK_STATUSES = (
    "backlog",
    "todo",
    "in_progress",
    "in_review",
    "done",
    "blocked",
    "cancelled",
)
TASK_PRIORITIES = ("urgent", "high", "medium", "low", "none")

_MAX_ROWS = 50


def _check_enum(value: str, allowed: tuple[str, ...], name: str) -> str:
    if value not in allowed:
        raise AgentToolError(
            f"`{name}` must be one of {', '.join(allowed)} — got {value!r}"
        )
    return value


def _task_line(row: Dict[str, Any]) -> str:
    return (
        f"- {row.get('id')} · [{row.get('status')}] {row.get('title')}"
        f" · priority {row.get('priority')}"
    )


async def list_tasks(
    context: AgentToolContext, arguments: Dict[str, Any]
) -> ToolResult:
    params: Dict[str, Any] = {
        "limit": parse_positive_int(
            arguments.get("limit"), name="limit", default=25, maximum=_MAX_ROWS
        )
    }
    status = optional_str(arguments, "status")
    if status:
        params["status"] = _check_enum(status, TASK_STATUSES, "status")
    project_id = optional_str(arguments, "project_id")
    if project_id:
        params["project_id"] = project_id
    payload = await context.client.request("GET", "/api/v1/tasks", params=params)
    rows = as_rows(payload)
    if not rows:
        return ToolResult(text="No tasks found.", details={"tasks": []})
    lines: List[str] = [f"{len(rows)} task(s):", *[_task_line(row) for row in rows]]
    return ToolResult(text="\n".join(lines), details={"tasks": rows})


async def get_task(context: AgentToolContext, arguments: Dict[str, Any]) -> ToolResult:
    task_id = require_str(arguments, "task_id")
    row = await context.client.request("GET", f"/api/v1/tasks/{task_id}")
    return ToolResult(
        text=json.dumps(row, indent=2, default=str), details={"task": row}
    )


async def create_task(
    context: AgentToolContext, arguments: Dict[str, Any]
) -> ToolResult:
    body: Dict[str, Any] = {"title": require_str(arguments, "title")}
    description = optional_str(arguments, "description")
    if description:
        body["description"] = description
    status = optional_str(arguments, "status")
    if status:
        body["status"] = _check_enum(status, TASK_STATUSES, "status")
    priority = optional_str(arguments, "priority")
    if priority:
        body["priority"] = _check_enum(priority, TASK_PRIORITIES, "priority")
    project_id = optional_str(arguments, "project_id")
    if project_id:
        body["project_id"] = project_id
    parent_task_id = optional_str(arguments, "parent_task_id")
    if parent_task_id:
        body["parent_task_id"] = parent_task_id

    row = await context.client.request("POST", "/api/v1/tasks", json=body)
    task_id = row.get("id") if isinstance(row, dict) else None
    return ToolResult(
        text=f"Created task {task_id}: {body['title']}", details={"task": row}
    )


async def update_task(
    context: AgentToolContext, arguments: Dict[str, Any]
) -> ToolResult:
    task_id = require_str(arguments, "task_id")
    body: Dict[str, Any] = {}
    title = optional_str(arguments, "title")
    if title:
        body["title"] = title
    if "description" in arguments:
        # Explicit null clears the field, which is the documented PATCH
        # semantic — so presence, not truthiness, is what matters here.
        body["description"] = arguments["description"]
    status = optional_str(arguments, "status")
    if status:
        body["status"] = _check_enum(status, TASK_STATUSES, "status")
    priority = optional_str(arguments, "priority")
    if priority:
        body["priority"] = _check_enum(priority, TASK_PRIORITIES, "priority")
    project_id = optional_str(arguments, "project_id")
    if project_id:
        body["project_id"] = project_id
    if not body:
        raise AgentToolError(
            "Nothing to update — pass at least one of title, description, "
            "status, priority, project_id."
        )
    row = await context.client.request("PATCH", f"/api/v1/tasks/{task_id}", json=body)
    return ToolResult(
        text=f"Updated task {task_id} ({', '.join(sorted(body))}).",
        details={"task": row},
    )


async def delete_task(
    context: AgentToolContext, arguments: Dict[str, Any]
) -> ToolResult:
    task_id = require_str(arguments, "task_id")
    await context.client.request("DELETE", f"/api/v1/tasks/{task_id}")
    return ToolResult(text=f"Deleted task {task_id}.", details={"task_id": task_id})


TOOLS = (
    AgentTool(
        name="vicoa_list_tasks",
        label="List Vicoa tasks",
        description=(
            "List tasks from the user's Vicoa backlog, optionally filtered by "
            "status or project. Use before creating a task, to avoid "
            "duplicates, and whenever asked what is on the backlog."
        ),
        parameters=object_schema(
            {
                "status": {
                    "type": "string",
                    "description": f"Filter by status: {', '.join(TASK_STATUSES)}.",
                },
                "project_id": {"type": "string", "description": "Filter by project."},
                "limit": {
                    "type": "integer",
                    "description": f"Max tasks to return (1-{_MAX_ROWS}).",
                },
            }
        ),
        handler=list_tasks,
        load_mode="essential",
    ),
    AgentTool(
        name="vicoa_get_task",
        label="Get a Vicoa task",
        description="Full details of one Vicoa task, including its description.",
        parameters=object_schema(
            {"task_id": {"type": "string", "description": "Task id."}},
            required=["task_id"],
        ),
        handler=get_task,
    ),
    AgentTool(
        name="vicoa_create_task",
        label="Create a Vicoa task",
        description=(
            "Add a task to the user's Vicoa backlog. Use when the user asks to "
            "remember or track work, or when you find follow-up work worth "
            "capturing."
        ),
        parameters=object_schema(
            {
                "title": {"type": "string", "description": "Short task title."},
                "description": {
                    "type": "string",
                    "description": "Longer description (Markdown is fine).",
                },
                "status": {
                    "type": "string",
                    "description": (
                        f"One of {', '.join(TASK_STATUSES)}. Defaults to backlog."
                    ),
                },
                "priority": {
                    "type": "string",
                    "description": (
                        f"One of {', '.join(TASK_PRIORITIES)}. Defaults to none."
                    ),
                },
                "project_id": {
                    "type": "string",
                    "description": "Project to file it under; omitted = Inbox.",
                },
                "parent_task_id": {
                    "type": "string",
                    "description": "Parent task, to create a subtask.",
                },
            },
            required=["title"],
        ),
        handler=create_task,
        load_mode="essential",
        mutating=True,
    ),
    AgentTool(
        name="vicoa_update_task",
        label="Update a Vicoa task",
        description=(
            "Change a task's title, description, status, priority or project — "
            "e.g. mark it done once you have finished the work."
        ),
        parameters=object_schema(
            {
                "task_id": {"type": "string", "description": "Task id."},
                "title": {"type": "string", "description": "New title."},
                "description": {
                    "type": "string",
                    "description": "New description (null clears it).",
                },
                "status": {
                    "type": "string",
                    "description": f"One of {', '.join(TASK_STATUSES)}.",
                },
                "priority": {
                    "type": "string",
                    "description": f"One of {', '.join(TASK_PRIORITIES)}.",
                },
                "project_id": {"type": "string", "description": "Move to a project."},
            },
            required=["task_id"],
        ),
        handler=update_task,
        mutating=True,
    ),
    AgentTool(
        name="vicoa_delete_task",
        label="Delete a Vicoa task",
        description=(
            "Permanently delete a Vicoa task. Prefer setting status to "
            "cancelled or done unless the user explicitly asked for deletion."
        ),
        parameters=object_schema(
            {"task_id": {"type": "string", "description": "Task id."}},
            required=["task_id"],
        ),
        handler=delete_task,
        mutating=True,
    ),
)


__all__ = ["TASK_PRIORITIES", "TASK_STATUSES", "TOOLS"]
