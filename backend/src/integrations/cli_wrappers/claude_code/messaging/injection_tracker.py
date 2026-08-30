"""Consume-once FIFO tracker for UI→Claude→JSONL echo suppression.

When a UI-originated user message is injected into Claude's input queue, Claude
transcribes it into its JSONL log. The JSONL monitor then sees that line and,
without this tracker, would call ``send_user_message`` to write a second copy
of the same message into the backend database.

Set-based deduplication (see ``MessageDeduplicator``) cannot solve this without
breaking the case where a user legitimately sends the same short content twice
in quick succession (e.g., clicking "No" on two consecutive permission prompts):
the second click would be wrongly suppressed as a "fake echo" of the first.

This tracker fixes that by giving each injection its own slot. Each UI injection
enqueues one entry; each JSONL echo consumes one matching entry. Two "No"
injections occupy two independent slots, each consumed by its own echo.
"""

import time
from collections import deque


class InjectionTracker:
    """FIFO tracker for content injected into Claude's input queue.

    ``mark_injected`` is called once per UI-originated injection.
    ``try_consume_echo`` is called once per CLI-originated JSONL user message;
    it returns True (and removes the matching entry) if the content matches a
    pending injection.

    Entries older than ``window_seconds`` are dropped on every operation, and
    ``max_pending`` caps the deque size so a pathological injection burst (or a
    matching bug that prevents consumption) cannot leak memory.
    """

    def __init__(self, window_seconds: float = 60.0, max_pending: int = 200):
        # deque(maxlen=...) silently drops the oldest entry when full. In the
        # worst case this causes one missed echo suppression (one extra row in
        # the DB), never an OOM.
        self._pending: deque[tuple[float, str]] = deque(maxlen=max_pending)
        self._window = window_seconds

    @staticmethod
    def _normalize(content: str) -> str:
        return " ".join(content.split()).strip()

    def mark_injected(self, content: str) -> None:
        """Record that ``content`` was just injected into Claude's input."""
        self._trim()
        normalized = self._normalize(content)
        if normalized:
            self._pending.append((time.time(), normalized))

    def try_consume_echo(self, content: str) -> bool:
        """Return True (and consume one slot) if ``content`` matches a pending injection."""
        self._trim()
        normalized = self._normalize(content)
        if not normalized:
            return False
        for i, (_, c) in enumerate(self._pending):
            if c == normalized:
                del self._pending[i]
                return True
        return False

    def _trim(self) -> None:
        cutoff = time.time() - self._window
        while self._pending and self._pending[0][0] < cutoff:
            self._pending.popleft()

    def pending_count(self) -> int:
        """Diagnostic — current queue depth after trim."""
        self._trim()
        return len(self._pending)
