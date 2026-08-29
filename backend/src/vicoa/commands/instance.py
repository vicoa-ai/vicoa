"""``vicoa session`` — list and inspect your agent sessions (agent instances).

Unlike ``vicoa ls`` (which enumerates agent processes *running on this
machine*), these commands read the backend, so they cover every session the
user owns — across machines, cloud/mobile-started, and finished ones — and can
print a session's full message transcript.

Talks to the agent-facing server with the same Bearer API key as every other
``vicoa`` command, hitting the read-only ``/api/v1/agent-instances`` endpoints
mirrored in ``servers/api/instances.py``. Human-readable output by default;
``--json`` on every subcommand for agents (or scripts) that want to parse it.
"""

from __future__ import annotations

import json as _json
import os
import re
import sys
from typing import Any, Optional
from uuid import UUID

from vicoa.commands._api import request, resolve_api_key

# One backend page is enough to resolve a short id and, at 500, to pull most
# transcripts in a single round-trip. Mirrors the server's ``le=500`` cap.
_MSG_PAGE = 500


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_AGENT_W = 12  # fits "Claude Code" / "OpenCode" without truncating to "Claude …"
_MODEL_W = 18
_NAME_W = 24
_PROJECT_W = 18


def _fit(s: str, width: int) -> str:
    s = s or ""
    return s if len(s) <= width else s[: width - 1] + "…"


def _short(value: Optional[str], n: int = 8) -> str:
    return value[:n] if value else "—"


def _model_of(item: dict) -> str:
    """Model slug from the already-fetched ``session_config`` (no extra call)."""
    sc = item.get("session_config")
    if isinstance(sc, dict) and sc.get("model"):
        return str(sc["model"])
    return "—"


def _basename(path: Optional[str]) -> str:
    if not path:
        return "—"
    # Last path segment, tolerant of both separators; falls back to the whole
    # string (e.g. a git URL) when there is no separator.
    tail = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return _fit(tail or path, _PROJECT_W)


# In-band control tokens the dashboards append to messages, e.g.
# `Stop current task. {"type":"control","setting":"interrupt"}` or a bare
# persist-only summary blob. Mirrors vicoa-web/lib/control-messages.ts so the
# CLI hides exactly what the web does.
_CONTROL_RE = re.compile(r'\{\s*"type"\s*:\s*"control"[^}]*\}', re.IGNORECASE)
# Tool-use messages render as `🔧 Using tool: <name>[ - detail]` with any
# payload (diff, file body, command output) on the following lines. See
# integrations/cli_wrappers/.../format_utils.py and headless/format_tools.py.
_TOOL_RE = re.compile(r"^\s*(?:🔧\s*)?Using tool:", re.IGNORECASE)


def _is_control_envelope(content: str) -> bool:
    """True only when ``content`` *is* a control directive, not prose quoting one.

    From the first control token to the end there must be nothing but control
    tokens and whitespace — so a real message that merely pastes control JSON
    stays visible. Matches the web's ``isControlEnvelope``.
    """
    if not content:
        return False
    match = _CONTROL_RE.search(content)
    if not match:
        return False
    residue = _CONTROL_RE.sub("", content[match.start() :])
    return residue.strip() == ""


def _split_tool_use(content: str) -> tuple[Optional[str], str]:
    """Split a tool-use message into (header line, payload).

    Returns ``(None, "")`` when ``content`` isn't a tool-use message. The header
    (``Using tool: X``) is always shown; the payload is gated behind
    ``--tool-content``. AskUserQuestion and friends have an empty payload.
    """
    lines = (content or "").splitlines()
    if lines and _TOOL_RE.match(lines[0]):
        return lines[0].rstrip(), "\n".join(lines[1:]).strip("\n")
    return None, ""


def _ask_user_question_lines(aq: dict) -> list[str]:
    """Format an AskUserQuestion's questions/options for the transcript.

    AskUserQuestion carries its real content in
    ``message_metadata["ask_user_question"]`` (the message body is just the
    ``Using tool`` header), so it would otherwise render blank. Shape is shared
    across wrappers: ``{questions: [{question, header, options:[{label,
    description}], multi_select}]}``.
    """
    out: list[str] = []
    for q in aq.get("questions", []) if isinstance(aq, dict) else []:
        question = (q.get("question") or "").strip()
        header = (q.get("header") or "").strip()
        suffix = f"  ({header})" if header else ""
        if q.get("multi_select") or q.get("multiSelect"):
            suffix += "  [select multiple]"
        out.append(f"❓ {question}{suffix}" if question else f"❓{suffix}")
        for opt in q.get("options") or []:
            label = (opt.get("label") or "").strip()
            desc = (opt.get("description") or "").strip()
            out.append(f"   • {label} — {desc}" if desc else f"   • {label}")
    return out


def _local_time(iso: Optional[str]) -> str:
    """Render an ISO-8601 timestamp (the API appends ``Z``) as local ``HH:MM``.

    Best-effort: returns the raw string on any parse failure so the transcript
    never crashes on an unexpected format.
    """
    if not iso:
        return "—"
    from datetime import datetime

    try:
        cleaned = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return iso


_RESET_W = 16  # matches _local_time's "YYYY-MM-DD HH:MM"


def _print_instance_table(items: list[dict], total: Optional[int]) -> None:
    if not items:
        print("No sessions found.")
        return
    # Only surface the RESET column when it carries information — a plain
    # `session ls` shouldn't widen for a field that's empty on every row.
    show_reset = any(it.get("rate_limited") for it in items)
    header = (
        f"{'ID':<8}  {'AGENT':<{_AGENT_W}} {'MODEL':<{_MODEL_W}} {'STATUS':<12} "
        f"{'NAME':<{_NAME_W}} {'PROJECT':<{_PROJECT_W}} {'MSGS':>5}  {'STARTED':<19}"
    )
    if show_reset:
        header += f"  {'RESET':<{_RESET_W}}"
    print(header)
    print("-" * len(header))
    for it in items:
        line = (
            f"{_short(it.get('id')):<8}  "
            f"{_fit(str(it.get('agent_type_name') or '—'), _AGENT_W):<{_AGENT_W}} "
            f"{_fit(_model_of(it), _MODEL_W):<{_MODEL_W}} "
            f"{str(it.get('status') or ''):<12} "
            f"{_fit(it.get('name') or '—', _NAME_W):<{_NAME_W}} "
            f"{_basename(it.get('project')):<{_PROJECT_W}} "
            f"{it.get('chat_length', 0):>5}  "
            f"{_local_time(it.get('started_at')):<19}"
        )
        if show_reset:
            reset = (
                _local_time(it.get("rate_limit_resets_at"))
                if it.get("rate_limited")
                else "—"
            )
            line += f"  {reset:<{_RESET_W}}"
        print(line)
    shown = len(items)
    suffix = f" of {total}" if total is not None and total > shown else ""
    print(f"\n{shown} session(s){suffix}.")


def _print_instance_detail(
    header: dict,
    messages: list[dict],
    *,
    timestamps: bool,
    emails: bool,
    control: bool,
    tool_content: bool,
) -> None:
    lines = [
        f"id:          {header.get('agent_instance_id')}",
        f"name:        {header.get('name') or '—'}",
        f"agent:       {header.get('agent_type_name') or '—'}",
        f"status:      {header.get('status')}",
        f"project:     {header.get('project') or '—'}",
        f"home_dir:    {header.get('home_dir') or '—'}",
        f"machine_id:  {header.get('machine_id') or '—'}",
    ]
    session_config = header.get("session_config")
    if isinstance(session_config, dict) and session_config.get("model"):
        lines.append(f"model:       {session_config['model']}")
    print("\n".join(lines))

    print("\n─── transcript " + "─" * 30)
    hidden_control = 0
    hidden_payloads = 0
    shown = 0
    for msg in messages:
        content = msg.get("content") or ""
        if _is_control_envelope(content):
            if not control:
                hidden_control += 1
                continue

        # Header line: LABEL, optionally prefixed by timestamp and suffixed by
        # sender email (user messages) and an awaiting-reply marker.
        sender = str(msg.get("sender_type") or "?").upper()
        parts: list[str] = []
        if timestamps:
            parts.append(f"[{_local_time(msg.get('created_at'))}]")
        if emails and sender == "USER":
            who = msg.get("sender_user_display_name") or msg.get("sender_user_email")
            parts.append(f"{sender} ({who})" if who else sender)
        else:
            parts.append(sender)
        if msg.get("requires_user_input"):
            parts.append("⏳ awaiting reply")
        print(f"\n{' '.join(parts)}")
        shown += 1

        tool_header, payload = _split_tool_use(content)
        if tool_header is not None:
            # Tool name always shows; the payload (diff/file/output) is opt-in.
            print(f"  {tool_header}")
            if payload:
                if tool_content:
                    for line in payload.splitlines():
                        print(f"  {line}")
                else:
                    hidden_payloads += 1
        else:
            for line in content.rstrip().splitlines():
                print(f"  {line}")

        # AskUserQuestion's question/options live in metadata, not the body.
        # Show them by default — they're the point of the message, not noise.
        meta = msg.get("message_metadata")
        aq = meta.get("ask_user_question") if isinstance(meta, dict) else None
        if aq:
            for line in _ask_user_question_lines(aq):
                print(f"    {line}")

    if not shown and not hidden_control:
        print("(no messages)")
    # Surface what was suppressed so a terse default never reads as "complete".
    notes = []
    if hidden_control:
        notes.append(f"{hidden_control} control message(s)")
    if hidden_payloads:
        notes.append(f"{hidden_payloads} tool payload(s)")
    if notes:
        print(
            f"\n({' and '.join(notes)} hidden — "
            "use --control / --tool-content / --full to show)"
        )


# ---------------------------------------------------------------------------
# Id resolution
# ---------------------------------------------------------------------------


def _resolve_instance_id(args, api_key: str, ref: str) -> str:
    """Resolve a full UUID as-is, or a short prefix via the backend list.

    ``vicoa ls`` prints 8-char prefixes, so accept those here (like
    ``vicoa stop``). Prefix lookup only scans the caller's most-recent
    ``_MSG_PAGE`` sessions; a full UUID always works if the prefix is too old
    or ambiguous.
    """
    try:
        UUID(ref)
        return ref
    except ValueError:
        pass

    data = request(
        args,
        api_key,
        "GET",
        "/api/v1/agent-instances",
        params={"limit": 100},
    )
    items = data.get("items", []) if isinstance(data, dict) else []
    matches = [it for it in items if str(it.get("id", "")).startswith(ref)]
    if not matches:
        print(
            f"No session found matching '{ref}'. "
            "Pass the full id, or run `vicoa session ls` to find it.",
            file=sys.stderr,
        )
        sys.exit(1)
    if len(matches) > 1:
        shown = ", ".join(str(m.get("id"))[:8] for m in matches)
        print(
            f"'{ref}' is ambiguous — matches {shown}. Use more characters.",
            file=sys.stderr,
        )
        sys.exit(1)
    return str(matches[0]["id"])


def _fetch_transcript(
    args, api_key: str, instance_id: str, limit: int, fetch_all: bool
) -> list[dict]:
    """Fetch a session's messages, oldest-first.

    Without ``--all`` this is the newest ``limit`` messages in one call. With
    ``--all`` it walks the cursor backwards (``before_message_id``) prepending
    each older page until the history is exhausted.
    """
    endpoint = f"/api/v1/agent-instances/{instance_id}/messages"
    if not fetch_all:
        page = request(args, api_key, "GET", endpoint, params={"limit": max(1, limit)})
        return page or []

    collected: list[dict] = []
    before: Optional[str] = None
    while True:
        params: dict[str, Any] = {"limit": _MSG_PAGE}
        if before:
            params["before_message_id"] = before
        page = request(args, api_key, "GET", endpoint, params=params) or []
        if not page:
            break
        collected = page + collected  # page is oldest-first; older page leads
        before = page[0].get("id")
        if len(page) < _MSG_PAGE or not before:
            break
    return collected


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _cmd_ls(args, api_key: str) -> int:
    params: dict[str, Any] = {"limit": getattr(args, "limit", 50)}
    if getattr(args, "active", False):
        params["active_only"] = "true"
    if getattr(args, "rate_limited", False):
        params["rate_limited_only"] = "true"
        # When this runs inside an automation-spawned session, tell the server
        # who's asking so it can exclude *this automation's own* sessions from
        # the sweep (no self-continue loop). Absent for a human/manual caller.
        self_id = os.environ.get("VICOA_AGENT_INSTANCE_ID")
        if self_id:
            params["caller_instance_id"] = self_id
    data = request(args, api_key, "GET", "/api/v1/agent-instances", params=params)
    items = data.get("items", []) if isinstance(data, dict) else []
    if getattr(args, "json", False):
        print(_json.dumps(data, indent=2))
    else:
        _print_instance_table(
            items, total=data.get("total") if isinstance(data, dict) else None
        )
    return 0


def _cmd_get(args, api_key: str) -> int:
    instance_id = _resolve_instance_id(args, api_key, args.session_id)
    header = request(args, api_key, "GET", f"/api/v1/agent-instances/{instance_id}")
    fetch_all = getattr(args, "all_messages", False)
    messages = _fetch_transcript(
        args,
        api_key,
        instance_id,
        limit=getattr(args, "limit", 50),
        fetch_all=fetch_all,
    )
    # Optional sender filter — applied client-side after the fetch, so it narrows
    # both the JSON and the rendered transcript. Note the interaction with
    # --limit below: the limit bounds the *fetch* (all senders), so a filtered
    # page can be much shorter than --limit.
    role = getattr(args, "role", None)
    filtered_out = 0
    if role:
        want = role.upper()
        kept = [m for m in messages if str(m.get("sender_type") or "").upper() == want]
        filtered_out = len(messages) - len(kept)
        messages = kept
    if getattr(args, "json", False):
        print(_json.dumps({"instance": header, "messages": messages}, indent=2))
    else:
        full = getattr(args, "full", False)
        _print_instance_detail(
            header,
            messages,
            timestamps=full or getattr(args, "timestamps", False),
            emails=full or getattr(args, "emails", False),
            control=full or getattr(args, "show_control", False),
            tool_content=full or getattr(args, "tool_content", False),
        )
        # --limit counts all senders before this filter runs, so a default
        # `session get --role user` can hide most of the fetched page. Say so,
        # and point at --all, unless the caller already asked for everything.
        if role and filtered_out and not fetch_all:
            print(
                f"\n(showing {role} messages only; {filtered_out} other-sender "
                "message(s) from this page hidden — --limit counts all senders, "
                "so pass --all for the full history)"
            )
    return 0


def _cmd_update(args, api_key: str) -> int:
    """Rename a session and/or (un)link its task via the instance PATCH.

    Mirrors the web: ``--title`` renames (``name``) and ``--task`` /
    ``--unlink-task`` stamp or clear ``task_id`` — which drives the linked
    task's status from the session's status server-side, so linking a
    running session flips its task to in_progress.
    """
    if getattr(args, "task", None) and getattr(args, "unlink_task", False):
        print("Pass either --task or --unlink-task, not both.", file=sys.stderr)
        return 2

    body: dict[str, Any] = {}
    if getattr(args, "title", None) is not None:
        body["name"] = args.title
    if getattr(args, "task", None):
        body["task_id"] = args.task
    elif getattr(args, "unlink_task", False):
        body["task_id"] = None

    if not body:
        print(
            "Nothing to update — pass --title, --task, or --unlink-task.",
            file=sys.stderr,
        )
        return 2

    instance_id = _resolve_instance_id(args, api_key, args.session_id)
    updated = request(
        args,
        api_key,
        "PATCH",
        f"/api/v1/agent-instances/{instance_id}",
        json=body,
    )
    if getattr(args, "json", False):
        print(_json.dumps(updated, indent=2))
        return 0

    changes: list[str] = []
    if "name" in body:
        changes.append(f'title set to "{body["name"]}"')
    if "task_id" in body:
        changes.append(
            f"linked to task {_short(body['task_id'])}"
            if body["task_id"]
            else "task unlinked"
        )
    print(f"Updated session {_short(instance_id)} — {', '.join(changes)}.")
    return 0


def _send_user_message(args, api_key: str, instance_id: str, content: str) -> dict:
    """POST a USER message to a session via the agent-facing message endpoint.

    Reuses ``POST /api/v1/messages/user`` — the same primitive the web/app use —
    which inserts a ``sender_type=USER`` message, flips the instance back to
    ACTIVE, and broadcasts it into the running agent's input. User-scoped by the
    API key, so it only ever reaches the caller's own sessions.
    """
    return request(
        args,
        api_key,
        "POST",
        "/api/v1/messages/user",
        json={"agent_instance_id": instance_id, "content": content},
    )


def _cmd_message(args, api_key: str) -> int:
    """Send an arbitrary message into a session (``vicoa session message``)."""
    content = (getattr(args, "text", None) or "").strip()
    if not content:
        print("Message text is required.", file=sys.stderr)
        return 2
    instance_id = _resolve_instance_id(args, api_key, args.session_id)
    result = _send_user_message(args, api_key, instance_id, content)
    if getattr(args, "json", False):
        print(_json.dumps(result, indent=2))
        return 0
    print(f"Sent message to session {_short(instance_id)}.")
    return 0


def _cmd_continue(args, api_key: str) -> int:
    """Sugar for the 90% case: send the literal ``continue`` to a session.

    This is what an auto-continue automation calls once a rate-limited session's
    window has reset — the CLI equivalent of typing ``continue`` in the TUI.
    """
    instance_id = _resolve_instance_id(args, api_key, args.session_id)
    result = _send_user_message(args, api_key, instance_id, "continue")
    if getattr(args, "json", False):
        print(_json.dumps(result, indent=2))
        return 0
    print(f"Continued session {_short(instance_id)}.")
    return 0


_HANDLERS = {
    "ls": _cmd_ls,
    "get": _cmd_get,
    "update": _cmd_update,
    "message": _cmd_message,
    "continue": _cmd_continue,
}


def run_session_command(args) -> int:
    """Entry point wired into ``cli.py``'s dispatch for ``vicoa session``."""
    sub = getattr(args, "session_command", None)
    handler = _HANDLERS.get(sub) if sub else None
    if handler is None:
        print(
            "usage: vicoa session {ls,get,update,message,continue} ...\n"
            "Run `vicoa session --help` for details.",
            file=sys.stderr,
        )
        return 2
    api_key = resolve_api_key(args)
    return handler(args, api_key)
