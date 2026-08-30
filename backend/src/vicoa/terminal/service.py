"""Renderer-driven PTY sessions for the desktop terminal tab.

Each session wraps a :class:`~vicoa.terminal.pty_manager.PTYManager` running a
general shell (not the Claude TUI). A per-session reader thread pumps
master-fd output to the ``on_output`` callback; child exit is reported exactly
once via ``on_exit``. All public methods are thread-safe.

The service never calls ``set_raw_mode`` / ``restore_terminal`` — the daemon
process typically has no controlling TTY when launched from Electron, and the
renderer's xterm owns the user-facing terminal state.
"""

from __future__ import annotations

import logging
import os
import select
import shlex
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from .pty_manager import PTYManager

logger = logging.getLogger(__name__)

DEFAULT_MAX_SESSIONS = 16
_READ_CHUNK_BYTES = 4096
_SELECT_TIMEOUT_SECONDS = 0.5

# Lease reaping: a client that opts into a lease (passing ``lease_secs`` to
# ``spawn``) must keep renewing it via ``renew_leases`` or the session is killed
# as an orphan. This catches the leak where a browser reload / crash tears down
# the page without sending ``pty-kill`` — the daemon (and the shell it hosts)
# would otherwise outlive the client forever, marching toward the 16-session cap
# with abandoned processes still running. Sessions spawned WITHOUT ``lease_secs``
# (older clients that can't heartbeat) are never lease-reaped, so this is purely
# additive. The client renews well inside the grace (~15s renew vs 60s grace).
DEFAULT_LEASE_SECONDS = 60.0
_MIN_LEASE_SECONDS = 30.0
_MAX_LEASE_SECONDS = 3600.0
_REAPER_INTERVAL_SECONDS = 10.0

OutputCallback = Callable[[str, bytes], None]
ExitCallback = Callable[[str, Optional[int]], None]


def default_shell() -> str:
    """The user's login shell, with a per-platform fallback."""
    shell = os.environ.get("SHELL", "").strip()
    if shell:
        return shell
    return "/bin/zsh" if sys.platform == "darwin" else "/bin/bash"


def _clamp_lease(lease_secs: float | None) -> float:
    """Bound a client-requested lease so a bad value can't self-reap a live pty
    (too short) or pin an orphan forever (too long)."""
    if lease_secs is None:
        return DEFAULT_LEASE_SECONDS
    return max(_MIN_LEASE_SECONDS, min(_MAX_LEASE_SECONDS, float(lease_secs)))


@dataclass
class _TerminalSession:
    pty_id: str
    manager: PTYManager
    stop_requested: threading.Event = field(default_factory=threading.Event)
    reader: threading.Thread | None = None
    # ``time.monotonic()`` past which an unrenewed lease is reaped, or None for
    # a session the client never opted into leasing (never lease-reaped).
    lease_deadline: float | None = None
    # Serializes PTYManager.close() between kill()/shutdown() callers and the
    # reader thread's finalize. Without it two threads can race through
    # close() and double-close the master fd — after the OS reuses the fd
    # number, the second close silently kills an unrelated file descriptor.
    close_lock: threading.Lock = field(default_factory=threading.Lock)


class TerminalService:
    """Registry of renderer-driven PTY sessions (spawn/write/resize/kill).

    Output and exit events are delivered on internal reader threads via the
    bound callbacks — callers must make their callbacks thread-safe (the local
    server bridges them onto its event loop).
    """

    def __init__(
        self,
        *,
        on_output: OutputCallback | None = None,
        on_exit: ExitCallback | None = None,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        reaper_interval: float = _REAPER_INTERVAL_SECONDS,
        enable_reaper: bool = True,
    ) -> None:
        self._on_output = on_output
        self._on_exit = on_exit
        self._max_sessions = max_sessions
        self._sessions: dict[str, _TerminalSession] = {}
        self._lock = threading.Lock()
        # Lease reaper: started lazily on the first leased session, so a service
        # that never leases (older callers, unit tests) spawns no thread.
        self._reaper_interval = reaper_interval
        self._reaper_enabled = enable_reaper
        self._reaper_stop = threading.Event()
        self._reaper_thread: threading.Thread | None = None
        self._reaper_start_lock = threading.Lock()

    def bind(self, *, on_output: OutputCallback, on_exit: ExitCallback) -> None:
        """Attach the output/exit callbacks (called by the local server app).

        Split from the constructor so the service can be created before the
        server app that fans its events out to WebSocket clients exists.
        """
        self._on_output = on_output
        self._on_exit = on_exit

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------
    def spawn(
        self,
        cwd: str,
        cols: int,
        rows: int,
        command: list[str] | None = None,
        lease_secs: float | None = None,
    ) -> str:
        """Spawn a shell (or explicit command) in a fresh PTY; return pty_id.

        When ``lease_secs`` is given the session is lease-managed: the caller
        must keep it alive via ``renew_leases`` or the reaper kills it once the
        grace elapses (see ``DEFAULT_LEASE_SECONDS``). Omit it to keep a session
        that only ``kill``/``shutdown`` can end (the legacy, non-heartbeat path).
        """
        expanded_cwd = os.path.abspath(os.path.expanduser(cwd or "~"))
        if not os.path.isdir(expanded_cwd):
            raise ValueError(f"terminal cwd does not exist: {expanded_cwd}")

        cols = max(2, int(cols))
        rows = max(2, int(rows))
        target = [str(part) for part in command] if command else [default_shell(), "-l"]

        # PTYManager has no cwd parameter (the file moved byte-identical from
        # the Claude wrapper), so start the child through a `cd && exec` shim
        # to apply the requested working directory.
        wrapped = [
            "/bin/sh",
            "-c",
            f'cd {shlex.quote(expanded_cwd)} && exec "$@"',
            "vicoa-terminal",
            *target,
        ]

        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["PWD"] = expanded_cwd

        pty_id = uuid.uuid4().hex
        manager = PTYManager(
            log_func=lambda msg, pid=pty_id: logger.debug("terminal %s: %s", pid, msg)
        )
        session = _TerminalSession(pty_id=pty_id, manager=manager)
        if lease_secs is not None:
            session.lease_deadline = time.monotonic() + _clamp_lease(lease_secs)

        with self._lock:
            if len(self._sessions) >= self._max_sessions:
                raise RuntimeError(
                    f"terminal session limit reached ({self._max_sessions})"
                )
            self._sessions[pty_id] = session

        try:
            manager.create_pty(wrapped, env=env)
            # create_pty sizes the PTY from the daemon's own terminal (or
            # 80x24); re-size to what the renderer actually asked for.
            manager._set_terminal_size(rows, cols)
        except Exception:
            with self._lock:
                self._sessions.pop(pty_id, None)
            raise

        reader = threading.Thread(
            target=self._pump,
            args=(session,),
            name=f"vicoa-terminal-{pty_id[:8]}",
            daemon=True,
        )
        session.reader = reader
        reader.start()
        # Arm the reaper only now — after the pty and its reader are up, so a
        # failed spawn (popped above) never leaves a reaper running with no
        # sessions, and the first forkpty isn't done with an extra live thread.
        if session.lease_deadline is not None:
            self._ensure_reaper_started()
        logger.info(
            "terminal session %s spawned: cwd=%s command=%s size=%dx%d",
            pty_id,
            expanded_cwd,
            target,
            cols,
            rows,
        )
        return pty_id

    def write(self, pty_id: str, data: bytes) -> None:
        """Write raw bytes to a session's PTY master."""
        self._get(pty_id).manager.write_to_pty(data)

    def resize(self, pty_id: str, cols: int, rows: int) -> None:
        """Resize a session's PTY (fires SIGWINCH in the child)."""
        self._get(pty_id).manager._set_terminal_size(max(2, rows), max(2, cols))

    def kill(self, pty_id: str) -> None:
        """Terminate a session's child and close its PTY.

        The reader thread observes the closed fd, reaps the child, and emits
        the single ``on_exit`` for the session.
        """
        session = self._get(pty_id)
        session.stop_requested.set()
        self._close_session(session, context="kill")

    def renew_leases(
        self, pty_ids: Iterable[str], lease_secs: float | None = None
    ) -> list[str]:
        """Extend the lease on each live, lease-managed session; return the ids
        actually renewed (unknown ids are skipped, so a stale client id is a
        no-op rather than an error). Renewing arms the reaper if it wasn't yet.
        """
        deadline = time.monotonic() + _clamp_lease(lease_secs)
        renewed: list[str] = []
        with self._lock:
            for pty_id in pty_ids:
                session = self._sessions.get(pty_id)
                if session is not None:
                    session.lease_deadline = deadline
                    renewed.append(pty_id)
        if renewed:
            self._ensure_reaper_started()
        return renewed

    def reap_expired(self) -> list[str]:
        """Kill every lease-managed session whose grace has elapsed; return the
        reaped ids. Called on a timer by the reaper thread (also a test hook)."""
        now = time.monotonic()
        with self._lock:
            expired = [
                session.pty_id
                for session in self._sessions.values()
                if session.lease_deadline is not None and session.lease_deadline <= now
            ]
        for pty_id in expired:
            logger.info(
                "terminal session %s lease expired; reaping orphaned pty", pty_id
            )
            try:
                self.kill(pty_id)
            except KeyError:
                pass  # finalized between the scan and the kill; already gone.
            except Exception:
                logger.exception("terminal reaper: killing %s failed", pty_id)
        return expired

    def shutdown(self) -> None:
        """Kill every live session (used on daemon exit)."""
        self._reaper_stop.set()
        reaper = self._reaper_thread
        if reaper is not None:
            reaper.join(timeout=2.0)
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            session.stop_requested.set()
            self._close_session(session, context="shutdown")
        for session in sessions:
            if session.reader is not None:
                session.reader.join(timeout=2.0)

    def live_session_ids(self) -> list[str]:
        """Ids of sessions still registered (test/introspection helper)."""
        with self._lock:
            return list(self._sessions)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _ensure_reaper_started(self) -> None:
        """Start the reaper thread the first time a lease is created. Idempotent;
        no thread exists until a client actually opts into leasing."""
        if self._reaper_thread is not None or not self._reaper_enabled:
            return
        with self._reaper_start_lock:
            if self._reaper_thread is not None:
                return
            thread = threading.Thread(
                target=self._reaper_loop,
                name="vicoa-terminal-reaper",
                daemon=True,
            )
            self._reaper_thread = thread
            thread.start()

    def _reaper_loop(self) -> None:
        # wait() returns True only when shutdown sets the stop event; a timeout
        # (False) is a normal sweep tick.
        while not self._reaper_stop.wait(self._reaper_interval):
            try:
                self.reap_expired()
            except Exception:
                logger.exception("terminal lease reaper sweep failed")

    def _get(self, pty_id: str) -> _TerminalSession:
        with self._lock:
            session = self._sessions.get(pty_id)
        if session is None:
            raise KeyError(f"unknown pty_id: {pty_id}")
        return session

    def _pump(self, session: _TerminalSession) -> None:
        """Reader loop: select on the master fd, forward output, detect exit."""
        manager = session.manager
        try:
            while not session.stop_requested.is_set():
                fd = manager.master_fd
                if fd is None:
                    break
                try:
                    ready, _, _ = select.select([fd], [], [], _SELECT_TIMEOUT_SECONDS)
                except (OSError, ValueError):
                    # fd closed under us by kill()/shutdown().
                    break
                if not ready:
                    if not manager.is_child_alive():
                        break
                    continue
                try:
                    data = manager.read_from_pty(_READ_CHUNK_BYTES)
                except OSError:
                    # EIO when the child side is gone (normal exit on Linux;
                    # macOS usually returns b"" instead).
                    break
                if data == b"":
                    break
                self._emit_output(session.pty_id, data)
        finally:
            # Reap first (close() would reap too, but then the code is lost),
            # then release the fd and report the exit exactly once — this
            # finally is the sole caller of _finalize for the session.
            exit_code = manager.wait_for_child(timeout=2.0)
            self._finalize(session, exit_code)

    def _emit_output(self, pty_id: str, data: bytes) -> None:
        callback = self._on_output
        if callback is None:
            return
        try:
            callback(pty_id, data)
        except Exception:
            logger.exception("terminal session %s: output callback raised", pty_id)

    def _close_session(self, session: _TerminalSession, *, context: str) -> None:
        """Run PTYManager.close() exactly-once-at-a-time for this session.

        ``close_lock`` serializes concurrent callers (kill/shutdown vs the
        reader's finalize); the second caller then sees ``master_fd is None``
        inside close() and no-ops instead of double-closing a possibly-reused
        fd number.
        """
        with session.close_lock:
            try:
                # kill_group: a shell tab's running command (e.g. a dev server)
                # must die with the tab, not linger as an orphan.
                session.manager.close(kill_group=True)
            except Exception:
                logger.exception(
                    "terminal session %s: close failed during %s",
                    session.pty_id,
                    context,
                )

    def _finalize(self, session: _TerminalSession, exit_code: int | None) -> None:
        with self._lock:
            self._sessions.pop(session.pty_id, None)
        self._close_session(session, context="finalize")
        logger.info(
            "terminal session %s exited with code %s", session.pty_id, exit_code
        )
        callback = self._on_exit
        if callback is None:
            return
        try:
            callback(session.pty_id, exit_code)
        except Exception:
            logger.exception(
                "terminal session %s: exit callback raised", session.pty_id
            )
