"""``vicoa task`` — list, read, create, update, comment on, and delete tasks.

Built so a running AI agent can manage its user's task backlog without leaving
the terminal (``vicoa task create "Fix the flaky test"``). Talks to the
agent-facing server (``agents.vicoa.ai``) with the same Bearer API key every
other ``vicoa`` command uses, hitting the ``/api/v1/tasks`` endpoints added in
``servers/api/tasks.py``.

Every task reference — the positional refs on ``get``/``update``/``delete``/
``comment(s)``, and ``--parent`` — accepts either the identifier the user
actually sees (``VIC-42``) or a full UUID. ``--project`` takes a project's key
(``VIC``), name, or id, or ``none`` for No project (``commands/project.py``);
``--label`` takes label names (``commands/label.py``).

Human-readable tables by default; ``--json`` on every subcommand for agents (or
scripts) that want to parse the result. Kept dependency-light — no
``shared.database`` imports — so the packaged CLI stays small.
"""

from __future__ import annotations

import json as _json
import os
import sys
from typing import Any, Optional
from uuid import UUID

from vicoa.commands._api import RequestError, request, resolve_api_key
from vicoa.commands.label import resolve_label_names
from vicoa.commands.project import resolve_project_ref

# Mirrors shared.database.task_models; duplicated (not imported) to keep the CLI
# free of the SQLAlchemy/model dependency chain. Kept in sync by hand — the
# server is the source of truth and rejects anything outside these sets.
TASK_STATUSES = (
    "backlog",
    "todo",
    "in_progress",
    "in_review",
    "done",
    "blocked",
    "cancelled",
)
TASK_PRIORITIES = ("urgent", "high", "medium", "low", "none")

# Module-level aliases: `vicoa agent` imports these, and the tests monkeypatch
# `_request` to capture what a handler sends.
_request = request
_resolve_api_key = resolve_api_key


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_TITLE_W = 44
_PROJECT_W = 14


def _fit(s: str, width: int) -> str:
    s = s or ""
    return s if len(s) <= width else s[: width - 1] + "…"


def _short(value: Optional[str], n: int = 8) -> str:
    return value[:n] if value else "—"


def _project_label(t: dict) -> str:
    """What the PROJECT column shows: the name, or "—" for No project."""
    if not t.get("project_id"):
        return "—"
    # An older server sends no project_name; fall back to the key the
    # identifier already carries rather than printing a bare UUID.
    name = t.get("project_name")
    if name:
        return str(name)
    identifier = str(t.get("identifier") or "")
    return (
        identifier.rsplit("-", 1)[0]
        if "-" in identifier
        else _short(t.get("project_id"))
    )


def _print_task_table(tasks: list[dict]) -> None:
    if not tasks:
        print("No tasks found.")
        return
    # Both an id and an identifier: the short id is what the other subcommands
    # take (truncated, so it is a browsing aid either way), while "VIC-42" is
    # what an agent quotes back to its user and what the web deep-links to.
    header = (
        f"{'ID':<8}  {'KEY':<9} {'STATUS':<12} {'PRIO':<7} "
        f"{'PROJECT':<{_PROJECT_W}} {'TITLE':<{_TITLE_W}}"
    )
    print(header)
    print("-" * len(header))
    for t in tasks:
        print(
            f"{_short(t.get('id')):<8}  "
            f"{str(t.get('identifier') or '—'):<9} "
            f"{str(t.get('status', '')):<12} "
            f"{str(t.get('priority', '')):<7} "
            f"{_fit(_project_label(t), _PROJECT_W):<{_PROJECT_W}} "
            f"{_fit(t.get('title', ''), _TITLE_W):<{_TITLE_W}}"
        )
    print(f"\n{len(tasks)} task(s).")


def _print_task_detail(t: dict) -> None:
    labels = ", ".join(lbl.get("name", "") for lbl in t.get("labels", [])) or "—"
    project = (
        f"{_project_label(t)} ({t.get('project_id')})"
        if t.get("project_id")
        else "— (No project)"
    )
    lines = [
        f"id:          {t.get('id')}",
        # The speakable identifier ("VIC-42"). Absent for a task that predates
        # the backfill; print nothing rather than a placeholder that would look
        # like a real reference someone could quote back.
        *([f"identifier:  {t['identifier']}"] if t.get("identifier") else []),
        f"title:       {t.get('title')}",
        f"status:      {t.get('status')}",
        f"priority:    {t.get('priority')}",
        f"project:     {project}",
        f"parent:      {t.get('parent_task_id') or '—'}",
        f"labels:      {labels}",
        f"start_date:  {t.get('start_date') or '—'}",
        f"due_date:    {t.get('due_date') or '—'}",
        f"created_at:  {t.get('created_at')}",
        f"updated_at:  {t.get('updated_at')}",
    ]
    print("\n".join(lines))
    description = t.get("description")
    if description:
        print(f"\ndescription:\n{description}")


def _principal_name(principal: Optional[dict]) -> str:
    if not principal:
        return "someone"
    name = principal.get("name") or "Unknown"
    # The agent tag matters here in a way it doesn't on the web, where an avatar
    # already says it: in a terminal "Claude" and "Nick" look identical.
    return f"{name} (agent)" if principal.get("type") == "agent" else name


def _print_comment(c: dict, indent: str = "") -> None:
    header = f"{indent}{_principal_name(c.get('author'))}  {c.get('created_at', '')}"
    if c.get("edited_at"):
        header += "  (edited)"
    print(header)
    print(f"{indent}  id: {c.get('id')}")
    body = c.get("body")
    if body is None:
        print(f"{indent}  (deleted)")
    else:
        for line in body.splitlines() or [""]:
            print(f"{indent}  {line}")
    reactions = c.get("reactions") or []
    if reactions:
        print(
            f"{indent}  "
            + "  ".join(f"{r.get('emoji')} {r.get('count')}" for r in reactions)
        )
    print()


def _print_thread(comments: list[dict]) -> None:
    """Print the thread. Replies are indented under the root they answer.

    The server sends the list already in thread order (each root followed by its
    replies), so this only has to decide the indent — it never has to sort or
    walk a tree, and neither does any other client.
    """
    if not comments:
        print("No comments yet.")
        return
    for c in comments:
        _print_comment(c, indent="    " if c.get("parent_comment_id") else "")


def _print_activity(activity: list[dict]) -> None:
    print("--- activity ---")
    if not activity:
        print("No activity yet.")
        return
    for row in activity:
        details = row.get("details") or {}
        change = ""
        if "from" in details or "to" in details:
            change = f" ({details.get('from')} -> {details.get('to')})"
        print(
            f"{row.get('created_at', '')}  "
            f"{_principal_name(row.get('actor'))}  "
            f"{str(row.get('action', '')).replace('_', ' ')}{change}"
        )


def _resolve_parent(args, api_key: str, ref: str) -> str:
    """Turn a ``--parent`` reference into the UUID the request body needs.

    Path parameters accept "VIC-42" server-side, but ``parent_task_id`` travels
    in the body as a typed UUID. Rather than loosen that field for every client,
    the one client that lets a *person* type a parent resolves it here — one
    extra GET, and only when the value isn't already a UUID.
    """
    try:
        UUID(ref)
        return ref
    except (ValueError, AttributeError):
        pass
    task = _request(args, api_key, "GET", f"/api/v1/tasks/{ref}")
    return task["id"]


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _label_ids(args, api_key: str, attr: str) -> list[str]:
    """Resolve a repeatable ``--label``-style flag (a list of names) to ids."""
    names = getattr(args, attr, None) or []
    return resolve_label_names(args, api_key, list(names))


def _cmd_ls(args, api_key: str) -> int:
    params: dict[str, Any] = {}
    project_ref = getattr(args, "project", None)
    if project_ref:
        project_id = resolve_project_ref(args, api_key, project_ref)
        if project_id is None:
            params["unfiled"] = "true"
        else:
            params["project_id"] = project_id
    if getattr(args, "status", None):
        params["status"] = args.status
    if getattr(args, "priority", None):
        params["priority"] = args.priority
    label_ids = _label_ids(args, api_key, "label")
    if label_ids:
        params["label_id"] = label_ids
    tasks = _request(args, api_key, "GET", "/api/v1/tasks", params=params or None)
    tasks = _apply_filters_locally(tasks or [], params.get("unfiled"), label_ids)
    if getattr(args, "json", False):
        print(_json.dumps(tasks, indent=2))
    else:
        _print_task_table(tasks)
    return 0


def _apply_filters_locally(
    tasks: list[dict], unfiled: Optional[str], label_ids: list[str]
) -> list[dict]:
    """Re-apply ``unfiled`` / ``label_id`` to the fetched list, in case the
    server didn't.

    A backend older than those params ignores them and returns the whole
    backlog — a silently wrong answer to "the unfiled ones". The list is not
    paginated, so filtering here is exact; on a current server it's a no-op.
    """
    if not unfiled and not label_ids:
        return tasks
    wanted = set(label_ids)

    def _keep(t: dict) -> bool:
        if unfiled and t.get("project_id"):
            return False
        have = {str(lbl.get("id")) for lbl in t.get("labels") or []}
        return wanted <= have

    return [t for t in tasks if _keep(t)]


def _cmd_get(args, api_key: str) -> int:
    task = _request(args, api_key, "GET", f"/api/v1/tasks/{args.task_id}")
    if getattr(args, "json", False):
        print(_json.dumps(task, indent=2))
    else:
        _print_task_detail(task)
    return 0


def _cmd_create(args, api_key: str) -> int:
    body: dict[str, Any] = {"title": args.title}
    if getattr(args, "description", None) is not None:
        body["description"] = args.description
    project_ref = getattr(args, "project", None)
    if project_ref:
        project_id = resolve_project_ref(args, api_key, project_ref)
        if project_id is not None:  # `none` = the default, No project
            body["project_id"] = project_id
    if getattr(args, "status", None):
        body["status"] = args.status
    if getattr(args, "priority", None):
        body["priority"] = args.priority
    if getattr(args, "parent", None):
        body["parent_task_id"] = _resolve_parent(args, api_key, args.parent)
    label_ids = _label_ids(args, api_key, "label")
    if label_ids:
        body["label_ids"] = label_ids
    if getattr(args, "start", None):
        body["start_date"] = args.start
    if getattr(args, "due", None):
        body["due_date"] = args.due
    task = _request(args, api_key, "POST", "/api/v1/tasks", json=body)
    if getattr(args, "json", False):
        print(_json.dumps(task, indent=2))
    else:
        ref = task.get("identifier") or task.get("id")
        print(f"Created task {ref}: {task.get('title')}")
    return 0


def _ref_of(task: dict, fallback: str) -> str:
    return str(task.get("identifier") or task.get("id") or fallback)


def _cmd_update(args, api_key: str) -> int:
    """PATCH one or more tasks with the same set of changes.

    Refs are the positional list (``VIC-20 VIC-21 …``): one command, N
    requests, and a failed ref is reported and skipped rather than aborting
    the rest — a bulk move that dies halfway is worse than one that reports
    which two refs it couldn't find. A project move reassigns the identifier
    (the number is per project), so each such row prints ``VIC-20 → VIC2-2``:
    the caller would otherwise have to diff ``--json`` to learn the new name.
    """
    # Only forward flags the user actually passed, so absent fields are left
    # untouched (the PATCH endpoint applies exclude_unset semantics).
    body: dict[str, Any] = {}
    for flag, field in (
        ("title", "title"),
        ("description", "description"),
        ("status", "status"),
        ("priority", "priority"),
        ("parent", "parent_task_id"),
        ("start", "start_date"),
        ("due", "due_date"),
    ):
        value = getattr(args, flag, None)
        if value is None:
            continue
        body[field] = (
            _resolve_parent(args, api_key, value) if flag == "parent" else value
        )
    project_ref = getattr(args, "project", None)
    if project_ref:
        # `none` resolves to None on purpose: an explicit null moves the task
        # out to No project (and drops its identifier).
        body["project_id"] = resolve_project_ref(args, api_key, project_ref)
    # One label lookup for all three flags, then split the ids back out.
    set_names = list(getattr(args, "label", None) or [])
    add_names = list(getattr(args, "add_label", None) or [])
    remove_names = list(getattr(args, "remove_label", None) or [])
    ids = resolve_label_names(args, api_key, set_names + add_names + remove_names)
    set_labels = ids[: len(set_names)]
    add_labels = ids[len(set_names) : len(set_names) + len(add_names)]
    remove_labels = set(ids[len(set_names) + len(add_names) :])
    if set_names:
        body["label_ids"] = set_labels
    if not body and not add_labels and not remove_labels:
        print(
            "Nothing to update — pass at least one field "
            "(e.g. --status done, --title ..., --project VIC).",
            file=sys.stderr,
        )
        return 2

    refs: list[str] = list(getattr(args, "task_ids", None) or [])
    # A move renames the task and +/- labels need the current set, so those
    # read each task first; a plain field edit doesn't pay for the extra GET.
    needs_before = bool(project_ref) or bool(add_labels) or bool(remove_labels)
    results: list[dict] = []
    failures = 0
    for ref in refs:
        try:
            before: Optional[dict] = None
            if needs_before:
                before = _request(
                    args, api_key, "GET", f"/api/v1/tasks/{ref}", raise_on_error=True
                )
            payload = dict(body)
            if (add_labels or remove_labels) and "label_ids" not in payload:
                current = [
                    str(lbl.get("id")) for lbl in (before or {}).get("labels", [])
                ]
                merged = [lid for lid in current if lid not in remove_labels]
                merged += [lid for lid in add_labels if lid not in merged]
                payload["label_ids"] = merged
            task = _request(
                args,
                api_key,
                "PATCH",
                f"/api/v1/tasks/{ref}",
                json=payload,
                raise_on_error=True,
            )
        except RequestError as exc:
            failures += 1
            print(
                f"Error: {ref}: {exc.detail} (HTTP {exc.status_code})", file=sys.stderr
            )
            continue
        results.append(task)
        if getattr(args, "json", False):
            continue
        old_ref = _ref_of(before, ref) if before else ref
        new_ref = _ref_of(task, ref)
        renamed = (
            f"{old_ref} → {new_ref}"
            if before is not None and old_ref != new_ref
            else new_ref
        )
        print(f"Updated task {renamed}: {task.get('title')}")
    if getattr(args, "json", False):
        # One ref in, one object out — the shape the command always had; a
        # list only when the caller passed a list.
        print(
            _json.dumps(results[0] if len(refs) == 1 and results else results, indent=2)
        )
    return 1 if failures else 0


def _cmd_comments(args, api_key: str) -> int:
    timeline = _request(args, api_key, "GET", f"/api/v1/tasks/{args.task_id}/timeline")
    if getattr(args, "json", False):
        print(_json.dumps(timeline, indent=2))
        return 0
    _print_thread(timeline.get("comments", []))
    if getattr(args, "activity", False):
        _print_activity(timeline.get("activity", []))
    return 0


def _cmd_comment(args, api_key: str) -> int:
    body = args.body
    # '-' reads stdin, so an agent can pipe a multi-line markdown report in
    # rather than fighting its own shell over quoting and newlines.
    if body == "-":
        body = sys.stdin.read()
    body = body.strip()
    if not body:
        print("Refusing to post an empty comment.", file=sys.stderr)
        return 2

    payload: dict[str, Any] = {"body": body}
    if getattr(args, "reply_to", None):
        payload["parent_comment_id"] = args.reply_to
    # When this runs inside a Vicoa session, tell the server which one: if that
    # session was started from an agent profile the comment is authored by the
    # agent ("Claude commented"), not by the human whose API key it is.
    self_id = os.environ.get("VICOA_AGENT_INSTANCE_ID")
    if self_id:
        payload["agent_instance_id"] = self_id

    timeline = _request(
        args,
        api_key,
        "POST",
        f"/api/v1/tasks/{args.task_id}/comments",
        json=payload,
    )
    if getattr(args, "json", False):
        print(_json.dumps(timeline, indent=2))
        return 0
    # Not `comments[-1]`: the list comes back in thread order, so a reply is
    # spliced under its root rather than appended at the end.
    comments = timeline.get("comments", [])
    posted = max(comments, key=lambda c: c.get("created_at") or "", default=None)
    print(f"Posted comment {posted.get('id')}" if posted else "Posted comment.")
    return 0


def _cmd_delete(args, api_key: str) -> int:
    if not getattr(args, "yes", False):
        try:
            answer = input(f"Delete task {args.task_id}? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            # Non-interactive (e.g. an agent) without --yes: refuse rather than
            # delete on an unanswerable prompt.
            print("\nAborted (pass --yes to delete non-interactively).")
            return 1
        if answer not in {"y", "yes"}:
            print("Aborted.")
            return 0
    _request(args, api_key, "DELETE", f"/api/v1/tasks/{args.task_id}")
    print(f"Deleted task {args.task_id}.")
    return 0


_HANDLERS = {
    "ls": _cmd_ls,
    "get": _cmd_get,
    "create": _cmd_create,
    "update": _cmd_update,
    "comments": _cmd_comments,
    "comment": _cmd_comment,
    "delete": _cmd_delete,
}


def run_task_command(args) -> int:
    """Entry point wired into ``cli.py``'s dispatch for ``vicoa task``."""
    sub = getattr(args, "task_command", None)
    handler = _HANDLERS.get(sub) if sub else None
    if handler is None:
        print(
            "usage: vicoa task {ls,get,create,update,comments,comment,delete} ...\n"
            "Run `vicoa task --help` for details.",
            file=sys.stderr,
        )
        return 2
    api_key = _resolve_api_key(args)
    return handler(args, api_key)
