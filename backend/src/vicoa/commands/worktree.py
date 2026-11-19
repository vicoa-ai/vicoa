"""``vicoa worktree`` — make a worktree for a session, or run a worktree's
committed lifecycle commands by hand.

    vicoa worktree new [NAME] [--path DIR] [--no-setup] [--no-session]
    vicoa worktree setup [PATH] [--trust] [--dry-run] [--force]

``new`` is how an agent on a task moves its work into a worktree: a task
session starts in the folder as it is, and the task brief tells the agent to
make one when the work changes code (``shared/task_dispatch_prompts.py``). It
makes the worktree where the daemon makes one for a new session, runs the
setup behind the daemon's trust gate, and files the running session under it
(``vicoa session update --worktree``), so one command does all three for any
agent.

``setup``: the daemon runs a repo's ``worktree.setup`` (``.vicoa/config.json``
/ root ``vicoa.json``) when it creates a worktree for a new session. This is the
terminal-side entry point for everything else: re-running after a failure,
trying a config you are editing, or an agent bringing up a bare worktree the
setup was skipped in (an untrusted repo spawned from the phone). Machine-local
— it needs no login and no running daemon — and it writes the same run record
the daemon does, so the dashboard's setup badge reflects a CLI run too.

Trust: typing ``setup`` is consent for this run, exactly like typing the
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
from typing import TYPE_CHECKING, Any

from vicoa.constants import DEFAULT_API_URL

if TYPE_CHECKING:
    from vicoa.rpc.worktree_setup import HookResult


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


def _execute_setup(
    worktree_root: str, source_repo: str, commands: list[str], branch: str
) -> HookResult | None:
    """Run ``commands`` in ``worktree_root``, echoing each and streaming its
    output, and write the run record the dashboard's setup badge reads.
    ``None`` when interrupted (Ctrl-C), else the run's result."""
    from vicoa.rpc.worktree_setup import SetupEvent, SetupRunRecorder, run_commands

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
        return None
    recorder.finish(outcome[0])
    return outcome[0]


def _cmd_setup(args) -> int:
    from vicoa.rpc.worktree_setup import (
        current_branch,
        read_committed_config_commands,
        read_setup_status,
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

    started = time.monotonic()
    result = _execute_setup(worktree_root, source_repo, commands, branch)
    if result is None:
        return 130
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


def _file_session(args, session_id: str, branch: str) -> str | None:
    """File the session under the new worktree, as ``vicoa session update
    --worktree`` does: its sidebar group and its next resume (and the task's
    later sessions) follow the folder. ``None`` when done, else why not."""
    from vicoa.commands._api import RequestError, _load_stored_api_key, request
    from vicoa.commands.instance import _resolve_worktree_move

    base_url = getattr(args, "base_url", None) or DEFAULT_API_URL
    api_key = (
        getattr(args, "api_key", None)
        or os.environ.get("VICOA_API_KEY")
        or _load_stored_api_key(base_url)
    )
    if not api_key:
        return "no Vicoa API key found"
    try:
        body = _resolve_worktree_move(
            args, api_key, session_id, branch, raise_on_error=True
        )
        updated = request(
            args,
            api_key,
            "PATCH",
            f"/api/v1/agent-instances/{session_id}",
            json=body,
            raise_on_error=True,
        )
    except (ValueError, RequestError) as exc:
        return str(exc)
    except SystemExit:
        # `request` exits on a transport error or a 401, having said why on
        # stderr. The worktree exists by now, and exiting non-zero would read
        # as "no worktree": an agent would make another one.
        return "the Vicoa server could not be reached"
    if not isinstance(updated, dict) or updated.get("project") != body["project"]:
        return "the server predates moving a session to a worktree"
    return None


def _cmd_new(args) -> int:
    from vicoa.rpc.worktree_ops import create_worktree
    from vicoa.rpc.worktree_setup import current_branch, read_committed_config_commands
    from vicoa.rpc.worktree_trust import is_repo_trusted

    start = os.path.realpath(os.path.expanduser(args.path or "."))
    resolved = _resolve_checkout(start)
    if resolved is None:
        print(
            f"{start} is not inside a git repository, so it has no worktrees: "
            "work in it as it is.",
            file=sys.stderr,
        )
        return 1
    checkout, source_repo = resolved
    if checkout != source_repo:
        # A worktree already. Forking another off it is rarely what an agent
        # on a task means; pointing --path at the main checkout still does it.
        branch = current_branch(checkout) or os.path.basename(checkout)
        print(f"Already in worktree {branch}, so nothing was made. Work here:")
        print(start)
        return 0

    created = create_worktree(start, name=args.name, suffix_if_taken=True)
    error = created.get("error")
    if error:
        reason = {
            "invalid_name": f"'{args.name}' is not a valid branch name",
            "not_a_repo": f"{start} is not inside a git repository",
        }.get(str(error), str(error))
        print(f"error: couldn't make a worktree: {reason}", file=sys.stderr)
        return 1
    path, branch = str(created["path"]), str(created["branch"])
    # A session in a subfolder of the repo (`repo/apps/web`) works in the same
    # subfolder of the worktree, as the daemon starts one.
    subdir = os.path.relpath(start, str(created["repo_root"]))
    work_dir = path if subdir in ("", ".") else os.path.join(path, subdir)
    taken = f" ({args.name} was taken)" if args.name and branch != args.name else ""
    print(f"Made worktree {branch}{taken} off {source_repo}.", flush=True)

    session_id = None if args.no_session else os.environ.get("VICOA_AGENT_INSTANCE_ID")
    if session_id:
        problem = _file_session(args, session_id, branch)
        if problem:
            print(
                f"Couldn't file this session under it ({problem}). Run "
                f'`vicoa session update "$VICOA_AGENT_INSTANCE_ID" --worktree {branch}`.',
                file=sys.stderr,
            )
        else:
            print("Filed this session under it.")

    commands = read_committed_config_commands(source_repo, "setup")
    if commands and args.no_setup:
        print(f"Setup skipped. Run `vicoa worktree setup {path}` to run it.")
    elif commands and not is_repo_trusted(source_repo):
        # The daemon's gate, unchanged: a repo's setup is arbitrary shell, and
        # only a repo trusted on this machine runs it without being asked.
        print(
            "Setup not run: this repository's worktree setup isn't trusted on this "
            f"machine. Run `vicoa worktree setup {path}` to run it."
        )
    elif commands:
        print()
        result = _execute_setup(path, source_repo, commands, branch)
        if result is None:
            print(f"Setup interrupted. Run `vicoa worktree setup {path}` to finish it.")
        elif not result.ok:
            failed = result.failed_result
            step = result.results.index(failed) + 1 if failed else len(commands)
            print(
                f"Setup failed at step {step}/{len(commands)}. Fix it, then run "
                f"`vicoa worktree setup {path}`.",
                file=sys.stderr,
            )
        else:
            print("Setup done.")

    print()
    print("Work in:")
    print(work_dir)
    return 0


_HANDLERS = {"setup": _cmd_setup, "new": _cmd_new}


def run_worktree_command(args) -> int:
    """Entry point wired into ``cli.py``'s dispatch for ``vicoa worktree``."""
    sub = getattr(args, "worktree_command", None)
    handler = _HANDLERS.get(sub) if sub else None
    if handler is None:
        print(
            "usage: vicoa worktree new [NAME] [--path DIR] [--no-setup]\n"
            "       vicoa worktree setup [PATH] [--trust] [--dry-run] [--force]\n"
            "Run `vicoa worktree --help` for details.",
            file=sys.stderr,
        )
        return 2
    return handler(args)


def add_worktree_subparser(subparsers) -> None:
    """Register the ``worktree`` subcommand tree on ``cli.py``'s subparsers."""
    parser = subparsers.add_parser(
        "worktree",
        help="Make a worktree for this session, or run a worktree's setup commands",
    )
    sub = parser.add_subparsers(dest="worktree_command")

    new = sub.add_parser(
        "new",
        help="Make a worktree of this repository and move this session into it",
        description=(
            "Makes a git worktree (a separate checkout on a new branch) of the "
            "repository the current directory is in, where Vicoa makes one for a "
            "new session, and runs the repository's worktree.setup in it when "
            "the repository is trusted on this machine. Run inside a Vicoa "
            "session, it also files that session under the worktree, so the "
            "app shows it there and the session resumes there. Prints the "
            "folder to work in last. Inside a worktree already, it makes nothing "
            "and prints that folder. Exits 0 once the worktree exists, even when "
            "its setup fails (it says so)."
        ),
    )
    new.add_argument(
        "name",
        nargs="?",
        help=(
            "Name for the branch and folder, e.g. vic-42 (default: a random "
            "one). Taken already? The first free vic-42-2, vic-42-3, … is used"
        ),
    )
    new.add_argument(
        "--path",
        help="A directory inside the repository (default: current directory)",
    )
    new.add_argument(
        "--no-setup",
        action="store_true",
        help="Don't run the repository's worktree.setup commands",
    )
    new.add_argument(
        "--no-session",
        action="store_true",
        help="Don't file the current Vicoa session under the new worktree",
    )
    new.add_argument(
        "--api-key",
        help="API key (defaults to VICOA_API_KEY or the stored credential)",
    )
    new.add_argument(
        "--base-url",
        default=DEFAULT_API_URL,
        help="Base URL of the Vicoa API server",
    )

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
