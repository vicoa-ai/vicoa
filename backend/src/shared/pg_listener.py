"""Process-wide PostgreSQL LISTEN/NOTIFY fan-out hub.

Maintains a single shared asyncpg connection per process and dispatches NOTIFY
payloads to multiple in-process subscribers via per-subscriber objects.

Without this, each SSE client opens its own asyncpg connection — at scale that
exhausts the database connection pool. With the hub, one connection per process
is shared by all SSE streams.

## Subscriber objects

Each call to ``subscribe()`` yields a ``(WakeEvent, CoalescingQueue)`` pair:

- ``WakeEvent`` — boolean flag set on every NOTIFY for must-deliver events
  (message_insert, message_update, terminate).  N rapid NOTIFYs collapse to 1;
  the generator wakes, queries the DB cursor, and picks up every row at once.

- ``CoalescingQueue`` — per-event_type latest-wins queue for signal events
  (status_update, git_diff_update, agent_heartbeat).  A burst of N identical
  types still occupies exactly one slot.  ``status_update`` events also set
  the WakeEvent so the generator wakes immediately rather than waiting up to
  15 s for the next message NOTIFY.

Single channel per instance.  ``_make_callback`` routes by ``event_type``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Dict, Optional, Set, Tuple

import asyncpg

logger = logging.getLogger(__name__)

RECONNECT_INITIAL_BACKOFF = 1.0
RECONNECT_MAX_BACKOFF = 30.0

# Warn when a single disconnect window exceeded this duration — past ~5 s
# NOTIFY events are silently lost for every subscriber while we're down.
_DISCONNECT_WARN_SECONDS: float = 5.0

# PG's NOTIFY payload hard limit is 8000 bytes — exceeding it raises an error
# that aborts the triggering INSERT/UPDATE. Warn well before we hit that cliff
# so a runaway field (e.g. instance_metadata) is visible in logs before it
# starts failing writes.
_NOTIFY_PAYLOAD_WARN_BYTES: int = 6000

# Periodic hub health log cadence. 300 s = 12 entries/hour/process — enough
# resolution to spot a trend in Fly logs without polluting them. Adjust if
# you're actively debugging.
_METRICS_LOG_INTERVAL_SECONDS: float = 300.0

# Orphan ratio threshold above which the periodic log escalates from INFO to
# WARNING. Orphans = channels with subscribers but no asyncpg callback — every
# NOTIFY for those channels is silently dropped. Should sit at ~0% in a
# healthy hub; sustained non-zero means subscriber leak or registration bug.
_METRICS_ORPHAN_RATIO_WARN: float = 0.05

# Events that set the wake flag — must-deliver, DB-cursor picks them up.
_WAKE_EVENTS: frozenset[str] = frozenset(
    {"message_insert", "message_update", "terminate"}
)

# Events that set the wake flag AND go into the CoalescingQueue.
# status_update is dual-routed so the generator wakes immediately on status
# changes (e.g. ACTIVE → AWAITING_INPUT) instead of waiting up to 15 s for
# the next message NOTIFY.  Ordering is preserved because the generator always
# runs the cursor query before draining the queue.
_DUAL_ROUTE_EVENTS: frozenset[str] = frozenset({"status_update"})


class WakeEvent:
    """Boolean wake flag — N set() calls collapse to 1. Cannot overflow."""

    def __init__(self) -> None:
        self._event = asyncio.Event()

    def set(self) -> None:
        self._event.set()

    async def wait_and_clear(self) -> None:
        await self._event.wait()
        self._event.clear()

    def is_set(self) -> bool:
        return self._event.is_set()


class CoalescingQueue:
    """Per-subscriber queue for signal events.

    Keeps only the latest payload per ``event_type`` key.  A burst of N
    identical event types occupies exactly one slot regardless of N.
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._event = asyncio.Event()

    def put_nowait(self, payload: str) -> None:
        try:
            import json as _json

            data = _json.loads(payload)
            event_type = data.get("event_type", "")
            # Unique events (e.g. spawn_request) carry a request_id or id —
            # use it as a suffix so distinct payloads are never coalesced.
            unique_id = data.get("request_id") or data.get("id")
            key = (
                f"{event_type}:{unique_id}"
                if unique_id
                else (event_type or "__unknown__")
            )
        except Exception:
            key = "__unknown__"
        self._store[key] = payload
        self._event.set()

    async def get(self) -> str:
        while not self._store:
            self._event.clear()
            await self._event.wait()
        key, payload = next(iter(self._store.items()))
        del self._store[key]
        if not self._store:
            self._event.clear()
        return payload

    def drain_nowait(self) -> list[str]:
        """Return all currently queued payloads and clear the store."""
        items = list(self._store.values())
        self._store.clear()
        self._event.clear()
        return items

    def __len__(self) -> int:
        return len(self._store)


class PGNotificationHub:
    """Shared asyncpg LISTEN/NOTIFY fan-out across in-process subscribers."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn: Optional[asyncpg.Connection] = None
        self._subscribers: Dict[str, Set[Tuple[WakeEvent, CoalescingQueue]]] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._lock = asyncio.Lock()
        self._reconnect_task: Optional[asyncio.Task[None]] = None
        self._closed = False
        self.reconnect_count: int = 0
        # Observability: track how long the hub has spent disconnected since
        # process start. NOTIFYs fired during a disconnect window are lost,
        # so this is the cleanest single number for "how lossy were we?"
        self._disconnected_at: Optional[float] = None
        self.total_disconnect_seconds: float = 0.0
        self.disconnect_count: int = 0
        self._metrics_task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        async with self._lock:
            await self._ensure_connection_locked()
        if self._metrics_task is None or self._metrics_task.done():
            self._metrics_task = asyncio.create_task(self._metrics_loop())

    async def stop(self) -> None:
        self._closed = True
        async with self._lock:
            if self._reconnect_task is not None and not self._reconnect_task.done():
                self._reconnect_task.cancel()
            if self._metrics_task is not None and not self._metrics_task.done():
                self._metrics_task.cancel()
            if self._conn is not None and not self._conn.is_closed():
                try:
                    await self._conn.close()
                except Exception:
                    pass
            self._conn = None
            self._callbacks.clear()
        if self._reconnect_task is not None:
            try:
                await self._reconnect_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._metrics_task is not None:
            try:
                await self._metrics_task
            except (asyncio.CancelledError, Exception):
                pass

    @asynccontextmanager
    async def subscribe(
        self, channel: str
    ) -> AsyncIterator[Tuple[WakeEvent, CoalescingQueue]]:
        """Subscribe to NOTIFY payloads on ``channel``.

        Yields a ``(WakeEvent, CoalescingQueue)`` pair.  The WakeEvent is set
        for must-deliver events (message_insert, message_update, terminate).
        The CoalescingQueue receives signal events (status_update,
        git_diff_update, agent_heartbeat).

        The first subscriber triggers LISTEN; the last triggers UNLISTEN.
        """
        wake = WakeEvent()
        signals = CoalescingQueue()
        pair = (wake, signals)
        # pair_added lets the finally run cleanup even when CancelledError
        # propagates out of __aenter__ before `yield pair` is reached.
        # @asynccontextmanager doesn't invoke __aexit__ on entry-time
        # cancellations, so without this flag `pair` would leak in
        # _subscribers[channel] forever — the source of
        # "self-healing orphaned channel ... N stale subscriber(s)" warnings.
        # subscribers.add(pair) and `pair_added = True` are adjacent synchronous
        # statements, so cancellation can't land between them.
        pair_added = False
        try:
            async with self._lock:
                subscribers = self._subscribers.setdefault(channel, set())
                existing_count = len(subscribers)
                subscribers.add(pair)
                pair_added = True
                if self._conn is None or self._conn.is_closed():
                    await self._ensure_connection_locked()
                # Gate on actual listener state, not "first subscriber". A stale
                # leaked pair in `subscribers` can make first_subscriber False
                # even when no asyncpg callback is registered — which silently
                # drops every NOTIFY for the channel. Self-heals orphaned
                # channels.
                if (
                    self._conn is not None
                    and not self._conn.is_closed()
                    and channel not in self._callbacks
                ):
                    # existing_count > 0 means we're registering a listener for
                    # a channel that already had subscribers — those subscribers
                    # were leaked (their cleanup didn't run, or a prior
                    # re-LISTEN failed mid-loop). Surfacing this as WARNING
                    # means a sustained rate in production logs points at a
                    # remaining leak source.
                    if existing_count > 0:
                        logger.warning(
                            "PG hub: self-healing orphaned channel %s "
                            "(%d stale subscriber(s) present)",
                            channel,
                            existing_count,
                        )
                    try:
                        await self._add_listener_locked(channel)
                    except Exception:
                        logger.exception("PG hub: failed to LISTEN on %s", channel)
                        self._schedule_reconnect_locked()
            yield pair
        finally:
            if pair_added:
                # Hold the lock only for dict mutations; do the awaitable
                # remove_listener call outside. Holding the lock across an
                # await made cleanup hang on lock contention during reconnect.
                callback_to_remove: Optional[Callable] = None
                conn_for_removal: Optional[asyncpg.Connection] = None
                async with self._lock:
                    remaining = self._subscribers.get(channel)
                    if remaining is not None:
                        remaining.discard(pair)
                        if not remaining:
                            self._subscribers.pop(channel, None)
                            callback = self._callbacks.pop(channel, None)
                            if (
                                callback is not None
                                and self._conn is not None
                                and not self._conn.is_closed()
                            ):
                                callback_to_remove = callback
                                conn_for_removal = self._conn
                if callback_to_remove is not None and conn_for_removal is not None:
                    try:
                        await conn_for_removal.remove_listener(
                            channel, callback_to_remove
                        )
                    except Exception as exc:
                        logger.debug(
                            "PG hub: remove_listener(%s) failed: %s",
                            channel,
                            exc,
                        )

    async def _ensure_connection_locked(self) -> None:
        if self._closed:
            return
        if self._conn is not None and not self._conn.is_closed():
            return
        try:
            conn = await asyncpg.connect(self._dsn)
        except Exception as exc:
            logger.warning("PG hub: connect failed: %s", exc)
            self._conn = None
            self._schedule_reconnect_locked()
            return
        conn.add_termination_listener(self._on_termination)  # pyright: ignore[reportOptionalMemberAccess]
        self._conn = conn
        self._callbacks.clear()
        # Re-register every channel; don't let one failure abandon the rest.
        # Early-returning here was the root cause of mass channel orphaning:
        # one bad channel left every channel iterated after it without a
        # callback, silently dropping NOTIFYs for all of them.
        failed_channels: list[str] = []
        for channel in list(self._subscribers.keys()):
            try:
                await self._add_listener_locked(channel)
            except Exception:
                logger.exception(
                    "PG hub: failed to re-LISTEN on %s after reconnect", channel
                )
                failed_channels.append(channel)
        if failed_channels:
            self._schedule_reconnect_locked()
        self.reconnect_count += 1
        # Close out any pending disconnect window — if we had an established
        # connection that died, _disconnected_at was set; compute how long we
        # were down and record it.
        if self._disconnected_at is not None:
            duration = time.monotonic() - self._disconnected_at
            self.total_disconnect_seconds += duration
            self.disconnect_count += 1
            self._disconnected_at = None
            if duration >= _DISCONNECT_WARN_SECONDS:
                logger.warning(
                    "PG hub: reconnected after %.1f s (NOTIFYs during this "
                    "window were dropped for every subscriber on %d channel(s))",
                    duration,
                    len(self._subscribers),
                )
            else:
                logger.info(
                    "PG hub: reconnected after %.2f s "
                    "(channels=%d, reconnect_count=%d)",
                    duration,
                    len(self._subscribers),
                    self.reconnect_count,
                )
        else:
            logger.info(
                "PG hub: connected (channels=%d, reconnect_count=%d)",
                len(self._subscribers),
                self.reconnect_count,
            )

    async def _add_listener_locked(self, channel: str) -> None:
        assert self._conn is not None
        callback = self._make_callback(channel)
        await self._conn.add_listener(channel, callback)
        self._callbacks[channel] = callback

    def _make_callback(self, channel: str) -> Callable:
        def _on_notify(connection, pid, ch, payload):
            if len(payload) >= _NOTIFY_PAYLOAD_WARN_BYTES:
                logger.warning(
                    "PG hub: large NOTIFY payload on %s: %d bytes "
                    "(PG hard limit is 8000; exceeding aborts the triggering write)",
                    channel,
                    len(payload),
                )
            try:
                import json as _json

                data = _json.loads(payload)
                event_type = data.get("event_type", "")
            except Exception:
                event_type = ""

            for wake, signals in list(self._subscribers.get(channel, ())):
                if event_type in _WAKE_EVENTS:
                    wake.set()
                elif event_type in _DUAL_ROUTE_EVENTS:
                    wake.set()
                    signals.put_nowait(payload)
                else:
                    signals.put_nowait(payload)

        return _on_notify

    def _on_termination(self, conn) -> None:
        logger.warning("PG hub: connection terminated; scheduling reconnect")
        if self._closed:
            return
        # Mark the start of the disconnect window so _ensure_connection_locked
        # can report duration on the next successful (re)connect.
        if self._disconnected_at is None:
            self._disconnected_at = time.monotonic()
        try:
            if self._reconnect_task is None or self._reconnect_task.done():
                self._reconnect_task = asyncio.create_task(self._reconnect_loop())
        except RuntimeError:
            pass

    def _schedule_reconnect_locked(self) -> None:
        if self._closed:
            return
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        backoff = RECONNECT_INITIAL_BACKOFF
        while not self._closed:
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_MAX_BACKOFF)
            async with self._lock:
                if self._closed:
                    return
                if self._conn is not None:
                    try:
                        await self._conn.close()
                    except Exception:
                        pass
                    self._conn = None
                self._callbacks.clear()
                await self._ensure_connection_locked()
                if self._conn is not None and not self._conn.is_closed():
                    return

    async def _metrics_loop(self) -> None:
        """Emit a structured snapshot of hub state every N seconds.

        Read under no lock — small races are fine for observability and we
        don't want to contend with subscribe/unsubscribe just to log. Escalates
        to WARNING when orphan ratio breaches the threshold so anomalies are
        loud without making steady-state noisy.
        """
        while not self._closed:
            try:
                await asyncio.sleep(_METRICS_LOG_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                return
            if self._closed:
                return
            channels = len(self._subscribers)
            callbacks = len(self._callbacks)
            orphans = channels - callbacks
            total_subscribers = sum(len(s) for s in self._subscribers.values())
            orphan_ratio = (orphans / channels) if channels > 0 else 0.0
            currently_disconnected = self._disconnected_at is not None
            log_fn = (
                logger.warning
                if orphan_ratio >= _METRICS_ORPHAN_RATIO_WARN
                else logger.info
            )
            log_fn(
                "PG hub metrics: channels=%d callbacks=%d orphans=%d "
                "orphan_ratio=%.1f%% total_subscribers=%d "
                "reconnects=%d disconnects=%d total_disconnect_seconds=%.1f "
                "currently_disconnected=%s",
                channels,
                callbacks,
                orphans,
                orphan_ratio * 100,
                total_subscribers,
                self.reconnect_count,
                self.disconnect_count,
                self.total_disconnect_seconds,
                currently_disconnected,
            )


_hub: Optional[PGNotificationHub] = None


def get_hub() -> PGNotificationHub:
    """Return the process-wide hub singleton, constructing it on first call."""
    global _hub
    if _hub is None:
        from shared.config.settings import settings

        _hub = PGNotificationHub(settings.database_url)
    return _hub


async def start_hub() -> None:
    await get_hub().start()


async def stop_hub() -> None:
    global _hub
    if _hub is not None:
        await _hub.stop()
        _hub = None
