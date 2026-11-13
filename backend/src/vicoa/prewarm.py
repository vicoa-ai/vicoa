"""The daemon's pool of prewarmed ("standby") agent sessions.

While the user types in a new-session composer, the client asks the daemon to
``prewarm-session``: the daemon launches the session it would launch on send,
with ``--standby`` (see ``vicoa.standby``), so the agent's engine starts during
the typing. On ``spawn-session`` the daemon looks the request up here; a match
gets the go line (with the prompt) instead of a cold launch.

A standby is keyed by the exact command the spawn would run, with the session
id replaced by a placeholder and no prompt: everything fixed at engine start
(directory, agent, model, effort, permission mode, system prompt, ...) has to
match, or the standby is the wrong session.

The pool never talks to the server. An unused standby is discarded by closing
its stdin; it exits without ever registering, so nobody else hears about it.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

#: Unused standbys kept per machine. Each warm Claude holds ~400 MiB.
PREWARM_CAPACITY = 2
#: How long an unused standby lives. The CLI snapshots its start-up context
#: (SessionStart hook output, CLAUDE.md, MCP tools), so a long-lived one would
#: run the prompt on stale context. A client still typing re-requests it.
PREWARM_TTL_SECONDS = 180.0
#: Below this much available memory the daemon does not prewarm.
PREWARM_MIN_AVAILABLE_BYTES = 2 * 1024**3
#: ``VICOA_PREWARM=0`` turns prewarming off on this machine.
PREWARM_ENV = "VICOA_PREWARM"
#: How long a discarded standby gets to exit on its own before it is terminated.
DISCARD_GRACE_SECONDS = 10.0

PLACEHOLDER_SESSION_ID = "00000000-0000-0000-0000-000000000000"


def prewarm_disabled() -> bool:
    return os.environ.get(PREWARM_ENV, "").strip().lower() in {
        "0",
        "false",
        "off",
        "no",
    }


def available_memory_bytes() -> Optional[int]:
    """Memory the OS can hand out now, or None when it cannot be read."""
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/meminfo", encoding="ascii") as fh:
                for line in fh:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) * 1024
            return None
        if sys.platform == "darwin":
            out = subprocess.run(
                ["vm_stat"], capture_output=True, text=True, timeout=2, check=True
            ).stdout
            return parse_vm_stat(out)
        if sys.platform == "win32":
            return _windows_available_memory()
    except Exception:  # noqa: BLE001 - unknown is not a reason to refuse
        logger.debug("could not read available memory", exc_info=True)
    return None


def parse_vm_stat(output: str) -> Optional[int]:
    """Free + inactive + speculative + purgeable pages from ``vm_stat``, in bytes."""
    size = re.search(r"page size of (\d+) bytes", output)
    if not size:
        return None
    pages = 0
    for label in ("free", "inactive", "speculative", "purgeable"):
        match = re.search(rf"Pages {label}:\s+(\d+)", output)
        if match:
            pages += int(match.group(1))
    return pages * int(size.group(1))


def _windows_available_memory() -> Optional[int]:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
        return None
    return int(status.ullAvailPhys)


def standby_key(command: list[str], session_id: str, cwd: str) -> str:
    """The pool key for a spawn command: the session id masked, plus the cwd."""
    masked = [
        PLACEHOLDER_SESSION_ID if part == session_id else part for part in command
    ]
    return json.dumps({"cwd": cwd, "command": masked}, separators=(",", ":"))


def go_line(prompt: Optional[str]) -> bytes:
    return (json.dumps({"prompt": prompt}) + "\n").encode("utf-8")


@dataclass
class Standby:
    key: str
    session_id: str
    process: subprocess.Popen[bytes]
    expires_at: float
    created_at: float = field(default_factory=time.monotonic)

    def alive(self) -> bool:
        return self.process.poll() is None


class PrewarmPool:
    """Unused standbys by key. Thread-safe: RPCs are served on worker threads."""

    def __init__(
        self,
        *,
        capacity: int = PREWARM_CAPACITY,
        ttl_seconds: float = PREWARM_TTL_SECONDS,
        on_discard: Optional[Callable[[Standby, str], None]] = None,
        clock: Callable[[], float] = time.monotonic,
        grace_seconds: float = DISCARD_GRACE_SECONDS,
    ) -> None:
        self._capacity = capacity
        self._ttl = ttl_seconds
        self._on_discard = on_discard
        self._clock = clock
        self._grace = grace_seconds
        self._lock = threading.Lock()
        self._entries: dict[str, Standby] = {}
        self._reaper: Optional[threading.Thread] = None
        self._closed = threading.Event()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def refresh(self, key: str) -> Optional[Standby]:
        """The live standby for ``key`` with its timer restarted, else None."""
        with self._lock:
            self._reap_locked()
            entry = self._entries.get(key)
            if entry is None:
                return None
            entry.expires_at = self._clock() + self._ttl
            return entry

    def add(
        self, key: str, launch: Callable[[], tuple[str, subprocess.Popen[bytes]]]
    ) -> Standby:
        """Launch a standby for ``key``, making room by discarding the oldest."""
        with self._lock:
            self._reap_locked()
            existing = self._entries.pop(key, None)
            if existing is not None:
                self._discard_locked(existing, "replaced")
            while len(self._entries) >= self._capacity:
                oldest = min(self._entries.values(), key=lambda e: e.created_at)
                del self._entries[oldest.key]
                self._discard_locked(oldest, "evicted")
            session_id, process = launch()
            entry = Standby(
                key=key,
                session_id=session_id,
                process=process,
                expires_at=self._clock() + self._ttl,
            )
            self._entries[key] = entry
            self._ensure_reaper_locked()
            return entry

    def take(self, key: str) -> Optional[Standby]:
        """Remove and return the live standby for ``key`` (it is being adopted)."""
        with self._lock:
            self._reap_locked()
            return self._entries.pop(key, None)

    def discard(self, entry: Standby, reason: str) -> None:
        with self._lock:
            if self._entries.get(entry.key) is entry:
                del self._entries[entry.key]
            self._discard_locked(entry, reason)

    def close(self) -> None:
        """Discard every standby (the daemon is shutting down)."""
        self._closed.set()
        with self._lock:
            entries, self._entries = list(self._entries.values()), {}
            for entry in entries:
                self._discard_locked(entry, "shutdown")

    # -- internals -------------------------------------------------------------

    def _reap_locked(self) -> None:
        now = self._clock()
        for key, entry in list(self._entries.items()):
            if not entry.alive():
                del self._entries[key]
                self._discard_locked(entry, "exited")
            elif now >= entry.expires_at:
                del self._entries[key]
                self._discard_locked(entry, "expired")

    def _discard_locked(self, entry: Standby, reason: str) -> None:
        logger.info("prewarm: discarding %s (%s)", entry.session_id, reason)
        close_stdin(entry.process)
        if entry.alive():
            threading.Thread(
                target=_terminate_after,
                args=(entry.process, self._grace),
                name="prewarm-discard",
                daemon=True,
            ).start()
        if self._on_discard is not None:
            try:
                self._on_discard(entry, reason)
            except Exception:  # noqa: BLE001 - bookkeeping must not break the pool
                logger.debug("prewarm on_discard failed", exc_info=True)

    def _ensure_reaper_locked(self) -> None:
        if self._reaper is not None and self._reaper.is_alive():
            return
        self._reaper = threading.Thread(
            target=self._reap_loop, name="prewarm-reaper", daemon=True
        )
        self._reaper.start()

    def _reap_loop(self) -> None:
        while not self._closed.wait(5.0):
            with self._lock:
                self._reap_locked()
                if not self._entries:
                    self._reaper = None
                    return


def close_stdin(process: subprocess.Popen[bytes]) -> None:
    """End of file for the standby: it exits without registering."""
    stdin = process.stdin
    if stdin is None:
        return
    try:
        stdin.close()
    except OSError:
        pass


def send_go(process: subprocess.Popen[bytes], prompt: Optional[str]) -> bool:
    """Hand the standby its first prompt and let go of the pipe. False if it is gone."""
    stdin = process.stdin
    if stdin is None or process.poll() is not None:
        return False
    try:
        stdin.write(go_line(prompt))
        stdin.flush()
        stdin.close()
    except (BrokenPipeError, OSError, ValueError):
        return False
    return True


def _terminate_after(process: subprocess.Popen[bytes], grace: float) -> None:
    try:
        process.wait(timeout=grace)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        process.terminate()
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        process.kill()
    except OSError:
        pass
