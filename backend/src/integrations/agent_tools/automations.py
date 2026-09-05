"""Vicoa automation tools: list, get, create, update, delete.

Backed by ``servers/api/automations.py``. An automation is a scheduled agent
session: a prompt, a machine, a directory, a session config, and either a
one-time instant or a structured recurrence.

This is the tool that makes the headline case real — *"every morning run the
tests, and if they fail open a session to fix it"* is `vicoa_create_automation`
plus, inside that session, `vicoa_start_session`.

The ``frequency`` shapes are defined by ``shared/scheduling/frequency.py`` and
described in this module's schema so the model can build one without a
round-trip. Weekday convention is 0=Sunday … 6=Saturday, matching the web.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from integrations.agent_tools.context import (
    AgentToolContext,
    AgentToolError,
    as_rows,
    optional_str,
    require_str,
)
from integrations.agent_tools.registry import AgentTool, ToolResult, object_schema


_FREQUENCY_DOC = (
    'Recurrence, required when schedule_kind is "recurring". One of: '
    '{"kind":"hourly","minute":0} · '
    '{"kind":"daily","time":"09:00"} · '
    '{"kind":"weekdays","time":"09:00"} (Mon-Fri) · '
    '{"kind":"weekly","weekdays":[1,3,5],"time":"09:00"} (0=Sunday) · '
    '{"kind":"custom","unit":"minutely|hourly|daily|weekly|monthly",'
    '"interval":N,...}. Minutely intervals have a 5-minute floor.'
)


def _automation_line(row: Dict[str, Any]) -> str:
    state = "enabled" if row.get("enabled") else "disabled"
    return (
        f"- {row.get('id')} · {row.get('title')} · {row.get('schedule_kind')} "
        f"· {state} · next {row.get('next_run_at') or '—'}"
    )


async def list_automations(
    context: AgentToolContext, _arguments: Dict[str, Any]
) -> ToolResult:
    payload = await context.client.request("GET", "/api/v1/automations")
    rows = as_rows(payload)
    if not rows:
        return ToolResult(
            text="No automations configured.", details={"automations": []}
        )
    lines: List[str] = [
        f"{len(rows)} automation(s):",
        *[_automation_line(row) for row in rows],
    ]
    return ToolResult(text="\n".join(lines), details={"automations": rows})


async def get_automation(
    context: AgentToolContext, arguments: Dict[str, Any]
) -> ToolResult:
    automation_id = require_str(arguments, "automation_id")
    row = await context.client.request("GET", f"/api/v1/automations/{automation_id}")
    return ToolResult(
        text=json.dumps(row, indent=2, default=str), details={"automation": row}
    )


async def create_automation(
    context: AgentToolContext, arguments: Dict[str, Any]
) -> ToolResult:
    title = require_str(arguments, "title")
    prompt = require_str(arguments, "prompt")
    schedule_kind = require_str(arguments, "schedule_kind")
    if schedule_kind not in {"once", "recurring"}:
        raise AgentToolError('`schedule_kind` must be "once" or "recurring"')

    directory = optional_str(arguments, "directory") or context.project_path
    if not directory:
        raise AgentToolError(
            "`directory` is required — this session does not know its own project path."
        )
    machine_id = optional_str(arguments, "machine_id") or context.machine_id
    if not machine_id:
        raise AgentToolError(
            "`machine_id` is required. Call `vicoa_list_machines` to find one."
        )

    agent = optional_str(arguments, "agent") or "claude"
    # ``session_config.agent`` is the one field the API validates: the
    # scheduler dispatches on it.
    session_config: Dict[str, Any] = {"agent": agent}
    model = optional_str(arguments, "model")
    if model:
        session_config["model"] = model

    body: Dict[str, Any] = {
        "title": title,
        "prompt": prompt,
        "machine_id": machine_id,
        "directory": directory,
        "session_config": session_config,
        "schedule_kind": schedule_kind,
        "timezone": optional_str(arguments, "timezone") or "UTC",
        "enabled": arguments.get("enabled", True) is not False,
    }

    if schedule_kind == "once":
        run_at = optional_str(arguments, "run_at")
        if not run_at:
            raise AgentToolError(
                '`run_at` (ISO 8601 UTC, e.g. "2026-09-06T09:00:00Z") is '
                'required when schedule_kind is "once"'
            )
        body["run_at"] = run_at
    else:
        frequency = arguments.get("frequency")
        if not isinstance(frequency, dict) or not frequency:
            raise AgentToolError(
                '`frequency` is required when schedule_kind is "recurring". '
                + _FREQUENCY_DOC
            )
        body["frequency"] = frequency

    row = await context.client.request("POST", "/api/v1/automations", json=body)
    automation_id = row.get("id") if isinstance(row, dict) else None
    next_run = row.get("next_run_at") if isinstance(row, dict) else None
    return ToolResult(
        text=(
            f"Created automation {automation_id}: {title}. "
            f"Next run: {next_run or 'not scheduled'}."
        ),
        details={"automation": row},
    )


async def update_automation(
    context: AgentToolContext, arguments: Dict[str, Any]
) -> ToolResult:
    automation_id = require_str(arguments, "automation_id")
    body: Dict[str, Any] = {}
    for key in ("title", "prompt", "directory", "timezone", "run_at"):
        value = optional_str(arguments, key)
        if value:
            body[key] = value
    if isinstance(arguments.get("frequency"), dict):
        body["frequency"] = arguments["frequency"]
    schedule_kind = optional_str(arguments, "schedule_kind")
    if schedule_kind:
        if schedule_kind not in {"once", "recurring"}:
            raise AgentToolError('`schedule_kind` must be "once" or "recurring"')
        body["schedule_kind"] = schedule_kind
    if "enabled" in arguments and isinstance(arguments["enabled"], bool):
        body["enabled"] = arguments["enabled"]
    if not body:
        raise AgentToolError(
            "Nothing to update — pass at least one of title, prompt, "
            "directory, schedule_kind, frequency, run_at, timezone, enabled."
        )
    row = await context.client.request(
        "PATCH", f"/api/v1/automations/{automation_id}", json=body
    )
    return ToolResult(
        text=f"Updated automation {automation_id} ({', '.join(sorted(body))}).",
        details={"automation": row},
    )


async def delete_automation(
    context: AgentToolContext, arguments: Dict[str, Any]
) -> ToolResult:
    automation_id = require_str(arguments, "automation_id")
    await context.client.request("DELETE", f"/api/v1/automations/{automation_id}")
    return ToolResult(
        text=f"Deleted automation {automation_id}.",
        details={"automation_id": automation_id},
    )


TOOLS = (
    AgentTool(
        name="vicoa_list_automations",
        label="List Vicoa automations",
        description=(
            "List the user's scheduled Vicoa automations, with their schedules "
            "and next run times. Check this before creating one."
        ),
        parameters=object_schema({}),
        handler=list_automations,
    ),
    AgentTool(
        name="vicoa_get_automation",
        label="Get a Vicoa automation",
        description="Full details of one automation, including its prompt.",
        parameters=object_schema(
            {"automation_id": {"type": "string", "description": "Automation id."}},
            required=["automation_id"],
        ),
        handler=get_automation,
    ),
    AgentTool(
        name="vicoa_create_automation",
        label="Create a Vicoa automation",
        description=(
            "Schedule an agent session to run later or on a recurring "
            'schedule. This is how to honour requests like "every weekday '
            "morning, run the tests and report\". Defaults to this session's "
            "machine and directory."
        ),
        parameters=object_schema(
            {
                "title": {"type": "string", "description": "Short name."},
                "prompt": {
                    "type": "string",
                    "description": "Prompt the scheduled session starts with.",
                },
                "schedule_kind": {
                    "type": "string",
                    "description": '"once" or "recurring".',
                },
                "run_at": {
                    "type": "string",
                    "description": (
                        'ISO 8601 UTC instant for "once", e.g. "2026-09-06T09:00:00Z".'
                    ),
                },
                "frequency": {"type": "object", "description": _FREQUENCY_DOC},
                "timezone": {
                    "type": "string",
                    "description": (
                        "IANA timezone the schedule is anchored in, e.g. "
                        '"Asia/Singapore". Defaults to UTC.'
                    ),
                },
                "directory": {
                    "type": "string",
                    "description": "Absolute working directory.",
                },
                "machine_id": {"type": "string", "description": "Machine to run on."},
                "agent": {
                    "type": "string",
                    "description": "Agent id. Defaults to claude.",
                },
                "model": {"type": "string", "description": "Optional model id."},
                "enabled": {
                    "type": "boolean",
                    "description": "Start enabled. Defaults to true.",
                },
            },
            required=["title", "prompt", "schedule_kind"],
        ),
        handler=create_automation,
        load_mode="essential",
        mutating=True,
    ),
    AgentTool(
        name="vicoa_update_automation",
        label="Update a Vicoa automation",
        description=(
            "Change an automation's prompt, schedule, or enabled state. "
            "Changing any schedule field recomputes the next fire time."
        ),
        parameters=object_schema(
            {
                "automation_id": {"type": "string", "description": "Automation id."},
                "title": {"type": "string", "description": "New name."},
                "prompt": {"type": "string", "description": "New prompt."},
                "schedule_kind": {
                    "type": "string",
                    "description": '"once" or "recurring".',
                },
                "run_at": {"type": "string", "description": "New ISO 8601 instant."},
                "frequency": {"type": "object", "description": _FREQUENCY_DOC},
                "timezone": {"type": "string", "description": "New IANA timezone."},
                "directory": {"type": "string", "description": "New directory."},
                "enabled": {"type": "boolean", "description": "Enable or disable."},
            },
            required=["automation_id"],
        ),
        handler=update_automation,
        mutating=True,
    ),
    AgentTool(
        name="vicoa_delete_automation",
        label="Delete a Vicoa automation",
        description=(
            "Permanently delete a scheduled automation. Prefer disabling it "
            "unless the user asked for deletion."
        ),
        parameters=object_schema(
            {"automation_id": {"type": "string", "description": "Automation id."}},
            required=["automation_id"],
        ),
        handler=delete_automation,
        mutating=True,
    ),
)


__all__ = ["TOOLS"]
