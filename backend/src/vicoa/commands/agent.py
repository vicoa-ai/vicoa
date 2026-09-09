"""``vicoa agent`` — list, create, and remove named agent profiles.

An "Agent" here is the user-facing preset: a saved provider + model + config +
instructions with a name, the same thing the web app's Agents page edits
(collaboration P1, `plans/todos/agent-profiles-p1.md`). Its main use from a
terminal is ``vicoa session start --agent-profile <name>``.

Talks to the agent-facing server (``agents.vicoa.ai``) with the same Bearer API
key every other ``vicoa`` command uses, hitting ``/api/v1/agents`` from
``servers/api/agent_profiles.py``. Auth/request/formatting helpers are reused
from :mod:`vicoa.commands.task` rather than duplicated — same server, same key,
same failure modes.
"""

from __future__ import annotations

import json as _json
import sys
from typing import Any, Optional

from vicoa.commands.task import _fit, _request, _resolve_api_key

_NAME_W = 24
_AGENT_W = 12


def resolve_profile_by_name(args, api_key: str, name: str) -> dict:
    """Find a non-archived profile by name, case-insensitively, or exit 2.

    Name (not id) is how a person addresses a profile in a terminal, and the
    server's uniqueness index is itself case-insensitive over non-archived rows,
    so this can only ever match one.
    """
    profiles = _request(args, api_key, "GET", "/api/v1/agents") or []
    wanted = name.strip().lower()
    for profile in profiles:
        if str(profile.get("name", "")).strip().lower() == wanted:
            return profile
    known = ", ".join(sorted(str(p.get("name")) for p in profiles)) or "(none yet)"
    print(
        f"No agent named '{name}'. Your agents: {known}.\n"
        "Create one with `vicoa agent add <name> --agent <id>`.",
        file=sys.stderr,
    )
    sys.exit(2)


def _print_table(profiles: list[dict]) -> None:
    if not profiles:
        print("No agents yet. Create one with `vicoa agent add <name> --agent <id>`.")
        return
    header = f"{'NAME':<{_NAME_W}} {'AGENT':<{_AGENT_W}} {'MODEL':<24} INSTRUCTIONS"
    print(header)
    print("-" * len(header))
    for p in profiles:
        config = p.get("config") or {}
        # A profile's value is mostly its instructions, so show whether it has
        # any rather than a truncated blob nobody can read at this width.
        instructions = "yes" if (p.get("system_prompt") or "").strip() else "—"
        archived = " (archived)" if p.get("is_archived") else ""
        print(
            f"{_fit(str(p.get('name', '')) + archived, _NAME_W):<{_NAME_W}} "
            f"{_fit(str(p.get('agent', '')), _AGENT_W):<{_AGENT_W}} "
            f"{_fit(str(config.get('model') or '—'), 24):<24} {instructions}"
        )


def _read_prompt_arg(value: Optional[str]) -> Optional[str]:
    """``@path`` reads from a file — a system prompt is usually too long to type
    and too awkward to quote inline."""
    if value is None:
        return None
    if value.startswith("@"):
        path = value[1:]
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        except OSError as exc:
            print(f"Error: could not read {path} ({exc}).", file=sys.stderr)
            sys.exit(2)
    return value


def _cmd_ls(args, api_key: str) -> int:
    profiles = (
        _request(
            args,
            api_key,
            "GET",
            "/api/v1/agents",
            params={"include_archived": "true"}
            if getattr(args, "include_archived", False)
            else None,
        )
        or []
    )
    if getattr(args, "json", False):
        print(_json.dumps({"agents": profiles}, indent=2))
        return 0
    _print_table(profiles)
    return 0


def _cmd_add(args, api_key: str) -> int:
    config: dict[str, Any] = {}
    agent = (args.agent or "claude").strip().lower()
    if getattr(args, "model", None):
        config["model"] = args.model
    # Effort routes to a per-agent key, exactly as the session-start flags do.
    effort = getattr(args, "effort", None)
    if effort:
        config["reasoning_effort" if agent == "codex" else "thinking_effort"] = effort
    if getattr(args, "permission_mode", None):
        config["permission_mode"] = args.permission_mode
    if getattr(args, "opencode_mode", None):
        config["opencode_mode"] = args.opencode_mode

    body: dict[str, Any] = {"name": args.name, "agent": agent, "config": config}
    system_prompt = _read_prompt_arg(getattr(args, "system_prompt", None))
    if system_prompt and system_prompt.strip():
        body["system_prompt"] = system_prompt
    for key, attr in (
        ("description", "description"),
        ("emoji", "emoji"),
        ("color", "color"),
        ("default_machine_id", "machine"),
        ("default_project_id", "project"),
    ):
        value = getattr(args, attr, None)
        if value:
            body[key] = value

    created = _request(args, api_key, "POST", "/api/v1/agents", json=body)
    if getattr(args, "json", False):
        print(_json.dumps(created, indent=2))
        return 0
    print(f"Created agent '{created['name']}' ({created['agent']}).")
    return 0


def _cmd_rm(args, api_key: str) -> int:
    profile = resolve_profile_by_name(args, api_key, args.name)
    _request(args, api_key, "DELETE", f"/api/v1/agents/{profile['id']}")
    if getattr(args, "json", False):
        print(_json.dumps({"deleted": profile["id"]}, indent=2))
        return 0
    # Automations referencing it keep running off their fallback snapshot; the
    # count lives on the dashboard's delete response, which this route omits.
    print(f"Deleted agent '{profile['name']}'.")
    return 0


_HANDLERS = {"ls": _cmd_ls, "add": _cmd_add, "rm": _cmd_rm}


def run_agent_command(args) -> int:
    """Entry point wired into ``cli.py``'s dispatch for ``vicoa agent``."""
    sub = getattr(args, "agent_command", None)
    handler = _HANDLERS.get(sub) if sub else None
    if handler is None:
        print(
            "usage: vicoa agent {ls,add,rm} ...\nRun `vicoa agent --help` for details.",
            file=sys.stderr,
        )
        return 2
    api_key = _resolve_api_key(args)
    return handler(args, api_key)
