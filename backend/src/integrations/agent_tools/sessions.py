"""Vicoa session tools: list, inspect, read, start, prompt, interrupt, end.

All of these are agent-facing REST endpoints on ``vicoa-server``, reached with
the calling session's own API key — so the results are already scoped to that
key's owner and no user id is ever passed explicitly.

Interrupt is worth a note: there is no "cancel" endpoint. The dashboard's Stop
button posts a control envelope as an ordinary user message, and the running
wrapper's router recognises it. Doing exactly the same thing here means an
agent-driven stop and a human-driven stop take the identical path.
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


#: The control envelope the dashboard's Stop button sends. Kept in sync with
#: ``integrations/headless/control_command.py``'s parser, which every wrapper
#: uses to recognise it.
_INTERRUPT_CONTROL = json.dumps({"type": "control", "setting": "interrupt"})

_MAX_ROWS = 50
_MAX_TRANSCRIPT_MESSAGES = 100
#: Per-message excerpt in a transcript read. Long enough to be useful, short
#: enough that 100 messages don't blow the model's context.
_TRANSCRIPT_EXCERPT_CHARS = 400


def _session_line(row: Dict[str, Any]) -> str:
    name = row.get("name") or row.get("agent_type_name") or "(untitled)"
    return (
        f"- {row.get('id')} · {name} · {row.get('status')} "
        f"· {row.get('agent_type_name') or '?'} "
        f"· {row.get('project_path') or row.get('directory') or ''}".rstrip(" ·")
    )


async def list_sessions(
    context: AgentToolContext, arguments: Dict[str, Any]
) -> ToolResult:
    limit = parse_positive_int(
        arguments.get("limit"), name="limit", default=20, maximum=_MAX_ROWS
    )
    params: Dict[str, Any] = {"limit": limit, "scope": "me"}
    status = optional_str(arguments, "status")
    if status:
        params["status"] = status
    payload = await context.client.request(
        "GET", "/api/v1/agent-instances", params=params
    )
    rows = as_rows(payload)
    if not rows:
        return ToolResult(text="No sessions found.", details={"sessions": []})
    lines = [f"{len(rows)} session(s):", *[_session_line(row) for row in rows]]
    return ToolResult(text="\n".join(lines), details={"sessions": rows})


async def get_session(
    context: AgentToolContext, arguments: Dict[str, Any]
) -> ToolResult:
    session_id = optional_str(arguments, "session_id") or context.agent_instance_id
    row = await context.client.request("GET", f"/api/v1/agent-instances/{session_id}")
    if not isinstance(row, dict):
        raise AgentToolError(f"Session {session_id} not found")
    summary = json.dumps(row, indent=2, default=str)
    return ToolResult(text=summary, details={"session": row})


async def read_session_transcript(
    context: AgentToolContext, arguments: Dict[str, Any]
) -> ToolResult:
    session_id = optional_str(arguments, "session_id") or context.agent_instance_id
    limit = parse_positive_int(
        arguments.get("limit"),
        name="limit",
        default=30,
        maximum=_MAX_TRANSCRIPT_MESSAGES,
    )
    payload = await context.client.request(
        "GET",
        f"/api/v1/agent-instances/{session_id}/messages",
        params={"limit": limit},
    )
    rows = as_rows(payload)
    if not rows:
        return ToolResult(text="No messages in that session.", details={"messages": []})
    lines: List[str] = []
    for row in rows:
        sender = str(row.get("sender_type") or "?").lower()
        content = str(row.get("content") or "")
        if len(content) > _TRANSCRIPT_EXCERPT_CHARS:
            content = content[:_TRANSCRIPT_EXCERPT_CHARS] + "…"
        lines.append(f"[{sender}] {content}")
    return ToolResult(text="\n\n".join(lines), details={"messages": rows})


async def list_machines(
    context: AgentToolContext, _arguments: Dict[str, Any]
) -> ToolResult:
    payload = await context.client.request("GET", "/api/v1/machines")
    rows = as_rows(payload)
    if not rows:
        return ToolResult(text="No machines registered.", details={"machines": []})
    lines = [
        f"- {row.get('id')} · {row.get('name') or row.get('hostname') or '?'} "
        f"· last seen {row.get('last_heartbeat_at') or 'never'}"
        for row in rows
    ]
    return ToolResult(
        text=f"{len(rows)} machine(s):\n" + "\n".join(lines),
        details={"machines": rows},
    )


async def _resolve_machine_id(
    context: AgentToolContext, arguments: Dict[str, Any]
) -> str:
    """Machine for a spawn: explicit argument, else this session's own.

    Falling back to "the machine I am running on" is what makes the tool usable
    without the model having to guess or look up a UUID first.
    """
    explicit = optional_str(arguments, "machine_id")
    if explicit:
        return explicit
    if context.machine_id:
        return context.machine_id
    payload = await context.client.request(
        "GET", f"/api/v1/agent-instances/{context.agent_instance_id}"
    )
    machine_id = None
    if isinstance(payload, dict):
        machine_id = payload.get("machine_id") or (
            (payload.get("machine") or {}).get("id")
            if isinstance(payload.get("machine"), dict)
            else None
        )
    if not machine_id:
        raise AgentToolError(
            "No machine_id given and this session's machine is unknown. Call "
            "`vicoa_list_machines` and pass one explicitly."
        )
    context.machine_id = str(machine_id)
    return context.machine_id


async def start_session(
    context: AgentToolContext, arguments: Dict[str, Any]
) -> ToolResult:
    context.ensure_can_spawn()
    prompt = require_str(arguments, "prompt")
    directory = optional_str(arguments, "directory") or context.project_path
    if not directory:
        raise AgentToolError(
            "`directory` is required — this session does not know its own project path."
        )
    agent = optional_str(arguments, "agent") or "claude"
    machine_id = await _resolve_machine_id(context, arguments)

    metadata: Dict[str, Any] = dict(context.child_metadata())
    name = optional_str(arguments, "name")
    if name:
        metadata["name"] = name
    model = optional_str(arguments, "model")
    if model:
        metadata["model"] = model

    payload = await context.client.request(
        "POST",
        f"/api/v1/machines/{machine_id}/spawn-requests",
        json={
            "directory": directory,
            "agent": agent,
            "prompt": prompt,
            "metadata": metadata,
        },
    )
    instance_id = (
        payload.get("agent_instance_id") if isinstance(payload, dict) else None
    )
    return ToolResult(
        text=(
            f"Started a {agent} session ({instance_id}) on machine {machine_id} "
            f"in {directory}. It is queued for the daemon; use "
            f"`vicoa_get_session` to check on it."
        ),
        details={"agent_instance_id": instance_id, "machine_id": machine_id},
    )


async def send_session_message(
    context: AgentToolContext, arguments: Dict[str, Any]
) -> ToolResult:
    session_id = require_str(arguments, "session_id")
    content = require_str(arguments, "content")
    if session_id == context.agent_instance_id:
        # Prompting yourself is an infinite loop with extra steps: the message
        # comes straight back to this wrapper as new user input.
        raise AgentToolError(
            "Refusing to send a message to this same session — that would "
            "re-prompt you in a loop. Target a different session."
        )
    await context.client.request(
        "POST",
        "/api/v1/messages/user",
        json={"agent_instance_id": session_id, "content": content},
    )
    return ToolResult(
        text=f"Sent to session {session_id}.",
        details={"agent_instance_id": session_id},
    )


async def interrupt_session(
    context: AgentToolContext, arguments: Dict[str, Any]
) -> ToolResult:
    session_id = require_str(arguments, "session_id")
    await context.client.request(
        "POST",
        "/api/v1/messages/user",
        json={
            "agent_instance_id": session_id,
            "content": f"Stop. {_INTERRUPT_CONTROL}",
        },
    )
    return ToolResult(
        text=f"Interrupt sent to session {session_id}.",
        details={"agent_instance_id": session_id},
    )


async def end_session(
    context: AgentToolContext, arguments: Dict[str, Any]
) -> ToolResult:
    session_id = require_str(arguments, "session_id")
    if session_id == context.agent_instance_id:
        raise AgentToolError(
            "Refusing to end this session from inside it. Finish your turn "
            "instead; the user closes the session."
        )
    await context.client.request(
        "PUT",
        f"/api/v1/agent-instances/{session_id}/status",
        json={"status": "COMPLETED"},
    )
    return ToolResult(
        text=f"Session {session_id} marked complete; its agent will shut down.",
        details={"agent_instance_id": session_id},
    )


TOOLS = (
    AgentTool(
        name="vicoa_list_sessions",
        label="List Vicoa sessions",
        description=(
            "List the user's Vicoa agent sessions (id, name, status, agent, "
            "project). Use this whenever asked what is running, what happened "
            "in another session, or before targeting one by id."
        ),
        parameters=object_schema(
            {
                "limit": {
                    "type": "integer",
                    "description": f"Max sessions to return (1-{_MAX_ROWS}).",
                },
                "status": {
                    "type": "string",
                    "description": (
                        "Optional status filter, e.g. ACTIVE, AWAITING_INPUT, "
                        "COMPLETED."
                    ),
                },
            }
        ),
        handler=list_sessions,
        load_mode="essential",
    ),
    AgentTool(
        name="vicoa_get_session",
        label="Get a Vicoa session",
        description=(
            "Full details of one Vicoa session. Defaults to the current "
            "session when session_id is omitted."
        ),
        parameters=object_schema(
            {"session_id": {"type": "string", "description": "Session id."}}
        ),
        handler=get_session,
    ),
    AgentTool(
        name="vicoa_read_session_transcript",
        label="Read a Vicoa session transcript",
        description=(
            "Read recent messages from a Vicoa session — how to find out what "
            "another agent actually did or said."
        ),
        parameters=object_schema(
            {
                "session_id": {"type": "string", "description": "Session id."},
                "limit": {
                    "type": "integer",
                    "description": (
                        f"Max messages (1-{_MAX_TRANSCRIPT_MESSAGES}, newest)."
                    ),
                },
            }
        ),
        handler=read_session_transcript,
    ),
    AgentTool(
        name="vicoa_list_machines",
        label="List Vicoa machines",
        description=(
            "List the machines running a Vicoa daemon, with their ids and last "
            "heartbeat. Needed to start a session somewhere other than here."
        ),
        parameters=object_schema({}),
        handler=list_machines,
    ),
    AgentTool(
        name="vicoa_start_session",
        label="Start a Vicoa session",
        description=(
            "Start a new Vicoa coding-agent session on a machine, with an "
            "initial prompt. Defaults to this session's machine and directory. "
            "Use for work that should run independently or in parallel — not "
            "for work you can do yourself."
        ),
        parameters=object_schema(
            {
                "prompt": {
                    "type": "string",
                    "description": "The initial prompt for the new session.",
                },
                "directory": {
                    "type": "string",
                    "description": (
                        "Absolute working directory. Defaults to this "
                        "session's project."
                    ),
                },
                "agent": {
                    "type": "string",
                    "description": (
                        "Agent id: claude, codex, opencode, omp, pi, cursor, "
                        "gemini, copilot, kimi, hermes. Defaults to claude."
                    ),
                },
                "model": {"type": "string", "description": "Optional model id."},
                "name": {"type": "string", "description": "Optional session title."},
                "machine_id": {
                    "type": "string",
                    "description": (
                        "Machine to run on. Defaults to this session's machine."
                    ),
                },
            },
            required=["prompt"],
        ),
        handler=start_session,
        mutating=True,
    ),
    AgentTool(
        name="vicoa_send_session_message",
        label="Message a Vicoa session",
        description=(
            "Send a message into another running Vicoa session, as if the user "
            "had typed it. Use to give a session you started further "
            "instructions."
        ),
        parameters=object_schema(
            {
                "session_id": {"type": "string", "description": "Target session id."},
                "content": {"type": "string", "description": "Message to send."},
            },
            required=["session_id", "content"],
        ),
        handler=send_session_message,
        mutating=True,
    ),
    AgentTool(
        name="vicoa_interrupt_session",
        label="Interrupt a Vicoa session",
        description=(
            "Stop what another Vicoa session is currently doing, leaving it "
            "open and awaiting input."
        ),
        parameters=object_schema(
            {"session_id": {"type": "string", "description": "Target session id."}},
            required=["session_id"],
        ),
        handler=interrupt_session,
        mutating=True,
    ),
    AgentTool(
        name="vicoa_end_session",
        label="End a Vicoa session",
        description=(
            "Mark another Vicoa session complete and shut its agent down. Use "
            "when a session you started has finished its work."
        ),
        parameters=object_schema(
            {"session_id": {"type": "string", "description": "Target session id."}},
            required=["session_id"],
        ),
        handler=end_session,
        mutating=True,
    ),
)


__all__ = ["TOOLS"]
