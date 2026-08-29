"""Output coalescer for streaming pty output over the cloud relay.

The relay's per-connection outbox sheds a client at 256 *frames*
(`shared/websocket/connection_manager.py`), so a chatty terminal emitting
thousands of tiny reads would overflow it instantly. This batches a pty's output
over a short window into a few large frames — the same idea as Paseo's 5 ms
coalescer. Only the cloud (remote) path needs it; the local 127.0.0.1 socket
streams raw for lowest echo latency.

Ordering: every emit runs on the single background drain thread, so a pty's
output chunks — and its final exit — are delivered strictly in order even though
`handle`/`mark_exit` are called from many TerminalService reader threads.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)

OutputFn = Callable[[str, bytes], None]
ExitFn = Callable[[str, "int | None"], None]

# ~10 ms window: imperceptible against WAN latency, but enough to fold a burst
# of small reads into one frame.
DEFAULT_INTERVAL_SECONDS = 0.010
# Flush early (wake the drain thread) once a pty's pending buffer passes this,
# so a firehose doesn't build one enormous frame.
DEFAULT_MAX_BYTES = 256 * 1024


class TerminalOutputCoalescer:
    """Batches per-pty output; flushes on a timer or a size cap."""

    def __init__(
        self,
        *,
        on_output: OutputFn,
        on_exit: ExitFn,
        interval: float = DEFAULT_INTERVAL_SECONDS,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self._on_output = on_output
        self._on_exit = on_exit
        self._interval = interval
        self._max_bytes = max_bytes
        self._buffers: dict[str, bytearray] = {}
        self._exits: dict[str, int | None] = {}
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def handle(self, pty_id: str, data: bytes) -> None:
        """Buffer a pty output chunk (called on a TerminalService reader thread)."""
        if not data:
            return
        with self._lock:
            if self._stopped.is_set():
                return
            buf = self._buffers.get(pty_id)
            if buf is None:
                buf = bytearray()
                self._buffers[pty_id] = buf
            buf.extend(data)
            over = len(buf) >= self._max_bytes
            self._ensure_thread_locked()
        if over:
            self._wake.set()

    def mark_exit(self, pty_id: str, exit_code: int | None) -> None:
        """Record a pty exit; drained after its remaining output, in order."""
        with self._lock:
            if self._stopped.is_set():
                return
            self._exits[pty_id] = exit_code
            self._ensure_thread_locked()
        self._wake.set()

    def shutdown(self) -> None:
        """Stop the drain thread after one final flush."""
        self._stopped.set()
        self._wake.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1.0)

    # ------------------------------------------------------------------
    def _ensure_thread_locked(self) -> None:
        # Lazy: a daemon that never serves a remote terminal never starts it.
        if self._thread is None and not self._stopped.is_set():
            self._thread = threading.Thread(
                target=self._run, name="vicoa-pty-coalesce", daemon=True
            )
            self._thread.start()

    def _run(self) -> None:
        while not self._stopped.is_set():
            self._wake.wait(self._interval)
            self._wake.clear()
            self._drain()
        self._drain()  # final flush after stop() so a clean exit isn't lost

    def _drain(self) -> None:
        with self._lock:
            outputs = [(pid, bytes(buf)) for pid, buf in self._buffers.items() if buf]
            for pid, _ in outputs:
                self._buffers[pid].clear()
            exits = list(self._exits.items())
            self._exits.clear()
            for pid, _ in exits:
                # The exited pty's remaining bytes are already captured above.
                self._buffers.pop(pid, None)
        for pid, payload in outputs:
            self._safe_output(pid, payload)
        for pid, code in exits:
            self._safe_exit(pid, code)

    def _safe_output(self, pty_id: str, payload: bytes) -> None:
        try:
            self._on_output(pty_id, payload)
        except Exception:
            logger.exception("pty coalescer output callback raised (pty=%s)", pty_id)

    def _safe_exit(self, pty_id: str, exit_code: int | None) -> None:
        try:
            self._on_exit(pty_id, exit_code)
        except Exception:
            logger.exception("pty coalescer exit callback raised (pty=%s)", pty_id)
