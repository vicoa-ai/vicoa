"""Daemon RPC handler for `scan-commands` — the live slash command/skill index.

Counterpart to `file_index.scan_files` for the composer's `/` menu: clients
read the machine's current command and skill set mid-session instead of the
copy the CLI synced into the `slash_commands` table at session start (that DB
copy stays as the fallback for offline/old daemons).

No TTL cache, unlike the file index: a scan reads a few hundred small
markdown files under `~/.claude`, `~/.codex`, and `~/.agents`, not a whole
project tree, and clients fetch once per panel-open rather than per
keystroke. The `known_hash` short-circuit still keeps a warm client's reply
at a few bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from integrations.cli_wrappers.claude_code.command_sync import scan_agent_commands


def _commands_hash(commands: list[dict[str, str]]) -> str:
    payload = json.dumps(commands, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def scan_commands(
    agent_type: str,
    cwd: str | None = None,
    known_hash: str | None = None,
) -> dict[str, Any]:
    """Return the slash command/skill index for ``agent_type`` on this machine.

    ``cwd`` scopes the project-local sources (`./.claude`, `./.agents/skills`);
    when it is missing or not a directory only the global sources are scanned —
    an empty result is a valid answer, not an error, so unlike `scan-files`
    there are no authoritative path error codes for clients to honor.
    """
    if not agent_type or not isinstance(agent_type, str):
        return {"error": "invalid_agent_type"}

    project_root: Path | None = None
    if cwd:
        normalized = os.path.realpath(os.path.expanduser(cwd))
        if os.path.isdir(normalized):
            project_root = Path(normalized)

    scanned = scan_agent_commands(agent_type, project_root=project_root)
    commands = [{"name": name, **details} for name, details in sorted(scanned.items())]

    index_hash = _commands_hash(commands)
    if known_hash is not None and known_hash == index_hash:
        return {"unchanged": True, "hash": index_hash}

    return {
        "commands": commands,
        "command_count": len(commands),
        "hash": index_hash,
        "scanned_at": time.time(),
    }
