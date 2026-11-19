"""Sessions coding agents keep on this machine, and bringing them into Vicoa.

Agents run outside Vicoa (a terminal, a desktop app, an editor) keep their own
transcripts. Each supported agent has a source module here that lists them and
reads one back as Vicoa messages; this module merges the lists, marks the ones
already in Vicoa, and posts an import. The machine daemon serves it as the
``list-local-sessions`` / ``import-local-session`` RPCs and ``vicoa session``
uses it directly, so the app and the CLI behave the same.

An imported session is an ordinary Vicoa session from then on; continuing it
is the existing Resume, which relaunches the agent with its native handle.
"""

from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol

from vicoa.utils import get_git_identity, get_worktree_name

from .types import (
    HistoryMessage,
    LocalSession,
    LocalSessionError,
    LocalSessionNotFound,
    Transcript,
    iso,
)

logger = logging.getLogger(__name__)

#: The agents whose sessions can be listed and imported, and the module that
#: reads each one. Every module offers the same interface: ``AGENT``, ``LABEL``,
#: ``has_session``, ``list_sessions`` and ``read_transcript``. Supporting another
#: agent is one more module and one more line here.
#:
#: The order is the order ``find_agent`` asks in: agents answered from files
#: first, ones that need a process started (Codex's app-server) last.
_SOURCE_MODULES: dict[str, str] = {
    "claude": "vicoa.local_sessions.claude",
    "codex": "vicoa.local_sessions.codex",
}
SUPPORTED_AGENTS: tuple[str, ...] = tuple(_SOURCE_MODULES)

#: Loaded source modules, imported on first use so that reading
#: ``SUPPORTED_AGENTS`` (the CLI's ``--agent`` choices) stays cheap.
SOURCES: dict[str, ModuleType] = {}

#: Same cap as the server (``servers/api/session_imports.py``): a longer
#: session keeps its most recent messages and says how many it left out.
MAX_IMPORTED_MESSAGES = 5000
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

__all__ = [
    "SUPPORTED_AGENTS",
    "agent_label",
    "find_agent",
    "source",
    "HistoryMessage",
    "LocalSession",
    "LocalSessionError",
    "LocalSessionNotFound",
    "Transcript",
    "build_import_payload",
    "import_local_session",
    "list_local_sessions",
    "mark_linked",
]


class ImportClient(Protocol):
    """The two server calls this needs (``vicoa.sdk.client.VicoaClient``)."""

    def lookup_native_sessions(
        self, *, machine_id: str, agent: str, native_session_ids: list[str]
    ) -> dict[str, str]: ...

    def import_session(
        self, payload: dict[str, Any], timeout: int | None = None
    ) -> dict[str, Any]: ...


def source(agent: str) -> ModuleType:
    """The module that reads this agent's sessions."""
    loaded = SOURCES.get(agent)
    if loaded is not None:
        return loaded
    module_name = _SOURCE_MODULES.get(agent)
    if module_name is None:
        raise LocalSessionError(f"Importing {agent} sessions isn't supported yet")
    loaded = importlib.import_module(module_name)
    SOURCES[agent] = loaded
    return loaded


def agent_label(agent: str) -> str:
    """The agent's name for people ("Claude Code"); the id if it isn't supported."""
    if agent not in _SOURCE_MODULES and agent not in SOURCES:
        return agent
    return str(getattr(source(agent), "LABEL", agent))


def find_agent(native_id: str, agents: list[str] | None = None) -> str:
    """Which agent a native session id belongs to, by asking each in turn.

    Session ids are random UUIDs, so two agents never share one; the first to
    recognise it wins, and the cheap file-based checks run before any that
    start a process.
    """
    candidates = agents or list(SUPPORTED_AGENTS)
    for agent in candidates:
        if source(agent).has_session(native_id):
            return agent
    looked_in = ", ".join(agent_label(agent) for agent in candidates)
    raise LocalSessionNotFound(
        f"No session {native_id} on this computer (looked in {looked_in})"
    )


def list_local_sessions(
    *,
    agent: str | None = None,
    directory: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    include_scripted: bool = False,
) -> dict[str, Any]:
    """One page of this machine's native sessions, newest first.

    With no ``agent``, every supported agent's sessions are merged. A source
    that fails (Codex not installed, too old) is reported under ``errors`` and
    the others are still listed.
    """
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))
    agents = [agent] if agent else list(SUPPORTED_AGENTS)
    wanted = offset + limit + 1
    found: list[LocalSession] = []
    errors: dict[str, str] = {}
    for name in agents:
        try:
            found.extend(
                source(name).list_sessions(
                    directory=directory, limit=wanted, include_scripted=include_scripted
                )
            )
        except LocalSessionError as exc:
            errors[name] = str(exc)
        except Exception as exc:  # noqa: BLE001 - one broken source must not hide the rest
            logger.exception("listing %s sessions failed", name)
            errors[name] = f"Couldn't read {name} sessions: {exc}"
    found.sort(key=lambda session: session.updated_at or 0.0, reverse=True)
    page = found[offset : offset + limit]
    return {
        "sessions": [session.to_wire() for session in page],
        "has_more": len(found) > offset + limit,
        "errors": errors,
    }


def mark_linked(
    client: ImportClient, machine_id: str, sessions: list[dict[str, Any]]
) -> None:
    """Set ``vicoa_instance_id`` on each listed session already in Vicoa.

    Best effort: if the lookup fails the list is still worth showing, so the
    field stays ``None`` and the server's import stays the real guard against
    a duplicate.
    """
    by_agent: dict[str, list[str]] = {}
    for session in sessions:
        session.setdefault("vicoa_instance_id", None)
        by_agent.setdefault(session["agent"], []).append(session["native_id"])
    for agent, ids in by_agent.items():
        try:
            matches = client.lookup_native_sessions(
                machine_id=machine_id, agent=agent, native_session_ids=ids
            )
        except Exception:  # noqa: BLE001 - see docstring
            logger.warning("native-lookup for %s failed", agent, exc_info=True)
            continue
        for session in sessions:
            if session["agent"] == agent:
                session["vicoa_instance_id"] = matches.get(session["native_id"])


def _trim(messages: list[HistoryMessage]) -> list[HistoryMessage]:
    if len(messages) <= MAX_IMPORTED_MESSAGES:
        return messages
    kept = messages[-(MAX_IMPORTED_MESSAGES - 1) :]
    left_out = len(messages) - len(kept)
    note = HistoryMessage(
        "agent",
        f"{left_out} earlier messages from this session weren't imported.",
        kept[0].created_at - 0.001,
    )
    return [note, *kept]


def build_import_payload(
    transcript: Transcript, *, machine_id: str, home_dir: str | None = None
) -> dict[str, Any]:
    """The ``POST /agent-instances/import`` body for one transcript."""
    session = transcript.session
    if not session.cwd:
        raise LocalSessionError(
            "This session has no folder recorded, so it couldn't be resumed from Vicoa"
        )
    messages = _trim(transcript.messages)
    payload: dict[str, Any] = {
        "machine_id": machine_id,
        "agent": session.agent,
        "native_session_id": session.native_id,
        "project": session.cwd,
        "home_dir": home_dir or str(Path.home()),
        "name": session.title,
        "source": session.source,
        "source_label": session.source_label,
        "messages": [message.to_wire() for message in messages],
    }
    # The session's real start, not the "left out" note a trim puts first.
    first = transcript.messages[0].created_at if transcript.messages else None
    started = session.created_at or first
    if started is not None:
        payload["started_at"] = iso(started)
    # The same git identity registration probes, so the session lands in the
    # project its folder belongs to (a worktree is matched by its repo).
    if os.path.isdir(session.cwd):
        worktree = get_worktree_name(session.cwd)
        if worktree:
            payload["worktree_name"] = worktree
        repo_root, remote = get_git_identity(session.cwd)
        if repo_root:
            payload["repo_root"] = repo_root
        if remote:
            payload["git_remote_url"] = remote
    return payload


def import_local_session(
    client: ImportClient,
    *,
    machine_id: str,
    native_id: str,
    agent: str | None = None,
) -> dict[str, Any]:
    """Read one native session and import it. Returns the server's answer plus
    the agent and the session title, for the caller to show.

    Without ``agent``, the agent is found from the id (``find_agent``).
    """
    agent = agent or find_agent(native_id)
    transcript = source(agent).read_transcript(native_id)
    payload = build_import_payload(transcript, machine_id=machine_id)
    result = client.import_session(payload)
    return {
        "agent": agent,
        "agent_instance_id": result.get("agent_instance_id"),
        "created": bool(result.get("created")),
        "message_count": int(result.get("message_count") or 0),
        "title": transcript.session.title,
    }
