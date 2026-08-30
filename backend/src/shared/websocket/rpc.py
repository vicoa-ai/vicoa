"""Point-to-point RPC routing over WebSocket (websocket-migration plan §2.8).

A daemon registers handlers under `(user_id, machine_id, method)`. A client
`call` looks up the matching daemon, generates a server-side `corr_id`, sends
an `rpc-request`, and awaits the daemon's `rpc-response`.

The client-chosen `request_id` is unique only within one caller connection, so
it never keys a server-wide map. The endpoint awaits `call()` directly, so the
caller's identity lives in its own stack frame; only the `corr_id` is mapped
server-side, and it is server-generated and globally unique.
"""

import asyncio
from uuid import uuid4

from .connection_manager import Connection

DEFAULT_TIMEOUT = 30.0

# §2.8 no-handler grace window: a daemon may be momentarily offline (reconnecting
# after a deploy or a network blip) when a call arrives. Wait this long for one
# to register before failing the call with `no_handler`.
GRACE_SECONDS = 3.0
_GRACE_POLL_INTERVAL = 0.05

RpcKey = tuple[str, str, str]  # (user_id, machine_id, method)


class RpcError(Exception):
    """An RPC call failed. `code` is one of the §2.8 wire error codes."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _Pending:
    __slots__ = ("future", "daemon")

    def __init__(self, future: "asyncio.Future[dict]", daemon: Connection) -> None:
        self.future = future
        self.daemon = daemon


class RpcRouter:
    """Routes RPC calls from clients to daemon connections."""

    def __init__(self) -> None:
        self._handlers: dict[RpcKey, Connection] = {}
        self._pending: dict[str, _Pending] = {}

    def register(
        self, user_id: str, machine_id: str, method: str, daemon: Connection
    ) -> None:
        """Record that `daemon` serves `method` for `(user_id, machine_id)`."""
        self._handlers[(user_id, machine_id, method)] = daemon

    def unregister(self, daemon: Connection) -> None:
        """Drop a disconnected daemon's handlers and fail its in-flight calls."""
        for key in [k for k, v in self._handlers.items() if v is daemon]:
            del self._handlers[key]
        for pending in list(self._pending.values()):
            if pending.daemon is daemon and not pending.future.done():
                pending.future.set_exception(RpcError("target_disconnected"))

    async def _await_handler(self, key: RpcKey, grace: float) -> Connection | None:
        """Return the daemon for `key`, waiting up to `grace` seconds for one
        to register (§2.8 no-handler grace window). None if none appears."""
        daemon = self._handlers.get(key)
        if daemon is not None or grace <= 0:
            return daemon
        deadline = asyncio.get_running_loop().time() + grace
        # Poll rather than asyncio.Event: the grace window almost never fires in
        # practice, so the extra complexity of signaling from register() isn't
        # justified. At 50 ms × up to grace/0.05 iterations the overhead is trivial.
        while True:
            await asyncio.sleep(_GRACE_POLL_INTERVAL)
            daemon = self._handlers.get(key)
            if daemon is not None:
                return daemon
            if asyncio.get_running_loop().time() >= deadline:
                return None

    async def call(
        self,
        user_id: str,
        machine_id: str,
        method: str,
        params: dict,
        timeout: float = DEFAULT_TIMEOUT,
        grace: float = GRACE_SECONDS,
    ) -> dict:
        """Route an RPC call to the owning daemon and await its result.

        If no daemon is registered for `(user_id, machine_id, method)`, wait up
        to `grace` seconds for one (covers a daemon reconnecting after a deploy
        or network blip) before raising `RpcError("no_handler")`.
        """
        daemon = await self._await_handler((user_id, machine_id, method), grace)
        if daemon is None:
            raise RpcError("no_handler")

        corr_id = uuid4().hex
        future: asyncio.Future[dict] = asyncio.get_running_loop().create_future()
        self._pending[corr_id] = _Pending(future, daemon)
        daemon.enqueue(
            {
                "type": "rpc-request",
                "method": method,
                "params": params,
                "corr_id": corr_id,
            }
        )
        try:
            return await asyncio.wait_for(future, timeout)
        except (TimeoutError, asyncio.TimeoutError) as exc:
            # asyncio.TimeoutError is only aliased to the builtin TimeoutError in 3.11+
            raise RpcError("timeout") from exc
        finally:
            self._pending.pop(corr_id, None)

    def resolve(self, corr_id: str, result: dict) -> None:
        """Deliver a daemon's `rpc-response` to the awaiting caller."""
        pending = self._pending.get(corr_id)
        if pending is not None and not pending.future.done():
            pending.future.set_result(result)


# Process-wide singleton, shared by the `/ws` endpoint (which dispatches
# `rpc-register`/`rpc-call`/`rpc-response` frames) and the `POST /machines/{id}/rpc`
# REST fallback. Process-local, like `connection_manager` (§2.10).
rpc_router = RpcRouter()
