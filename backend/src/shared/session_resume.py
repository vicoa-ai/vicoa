"""What it takes to relaunch a stopped session, server-side.

A Python port of the pieces of the web's `lib/session-resume.ts` that an
automation running in an existing session needs: which agent to launch, the
agent's own conversation handle, and the folder to launch it in. A resume is a
`spawn-session` RPC that reuses the instance id; see that module for why.
"""

from __future__ import annotations

from typing import Any

#: Where each wrapper records the agent's own conversation handle on
#: `instance_metadata`, in the order the web reads them.
AGENT_SESSION_HANDLE_KEYS = (
    "codex_thread_id",
    "acp_session_id",
    "pi_session_id",
    "antigravity_conversation_id",
)

# Display-name keywords for rows that predate `session_config.agent`. Order
# matters: "pi" is a substring of "copilot", so the Pi checks come last.
_AGENT_NAME_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("codex", "codex"),
    ("opencode", "opencode"),
    ("cursor", "cursor"),
    ("gemini", "gemini"),
    ("copilot", "copilot"),
    ("kimi", "kimi"),
    ("hermes", "hermes"),
    ("antigravity", "antigravity"),
    ("oh my pi", "omp"),
    ("omp", "omp"),
    ("pi", "pi"),
)


def resume_agent_slug(
    session_config: dict[str, Any] | None, agent_type_name: str | None
) -> str:
    """The agent id the daemon expects. `session_config.agent` is the catalog
    id recorded at spawn and wins; the free-form agent type name is only a
    fallback for rows that never recorded one."""
    configured = (session_config or {}).get("agent")
    if isinstance(configured, str) and configured.strip():
        return configured.strip().lower()
    name = (agent_type_name or "").lower()
    for keyword, slug in _AGENT_NAME_KEYWORDS:
        if keyword in name:
            return slug
    return "claude"


def agent_session_handle(instance_metadata: dict[str, Any] | None) -> str | None:
    """The agent's prior conversation handle, if the previous run recorded one.
    Absent is normal: the relaunch still happens, without the history."""
    meta = instance_metadata or {}
    for key in AGENT_SESSION_HANDLE_KEYS:
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def expand_project_path(project: str, home_dir: str | None) -> str:
    """Expand a stored `~` path against the session's recorded home dir."""
    if not project.startswith("~") or not home_dir:
        return project
    return home_dir.rstrip("/") + project[1:]
