"""What someone a session was shared with may see of it (collaboration §10.2).

One definition for both processes: the dashboard's REST rows
(`backend.db.queries.redact_for_grantee`) and the relay's watcher-room frames
(`shared.websocket.watchers`). A second copy is how a field that one side
strips starts leaking through the other.

The line is the one the public share viewer draws: what ran, with which model
and effort, under which permission mode — nothing that locates the owner's
machine. Beyond privacy this is the second layer of §10.2: with no
`machine_id` and no absolute paths a client has nothing to aim a terminal,
file or git RPC at.
"""

from __future__ import annotations

from typing import Any

# The `session_config` keys anyone but the owner may see (old plan D5). Shared
# by the public share viewer and the signed-in grantee view.
DISPLAY_SESSION_CONFIG_KEYS = (
    "agent",
    "model",
    "thinking_effort",
    "reasoning_effort",
    "permission_mode",
    "opencode_mode",
)

# `instance_metadata` keys a grantee's client reads that locate nothing on the
# owner's machine. `repo_root` and friends are absolute paths; they stay home.
GRANTEE_METADATA_KEYS = ("worktree_name", "source", "usage")


def project_label(project: str | None) -> str | None:
    """The folder's name without the path that leads to it."""
    if not project:
        return None
    return project.rstrip("/").rsplit("/", 1)[-1] or None


def grantee_metadata(metadata: Any) -> dict | None:
    if not isinstance(metadata, dict):
        return None
    return {k: metadata[k] for k in GRANTEE_METADATA_KEYS if k in metadata} or None


def display_session_config(config: Any) -> dict | None:
    if not isinstance(config, dict):
        return None
    return {
        k: config[k] for k in DISPLAY_SESSION_CONFIG_KEYS if config.get(k) is not None
    } or None
