"""Input handling utilities for Claude CLI interaction.

This module provides utilities for processing stdin input and
handling special cases like backspace.
"""


class InputHandler:
    """Handles user input from stdin.

    Responsibilities:
    - Processing stdin input character by character
    - Line buffering
    - Backspace handling
    - Special character handling
    """

    def __init__(self):
        """Initialize input handler."""
        self.line_buffer = ""
        self._in_escape = False
        self._escape_buffer = ""

    def process_char(self, char: bytes) -> str:
        """Process a single character from stdin.

        Args:
            char: Character bytes

        Returns:
            Complete line if Enter was pressed, empty string otherwise
        """
        try:
            # Decode the character
            char_str = char.decode("utf-8", errors="ignore")

            # Ignore ANSI escape sequences (arrow keys, etc.)
            if self._in_escape:
                self._escape_buffer += char_str
                if char_str.isalpha() or char_str in "~":
                    self._in_escape = False
                    self._escape_buffer = ""
                return ""

            if char == b"\x1b":  # ESC
                self._in_escape = True
                self._escape_buffer = char_str
                return ""

            # Handle Enter (newline)
            if char_str in ("\n", "\r"):
                line = self.line_buffer
                self.line_buffer = ""
                return line

            # Handle backspace
            if char in (b"\x7f", b"\x08"):  # DEL or BS
                if self.line_buffer:
                    self.line_buffer = self.line_buffer[:-1]
                return ""

            # Add to buffer
            self.line_buffer += char_str
            return ""

        except Exception:
            return ""

    def clear_buffer(self) -> None:
        """Clear the line buffer."""
        self.line_buffer = ""

    def get_buffer(self) -> str:
        """Get current buffer contents.

        Returns:
            Current buffer
        """
        return self.line_buffer
