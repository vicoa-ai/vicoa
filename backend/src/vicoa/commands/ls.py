"""``vicoa ls`` — list active vicoa agent instances on this machine."""

from __future__ import annotations

import json as _json
import os
from pathlib import Path
from typing import Optional

from vicoa.constants import DEFAULT_API_URL


def _format_age(etime: str | None) -> str:
    """Convert ``ps etime`` to a short relative string (``2h``, ``3d``).

    ``ps -o etime=`` formats: ``MM:SS``, ``HH:MM:SS``, or ``D-HH:MM:SS``.
    Returns the raw string on parse failure so we never crash on an
    unexpected format from a less-common platform.
    """
    if not etime:
        return ""
    s = etime.strip()
    try:
        days = 0
        if "-" in s:
            days_part, s = s.split("-", 1)
            days = int(days_part)
        parts = [int(p) for p in s.split(":")]
        if len(parts) == 3:
            hours, mins, _ = parts
        elif len(parts) == 2:
            hours, mins = 0, parts[0]
        else:
            return f"{parts[0]}s"
        if days > 0:
            return f"{days}d"
        if hours > 0:
            return f"{hours}h"
        return f"{mins}m"
    except (ValueError, IndexError):
        return etime


def _short_id(session_id: str | None, pid: int) -> str:
    """8-char prefix of a session UUID, falling back to PID when absent."""
    if session_id:
        return session_id[:8]
    return f"pid:{pid}"


_NAME_W = 40
_PROJECT_W = 18


def _fit(s: str, width: int) -> str:
    """Truncate ``s`` to ``width`` chars, appending ``…`` if it overflows."""
    if len(s) > width:
        return s[: width - 1] + "…"
    return s


def _shorten_path(path: str | None) -> str:
    """Return only the last path component, fit to ``_PROJECT_W`` columns."""
    if not path:
        return "—"
    last = Path(path).name or path
    return _fit(last, _PROJECT_W)


def _fetch_session_names(
    session_ids: list[str], api_key: str, base_url: str
) -> dict[str, str]:
    """Fetch agent instance names from the backend for the given session IDs.

    Runs requests concurrently and returns a mapping of session_id → name.
    Silently ignores failures so ``vicoa ls`` never blocks or crashes.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from vicoa.sdk.client import VicoaClient

    result: dict[str, str] = {}
    if not session_ids:
        return result

    def _fetch_one(sid: str) -> tuple[str, str | None]:
        try:
            with VicoaClient(api_key=api_key, base_url=base_url) as client:
                data = client._make_request(
                    "GET", f"/api/v1/agent-instances/{sid}", timeout=3
                )
                return sid, data.get("name")
        except Exception:
            return sid, None

    with ThreadPoolExecutor(max_workers=min(len(session_ids), 8)) as pool:
        futures = {pool.submit(_fetch_one, sid): sid for sid in session_ids}
        for future in as_completed(futures, timeout=4):
            try:
                sid, name = future.result()
                if name:
                    result[sid] = name
            except Exception:
                pass

    return result


def cmd_ls(args, api_key: Optional[str] = None) -> None:
    """``vicoa ls`` — list active vicoa agent instances on this machine.

    Works on POSIX (``ps``) and Windows (PowerShell ``Get-CimInstance``).
    TUI sessions don't run on Windows today, so on Windows the TUI section
    is usually empty; daemon-spawned headless sessions appear normally.
    """
    from vicoa.agent_processes import list_running_agents

    agents = list_running_agents()

    # Enrich with backend names for sessions that have a session_id.
    try:
        resolved_key = api_key or os.environ.get("VICOA_API_KEY")
        base_url = getattr(args, "base_url", None) or DEFAULT_API_URL
        if resolved_key:
            ids_to_fetch = [a.session_id for a in agents if a.session_id]
            backend_names = _fetch_session_names(ids_to_fetch, resolved_key, base_url)
            for a in agents:
                if a.session_id and a.session_id in backend_names:
                    a.name = backend_names[a.session_id]
    except Exception:
        pass

    if getattr(args, "json", False):
        print(
            _json.dumps(
                [
                    {
                        "pid": a.pid,
                        "agent": a.agent,
                        "kind": a.kind,
                        "session_id": a.session_id,
                        "name": a.name,
                        "project_path": a.project_path,
                        "age": a.age,
                    }
                    for a in agents
                ],
                indent=2,
            )
        )
        return

    if not agents:
        print("No active vicoa sessions found.")
        return

    headless = [a for a in agents if a.kind == "headless"]
    tui = [a for a in agents if a.kind == "tui"]

    def _print_section(heading: str, rows: list) -> None:
        print(f"\n{heading} ({len(rows)})")
        if not rows:
            print("  (none)")
            return
        header = f"  {'ID':<12} {'AGENT':<10} {'NAME':<{_NAME_W}} {'PROJECT':<{_PROJECT_W}} {'PID':<8} {'AGE'}"
        print(header)
        print(f"  {'-' * (len(header) - 2)}")
        for r in rows:
            print(
                f"  {_short_id(r.session_id, r.pid):<12} "
                f"{r.agent:<10} "
                f"{_fit(r.name or '—', _NAME_W):<{_NAME_W}} "
                f"{_shorten_path(r.project_path):<{_PROJECT_W}} "
                f"{r.pid:<8} "
                f"{_format_age(r.age)}"
            )

    _print_section("DAEMON SESSIONS", headless)
    _print_section("TUI SESSIONS", tui)
    print()
