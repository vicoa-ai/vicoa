"""`vicoa session ls --local`, `vicoa session import`, and the `--resume` bridge.

Sessions an agent ran outside Vicoa (a terminal, a desktop app, an editor)
live only on this machine. These commands list them and import them, using
the same ``vicoa.local_sessions`` code the daemon serves to the app, so both
behave the same. ``vicoa --resume`` keeps taking Vicoa ids; given a native id
it resolves one that is already linked, and offers to import one that isn't.
"""

from __future__ import annotations

import json as _json
import os
import sys
from typing import Any, Optional

from vicoa.sdk.client import VicoaClient
from vicoa.sdk.exceptions import APIError, VicoaError

#: Shown when a command needs this machine's id and the daemon never ran.
_NO_MACHINE = "This computer isn't connected to Vicoa yet. Run `vicoa daemon` once, then try again."


def _client(args: Any, api_key: str) -> VicoaClient:
    from vicoa.constants import DEFAULT_API_URL

    return VicoaClient(
        api_key=api_key, base_url=getattr(args, "base_url", None) or DEFAULT_API_URL
    )


def _machine_id(args: Any) -> Optional[str]:
    from vicoa.commands.instance import _local_machine_id

    return _local_machine_id(args)


def _print_local_table(sessions: list[dict[str, Any]]) -> None:
    from vicoa.commands.instance import _basename, _fit, _local_time, _or_dash

    if not sessions:
        print("No sessions found on this computer.")
        return
    header = (
        f"{'AGENT':<7} {'SOURCE':<15} {'FOLDER':<20} {'UPDATED':<16} "
        f"{'IN VICOA':<9} {'ID':<36}  TITLE"
    )
    print(header)
    for item in sessions:
        in_vicoa = "yes" if item.get("vicoa_instance_id") else "-"
        print(
            f"{_fit(item.get('agent') or '', 7):<7} "
            f"{_fit(_or_dash(item.get('source_label') or item.get('source')), 15):<15} "
            f"{_fit(_basename(item.get('cwd')), 20):<20} "
            f"{_fit(_local_time(item.get('updated_at')), 16):<16} "
            f"{in_vicoa:<9} {item.get('native_id', ''):<36}  "
            f"{_fit(item.get('title') or '', 60)}"
        )


def cmd_ls_local(args: Any, api_key: str) -> int:
    """List the native sessions on this computer, newest first."""
    from vicoa import local_sessions

    result = local_sessions.list_local_sessions(
        agent=getattr(args, "local_agent", None),
        directory=os.path.abspath(args.dir) if getattr(args, "dir", None) else None,
        limit=getattr(args, "limit", local_sessions.DEFAULT_LIMIT),
        offset=getattr(args, "offset", 0) or 0,
        include_scripted=bool(getattr(args, "scripted", False)),
    )
    machine_id = _machine_id(args)
    if machine_id and result["sessions"]:
        client = _client(args, api_key)
        try:
            local_sessions.mark_linked(client, machine_id, result["sessions"])
        finally:
            client.close()
    if getattr(args, "json", False):
        print(_json.dumps(result, indent=2))
    else:
        _print_local_table(result["sessions"])
        if result.get("has_more"):
            print("More with --offset.")
    for agent, message in (result.get("errors") or {}).items():
        print(f"{local_sessions.agent_label(agent)}: {message}", file=sys.stderr)
    return 0


def cmd_import(args: Any, api_key: str) -> int:
    """Import native sessions by id. Already-imported ones report their session."""
    from vicoa import local_sessions

    machine_id = _machine_id(args)
    if not machine_id:
        print(f"Error: {_NO_MACHINE}", file=sys.stderr)
        return 1
    client = _client(args, api_key)
    failures = 0
    results: list[dict[str, Any]] = []
    try:
        for native_id in args.native_ids:
            try:
                # Without --agent, the agent is found from the id.
                result = local_sessions.import_local_session(
                    client,
                    machine_id=machine_id,
                    native_id=native_id,
                    agent=getattr(args, "import_agent", None),
                )
            except local_sessions.LocalSessionError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                failures += 1
                continue
            except APIError as exc:
                print(
                    f"Error: couldn't import {native_id}: {exc.detail}", file=sys.stderr
                )
                failures += 1
                continue
            except VicoaError as exc:
                print(f"Error: couldn't import {native_id}: {exc}", file=sys.stderr)
                failures += 1
                continue
            results.append({"native_id": native_id, **result})
            if not getattr(args, "json", False):
                verb = "Imported" if result["created"] else "Already in Vicoa:"
                print(f'{verb} "{result["title"]}" as {result["agent_instance_id"]}')
    finally:
        client.close()
    if getattr(args, "json", False):
        print(_json.dumps(results, indent=2))
    return 1 if failures else 0


def resolve_resume_target(
    args: Any, api_key: str, native_id: str, agent_hint: Optional[str]
) -> Optional[tuple[str, str]]:
    """For `vicoa --resume <id>` when the id isn't a Vicoa session.

    Returns ``(agent, vicoa instance id)`` to resume, or ``None`` after telling
    the user why not. A native session already imported resolves to its Vicoa
    session; one that isn't is imported after a yes at the prompt (or, without
    a terminal to ask in, the import command is printed instead).
    """
    from vicoa import local_sessions

    agents: list[str] = (
        [agent_hint]
        if agent_hint and agent_hint in local_sessions.SUPPORTED_AGENTS
        else list(local_sessions.SUPPORTED_AGENTS)
    )
    machine_id = _machine_id(args)
    client = _client(args, api_key)
    try:
        if machine_id:
            for agent in agents:
                try:
                    matches = client.lookup_native_sessions(
                        machine_id=machine_id,
                        agent=agent,
                        native_session_ids=[native_id],
                    )
                except VicoaError:
                    matches = {}
                if native_id in matches:
                    return agent, matches[native_id]

        try:
            found = local_sessions.find_agent(native_id, agents)
        except local_sessions.LocalSessionNotFound as exc:
            print(f"Error: {exc}, and not in Vicoa either.", file=sys.stderr)
            return None
        if not machine_id:
            print(f"Error: {_NO_MACHINE}", file=sys.stderr)
            return None
        label = local_sessions.agent_label(found)
        if not sys.stdin.isatty():
            print(
                f"{label} session {native_id} isn't in Vicoa yet. Import it first:\n"
                f"  vicoa session import {native_id}",
                file=sys.stderr,
            )
            return None
        answer = input(
            f"{label} session {native_id} isn't in Vicoa yet. Import it and continue? [Y/n] "
        )
        if answer.strip().lower() not in ("", "y", "yes"):
            return None
        try:
            result = local_sessions.import_local_session(
                client, machine_id=machine_id, agent=found, native_id=native_id
            )
        except (local_sessions.LocalSessionError, VicoaError) as exc:
            detail = exc.detail if isinstance(exc, APIError) else str(exc)
            print(f"Error: couldn't import the session: {detail}", file=sys.stderr)
            return None
        print(f'Imported "{result["title"]}" as {result["agent_instance_id"]}')
        return found, str(result["agent_instance_id"])
    finally:
        client.close()
