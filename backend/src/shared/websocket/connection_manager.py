"""In-memory WebSocket connection registry (websocket-migration plan §2.10).

`ConnectionManager` is process-local: it has no cross-replica fan-out, which is
why the `server` process is pinned to a single process until Phase 6 (Redis).
It indexes connections by `user_id` and by room, fans `update`/`ephemeral`
frames out to rooms, and answers presence queries used to gate FCM push.

Connections expose an `outbox` queue rather than a live socket. The endpoint
owns a writer task that drains the outbox; the manager only enqueues, so every
broadcast method is synchronous and never awaits a slow client.

Backpressure (§2.10): the outbox is bounded. A client whose TCP send buffer
fills up stalls `drain_outbox` on `await websocket.send_json`; without a cap,
broadcasters keep enqueuing and the single-pinned process runs out of memory.
On overflow the connection is "shed" via its `on_overflow` callback (the WS
handler closes the socket with policy-violation 1008) and the client recovers
on the next reconnect through `fetch_*` catch-up — no message is lost, only
that one stuck connection is dropped.
"""

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# How long a reported "desktop foreground" presence stays authoritative without
# a refresh. The desktop client re-asserts foreground on a heartbeat (~25s) while
# the window is focused, so a live focused app comfortably stays inside this
# window. Sized above the WS ping interval (30s) so a briefly-stalled client
# isn't prematurely treated as backgrounded, while a wedged-but-open socket stops
# suppressing phone push within ~75s even if its blur frame never arrives.
_FOREGROUND_TTL_SECONDS = 75.0

# Per-connection outbox cap. Sized so a normal agent burst (a few dozen rapid
# `log_step` messages) doesn't trip it, while a genuinely stuck client can't
# grow memory past ~tens of MB before being shed. Final value is meant to be
# tuned against the Phase 4a load test's slow-consumer scenario; 256 is the
# starting point.
_OUTBOX_MAXSIZE = 256

# Cumulative shed count since process start. Read via
# `connections_closed_slow_count()`. 0 in normal operation; sustained
# non-zero is the alert signal for "slow clients / network issues / cap too
# tight". Module-level int — single-threaded asyncio, no lock needed.
_connections_closed_slow = 0


def connections_closed_slow_count() -> int:
    """Total connections shed for slow-consumer backpressure since process start."""
    return _connections_closed_slow


@dataclass(slots=True, eq=False)
class Connection:
    """One WebSocket client: its identity, scope, joined rooms, and outbox.

    `eq=False` keeps identity-based equality and hashing so a Connection can
    live in the manager's room sets — two distinct sockets are never "equal".
    """

    connection_id: str
    user_id: str
    scope: str
    rooms: frozenset[str]
    # Set for machine-scoped connections — the daemon's own machine. RPC
    # handler registration keys on it (§2.8); `rpc-register` does not carry it.
    machine_id: str | None = None
    # Fired when the outbox overflows. The handler registers a closure that
    # schedules `websocket.close(code=1008)`; kept as a callback rather than a
    # direct WebSocket reference so this shared module stays FastAPI-free.
    on_overflow: Callable[[], None] | None = None
    # Fired when the owning user is revoked (account deleted or API key
    # rotated). The handler registers a closure that schedules
    # `websocket.close(code=4401, reason="credential_revoked")` so the daemon
    # sees the same fatal-auth signal it gets from a REST 401, instead of
    # treating the disconnect as a transient drop and reconnecting. Same
    # FastAPI-free callback contract as ``on_overflow``.
    on_revoked: Callable[[], None] | None = None
    # Idempotent guard: once a connection has overflowed and been shed, further
    # broadcasts to it are silent no-ops until the socket closes and
    # ConnectionManager.unregister drops it from the room index.
    overflowed: bool = False
    # Whether the client behind this connection last reported its window in the
    # foreground. Only the desktop app emits `presence` frames (and only when the
    # user has opted in), so a True here means "a desktop app the user is looking
    # at". Read via `is_desktop_foreground` to suppress FCM phone push. Paired
    # with `foreground_updated` (monotonic seconds) for TTL staleness.
    foreground: bool = False
    foreground_updated: float = 0.0
    outbox: "asyncio.Queue[dict]" = field(
        default_factory=lambda: asyncio.Queue(maxsize=_OUTBOX_MAXSIZE)
    )

    def enqueue(self, frame: dict) -> None:
        """Queue a frame for the endpoint's writer task to send.

        On a full outbox the connection is shed exactly once: counter
        incremented, warning logged, `on_overflow` callback invoked. Further
        enqueues are silent no-ops until the socket actually closes.
        """
        if self.overflowed:
            return
        try:
            self.outbox.put_nowait(frame)
        except asyncio.QueueFull:
            self._trigger_overflow()

    def _trigger_overflow(self) -> None:
        global _connections_closed_slow
        self.overflowed = True
        _connections_closed_slow += 1
        logger.warning(
            "ws_outbox_overflow_shed conn_id=%s user=%s scope=%s rooms=%s "
            "outbox_max=%d",
            self.connection_id,
            self.user_id,
            self.scope,
            list(self.rooms),
            _OUTBOX_MAXSIZE,
        )
        cb = self.on_overflow
        if cb is None:
            return
        try:
            cb()
        except Exception:
            # Never let a misbehaving handler take the broadcaster down.
            logger.exception(
                "on_overflow callback raised for conn_id=%s", self.connection_id
            )


class ConnectionManager:
    """Process-local registry of WebSocket connections."""

    def __init__(self) -> None:
        self._connections: dict[str, list[Connection]] = defaultdict(list)
        self._rooms: dict[str, set[Connection]] = defaultdict(set)

    def register(self, conn: Connection) -> None:
        """Add a connection to the user index and to each of its rooms."""
        self._connections[conn.user_id].append(conn)
        for room in conn.rooms:
            self._rooms[room].add(conn)

    def unregister(self, conn: Connection) -> None:
        """Remove a connection from every index, leaving no dangling references."""
        peers = self._connections.get(conn.user_id)
        if peers and conn in peers:
            peers.remove(conn)
            if not peers:
                del self._connections[conn.user_id]
        for room in conn.rooms:
            members = self._rooms.get(room)
            if members is None:
                continue
            members.discard(conn)
            if not members:
                del self._rooms[room]

    def broadcast_update(self, user_id: str, payload: dict, rooms: list[str]) -> None:
        """Fan an `update` frame out to every connection in the target rooms."""
        self._fan_out(rooms, {"type": "update", "payload": payload})

    def broadcast_frame(self, rooms: list[str], frame: dict) -> None:
        """Fan an already-shaped frame (verbatim) out to the target rooms.

        Unlike `broadcast_update`, the frame is NOT wrapped in an `update`
        envelope — used for top-level push frames the client dispatches
        directly, e.g. streamed `pty-output`/`pty-exit`.
        """
        self._fan_out(rooms, frame)

    def broadcast_ephemeral(self, user_id: str, body: dict) -> None:
        """Send a not-stored `ephemeral` frame to every connection of the user."""
        frame = {"type": "ephemeral", "body": body}
        for conn in self._connections.get(user_id, ()):
            conn.enqueue(frame)

    def has_user_scoped(self, user_id: str) -> bool:
        """Whether the user has a live user-scoped connection (gates FCM push)."""
        return any(c.scope == "user-scoped" for c in self._connections.get(user_id, ()))

    def record_presence(self, conn: Connection, foreground: bool) -> None:
        """Record a `presence` frame's foreground state on a connection.

        Centralises the monotonic timestamp so `is_desktop_foreground`'s TTL
        read and this write share one clock. Called from the WS receive loop
        when a (desktop) client reports its window focus/blur.
        """
        conn.foreground = foreground
        conn.foreground_updated = time.monotonic()

    def is_desktop_foreground(self, user_id: str) -> bool:
        """Whether the user has a connection whose window is currently foreground.

        Used to suppress FCM phone push: if the user is actively looking at the
        desktop app we don't buzz their phone (mirrors the desktop banner's
        "only when unfocused" policy). A stale report (older than the TTL — e.g.
        a wedged socket whose blur frame never arrived) does not count.
        """
        now = time.monotonic()
        return any(
            c.scope == "user-scoped"
            and c.foreground
            and (now - c.foreground_updated) < _FOREGROUND_TTL_SECONDS
            for c in self._connections.get(user_id, ())
        )

    def close_user(self, user_id: str) -> int:
        """Trigger close on every live WS connection owned by `user_id`.

        Used by `delete_user_account` (via the `_internal/close_user` bridge)
        so a deleted user's daemon and any other WS clients drop within
        milliseconds — before the daemon's heartbeat thread can fire another
        REST call that would 404 against the cascade-deleted entities.

        Returns the count of connections signalled. A connection without an
        `on_revoked` callback is counted but does nothing (defensive: lets us
        evolve the close mechanism without breaking older callers). Each
        connection unregisters itself from the manager via the existing
        finally-block in the WS endpoint after the close fires.
        """
        peers = self._connections.get(user_id, ())
        count = 0
        for conn in peers:
            cb = conn.on_revoked
            count += 1
            if cb is None:
                continue
            try:
                cb()
            except Exception:
                logger.exception(
                    "on_revoked callback raised for conn_id=%s", conn.connection_id
                )
        return count

    def _fan_out(self, rooms: list[str], frame: dict) -> None:
        seen: set[str] = set()
        for room in rooms:
            for conn in self._rooms.get(room, ()):
                if conn.connection_id not in seen:
                    seen.add(conn.connection_id)
                    conn.enqueue(frame)


# Process-wide singleton. The `/ws` endpoint and the `_internal/broadcast`
# receiver share this one registry; it is process-local, which is why the
# `vicoa-server` app is pinned to a single process (§2.10).
connection_manager = ConnectionManager()
