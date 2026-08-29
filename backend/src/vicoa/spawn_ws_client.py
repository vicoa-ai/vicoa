"""Daemon WebSocket client for spawn requests (websocket-migration §4 Phase 2).

The machine daemon connects to `/ws` as `machine-scoped` and treats each
`spawn-request` update as a wake-up: it still claims the request atomically
over REST (`/spawn-requests/next`), exactly as the SSE path did. New daemons
use this; old daemons stay on SSE until their telemetry tail drops.
"""

import json
import logging
import threading
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from functools import partial
from random import uniform
from typing import Any

import certifi
import websocket

from vicoa.sdk.exceptions import AuthenticationError

logger = logging.getLogger(__name__)

DEFAULT_BACKOFF_BASE = 1.0
DEFAULT_BACKOFF_CAP = 30.0
# Socket timeout: the server pings every 30s, so two missed pings (60s+ of
# silence) surface as a timeout and trigger a reconnect rather than hanging.
RECV_TIMEOUT_SECONDS = 70.0

# RPC handlers run off the receive loop (see `dispatch_frame`). Four workers
# covers the bursty, human-paced RPC traffic one machine sees while bounding
# the thread count on a laptop; excess calls queue behind them and are covered
# by the caller's own RPC timeout.
RPC_WORKER_COUNT = 4

# RFC 6455 private-use range. 4401 matches REST 401 semantically — sent by
# the server's WS handler when the JWT's user no longer exists, so the
# daemon can treat it as fatal-auth and stop reconnecting instead of
# spinning forever against a dead credential.
_WS_CLOSE_CREDENTIAL_REVOKED = 4401

# RFC 6455 opcodes we care about. websocket-client's ``ABNF.OPCODE_*`` would
# work but the constants are tiny and pinning them here avoids importing a
# private-looking module from the library.
_OPCODE_TEXT = 0x1
_OPCODE_CLOSE = 0x8


def _recv_frame_or_raise(socket: Any) -> str:
    """Receive one frame. Returns the text payload, or ``""`` on close.
    Raises ``AuthenticationError`` if the server closed with 4401.

    Replaces a plain ``socket.recv()`` because ``websocket-client`` 1.9 does
    NOT expose ``close_status_code`` on the WebSocket object after a server
    CLOSE — verified empirically (the attribute is unset). The close payload
    *is* available via ``recv_data(control_frame=False)``: opcode 8 with the
    first two bytes carrying the big-endian close code. So we read the frame
    ourselves, inspect the opcode, parse the code, and surface 4401 as a
    fatal-auth signal the outer ``run()`` loop can re-raise.
    """
    opcode, data = socket.recv_data(control_frame=False)
    if opcode == _OPCODE_CLOSE:
        if len(data) >= 2:
            code = int.from_bytes(data[:2], "big")
            if code == _WS_CLOSE_CREDENTIAL_REVOKED:
                raise AuthenticationError(
                    f"ws server closed with credential_revoked ({code})"
                )
        return ""
    if isinstance(data, (bytes, bytearray)):
        return data.decode("utf-8")
    return data


def full_jitter_delay(
    attempt: int,
    base: float = DEFAULT_BACKOFF_BASE,
    cap: float = DEFAULT_BACKOFF_CAP,
) -> float:
    """Reconnect backoff delay, full-jitter from the first attempt (§2.10).

    `random(0, min(cap, base * 2**attempt))` — applied from attempt 0, so even
    the first reconnect is jittered and a mass-disconnect herd spreads out
    instead of retrying in a synchronized wave.

    The shift is clamped before the multiply: a daemon that never connects
    (e.g., persistent 403 against a not-yet-deployed backend) would otherwise
    grow `2**attempt` into a Python big-int that overflows when converted to
    float in `base * (...)`. `2**30 ≈ 1.07e9` is well past any sane cap.
    """
    shift = min(attempt, 30)
    return uniform(0.0, min(cap, base * (2**shift)))


def _run_rpc_request(
    frame: dict,
    on_rpc_request: Callable[[dict], dict],
    send_rpc_response: Callable[[str, dict], None],
) -> None:
    """Run one RPC handler and reply. Runs on an `rpc_executor` worker.

    Backstop catch — individual handlers (machine_daemon.spawn_session_rpc)
    already wrap their bodies and return `{"error": ...}` on known failures,
    but an unexpected exception escaping the handler would otherwise unwind
    `_connect_and_serve` and tear down the WebSocket (or, off-loop, vanish
    into an unread Future). That triggers `rpc_router.unregister` on the
    server, failing all in-flight calls with `target_disconnected` for what is
    really a single-call bug. Catch here, reply with the same error shape the
    handlers use, keep the socket alive.
    """
    try:
        result = on_rpc_request(frame)
    except Exception as exc:
        logger.exception(
            "rpc handler %r raised; replying with error",
            frame.get("method"),
        )
        result = {"error": f"handler raised: {type(exc).__name__}: {exc}"}
    send_rpc_response(str(frame.get("corr_id")), result)


def dispatch_frame(
    frame: dict,
    *,
    on_spawn_request: Callable[[], None],
    send_pong: Callable[[], None],
    on_rpc_request: Callable[[dict], dict] | None = None,
    send_rpc_response: Callable[[str, dict], None] | None = None,
    rpc_executor: Executor | None = None,
    ordered_executor: Executor | None = None,
    ordered_methods: frozenset[str] = frozenset(),
) -> None:
    """Route one received frame.

    spawn-request -> wake-up, ping -> pong, rpc-request -> run the handler and
    reply with an `rpc-response` echoing the server's `corr_id` (§2.8).

    RPC handlers are handed to `rpc_executor` rather than run here, because
    this function executes on the daemon's *receive loop*: a slow handler
    (`git-log` on a large repo, a full project scan) would otherwise block
    pong replies, and the server drops a daemon after two missed 30s pings.
    Without an executor the handler runs inline — the old behaviour, kept for
    direct unit tests of this function.

    A method in `ordered_methods` is routed to `ordered_executor` (a single
    worker) instead of the parallel `rpc_executor`, so pipelined pty input
    (`pty-write`/`pty-resize`/`pty-kill`) is applied in receive order and a
    fast typist's keystrokes can't reorder across worker threads.
    """
    frame_type = frame.get("type")
    if frame_type == "ping":
        send_pong()
    elif frame_type == "update":
        body = frame.get("payload", {}).get("body", {})
        if body.get("t") == "spawn-request":
            on_spawn_request()
    elif frame_type == "rpc-request":
        if on_rpc_request is not None and send_rpc_response is not None:
            work = partial(_run_rpc_request, frame, on_rpc_request, send_rpc_response)
            executor = rpc_executor
            if ordered_executor is not None and frame.get("method") in ordered_methods:
                executor = ordered_executor
            if executor is None:
                work()
                return
            try:
                executor.submit(work)
            except RuntimeError:
                # Executor already shut down — the daemon is stopping. Answer
                # inline rather than dropping the call on the floor; blocking
                # the receive loop no longer matters at this point.
                work()


class SpawnRequestWsClient:
    """Maintains a machine-scoped /ws connection that wakes the daemon.

    `run()` is a blocking reconnect loop; call `stop()` from another thread to
    shut it down. A `spawn-request` frame invokes `on_spawn_request`, which the
    daemon uses as a wake-up to claim and process pending requests over REST.
    """

    def __init__(
        self,
        *,
        ws_url: str,
        api_key: str,
        machine_id: str,
        on_spawn_request: Callable[[], None],
        cli_version: str | None = None,
        on_connect: Callable[[], None] | None = None,
        on_rpc_request: Callable[[dict], dict] | None = None,
        rpc_methods: list[str] | None = None,
        ordered_rpc_methods: list[str] | None = None,
        connect_fn: Callable[..., Any] = websocket.create_connection,
        rpc_executor: Executor | None = None,
    ) -> None:
        self._ws_url = ws_url
        self._api_key = api_key
        self._machine_id = machine_id
        self._on_spawn_request = on_spawn_request
        self._cli_version = cli_version
        self._on_connect = on_connect
        # When set, the daemon serves RPC: it announces `rpc_methods` with
        # `rpc-register` on connect and answers `rpc-request` frames (§2.8).
        self._on_rpc_request = on_rpc_request
        self._rpc_methods = rpc_methods or []
        # Methods whose relative order must be preserved (pty input): routed to
        # a single ordered worker instead of the parallel pool (§ dispatch_frame).
        self._ordered_methods = frozenset(ordered_rpc_methods or ())
        self._connect_fn = connect_fn
        self._stop = threading.Event()
        self._socket: Any = None
        # Set while a connection is live so `push_frame` (called from terminal
        # reader/coalescer threads) can stream `pty-output`/`pty-exit` upstream.
        # None between connections; pushes are then dropped (best-effort — pty
        # output is lossy, and the client re-spawns fresh on reconnect).
        self._push: Callable[[dict], None] | None = None
        # One pool for the client's whole life, not per-connection: reconnects
        # are routine and re-creating threads on each one is pure churn. Only
        # built when this daemon actually serves RPC. An injected executor
        # (tests) is borrowed, not owned — we don't shut down what we didn't
        # create.
        self._owns_rpc_executor = rpc_executor is None and on_rpc_request is not None
        self._rpc_executor: Executor | None = rpc_executor
        # A single dedicated worker for order-sensitive pty input, kept off the
        # parallel pool so a fast typist's pipelined keystrokes apply in order.
        # Built (and owned) only when this daemon serves ordered methods and
        # owns its pool — an injected `rpc_executor` (tests) opts out, keeping
        # pty routing on that one executor for deterministic assertions.
        self._ordered_executor: Executor | None = None
        if self._owns_rpc_executor:
            self._rpc_executor = ThreadPoolExecutor(
                max_workers=RPC_WORKER_COUNT, thread_name_prefix="vicoa-rpc"
            )
            if self._ordered_methods:
                self._ordered_executor = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="vicoa-pty-input"
                )

    def stop(self) -> None:
        """Signal the reconnect loop to exit and close any open socket.

        ``WebSocket.close()`` defaults to a 3-second wait for the server's
        CLOSE frame, which becomes a hard 3s floor on daemon shutdown. Pass a
        short ``timeout`` so a healthy server's CLOSE round-trip still
        completes (~50-150ms) but an unresponsive one doesn't gate exit.

        RPC workers are abandoned rather than awaited (``wait=False``): a
        handler mid-``git-log`` would otherwise gate shutdown on it, and the
        server already fails the caller with ``target_disconnected`` the
        moment this connection drops.
        """
        self._stop.set()
        socket = self._socket
        if socket is not None:
            try:
                socket.close(timeout=1.0)
            except Exception:  # noqa: BLE001 - best-effort close
                pass
        if self._owns_rpc_executor and self._rpc_executor is not None:
            self._rpc_executor.shutdown(wait=False, cancel_futures=True)
        if self._ordered_executor is not None:
            self._ordered_executor.shutdown(wait=False, cancel_futures=True)

    def push_frame(self, frame: dict) -> bool:
        """Send a server-initiated frame upstream (e.g. streamed pty output).

        Best-effort: returns False (and drops the frame) when no connection is
        live or the send fails — pty output is lossy and the client resyncs on
        reconnect, so this must never raise into a reader/coalescer thread.
        """
        send = self._push
        if send is None:
            return False
        try:
            send(frame)
            return True
        except Exception as exc:  # noqa: BLE001 - connection went away mid-send
            logger.debug("push_frame dropped (%s): %s", frame.get("type"), exc)
            return False

    def run(self) -> None:
        """Blocking reconnect loop until `stop()` is called."""
        attempt = 0
        while not self._stop.is_set():
            try:
                self._connect_and_serve()
                attempt = 0
            except AuthenticationError:
                # A 401 surfaced inside the loop (e.g. _catchup_poll on connect,
                # or _recv_frame_or_raise after a 4401 close from the server's
                # credential-revoke push) means the credential is dead. Don't
                # treat it as a transient drop — re-raise so the owner (daemon
                # MachineDaemon.run()) flags _fatal_auth and exits via
                # _handle_fatal_auth.
                raise
            except Exception as exc:  # noqa: BLE001 - any failure -> reconnect
                logger.warning("spawn WS connection lost: %s", exc)
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
        # RPC workers now send on this socket concurrently with the receive
        # loop's pongs, and ``websocket-client`` sends are not thread-safe —
        # two unsynchronized sends interleave their frames on the wire and
        # corrupt both. Serialization happens *outside* the lock so a 1 MB
        # result doesn't hold it for the encode.
        send_lock = threading.Lock()
        connection_closed = threading.Event()

        def send_json(payload: dict) -> None:
            data = json.dumps(payload)
            with send_lock:
                socket.send(data)

        try:
            send_json(
                {
                    "type": "hello",
                    "scope": "machine-scoped",
                    "machine_id": self._machine_id,
                }
            )
            if not _recv_frame_or_raise(
                socket
            ):  # expect server_info; empty => rejected/closed
                return
            if self._on_rpc_request is not None:
                for method in self._rpc_methods:
                    send_json({"type": "rpc-register", "method": method})
            if self._on_connect is not None:
                self._on_connect()
            # Expose the (thread-safe) sender so terminal output can stream
            # upstream; cleared in the finally when the socket drops.
            self._push = send_json

            def send_rpc_response(corr_id: str, result: dict) -> None:
                # A worker can outlive its connection (slow handler, socket
                # dropped underneath it). Both the pre-check and the catch are
                # needed: the flag skips the common case cheaply, the catch
                # covers the race where teardown lands mid-send. Swallowing is
                # right here — the receive loop discovers the dead socket on
                # its own and reconnects, and the server has already failed
                # this call with `target_disconnected`.
                if connection_closed.is_set():
                    logger.debug(
                        "dropping rpc-response %s: connection already closed", corr_id
                    )
                    return
                try:
                    send_json(
                        {
                            "type": "rpc-response",
                            "corr_id": corr_id,
                            "result": result,
                        }
                    )
                except Exception as exc:  # noqa: BLE001 - connection is gone
                    logger.warning("failed to send rpc-response %s: %s", corr_id, exc)

            while not self._stop.is_set():
                raw = _recv_frame_or_raise(socket)
                if not raw:
                    return
                dispatch_frame(
                    json.loads(raw),
                    on_spawn_request=self._on_spawn_request,
                    send_pong=lambda: send_json({"type": "pong"}),
                    on_rpc_request=self._on_rpc_request,
                    send_rpc_response=send_rpc_response,
                    rpc_executor=self._rpc_executor,
                    ordered_executor=self._ordered_executor,
                    ordered_methods=self._ordered_methods,
                )
        finally:
            connection_closed.set()
            self._push = None
            self._socket = None
            try:
                socket.close()
            except Exception:  # noqa: BLE001 - best-effort close
                pass
