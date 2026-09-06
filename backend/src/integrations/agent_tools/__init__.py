"""Tools that let a coding agent drive Vicoa itself.

Provider-agnostic on purpose. Today the only consumer is the Pi-family
wrapper's ``host_tools.py``, which adapts these to omp's ``set_host_tools`` /
``host_tool_call`` frames — but nothing here knows omp exists. A tool is a name,
a JSON Schema and an async handler; the handler talks to the agent-facing REST
API through the wrapper's own :class:`AsyncVicoaClient`, in-process.

Why this boundary exists even with exactly one caller: exposing the same tools
over MCP later (for the eight agents that have no host-tool channel) should be
an adapter over this module, not a rewrite. That exposure is deliberately *not*
built here — Vicoa-spawned sessions do not use the MCP server today, and
re-introducing per-session MCP injection is a separate, previously-reversed
decision.

Scope is sessions + tasks + automations, all of which the agent-facing server
exposes to an API-key caller (``servers/api/instances.py``, ``tasks.py``,
``automations.py``, and the spawn-request route in ``routers.py``). Terminal,
worktree, file and git tools are out of scope.

Everything is user-scoped for free: the client authenticates with the session's
own API key, so every call already resolves to that key's owner.
"""

from integrations.agent_tools.context import (
    AgentToolContext,
    AgentToolError,
    SpendGuard,
)
from integrations.agent_tools.registry import (
    AgentTool,
    ToolResult,
    build_registry,
    dispatch,
)

__all__ = [
    "AgentTool",
    "AgentToolContext",
    "AgentToolError",
    "SpendGuard",
    "ToolResult",
    "build_registry",
    "dispatch",
]
