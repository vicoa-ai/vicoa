"""Discover and stop vicoa-managed agent processes on the local machine.

Used by ``vicoa ls`` (read-only enumeration) and ``vicoa stop sessions``
(bulk termination). We classify each process by command pattern — we don't
keep a separate registry because (a) headless sessions are spawned with
``start_new_session=True`` and survive daemon restarts, and (b) the OS
process table is the only source that stays accurate across daemon crashes.

Cross-platform:
* **POSIX** (macOS / Linux) — ``ps ax -o pid=,etime=,command=`` + ``os.kill``
  with SIGTERM / SIGKILL.
* **Windows** — PowerShell's ``Get-CimInstance Win32_Process`` to enumerate
  (it's the only thing that reliably gives full command lines), and
  ``taskkill`` / ``taskkill /F`` to terminate. TUI sessions don't run on
  Windows today; only daemon-spawned headless sessions are expected.
"""

from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class RunningAgent:
    """A vicoa-managed agent process discovered via ``ps``."""

    pid: int
    agent: str  # "claude" / "codex" / "opencode" / "amp"
    kind: str  # "headless" / "tui"
    session_id: Optional[str]
    project_path: Optional[str]
    age: Optional[str]  # `ps etime`, e.g. "1-23:45:00" (D-HH:MM:SS) or "05:32"
    command: str  # full command-line, for debugging
    name: Optional[str] = None  # --name value passed to headless runners


# Subcommand tokens that mean a `vicoa ...` invocation is NOT a TUI session
# (it's the daemon, an admin command, or something else). Used to gate the
# fallthrough "vicoa <agent>" classification.
_NON_TUI_VICOA_TOKENS = frozenset(
    {
        "daemon",
        "stop",
        "disconnect",
        "headless",
        "ls",
        "mcp",
    }
)


def _classify(command: str) -> tuple[Optional[str], Optional[str]]:
    """Return ``(agent, kind)`` or ``(None, None)`` for a non-vicoa line.

    Order matters: headless patterns are checked first because some of them
    (the claude one) overlap with the generic "vicoa headless" form.
    """
    # ── Headless (daemon-spawned) ───────────────────────────────────────
    if "integrations.headless.codex_acp" in command:
        return ("codex", "headless")
    if "integrations.headless.codex_native" in command:
        return ("codex", "headless")
    if "integrations.headless.opencode_acp" in command:
        return ("opencode", "headless")
    if "integrations.headless.generic_acp" in command:
        # One module serves cursor/gemini/copilot/kimi/hermes; the agent id
        # rides in the --agent flag.
        return (_extract_flag(command, "--agent") or "acp", "headless")
    if "integrations.headless.claude_code" in command:
        return ("claude", "headless")

    tokens = command.split()

    # ``vicoa headless`` / ``python -m vicoa.cli headless`` — claude path
    # (codex/opencode headless go through the integrations.headless.* modules
    # above, never through vicoa.cli).
    if "headless" in tokens and any("vicoa" in t for t in tokens):
        return (_extract_flag(command, "--agent") or "claude", "headless")

    # ── TUI claude/amp wrappers ─────────────────────────────────────────
    if "integrations.cli_wrappers.claude_code" in command:
        return ("claude", "tui")
    if "integrations.cli_wrappers.amp" in command:
        return ("amp", "tui")

    # ── TUI codex/opencode/claude/amp (vicoa wrapper process) ───────────
    # `vicoa codex ...` execs the codex binary as a child; the python
    # parent is what we identify here. The child `codex` binary itself has
    # no vicoa signature so we'd never spot it otherwise.
    if any("vicoa" in t for t in tokens):
        if _NON_TUI_VICOA_TOKENS & set(tokens):
            return (None, None)
        if "codex" in tokens:
            return ("codex", "tui")
        if "opencode" in tokens:
            return ("opencode", "tui")
        # claude/amp go through `run_python_module`. In a source install
        # that spawns a `python -m integrations.cli_wrappers.*` child,
        # already classified above — classifying the `vicoa claude` parent
        # here too would double-count the session. A frozen npm build has
        # no such child: `run_python_module` runs the wrapper in-process,
        # so the `vicoa` binary's own argv is the only signature. Restrict
        # the claude/amp fallthrough to that frozen case by requiring
        # argv[0] to be the vicoa executable itself, not a Python
        # interpreter running vicoa from source.
        if tokens and _is_vicoa_executable(tokens[0]):
            if "claude" in tokens:
                return ("claude", "tui")
            if "amp" in tokens:
                return ("amp", "tui")
            # Bare `vicoa` (no subcommand, no --agent): a frozen build runs the
            # default-agent wrapper in-process, so the parent process keeps the
            # original `.../vicoa` argv with no agent hint — and pty.forks the
            # real agent child, which carries no vicoa signature either. Without
            # this branch a TUI started as plain `vicoa` is invisible to
            # `vicoa ls`. Admin subcommands (daemon/ls/headless/…) were already
            # filtered via _NON_TUI_VICOA_TOKENS / the headless branch, and
            # codex/opencode via the token checks above, so anything still here
            # is the default-agent TUI (possibly with global flags like
            # --name).
            return (_default_tui_agent(), "tui")

    return (None, None)


_AGENT_NAMES = frozenset(
    {
        "claude",
        "amp",
        "codex",
        "opencode",
        "cursor",
        "gemini",
        "copilot",
        "kimi",
        "hermes",
    }
)


def _default_tui_agent() -> str:
    """Resolve the default agent for a bare ``vicoa`` TUI session.

    A frozen ``vicoa`` launched with no subcommand runs the user's default
    agent (claude unless overridden via ``vicoa --set-default``). That choice
    isn't visible in the process argv — the wrapper runs in-process and the
    parent keeps the original ``.../vicoa`` argv — so read it from the user
    config, falling back to claude.
    """
    try:
        cfg_path = os.path.join(os.path.expanduser("~"), ".vicoa", "config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            import json

            agent = json.load(f).get("default_agent")
        if isinstance(agent, str) and agent in _AGENT_NAMES:
            return agent
    except Exception:
        pass
    return "claude"


def _is_vicoa_executable(argv0: str) -> bool:
    """True when ``argv0`` is the vicoa CLI binary itself (a frozen npm
    build), rather than a Python interpreter running vicoa from source.

    A frozen build ships as a PyInstaller binary named ``vicoa`` (e.g.
    ``…/@vicoa/cli-linux-x64/bin/vicoa``); a source install runs as
    ``python …/bin/vicoa`` or ``python -m vicoa.cli``, where argv[0] is
    the interpreter.
    """
    name = os.path.basename(argv0).lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name == "vicoa"


def _extract_flag(command: str, flag: str) -> Optional[str]:
    """Extract the value of ``--flag value`` (space-separated) from a command line.

    Tries shlex first so quoted args with spaces survive. Falls back to a plain
    whitespace split when shlex fails (e.g. an unmatched quote inside a
    ``--prompt`` argument containing an apostrophe). The flag values we care
    about — UUIDs, paths, agent names — never contain spaces, so the fallback
    is safe for all practical purposes.
    """
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    try:
        idx = tokens.index(flag)
    except ValueError:
        return None
    if idx + 1 >= len(tokens):
        return None
    return tokens[idx + 1]


def _extract_project_path(command: str) -> Optional[str]:
    """Best-effort project-path extraction. Headless claude uses --cwd,
    headless codex/opencode use --project-path; daemon TUI codex/opencode
    pass it positionally to the underlying binary, which we can't easily
    recover from ``ps`` alone."""
    return _extract_flag(command, "--cwd") or _extract_flag(command, "--project-path")


def list_running_agents() -> list[RunningAgent]:
    """Enumerate vicoa-managed agent processes (POSIX + Windows)."""
    if os.name == "nt":
        return _list_running_agents_windows()
    if os.name == "posix":
        return _list_running_agents_posix()
    return []


def _list_running_agents_posix() -> list[RunningAgent]:
    try:
        result = subprocess.run(
            ["ps", "ax", "-o", "pid=,etime=,command="],
            capture_output=True,
            check=False,
            text=True,
        )
    except Exception:
        return []

    # Format: " PID  ETIME COMMAND ..."  where etime is
    #   "MM:SS", "HH:MM:SS", or "D-HH:MM:SS". Width-padded by ps.
    # Choosing etime over lstart because lstart's locale-dependent format
    # parses inconsistently across macOS / Linux releases — we shipped a
    # bug where macOS-style "Tue 19 May …" didn't match the strptime fmt.
    line_re = re.compile(r"^\s*(\d+)\s+(\S+)\s+(.+)$")
    my_pid = os.getpid()
    agents: list[RunningAgent] = []
    for line in result.stdout.splitlines():
        m = line_re.match(line)
        if not m:
            continue
        pid_str, etime, command = m.group(1), m.group(2).strip(), m.group(3).strip()
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        if pid == my_pid:
            continue

        agent, kind = _classify(command)
        if agent is None or kind is None:
            continue

        agents.append(
            RunningAgent(
                pid=pid,
                agent=agent,
                kind=kind,
                session_id=_extract_flag(command, "--session-id"),
                project_path=_extract_project_path(command),
                age=etime,
                command=command,
                name=_extract_flag(command, "--name"),
            )
        )
    _enrich_tui_agents_posix(agents)
    return agents


# Regex matching a vicoa session log path: ~/.vicoa/<dir>/<uuid>.log
_VICOA_SESSION_LOG_RE = re.compile(
    r"[/\\]\.vicoa[/\\][^/\\]+[/\\]"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.log$",
    re.IGNORECASE,
)


def _enrich_tui_agents_posix(agents: list[RunningAgent]) -> None:
    """Fill in session_id and project_path for TUI agents that lack them.

    TUI wrapper processes don't carry ``--session-id`` / ``--cwd`` in their
    argv. Instead the wrapper writes a log at
    ``~/.vicoa/<type>_wrapper/<uuid>.log`` whose filename IS the session UUID.
    One ``lsof -F pfn -p <pids>`` call retrieves both the log path (→ UUID)
    and the process CWD (→ project path) for all matching processes at once.
    """
    targets = [a for a in agents if a.kind == "tui" and a.session_id is None]
    if not targets:
        return

    pids_str = ",".join(str(a.pid) for a in targets)
    try:
        result = subprocess.run(
            ["lsof", "-p", pids_str, "-F", "pfn"],
            capture_output=True,
            check=False,
            text=True,
            timeout=8,
        )
    except Exception:
        return

    # lsof -F pfn emits records in groups:
    #   p<pid>        ← process header
    #   f<fd-name>    ← file-descriptor name (e.g. "cwd", "3w")
    #   n<path>       ← file name for that fd
    pid_sessions: dict[int, str] = {}
    pid_cwds: dict[int, str] = {}
    current_pid: Optional[int] = None
    current_fd: Optional[str] = None

    for line in result.stdout.splitlines():
        if not line:
            continue
        tag, value = line[0], line[1:]
        if tag == "p":
            try:
                current_pid = int(value)
            except ValueError:
                current_pid = None
            current_fd = None
        elif tag == "f":
            current_fd = value
        elif tag == "n" and current_pid is not None:
            if current_fd == "cwd" and current_pid not in pid_cwds:
                pid_cwds[current_pid] = value
            m = _VICOA_SESSION_LOG_RE.search(value)
            if m and current_pid not in pid_sessions:
                pid_sessions[current_pid] = m.group(1)

    for a in targets:
        if a.pid in pid_sessions:
            a.session_id = pid_sessions[a.pid]
        if a.pid in pid_cwds and not a.project_path:
            a.project_path = pid_cwds[a.pid]


# PowerShell pipeline for Windows enumeration. Emits one tab-separated row
# per process: "<pid>\t<age_seconds>\t<command_line>". We compute age inside
# PowerShell because CIM CreationDate serializes awkwardly through stdout.
# ``-NoProfile`` skips the user's PowerShell profile for speed and isolation.
_WINDOWS_PS_SCRIPT = (
    "$ErrorActionPreference='Continue';"
    "Get-CimInstance Win32_Process | "
    "Where-Object { $_.CommandLine -ne $null } | "
    "ForEach-Object { "
    "  $age = [int]((Get-Date) - $_.CreationDate).TotalSeconds; "
    # The `t tab escape ONLY fires inside a DOUBLE-quoted PowerShell string.
    # A single-quoted '...' is literal, so the old `'{0}`t{1}`t{2}'` emitted a
    # literal backtick-t instead of a tab — every row then failed the
    # `split("\t", 2)` below and Windows reported "No active instances" even
    # with sessions running. Use PS double quotes (wrapped in Python single
    # quotes so they don't collide).
    '  Write-Output ("{0}`t{1}`t{2}" -f $_.ProcessId, $age, $_.CommandLine) '
    "}"
)


def _format_seconds_as_etime(seconds: int) -> str:
    """Render seconds as ``ps etime`` style for cross-platform consistency.

    Output matches POSIX ``ps -o etime=``: ``MM:SS`` under an hour,
    ``HH:MM:SS`` under a day, ``D-HH:MM:SS`` beyond. Keeps ``vicoa ls``
    columns identical regardless of host OS.
    """
    if seconds < 0:
        seconds = 0
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    if days > 0:
        return f"{days}-{hours:02d}:{minutes:02d}:{secs:02d}"
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _list_running_agents_windows() -> list[RunningAgent]:
    """Windows enumeration via PowerShell ``Get-CimInstance Win32_Process``.

    PowerShell is the only built-in tool that reliably exposes full
    command lines (tasklist truncates, wmic is deprecated). Available on
    every supported Windows release. If PowerShell isn't on PATH we
    silently return empty rather than crashing — matches POSIX behavior
    when ``ps`` is missing.
    """
    try:
        # ``powershell.exe`` is on PATH on every supported Windows. We don't
        # use ``pwsh`` (PowerShell Core) because it isn't installed by
        # default and the script is compatible with the older one.
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                _WINDOWS_PS_SCRIPT,
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return []

    my_pid = os.getpid()
    agents: list[RunningAgent] = []
    for line in result.stdout.splitlines():
        # Split into exactly 3 parts — the command can contain anything,
        # including tabs (unlikely but defensible).
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        pid_str, age_str, command = parts[0].strip(), parts[1].strip(), parts[2].strip()
        try:
            pid = int(pid_str)
            age_seconds = int(age_str)
        except ValueError:
            continue
        if pid == my_pid:
            continue

        agent, kind = _classify(command)
        if agent is None or kind is None:
            continue

        agents.append(
            RunningAgent(
                pid=pid,
                agent=agent,
                kind=kind,
                session_id=_extract_flag(command, "--session-id"),
                project_path=_extract_project_path(command),
                age=_format_seconds_as_etime(age_seconds),
                command=command,
                name=_extract_flag(command, "--name"),
            )
        )
    return agents


def stop_pid(pid: int, *, timeout: float = 5.0) -> tuple[bool, str]:
    """Terminate a PID with a soft-then-hard escalation.

    Returns ``(stopped, message)``. ``stopped=True`` means the process is
    no longer running (either it stopped, or it was already gone).

    Platform dispatch:
    * POSIX → SIGTERM then SIGKILL after ``timeout``.
    * Windows → ``taskkill /PID`` then ``taskkill /F /PID`` after ``timeout``.
    """
    if os.name == "nt":
        return _stop_pid_windows(pid, timeout=timeout)
    return _stop_pid_posix(pid, timeout=timeout)


def _stop_pid_posix(pid: int, *, timeout: float) -> tuple[bool, str]:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True, "already gone"
    except PermissionError as exc:
        return False, f"permission denied: {exc}"
    except Exception as exc:
        return False, f"SIGTERM failed: {exc}"

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True, "stopped"
        except PermissionError:
            # Process exists but we can't signal it; treat as still running.
            pass
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True, "stopped"
    except Exception as exc:
        return False, f"SIGKILL failed: {exc}"

    # Give SIGKILL a moment to land.
    deadline = time.time() + 1.0
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True, "killed (SIGKILL after SIGTERM timeout)"
        time.sleep(0.05)
    return False, "still alive after SIGKILL"


def _windows_pid_exists(pid: int) -> bool:
    """Best-effort PID liveness check via ``tasklist``."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except Exception:
        # If tasklist itself fails, assume the process is still there so the
        # caller proceeds to the force-kill escalation rather than reporting
        # a false success.
        return True
    return f" {pid} " in f" {result.stdout} "


def _stop_pid_windows(pid: int, *, timeout: float) -> tuple[bool, str]:
    """Soft-then-hard kill on Windows.

    ``taskkill /PID <n>`` posts WM_CLOSE — equivalent to SIGTERM for GUI
    apps; for headless Python processes it amounts to a graceful exit
    request, with no signal handler runs (Python on Windows can't intercept
    it). ``taskkill /F /PID <n>`` is the force-kill, equivalent to SIGKILL.
    """
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid)],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        return False, "taskkill not found"
    except Exception as exc:
        return False, f"taskkill failed: {exc}"

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _windows_pid_exists(pid):
            return True, "stopped"
        time.sleep(0.2)

    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        return False, "taskkill not found"
    except Exception as exc:
        return False, f"taskkill /F failed: {exc}"

    deadline = time.time() + 1.0
    while time.time() < deadline:
        if not _windows_pid_exists(pid):
            return True, "killed (taskkill /F after grace period)"
        time.sleep(0.1)
    return False, "still alive after taskkill /F"
