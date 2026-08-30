"""ANSI escape sequence cleaning utilities.

This module provides utilities for removing ANSI escape sequences and control
characters from terminal output. Claude CLI uses various ANSI codes for formatting,
cursor control, and other terminal features that need to be stripped for parsing.
"""

import re


class ANSICleaner:
    """Utility class for cleaning ANSI escape sequences from terminal output.

    This class provides methods to remove various types of ANSI escape sequences:
    - CSI (Control Sequence Introducer) sequences: ESC [ ... letter
    - OSC (Operating System Command) sequences: ESC ] ... BEL/ST
    - Other escape sequences
    - Bracketed paste mode markers
    - Cursor visibility sequences
    - Synchronized output sequences
    """

    # Precompiled regex patterns for performance
    # CSI pattern: ESC [ [params] [intermediate] final
    # - params: 0-9 ; < = > ?
    # - intermediate (optional): space ! " # $ % & ' ( ) * +
    # - final: @ A-Z [ \ ] ^ _ ` a-z { | } ~ (0x40-0x7E)
    CSI_PATTERN = re.compile(r"\x1b\[[0-9;?<=>]*[ -/]*[@-~]")
    OSC_PATTERN = re.compile(r"\x1b\].*?(\x07|\x1b\\)")
    OTHER_ESC_PATTERN = re.compile(r"\x1b[=>\[\]PI]")
    BRACKETED_PASTE_PATTERN = re.compile(r"\x1b\[\?2004[hl]")
    CURSOR_VISIBILITY_PATTERN = re.compile(r"\x1b\[\?25[hl]")
    SYNCHRONIZED_OUTPUT_PATTERN = re.compile(r"\x1b\[\?2026[hl]")

    # Combined pattern for single-pass cleaning (performance optimization)
    # This pattern matches all ANSI sequences in one regex operation
    ALL_ANSI_PATTERN = re.compile(
        r"\x1b\[[0-9;?<=>]*[ -/]*[@-~]|"  # CSI sequences (full spec)
        r"\x1b\].*?(?:\x07|\x1b\\)|"  # OSC sequences
        r"\x1b[=>\[\]PI]|"  # Other ESC sequences
        r"\x1b\[\?2004[hl]|"  # Bracketed paste mode
        r"\x1b\[\?25[hl]|"  # Cursor visibility
        r"\x1b\[\?2026[hl]"  # Synchronized output
    )

    @classmethod
    def clean_csi_sequences(cls, text: str) -> str:
        """Remove CSI (Control Sequence Introducer) sequences.

        CSI sequences start with ESC [ and end with a letter.
        Examples: cursor movement, colors, text formatting

        Args:
            text: Input text with ANSI sequences

        Returns:
            Text with CSI sequences removed
        """
        return cls.CSI_PATTERN.sub("", text)

    @classmethod
    def clean_osc_sequences(cls, text: str) -> str:
        """Remove OSC (Operating System Command) sequences.

        OSC sequences start with ESC ] and end with BEL or ST.
        Examples: window title, color palette

        Args:
            text: Input text with ANSI sequences

        Returns:
            Text with OSC sequences removed
        """
        return cls.OSC_PATTERN.sub("", text)

    @classmethod
    def clean_other_escape_sequences(cls, text: str) -> str:
        """Remove other escape sequences.

        Args:
            text: Input text with ANSI sequences

        Returns:
            Text with other escape sequences removed
        """
        return cls.OTHER_ESC_PATTERN.sub("", text)

    @classmethod
    def clean_bracketed_paste(cls, text: str) -> str:
        """Remove bracketed paste mode markers.

        Args:
            text: Input text with ANSI sequences

        Returns:
            Text with bracketed paste markers removed
        """
        return cls.BRACKETED_PASTE_PATTERN.sub("", text)

    @classmethod
    def clean_cursor_visibility(cls, text: str) -> str:
        """Remove cursor visibility sequences.

        Args:
            text: Input text with ANSI sequences

        Returns:
            Text with cursor visibility sequences removed
        """
        return cls.CURSOR_VISIBILITY_PATTERN.sub("", text)

    @classmethod
    def clean_synchronized_output(cls, text: str) -> str:
        """Remove synchronized output sequences.

        Args:
            text: Input text with ANSI sequences

        Returns:
            Text with synchronized output sequences removed
        """
        return cls.SYNCHRONIZED_OUTPUT_PATTERN.sub("", text)

    @classmethod
    def clean_all(cls, text: str) -> str:
        """Remove all ANSI escape sequences and control characters.

        This uses a single-pass regex operation for optimal performance.
        The combined pattern matches all ANSI sequence types in one pass,
        which is significantly faster than multiple sequential operations.

        Args:
            text: Input text with ANSI sequences

        Returns:
            Text with all ANSI sequences removed
        """
        # First, replace cursor forward sequences with spaces
        # Claude CLI uses cursor forward (\x1b[1C, \x1b[2C, etc.) to create visual spacing
        # without actual space characters. We need to convert these to spaces.
        import re

        cursor_forward_pattern = re.compile(r"\x1b\[(\d*)C")

        def replace_cursor_forward(match):
            # Get the number of positions to move (default 1)
            count_str = match.group(1)
            count = int(count_str) if count_str else 1
            return " " * count

        text = cursor_forward_pattern.sub(replace_cursor_forward, text)

        # Then use optimized single-pass pattern to remove remaining ANSI sequences
        return cls.ALL_ANSI_PATTERN.sub("", text)

    @classmethod
    def clean_for_parsing(cls, text: str) -> str:
        """Clean text specifically for parsing (alias for clean_all).

        Args:
            text: Input text with ANSI sequences

        Returns:
            Text cleaned and ready for parsing
        """
        return cls.clean_all(text)
