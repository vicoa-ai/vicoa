"""Message processing logic for Claude Code Wrapper.

This module handles processing of messages flowing between Claude CLI
and Vicoa servers, including sanitization and state tracking.
"""

import time
from typing import Any, Callable, List, Optional, TYPE_CHECKING

from .deduplicator import MessageDeduplicator
from .injection_tracker import InjectionTracker

if TYPE_CHECKING:
    from vicoa.sdk.client import VicoaClient


class MessageProcessor:
    """Processes messages between Claude CLI and Vicoa servers.

    This class handles:
    - User message processing (from CLI or web)
    - Assistant message processing (from Claude CLI)
    - Message deduplication
    - Idle state tracking
    - Input request state
    """

    def __init__(
        self,
        agent_instance_id: Optional[str],
        agent_name: str,
        vicoa_client: Optional["VicoaClient"],
        log_func: Callable[[str], None],
    ):
        """Initialize message processor.

        Args:
            agent_instance_id: Agent instance ID for Vicoa
            agent_name: Agent display name
            vicoa_client: Vicoa SDK client (sync)
            log_func: Logging function
        """
        self.agent_instance_id = agent_instance_id
        self.agent_name = agent_name
        self.vicoa_client = vicoa_client
        self.log = log_func

        # State tracking
        self.last_message_id: Optional[str] = None
        self.last_message_time: Optional[float] = None
        self.pending_input_message_id: Optional[str] = None
        self.last_was_tool_use = False
        self.suppress_cli_user_echo_until: float = 0.0

        # Track recent tool context for permission prompts
        self.last_tool_context: Optional[str] = None

        # Deduplication
        self.deduplicator = MessageDeduplicator()

        # UI→Claude→JSONL echo suppression. Each UI injection enqueues one
        # slot; the JSONL monitor consumes a slot per echo. Independent of the
        # TUI→SSE deduplicator above.
        self.injection_tracker = InjectionTracker()

        # Requested input tracking (to avoid duplicate requests)
        self.requested_input_messages: set[str] = set()

        # Debouncing for input requests
        self.last_input_request_time: Optional[float] = None
        self.minimum_idle_time: float = 1.0  # seconds before considering "truly idle"
        self.min_request_interval: float = 5.0  # minimum time between input requests

    def process_user_message(
        self,
        content: str,
        from_web: bool,
        input_queue,  # MessageQueue
    ) -> None:
        """Process a user message (sync version for monitor thread).

        Args:
            content: Message content
            from_web: Whether message came from web UI
            input_queue: Message queue for queuing web messages to CLI
        """
        if from_web:
            # Message from web UI - track it to avoid duplicate sends
            self.deduplicator.track(content)
        else:
            # First, check if this JSONL line is an echo of a UI message we
            # just injected into Claude. If so, the message already exists in
            # the DB (the UI POST created it) and we must not write a second
            # copy via send_user_message.
            if self.injection_tracker.try_consume_echo(content):
                self.log(
                    f"[DEBUG] UI echo suppressed (JSONL transcription): {content[:80]!r}"
                )
            # Plain TUI input — always post. The MessageDeduplicator's
            # `is_duplicate` / `is_near_duplicate` checks used to live here as
            # a safety net for two cases:
            #   (a) double-posting if a WS echo somehow re-entered this code
            #       path with from_web=False — never observed, and now
            #       structurally impossible since the WS path goes through
            #       _handle_user_message which has its own is_duplicate check
            #       on the receive side.
            #   (b) Claude transcribing user input with a slight transformation
            #       (e.g., prefix/suffix decoration) so the jsonl line is
            #       near-but-not-exactly the original — `is_near_duplicate`'s
            #       fuzzy startswith/endswith with 5+ char delta would catch
            #       this. We've never observed Claude doing this for plain
            #       user input; it transcribes verbatim. injection_tracker
            #       (above) already handles the only well-known transformation
            #       path (UI inject → PTY → jsonl).
            # The checks broke a real, observed case: typing 'Hi' twice in
            # quick succession (session 6837b5b8) — second silently dropped.
            # If either guard turns out to matter in practice, the right fix
            # is a targeted check (FIFO consume-once like injection_tracker),
            # NOT restoring set-based dedup here.
            elif self.agent_instance_id and self.vicoa_client:
                try:
                    # Track BEFORE the HTTP call so the SSE/WS echo (which
                    # can arrive while send_user_message() is still
                    # blocking) is recognized as a duplicate at the
                    # receive side and does not re-queue into Claude.
                    self.deduplicator.track(content)
                    self.vicoa_client.send_user_message(
                        agent_instance_id=self.agent_instance_id,
                        content=content,
                    )
                except Exception as e:
                    self.deduplicator.remove(content)  # undo tracking on failure
                    self.log(f"[ERROR] Failed to send CLI message to Vicoa: {e}")
                    import traceback

                    self.log(traceback.format_exc())
            else:
                self.log(
                    f"[WARNING] Cannot send CLI message: agent_instance_id={self.agent_instance_id}, vicoa_client={self.vicoa_client}"
                )

            # When user sends a message, we need to:
            # 1. Clear pending_input_message_id to stop any waiting input request
            # 2. Clear last_message_id so we don't request input for old messages
            # NOTE: We do NOT update last_message_time - that only tracks Claude's output
            # This prevents idle detection from using stale timestamps
            self.pending_input_message_id = None
            self.last_message_id = None

    def send_cli_command_echo(self, content: str) -> None:
        """Forward a TUI slash-command / local-command-stdout entry as an AGENT
        message.

        TUI artifacts (e.g. the user typing `/model`, and Claude's
        `<local-command-stdout>Set model to Opus 4.8 (1M context)`
        confirmation) appear in the JSONL as `user` entries but are not real
        chat input — they're terminal state changes. Routing them through
        ``send_message`` (sender_type=AGENT) keeps them visible in the
        timeline as system notes without triggering the user-message side
        effects we don't want for these:

        - Title generation (which would derive titles like "Set model to
          Opus 4.8 (1M context)" from the first session message).
        - Dispatch into Claude's stdin via the queued-input loop.
        - Dedup tracking (these are not user prompts that can be echoed
          back from the UI side).
        """
        if not self.agent_instance_id or not self.vicoa_client:
            return
        try:
            self.vicoa_client.send_message(
                content=content,
                agent_type=self.agent_name,
                agent_instance_id=self.agent_instance_id,
                requires_user_input=False,
            )
        except Exception as e:
            self.log(f"[ERROR] Failed to send CLI command echo to Vicoa: {e}")

    def process_assistant_message(
        self,
        content: str,
        tools_used: List[str],
        send_message_lock,  # threading.Lock
        requested_input_messages: set,
        pending_permission_options: dict,
        requires_user_input: bool = False,
        message_metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[List[str]]:
        """Process an assistant message (sync version for monitor thread).

        Args:
            content: Message content
            tools_used: List of tools used in this message
            send_message_lock: Lock for thread-safe message sending
            requested_input_messages: Set of messages we've requested input for
            pending_permission_options: Dict of pending permission options

        Returns:
            List of queued user messages, or None
        """
        if not self.agent_instance_id or not self.vicoa_client:
            return None

        # Use lock to ensure atomic message processing
        with send_message_lock:
            # Track if this message uses tools
            self.last_was_tool_use = bool(tools_used)

            # Store tool context for permission prompts
            # Only keep the most recent tool use (permission prompts typically follow immediately)
            if tools_used:
                self.last_tool_context = tools_used[-1]  # Most recent tool

            # Sanitize content - remove NUL and control characters
            sanitized_content = self._sanitize_content(content)

            # Send to Vicoa
            response = self.vicoa_client.send_message(
                content=sanitized_content,
                agent_type=self.agent_name,
                agent_instance_id=self.agent_instance_id,
                requires_user_input=requires_user_input,
                message_metadata=message_metadata,
            )

            # Track message for idle detection
            self.last_message_id = response.message_id
            self.last_message_time = time.time()
            if requires_user_input:
                self.pending_input_message_id = response.message_id

            # Clear old tracked input requests since we have a new message
            requested_input_messages.clear()

            # Clear pending permission options since we have a new message
            pending_permission_options.clear()

            # Return queued user messages if any
            if response.queued_user_messages:
                return response.queued_user_messages

            return None

    def should_request_input(
        self, is_claude_idle_func: Callable[[], bool]
    ) -> Optional[str]:
        """Check if we should request input.

        Args:
            is_claude_idle_func: Function that returns True if Claude is idle

        Returns:
            Message ID to request input for, or None
        """
        # FIRST: Check if Claude appears idle (showing "esc to interrupt")
        # This blocks notifications while Claude is actively processing
        is_idle = is_claude_idle_func()
        if not is_idle:
            return None

        # Don't request input if we might have a permission prompt
        # (only applies if Claude is idle, which we've already confirmed above)
        if self.last_was_tool_use:
            # We're in a state where a permission prompt might appear
            return None

        # Basic requirements
        if (
            not self.last_message_id
            or self.last_message_id == self.pending_input_message_id
        ):
            return None

        current_time = time.time()

        # Check if enough time has passed since last message (minimum idle time)
        if self.last_message_time:
            time_since_last_message = current_time - self.last_message_time
            if time_since_last_message < self.minimum_idle_time:
                # Not idle long enough yet
                return None

        # Check if enough time has passed since last input request (prevent rapid requests)
        if self.last_input_request_time:
            time_since_last_request = current_time - self.last_input_request_time
            if time_since_last_request < self.min_request_interval:
                # Too soon since last request
                return None

        # All checks passed - request input
        return self.last_message_id

    def mark_input_requested(self, message_id: str) -> None:
        """Mark that input has been requested for a message.

        Args:
            message_id: Message ID to mark as requested
        """
        self.pending_input_message_id = message_id
        self.last_input_request_time = time.time()

    def _sanitize_content(self, content: str) -> str:
        """Sanitize content - remove NUL and control characters.

        This handles binary content from .docx, PDFs, etc. that might
        break the API.

        Args:
            content: Raw content

        Returns:
            Sanitized content
        """
        return "".join(
            char if ord(char) >= 32 or char in "\n\r\t" else ""
            for char in content.replace("\x00", "")
        )

    def get_last_message_time(self) -> Optional[float]:
        """Get the time of the last message.

        Returns:
            Timestamp of last message, or None
        """
        return self.last_message_time

    def get_last_message_id(self) -> Optional[str]:
        """Get the ID of the last message.

        Returns:
            Last message ID, or None
        """
        return self.last_message_id

    def reset_idle_tracking(self) -> None:
        """Reset idle tracking state."""
        self.last_message_time = time.time()
        self.pending_input_message_id = None

    def process_user_message_sync(self, content: str, from_web: bool = False) -> None:
        """Process a user message for deduplication tracking.

        This doesn't send the message, just tracks it for deduplication.

        Args:
            content: Message content
            from_web: Whether this message came from the web UI
        """
        # Track for deduplication
        self.deduplicator.process_user_message(content, from_web=from_web)
