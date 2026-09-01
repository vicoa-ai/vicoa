"""``vicoa session`` — start, list, and inspect your agent sessions.

Unlike ``vicoa ls`` (which enumerates agent processes *running on this
machine*), these commands read the backend, so they cover every session the
user owns — across machines, cloud/mobile-started, and finished ones — and can
print a session's full message transcript.

``vicoa session start`` is the terminal equivalent of the desktop/web "New
Session" composer: it picks a machine, directory, agent and model/config, then
POSTs a spawn-request that the target machine's daemon claims and launches —
the exact same spawn path the apps drive, just triggered over REST instead of
the WebSocket ``spawn-session`` RPC. The machine's ``vicoa daemon`` must be
running/connected for the request to be picked up.

Talks to the agent-facing server with the same Bearer API key as every other
``vicoa`` command, hitting the ``/api/v1/agent-instances`` and
``/api/v1/machines`` endpoints. Human-readable output by default; ``--json`` on
every subcommand for agents (or scripts) that want to parse it.
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


# ---------------------------------------------------------------------------
# session start — spawn a new session (mirrors the desktop "New Session")
# ---------------------------------------------------------------------------


def _load_agent_catalog():
    """Deferred import of the static catalog + its validation sets.

    Kept out of module load (``cli.py`` imports this module eagerly) since it's
    only needed when actually spawning. ``protocol`` is on the path in both the
    source tree and the frozen daemon — ``machine_daemon`` imports it the same
    way — so this resolves in a packaged CLI too.
    """
    from protocol.agent_catalog import (
        AGENT_CATALOG,
        PERMISSION_MODES,
        REASONING_EFFORTS,
        THINKING_EFFORTS,
    )

    return AGENT_CATALOG, PERMISSION_MODES, THINKING_EFFORTS, REASONING_EFFORTS


def _agent_entry(catalog: dict, agent_id: str) -> Optional[dict]:
    for agent in catalog.get("agents", []):
        if agent.get("id") == agent_id:
            return agent
    return None


def _fetch_machines(args, api_key: str) -> list[dict]:
    data = request(args, api_key, "GET", "/api/v1/machines")
    return data.get("machines", []) if isinstance(data, dict) else []


def _machine_label(m: dict) -> str:
    return m.get("display_name") or m.get("hostname") or _short(m.get("machine_id"))


# Mirrors ``settings.liveness_online_threshold_seconds`` (90) and the web's
# ``LIVENESS_ONLINE_THRESHOLD_MS`` in apps/web/lib/session-liveness.ts: daemons
# beat every 30s, so ~3 missed beats means offline. Kept as a local constant
# rather than importing ``shared.database.liveness`` — that pulls in the DB/env
# settings module, which the lightweight REST-only CLI shouldn't need to load.
_MACHINE_ONLINE_THRESHOLD_SECONDS = 90


def _machine_online(m: dict) -> bool:
    """Whether a machine's daemon heartbeat is fresh enough to accept work."""
    from datetime import datetime, timezone

    ts = m.get("last_heartbeat_at")
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - dt).total_seconds()
    return age < _MACHINE_ONLINE_THRESHOLD_SECONDS


def _local_machine_id(args) -> Optional[str]:
    """The ``machine_id`` the local daemon persisted for this base URL, if any.

    The daemon writes it to ``~/.vicoa/daemon_state.json`` at registration, so
    this is how the CLI defaults ``--machine`` to "this host" — the same id the
    backend knows this machine by, not a recomputed fingerprint (which is only
    the create-time seed and can differ from the registered row).
    """
    try:
        from vicoa.constants import DEFAULT_API_URL
        from vicoa.machine_state import read_daemon_entry

        base_url = getattr(args, "base_url", None) or DEFAULT_API_URL
        entry = read_daemon_entry(base_url)
        mid = entry.get("machine_id") if isinstance(entry, dict) else None
        return str(mid) if mid else None
    except Exception:  # noqa: BLE001 - best-effort; missing state just means "no default"
        return None


def _print_machines(machines: list[dict]) -> None:
    if not machines:
        print(
            "No machines registered. Start the Vicoa daemon on a machine first "
            "(`vicoa daemon`)."
        )
        return
    header = (
        f"{'ID':<10}  {'NAME':<20} {'HOSTNAME':<20} {'PLATFORM':<10} "
        f"{'STATUS':<8} {'LAST SEEN':<16}"
    )
    print(header)
    print("-" * len(header))
    for m in machines:
        status = "online" if _machine_online(m) else "offline"
        print(
            f"{_short(m.get('machine_id'), 10):<10}  "
            f"{_fit(m.get('display_name') or '—', 20):<20} "
            f"{_fit(m.get('hostname') or '—', 20):<20} "
            f"{_fit(str(m.get('platform') or '—'), 10):<10} "
            f"{status:<8} "
            f"{_local_time(m.get('last_heartbeat_at')):<16}"
        )
    print(f"\n{len(machines)} machine(s).")


def _match_machine(machines: list[dict], ref: str) -> dict:
    """Resolve an explicit ref by id (exact/prefix) or name/hostname substring."""
    for m in machines:
        if str(m.get("machine_id")) == ref:
            return m

    low = ref.lower()
    matches = [
        m
        for m in machines
        if str(m.get("machine_id", "")).startswith(ref)
        or low in (m.get("display_name") or "").lower()
        or low in (m.get("hostname") or "").lower()
    ]
    if not matches:
        print(
            f"No machine matching '{ref}'. "
            "Run `vicoa session start --list-machines` to see them.",
            file=sys.stderr,
        )
        sys.exit(1)
    if len(matches) > 1:
        shown = ", ".join(
            f"{_machine_label(m)} ({_short(m.get('machine_id'))})" for m in matches
        )
        print(
            f"'{ref}' is ambiguous — matches {shown}. Pass the full machine id.",
            file=sys.stderr,
        )
        sys.exit(1)
    return matches[0]


def _select_machine(args, api_key: str, ref: Optional[str]) -> dict:
    """Pick the target machine — an explicit ``--machine`` or this local host.

    With no ref we default to the machine this host's daemon registered (read
    from local daemon state), matching the desktop's "runs on this computer"
    default. If there's no local daemon we can't guess a remote one, so we fail
    with guidance rather than silently picking someone else's machine.
    """
    machines = _fetch_machines(args, api_key)
    if not machines:
        print(
            "No machines registered. Start the Vicoa daemon on a machine first "
            "(`vicoa daemon`).",
            file=sys.stderr,
        )
        sys.exit(1)

    if ref:
        return _match_machine(machines, ref)

    local_id = _local_machine_id(args)
    if not local_id:
        print(
            "No --machine given and no local daemon found on this host.\n"
            "Pass --machine (see `vicoa session start --list-machines`) or run "
            "`vicoa daemon` here first.",
            file=sys.stderr,
        )
        sys.exit(1)
    for m in machines:
        if str(m.get("machine_id")) == local_id:
            return m
    print(
        f"This host's daemon ({_short(local_id)}) isn't registered on this server. "
        "Run `vicoa daemon` here, or pass --machine.",
        file=sys.stderr,
    )
    sys.exit(1)


def _print_models(catalog: dict, agent_filter: Optional[str]) -> int:
    agents = catalog.get("agents", [])
    if agent_filter:
        agents = [a for a in agents if a.get("id") == agent_filter]
        if not agents:
            known = ", ".join(a["id"] for a in catalog.get("agents", []))
            print(
                f"Unknown agent '{agent_filter}'. Known agents: {known}.",
                file=sys.stderr,
            )
            return 2

    def _ids(entries: Optional[list]) -> str:
        out = []
        for e in entries or []:
            out.append(f"{e['id']}*" if e.get("is_default") else e["id"])
        return ", ".join(out) if out else "—"

    for agent in agents:
        print(f"\n{agent.get('label', agent['id'])}  ({agent['id']})")
        print(f"  models:           {_ids(agent.get('models'))}")
        if agent.get("thinking_efforts"):
            print(f"  thinking efforts: {_ids(agent.get('thinking_efforts'))}")
        if agent.get("reasoning_efforts"):
            print(f"  reasoning efforts:{_ids(agent.get('reasoning_efforts'))}")
        if agent.get("permission_modes"):
            print(f"  permission modes: {_ids(agent.get('permission_modes'))}")
        if agent.get("modes"):
            print(f"  modes:            {_ids(agent.get('modes'))}")
    print("\n(* = default)")
    return 0


def _validate_and_build_metadata(args, agent: str) -> dict:
    """Validate the picked config against the catalog and build spawn metadata.

    Mirrors the web's ``toSpawnMetadata`` (apps/web/lib/agent-catalog.ts): the
    daemon's ``_extract_*`` helpers read these exact keys when building the
    headless command. Unknown effort/permission/mode values are hard errors;
    an unrecognised model is a soft warning (per-install ACP/opencode models
    aren't in the static catalog), so the daemon still applies it best-effort.
    """
    catalog, permission_modes, thinking_efforts, reasoning_efforts = (
        _load_agent_catalog()
    )
    entry = _agent_entry(catalog, agent)
    if entry is None:
        known = ", ".join(a["id"] for a in catalog.get("agents", []))
        print(f"Unknown agent '{agent}'. Known agents: {known}.", file=sys.stderr)
        sys.exit(2)

    model = getattr(args, "model", None)
    effort = getattr(args, "effort", None)
    permission_mode = getattr(args, "permission_mode", None)
    opencode_mode = getattr(args, "opencode_mode", None)

    # Soft-validate the model against the static catalog.
    if model:
        known_models = {m["id"] for m in entry.get("models") or []}
        if known_models and model not in known_models:
            print(
                f"Warning: '{model}' isn't a catalog model for {agent} "
                f"({', '.join(sorted(known_models))}); passing it through anyway.",
                file=sys.stderr,
            )

    # Effort routes to a per-agent key; reject when the agent has no such axis.
    if effort:
        if agent == "claude" and effort not in thinking_efforts:
            print(
                f"Invalid effort '{effort}' for claude. "
                f"Valid: {', '.join(sorted(thinking_efforts))}.",
                file=sys.stderr,
            )
            sys.exit(2)
        if agent == "codex" and effort not in reasoning_efforts:
            print(
                f"Invalid effort '{effort}' for codex. "
                f"Valid: {', '.join(sorted(reasoning_efforts))}.",
                file=sys.stderr,
            )
            sys.exit(2)
        if agent not in ("claude", "codex"):
            print(
                f"Warning: --effort is only used by claude/codex; ignored for {agent}.",
                file=sys.stderr,
            )
            effort = None

    if permission_mode:
        valid = permission_modes.get(agent)
        # Only hard-fail when the agent declares a permission-mode set; ACP
        # agents validate against their live session, so pass through otherwise.
        if valid and permission_mode not in valid:
            print(
                f"Invalid --permission-mode '{permission_mode}' for {agent}. "
                f"Valid: {', '.join(sorted(valid))}.",
                file=sys.stderr,
            )
            sys.exit(2)

    if opencode_mode:
        if agent != "opencode":
            print(
                "Warning: --opencode-mode only applies to opencode; ignored.",
                file=sys.stderr,
            )
            opencode_mode = None
        else:
            valid_modes = {e["id"] for e in entry.get("modes") or []}
            if valid_modes and opencode_mode not in valid_modes:
                print(
                    f"Invalid --opencode-mode '{opencode_mode}'. "
                    f"Valid: {', '.join(sorted(valid_modes))}.",
                    file=sys.stderr,
                )
                sys.exit(2)

    meta: dict[str, Any] = {}
    name = getattr(args, "name", None)
    if name:
        meta["name"] = name

    if agent == "claude":
        if model:
            meta["model"] = model
        if effort:
            meta["thinking_effort"] = effort
            # Dual-write for old daemons, exactly as the web does.
            meta["enable_thinking"] = effort != "off"
        if permission_mode:
            meta["permission_mode"] = permission_mode
    elif agent == "codex":
        if model:
            meta["model"] = model
        if effort:
            meta["reasoning_effort"] = effort
        if permission_mode:
            meta["permission_mode"] = permission_mode
    elif agent == "opencode":
        if opencode_mode:
            meta["agent_mode"] = opencode_mode
        # `default`/`auto` keep OpenCode's own configured model.
        if model and model not in ("default", "auto"):
            meta["model"] = model
    else:  # generic ACP agents (cursor/gemini/copilot/kimi/hermes)
        if model:
            meta["model"] = model
        if permission_mode:
            meta["permission_mode"] = permission_mode

    return meta


def _wait_for_status(
    args, api_key: str, instance_id: str, timeout: float
) -> Optional[str]:
    """Poll the instance until it leaves STARTING, or the timeout elapses.

    Returns the last-seen status. The spawn is asynchronous — the daemon claims
    the request and launches out of band — so this gives ``--wait`` callers a
    concrete "it's running" (or the error the daemon reported) instead of just
    a freshly-minted id.
    """
    import time

    endpoint = f"/api/v1/agent-instances/{instance_id}"
    deadline = time.monotonic() + timeout
    last: Optional[str] = None
    while True:
        header = request(args, api_key, "GET", endpoint)
        last = str(header.get("status") or "") if isinstance(header, dict) else last
        if last and last.upper() != "STARTING":
            return last
        if time.monotonic() >= deadline:
            return last
        time.sleep(2.0)


def _cmd_start(args, api_key: str) -> int:
    """Spawn a new session on a chosen machine (the desktop "New Session")."""
    as_json = getattr(args, "json", False)

    # Discovery short-circuits: list machines or the model/agent catalog.
    if getattr(args, "list_machines", False):
        machines = _fetch_machines(args, api_key)
        if as_json:
            print(_json.dumps({"machines": machines}, indent=2))
        else:
            _print_machines(machines)
        return 0
    if getattr(args, "list_models", False):
        catalog, *_ = _load_agent_catalog()
        agent_filter = getattr(args, "agent", None)
        if as_json:
            agents = catalog.get("agents", [])
            if agent_filter:
                agents = [a for a in agents if a.get("id") == agent_filter]
            print(_json.dumps({"agents": agents}, indent=2))
            return 0
        return _print_models(catalog, agent_filter)

    machine_ref = getattr(args, "machine", None)
    directory = getattr(args, "dir", None)
    if not directory:
        print(
            "--dir is required to start a session.\n"
            "See machines with `vicoa session start --list-machines` and models "
            "with `vicoa session start --list-models`.",
            file=sys.stderr,
        )
        return 2

    agent = (getattr(args, "agent", None) or "claude").strip().lower()
    metadata = _validate_and_build_metadata(args, agent)

    machine = _select_machine(args, api_key, machine_ref)
    machine_id = str(machine["machine_id"])

    # A spawn-request only runs when the machine's daemon claims it. If the
    # daemon looks offline the request would silently queue forever, so refuse
    # by default — unless the caller explicitly wants it queued for whenever the
    # host next reconnects (a legit "start this when my laptop wakes" flow).
    online = _machine_online(machine)
    if not online:
        last_seen = _local_time(machine.get("last_heartbeat_at"))
        if getattr(args, "allow_offline", False):
            print(
                f"Warning: daemon on {_machine_label(machine)} looks offline "
                f"(last seen {last_seen}); queuing the request until it reconnects.",
                file=sys.stderr,
            )
        else:
            print(
                f"Daemon on {_machine_label(machine)} looks offline "
                f"(last seen {last_seen}). Start it with `vicoa daemon` on that "
                "machine, or pass --allow-offline to queue the request until it "
                "reconnects.",
                file=sys.stderr,
            )
            return 1

    body: dict[str, Any] = {"directory": directory, "agent": agent}
    prompt = getattr(args, "prompt", None)
    if prompt and prompt.strip():
        body["prompt"] = prompt
    if metadata:
        body["metadata"] = metadata

    result = request(
        args,
        api_key,
        "POST",
        f"/api/v1/machines/{machine_id}/spawn-requests",
        json=body,
    )
    instance_id = (
        str(result.get("agent_instance_id")) if isinstance(result, dict) else ""
    )

    # Link a task if asked — mirrors `session update --task`, which drives the
    # task's status from the session server-side.
    task_id = getattr(args, "task", None)
    if task_id and instance_id:
        request(
            args,
            api_key,
            "PATCH",
            f"/api/v1/agent-instances/{instance_id}",
            json={"task_id": task_id},
        )

    final_status: Optional[str] = None
    if getattr(args, "wait", False) and instance_id:
        final_status = _wait_for_status(
            args, api_key, instance_id, timeout=getattr(args, "wait_timeout", 60.0)
        )

    if as_json:
        out = dict(result) if isinstance(result, dict) else {}
        out["machine_id"] = machine_id
        if final_status is not None:
            out["status"] = final_status
        print(_json.dumps(out, indent=2))
        return 0

    verb = "Started" if online else "Queued"
    print(
        f"{verb} {agent} session on {_machine_label(machine)} in {directory} "
        f"— session {_short(instance_id)}."
    )
    if final_status is not None:
        print(f"Status: {final_status}.")
    print(
        f"Track it with `vicoa session get {_short(instance_id)}` "
        f"or send input with `vicoa session message {_short(instance_id)} '...'`."
    )
    return 0


_HANDLERS = {
    "start": _cmd_start,
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
            "usage: vicoa session {start,ls,get,update,message,continue} ...\n"
            "Run `vicoa session --help` for details.",
            file=sys.stderr,
        )
        return 2
    api_key = resolve_api_key(args)
    return handler(args, api_key)
