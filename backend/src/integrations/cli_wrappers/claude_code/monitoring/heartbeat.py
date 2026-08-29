"""Heartbeat management for Claude Code Wrapper.

This module provides heartbeat functionality to keep the agent
instance alive on the Vicoa servers.
"""

import random
import threading
import time
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from vicoa.sdk.client import VicoaClient


class HeartbeatManager:
    """Manages heartbeat pings to keep agent instance alive.

    Runs in a background thread and periodically sends heartbeat
    requests to the Vicoa server.
    """

    def __init__(
        self,
        agent_instance_id: str,
        base_url: str,
        vicoa_client: Optional["VicoaClient"],
        interval: float = 30.0,
        log_func: Optional[Callable[[str], None]] = None,
    ):
        """Initialize heartbeat manager.

        Args:
            agent_instance_id: Agent instance ID
            base_url: Vicoa base URL
            vicoa_client: Vicoa SDK client (sync)
            interval: Heartbeat interval in seconds
            log_func: Optional logging function
        """
        self.agent_instance_id = agent_instance_id
        self.base_url = base_url
        self.vicoa_client = vicoa_client
        self.interval = interval
        self.log = log_func or (lambda msg: None)

        self.running = True
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the heartbeat thread."""
        if self.thread is not None:
            self.log("[WARNING] Heartbeat thread already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.thread.start()
        self.log("[INFO] Started heartbeat thread")

    def stop(self) -> None:
        """Stop the heartbeat thread.

        Note: This is a daemon thread, so we just signal it to stop.
        The thread will exit on its own when the main process exits.
        """
        self.running = False
        self.log("[INFO] Signaled heartbeat thread to stop")

    def _heartbeat_loop(self) -> None:
        """Background loop to POST heartbeat while running."""
        if not self.vicoa_client:
            return

        session = self.vicoa_client.session
        url = (
            self.base_url.rstrip("/")
            + f"/api/v1/agents/instances/{self.agent_instance_id}/heartbeat"
        )

        # Small stagger to avoid herd
        jitter = random.uniform(0, 2.0)
        time.sleep(jitter)

        while self.running:
            try:
                resp = session.post(url, timeout=10)
                if resp.status_code >= 400:
                    self.log(
                        f"[WARN] Heartbeat failed {resp.status_code}: {resp.text[:120]}"
                    )
            except Exception as e:
                self.log(f"[WARN] Heartbeat error: {e}")

            # Wait for next heartbeat with interruptible sleep
            # Sleep in small increments so we can respond quickly to shutdown
            elapsed = 0.0
            while elapsed < self.interval and self.running:
                time.sleep(0.1)
                elapsed += 0.1

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False
