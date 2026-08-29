"""Session heartbeat for headless agent wrappers.

Headless wrappers (ACP, claude_code, codex_native) historically never
heartbeat. ``agent_instances.last_heartbeat_at`` only advanced as a side
effect of the agent posting a message (``create_agent_message`` stamps it),
so an idle-but-healthy session awaiting user input looked indistinguishable
from a dead one after a couple of minutes.

That is the wrong signal to hang a liveness indicator on: the sessions most
likely to be idle are exactly the ones waiting for the user to reply. This
module gives headless wrappers the same 30s timer the interactive wrappers
already run, so a stale ``last_heartbeat_at`` genuinely means "gone".

Interactive wrappers have their own equivalent implementations
(``cli_wrappers/claude_code/monitoring/heartbeat.py`` and the inline loop in
``vicoa/agents/codex.py``); folding those onto this module is a worthwhile
follow-up but is deliberately out of scope here.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import threading
from typing import Any, Callable, Optional

DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30.0

logger = logging.getLogger(__name__)


class SessionHeartbeat:
    """Periodically POST a session heartbeat on a background daemon thread.

    Failures are logged and swallowed — a heartbeat problem must never take
    down the agent session it is describing.
    """

    def __init__(
        self,
        agent_instance_id: str,
        base_url: str,
        http_session: Any,
        interval: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        log_func: Optional[Callable[[str], None]] = None,
    ):
        """
        Args:
            agent_instance_id: Instance to heartbeat. Must be the *post*
                registration id — registration can hand back a different one.
            base_url: Vicoa API base URL.
            http_session: A ``requests``-style session (``VicoaClient.session``),
                already carrying auth headers.
            interval: Seconds between heartbeats.
            log_func: Optional logger.
        """
        self.agent_instance_id = agent_instance_id
        self.base_url = base_url
        self.http_session = http_session
        self.interval = max(float(interval), 5.0)
        self.log = log_func or (lambda msg: None)

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        return (
            self.base_url.rstrip("/")
            + f"/api/v1/agents/instances/{self.agent_instance_id}/heartbeat"
        )

    def start(self) -> None:
        """Start the heartbeat thread. Idempotent."""
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="vicoa-session-heartbeat", daemon=True
        )
        self._thread.start()
        self.log(f"[INFO] Started session heartbeat ({self.interval:.0f}s)")

    def stop(self) -> None:
        """Signal the heartbeat thread to stop. Does not block on join."""
        self._stop_event.set()
        self._thread = None

    def _loop(self) -> None:
        # Stagger startup so a machine relaunching many sessions at once
        # doesn't emit a synchronized burst of writes.
        if self._stop_event.wait(random.uniform(0, 2.0)):
            return

        while not self._stop_event.is_set():
            try:
                resp = self.http_session.post(self.url, timeout=10)
                # 404 is expected in the window before the instance row exists.
                if resp.status_code >= 400 and resp.status_code != 404:
                    self.log(f"[WARN] Heartbeat failed {resp.status_code}")
            except Exception as exc:
                self.log(f"[WARN] Heartbeat error: {exc}")

            # Jitter each interval so concurrent sessions stay spread out.
            delay = self.interval + random.uniform(-2.0, 2.0)
            self._stop_event.wait(max(delay, 5.0))

    def __enter__(self) -> "SessionHeartbeat":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.stop()
        return False


class AsyncSessionHeartbeat:
    """asyncio-native counterpart of :class:`SessionHeartbeat`.

    For wrappers built on ``AsyncVicoaClient`` (claude_code, codex_native),
    where a thread + ``requests`` session would mean a second HTTP stack.
    """

    def __init__(
        self,
        agent_instance_id: str,
        vicoa_client: Any,
        interval: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    ):
        """
        Args:
            agent_instance_id: Instance to heartbeat.
            vicoa_client: An ``AsyncVicoaClient`` (uses ``heartbeat_instance``).
            interval: Seconds between heartbeats.
        """
        self.agent_instance_id = agent_instance_id
        self.vicoa_client = vicoa_client
        self.interval = max(float(interval), 5.0)
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """Schedule the heartbeat task on the running loop. Idempotent."""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the heartbeat task and await its teardown."""
        task, self._task = self._task, None
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _loop(self) -> None:
        # Stagger startup so a machine relaunching many sessions at once
        # doesn't emit a synchronized burst of writes.
        await asyncio.sleep(random.uniform(0, 2.0))

        while True:
            try:
                await self.vicoa_client.heartbeat_instance(self.agent_instance_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                # A heartbeat failure must never take down the session it
                # describes; the next tick retries.
                logger.debug("session heartbeat failed", exc_info=True)

            # Jitter each interval so concurrent sessions stay spread out.
            await asyncio.sleep(max(self.interval + random.uniform(-2.0, 2.0), 5.0))
