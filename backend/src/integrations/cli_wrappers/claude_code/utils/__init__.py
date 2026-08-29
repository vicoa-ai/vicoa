"""Utility functions for Claude Code Wrapper.

This module contains utility functions for:
- Finding Claude CLI binary
- Handling user input
- Detecting Claude CLI version
"""

from .cli_finder import find_claude_cli
from .input_handler import InputHandler
from .version_detector import (
    get_claude_version,
    should_use_legacy_wrapper,
    get_version_string,
)

__all__ = [
    "find_claude_cli",
    "InputHandler",
    "get_claude_version",
    "should_use_legacy_wrapper",
    "get_version_string",
]
