"""CLI-wrapper session WebSocket client (websocket-migration §4 Phase 3).

The CLI wrapper connects to `/ws` as `session-scoped` and receives user
messages as live `new-message` updates, replacing the SSE stream. On connect
it sends a `fetch_messages_request` to catch up on messages missed while
disconnected; live updates that arrive before the `fetch_messages_response`
are buffered so history renders in order (§2.6).
"""

import json
import logging
import threading
from collections.abc import Callable
from typing import Any

import certifi
import websocket

from vicoa.sdk.exceptions import AuthenticationError
from vicoa.spawn_ws_client import (
    RECV_TIMEOUT_SECONDS,
    _recv_frame_or_raise,
    full_jitter_delay,
)

logger = logging.getLogger(__name__)

# request_id for the catch-up fetch — unique within this caller connection.
_CATCH_UP_REQUEST_ID = "catch-up"


class CatchUpBuffer:
    """Holds live `new-message` bodies until catch-up completes (§2.6).

    A live update may arrive between the `fetch_messages_request` and its
    response. Buffering it until the catch-up rows are delivered keeps the
    client's message order correct.
    """

    def __init__(self) -> None:
        self._buffered: list[dict] = []
        self._fetch_complete = False
        self._seen: set[str | None] = set()

    def begin_catch_up(self) -> None:
        """Start a fresh catch-up cycle (called on every (re)connect).

        Per-connection buffering state is reset; the seen-id set is kept so
        the reconnect re-fetch's safety-window overlap is not re-delivered.
        """
        self._buffered = []
        self._fetch_complete = False

    def buffer_live(self, body: dict) -> list[dict]:
        """Take a live `new-message` body; return bodies ready to deliver.

        Before catch-up completes the body is held back; after, it is
        delivered straight away (still deduped against catch-up rows).
        """
        if self._fetch_complete:
            return self._dedupe([body])
        self._buffered.append(body)
        return []

    def complete_fetch(self, rows: list[dict]) -> list[dict]:
        """Catch-up response arrived: deliver its rows, then buffered live."""
        delivered = self._dedupe(list(rows) + self._buffered)
        self._buffered = []
        self._fetch_complete = True
        return delivered

    def _dedupe(self, bodies: list[dict]) -> list[dict]:
        """Drop bodies whose id was already delivered (first-write-wins)."""
        fresh: list[dict] = []
        for body in bodies:
            message_id = body.get("id")
            if message_id not in self._seen:
                self._seen.add(message_id)
                fresh.append(body)
        return fresh


class SessionMessagesWsClient:
    """Maintains a session-scoped /ws connection that delivers user messages.

    Mirrors `SpawnRequestWsClient`: `run()` is a blocking reconnect loop,
    `stop()` shuts it down. On every (re)connect it sends a
    `fetch_messages_request` to catch up; each delivered message advances a
    `created_at` watermark used as the next reconnect's catch-up cursor (§2.6).
    """

    def __init__(
        self,
        *,
        ws_url: str,
        api_key: str,
        instance_id: str,
        on_user_message: Callable[[dict], None],
        initial_watermark: dict | None = None,
        cli_version: str | None = None,
        on_connect: Callable[[], None] | None = None,
        connect_fn: Callable[..., Any] = websocket.create_connection,
        on_message_update: Callable[[dict], None] | None = None,
        on_instance_update: Callable[[dict], None] | None = None,
    ) -> None:
        self._ws_url = ws_url
        self._api_key = api_key
        self._instance_id = instance_id
        self._on_user_message = on_user_message
        # {"created_at": iso} or None — the reconnect watermark (§2.6).
        self._watermark = initial_watermark
        self._cli_version = cli_version
        self._on_connect = on_connect
        self._connect_fn = connect_fn
        # Live-only signal (e.g. queue cancellation) — not routed through the
        # CatchUpBuffer/watermark since it isn't a persisted message.
        self._on_message_update = on_message_update
        # Instance row changes (status/metadata). The wrapper watches these to
        # stop itself when the session is archived/closed from another client —
        # otherwise archiving marks the row terminal but leaves the agent
        # running in the background.
        self._on_instance_update = on_instance_update
        self._buffer = CatchUpBuffer()
        self._stop = threading.Event()
        self._socket: Any = None
        # Serializes writes to the socket. The reader thread sends pong /
        # catch-up frames from ``_connect_and_serve``; ``request_refetch`` sends
        # a catch-up frame from the *runner's* event-loop thread. websocket
        # ``send`` is not safe under concurrent writers — two threads
        # interleaving bytes would corrupt the frame stream — so every send
        # goes through ``_send`` under this mutex.
        self._send_mutex = threading.Lock()
        # Set when the first `fetch_messages_response` of the current connection
        # has been processed. After this point the subscription is registered
        # server-side AND the catch-up SELECT has run, so any message either
        # already-persisted or broadcast from now on is guaranteed to reach the
        # delivery callback. Callers that need to POST a message and have it
        # routed back to themselves (e.g. initial-prompt delivery in
        # codex_native) should wait on this before POSTing to avoid the
        # subscribe/catch-up race.
        self._ready = threading.Event()

    @property
    def watermark(self) -> dict | None:
        """The current reconnect watermark — exposed for cross-restart persistence."""
        return self._watermark

    def wait_until_ready(self, timeout: float) -> bool:
        """Block until catch-up has completed on the current connection.

        Returns ``True`` if ready within ``timeout`` seconds, ``False`` on
        timeout. Safe to call from any thread; designed to be awaited from
        asyncio via ``asyncio.to_thread``.
        """
        return self._ready.wait(timeout)

    def request_refetch(self) -> None:
        """Re-issue a catch-up fetch on the *live* connection (thread-safe).

        The runner calls this while an AskUserQuestion / permission reply is
        still pending, to reconcile a reply whose realtime broadcast the
        fire-and-forget backend→server bridge dropped (``post_broadcast`` is
        best-effort and never raises, so a lost POST is silent). The reply is
        durably persisted, so re-fetching the tail recovers it; the
        ``CatchUpBuffer`` dedupes already-delivered rows so this never
        double-delivers, and live delivery is unaffected (``_fetch_complete``
        stays True). No-op when disconnected — the next reconnect's catch-up
        covers that case. Safe to call from another thread via ``_send``.
        """
        socket = self._socket
        if socket is None:
            return
        try:
            self._send_fetch_request(socket)
        except Exception:  # noqa: BLE001 - best-effort backstop
            logger.debug("session WS refetch send failed", exc_info=True)

    def stop(self) -> None:
        """Signal the reconnect loop to exit and close any open socket.

        ``WebSocket.close()`` defaults to a 3-second wait for the server's
        CLOSE frame, which becomes a hard 3s floor on wrapper shutdown. Pass a
        short ``timeout`` so a healthy server's CLOSE round-trip still
        completes (~50-150ms) but an unresponsive one doesn't gate exit.
        """
        self._stop.set()
        socket = self._socket
        if socket is not None:
            try:
                socket.close(timeout=1.0)
            except Exception:  # noqa: BLE001 - best-effort close
                pass

    def run(self) -> None:
        """Blocking reconnect loop until `stop()` is called."""
        attempt = 0
        while not self._stop.is_set():
            try:
                self._connect_and_serve()
                attempt = 0
            except AuthenticationError:
                # A 401 surfaced inside the loop (e.g. _recv_frame_or_raise
                # after a 4401 close from the server's credential-revoke push)
                # means the credential is dead. Re-raise so the owning wrapper
                # tears the link down (`_drop_vicoa_link`) instead of treating
                # it as a transient drop and reconnecting forever.
                raise
            except Exception as exc:  # noqa: BLE001 - any failure -> reconnect
                logger.warning("session WS connection lost: %s", exc)
            if self._stop.is_set():
                break
            delay = full_jitter_delay(attempt)
            attempt += 1
            self._stop.wait(delay)

    def _connect_and_serve(self) -> None:
        subprotocols = ["vicoa-ws", f"vicoa-key.{self._api_key}"]
        header = [f"X-CLI-Version: {self._cli_version}"] if self._cli_version else []
        socket = self._connect_fn(
            self._ws_url,
            subprotocols=subprotocols,
            header=header,
            timeout=RECV_TIMEOUT_SECONDS,
            sslopt={"ca_certs": certifi.where()},
        )
        self._socket = socket
        try:
            self._send(
                socket,
                {
                    "type": "hello",
                    "scope": "session-scoped",
                    "instance_id": self._instance_id,
                },
            )
            if not _recv_frame_or_raise(
                socket
            ):  # expect server_info; empty => rejected/closed
                return
            self._buffer.begin_catch_up()
            self._ready.clear()
            # INFO so reconnects show up in the per-session log (the runner
            # attaches this logger to that file). Silent reconnect churn is
            # exactly what masked the idle-session message-swallow.
            logger.info(
                "session WS connected (instance=%s, watermark=%s)",
                self._instance_id,
                (self._watermark or {}).get("created_at"),
            )
            self._send_fetch_request(socket)
            if self._on_connect is not None:
                self._on_connect()
            while not self._stop.is_set():
                raw = _recv_frame_or_raise(socket)
                if not raw:
                    return
                self._handle_frame(json.loads(raw), socket)
        finally:
            self._socket = None
            try:
                socket.close()
            except Exception:  # noqa: BLE001 - best-effort close
                pass

    def _send(self, socket: Any, obj: dict) -> None:
        """Serialize + write one JSON frame under ``_send_mutex``.

        The single choke point for every socket write, so the reader thread's
        pong/catch-up sends and ``request_refetch``'s cross-thread catch-up
        send can never interleave bytes on the wire.
        """
        with self._send_mutex:
            socket.send(json.dumps(obj))

    def _send_fetch_request(self, socket: Any) -> None:
        self._send(
            socket,
            {
                "type": "fetch_messages_request",
                "request_id": _CATCH_UP_REQUEST_ID,
                "instance_id": self._instance_id,
                "after": self._watermark,
            },
        )

    def _handle_frame(self, frame: dict, socket: Any) -> None:
        frame_type = frame.get("type")
        if frame_type == "ping":
            self._send(socket, {"type": "pong"})
        elif frame_type == "fetch_messages_response":
            delivered = self._buffer.complete_fetch(frame.get("rows", []))
            if delivered:
                # Fires on the connect catch-up AND on every reconcile refetch,
                # so a message recovered after a dropped realtime broadcast is
                # traceable in the session log.
                logger.info(
                    "session WS catch-up delivered %d message(s)", len(delivered)
                )
            self._deliver(delivered)
            self._ready.set()
        elif frame_type == "resync_required":
            # The watermark is unservable — drop it and re-fetch the tail.
            self._watermark = None
            self._buffer.begin_catch_up()
            self._ready.clear()
            self._send_fetch_request(socket)
        elif frame_type == "update":
            body = frame.get("payload", {}).get("body", {})
            t = body.get("t")
            if t == "new-message":
                self._deliver(self._buffer.buffer_live(body))
            elif t == "message-update" and self._on_message_update is not None:
                self._on_message_update(body)
            elif t == "instance-update" and self._on_instance_update is not None:
                self._on_instance_update(body)

    def _deliver(self, bodies: list[dict]) -> None:
        for body in bodies:
            self._advance_watermark(body)
            self._on_user_message(body)

    def _advance_watermark(self, body: dict) -> None:
        """Track the latest message `created_at` as the next reconnect cursor."""
        created_at = body.get("created_at")
        if created_at is None:
            return
        if self._watermark is None or created_at > self._watermark["created_at"]:
            self._watermark = {"created_at": created_at}
