"""Session state management for Claude Code Wrapper.

This module tracks session-level state including idle detection,
resume handling, and permission prompt state.
"""

import time
from typing import Optional


class SessionState:
    """Manages session-level state for the wrapper.

    This includes:
    - Idle detection and tracking
    - Resume state
    - Permission prompt tracking
    - Interrupt detection
    """

    def __init__(
        self,
        is_resuming: bool = False,
        idle_delay: float = 3.5,
        terminal_buffer=None,  # TerminalBuffer
    ):
        """Initialize session state.

        Args:
            is_resuming: Whether this is a resumed session
            idle_delay: Seconds of inactivity before considering Claude idle
            terminal_buffer: Terminal buffer for checking current state
        """
        self.is_resuming = is_resuming
        self.idle_delay = idle_delay
        self.terminal_buffer = terminal_buffer

        # Idle tracking
        self._last_esc_interrupt_seen: Optional[float] = None
        self._last_terminal_activity: Optional[float] = None

        # Permission tracking (for permission assumed time)
        self._permission_assumed_time: Optional[float] = None
        self._permission_handled: bool = False

        # Pending permission options (map option text to number)
        self.pending_permission_options: dict[str, str] = {}

        # Requested input tracking (to avoid duplicate requests)
        self.requested_input_messages: set[str] = set()

        # Last prompt signature to avoid repeated sends
        self.last_prompt_signature: Optional[str] = None
        self.last_prompt_time: Optional[float] = None
        self.last_prompt_type: Optional[str] = None

    def mark_interrupt(self) -> None:
        """Mark that an interrupt (Esc) was seen."""
        self._last_esc_interrupt_seen = time.time()

    def mark_terminal_activity(self) -> None:
        """Mark that terminal activity (any output) was seen."""
        self._last_terminal_activity = time.time()

    def get_time_since_terminal_activity(self) -> Optional[float]:
        """Get seconds since last terminal activity.

        Returns:
            Seconds since last activity, or None if no activity seen
        """
        if self._last_terminal_activity is None:
            return None
        return time.time() - self._last_terminal_activity

    def get_time_since_interrupt(self) -> Optional[float]:
        """Get seconds since last interrupt.

        Returns:
            Seconds since last interrupt, or None if no interrupt seen
        """
        if self._last_esc_interrupt_seen is None:
            return None
        return time.time() - self._last_esc_interrupt_seen

    def is_claude_idle(self) -> bool:
        """Check if Claude is idle (not showing 'esc to interrupt' and no recent activity).

        This checks THREE things:
        1. Recent terminal activity (any output in last 1.5 seconds = busy)
        2. The terminal buffer for current presence of "esc to interrupt"
        3. Time-based check as a fallback

        Returns:
            True if Claude is idle, False otherwise
        """
        # FIRST: Check for recent terminal activity (ANY output)
        # If terminal is actively changing, Claude is not idle
        time_since_activity = self.get_time_since_terminal_activity()
        if time_since_activity is not None and time_since_activity < 1.5:
            return False  # Claude is BUSY - terminal was active recently

        # SECOND: Check if "esc to interrupt" is currently in the terminal buffer
        # This handles cases where the status line updates in-place and we only
        # detected it once at the beginning
        if self.terminal_buffer:
            # Check the last 2000 chars of buffer (enough to catch status line)
            recent_output = self.terminal_buffer.get_last_n_chars(2000).lower()
            if "esc to interrupt" in recent_output:
                return False  # Claude is BUSY - status line is currently showing

        # THIRD: Fallback to time-based check
        time_since = self.get_time_since_interrupt()
        if time_since is None:
            # No "esc to interrupt" seen yet - Claude is idle (waiting for input)
            return True

        return time_since >= self.idle_delay

    def is_claude_busy(self) -> bool:
        """Check if Claude is busy (opposite of idle).

        Returns:
            True if Claude is busy, False otherwise
        """
        return not self.is_claude_idle()

    def start_permission_assumption(self) -> None:
        """Mark that we're starting to assume a permission prompt."""
        self._permission_assumed_time = time.time()
        self._permission_handled = False

    def get_permission_assumption_time(self) -> Optional[float]:
        """Get seconds since permission assumption started.

        Returns:
            Seconds since assumption started, or None if not started
        """
        if self._permission_assumed_time is None:
            return None
        return time.time() - self._permission_assumed_time

    def is_permission_handled(self) -> bool:
        """Check if permission has been handled.

        Returns:
            True if handled, False otherwise
        """
        return self._permission_handled

    def mark_permission_handled(self) -> None:
        """Mark that permission prompt has been handled."""
        self._permission_handled = True

    def reset_permission_tracking(self) -> None:
        """Reset permission tracking state."""
        self._permission_assumed_time = None
        self._permission_handled = False

    def clear_pending_permission_options(self) -> None:
        """Clear pending permission options."""
        self.pending_permission_options.clear()

    def set_pending_permission_options(self, options_map: dict[str, str]) -> None:
        """Set pending permission options.

        Args:
            options_map: Map of option text to option number
        """
        self.pending_permission_options.clear()
        self.pending_permission_options.update(options_map)

    def clear_requested_input_messages(self) -> None:
        """Clear requested input messages tracking."""
        self.requested_input_messages.clear()

    def should_send_prompt(self, signature: str) -> bool:
        """Check if a prompt signature should be sent."""
        return self.last_prompt_signature != signature

    def mark_prompt_sent(self, signature: str) -> None:
        """Mark a prompt signature as sent."""
        self.last_prompt_signature = signature

    def clear_prompt_signature(self) -> None:
        """Clear the last prompt signature."""
        self.last_prompt_signature = None

    def mark_prompt_detected(self, prompt_type: str) -> None:
        """Mark that a prompt was detected and sent."""
        self.last_prompt_time = time.time()
        self.last_prompt_type = prompt_type

    def get_time_since_prompt(self) -> Optional[float]:
        """Get seconds since last prompt was detected."""
        if self.last_prompt_time is None:
            return None
        return time.time() - self.last_prompt_time

    def clear_prompt_timing(self) -> None:
        """Clear prompt timing metadata."""
        self.last_prompt_time = None
        self.last_prompt_type = None

    def add_requested_input_message(self, message_id: str) -> None:
        """Add a message ID to requested input tracking.

        Args:
            message_id: Message ID to track
        """
        self.requested_input_messages.add(message_id)

    def has_requested_input_for(self, message_id: str) -> bool:
        """Check if we've already requested input for a message.

        Args:
            message_id: Message ID to check

        Returns:
            True if already requested, False otherwise
        """
        return message_id in self.requested_input_messages

    def __repr__(self) -> str:
        """Get debug representation of session state.

        Returns:
            String representation
        """
        return (
            f"SessionState("
            f"is_resuming={self.is_resuming}, "
            f"idle={self.is_claude_idle()}, "
            f"permission_handled={self._permission_handled})"
        )
