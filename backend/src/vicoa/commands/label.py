"""``vicoa label`` — list, create, rename, recolour and delete task labels.

Labels are the one vocabulary a user has across every project (Settings →
Tasks in the apps). ``task ls|create|update --label <name>`` take them by
name; this is where an agent sees which names exist, adds one before tagging
with it, and tidies the list (``update`` / ``delete``). Only the user's own
labels: a team's vocabulary is managed in the apps.

Also home to :func:`resolve_label_names`, the name → id lookup every
``--label`` flag goes through — labels travel as ids on the wire, names are
what a person types.

Talks to the agent-facing server with the same Bearer API key every other
``vicoa`` command uses, hitting ``/api/v1/task-labels`` from
``servers/api/tasks.py``.
"""

from __future__ import annotations

import json as _json
import sys
from typing import Optional

from vicoa.commands._api import RequestError, request, resolve_api_key

# The web's inline-label palette, cycled by a hash of the name so a label made
# from the terminal gets the same colour the web would have given it
# (INLINE_LABEL_COLORS in apps/web/components/dashboard/task-ui.tsx).
_INLINE_LABEL_COLORS = (
    "#ef4444",
    "#f97316",
    "#eab308",
    "#22c55e",
    "#14b8a6",
    "#3b82f6",
    "#6366f1",
    "#a855f7",
    "#ec4899",
    "#64748b",
)


def inline_label_color(name: str) -> str:
    """The web's ``inlineLabelColor`` — Java-style 32-bit string hash.

    Walks UTF-16 code units, as JS ``charCodeAt`` does, so an emoji (a
    surrogate pair there, one code point here) hashes the same on both sides.
    """
    units = name.encode("utf-16-le")
    h = 0
    for i in range(0, len(units), 2):
        h = (h * 31 + int.from_bytes(units[i : i + 2], "little")) & 0xFFFFFFFF
    if h >= 0x80000000:  # reinterpret as the signed int32 JS produces
        h -= 0x100000000
    return _INLINE_LABEL_COLORS[abs(h) % len(_INLINE_LABEL_COLORS)]


def _list_labels(args, api_key: str) -> list[dict]:
    return request(args, api_key, "GET", "/api/v1/task-labels") or []


def resolve_label_names(args, api_key: str, names: list[str]) -> list[str]:
    """Names → ids, exact and case-insensitive, or exit 2 naming the miss.

    One GET for the whole list, however many names. Labels have no uniqueness
    rule on the server, so two labels spelt the same is an error rather than
    a silent pick — the user can tidy that in Settings.
    """
    if not names:
        return []
    labels = _list_labels(args, api_key)
    return [_resolve_one(labels, name) for name in names]


def resolve_label_groups(args, api_key: str, values: list[str]) -> list[list[str]]:
    """``task ls --label`` values → one group of ids per value.

    A value is a label name, or comma-separated names meaning any of them
    (``bug,docs``), the way GitHub search reads ``label:bug,docs``. A label
    whose own name has a comma still works: the whole value is tried as one
    name first and only split when no label is called that. Misses exit 2,
    like :func:`resolve_label_names`; one GET for every value.
    """
    if not values:
        return []
    labels = _list_labels(args, api_key)
    groups: list[list[str]] = []
    for value in values:
        names = [part.strip() for part in value.split(",") if part.strip()]
        if _matching(labels, value) or not names:
            names = [value]
        groups.append(list(dict.fromkeys(_resolve_one(labels, n) for n in names)))
    return groups


def _matching(labels: list[dict], name: str) -> list[dict]:
    wanted = name.strip().lower()
    return [lbl for lbl in labels if str(lbl.get("name", "")).strip().lower() == wanted]


def _resolve_one(labels: list[dict], name: str) -> str:
    """One name → its id, exact and case-insensitive, or exit 2 naming it."""
    return str(_pick(labels, name, target=False)["id"])


def _pick(labels: list[dict], ref: str, *, target: bool) -> dict:
    """One reference → its label, or exit 2 naming the problem.

    A name matches exactly, case-insensitively. ``target`` is the reading
    ``label update|delete`` use: an id is accepted as well, a name two labels
    share lists their ids to choose from, and a miss doesn't suggest creating
    the label it was about to change.
    """
    if target:
        wanted = ref.strip()
        for lbl in labels:
            if str(lbl.get("id")) == wanted:
                return lbl
    matches = _matching(labels, ref)
    if len(matches) == 1:
        return matches[0]
    if matches:
        ids = ", ".join(str(m.get("id")) for m in matches)
        fix = (
            "pass the id of the one you mean"
            if target
            else "rename one with `vicoa label update <id> --name <new>` and retry"
        )
        print(
            f"Error: {len(matches)} labels are named '{ref}' ({ids}); {fix}.",
            file=sys.stderr,
        )
        sys.exit(2)
    known = ", ".join(sorted(str(lbl.get("name")) for lbl in labels)) or "(none yet)"
    message = f"Error: no label named '{ref}'. Your labels: {known}."
    if not target:
        message += f"\nCreate it with `vicoa label create {ref!r}`."
    print(message, file=sys.stderr)
    sys.exit(2)


def _print_label_table(labels: list[dict]) -> None:
    if not labels:
        print("No labels yet. Create one with `vicoa label create <name>`.")
        return
    header = f"{'NAME':<24} {'COLOR':<8}  {'ID':<36}"
    print(header)
    print("-" * len(header))
    for lbl in labels:
        print(
            f"{str(lbl.get('name') or ''):<24} "
            f"{str(lbl.get('color') or ''):<8}  "
            f"{lbl.get('id') or '—'}"
        )
    print(f"\n{len(labels)} label(s).")


def _cmd_ls(args, api_key: str) -> int:
    labels = _list_labels(args, api_key)
    if getattr(args, "json", False):
        print(_json.dumps(labels, indent=2))
        return 0
    _print_label_table(labels)
    return 0


def _cmd_create(args, api_key: str) -> int:
    name = str(args.name).strip()
    if not name:
        print("Error: a label needs a name.", file=sys.stderr)
        return 2
    # Refuse a duplicate here — the server allows two labels with one name,
    # and a second "growth" would make every later `--label growth` ambiguous.
    existing = [
        lbl
        for lbl in _list_labels(args, api_key)
        if str(lbl.get("name", "")).strip().lower() == name.lower()
    ]
    if existing:
        print(
            f"Label '{existing[0].get('name')}' already exists ({existing[0].get('id')}).",
            file=sys.stderr,
        )
        return 1
    color: Optional[str] = getattr(args, "color", None)
    body = {"name": name, "color": color or inline_label_color(name)}
    label = request(args, api_key, "POST", "/api/v1/task-labels", json=body)
    if getattr(args, "json", False):
        print(_json.dumps(label, indent=2))
        return 0
    print(f"Created label '{label.get('name')}' ({label.get('color')}).")
    return 0


def _is_old_server(exc: RequestError) -> bool:
    """FastAPI's own 404/405 — a server from before label update/delete — as
    opposed to this route's ``Label not found``."""
    return exc.status_code == 405 or (
        exc.status_code == 404 and exc.detail == "Not Found"
    )


_OLD_SERVER = (
    "Error: this Vicoa server can't change labels from the CLI yet; "
    "do it in Settings → Tasks."
)


def _cmd_update(args, api_key: str) -> int:
    new_name: Optional[str] = getattr(args, "new_name", None)
    color: Optional[str] = getattr(args, "color", None)
    if new_name is None and color is None:
        print("Error: pass --name and/or --color.", file=sys.stderr)
        return 2
    if new_name is not None:
        new_name = new_name.strip()
        if not new_name:
            print("Error: a label needs a name.", file=sys.stderr)
            return 2
    labels = _list_labels(args, api_key)
    label = _pick(labels, str(args.label), target=True)
    old_name = str(label.get("name") or "")
    body: dict = {}
    if new_name is not None:
        # Same rule as `create`: a second label spelt like another would make
        # every later `--label <name>` ambiguous. A case-only rename is fine.
        clash = [lbl for lbl in _matching(labels, new_name) if lbl["id"] != label["id"]]
        if clash:
            print(
                f"Label '{clash[0].get('name')}' already exists ({clash[0].get('id')}).",
                file=sys.stderr,
            )
            return 1
        body["name"] = new_name
    if color is not None:
        body["color"] = color
    try:
        updated = request(
            args,
            api_key,
            "PATCH",
            f"/api/v1/task-labels/{label['id']}",
            json=body,
            raise_on_error=True,
        )
    except RequestError as exc:
        print(_OLD_SERVER if _is_old_server(exc) else f"Error: {exc}", file=sys.stderr)
        return 1
    if getattr(args, "json", False):
        print(_json.dumps(updated, indent=2))
        return 0
    name = str(updated.get("name") or "")
    head = (
        f"Renamed label '{old_name}' to '{name}'"
        if name != old_name
        else f"Updated label '{name}'"
    )
    print(f"{head} ({updated.get('color')}).")
    return 0


def _confirm_delete(targets: list[dict]) -> bool | None:
    """Ask on a terminal. ``None`` = no terminal to ask on (an agent)."""
    names = ", ".join(f"'{lbl.get('name')}'" for lbl in targets)
    if len(targets) == 1:
        question = (
            f"Delete label {names}? It comes off every task that carries it. [y/N] "
        )
    else:
        question = (
            f"Delete {len(targets)} labels ({names})? They come off every task "
            "that carries them. [y/N] "
        )
    try:
        answer = input(question).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None
    return answer in {"y", "yes"}


def _cmd_delete(args, api_key: str) -> int:
    labels = _list_labels(args, api_key)
    # Every ref resolves before anything is deleted, so a typo in the third
    # name doesn't leave the first two gone.
    targets = list(
        {
            str(lbl["id"]): lbl
            for lbl in (_pick(labels, str(ref), target=True) for ref in args.labels)
        }.values()
    )
    if not getattr(args, "yes", False):
        confirmed = _confirm_delete(targets)
        if confirmed is None:
            # Non-interactive without --yes: refuse rather than delete on an
            # unanswerable prompt.
            print(
                "\nAborted (pass --yes to delete non-interactively).", file=sys.stderr
            )
            return 1
        if not confirmed:
            print("Aborted.")
            return 0
    deleted: list[dict] = []
    failed = False
    for label in targets:
        try:
            request(
                args,
                api_key,
                "DELETE",
                f"/api/v1/task-labels/{label['id']}",
                raise_on_error=True,
            )
        except RequestError as exc:
            if _is_old_server(exc):
                print(_OLD_SERVER, file=sys.stderr)
                return 1
            print(f"Error: '{label.get('name')}': {exc}", file=sys.stderr)
            failed = True
            continue
        deleted.append(label)
        if not getattr(args, "json", False):
            print(f"Deleted label '{label.get('name')}'.")
    if getattr(args, "json", False) and (deleted or len(args.labels) > 1):
        # One ref → one object, several → a list (as `task update --json`).
        out = deleted[0] if len(args.labels) == 1 else deleted
        print(_json.dumps(out, indent=2))
    return 1 if failed else 0


_HANDLERS = {
    "ls": _cmd_ls,
    "create": _cmd_create,
    "update": _cmd_update,
    "delete": _cmd_delete,
}


def run_label_command(args) -> int:
    """Entry point wired into ``cli.py``'s dispatch for ``vicoa label``."""
    sub = getattr(args, "label_command", None)
    handler = _HANDLERS.get(sub) if sub else None
    if handler is None:
        print(
            "usage: vicoa label {ls,create,update,delete} ...\n"
            "Run `vicoa label --help` for details.",
            file=sys.stderr,
        )
        return 2
    api_key = resolve_api_key(args)
    return handler(args, api_key)
