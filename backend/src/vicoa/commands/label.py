"""``vicoa label`` — list and create the user's task labels.

Labels are the one vocabulary a user has across every project (Settings →
Tasks in the apps). ``task ls|create|update --label <name>`` take them by
name; this is where an agent sees which names exist, and where it can add
one before tagging with it. Rename / recolour / delete stay in the apps.

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

from vicoa.commands._api import request, resolve_api_key

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
    ids: list[str] = []
    for name in names:
        wanted = name.strip().lower()
        matches = [
            lbl for lbl in labels if str(lbl.get("name", "")).strip().lower() == wanted
        ]
        if len(matches) == 1:
            ids.append(str(matches[0]["id"]))
            continue
        if len(matches) > 1:
            print(
                f"Error: {len(matches)} labels are named '{name}'; rename one in "
                "Settings → Tasks and retry.",
                file=sys.stderr,
            )
            sys.exit(2)
        known = (
            ", ".join(sorted(str(lbl.get("name")) for lbl in labels)) or "(none yet)"
        )
        print(
            f"Error: no label named '{name}'. Your labels: {known}.\n"
            f"Create it with `vicoa label create {name!r}`.",
            file=sys.stderr,
        )
        sys.exit(2)
    return ids


def _print_label_table(labels: list[dict]) -> None:
    if not labels:
        print("No labels yet. Create one with `vicoa label create <name>`.")
        return
    header = f"{'ID':<8}  {'NAME':<24} {'COLOR':<8}"
    print(header)
    print("-" * len(header))
    for lbl in labels:
        print(
            f"{str(lbl.get('id') or '')[:8]:<8}  "
            f"{str(lbl.get('name') or ''):<24} "
            f"{str(lbl.get('color') or ''):<8}"
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


_HANDLERS = {"ls": _cmd_ls, "create": _cmd_create}


def run_label_command(args) -> int:
    """Entry point wired into ``cli.py``'s dispatch for ``vicoa label``."""
    sub = getattr(args, "label_command", None)
    handler = _HANDLERS.get(sub) if sub else None
    if handler is None:
        print(
            "usage: vicoa label {ls,create} ...\nRun `vicoa label --help` for details.",
            file=sys.stderr,
        )
        return 2
    api_key = resolve_api_key(args)
    return handler(args, api_key)
