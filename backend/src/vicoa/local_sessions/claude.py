"""Claude Code sessions on this machine.

Claude Code writes every session, whichever client started it (the terminal,
the desktop app, an editor, the SDK), to
``<config dir>/projects/<cwd slug>/<session id>.jsonl``. The SDK's
``get_session_info`` gives the title and branch; which client started it is the
``entrypoint`` field Claude stamps on each entry (``cli``, ``claude-desktop``,
``sdk-py``, ...), read from the head of the file.

History is rendered with the rules the terminal wrapper applies to the same
file live (``claude_wrapper_v2_0.process_claude_log_entry``) and its block
formatter, so an imported session reads like one Vicoa watched happen. It is
read in file order rather than along the SDK's conversation chain: after a
``/compact`` the chain starts at the summary, and the earlier turns would be
lost.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID

from integrations.cli_wrappers.claude_code.format_utils import format_content_block
from integrations.headless.thinking import build_thinking_metadata

from .types import HistoryMessage, LocalSession, LocalSessionNotFound, Transcript

AGENT = "claude"
LABEL = "Claude Code"

#: Claude stamps the entrypoint and cwd on its first conversation entry, but
#: newer transcripts open with bookkeeping lines (a queued prompt can run past
#: 100 KB), so the first entry is looked for line by line within this budget.
_HEAD_BUDGET_BYTES = 4 * 1024 * 1024
_HEAD_MAX_LINES = 200
_SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)

SOURCE_LABELS = {
    "cli": "Terminal",
    # Vicoa's own terminal wrapper (`vicoa` with no daemon). Those sessions
    # are normally in Vicoa already, under the same id, so the list marks them.
    "jsonlog-wrapper": "Terminal",
    "claude-desktop": "Claude desktop",
    "claude-vscode": "VS Code",
}


def projects_dir() -> Path:
    """Where Claude keeps transcripts (honours ``CLAUDE_CONFIG_DIR``, as Claude does)."""
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(config) if config else Path.home() / ".claude"
    return base / "projects"


def is_scripted(entrypoint: str | None) -> bool:
    """SDK runs (``sdk-py``, ``sdk-ts``) and ``claude -p`` (``sdk-cli``)."""
    return entrypoint is not None and entrypoint.startswith("sdk-")


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class _Head:
    entrypoint: str | None = None
    cwd: str | None = None
    git_branch: str | None = None
    created_at: float | None = None
    first_prompt: str | None = None


def _read_head(path: Path) -> _Head:
    """What the first conversation entries say about the session.

    The entrypoint, cwd and branch ride on every conversation entry; the first
    prompt is the first one that converts to a user row. Read line by line
    within a budget, since bookkeeping lines can come first.
    """
    entrypoint: str | None = None
    cwd: str | None = None
    branch: str | None = None
    created: float | None = None
    prompt: str | None = None
    read = 0
    try:
        with path.open("rb") as handle:
            for count, line in enumerate(handle):
                read += len(line)
                if count >= _HEAD_MAX_LINES or read > _HEAD_BUDGET_BYTES:
                    break
                if b'"cwd"' not in line and b'"entrypoint"' not in line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                if entrypoint is None and isinstance(entry.get("entrypoint"), str):
                    entrypoint = entry["entrypoint"]
                if cwd is None and isinstance(entry.get("cwd"), str):
                    cwd = entry["cwd"]
                if branch is None and isinstance(entry.get("gitBranch"), str):
                    branch = entry["gitBranch"]
                if created is None:
                    created = _timestamp(entry)
                if prompt is None:
                    prompt = next(
                        (
                            row.content
                            for row in convert_entry(entry)
                            if row.sender == "user"
                        ),
                        None,
                    )
                if entrypoint and cwd and prompt:
                    break
    except OSError:
        pass
    return _Head(entrypoint, cwd, branch, created, prompt)


def _one_line(text: str, limit: int = 200) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first if len(first) <= limit else first[: limit - 1].rstrip() + "…"


def _within(cwd: str | None, directory: str) -> bool:
    if not cwd:
        return False
    root = os.path.realpath(os.path.expanduser(directory)).rstrip(os.sep)
    path = os.path.realpath(cwd).rstrip(os.sep)
    return path == root or path.startswith(root + os.sep)


def _transcripts() -> list[tuple[float, Path]]:
    """Every top-level transcript, newest first."""
    root = projects_dir()
    if not root.is_dir():
        return []
    found: list[tuple[float, Path]] = []
    for path in root.glob("*/*.jsonl"):
        if not _is_uuid(path.stem):
            continue
        try:
            found.append((path.stat().st_mtime, path))
        except OSError:
            continue
    found.sort(key=lambda pair: pair[0], reverse=True)
    return found


def _session_from(path: Path, mtime: float, head: _Head) -> LocalSession | None:
    from claude_agent_sdk import get_session_info

    entrypoint = head.entrypoint
    cwd = head.cwd
    info = get_session_info(path.stem, directory=cwd) if cwd else None
    if info is None:
        info = get_session_info(path.stem)
    if info is None:
        # The SDK reads a fixed-size head, which a long queued prompt can
        # fill. Fall back to what the line scan found; with no prompt at all
        # there is nothing to show.
        if not head.first_prompt:
            return None
        return LocalSession(
            agent=AGENT,
            native_id=path.stem,
            title=_one_line(head.first_prompt),
            cwd=cwd,
            updated_at=mtime,
            created_at=head.created_at,
            git_branch=head.git_branch,
            source=entrypoint,
            source_label=SOURCE_LABELS.get(entrypoint or ""),
            scripted=is_scripted(entrypoint),
        )
    return LocalSession(
        agent=AGENT,
        native_id=path.stem,
        title=_one_line(info.summary or "")
        or _one_line(head.first_prompt or "")
        or "Untitled session",
        cwd=info.cwd or cwd,
        updated_at=(info.last_modified / 1000) if info.last_modified else mtime,
        created_at=(info.created_at / 1000) if info.created_at else head.created_at,
        git_branch=info.git_branch or head.git_branch,
        source=entrypoint,
        source_label=SOURCE_LABELS.get(entrypoint or ""),
        scripted=is_scripted(entrypoint),
    )


def list_sessions(
    *, directory: str | None = None, limit: int = 50, include_scripted: bool = False
) -> list[LocalSession]:
    """Newest first, at most ``limit``; scripted runs only when asked for."""
    sessions: list[LocalSession] = []
    for mtime, path in _transcripts():
        head = _read_head(path)
        if not include_scripted and is_scripted(head.entrypoint):
            continue
        if directory and not _within(head.cwd, directory):
            continue
        session = _session_from(path, mtime, head)
        if session is None or not session.cwd:
            # Without a folder there is nowhere to resume it.
            continue
        sessions.append(session)
        if len(sessions) >= limit:
            break
    return sessions


def has_session(native_id: str) -> bool:
    """Whether this machine has a Claude Code session with this id."""
    return find_transcript(native_id) is not None


def find_transcript(native_id: str) -> Path | None:
    if not _is_uuid(native_id):
        return None
    matches = list(projects_dir().glob(f"*/{native_id}.jsonl"))
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def _entries(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                yield entry


def _timestamp(entry: dict[str, Any]) -> float | None:
    raw = entry.get("timestamp")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _user_text(content: Any) -> str:
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts: list[str] = []
        images = 0
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text"):
                parts.append(str(block["text"]))
            elif block.get("type") == "image":
                images += 1
        if images and not parts:
            parts.append("[Image]" if images == 1 else f"[{images} images]")
        text = "\n".join(parts)
    else:
        return ""
    return _SYSTEM_REMINDER_RE.sub("", text).strip()


def convert_entry(entry: dict[str, Any]) -> list[HistoryMessage]:
    """The Vicoa rows one transcript entry becomes (often none)."""
    entry_type = entry.get("type")
    if entry_type not in ("user", "assistant"):
        return []
    # Sub-agent side chains, injected meta entries and the summary /compact
    # leaves behind (the turns it summarises are already in the file).
    if entry.get("isSidechain") or entry.get("isMeta") or entry.get("isCompactSummary"):
        return []
    at = _timestamp(entry)
    if at is None:
        return []
    message = entry.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")

    if entry_type == "user":
        if isinstance(content, list) and any(
            isinstance(block, dict) and block.get("type") == "tool_result"
            for block in content
        ):
            # Tool results are acknowledgements, not something the user said.
            return []
        text = _user_text(content)
        if not text or text == "<local-command-stdout></local-command-stdout>":
            return []
        if "<command-name>" in text:
            # The echo of a slash command typed in the terminal.
            return []
        if "<local-command-stdout>" in text:
            # A slash command's output: visible, but the agent's side.
            return [HistoryMessage("agent", text, at)]
        return [HistoryMessage("user", text, at)]

    if not isinstance(content, list):
        return []
    rows: list[HistoryMessage] = []
    thinking = "\n\n".join(
        str(block.get("thinking")).strip()
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "thinking"
        and str(block.get("thinking") or "").strip()
    )
    if thinking:
        rows.append(
            HistoryMessage("agent", thinking, at, build_thinking_metadata(AGENT))
        )
    parts = [
        formatted
        for block in content
        if isinstance(block, dict)
        and block.get("type") not in ("thinking", "redacted_thinking")
        and (formatted := format_content_block(block))
    ]
    if parts:
        rows.append(HistoryMessage("agent", "\n".join(parts), at))
    return rows


def read_transcript(native_id: str) -> Transcript:
    path = find_transcript(native_id)
    if path is None:
        raise LocalSessionNotFound(
            f"No Claude Code session {native_id} on this machine"
        )
    session = _session_from(path, path.stat().st_mtime, _read_head(path))
    if session is None:
        raise LocalSessionNotFound(
            f"Claude Code session {native_id} has nothing to import"
        )
    messages = [row for entry in _entries(path) for row in convert_entry(entry)]
    return Transcript(session=session, messages=messages)
