"""``vicoa stop`` — stop daemon, sessions, or a specific session by ID."""

from __future__ import annotations

import sys
from typing import Optional


def _confirm(
    question: str, *, default_yes: bool = False, assume_yes: bool = False
) -> bool:
    """Plain ``[y/N]`` prompt — works in pipes and non-TTY contexts."""
    if assume_yes:
        return True
    suffix = "[Y/n]" if default_yes else "[y/N]"
    try:
        answer = input(f"{question} {suffix} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not answer:
        return default_yes
    return answer in {"y", "yes"}


def _stop_daemon(*, base_url: Optional[str], assume_yes: bool) -> bool:
    """Confirm + stop daemon(s). Returns True if everything stopped cleanly.

    When ``base_url`` is provided, stops only that daemon. When it's ``None``,
    stops every running daemon — the decision the user made when multi-URL
    support landed: a bare ``vicoa stop daemon`` should stop them all rather
    than silently leaving a sibling daemon running.
    """
    from vicoa.machine_daemon import (
        find_running_daemon_pid,
        list_running_daemons,
        stop_background_daemon,
    )

    if base_url:
        pid = find_running_daemon_pid(base_url)
        if pid is None:
            print(f"No active Vicoa daemon for {base_url}.")
            return True
        if not _confirm(
            f"Stop the Vicoa daemon for {base_url} (pid {pid})?",
            assume_yes=assume_yes,
        ):
            print("Aborted.")
            return False
        stopped, message = stop_background_daemon(base_url=base_url)
        print(message)
        return stopped

    daemons = list_running_daemons()
    if not daemons:
        print("No active Vicoa daemon.")
        return True

    if len(daemons) == 1:
        url, pid = daemons[0]
        prompt = f"Stop the Vicoa daemon for {url} (pid {pid})?"
    else:
        prompt_lines = [f"Stop {len(daemons)} Vicoa daemon(s)?"]
        for url, pid in daemons:
            prompt_lines.append(f"  - {url} (pid {pid})")
        prompt = "\n".join(prompt_lines)
    if not _confirm(prompt, assume_yes=assume_yes):
        print("Aborted.")
        return False

    all_stopped = True
    for url, pid in daemons:
        stopped, message = stop_background_daemon(base_url=url)
        marker = "✓" if stopped else "✗"
        print(f"  {marker} {url} (pid {pid}) — {message}")
        if not stopped:
            all_stopped = False
    return all_stopped


def _stop_sessions(*, agent_filter: Optional[str], assume_yes: bool) -> bool:
    """Confirm + terminate all daemon-spawned headless sessions.

    Optionally filtered by agent type. Returns True if all matched sessions stopped.
    """
    from vicoa.agent_processes import list_running_agents, stop_pid
    from vicoa.commands.ls import _short_id

    sessions = [a for a in list_running_agents() if a.kind == "headless"]
    if agent_filter:
        sessions = [a for a in sessions if a.agent == agent_filter]

    if not sessions:
        filter_note = f" (agent={agent_filter})" if agent_filter else ""
        print(f"No daemon-spawned headless sessions running{filter_note}.")
        return True

    label = f"{len(sessions)} headless session(s)"
    if agent_filter:
        label = f"{len(sessions)} {agent_filter} headless session(s)"
    if not _confirm(f"Stop {label}?", assume_yes=assume_yes):
        print("Aborted.")
        return False

    all_stopped = True
    for s in sessions:
        # 10s grace: a headless session's SIGTERM handler runs end_session() +
        # Claude-client disconnect + SSE task teardown before exiting.
        ok, msg = stop_pid(s.pid, timeout=10.0)
        marker = "✓" if ok else "✗"
        print(
            f"  {marker} pid={s.pid} agent={s.agent} session={_short_id(s.session_id, s.pid)} — {msg}"
        )
        if not ok:
            all_stopped = False
    return all_stopped


def _stop_session_by_id(session_id_prefix: str, *, assume_yes: bool) -> None:
    """Stop one or more sessions identified by a full or 8-char-prefix UUID."""
    from vicoa.agent_processes import list_running_agents, stop_pid
    from vicoa.commands.ls import _short_id

    agents = list_running_agents()
    matches = [
        a for a in agents if a.session_id and a.session_id.startswith(session_id_prefix)
    ]

    if not matches:
        print(f"No running session matches '{session_id_prefix}'.")
        sys.exit(1)

    label = (
        f"session {_short_id(matches[0].session_id, matches[0].pid)}"
        if len(matches) == 1
        else f"{len(matches)} sessions matching '{session_id_prefix}'"
    )
    if not _confirm(f"Stop {label}?", assume_yes=assume_yes):
        print("Aborted.")
        return

    all_stopped = True
    for s in matches:
        ok, msg = stop_pid(s.pid, timeout=10.0)
        marker = "✓" if ok else "✗"
        print(
            f"  {marker} {_short_id(s.session_id, s.pid)} ({s.agent}, pid={s.pid}) — {msg}"
        )
        if not ok:
            all_stopped = False
    if not all_stopped:
        sys.exit(1)


def cmd_stop(args) -> None:
    """``vicoa stop [target] [--agent X] [--yes]`` — stop daemon, sessions, or both.

    Targets:
      * ``daemon`` (default) — stop only the daemon.
      * ``sessions`` — stop all daemon-spawned headless sessions, optionally
        filtered by ``--agent``. Leaves the daemon running.
      * ``all`` — stop sessions first, then the daemon.
      * ``<session-id>`` — stop a single session by its full UUID or 8-char
        prefix (as shown in ``vicoa ls``).
    """
    target = getattr(args, "target", None) or "daemon"
    agent_filter = getattr(args, "agent", None)
    assume_yes = bool(getattr(args, "yes", False))
    # ``--base-url`` is always present on ``args`` because the global parser
    # defaults it to ``DEFAULT_API_URL``. To distinguish "user passed it" from
    # "default kicked in" we scan ``sys.argv`` — a bare ``vicoa stop daemon``
    # then falls into the "stop every running daemon" branch instead of
    # quietly targeting only the default URL.
    base_url_was_explicit = any(
        a == "--base-url" or a.startswith("--base-url=") for a in sys.argv[1:]
    )
    base_url = getattr(args, "base_url", None) if base_url_was_explicit else None

    if target == "daemon":
        if agent_filter:
            print("--agent only applies to `vicoa stop sessions` / `vicoa stop all`.")
            sys.exit(2)
        if not _stop_daemon(base_url=base_url, assume_yes=assume_yes):
            sys.exit(1)
        return

    if target == "sessions":
        if not _stop_sessions(agent_filter=agent_filter, assume_yes=assume_yes):
            sys.exit(1)
        return

    if target == "all":
        sessions_ok = _stop_sessions(agent_filter=agent_filter, assume_yes=assume_yes)
        daemon_ok = _stop_daemon(base_url=base_url, assume_yes=assume_yes)
        if not (sessions_ok and daemon_ok):
            sys.exit(1)
        return

    # Treat any other value as a session ID prefix.
    if agent_filter:
        print("--agent only applies to `vicoa stop sessions` / `vicoa stop all`.")
        sys.exit(2)
    _stop_session_by_id(target, assume_yes=assume_yes)
