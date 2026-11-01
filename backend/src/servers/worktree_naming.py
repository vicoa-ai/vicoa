"""Name a spawn's new worktree, and its session, from the spawn's prompt.

The server side of `protocol.worktree_naming`. Every path that relays a
``spawn-session`` RPC to a daemon calls `start_worktree_naming` just before the
call: the web/mobile WebSocket (``servers/api/ws_handler.py``), the REST
fallback (``servers/api/routers.py``) and the automation sweep
(``servers/scheduler/dispatch.py``). It starts the LLM call right away, so it
runs while the daemon is still checking the worktree out, and marks the params
so the daemon knows a name is coming. The answer is pushed to that daemon as a
``worktree-name`` frame; whether it arrived in time is the daemon's call.
"""

import asyncio
import logging
from typing import Any
from uuid import uuid4

from protocol.worktree_naming import AUTO_NAME_PARAM, WORKTREE_NAME_FRAME
from shared.llms.session_names import generate_session_names, session_naming_configured
from shared.websocket.rpc import rpc_router

logger = logging.getLogger(__name__)

# Detached tasks are referenced only weakly by the event loop; hold them until
# they finish (same guard as `servers.profile_provenance`).
_tasks: set[asyncio.Task] = set()


def _naming_prompt(params: dict[str, Any]) -> str | None:
    """The prompt to name this spawn's worktree from, or None when the spawn
    does not create a worktree that the daemon would name at random."""
    worktree = params.get("worktree")
    if not isinstance(worktree, dict) or worktree.get("new") is not True:
        return None
    name = worktree.get("name")
    if isinstance(name, str) and name.strip():
        return None  # the user picked the name
    if params.get("resume"):
        return None
    metadata = params.get("metadata")
    if not isinstance(metadata, dict):
        return None
    prompt = metadata.get("prompt") or metadata.get("initial_prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    return prompt


def start_worktree_naming(
    user_id: str, machine_id: str, params: dict[str, Any]
) -> None:
    """If this `spawn-session` will create a randomly named worktree from a
    prompt, start naming it and mark `params` so the daemon waits for the name.

    Mutates `params` in place; call it before forwarding them. A no-op for
    every other spawn, and when no naming provider is configured.
    """
    prompt = _naming_prompt(params)
    if prompt is None or not session_naming_configured():
        return
    token = uuid4().hex
    params["worktree"][AUTO_NAME_PARAM] = token
    task = asyncio.create_task(_name_and_deliver(user_id, machine_id, token, prompt))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _name_and_deliver(
    user_id: str, machine_id: str, token: str, prompt: str
) -> None:
    try:
        names = await asyncio.to_thread(generate_session_names, prompt)
    except Exception:  # noqa: BLE001 — naming must never break a spawn
        logger.exception("worktree naming failed")
        names = None
    # Sent even when naming failed, so the daemon stops waiting at once.
    frame: dict[str, Any] = {"type": WORKTREE_NAME_FRAME, "token": token}
    if names is not None:
        if names.branch:
            frame["branch"] = names.branch
        if names.title:
            frame["title"] = names.title
    daemon = rpc_router.handler(user_id, machine_id, "spawn-session")
    if daemon is None:
        logger.info("worktree name for machine %s dropped: daemon gone", machine_id)
        return
    daemon.enqueue(frame)
