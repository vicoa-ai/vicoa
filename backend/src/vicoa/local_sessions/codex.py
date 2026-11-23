"""Codex sessions on this machine, read through ``codex app-server``.

Codex's rollout files change shape between releases (newer ones store typed
items, older ones plain events), so rather than parse them we ask Codex itself:
``thread/list`` for the sessions and ``thread/read`` with ``includeTurns`` for
a history. Its items are the ones the live wrapper renders, so they go through
the same ``item_renderer``. The one thing the API leaves out is which client
started a thread, which is the ``originator`` on the rollout's first line.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Awaitable, Callable, TypeVar

from integrations.headless.codex.item_renderer import render_item
from integrations.headless.codex.spawn import spawn_codex_app_server
from integrations.headless.codex.transport import CodexTransport
from integrations.headless.thinking import build_thinking_metadata
from vicoa.utils import find_codex_cli

from .types import (
    HistoryMessage,
    LocalSession,
    LocalSessionError,
    LocalSessionNotFound,
    Transcript,
)

AGENT = "codex"
LABEL = "Codex"

_CLIENT_INFO = {"name": "vicoa", "title": "Vicoa", "version": "0.1"}
_REQUEST_TIMEOUT = 60.0
_PAGE_SIZE = 100
_MAX_PAGES = 20

SOURCE_LABELS = {
    "codex_cli_rs": "Terminal",
    "codex-tui": "Terminal",
    "Codex Desktop": "Codex desktop",
    "codex_vscode": "VS Code",
}

T = TypeVar("T")


def is_scripted(originator: str | None, thread_source: str | None) -> bool:
    return originator == "codex_exec" or thread_source == "exec"


def is_vicoa(originator: str | None) -> bool:
    """Threads Vicoa itself started: already Vicoa sessions, never offered.

    The terminal ``vicoa codex`` path doesn't record its thread id on the
    session yet, so the server lookup alone would miss those.
    """
    return originator is not None and originator.lower().startswith("vicoa")


def _seconds(raw: Any) -> float | None:
    """Codex timestamps arrive in seconds or milliseconds depending on the field."""
    if not isinstance(raw, (int, float)) or raw <= 0:
        return None
    return raw / 1000 if raw > 1e12 else float(raw)


def _originator(rollout_path: Any) -> str | None:
    if not isinstance(rollout_path, str) or not rollout_path:
        return None
    try:
        with open(rollout_path, "r", encoding="utf-8", errors="replace") as handle:
            first = json.loads(handle.readline() or "{}")
    except (OSError, json.JSONDecodeError):
        return None
    payload = first.get("payload") if isinstance(first, dict) else None
    value = payload.get("originator") if isinstance(payload, dict) else None
    return value if isinstance(value, str) else None


def _within(cwd: str | None, directory: str) -> bool:
    if not cwd:
        return False
    root = os.path.realpath(os.path.expanduser(directory)).rstrip(os.sep)
    path = os.path.realpath(cwd).rstrip(os.sep)
    return path == root or path.startswith(root + os.sep)


def _session_from(thread: dict[str, Any]) -> LocalSession:
    originator = _originator(thread.get("path"))
    raw_source = thread.get("source")
    thread_source = raw_source if isinstance(raw_source, str) else None
    raw_git = thread.get("gitInfo")
    git_info: dict[str, Any] = raw_git if isinstance(raw_git, dict) else {}
    raw_branch = git_info.get("branch")
    raw_cwd = thread.get("cwd")
    preview = str(thread.get("preview") or "").strip().splitlines()
    return LocalSession(
        agent=AGENT,
        native_id=str(thread["id"]),
        title=(preview[0] if preview else "") or "Untitled session",
        cwd=raw_cwd if isinstance(raw_cwd, str) else None,
        updated_at=_seconds(thread.get("updatedAt"))
        or _seconds(thread.get("createdAt")),
        created_at=_seconds(thread.get("createdAt")),
        git_branch=raw_branch if isinstance(raw_branch, str) else None,
        source=originator,
        source_label=SOURCE_LABELS.get(originator or ""),
        scripted=is_scripted(originator, thread_source),
    )


async def _with_app_server(work: Callable[[CodexTransport], Awaitable[T]]) -> T:
    env = {k: v for k, v in os.environ.items() if not k.startswith("VICOA_")}
    # The same search detection uses (npm prefix, the Windows installer's
    # dir, Vicoa's own copy), not just this daemon's PATH.
    binary = find_codex_cli()
    try:
        codex = await spawn_codex_app_server(
            env=env, command=[binary, "app-server"] if binary else None
        )
    except (RuntimeError, OSError) as exc:
        # RuntimeError: none found; OSError: the found path won't start (a
        # Windows npm shim, or a copy removed since the lookup).
        raise LocalSessionError("Codex isn't installed on this machine") from exc
    try:
        await codex.transport.start()
        await codex.transport.send_request(
            "initialize",
            {"clientInfo": _CLIENT_INFO, "capabilities": {"experimentalApi": True}},
            timeout=_REQUEST_TIMEOUT,
        )
        codex.transport.notify("initialized", {})
        return await work(codex.transport)
    finally:
        await codex.aclose()


def _run(work: Callable[[CodexTransport], Awaitable[T]]) -> T:
    """Run against a short-lived app-server. Called from RPC worker threads and
    the CLI, neither of which has a running event loop."""
    try:
        return asyncio.run(_with_app_server(work))
    except LocalSessionError:
        raise
    except Exception as exc:
        message = str(exc)
        if "thread/list" in message or "thread/read" in message or "-32601" in message:
            raise LocalSessionError(
                "This version of Codex can't list its sessions; update Codex and try again"
            ) from exc
        raise LocalSessionError(f"Couldn't read Codex sessions: {message}") from exc


def list_sessions(
    *, directory: str | None = None, limit: int = 50, include_scripted: bool = False
) -> list[LocalSession]:
    async def work(transport: CodexTransport) -> list[LocalSession]:
        sessions: list[LocalSession] = []
        cursor: str | None = None
        for _ in range(_MAX_PAGES):
            params: dict[str, Any] = {"limit": _PAGE_SIZE}
            if cursor:
                params["cursor"] = cursor
            result = await transport.send_request(
                "thread/list", params, timeout=_REQUEST_TIMEOUT
            )
            for thread in result.get("data") or []:
                if (
                    not isinstance(thread, dict)
                    or not thread.get("id")
                    or thread.get("ephemeral")
                ):
                    continue
                if directory and not _within(thread.get("cwd"), directory):
                    continue
                session = _session_from(thread)
                if is_vicoa(session.source) or not session.cwd:
                    continue
                if session.scripted and not include_scripted:
                    continue
                sessions.append(session)
                if len(sessions) >= limit:
                    return sessions
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return sessions

    return _run(work)


def _user_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    images = 0
    for piece in item.get("content") or []:
        if not isinstance(piece, dict):
            continue
        if piece.get("type") == "text" and piece.get("text"):
            parts.append(str(piece["text"]))
        elif piece.get("type") in ("image", "localImage"):
            images += 1
    if images and not parts:
        parts.append("[Image]" if images == 1 else f"[{images} images]")
    return "\n".join(parts).strip()


def convert_turns(turns: list[Any], fallback_at: float | None) -> list[HistoryMessage]:
    """Rows for a thread's turns. Items carry no time of their own, so each
    turn's are spread evenly between its start and end, in order."""
    rows: list[HistoryMessage] = []
    clock = fallback_at or 0.0
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        items = [item for item in turn.get("items") or [] if isinstance(item, dict)]
        start = _seconds(turn.get("startedAt")) or clock
        end = _seconds(turn.get("completedAt")) or start
        step = (end - start) / max(len(items) - 1, 1) if end > start else 0.0
        for index, item in enumerate(items):
            at = max(start + step * index, clock)
            clock = at
            if item.get("type") == "userMessage":
                text = _user_text(item)
                if text:
                    rows.append(HistoryMessage("user", text, at))
                continue
            content = render_item(item)
            if not content:
                continue
            metadata = (
                build_thinking_metadata(AGENT)
                if item.get("type") == "reasoning"
                else None
            )
            rows.append(HistoryMessage("agent", content, at, metadata))
        failure = _turn_error(turn)
        if failure:
            clock = max(end, clock)
            rows.append(HistoryMessage("agent", failure, clock))
    return rows


def _turn_error(turn: dict[str, Any]) -> str | None:
    """A failed turn's reason, so a session isn't just the user's prompts."""
    if turn.get("status") != "failed":
        return None
    error = turn.get("error")
    message = error.get("message") if isinstance(error, dict) else None
    if isinstance(message, str) and message.strip():
        return f"This turn failed: {message.strip()}"
    return "This turn failed."


def has_session(native_id: str) -> bool:
    """Whether Codex on this machine has a thread with this id.

    Any failure counts as no: an id Codex doesn't know, and a machine without
    a usable Codex, both mean this isn't a Codex session we can import.
    """

    async def work(transport: CodexTransport) -> bool:
        result = await transport.send_request(
            "thread/read",
            {"threadId": native_id, "includeTurns": False},
            timeout=_REQUEST_TIMEOUT,
        )
        thread = result.get("thread") if isinstance(result, dict) else None
        return isinstance(thread, dict) and bool(thread.get("id"))

    try:
        return _run(work)
    except LocalSessionError:
        return False


def read_transcript(native_id: str) -> Transcript:
    async def work(transport: CodexTransport) -> Transcript:
        try:
            result = await transport.send_request(
                "thread/read",
                {"threadId": native_id, "includeTurns": True},
                timeout=_REQUEST_TIMEOUT,
            )
        except RuntimeError as exc:
            if "not found" in str(exc).lower():
                raise LocalSessionNotFound(
                    f"No Codex session {native_id} on this machine"
                ) from exc
            raise
        thread = result.get("thread") if isinstance(result, dict) else None
        if not isinstance(thread, dict) or not thread.get("id"):
            raise LocalSessionNotFound(f"No Codex session {native_id} on this machine")
        session = _session_from(thread)
        return Transcript(
            session=session,
            messages=convert_turns(thread.get("turns") or [], session.created_at),
        )

    return _run(work)
