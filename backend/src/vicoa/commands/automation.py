"""``vicoa automation`` — list, read, create, edit, and delete scheduled automations.

An automation is a saved prompt + agent/model + machine/folder that fires an
agent session automatically at a chosen time (once, or on a recurring schedule).
Built so a running AI agent can manage its user's automations without leaving
the terminal (``vicoa automation create "Nightly triage" --prompt ... --daily``).

Talks to the agent-facing server (``agents.vicoa.ai``) with the same Bearer API
key every other ``vicoa`` command uses, hitting the ``/api/v1/automations``
endpoints mirrored in ``servers/api/automations.py``. Human-readable tables by
default; ``--json`` on every subcommand for agents (or scripts) that want to
parse the result.

CRUD only: this manages the schedule rows. The actual firing happens in the
server's scheduler sweep, so an automation created here dispatches on its own —
there is no ``run now`` here.
"""

from __future__ import annotations

import argparse
import json as _json
import os
import sys
from typing import Any, Optional

from vicoa.commands._api import request, resolve_api_key
from vicoa.constants import DEFAULT_API_URL

# Weekday convention is 0=Sunday … 6=Saturday (JS getDay), matching the web and
# shared/scheduling/frequency.py. Documented on the --weekly flag too.
_WEEKDAY_MIN, _WEEKDAY_MAX = 0, 6
_DEFAULT_TIME = "09:00"


# ---------------------------------------------------------------------------
# Body builders (schedule + session config from flags)
# ---------------------------------------------------------------------------


def _parse_weekdays(raw: str) -> list[int]:
    """Parse ``"1,3,5"`` into ``[1, 3, 5]``, validating the 0–6 range."""
    days: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            day = int(part)
        except ValueError as exc:
            raise ValueError(f"weekday must be an integer 0–6, got {part!r}") from exc
        if not _WEEKDAY_MIN <= day <= _WEEKDAY_MAX:
            raise ValueError(f"weekday must be 0 (Sun)–6 (Sat), got {day}")
        days.append(day)
    if not days:
        raise ValueError("--weekly needs at least one weekday, e.g. --weekly 1,3,5")
    return days


def _schedule_fields(args) -> dict[str, Any]:
    """Build the schedule portion of the request body from the schedule flags.

    Returns only the keys the user actually selected (so an ``update`` leaves the
    schedule untouched when no selector is passed). Raises ``ValueError`` if more
    than one selector is given; the caller enforces "exactly one" for create.
    """
    time = getattr(args, "time", None) or _DEFAULT_TIME
    selectors: list[tuple[str, dict[str, Any]]] = []

    if getattr(args, "at", None):
        selectors.append(("at", {"schedule_kind": "once", "run_at": args.at}))
    if getattr(args, "daily", False):
        selectors.append(
            (
                "daily",
                {
                    "schedule_kind": "recurring",
                    "frequency": {"kind": "daily", "time": time},
                },
            )
        )
    if getattr(args, "hourly", False):
        minute = getattr(args, "minute", None)
        minute = 0 if minute is None else minute
        selectors.append(
            (
                "hourly",
                {
                    "schedule_kind": "recurring",
                    "frequency": {"kind": "hourly", "minute": minute},
                },
            )
        )
    if getattr(args, "weekdays", False):
        selectors.append(
            (
                "weekdays",
                {
                    "schedule_kind": "recurring",
                    "frequency": {"kind": "weekdays", "time": time},
                },
            )
        )
    if getattr(args, "weekly", None):
        days = _parse_weekdays(args.weekly)
        selectors.append(
            (
                "weekly",
                {
                    "schedule_kind": "recurring",
                    "frequency": {"kind": "weekly", "weekdays": days, "time": time},
                },
            )
        )
    if getattr(args, "frequency_json", None):
        try:
            freq = _json.loads(args.frequency_json)
        except _json.JSONDecodeError as exc:
            raise ValueError(f"--frequency-json is not valid JSON: {exc}") from exc
        if not isinstance(freq, dict):
            raise ValueError("--frequency-json must be a JSON object")
        selectors.append(
            ("frequency-json", {"schedule_kind": "recurring", "frequency": freq})
        )

    if len(selectors) > 1:
        names = ", ".join(f"--{n}" for n, _ in selectors)
        raise ValueError(f"pass only one schedule ({names} are mutually exclusive)")

    fields: dict[str, Any] = dict(selectors[0][1]) if selectors else {}
    # timezone applies to recurring schedules; it is itself a schedule-defining
    # field server-side, so sending it alone on update re-times the next run.
    if getattr(args, "timezone", None):
        fields["timezone"] = args.timezone
    return fields


def _session_config(args, *, required: bool) -> Optional[dict]:
    """Build ``session_config`` from ``--session-config-json`` or the convenience
    flags (``--agent`` etc.). Returns ``None`` when nothing was supplied.

    ``--effort`` maps to the per-agent key the scheduler reads (claude →
    ``thinking_effort``, codex → ``reasoning_effort``); for other agents pass a
    full ``--session-config-json`` instead.
    """
    raw = getattr(args, "session_config_json", None)
    if raw:
        try:
            config = _json.loads(raw)
        except _json.JSONDecodeError as exc:
            raise ValueError(f"--session-config-json is not valid JSON: {exc}") from exc
        if not isinstance(config, dict):
            raise ValueError("--session-config-json must be a JSON object")
        return config

    agent = getattr(args, "agent", None)
    model = getattr(args, "model", None)
    effort = getattr(args, "effort", None)
    permission_mode = getattr(args, "permission_mode", None)
    if not any((agent, model, effort, permission_mode)):
        if required:
            raise ValueError(
                "a session config is required — pass --agent (e.g. --agent claude) "
                "or --session-config-json"
            )
        return None
    if not agent:
        raise ValueError(
            "--agent is required when building a session config from flags"
        )

    config: dict[str, Any] = {"agent": agent}
    if model:
        config["model"] = model
    if permission_mode:
        config["permission_mode"] = permission_mode
    if effort:
        if agent == "claude":
            config["thinking_effort"] = effort
        elif agent == "codex":
            config["reasoning_effort"] = effort
        else:
            raise ValueError(
                f"--effort has no meaning for agent {agent!r}; "
                "use --session-config-json for its config instead"
            )
    return config


def _worktree(args) -> Optional[dict]:
    raw = getattr(args, "worktree_json", None)
    if not raw:
        return None
    try:
        wt = _json.loads(raw)
    except _json.JSONDecodeError as exc:
        raise ValueError(f"--worktree-json is not valid JSON: {exc}") from exc
    if not isinstance(wt, dict):
        raise ValueError("--worktree-json must be a JSON object")
    return wt


def _resolve_machine_id(args) -> Optional[str]:
    """Explicit ``--machine-id`` wins; otherwise default to the machine the local
    daemon registered for this server (so ``vicoa automation create`` on a
    developer's box just targets that box)."""
    if getattr(args, "machine_id", None):
        return args.machine_id
    from vicoa.machine_state import read_machine_id

    base_url = getattr(args, "base_url", None)
    return read_machine_id(base_url)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_TITLE_W = 34


def _fit(s: str, width: int) -> str:
    s = s or ""
    return s if len(s) <= width else s[: width - 1] + "…"


def _short(value: Optional[str], n: int = 8) -> str:
    return value[:n] if value else "—"


def _short_dt(value: Optional[str]) -> str:
    """Trim an ISO timestamp to ``YYYY-MM-DD HH:MM`` for table display."""
    if not value:
        return "—"
    return value[:16].replace("T", " ")


def _schedule_summary(a: dict) -> str:
    """One-line human schedule, e.g. ``daily 09:00`` or ``once``."""
    kind = a.get("schedule_kind")
    if kind == "once":
        return "once"
    freq = a.get("frequency")
    if not isinstance(freq, dict):
        return "recurring"
    fkind = freq.get("kind")
    if fkind == "hourly":
        return f"hourly :{int(freq.get('minute', 0)):02d}"
    if fkind == "daily":
        return f"daily {freq.get('time', _DEFAULT_TIME)}"
    if fkind == "weekdays":
        return f"weekdays {freq.get('time', _DEFAULT_TIME)}"
    if fkind == "weekly":
        days = ",".join(str(d) for d in (freq.get("weekdays") or []))
        return f"weekly [{days}] {freq.get('time', _DEFAULT_TIME)}"
    if fkind == "custom":
        return f"custom {freq.get('unit', '')}".strip()
    return "recurring"


def _print_automation_table(rows: list[dict]) -> None:
    if not rows:
        print("No automations found.")
        return
    header = (
        f"{'ID':<8}  {'TITLE':<{_TITLE_W}} {'ON':<3} {'SCHEDULE':<18} {'NEXT RUN':<16}"
    )
    print(header)
    print("-" * len(header))
    for a in rows:
        print(
            f"{_short(a.get('id')):<8}  "
            f"{_fit(a.get('title', ''), _TITLE_W):<{_TITLE_W}} "
            f"{('yes' if a.get('enabled') else 'no'):<3} "
            f"{_fit(_schedule_summary(a), 18):<18} "
            f"{_short_dt(a.get('next_run_at')):<16}"
        )
    print(f"\n{len(rows)} automation(s).")


def _print_automation_detail(a: dict) -> None:
    lines = [
        f"id:              {a.get('id')}",
        f"title:           {a.get('title')}",
        f"enabled:         {a.get('enabled')}",
        f"machine_id:      {a.get('machine_id')}",
        f"directory:       {a.get('directory')}",
        f"worktree:        {_json.dumps(a.get('worktree')) if a.get('worktree') else '—'}",
        f"schedule_kind:   {a.get('schedule_kind')}",
        f"schedule:        {_schedule_summary(a)}",
        f"frequency:       {_json.dumps(a.get('frequency')) if a.get('frequency') else '—'}",
        f"timezone:        {a.get('timezone')}",
        f"next_run_at:     {a.get('next_run_at') or '—'}",
        f"last_run_at:     {a.get('last_run_at') or '—'}",
        f"last_run_status: {a.get('last_run_status') or '—'}",
        f"session_config:  {_json.dumps(a.get('session_config'))}",
        f"created_at:      {a.get('created_at')}",
        f"updated_at:      {a.get('updated_at')}",
    ]
    print("\n".join(lines))
    prompt = a.get("prompt")
    if prompt:
        print(f"\nprompt:\n{prompt}")


def _print_runs_table(runs: list[dict]) -> None:
    if not runs:
        print("No runs yet.")
        return
    header = f"{'ID':<8}  {'STATUS':<14} {'FIRED AT':<16} {'INSTANCE':<8} DETAIL"
    print(header)
    print("-" * len(header))
    for r in runs:
        print(
            f"{_short(r.get('id')):<8}  "
            f"{str(r.get('status', '')):<14} "
            f"{_short_dt(r.get('fired_at')):<16} "
            f"{_short(r.get('agent_instance_id')):<8} "
            f"{_fit(r.get('detail') or '—', 40)}"
        )
    print(f"\n{len(runs)} run(s).")


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _cmd_ls(args, api_key: str) -> int:
    rows = request(args, api_key, "GET", "/api/v1/automations")
    if getattr(args, "json", False):
        print(_json.dumps(rows, indent=2))
    else:
        _print_automation_table(rows)
    return 0


def _cmd_get(args, api_key: str) -> int:
    a = request(args, api_key, "GET", f"/api/v1/automations/{args.automation_id}")
    if getattr(args, "json", False):
        print(_json.dumps(a, indent=2))
    else:
        _print_automation_detail(a)
    return 0


def _cmd_create(args, api_key: str) -> int:
    try:
        schedule = _schedule_fields(args)
        if not schedule:
            print(
                "A schedule is required — pass one of --at, --daily, --hourly, "
                "--weekdays, --weekly, or --frequency-json.",
                file=sys.stderr,
            )
            return 2
        session_config = _session_config(args, required=True)
        worktree = _worktree(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    machine_id = _resolve_machine_id(args)
    if not machine_id:
        print(
            "No machine to run on. Pass --machine-id, or run the Vicoa daemon on "
            "the target machine first so it registers.",
            file=sys.stderr,
        )
        return 2

    body: dict[str, Any] = {
        "title": args.title,
        "prompt": args.prompt,
        "machine_id": machine_id,
        "directory": args.directory or os.getcwd(),
        "session_config": session_config,
        "enabled": not getattr(args, "disabled", False),
    }
    if worktree is not None:
        body["worktree"] = worktree
    body.update(schedule)

    a = request(args, api_key, "POST", "/api/v1/automations", json=body)
    if getattr(args, "json", False):
        print(_json.dumps(a, indent=2))
    else:
        print(f"Created automation {a.get('id')}: {a.get('title')}")
        print(
            f"  schedule: {_schedule_summary(a)}  next run: {a.get('next_run_at') or '—'}"
        )
    return 0


def _cmd_update(args, api_key: str) -> int:
    try:
        body: dict[str, Any] = dict(_schedule_fields(args))
        session_config = _session_config(args, required=False)
        worktree = _worktree(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    for flag, field in (
        ("title", "title"),
        ("prompt", "prompt"),
        ("directory", "directory"),
        ("machine_id", "machine_id"),
    ):
        value = getattr(args, flag, None)
        if value is not None:
            body[field] = value
    if session_config is not None:
        body["session_config"] = session_config
    if worktree is not None:
        body["worktree"] = worktree
    # --enable / --disable resolve to the same tri-state on `enabled`.
    if getattr(args, "enabled", None) is not None:
        body["enabled"] = args.enabled

    if not body:
        print(
            "Nothing to update — pass at least one field (e.g. --disable, "
            "--prompt ..., --daily).",
            file=sys.stderr,
        )
        return 2

    a = request(
        args, api_key, "PATCH", f"/api/v1/automations/{args.automation_id}", json=body
    )
    if getattr(args, "json", False):
        print(_json.dumps(a, indent=2))
    else:
        print(f"Updated automation {a.get('id')}: {a.get('title')}")
    return 0


def _cmd_delete(args, api_key: str) -> int:
    if not getattr(args, "yes", False):
        try:
            answer = (
                input(f"Delete automation {args.automation_id}? [y/N] ").strip().lower()
            )
        except (EOFError, KeyboardInterrupt):
            # Non-interactive (e.g. an agent) without --yes: refuse rather than
            # delete on an unanswerable prompt.
            print("\nAborted (pass --yes to delete non-interactively).")
            return 1
        if answer not in {"y", "yes"}:
            print("Aborted.")
            return 0
    request(args, api_key, "DELETE", f"/api/v1/automations/{args.automation_id}")
    print(f"Deleted automation {args.automation_id}.")
    return 0


def _cmd_runs(args, api_key: str) -> int:
    runs = request(
        args, api_key, "GET", f"/api/v1/automations/{args.automation_id}/runs"
    )
    if getattr(args, "json", False):
        print(_json.dumps(runs, indent=2))
    else:
        _print_runs_table(runs)
    return 0


_HANDLERS = {
    "ls": _cmd_ls,
    "get": _cmd_get,
    "create": _cmd_create,
    "update": _cmd_update,
    "delete": _cmd_delete,
    "runs": _cmd_runs,
}


def run_automation_command(args) -> int:
    """Entry point wired into ``cli.py``'s dispatch for ``vicoa automation``."""
    sub = getattr(args, "automation_command", None)
    handler = _HANDLERS.get(sub) if sub else None
    if handler is None:
        print(
            "usage: vicoa automation {ls,get,create,update,delete,runs} ...\n"
            "Run `vicoa automation --help` for details.",
            file=sys.stderr,
        )
        return 2
    api_key = resolve_api_key(args)
    return handler(args, api_key)


# ---------------------------------------------------------------------------
# Argparse wiring
# ---------------------------------------------------------------------------


def add_automation_subparser(subparsers) -> None:
    """Register the ``automation`` subcommand tree on ``cli.py``'s subparsers.

    Kept here (not inline in ``cli.py``) so the automation surface — parser,
    handlers, and body builders — lives in one file and doesn't bloat ``cli.py``.
    Call once from ``main()``; ``run_automation_command`` handles dispatch.
    """
    # CRUD only; the server's scheduler does the firing. Primary consumer is a
    # running agent, so every leaf accepts --json.
    automation_parser = subparsers.add_parser(
        "automation",
        help="List, read, create, edit, or delete scheduled automations",
    )
    automation_sub = automation_parser.add_subparsers(dest="automation_command")

    # Auth/output flags shared by every automation subcommand.
    automation_common = argparse.ArgumentParser(add_help=False)
    automation_common.add_argument(
        "--api-key",
        help="API key (defaults to VICOA_API_KEY or the stored credential)",
    )
    automation_common.add_argument(
        "--base-url",
        default=DEFAULT_API_URL,
        help="Base URL of the Vicoa API server",
    )
    automation_common.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of a table",
    )

    # Schedule selectors — pass exactly one on create (mutually exclusive). On
    # update, passing one re-times the automation; passing none leaves it alone.
    automation_schedule = argparse.ArgumentParser(add_help=False)
    automation_schedule.add_argument(
        "--at",
        metavar="ISO8601",
        help="Run once at this UTC instant, e.g. 2026-08-10T09:00:00Z",
    )
    automation_schedule.add_argument(
        "--daily", action="store_true", help="Run every day at --time"
    )
    automation_schedule.add_argument(
        "--hourly", action="store_true", help="Run every hour at --minute"
    )
    automation_schedule.add_argument(
        "--weekdays", action="store_true", help="Run Mon–Fri at --time"
    )
    automation_schedule.add_argument(
        "--weekly",
        metavar="DAYS",
        help="Run weekly on these weekdays (0=Sun..6=Sat), e.g. --weekly 1,3,5",
    )
    automation_schedule.add_argument(
        "--frequency-json",
        metavar="JSON",
        help="Recurring frequency as a raw JSON object (custom/interval schedules)",
    )
    automation_schedule.add_argument(
        "--time",
        metavar="HH:MM",
        help="Time of day for --daily/--weekdays/--weekly (default 09:00)",
    )
    automation_schedule.add_argument(
        "--minute",
        type=int,
        metavar="M",
        help="Minute past the hour for --hourly (default 0)",
    )
    automation_schedule.add_argument(
        "--timezone",
        metavar="TZ",
        help="IANA timezone for recurring schedules (default UTC)",
    )

    # Where/how the session runs — shared by create and update.
    automation_target = argparse.ArgumentParser(add_help=False)
    automation_target.add_argument(
        "--machine-id",
        metavar="MACHINE_ID",
        help="Machine to run on (defaults to this machine's registered daemon)",
    )
    automation_target.add_argument(
        "--directory", metavar="PATH", help="Working directory on the machine"
    )
    automation_target.add_argument(
        "--worktree-json",
        metavar="JSON",
        help='Worktree spec, e.g. \'{"mode":"new"}\' or \'{"mode":"existing","path":"..."}\'',
    )

    automation_sub.add_parser(
        "ls", parents=[automation_common], help="List automations"
    )

    automation_get = automation_sub.add_parser(
        "get", parents=[automation_common], help="Show one automation's full details"
    )
    automation_get.add_argument("automation_id", help="Automation id (full UUID)")

    automation_create = automation_sub.add_parser(
        "create",
        parents=[automation_common, automation_schedule, automation_target],
        help="Create an automation",
    )
    # cli.py's run path defines a top-level `--agent` whose default ("claude")
    # argparse leaks into every subcommand's namespace. Reset it so the session
    # config is built only from what the user actually passes (see _session_config).
    automation_create.set_defaults(agent=None)
    automation_create.add_argument("title", help="Automation title")
    automation_create.add_argument(
        "--prompt", required=True, help="Prompt the scheduled session starts with"
    )
    automation_create.add_argument(
        "--agent", help="Agent to run, e.g. claude / codex / opencode"
    )
    automation_create.add_argument("--model", help="Model slug for the agent")
    automation_create.add_argument(
        "--effort", help="Reasoning/thinking effort (claude & codex only)"
    )
    automation_create.add_argument(
        "--permission-mode", help="Agent permission mode (e.g. plan, acceptEdits)"
    )
    automation_create.add_argument(
        "--session-config-json",
        metavar="JSON",
        help="Full session config as JSON (overrides --agent/--model/…); must include 'agent'",
    )
    automation_create.add_argument(
        "--disabled",
        action="store_true",
        help="Create paused (enabled=false); default is enabled",
    )

    automation_update = automation_sub.add_parser(
        "update",
        parents=[automation_common, automation_schedule, automation_target],
        help="Edit an automation (only the flags you pass change)",
    )
    # update has no --agent flag, so the leaked top-level default is especially
    # wrong here — it would wrongly rebuild session_config on a bare update.
    automation_update.set_defaults(agent=None)
    automation_update.add_argument("automation_id", help="Automation id (full UUID)")
    automation_update.add_argument("--title", help="New title")
    automation_update.add_argument("--prompt", help="New prompt")
    automation_update.add_argument(
        "--session-config-json",
        metavar="JSON",
        help="Replace the session config wholesale (JSON object including 'agent')",
    )
    automation_enable = automation_update.add_mutually_exclusive_group()
    automation_enable.add_argument(
        "--enable",
        dest="enabled",
        action="store_true",
        default=None,
        help="Enable (resume) the automation",
    )
    automation_enable.add_argument(
        "--disable",
        dest="enabled",
        action="store_false",
        default=None,
        help="Disable (pause) the automation",
    )

    automation_delete = automation_sub.add_parser(
        "delete", parents=[automation_common], help="Delete an automation"
    )
    automation_delete.add_argument("automation_id", help="Automation id (full UUID)")
    automation_delete.add_argument(
        "-y", "--yes", action="store_true", help="Skip the confirmation prompt"
    )

    automation_runs = automation_sub.add_parser(
        "runs", parents=[automation_common], help="Show an automation's run history"
    )
    automation_runs.add_argument("automation_id", help="Automation id (full UUID)")
