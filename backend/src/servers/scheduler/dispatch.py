"""Automation dispatch — turn a stored automation into a live agent session.

Kept as a standalone, pluggable function on purpose: v1 dispatches to the owning
machine's daemon over the `spawn-session` RPC; a future cloud-execution fallback
(the cloud-agent bet) slots in as an `else` branch when the daemon is offline,
without touching the sweep loop. See the plan's "cloud execution fallback" §.
"""

from dataclasses import dataclass
from uuid import UUID

from shared.websocket.rpc import RpcError, rpc_router


def to_spawn_metadata(session_config: dict, prompt: str | None) -> dict:
    """Build the daemon `spawn-session` `metadata` payload from a SessionConfig.

    A direct port of the web `toSpawnMetadata` (lib/agent-catalog.ts) so scheduled
    runs launch with the exact agent/model/effort/permission-mode the user picked.
    """
    m: dict = {}
    if prompt is not None:
        m["prompt"] = prompt

    agent = session_config.get("agent")
    model = session_config.get("model")

    if agent == "claude":
        if model:
            m["model"] = model
        thinking = session_config.get("thinking_effort")
        if thinking:
            m["thinking_effort"] = thinking
            # Dual-write for old daemons that only know enable_thinking.
            m["enable_thinking"] = thinking != "off"
        permission_mode = session_config.get("permission_mode")
        if permission_mode:
            m["permission_mode"] = permission_mode
    elif agent == "codex":
        if model:
            m["model"] = model
        reasoning = session_config.get("reasoning_effort")
        if reasoning:
            m["reasoning_effort"] = reasoning
        permission_mode = session_config.get("permission_mode")
        if permission_mode:
            m["permission_mode"] = permission_mode
    elif agent == "opencode":
        opencode_mode = session_config.get("opencode_mode")
        if opencode_mode:
            m["agent_mode"] = opencode_mode
        if model and model not in ("default", "auto"):
            m["model"] = model
    else:
        if model:
            m["model"] = model
        permission_mode = session_config.get("permission_mode")
        if permission_mode:
            m["permission_mode"] = permission_mode

    return m


@dataclass
class DispatchResult:
    status: str  # one of AUTOMATION_RUN_STATUSES
    agent_instance_id: str | None = None
    detail: str | None = None


def resolve_worktree_spawn(
    directory: str, worktree: dict | None
) -> tuple[str, dict | None]:
    """Map a stored worktree spec to (spawn_directory, worktree_param).

    - none / missing → run in `directory`, no worktree param
    - new            → run in `directory`, ask the daemon for a fresh worktree
    - existing       → run directly in the worktree `path`
    Mirrors the web `resolveWorktreeSpawn`."""
    if not isinstance(worktree, dict):
        return directory, None
    mode = worktree.get("mode")
    if mode == "new":
        return directory, {"new": True}
    if mode == "existing":
        path = worktree.get("path")
        if isinstance(path, str) and path.strip():
            return path.strip(), None
    return directory, None


async def dispatch_automation(
    *,
    user_id: UUID,
    machine_id: UUID,
    directory: str,
    worktree: dict | None = None,
    session_config: dict,
    prompt: str,
) -> DispatchResult:
    """Fire one automation run against its owning machine's daemon.

    - daemon connected + spawns → ``fired`` (+ agent_instance_id)
    - daemon offline (`no_handler` after the RPC's reconnect grace) → ``missed_offline``
    - daemon error / disconnect / timeout → ``failed``
    """
    agent = str(session_config.get("agent") or "claude")
    spawn_directory, worktree_param = resolve_worktree_spawn(directory, worktree)
    params: dict = {
        "directory": spawn_directory,
        "agent": agent,
        "metadata": to_spawn_metadata(session_config, prompt),
    }
    if worktree_param is not None:
        params["worktree"] = worktree_param

    try:
        result = await rpc_router.call(
            str(user_id), str(machine_id), "spawn-session", params
        )
    except RpcError as exc:
        if exc.code == "no_handler":
            # Machine isn't connected right now. v1: drop the run; v2 adds a
            # cloud-execution fallback here.
            return DispatchResult(status="missed_offline", detail="machine offline")
        return DispatchResult(status="failed", detail=exc.code)

    if isinstance(result, dict) and result.get("error"):
        return DispatchResult(status="failed", detail=str(result["error"]))

    instance_id = None
    if isinstance(result, dict):
        raw = result.get("agent_instance_id")
        if isinstance(raw, str) and raw.strip():
            instance_id = raw.strip()
    return DispatchResult(status="fired", agent_instance_id=instance_id)
