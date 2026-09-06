"""Execution context and safety guards for agent-driven Vicoa tools.

The guards are the genuinely new risk surface these tools introduce. Once an
agent can call ``vicoa_start_session`` and ``vicoa_send_session_message``, it
can spawn agents that spawn agents, unattended, each burning the user's model
quota. So the depth cap and the rate limit ship *with* the tools, in the same
change, rather than as a follow-up.

Two independent limits:

* **Depth** — a session started by a tool call is stamped with its parent's
  depth + 1 (``VICOA_AGENT_TOOL_DEPTH`` in the spawned environment, echoed into
  the spawn metadata). At :data:`MAX_SPAWN_DEPTH` the spawn tool refuses. This
  bounds recursion even when each level only spawns one child.
* **Rate** — a rolling window cap on *mutating* calls per session. This bounds
  fan-out, which depth alone does not: one agent looping ``start_session`` a
  thousand times never exceeds depth 1.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional
from collections import deque


#: Environment variable carrying the caller's nesting depth into a spawned
#: session. Absent (or unparseable) means depth 0 — a session a human started.
DEPTH_ENV_VAR = "VICOA_AGENT_TOOL_DEPTH"

#: A session may spawn children, and those children may spawn children, but the
#: third level stops. Deep enough for "run the tests, and if they fail open a
#: session to fix it"; shallow enough that a runaway costs a bounded amount.
MAX_SPAWN_DEPTH = 2

#: Mutating calls allowed per rolling window, per session.
RATE_LIMIT_MAX_CALLS = 30
RATE_LIMIT_WINDOW_SECONDS = 300.0


class AgentToolError(RuntimeError):
    """A tool failed in a way the model should see and can act on.

    Raised for bad arguments, refused guards and API errors alike: all three
    are things the agent can reason about (fix the argument, stop spawning, tell
    the user). The adapter turns it into an ``isError`` tool result rather than
    letting it escape and kill the turn.
    """


def current_depth() -> int:
    """This process's nesting depth, from the environment."""
    try:
        return max(0, int(os.environ.get(DEPTH_ENV_VAR, "0")))
    except (TypeError, ValueError):
        return 0


@dataclass
class SpendGuard:
    """Rolling-window rate limit on mutating tool calls.

    Deliberately in-process and per-session: it is a runaway-loop brake, not a
    billing control. A user who wants more just starts another session.
    """

    max_calls: int = RATE_LIMIT_MAX_CALLS
    window_seconds: float = RATE_LIMIT_WINDOW_SECONDS
    _calls: Deque[float] = field(default_factory=deque)
    #: Injectable so tests don't have to sleep.
    now: Any = time.monotonic

    def check_and_record(self, tool_name: str) -> None:
        """Record one mutating call, or raise when the window is full."""
        now = self.now()
        cutoff = now - self.window_seconds
        while self._calls and self._calls[0] < cutoff:
            self._calls.popleft()
        if len(self._calls) >= self.max_calls:
            raise AgentToolError(
                f"Rate limit reached: at most {self.max_calls} Vicoa-modifying "
                f"tool calls per {int(self.window_seconds / 60)} minutes. "
                f"`{tool_name}` was refused. Tell the user what you were trying "
                f"to do and wait before retrying."
            )
        self._calls.append(now)


@dataclass
class AgentToolContext:
    """Everything a tool handler needs, and nothing it doesn't.

    ``client`` is the wrapper's existing :class:`AsyncVicoaClient` — the same
    authenticated, retrying, *async* client the wrapper already uses. Async
    matters: several ``host_tool_call`` frames can be in flight at once, and a
    blocking sync HTTP call would stall the event stream mid-turn.
    """

    client: Any
    #: The calling session, so tools can default to "this session" and so a
    #: spawn can record its parent.
    agent_instance_id: str
    #: Working directory of the calling session — the default for a spawn.
    project_path: str = ""
    #: Machine the calling session runs on, when known. Lets a spawn default to
    #: the same machine instead of making the model guess a UUID.
    machine_id: Optional[str] = None
    depth: int = field(default_factory=current_depth)
    guard: SpendGuard = field(default_factory=SpendGuard)

    def ensure_can_spawn(self) -> None:
        if self.depth >= MAX_SPAWN_DEPTH:
            raise AgentToolError(
                f"Refusing to start another session: this one is already "
                f"{self.depth} level(s) deep and the limit is "
                f"{MAX_SPAWN_DEPTH}. Do the work here, or ask the user to "
                f"start a session themselves."
            )

    def child_metadata(self) -> Dict[str, Any]:
        """Spawn metadata that records the parent link and the new depth."""
        return {
            "spawned_by_agent_instance_id": self.agent_instance_id,
            "agent_tool_depth": self.depth + 1,
        }


def child_env(
    base: Optional[Dict[str, str]] = None, *, depth: int = 0
) -> Dict[str, str]:
    """Environment for a process one level deeper than ``depth``.

    Used by the wrapper when it spawns the agent CLI, so a session started
    through a tool call inherits a depth its own tools will read back.
    """
    env = dict(base if base is not None else os.environ)
    env[DEPTH_ENV_VAR] = str(depth)
    return env


def parse_positive_int(value: Any, *, name: str, default: int, maximum: int) -> int:
    """Coerce a model-supplied count, clamped and with a clear error.

    Models routinely send ``"5"`` for an integer parameter, so a string that
    parses is accepted rather than rejected on a technicality.
    """
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise AgentToolError(f"`{name}` must be a number, got {value!r}") from None
    if parsed < 1:
        raise AgentToolError(f"`{name}` must be at least 1, got {parsed}")
    return min(parsed, maximum)


def require_str(arguments: Dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise AgentToolError(f"`{name}` is required and must be a non-empty string")
    return value.strip()


def optional_str(arguments: Dict[str, Any], name: str) -> Optional[str]:
    value = arguments.get(name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def as_rows(payload: Any) -> List[Dict[str, Any]]:
    """Normalise a list-or-``{items: [...]}`` API response into rows."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("items", "data", "results", "instances", "machines"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


__all__ = [
    "AgentToolContext",
    "AgentToolError",
    "DEPTH_ENV_VAR",
    "MAX_SPAWN_DEPTH",
    "RATE_LIMIT_MAX_CALLS",
    "RATE_LIMIT_WINDOW_SECONDS",
    "SpendGuard",
    "as_rows",
    "child_env",
    "current_depth",
    "optional_str",
    "parse_positive_int",
    "require_str",
]
