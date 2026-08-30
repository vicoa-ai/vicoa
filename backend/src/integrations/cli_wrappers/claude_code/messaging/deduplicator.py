"""Message deduplication utilities.

This module provides functionality to track and deduplicate messages
to avoid sending the same message multiple times.
"""

import time
from collections import deque
from typing import Deque, Set, Tuple


class MessageDeduplicator:
    """Tracks messages to prevent duplicate sends.

    This is particularly important for messages coming from the web UI
    that we don't want to echo back to the server.
    """

    def __init__(self):
        """Initialize the deduplicator."""
        self._tracked_messages: Set[str] = set()
        self._recent_messages: Deque[Tuple[float, str]] = deque()
        # SSE echoes of TUI-originated user messages have been observed to
        # arrive 15+ seconds after the TUI input was tracked (server lag,
        # heartbeat retries, etc.). 60s gives ample margin to catch the echo
        # while still allowing later legitimate UI sends of common short
        # responses ("Yes" / "No") to pass through after the window expires.
        self._recent_window_seconds = 60.0

    def track(self, content: str) -> None:
        """Track a message to mark it as seen.

        Args:
            content: Message content to track
        """
        self._tracked_messages.add(content)
        normalized = self._normalize(content)
        if normalized:
            self._recent_messages.append((time.time(), normalized))
            self._trim_recent()

    def is_duplicate(self, content: str) -> bool:
        """Check if a message was seen within the recent dedup window.

        Time-bounded by ``_recent_window_seconds``. The original
        implementation consulted an unbounded set, which caused common short
        permission responses ("Yes" / "No" / "1") to be silently dropped if
        the user had ever sent the same string earlier in the session — even
        minutes or hours later via a different channel. SSE echoes arrive
        within seconds, so the window is plenty for genuine echo
        suppression while not poisoning later legitimate sends.

        Args:
            content: Message content to check

        Returns:
            True if message was seen within the dedup window, False otherwise
        """
        self._trim_recent()
        normalized = self._normalize(content)
        if not normalized:
            return False
        return any(recent == normalized for _, recent in self._recent_messages)

    def is_near_duplicate(self, content: str) -> bool:
        """Check if a message is a near-duplicate of a recent tracked message."""
        normalized = self._normalize(content)
        if not normalized:
            return False

        self._trim_recent()
        for _, recent in self._recent_messages:
            if normalized == recent:
                return True
            if len(recent) >= len(normalized) + 5 and (
                recent.startswith(normalized) or recent.endswith(normalized)
            ):
                return True
            if len(normalized) >= len(recent) + 5 and (
                normalized.startswith(recent) or normalized.endswith(recent)
            ):
                return True
        return False

    def remove(self, content: str) -> None:
        """Remove a message from tracking.

        This is useful after processing a message to allow
        the same content to be sent again if needed.

        Args:
            content: Message content to remove from tracking
        """
        self._tracked_messages.discard(content)

    def clear(self) -> None:
        """Clear all tracked messages."""
        self._tracked_messages.clear()

    def process_user_message(self, content: str, from_web: bool = False) -> None:
        """Process a user message for deduplication.

        Only TUI-originated messages are tracked. TUI input flows through
        JSONL → backend → SSE → back to this wrapper, and we need to drop
        the SSE echo so the same content isn't typed into Claude twice.

        UI-originated messages do NOT echo — SSE delivery IS the original
        send path, not a round-trip. Tracking them poisons the 60s window
        for legitimate later UI sends of the same content (e.g., the user
        clicking "No" on a second permission prompt within a minute of
        the first), which then get silently suppressed as fake "echoes".

        Args:
            content: Message content
            from_web: Whether message came from web UI
        """
        if from_web:
            return
        self.track(content)

    def size(self) -> int:
        """Get the number of tracked messages.

        Returns:
            Number of tracked messages
        """
        return len(self._tracked_messages)

    def __len__(self) -> int:
        """Get the number of tracked messages (same as size()).

        Returns:
            Number of tracked messages
        """
        return len(self._tracked_messages)

    def __contains__(self, content: str) -> bool:
        """Check if content is a recent duplicate (allows 'in' operator).

        Routes through ``is_duplicate`` so the time-bounded semantics apply
        consistently regardless of which API a caller uses.

        Args:
            content: Message content to check

        Returns:
            True if a recent duplicate, False otherwise
        """
        return self.is_duplicate(content)

    def _normalize(self, content: str) -> str:
        """Normalize content for fuzzy deduplication."""
        return " ".join(content.split()).strip()

    def _trim_recent(self) -> None:
        """Trim old recent messages outside the deduplication window."""
        cutoff = time.time() - self._recent_window_seconds
        while self._recent_messages and self._recent_messages[0][0] < cutoff:
            self._recent_messages.popleft()
