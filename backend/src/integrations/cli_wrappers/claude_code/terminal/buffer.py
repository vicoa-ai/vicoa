"""Terminal buffer management.

This module provides a TerminalBuffer class for managing terminal output.
The buffer has a maximum size and automatically truncates old content when full.
"""

from typing import Optional


class TerminalBuffer:
    """Manages terminal output with automatic size limiting.

    The buffer stores terminal output and automatically truncates from the beginning
    when it exceeds the maximum size. This prevents unbounded memory growth while
    keeping recent output for analysis.
    """

    def __init__(self, max_size: int = 200000):
        """Initialize terminal buffer.

        Args:
            max_size: Maximum buffer size in bytes (default: 200KB)
        """
        if max_size <= 0:
            raise ValueError("max_size must be positive")

        self._buffer = ""
        self._max_size = max_size

    def append(self, text: str) -> None:
        """Append text to the buffer.

        If adding the text would exceed max_size, old content from the
        beginning is removed to make room.

        Args:
            text: Text to append to buffer
        """
        self._buffer += text

        # Truncate from beginning if buffer exceeds max size
        if len(self._buffer) > self._max_size:
            # Keep only the last max_size bytes
            self._buffer = self._buffer[-self._max_size :]

    def get(self) -> str:
        """Get the current buffer contents.

        Returns:
            Current buffer contents as a string
        """
        return self._buffer

    def clear(self) -> None:
        """Clear the buffer completely."""
        self._buffer = ""

    def search(self, pattern: str, case_sensitive: bool = True) -> bool:
        """Search for a pattern in the buffer.

        Args:
            pattern: String pattern to search for
            case_sensitive: Whether search should be case-sensitive (default: True)

        Returns:
            True if pattern is found, False otherwise
        """
        if case_sensitive:
            return pattern in self._buffer
        else:
            return pattern.lower() in self._buffer.lower()

    def find_last_occurrence(self, pattern: str) -> Optional[int]:
        """Find the last occurrence of a pattern in the buffer.

        Args:
            pattern: String pattern to search for

        Returns:
            Index of last occurrence, or None if not found
        """
        index = self._buffer.rfind(pattern)
        return index if index != -1 else None

    def get_last_n_chars(self, n: int) -> str:
        """Get the last N characters from the buffer.

        Args:
            n: Number of characters to retrieve

        Returns:
            Last N characters (or entire buffer if buffer is smaller)
        """
        if n <= 0:
            return ""
        return self._buffer[-n:]

    def size(self) -> int:
        """Get the current size of the buffer in bytes.

        Returns:
            Current buffer size in bytes
        """
        return len(self._buffer)

    def __len__(self) -> int:
        """Get the current size of the buffer (same as size()).

        Returns:
            Current buffer size in bytes
        """
        return len(self._buffer)

    def __str__(self) -> str:
        """String representation of buffer contents.

        Returns:
            Current buffer contents
        """
        return self._buffer

    def __repr__(self) -> str:
        """Detailed representation for debugging.

        Returns:
            Debug representation showing buffer size and max size
        """
        return f"TerminalBuffer(size={len(self._buffer)}, max_size={self._max_size})"
