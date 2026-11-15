"""On-disk "this session is registered" marker, runner → daemon.

The daemon's `spawn-session` RPC used to return success the moment the agent
process was launched. The agent then registered its instance on its own —
and when that failed (a slow or unreachable server) the caller had already
been told the spawn worked, so it navigated to a row that never appeared,
while the process either ran on as an invisible orphan or exited unseen.

Now the runner touches this marker once its instance row is settled
(registered, or reopened on resume), and the daemon holds the RPC until the
marker appears or the process exits. A file rather than a pipe: it needs no
fd plumbing across platforms, and a runner started without a daemon (the
`vicoa` TUI) simply leaves a file nobody reads, which it removes on exit.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def registered_marker_path(session_id: str) -> Path:
    return Path.home() / ".vicoa" / "session_registered" / session_id


def mark_session_registered(session_id: str) -> None:
    """Signal the daemon that this session's instance row exists. Best-effort."""
    try:
        path = registered_marker_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"1")
    except Exception:  # noqa: BLE001 — a diagnostics marker must never fail a session
        logger.debug(
            "could not write registered marker for %s", session_id, exc_info=True
        )


def standby_ready_marker_path(session_id: str) -> Path:
    return Path.home() / ".vicoa" / "session_standby" / session_id


def mark_standby_ready(session_id: str) -> None:
    """Signal the daemon that this standby's engine is up (``vicoa.standby``).

    The daemon only hands the prompt to a standby that is ready: one still
    bringing its engine up would otherwise hold the spawn until it is, and a
    bring-up that then fails would leave the user with a timeout instead of the
    reason a cold start reports in the session. Best-effort.
    """
    try:
        path = standby_ready_marker_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"1")
    except Exception:  # noqa: BLE001 — a missing marker only means a cold start
        logger.debug("could not write standby marker for %s", session_id, exc_info=True)


def standby_is_ready(session_id: str) -> bool:
    return standby_ready_marker_path(session_id).exists()


def clear_standby_ready(session_id: str) -> None:
    """Remove the standby marker (the daemon, once adopted or discarded)."""
    try:
        standby_ready_marker_path(session_id).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        logger.debug(
            "could not remove standby marker for %s", session_id, exc_info=True
        )


def clear_session_registered(session_id: str) -> None:
    """Remove the marker (daemon after consuming it, runner on exit). Best-effort."""
    try:
        registered_marker_path(session_id).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        logger.debug(
            "could not remove registered marker for %s", session_id, exc_info=True
        )
