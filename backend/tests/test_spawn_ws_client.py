"""Behavioral tests for the daemon spawn-request WebSocket client (Phase 2).

The connection loop is integration-tested; these cover the pure pieces — the
full-jitter reconnect delay (§2.10) and the frame dispatch that turns a
`spawn-request` update into a wake-up callback.
"""

import json
import threading
import time
from concurrent.futures import Executor, Future

import pytest

from vicoa.sdk.exceptions import AuthenticationError
from vicoa.spawn_ws_client import (
    SpawnRequestWsClient,
    dispatch_frame,
    full_jitter_delay,
)
from vicoa.terminal.rpc import PTY_ORDERED_METHODS


class _InlineExecutor(Executor):
    """Runs submitted work immediately on the calling thread.

    Lets the connection-level tests assert on RPC responses deterministically
    without racing a real worker pool. Concurrency itself is covered
    separately, against the real `ThreadPoolExecutor`.
    """

    def submit(self, fn, /, *args, **kwargs):  # type: ignore[override]
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001 - mirror Executor semantics
            future.set_exception(exc)
        return future


class _FakeSocket:
    """A WebSocket stand-in that replays preloaded TEXT frames, then closes.

    Mirrors the slice of ``websocket-client``'s API the production code uses:
    ``recv_data(control_frame=False)`` returns ``(opcode, bytes)``. Text
    frames replay as opcode=1; once the queue empties we return a CLOSE
    frame (opcode=8) carrying ``_close_code`` as 2-byte big-endian + reason.

    ``send`` records under a lock and, when ``send_delay`` is set, holds the
    socket for that long — the interleaving hazard the production send lock
    exists to prevent.
    """

    def __init__(
        self,
        incoming: list[str],
        close_code: int | None = None,
        close_reason: str = "",
        recv_block: threading.Event | None = None,
        send_delay: float = 0.0,
    ) -> None:
        self._incoming = list(incoming)
        self._close_code = close_code
        self._close_reason = close_reason
        self._recv_block = recv_block
        self._send_delay = send_delay
        self._lock = threading.Lock()
        self.sent: list[str] = []
        self.concurrent_sends = 0
        self._in_send = 0

    def send(self, data: str) -> None:
        with self._lock:
            self._in_send += 1
            if self._in_send > 1:
                self.concurrent_sends += 1
        if self._send_delay:
            time.sleep(self._send_delay)
        with self._lock:
            self._in_send -= 1
            self.sent.append(data)

    def recv_data(self, control_frame: bool = False) -> tuple[int, bytes]:
        if self._incoming:
            return (1, self._incoming.pop(0).encode("utf-8"))
        # Hold the connection open so in-flight RPC workers can finish before
        # teardown drops their responses.
        if self._recv_block is not None:
            self._recv_block.wait(5.0)
        if self._close_code is None:
            return (8, b"")
        payload = self._close_code.to_bytes(2, "big") + self._close_reason.encode(
            "utf-8"
        )
        return (8, payload)

    def close(self, timeout: float | None = None) -> None:
        return None


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    """Poll `predicate` until true or `timeout` elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


_SERVER_INFO = json.dumps({"type": "server_info", "body": {}})
_SPAWN_FRAME = json.dumps(
    {"type": "update", "payload": {"body": {"t": "spawn-request"}}}
)


def test_full_jitter_delay_stays_within_the_attempt_window() -> None:
    for _ in range(200):
        assert 0.0 <= full_jitter_delay(0, base=1.0, cap=30.0) <= 1.0


def test_full_jitter_delay_is_capped_for_large_attempts() -> None:
    for _ in range(200):
        assert 0.0 <= full_jitter_delay(20, base=1.0, cap=30.0) <= 30.0


def test_full_jitter_delay_does_not_overflow_for_unbounded_attempts() -> None:
    """A daemon that never connects grows attempt unbounded; the shift must be
    clamped before the multiply or `base * 2**attempt` overflows when Python
    converts the big-int to float."""
    for attempt in (1024, 10_000, 100_000):
        # Just runs without OverflowError, stays within the cap.
        assert 0.0 <= full_jitter_delay(attempt, base=1.0, cap=30.0) <= 30.0


def test_run_reraises_authentication_error_instead_of_reconnecting() -> None:
    """A 401 surfaced inside the loop (e.g. the daemon's _catchup_poll on
    connect) is fatal-auth, not a transient drop. ``run()`` must re-raise it so
    the owner tears down, not swallow it into the reconnect backoff. The safety
    counter raises KeyboardInterrupt on the 2nd connect so a regressed (looping)
    impl ends the test instead of spinning forever."""
    calls = {"n": 0}

    def connect_fn(*a, **k):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise KeyboardInterrupt
        raise AuthenticationError("401")

    client = SpawnRequestWsClient(
        ws_url="wss://agents.example/ws",
        api_key="k",
        machine_id="m1",
        on_spawn_request=lambda: None,
        connect_fn=connect_fn,
    )

    with pytest.raises(AuthenticationError):
        client.run()
    assert calls["n"] == 1  # did not reconnect after the 401


def test_dispatch_frame_wakes_on_a_spawn_request_update() -> None:
    woke: list[bool] = []
    dispatch_frame(
        {"type": "update", "payload": {"body": {"t": "spawn-request"}}},
        on_spawn_request=lambda: woke.append(True),
        send_pong=lambda: None,
    )
    assert woke == [True]


def test_dispatch_frame_replies_to_ping_with_pong() -> None:
    pongs: list[bool] = []
    dispatch_frame(
        {"type": "ping"},
        on_spawn_request=lambda: None,
        send_pong=lambda: pongs.append(True),
    )
    assert pongs == [True]


def test_dispatch_frame_ignores_unrelated_frames() -> None:
    calls: list[str] = []
    for frame in (
        {"type": "server_info", "body": {}},
        {"type": "update", "payload": {"body": {"t": "new-message"}}},
    ):
        dispatch_frame(
            frame,
            on_spawn_request=lambda: calls.append("spawn"),
            send_pong=lambda: calls.append("pong"),
        )
    assert calls == []


def test_dispatch_frame_handles_an_rpc_request_and_sends_a_response() -> None:
    sent: list[tuple[str, dict]] = []
    dispatch_frame(
        {
            "type": "rpc-request",
            "method": "spawn-session",
            "params": {"directory": "/code"},
            "corr_id": "c1",
        },
        on_spawn_request=lambda: None,
        send_pong=lambda: None,
        on_rpc_request=lambda frame: {"agent_instance_id": "i1"},
        send_rpc_response=lambda corr_id, result: sent.append((corr_id, result)),
    )
    assert sent == [("c1", {"agent_instance_id": "i1"})]


def test_dispatch_frame_catches_handler_exception_and_replies_with_error() -> None:
    """A buggy RPC handler must not tear down the WebSocket connection.

    Without the backstop catch, an unhandled exception in the handler would
    propagate out of dispatch_frame, unwind _connect_and_serve, force a
    reconnect, and fail every in-flight RPC call on the server side with
    `target_disconnected` for what is really a single-call bug.
    """
    sent: list[tuple[str, dict]] = []

    def buggy_handler(frame: dict) -> dict:
        raise RuntimeError("simulated handler bug")

    # Should NOT raise — the exception is caught inside dispatch_frame.
    dispatch_frame(
        {
            "type": "rpc-request",
            "method": "spawn-session",
            "params": {},
            "corr_id": "c2",
        },
        on_spawn_request=lambda: None,
        send_pong=lambda: None,
        on_rpc_request=buggy_handler,
        send_rpc_response=lambda corr_id, result: sent.append((corr_id, result)),
    )

    assert len(sent) == 1
    corr_id, result = sent[0]
    assert corr_id == "c2"
    assert "error" in result
    assert "RuntimeError" in result["error"]
    assert "simulated handler bug" in result["error"]


class _RecordingExecutor(Executor):
    """Records submitted work (and runs it inline) so a test can assert WHICH
    executor a frame was routed to."""

    def __init__(self) -> None:
        self.methods: list[str] = []

    def submit(self, fn, /, *args, **kwargs):  # type: ignore[override]
        self.methods.append("submitted")
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001 - mirror Executor semantics
            future.set_exception(exc)
        return future


def test_dispatch_frame_routes_ordered_methods_to_the_ordered_executor() -> None:
    """Pty input (write/resize/kill) must go to the single ordered worker, not
    the parallel pool — otherwise a fast typist's pipelined keystrokes could
    land on different pool threads and reorder. spawn/heartbeat and every
    non-pty RPC keep the parallel pool.
    """

    def route(method: str) -> str:
        pool = _RecordingExecutor()
        ordered = _RecordingExecutor()
        dispatch_frame(
            {"type": "rpc-request", "method": method, "params": {}, "corr_id": "c"},
            on_spawn_request=lambda: None,
            send_pong=lambda: None,
            on_rpc_request=lambda frame: {},
            send_rpc_response=lambda corr_id, result: None,
            rpc_executor=pool,
            ordered_executor=ordered,
            ordered_methods=PTY_ORDERED_METHODS,
        )
        assert not (pool.methods and ordered.methods), "routed to both executors"
        return "ordered" if ordered.methods else "pool"

    assert route("pty-write") == "ordered"
    assert route("pty-resize") == "ordered"
    assert route("pty-kill") == "ordered"
    # Not order-sensitive → parallel pool.
    assert route("pty-spawn") == "pool"
    assert route("pty-heartbeat") == "pool"
    assert route("git-status") == "pool"


def test_dispatch_frame_without_ordered_executor_keeps_pty_input_on_the_pool() -> None:
    """Back-compat: with no ordered executor supplied, pty input falls back to
    the parallel pool exactly as before (unit tests that inject one executor)."""
    pool = _RecordingExecutor()
    dispatch_frame(
        {"type": "rpc-request", "method": "pty-write", "params": {}, "corr_id": "c"},
        on_spawn_request=lambda: None,
        send_pong=lambda: None,
        on_rpc_request=lambda frame: {},
        send_rpc_response=lambda corr_id, result: None,
        rpc_executor=pool,
        ordered_methods=PTY_ORDERED_METHODS,
    )
    assert pool.methods == ["submitted"]


def _client(socket: _FakeSocket, **overrides: object) -> SpawnRequestWsClient:
    kwargs: dict[str, object] = {
        "ws_url": "wss://agents.vicoa.ai/ws",
        "api_key": "secret-key",
        "machine_id": "m1",
        "cli_version": "9.9.9",
        "on_spawn_request": lambda: None,
        "connect_fn": lambda *a, **k: socket,
    }
    kwargs.update(overrides)
    return SpawnRequestWsClient(**kwargs)  # type: ignore[arg-type]


def test_client_sends_a_machine_hello_then_wakes_on_a_spawn_request() -> None:
    woke: list[bool] = []
    connected: list[bool] = []
    socket = _FakeSocket([_SERVER_INFO, _SPAWN_FRAME])
    client = _client(
        socket,
        on_spawn_request=lambda: woke.append(True),
        on_connect=lambda: connected.append(True),
    )

    client._connect_and_serve()

    assert json.loads(socket.sent[0]) == {
        "type": "hello",
        "scope": "machine-scoped",
        "machine_id": "m1",
    }
    assert connected == [True]
    assert woke == [True]


def test_client_connects_with_the_agent_credential_and_version() -> None:
    captured: dict[str, object] = {}

    def fake_connect(url: str, **kwargs: object) -> _FakeSocket:
        captured["url"] = url
        captured.update(kwargs)
        return _FakeSocket([_SERVER_INFO])

    _client(_FakeSocket([]), connect_fn=fake_connect)._connect_and_serve()

    assert captured["url"] == "wss://agents.vicoa.ai/ws"
    assert "vicoa-key.secret-key" in captured["subprotocols"]  # type: ignore[operator]
    assert "X-CLI-Version: 9.9.9" in captured["header"]  # type: ignore[operator]


def test_client_registers_rpc_methods_on_connect() -> None:
    socket = _FakeSocket([_SERVER_INFO])
    client = _client(
        socket,
        on_rpc_request=lambda frame: {},
        rpc_methods=["spawn-session"],
    )

    client._connect_and_serve()

    registrations = [
        json.loads(s)
        for s in socket.sent
        if json.loads(s).get("type") == "rpc-register"
    ]
    assert registrations == [{"type": "rpc-register", "method": "spawn-session"}]


def test_client_answers_an_rpc_request_with_a_response() -> None:
    rpc_request = json.dumps(
        {
            "type": "rpc-request",
            "method": "spawn-session",
            "params": {"directory": "/code"},
            "corr_id": "c9",
        }
    )
    socket = _FakeSocket([_SERVER_INFO, rpc_request])
    client = _client(
        socket,
        on_rpc_request=lambda frame: {"agent_instance_id": "i9"},
        rpc_methods=["spawn-session"],
        rpc_executor=_InlineExecutor(),
    )

    client._connect_and_serve()

    response = json.loads(socket.sent[-1])
    assert response == {
        "type": "rpc-response",
        "corr_id": "c9",
        "result": {"agent_instance_id": "i9"},
    }


def test_client_replies_to_a_server_ping_with_a_pong() -> None:
    socket = _FakeSocket([_SERVER_INFO, json.dumps({"type": "ping"})])

    _client(socket)._connect_and_serve()

    assert json.loads(socket.sent[-1]) == {"type": "pong"}


# ---------------------------------------------------------------------------
# Credential-revoked close (4401): _connect_and_serve raises AuthenticationError
# so the reconnect loop in run() bails out instead of spinning forever.
# ---------------------------------------------------------------------------


def test_connect_and_serve_raises_on_4401_close_during_handshake() -> None:
    """Server closed before sending server_info — if the close code is 4401
    that's the user-gone signal, must surface as AuthenticationError."""
    socket = _FakeSocket(
        incoming=[], close_code=4401, close_reason="credential_revoked"
    )
    client = _client(socket)

    with pytest.raises(AuthenticationError):
        client._connect_and_serve()


def test_connect_and_serve_raises_on_4401_close_in_serve_loop() -> None:
    """Server closed *after* server_info — same 4401 must propagate from the
    main recv loop, not just the handshake."""
    socket = _FakeSocket(
        incoming=[_SERVER_INFO], close_code=4401, close_reason="credential_revoked"
    )
    client = _client(socket)

    with pytest.raises(AuthenticationError):
        client._connect_and_serve()


def test_connect_and_serve_returns_silently_on_non_4401_close() -> None:
    """A close without a 4401 code (transient drop, 1006, 1001, slow_consumer
    1008, wrong-owner 4403) must NOT raise — the reconnect loop owns that."""
    for code in (None, 1001, 1006, 1008, 4400, 4403):
        socket = _FakeSocket(incoming=[], close_code=code)
        client = _client(socket)
        client._connect_and_serve()  # must return, not raise


# ---------------------------------------------------------------------------
# RPC dispatch runs off the receive loop.
#
# Handlers used to run inline, so a slow one (`git-log` on a big repo, a full
# project scan for @-mentions) blocked pong replies — and the server drops a
# daemon after two missed 30s pings. Handlers now go to a worker pool, which
# means responses share the socket with pongs and with each other.
# ---------------------------------------------------------------------------


def _rpc_frame(corr_id: str, method: str = "git-log") -> str:
    return json.dumps(
        {"type": "rpc-request", "method": method, "params": {}, "corr_id": corr_id}
    )


def _frames_of_type(socket: _FakeSocket, frame_type: str) -> list[dict]:
    return [
        f for f in map(json.loads, list(socket.sent)) if f.get("type") == frame_type
    ]


def test_dispatch_frame_submits_rpc_work_to_the_executor() -> None:
    """With an executor present the handler must not run on the caller."""
    submitted: list[object] = []

    class _RecordingExecutor(Executor):
        def submit(self, fn, /, *args, **kwargs):  # type: ignore[override]
            submitted.append(fn)
            return Future()

    ran: list[bool] = []
    dispatch_frame(
        {"type": "rpc-request", "method": "git-log", "params": {}, "corr_id": "c1"},
        on_spawn_request=lambda: None,
        send_pong=lambda: None,
        on_rpc_request=lambda frame: ran.append(True) or {},
        send_rpc_response=lambda corr_id, result: None,
        rpc_executor=_RecordingExecutor(),
    )

    assert len(submitted) == 1
    assert ran == []  # deferred to the pool, not run on the receive loop


def test_dispatch_frame_runs_inline_when_the_executor_is_shut_down() -> None:
    """Racing daemon shutdown must answer the call, not drop it."""
    from concurrent.futures import ThreadPoolExecutor

    executor = ThreadPoolExecutor(max_workers=1)
    executor.shutdown()
    sent: list[tuple[str, dict]] = []

    dispatch_frame(
        {"type": "rpc-request", "method": "git-log", "params": {}, "corr_id": "c2"},
        on_spawn_request=lambda: None,
        send_pong=lambda: None,
        on_rpc_request=lambda frame: {"ok": True},
        send_rpc_response=lambda corr_id, result: sent.append((corr_id, result)),
        rpc_executor=executor,
    )

    assert sent == [("c2", {"ok": True})]


def test_a_slow_rpc_handler_does_not_delay_the_pong() -> None:
    """The regression this refactor exists to prevent: a handler that takes
    longer than the server's ping deadline must not cost us the connection."""
    release = threading.Event()
    recv_block = threading.Event()
    socket = _FakeSocket(
        [_SERVER_INFO, _rpc_frame("slow"), json.dumps({"type": "ping"})],
        recv_block=recv_block,
    )
    client = _client(
        socket,
        on_rpc_request=lambda frame: (release.wait(5.0), {"ok": True})[1],
        rpc_methods=["git-log"],
    )
    server = threading.Thread(target=client._connect_and_serve, daemon=True)
    server.start()
    try:
        assert _wait_for(lambda: _frames_of_type(socket, "pong"))
        # The pong is out while the handler is still stuck.
        assert _frames_of_type(socket, "rpc-response") == []
        release.set()
        assert _wait_for(lambda: _frames_of_type(socket, "rpc-response"))
    finally:
        release.set()
        recv_block.set()
        server.join(5.0)
        client.stop()


def test_concurrent_rpc_requests_are_served_in_parallel() -> None:
    """Two calls must overlap. The barrier only clears if both handlers are in
    flight at once — serialized execution times it out, breaking the barrier
    and surfacing as an `error` result."""
    barrier = threading.Barrier(2, timeout=5.0)
    recv_block = threading.Event()
    socket = _FakeSocket(
        [_SERVER_INFO, _rpc_frame("a"), _rpc_frame("b")], recv_block=recv_block
    )
    client = _client(
        socket,
        on_rpc_request=lambda frame: {"seen": barrier.wait()},
        rpc_methods=["git-log"],
    )
    server = threading.Thread(target=client._connect_and_serve, daemon=True)
    server.start()
    try:
        assert _wait_for(lambda: len(_frames_of_type(socket, "rpc-response")) == 2)
        responses = _frames_of_type(socket, "rpc-response")
        assert {r["corr_id"] for r in responses} == {"a", "b"}
        assert all("error" not in r["result"] for r in responses)
    finally:
        recv_block.set()
        server.join(5.0)
        client.stop()


def test_concurrent_rpc_responses_are_never_interleaved_on_the_wire() -> None:
    """`websocket-client` sends are not thread-safe — two unsynchronized sends
    interleave their frames and corrupt both. The barrier forces both workers
    to reach `send` together; the socket records any overlap."""
    barrier = threading.Barrier(2, timeout=5.0)
    recv_block = threading.Event()
    socket = _FakeSocket(
        [_SERVER_INFO, _rpc_frame("a"), _rpc_frame("b")],
        recv_block=recv_block,
        send_delay=0.05,
    )
    client = _client(
        socket,
        on_rpc_request=lambda frame: {"seen": barrier.wait()},
        rpc_methods=["git-log"],
    )
    server = threading.Thread(target=client._connect_and_serve, daemon=True)
    server.start()
    try:
        assert _wait_for(lambda: len(_frames_of_type(socket, "rpc-response")) == 2)
        assert socket.concurrent_sends == 0
    finally:
        recv_block.set()
        server.join(5.0)
        client.stop()


def test_rpc_response_is_dropped_when_the_connection_is_already_gone() -> None:
    """A worker can outlive its connection. The late response must be dropped
    quietly — the server already failed that call with `target_disconnected`,
    and raising inside a worker would vanish into an unread Future."""
    from concurrent.futures import ThreadPoolExecutor

    release = threading.Event()
    executor = ThreadPoolExecutor(max_workers=1)
    socket = _FakeSocket([_SERVER_INFO, _rpc_frame("late")])
    client = _client(
        socket,
        on_rpc_request=lambda frame: (release.wait(5.0), {"ok": True})[1],
        rpc_methods=["git-log"],
        rpc_executor=executor,
    )

    client._connect_and_serve()  # returns on the close frame, worker still running
    release.set()
    executor.shutdown(wait=True)

    assert _frames_of_type(socket, "rpc-response") == []
