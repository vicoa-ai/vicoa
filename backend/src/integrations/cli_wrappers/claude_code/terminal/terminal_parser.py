"""Terminal buffer parser that simulates terminal rendering.

This module provides a parser that processes terminal escape sequences
and cursor movements to produce the actual rendered text as it would
appear on a real terminal.
"""

import re
from typing import List


class TerminalRenderer:
    """Renders terminal buffer by simulating cursor movements and overwrites.

    This parser handles:
    - Cursor positioning (forward, backward, up, down, absolute)
    - Character insertion and deletion
    - Line clearing
    - Proper overwriting of characters when cursor moves back
    """

    def __init__(self):
        """Initialize terminal renderer."""
        self.lines: List[List[str]] = [[]]  # List of lines, each line is list of chars
        self.cursor_row = 0
        self.cursor_col = 0

    def render(self, text: str) -> str:
        """Render terminal buffer text with escape sequences.

        Args:
            text: Raw terminal text with escape sequences

        Returns:
            Rendered text as it would appear on screen
        """
        self.lines = [[]]
        self.cursor_row = 0
        self.cursor_col = 0

        i = 0
        while i < len(text):
            if text[i] == "\x1b":
                # Escape sequence
                seq_len = self._process_escape_sequence(text[i:])
                i += seq_len
            elif text[i] == "\r":
                # Carriage return - move to start of line
                self.cursor_col = 0
                i += 1
            elif text[i] == "\n":
                # Newline - move to next line
                self.cursor_row += 1
                self.cursor_col = 0
                # Ensure line exists
                while len(self.lines) <= self.cursor_row:
                    self.lines.append([])
                i += 1
            elif text[i] == "\b":
                # Backspace
                if self.cursor_col > 0:
                    self.cursor_col -= 1
                i += 1
            else:
                # Regular character - write at cursor position
                self._write_char(text[i])
                i += 1

        # Convert lines to string
        return "\n".join("".join(line).rstrip() for line in self.lines)

    def _write_char(self, char: str) -> None:
        """Write a character at the current cursor position."""
        # Ensure line exists
        while len(self.lines) <= self.cursor_row:
            self.lines.append([])

        line = self.lines[self.cursor_row]

        # Ensure line is long enough
        while len(line) <= self.cursor_col:
            line.append(" ")

        # Write character (overwrites existing)
        line[self.cursor_col] = char
        self.cursor_col += 1

    def _process_escape_sequence(self, text: str) -> int:
        """Process an escape sequence and return its length.

        Args:
            text: Text starting with escape character

        Returns:
            Number of characters consumed
        """
        if len(text) < 2:
            return 1

        if text[1] == "[":
            # CSI sequence
            return self._process_csi_sequence(text)
        elif text[1] == "]":
            # OSC sequence - find terminator
            match = re.match(r"\x1b\].*?(\x07|\x1b\\)", text)
            return len(match.group(0)) if match else 2
        else:
            # Other escape sequence - skip 2 chars
            return 2

    def _process_csi_sequence(self, text: str) -> int:
        """Process a CSI escape sequence.

        Args:
            text: Text starting with ESC[

        Returns:
            Number of characters consumed
        """
        # Match CSI pattern: ESC [ [params] [intermediate] final
        match = re.match(r"\x1b\[[0-9;?<=>]*[ -/]*[@-~]", text)
        if not match:
            return 2

        seq = match.group(0)
        final_char = seq[-1]
        params_str = seq[2:-1]

        # Parse parameters
        params = []
        if params_str and params_str[0] not in "?<=>":
            try:
                params = [int(p) if p else 1 for p in params_str.split(";")]
            except ValueError:
                params = []

        # Handle different CSI sequences
        if final_char == "C":
            # Cursor Forward
            count = params[0] if params else 1
            self.cursor_col += count
        elif final_char == "D":
            # Cursor Backward
            count = params[0] if params else 1
            self.cursor_col = max(0, self.cursor_col - count)
        elif final_char == "A":
            # Cursor Up
            count = params[0] if params else 1
            self.cursor_row = max(0, self.cursor_row - count)
        elif final_char == "B":
            # Cursor Down
            count = params[0] if params else 1
            self.cursor_row += count
        elif final_char == "G":
            # Cursor Horizontal Absolute
            col = params[0] - 1 if params else 0
            self.cursor_col = max(0, col)
        elif final_char == "H" or final_char == "f":
            # Cursor Position
            row = (params[0] - 1) if params else 0
            col = (params[1] - 1) if len(params) > 1 else 0
            self.cursor_row = max(0, row)
            self.cursor_col = max(0, col)
        elif final_char == "J":
            # Erase in Display
            self._erase_display(params[0] if params else 0)
        elif final_char == "K":
            # Erase in Line
            self._erase_line(params[0] if params else 0)
        elif final_char == "P":
            # Delete Character
            count = params[0] if params else 1
            self._delete_chars(count)
        elif final_char == "X":
            # Erase Character
            count = params[0] if params else 1
            self._erase_chars(count)
        elif final_char == "@":
            # Insert Character (insert spaces)
            count = params[0] if params else 1
            self._insert_chars(count)
        # Ignore other sequences (colors, etc.)

        return len(seq)

    def _erase_display(self, mode: int) -> None:
        """Erase in display."""
        if mode == 2:
            # Clear entire display
            self.lines = [[]]
            self.cursor_row = 0
            self.cursor_col = 0

    def _erase_line(self, mode: int) -> None:
        """Erase in line."""
        while len(self.lines) <= self.cursor_row:
            self.lines.append([])

        line = self.lines[self.cursor_row]

        if mode == 0:
            # Erase from cursor to end of line
            line[self.cursor_col :] = []
        elif mode == 1:
            # Erase from start of line to cursor
            for i in range(min(self.cursor_col + 1, len(line))):
                line[i] = " "
        elif mode == 2:
            # Erase entire line
            line.clear()

    def _delete_chars(self, count: int) -> None:
        """Delete characters at cursor position."""
        while len(self.lines) <= self.cursor_row:
            self.lines.append([])

        line = self.lines[self.cursor_row]

        # Delete characters by removing them from the line
        end_pos = min(self.cursor_col + count, len(line))
        del line[self.cursor_col : end_pos]

    def _erase_chars(self, count: int) -> None:
        """Erase characters at cursor position (replace with spaces)."""
        while len(self.lines) <= self.cursor_row:
            self.lines.append([])

        line = self.lines[self.cursor_row]

        # Ensure line is long enough
        while len(line) < self.cursor_col + count:
            line.append(" ")

        # Replace characters with spaces
        for i in range(count):
            if self.cursor_col + i < len(line):
                line[self.cursor_col + i] = " "

    def _insert_chars(self, count: int) -> None:
        """Insert blank characters at cursor position."""
        while len(self.lines) <= self.cursor_row:
            self.lines.append([])

        line = self.lines[self.cursor_row]

        # Insert spaces
        for _ in range(count):
            line.insert(self.cursor_col, " ")
