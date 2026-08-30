"""Message queue management.

This module provides a queue for managing pending messages from
the web UI that need to be sent to Claude CLI.
"""

from collections import deque
from typing import Optional


class MessageQueue:
    """Queue for managing pending messages.

    This queue stores messages from the web UI that are waiting
    to be sent to Claude CLI through the PTY.
    """

    def __init__(self):
        """Initialize the message queue."""
        self._queue: deque[str] = deque()

    def append(self, message: str) -> None:
        """Add a message to the end of the queue.

        Args:
            message: Message content to add
        """
        self._queue.append(message)

    def appendleft(self, message: str) -> None:
        """Add a message to the beginning of the queue (high priority).

        Args:
            message: Message content to add
        """
        self._queue.appendleft(message)

    def popleft(self) -> str:
        """Remove and return the first message from the queue.

        Returns:
            First message in the queue

        Raises:
            IndexError: If queue is empty
        """
        return self._queue.popleft()

    def peek(self) -> Optional[str]:
        """Get the first message without removing it.

        Returns:
            First message in the queue, or None if empty
        """
        if self._queue:
            return self._queue[0]
        return None

    def clear(self) -> None:
        """Clear all messages from the queue."""
        self._queue.clear()

    def is_empty(self) -> bool:
        """Check if the queue is empty.

        Returns:
            True if queue is empty, False otherwise
        """
        return len(self._queue) == 0

    def size(self) -> int:
        """Get the number of messages in the queue.

        Returns:
            Number of messages
        """
        return len(self._queue)

    def __len__(self) -> int:
        """Get the number of messages in the queue (same as size()).

        Returns:
            Number of messages
        """
        return len(self._queue)

    def __bool__(self) -> bool:
        """Check if queue has messages (allows truthiness check).

        Returns:
            True if queue has messages, False if empty
        """
        return len(self._queue) > 0

    def __repr__(self) -> str:
        """Get a debug representation of the queue.

        Returns:
            String representation showing queue size
        """
        return f"MessageQueue(size={len(self._queue)})"
