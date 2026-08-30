"""When a headless wrapper should stop itself.

Archiving or closing a session from the web/app marks the row terminal and
broadcasts an ``instance-update`` frame over the session's WebSocket. The
wrapper already receives that frame (for its own status echoes); this decides
whether the frame means "you were shut down from elsewhere — exit".

Without this, archiving marked the row COMPLETED but left the agent running in
the background forever — the WebSocket migration dropped the terminate handling
the old SSE path had, which is the source of the accumulated zombie sessions.
"""

from __future__ import annotations

from typing import Any

#: Statuses that mean the session is over and the wrapper should exit. Mirrors
#: the backend's terminal set (shared/database/liveness.py). Kept as strings so
#: the wrapper layer doesn't depend on the DB models.
WRAPPER_STOP_STATUSES: frozenset[str] = frozenset(
    {"COMPLETED", "FAILED", "KILLED", "DISCONNECTED", "DELETED"}
)


def instance_update_requests_stop(body: Any) -> bool:
    """Whether an ``instance-update`` body means this wrapper should exit.

    The wrapper's own transitions (ACTIVE / AWAITING_INPUT, including the
    reopen it does on resume) are non-terminal, so they never trip this. Its
    own terminal echo during shutdown may — but stopping is idempotent, so a
    wrapper that's already exiting is unaffected.
    """
    if not isinstance(body, dict):
        return False
    status = str(body.get("status") or "").upper()
    return status in WRAPPER_STOP_STATUSES
