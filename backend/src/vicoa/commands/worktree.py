"""``vicoa worktree`` — run a worktree's committed lifecycle commands by hand.

    vicoa worktree setup [PATH] [--trust] [--dry-run] [--force]

The daemon runs a repo's ``worktree.setup`` (``.vicoa/config.json`` / root
``vicoa.json``) when it creates a worktree for a new session. This is the
terminal-side entry point for everything else: re-running after a failure,
trying a config you are editing, or an agent bringing up a bare worktree the
setup was skipped in (an untrusted repo spawned from the phone). Machine-local
— it needs no login and no running daemon — and it writes the same run record
the daemon does, so the dashboard's setup badge reflects a CLI run too.

Trust: typing this command is consent for this run, exactly like typing the
commands yourself, so there is no gate here; every command is echoed before it
runs. ``--trust`` additionally records the repo as trusted so the daemon
auto-runs its setup for new worktrees from now on.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from typing import Any


def _resolve_checkout(path: str) -> tuple[str, str] | None:
    """``(worktree_root, source_repo)`` for the git checkout containing ``path``.

    A linked worktree's source repo is the main checkout — the parent of the
    shared common dir — which is where the daemon reads the committed config
    from too. A main checkout (git-dir == common-dir; also every submodule) is
    its own source. ``None`` when ``path`` is not inside a git checkout.
    """
    target = os.path.abspath(os.path.expanduser(path))
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                target,
                "rev-parse",
                "--git-dir",
                "--git-common-dir",
                "--show-toplevel",
            ],
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    lines = proc.stdout.decode("utf-8", errors="replace").splitlines()
    if len(lines) < 3:
        return None
    git_dir, common_dir, toplevel = (line.strip() for line in lines[:3])

    def _resolve(raw: str) -> str:
        return os.path.normpath(os.path.join(target, raw))

    worktree_root = _resolve(toplevel)
    if _resolve(git_dir) == _resolve(common_dir):
        return worktree_root, worktree_root
    return worktree_root, os.path.dirname(_resolve(common_dir))


def _run_in_flight(status: dict[str, Any]) -> bool:
    """A recorded run counts as in flight only while it could still be alive.

    A daemon that died mid-run leaves ``running`` behind forever; past the
    engine's whole-hook budget nothing can still be executing it.
    """
    from vicoa.rpc.worktree_setup import DEFAULT_TOTAL_TIMEOUT_S

    if status.get("status") != "running":
        return False
    started = status.get("started_at")
    if not isinstance(started, (int, float)):
        return True
    return (time.time() - started) < DEFAULT_TOTAL_TIMEOUT_S


def _cmd_setup(args) -> int:
    from vicoa.rpc.worktree_setup import (
        HookResult,
        SetupEvent,
        SetupRunRecorder,
        current_branch,
        read_committed_config_commands,
        read_setup_status,
        run_commands,
    )
    from vicoa.rpc.worktree_trust import grant_repo_trust, is_repo_trusted

    resolved = _resolve_checkout(args.path or ".")
    if resolved is None:
        print(
            f"error: {args.path or '.'} is not inside a git checkout", file=sys.stderr
        )
        return 2
    worktree_root, source_repo = resolved

    commands = read_committed_config_commands(source_repo, "setup")
    if not commands:
        print(
            f"Nothing to run: {source_repo} has no worktree.setup in "
            ".vicoa/config.json or vicoa.json."
        )
        return 0

    if args.dry_run:
        print(f"Would run in {worktree_root} (config from {source_repo}):")
        for i, cmd in enumerate(commands, start=1):
            print(f"  {i}. {cmd}")
        return 0

    status = read_setup_status(worktree_root)
    if _run_in_flight(status) and not args.force:
        step = next(
            (c for c in status.get("commands", []) if c.get("status") == "running"),
            None,
        )
        where = f" (step {step['index']}/{status.get('total')})" if step else ""
        print(
            f"error: a setup run is already in progress for this worktree{where}. "
            "Wait for it to finish, or pass --force to run alongside it.",
            file=sys.stderr,
        )
        return 1

    if args.trust:
        grant_repo_trust(source_repo)
        print(
            f"Trusted {source_repo}: new worktrees from it will set up automatically."
        )

    branch = current_branch(worktree_root)
    print(f"Worktree: {worktree_root}")
    if source_repo != worktree_root:
        print(f"Source:   {source_repo}")
    if branch:
        print(f"Branch:   {branch}")
    print()

    recorder = SetupRunRecorder(
        worktree_path=worktree_root, source_repo=source_repo, commands=commands
    )

    def on_event(event: SetupEvent) -> None:
        recorder(event)
        if event.type == "command_started":
            print(f"$ {event.command}", flush=True)
        elif event.type == "output" and event.chunk:
            stream = sys.stderr if event.stream == "stderr" else sys.stdout
            stream.write(event.chunk)
            stream.flush()
        elif event.type == "command_completed":
            ok = event.exit_code == 0 and not event.timed_out and not event.aborted
            if not ok:
                why = (
                    "timed out"
                    if event.timed_out
                    else "aborted"
                    if event.aborted
                    else f"exit {event.exit_code}"
                )
                print(f"→ {why}", flush=True)

    # The engine runs on a worker so Ctrl-C reaches us here and turns into a
    # cooperative abort — the children sit in their own process group and
    # would otherwise keep running after the CLI died.
    abort = threading.Event()
    outcome: list[HookResult] = []
    started = time.monotonic()

    def _work() -> None:
        outcome.append(
            run_commands(
                commands,
                hook="setup",
                worktree_path=worktree_root,
                source_repo=source_repo,
                branch_name=branch,
                on_event=on_event,
                abort=abort,
            )
        )

    worker = threading.Thread(target=_work, daemon=True)
    worker.start()
    try:
        while worker.is_alive():
            worker.join(timeout=0.2)
    except KeyboardInterrupt:
        print("\nInterrupted — stopping setup…", file=sys.stderr)
        abort.set()
        worker.join(timeout=10)

    if not outcome:
        recorder.fail("interrupted")
        return 130
    result = outcome[0]
    recorder.finish(result)
    elapsed = time.monotonic() - started

    if result.ok:
        n = len(result.results)
        print(f"\nSetup done: {n} command{'s' if n != 1 else ''} in {elapsed:.1f}s.")
        if not is_repo_trusted(source_repo):
            print(
                "Note: this repository's setup isn't trusted on this machine yet, so "
                "new worktrees won't run it automatically. Re-run with --trust to "
                "allow that."
            )
        return 0

    failed = result.failed_result
    if result.aborted:
        return 130
    if failed is None:
        return 1
    index = result.results.index(failed) + 1
    print(
        f"\nSetup failed at step {index}/{len(commands)}: {failed.command}",
        file=sys.stderr,
    )
    return failed.exit_code if failed.exit_code else 1


_HANDLERS = {"setup": _cmd_setup}


def run_worktree_command(args) -> int:
    """Entry point wired into ``cli.py``'s dispatch for ``vicoa worktree``."""
    sub = getattr(args, "worktree_command", None)
    handler = _HANDLERS.get(sub) if sub else None
    if handler is None:
        print(
            "usage: vicoa worktree setup [PATH] [--trust] [--dry-run] [--force]\n"
            "Run `vicoa worktree --help` for details.",
            file=sys.stderr,
        )
        return 2
    return handler(args)


def add_worktree_subparser(subparsers) -> None:
    """Register the ``worktree`` subcommand tree on ``cli.py``'s subparsers."""
    parser = subparsers.add_parser(
        "worktree",
        help="Run a worktree's committed setup commands (.vicoa/config.json)",
    )
    sub = parser.add_subparsers(dest="worktree_command")

    setup = sub.add_parser(
        "setup",
        help="Run the repository's worktree.setup commands in a checkout, now",
        description=(
            "Runs the source repository's worktree.setup commands (from its "
            ".vicoa/config.json or vicoa.json) inside the checkout at PATH — a "
            "linked worktree or the main checkout — echoing each command and "
            "streaming its output. Stops at the first failure. Writes the same "
            "run record the daemon does, so the dashboard shows this run too."
        ),
    )
    setup.add_argument(
        "path",
        nargs="?",
        help="A directory inside the worktree to set up (default: current directory)",
    )
    setup.add_argument(
        "--trust",
        action="store_true",
        help=(
            "Also mark the source repository as trusted on this machine, so the "
            "daemon runs its setup automatically for new worktrees"
        ),
    )
    setup.add_argument(
        "--dry-run",
        action="store_true",
        help="List the commands that would run, without running them",
    )
    setup.add_argument(
        "--force",
        action="store_true",
        help="Run even if a setup run for this worktree is already in progress",
    )
