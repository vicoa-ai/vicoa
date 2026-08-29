"""State module for Claude Code Wrapper.

This module handles state management including:
- Toggle state (permission mode, thinking)
- Session state (idle tracking, resume handling)
"""

from .session_state import SessionState
from .toggle_manager import ToggleManager

__all__ = [
    "SessionState",
    "ToggleManager",
]
