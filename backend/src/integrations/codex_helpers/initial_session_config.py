"""Build the register-time session_config payload for Codex TUI.

The Python launcher (`vicoa/agents/codex.py`) calls this just before
`register_agent_instance` so the agent_instances row has the model /
reasoning_effort / permission_mode populated from the start, closing
the brief window where mobile would otherwise see a null session_config
on the chat header pill.

CODEX_MODEL / CODEX_REASONING_EFFORT / CODEX_PERMISSION_MODE are env
vars the daemon sets at spawn time (matches what headless/codex_acp.py
already reads — see its `build_session_config` for the headless
analog). The Rust bridge's `notify_session_config_changed` hook (see
plans/inprogress/mid-session-mode-switching.md §"Codex TUI") takes
over once a real TurnContext event lands.
"""

from __future__ import annotations

import os
from typing import Optional


def build_initial_session_config_codex() -> Optional[dict]:
    """Return the session_config dict to send on first register, or None.

    Returns None when no CODEX_* env var is set — the launcher then omits
    the field from the POST and the server's field-present semantics
    preserve any pre-staged value on the row.
    """
    sc: dict = {"agent": "codex"}
    model = os.environ.get("CODEX_MODEL")
    if model:
        sc["model"] = model
    effort = os.environ.get("CODEX_REASONING_EFFORT")
    if effort:
        sc["reasoning_effort"] = effort
    permission_mode = os.environ.get("CODEX_PERMISSION_MODE")
    if permission_mode:
        sc["permission_mode"] = permission_mode

    # Only return the dict when at least one known value was found.
    if len(sc) == 1:  # just the "agent" key
        return None
    return sc
