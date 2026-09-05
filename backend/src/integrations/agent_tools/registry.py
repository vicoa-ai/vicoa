"""Tool definitions, result shape, and dispatch.

A tool is a name, a JSON Schema and an async handler. The schema is plain JSON
Schema because that is what every consumer of this module wants — omp's
``set_host_tools`` takes ``parameters`` verbatim, and so would an MCP
``inputSchema``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from integrations.agent_tools.context import AgentToolContext, AgentToolError


logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """A tool's answer, in the shape both consumers already expect.

    ``text`` is what the model reads; ``details`` is structured data a client
    may render. Matches omp's ``AgentToolResult`` (``{content: [{type, text}],
    details}``) exactly, which is also a reasonable MCP content block, so the
    adapter is a rename rather than a translation.
    """

    text: str
    details: Optional[Dict[str, Any]] = None
    is_error: bool = False

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"content": [{"type": "text", "text": self.text}]}
        if self.details is not None:
            payload["details"] = self.details
        return payload


Handler = Callable[[AgentToolContext, Dict[str, Any]], Awaitable[ToolResult]]


@dataclass(frozen=True)
class AgentTool:
    name: str
    label: str
    description: str
    parameters: Dict[str, Any]
    handler: Handler
    #: ``essential`` tools are always in the model's context; ``discoverable``
    #: ones are surfaced on demand. Only the few tools an agent should reach
    #: for unprompted are essential — the long tail stays discoverable so the
    #: agent's context budget isn't spent describing tools it will never call.
    load_mode: str = "discoverable"
    #: Whether the call changes Vicoa state. Mutating calls are metered by the
    #: spend guard; reads are not, so an agent can freely inspect.
    mutating: bool = False


def object_schema(
    properties: Dict[str, Any], required: Optional[List[str]] = None
) -> Dict[str, Any]:
    """A JSON Schema object with ``additionalProperties`` closed.

    Closed on purpose: an open schema invites the model to invent parameters
    that are then silently dropped, which reads to the user as the tool
    ignoring their instruction.
    """
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def build_registry() -> Dict[str, AgentTool]:
    """Every tool, keyed by name.

    Imported lazily inside the function so the submodules can import the
    registry helpers above without a cycle.
    """
    from integrations.agent_tools import automations, sessions, tasks

    registry: Dict[str, AgentTool] = {}
    for tool in (*sessions.TOOLS, *tasks.TOOLS, *automations.TOOLS):
        if tool.name in registry:
            raise RuntimeError(f"duplicate agent tool name: {tool.name}")
        registry[tool.name] = tool
    return registry


async def dispatch(
    registry: Dict[str, AgentTool],
    context: AgentToolContext,
    name: str,
    arguments: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Run one tool call, turning every failure into a readable tool result.

    Nothing here raises. A tool that blew up must come back as an ``isError``
    result the model can read and recover from — an exception escaping into the
    frame loop would strand the call and, worse, leave the agent waiting for a
    result that will never arrive.
    """
    tool = registry.get(name)
    if tool is None:
        return ToolResult(
            text=f"Unknown tool `{name}`. Available: {', '.join(sorted(registry))}",
            is_error=True,
        )
    args = arguments if isinstance(arguments, dict) else {}
    try:
        if tool.mutating:
            context.guard.check_and_record(name)
        return await tool.handler(context, args)
    except AgentToolError as exc:
        return ToolResult(text=str(exc), is_error=True)
    except asyncio.CancelledError:
        # The only failure that must NOT become a result: the caller cancelled,
        # and a late result for a cancelled call corrupts the agent's state.
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate catch-all
        # BaseException, not Exception, on purpose. `SystemExit` and
        # `KeyboardInterrupt` do not inherit from Exception, so a handler that
        # raises one would slip past a plain `except Exception`, return no
        # result at all, and leave the agent blocked on a tool call that can
        # never complete — a hung turn with nothing in the log to explain it.
        #
        # That is not hypothetical: it is exactly what reusing the CLI's
        # `vicoa/commands/_api.request()` would do, since it calls
        # `sys.exit(1)` on any transport error, 401 or non-2xx. A handler is a
        # library call, so nothing it raises may be allowed to end the process
        # or strand the turn.
        logger.exception("agent tool %s failed", name)
        return ToolResult(text=f"`{name}` failed: {exc}", is_error=True)


def to_host_tool_definitions(registry: Dict[str, AgentTool]) -> List[Dict[str, Any]]:
    """Registry -> the ``set_host_tools`` payload."""
    return [
        {
            "name": tool.name,
            "label": tool.label,
            "description": tool.description,
            "parameters": tool.parameters,
            "loadMode": tool.load_mode,
        }
        for tool in registry.values()
    ]


__all__ = [
    "AgentTool",
    "Handler",
    "ToolResult",
    "build_registry",
    "dispatch",
    "object_schema",
    "to_host_tool_definitions",
]
