"""Base terminal output parser.

This module provides a base class for parsing terminal output.
Specific detectors can inherit from this class to implement
specialized parsing logic.
"""

from abc import ABC, abstractmethod
from typing import List, Optional


class TerminalParser(ABC):
    """Abstract base class for terminal output parsers.

    Provides common utilities for parsing terminal output line-by-line
    or as a whole buffer. Specific parsers should inherit from this class
    and implement the abstract methods.
    """

    @abstractmethod
    def parse(self, text: str) -> Optional[dict]:
        """Parse text and return structured data.

        Args:
            text: Cleaned terminal output text

        Returns:
            Parsed data as a dictionary, or None if parsing fails
        """
        pass

    def parse_lines(self, lines: List[str]) -> Optional[dict]:
        """Parse a list of lines.

        Default implementation joins lines and calls parse().
        Subclasses can override for more efficient line-by-line parsing.

        Args:
            lines: List of text lines

        Returns:
            Parsed data as a dictionary, or None if parsing fails
        """
        text = "\n".join(lines)
        return self.parse(text)

    @staticmethod
    def extract_lines(
        text: str, start_marker: str, end_marker: Optional[str] = None
    ) -> List[str]:
        """Extract lines between start and end markers.

        Args:
            text: Input text
            start_marker: Starting marker text
            end_marker: Ending marker text (optional, if None extracts to end)

        Returns:
            List of lines between markers
        """
        lines = text.split("\n")
        result = []
        started = False

        for line in lines:
            if start_marker in line:
                started = True
                continue

            if started:
                if end_marker and end_marker in line:
                    break
                result.append(line)

        return result

    @staticmethod
    def find_line_with_pattern(lines: List[str], pattern: str) -> Optional[str]:
        """Find the first line containing a pattern.

        Args:
            lines: List of lines to search
            pattern: Pattern to search for

        Returns:
            First matching line, or None if not found
        """
        for line in lines:
            if pattern in line:
                return line
        return None

    @staticmethod
    def extract_numbered_options(text: str) -> List[str]:
        """Extract numbered options from text (1. option1, 2. option2, etc.).

        Args:
            text: Text containing numbered options

        Returns:
            List of option strings (without numbers)
        """
        import re

        lines = text.split("\n")
        options = []

        # Match lines starting with number followed by period or closing paren
        number_pattern = re.compile(r"^\s*(\d+)[\.)]\s+(.+)")

        for line in lines:
            match = number_pattern.match(line.strip())
            if match:
                option_text = match.group(2).strip()
                if option_text:
                    options.append(option_text)

        return options

    @staticmethod
    def clean_whitespace(text: str) -> str:
        """Clean excessive whitespace from text.

        Args:
            text: Input text

        Returns:
            Text with cleaned whitespace
        """
        # Replace multiple spaces with single space
        import re

        text = re.sub(r" {2,}", " ", text)
        # Remove leading/trailing whitespace from each line
        lines = [line.strip() for line in text.split("\n")]
        # Remove empty lines
        lines = [line for line in lines if line]
        return "\n".join(lines)
