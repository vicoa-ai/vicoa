"""``vicoa project`` — list and inspect the user's projects.

Projects are how tasks and sessions are grouped (the sidebar in the apps).
Three other flags take one — ``task ls|create|update --project`` and
``agent add --project`` — and this is where an agent finds out what to pass:
the ``ID``, or better the ``KEY`` (``VIC``, the prefix on every task
identifier) or the name. Read-only; projects are made and edited in the apps.

Also home to :func:`resolve_project_ref`, the one place a ``--project`` value
turns into the ``project_id`` a request body needs — the same client-side
lookup ``--parent`` does for ``VIC-42``, so every flag that takes a project
accepts the same forms.

Talks to the agent-facing server with the same Bearer API key every other
``vicoa`` command uses, hitting ``/api/v1/projects`` from
``servers/api/projects.py``.
"""

from __future__ import annotations

import json as _json
import sys
from typing import Optional
from uuid import UUID

from vicoa.commands._api import request, resolve_api_key

# The one non-project value `--project` takes: No project (a NULL project_id).
# A word rather than an empty string so it survives every shell and reads as
# what it means in `task ls --project none`.
NO_PROJECT = "none"

_NAME_W = 24
_PATH_W = 36


def _fit(s: str, width: int) -> str:
    s = s or ""
    return s if len(s) <= width else s[: width - 1] + "…"


def _local_path(project: dict, machine_id: Optional[str]) -> str:
    """The checkout on this machine when the project has one, else the first
    one anywhere — a listing wants *a* path, and the local one is the useful
    one when it exists."""
    directories = project.get("directories") or []
    for d in directories:
        if machine_id and d.get("machine_id") == machine_id:
            return str(d.get("local_path") or "")
    return str(directories[0].get("local_path") or "") if directories else "—"


def _local_machine_id(args) -> Optional[str]:
    # Deferred: instance.py pulls in the whole session toolkit.
    from vicoa.commands.instance import _local_machine_id as local_machine_id

    return local_machine_id(args)


def _print_project_table(projects: list[dict], machine_id: Optional[str]) -> None:
    if not projects:
        print("No projects found.")
        return
    header = (
        f"{'KEY':<6} {'NAME':<{_NAME_W}} {'PATH':<{_PATH_W}} {'TASKS':>5}  {'ID':<36}"
    )
    print(header)
    print("-" * len(header))
    for p in projects:
        archived = " (archived)" if p.get("is_archived") else ""
        count = p.get("task_count")
        print(
            f"{str(p.get('key') or '—'):<6} "
            f"{_fit(str(p.get('name') or '') + archived, _NAME_W):<{_NAME_W}} "
            f"{_fit(_local_path(p, machine_id), _PATH_W):<{_PATH_W}} "
            f"{(count if count is not None else '—'):>5}  "
            f"{p.get('id') or '—'}"
        )
    print(f"\n{len(projects)} project(s).")


def _print_project_detail(p: dict) -> None:
    lines = [
        f"id:          {p.get('id')}",
        f"key:         {p.get('key') or '—'}",
        f"name:        {p.get('name')}",
        f"git_remote:  {p.get('git_remote_url') or '—'}",
        f"open_tasks:  {p.get('task_count') if p.get('task_count') is not None else '—'}",
        f"archived:    {'yes' if p.get('is_archived') else 'no'}",
        f"created_at:  {p.get('created_at')}",
        f"updated_at:  {p.get('updated_at')}",
    ]
    print("\n".join(lines))
    directories = p.get("directories") or []
    if directories:
        print("\ndirectories:")
        for d in directories:
            machine = d.get("machine_name") or d.get("machine_id") or "—"
            print(f"  {machine}: {d.get('local_path')}")


def _list_projects(args, api_key: str, include_archived: bool = False) -> list[dict]:
    params = {"include_archived": "true"} if include_archived else None
    return request(args, api_key, "GET", "/api/v1/projects", params=params) or []


def find_project(args, api_key: str, ref: str) -> dict:
    """The project a ``--project`` value names, or exit 2.

    A UUID is fetched directly; anything else is matched exactly and
    case-insensitively against the user's projects, key first ("VIC" — unique
    per owner) then name — one GET, the same client-side lookup ``--parent``
    does for ``VIC-42``. Names are not unique, so a name that matches several
    projects is an error listing them rather than a silent pick. Archived
    projects count: an agent reorganising a backlog may well be filing into
    one.
    """
    ref = (ref or "").strip()
    try:
        UUID(ref)
    except ValueError:
        pass
    else:
        return request(args, api_key, "GET", f"/api/v1/projects/{ref}")
    projects = _list_projects(args, api_key, include_archived=True)
    wanted = ref.lower()
    by_key = [p for p in projects if str(p.get("key") or "").lower() == wanted]
    if len(by_key) == 1:
        return by_key[0]
    by_name = [p for p in projects if str(p.get("name") or "").lower() == wanted]
    if len(by_name) == 1:
        return by_name[0]
    if len(by_name) > 1:
        options = "\n".join(
            f"  {str(p.get('key') or '—'):<6} {p.get('id')}" for p in by_name
        )
        print(
            f"Error: {len(by_name)} projects are named '{ref}'; pass the key or "
            f"the id instead:\n{options}",
            file=sys.stderr,
        )
        sys.exit(2)
    known = (
        ", ".join(
            sorted(
                str(p.get("key") or p.get("name"))
                for p in projects
                if not p.get("is_archived")
            )
        )
        or "(none yet)"
    )
    print(
        f"Error: no project with key or name '{ref}'. Your projects: {known}.\n"
        "Run `vicoa project ls` to see keys and ids, or pass `none` for No project.",
        file=sys.stderr,
    )
    sys.exit(2)


def resolve_project_ref(args, api_key: str, ref: str) -> Optional[str]:
    """Turn a ``--project`` value into the ``project_id`` a request body needs:
    ``None`` for :data:`NO_PROJECT` (file under No project), else the id of
    the project :func:`find_project` matches."""
    if (ref or "").strip().lower() == NO_PROJECT:
        return None
    return str(find_project(args, api_key, ref)["id"])


def _cmd_ls(args, api_key: str) -> int:
    projects = _list_projects(
        args, api_key, include_archived=getattr(args, "include_archived", False)
    )
    if getattr(args, "json", False):
        print(_json.dumps(projects, indent=2))
        return 0
    _print_project_table(projects, _local_machine_id(args))
    return 0


def _cmd_get(args, api_key: str) -> int:
    project = find_project(args, api_key, str(args.project))
    if getattr(args, "json", False):
        print(_json.dumps(project, indent=2))
        return 0
    _print_project_detail(project)
    return 0


_HANDLERS = {"ls": _cmd_ls, "get": _cmd_get}


def run_project_command(args) -> int:
    """Entry point wired into ``cli.py``'s dispatch for ``vicoa project``."""
    sub = getattr(args, "project_command", None)
    handler = _HANDLERS.get(sub) if sub else None
    if handler is None:
        print(
            "usage: vicoa project {ls,get} ...\n"
            "Run `vicoa project --help` for details.",
            file=sys.stderr,
        )
        return 2
    api_key = resolve_api_key(args)
    return handler(args, api_key)
