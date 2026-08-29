"""Idle state monitoring for Claude CLI.

This module monitors Claude's idle state and triggers input requests
when appropriate (placeholder for now - async integration needed).
"""

from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from vicoa.sdk.async_client import AsyncVicoaClient
    from ..messaging.processor import MessageProcessor


class IdleMonitor:
    """Monitors Claude's idle state.

    Responsibilities:
    - Detecting when Claude is idle
    - Requesting input from web UI when appropriate
    - Avoiding duplicate input requests
    """

    def __init__(
        self,
        vicoa_client_async: Optional["AsyncVicoaClient"],
        message_processor: "MessageProcessor",
        log_func: Callable[[str], None],
    ):
        """Initialize idle monitor.

        Args:
            vicoa_client_async: Async Vicoa client
            message_processor: Message processor
            log_func: Logging function
        """
        self.vicoa_client_async = vicoa_client_async
        self.message_processor = message_processor
        self.log = log_func

    async def start(self) -> None:
        """Start idle monitoring (async)."""
        self.log("[INFO] Idle monitor started")
        # TODO: Implement async monitoring loop
        # This would run in the async event loop and check
        # message_processor.should_request_input() periodically

    def stop(self) -> None:
        """Stop monitoring."""
        self.log("[INFO] Idle monitor stopped")

    # TODO: Implement full idle monitoring logic
    # - Async monitoring loop
    # - Input request triggering
    # - Integration with MessageProcessor
