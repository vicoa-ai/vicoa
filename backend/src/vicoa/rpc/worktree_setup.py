"""Execution engine for worktree lifecycle commands (setup / teardown).

Runs on the machine that owns the worktree, inside a background daemon thread
(the daemon is threaded, not asyncio — this module is deliberately sync). Given a
normalized command list (see :mod:`protocol.worktree_config`) it runs each
command in the worktree, streaming output to an ``on_event`` callback so the
caller can surface progress, and stops at the first failure.

Ported from Paseo's ``runWorktreeSetupCommands`` with the gaps it documents
closed: a per-command wall-clock timeout and a cooperative abort (session stop /
worktree removal), both enforced with a process-group tree-kill so a hung
``npm ci`` can't wedge the worktree forever.

Cross-platform: commands run under ``bash -lc`` on POSIX (a login shell so the
user's PATH — nvm/pyenv/homebrew — is present, which is what makes ``npm ci``
"just work") and PowerShell on Windows. Keep this module free of POSIX-only
top-level imports; Vicoa ships a Windows daemon.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

# Per-command wall-clock ceiling and a whole-hook budget. Generous defaults —
# `npm ci` on a cold cache is slow — but bounded so a hang can't run forever.
DEFAULT_COMMAND_TIMEOUT_S = 600.0  # 10 min
DEFAULT_TOTAL_TIMEOUT_S = 1800.0  # 30 min

# Cap captured output per command so a chatty build can't balloon memory or the
# message it ends up in. Head + tail are kept; the middle is dropped.
_MAX_OUTPUT_BYTES = 64 * 1024
_TRUNCATION_MARKER = "\n...<output truncated>...\n"

_READ_CHUNK = 4096

# CSI / OSC escape sequences — stripped so streamed output is plain text.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")

HookName = Literal["setup", "teardown"]
EventType = Literal["command_started", "output", "command_completed"]


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


@dataclass
class SetupEvent:
    """One progress signal for a lifecycle command, handed to ``on_event``.

    ``command_started`` and ``command_completed`` bracket each command;
    ``output`` carries a decoded, ANSI-stripped stdout/stderr chunk in between.
    """

    type: EventType
    hook: HookName
    index: int  # 1-based position in the command list
    total: int
    command: str
    cwd: str
    stream: Literal["stdout", "stderr"] | None = None  # output only
    chunk: str | None = None  # output only
    exit_code: int | None = None  # command_completed only
    duration_ms: int | None = None  # command_completed only
    timed_out: bool = False  # command_completed only
    aborted: bool = False  # command_completed only


@dataclass
class CommandResult:
    """Outcome of one lifecycle command."""

    command: str
    cwd: str
    exit_code: int | None
    duration_ms: int
    output: str  # combined stdout+stderr, ANSI-stripped, truncated
    timed_out: bool = False
    aborted: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.aborted


@dataclass
class HookResult:
    """Aggregate outcome of a whole setup / teardown run."""

    hook: HookName
    results: list[CommandResult] = field(default_factory=list)
    aborted: bool = False

    @property
    def ok(self) -> bool:
        # An empty command list is a vacuous success.
        return all(r.ok for r in self.results) and not self.aborted

    @property
    def failed_result(self) -> CommandResult | None:
        return next((r for r in self.results if not r.ok), None)


class _BoundedOutput:
    """Accumulates decoded output, keeping head + tail within a byte budget."""

    def __init__(self, max_bytes: int = _MAX_OUTPUT_BYTES) -> None:
        self._max = max_bytes
        self._head = bytearray()
        self._tail = bytearray()
        self._truncated = False

    def append(self, chunk: str) -> None:
        data = chunk.encode("utf-8", errors="replace")
        if not self._truncated and len(self._head) + len(data) <= self._max:
            self._head.extend(data)
            return
        self._truncated = True
        self._tail.extend(data)
        # Keep only the last half-budget of tail so it stays bounded.
        keep = self._max // 2
        if len(self._tail) > keep:
            del self._tail[: len(self._tail) - keep]

    def render(self) -> str:
        head = self._head.decode("utf-8", errors="replace")
        if not self._truncated:
            return head
        tail = self._tail.decode("utf-8", errors="replace")
        return f"{head}{_TRUNCATION_MARKER}{tail}"


def _shell_invocation(command: str) -> list[str]:
    """Build the argv that runs ``command`` under a stable script shell.

    POSIX: a login bash so the interactive PATH is present. Windows: PowerShell
    with profile/execution-policy neutralized, so project commands run the same
    regardless of the machine's shell config.
    """
    if os.name == "nt":
        return [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ]
    return ["bash", "-lc", command]


def _build_env(
    *,
    worktree_path: str,
    source_repo: str,
    branch_name: str,
    project_id: str | None,
) -> dict[str, str]:
    env = os.environ.copy()
    # BASH_ENV would let a startup file rewrite the environment behind our back;
    # drop it so the shell the command runs in is predictable (matches Paseo).
    env.pop("BASH_ENV", None)
    env["VICOA_WORKTREE_PATH"] = worktree_path
    env["VICOA_SOURCE_CHECKOUT_PATH"] = source_repo
    env["VICOA_BRANCH_NAME"] = branch_name
    if project_id:
        env["VICOA_PROJECT_ID"] = project_id
    return env


def _popen_kwargs() -> dict[str, Any]:
    """Put the child in its own process group so the whole tree can be killed."""
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return {"creationflags": flags} if flags else {}
    return {"start_new_session": True}


def _terminate_tree(proc: subprocess.Popen[Any]) -> None:
    """Best-effort kill of the process and everything it spawned."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
        )
        return
    # POSIX: signal the whole process group (created via start_new_session).
    import signal  # local: keep POSIX-only symbols out of module import on Windows

    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    # Give it a moment to exit gracefully, then SIGKILL the stragglers.
    try:
        proc.wait(timeout=1.0)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _pump(stream: Any, on_chunk: Callable[[str], None]) -> None:
    """Drain a child pipe to ``on_chunk`` until EOF (runs in its own thread)."""
    try:
        while True:
            data = stream.read(_READ_CHUNK)
            if not data:
                break
            on_chunk(data.decode("utf-8", errors="replace"))
    except (ValueError, OSError):
        # Pipe closed underneath us during a kill — nothing left to read.
        return


def _run_one(
    command: str,
    *,
    hook: HookName,
    index: int,
    total: int,
    cwd: str,
    env: dict[str, str],
    command_timeout_s: float,
    deadline: float,
    abort: threading.Event | None,
    on_event: Callable[[SetupEvent], None] | None,
) -> CommandResult:
    started = time.monotonic()
    output = _BoundedOutput()
    lock = threading.Lock()

    def emit(event: SetupEvent) -> None:
        if on_event is not None:
            on_event(event)

    emit(
        SetupEvent(
            type="command_started",
            hook=hook,
            index=index,
            total=total,
            command=command,
            cwd=cwd,
        )
    )

    def on_chunk(stream: Literal["stdout", "stderr"], raw: str) -> None:
        text = strip_ansi(raw)
        if not text:
            return
        with lock:
            output.append(text)
        emit(
            SetupEvent(
                type="output",
                hook=hook,
                index=index,
                total=total,
                command=command,
                cwd=cwd,
                stream=stream,
                chunk=text,
            )
        )

    try:
        proc = subprocess.Popen(
            _shell_invocation(command),
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **_popen_kwargs(),
        )
    except OSError as exc:
        # e.g. bash/powershell not found — surface as a failed command, not a raise.
        duration_ms = int((time.monotonic() - started) * 1000)
        result = CommandResult(
            command=command,
            cwd=cwd,
            exit_code=None,
            duration_ms=duration_ms,
            output=f"failed to launch shell: {exc}",
        )
        emit(
            SetupEvent(
                type="command_completed",
                hook=hook,
                index=index,
                total=total,
                command=command,
                cwd=cwd,
                exit_code=None,
                duration_ms=duration_ms,
            )
        )
        return result

    readers = [
        threading.Thread(
            target=_pump,
            args=(proc.stdout, lambda c: on_chunk("stdout", c)),
            daemon=True,
        ),
        threading.Thread(
            target=_pump,
            args=(proc.stderr, lambda c: on_chunk("stderr", c)),
            daemon=True,
        ),
    ]
    for t in readers:
        t.start()

    cmd_deadline = min(started + command_timeout_s, deadline)
    timed_out = False
    aborted = False
    while True:
        if proc.poll() is not None:
            break
        now = time.monotonic()
        if abort is not None and abort.is_set():
            aborted = True
            _terminate_tree(proc)
            break
        if now >= cmd_deadline:
            timed_out = True
            _terminate_tree(proc)
            break
        # Short sleep keeps abort/timeout responsive without busy-spinning.
        time.sleep(0.05)

    exit_code = proc.wait()
    for t in readers:
        t.join(timeout=1.0)

    duration_ms = int((time.monotonic() - started) * 1000)
    result = CommandResult(
        command=command,
        cwd=cwd,
        exit_code=exit_code,
        duration_ms=duration_ms,
        output=output.render(),
        timed_out=timed_out,
        aborted=aborted,
    )
    emit(
        SetupEvent(
            type="command_completed",
            hook=hook,
            index=index,
            total=total,
            command=command,
            cwd=cwd,
            exit_code=exit_code,
            duration_ms=duration_ms,
            timed_out=timed_out,
            aborted=aborted,
        )
    )
    return result


def run_commands(
    commands: list[str],
    *,
    hook: HookName,
    worktree_path: str,
    source_repo: str,
    branch_name: str,
    project_id: str | None = None,
    on_event: Callable[[SetupEvent], None] | None = None,
    abort: threading.Event | None = None,
    command_timeout_s: float = DEFAULT_COMMAND_TIMEOUT_S,
    total_timeout_s: float = DEFAULT_TOTAL_TIMEOUT_S,
) -> HookResult:
    """Run a lifecycle hook's commands sequentially in the worktree.

    Stops at the first command that fails (non-zero exit, timeout, or abort) —
    later commands assume earlier ones succeeded. Returns a :class:`HookResult`;
    the caller decides what a failure means (setup leaves the worktree for
    inspection; teardown is non-fatal). Never raises for a command failure.
    """
    hook_result = HookResult(hook=hook)
    if not commands:
        return hook_result

    env = _build_env(
        worktree_path=worktree_path,
        source_repo=source_repo,
        branch_name=branch_name,
        project_id=project_id,
    )
    start = time.monotonic()
    deadline = start + total_timeout_s
    total = len(commands)

    for i, command in enumerate(commands, start=1):
        if abort is not None and abort.is_set():
            hook_result.aborted = True
            break
        result = _run_one(
            command,
            hook=hook,
            index=i,
            total=total,
            cwd=worktree_path,
            env=env,
            command_timeout_s=command_timeout_s,
            deadline=deadline,
            abort=abort,
            on_event=on_event,
        )
        hook_result.results.append(result)
        if result.aborted:
            hook_result.aborted = True
        if not result.ok:
            break

    return hook_result


def read_committed_config_commands(source_repo: str, hook: HookName) -> list[str]:
    """Read ``vicoa.json`` from the source repo working tree, return its hook.

    Working tree (not committed HEAD) so users can iterate on the config without
    committing. Any read/parse error yields ``[]`` — a broken file must never
    break a spawn. Import kept local so the daemon's hot import path stays lean.
    """
    import json

    from protocol.worktree_config import parse_committed_config

    path = Path(os.path.expanduser(source_repo)).resolve() / "vicoa.json"
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    config = parse_committed_config(data)
    return config.setup if hook == "setup" else config.teardown


def _current_branch(path: str) -> str:
    """Best-effort branch of the repo at ``path`` (``""`` when detached/broken)."""
    try:
        proc = subprocess.run(
            ["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    branch = proc.stdout.decode("utf-8", errors="replace").strip()
    return "" if branch == "HEAD" else branch


def run_worktree_setup(
    worktree_path: str,
    source_repo: str,
    *,
    project_id: str | None = None,
    on_event: Callable[[SetupEvent], None] | None = None,
    abort: threading.Event | None = None,
) -> HookResult:
    """Run a worktree's setup commands in the worktree (blocking).

    The daemon-side fallback for clients without a terminal (Windows): reads
    ``setup`` from the source repo working tree and runs it in ``worktree_path``.
    Non-visible — callers stream ``on_event`` to a log. The visible path is the
    web terminal; this exists only where no PTY is available.
    """
    commands = read_committed_config_commands(source_repo, "setup")
    if not commands:
        return HookResult(hook="setup")
    return run_commands(
        commands,
        hook="setup",
        worktree_path=worktree_path,
        source_repo=source_repo,
        branch_name=_current_branch(worktree_path),
        project_id=project_id,
        on_event=on_event,
        abort=abort,
    )


def run_worktree_teardown(
    worktree_path: str,
    repo_dir: str,
    *,
    project_id: str | None = None,
    on_event: Callable[[SetupEvent], None] | None = None,
    abort: threading.Event | None = None,
) -> HookResult:
    """Run a worktree's teardown commands before it is removed (blocking).

    Reads ``teardown`` from the worktree's own ``vicoa.json`` — it is about to be
    deleted, so its working tree is the authoritative copy. Non-fatal by
    contract: the caller runs this best-effort and proceeds with the removal
    regardless of the outcome. Branch is best-effort, only for the injected env.
    """
    commands = read_committed_config_commands(worktree_path, "teardown")
    if not commands:
        return HookResult(hook="teardown")
    return run_commands(
        commands,
        hook="teardown",
        worktree_path=worktree_path,
        source_repo=repo_dir,
        branch_name=_current_branch(worktree_path),
        project_id=project_id,
        on_event=on_event,
        abort=abort,
    )
