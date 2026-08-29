"""TerminalOutputCoalescer: batches bursty pty output, preserves order.

The coalescer folds a burst of small reads into a few frames so the relay's
256-frame outbox can't be overflowed by a chatty terminal, while guaranteeing a
pty's output — and its final exit — arrive strictly in order.
"""

from __future__ import annotations

import threading
import time

from vicoa.terminal.coalescer import TerminalOutputCoalescer


class _Sink:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, object]] = []
        self._lock = threading.Lock()

    def on_output(self, pty_id: str, data: bytes) -> None:
        with self._lock:
            self.events.append(("out", pty_id, data))

    def on_exit(self, pty_id: str, code: int | None) -> None:
        with self._lock:
            self.events.append(("exit", pty_id, code))

    def snapshot(self) -> list[tuple[str, str, object]]:
        with self._lock:
            return list(self.events)


def _wait_for(pred, timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.005)
    return False


def test_burst_is_coalesced_and_kept_in_order() -> None:
    sink = _Sink()
    coalescer = TerminalOutputCoalescer(
        on_output=sink.on_output, on_exit=sink.on_exit, interval=0.05
    )
    try:
        chunks = [f"{i},".encode() for i in range(20)]
        for chunk in chunks:
            coalescer.handle("p1", chunk)
        assert _wait_for(lambda: any(e[0] == "out" for e in sink.snapshot()))
        time.sleep(0.12)  # let any trailing drain settle
        outs = [e for e in sink.snapshot() if e[0] == "out" and e[1] == "p1"]
        # 20 tiny writes fold into a handful of frames, not 20.
        assert 1 <= len(outs) <= 3
        assert b"".join(e[2] for e in outs) == b"".join(chunks)  # order preserved
    finally:
        coalescer.shutdown()


def test_output_is_flushed_before_exit() -> None:
    sink = _Sink()
    coalescer = TerminalOutputCoalescer(
        on_output=sink.on_output, on_exit=sink.on_exit, interval=0.05
    )
    try:
        coalescer.handle("p1", b"tail-bytes")
        coalescer.mark_exit("p1", 0)
        assert _wait_for(lambda: any(e[0] == "exit" for e in sink.snapshot()))
        events = [e for e in sink.snapshot() if e[1] == "p1"]
        assert [e[0] for e in events] == ["out", "exit"]  # output THEN exit
        assert events[0][2] == b"tail-bytes"  # trailing bytes not dropped
        assert events[1][2] == 0
    finally:
        coalescer.shutdown()


def test_size_cap_forces_an_early_flush() -> None:
    sink = _Sink()
    # A huge interval means only the byte cap can trigger a flush.
    coalescer = TerminalOutputCoalescer(
        on_output=sink.on_output, on_exit=sink.on_exit, interval=5.0, max_bytes=1024
    )
    try:
        coalescer.handle("p1", b"x" * 4096)
        assert _wait_for(
            lambda: any(e[0] == "out" for e in sink.snapshot()), timeout=1.0
        )
    finally:
        coalescer.shutdown()


def test_shutdown_flushes_pending_output() -> None:
    sink = _Sink()
    coalescer = TerminalOutputCoalescer(
        on_output=sink.on_output, on_exit=sink.on_exit, interval=5.0
    )
    coalescer.handle("p1", b"pending")
    coalescer.shutdown()  # a clean exit must not lose buffered bytes
    outs = [e for e in sink.snapshot() if e[0] == "out"]
    assert outs and b"".join(e[2] for e in outs) == b"pending"
