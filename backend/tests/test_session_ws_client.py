"""Behavioral tests for the CLI-wrapper session WebSocket client (Phase 3).

The connection loop is integration-tested; these cover the pure pieces — the
catch-up buffer that holds live `new-message` frames until the
`fetch_messages_response` arrives (§2.6) and the frame dispatch.
"""

import json

import pytest

from vicoa.sdk.exceptions import AuthenticationError
from vicoa.session_ws_client import CatchUpBuffer, SessionMessagesWsClient


def test_run_reraises_authentication_error_instead_of_reconnecting() -> None:
    """A 401 surfaced inside the loop is fatal-auth: ``run()`` must re-raise so
    the owner tears down, not swallow it into the reconnect backoff. Safety
    counter raises KeyboardInterrupt on the 2nd connect to bound a regression."""
    calls = {"n": 0}

    def connect_fn(*a, **k):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise KeyboardInterrupt
        raise AuthenticationError("401")

    client = SessionMessagesWsClient(
        ws_url="wss://agents.example/ws",
        api_key="k",
        instance_id="i1",
        on_user_message=lambda body: None,
        connect_fn=connect_fn,
    )

    with pytest.raises(AuthenticationError):
        client.run()
    assert calls["n"] == 1  # did not reconnect after the 401


def test_request_refetch_sends_fetch_on_live_socket_else_noop() -> None:
    """``request_refetch`` re-issues the watermark catch-up on the live socket
    (so a dropped backend→server broadcast self-heals) and is a safe no-op when
    disconnected."""
    sent: list[dict] = []

    class _FakeSocket:
        def send(self, raw: str) -> None:
            sent.append(json.loads(raw))

    client = SessionMessagesWsClient(
        ws_url="wss://agents.example/ws",
        api_key="k",
        instance_id="i1",
        on_user_message=lambda body: None,
    )

    # Disconnected → no send, no raise.
    client.request_refetch()
    assert sent == []

    # Connected → one fetch_messages_request carrying the current watermark.
    client._socket = _FakeSocket()
    client._watermark = {"created_at": "2026-01-01T00:00:00Z"}
    client.request_refetch()

    assert len(sent) == 1
    assert sent[0]["type"] == "fetch_messages_request"
    assert sent[0]["instance_id"] == "i1"
    assert sent[0]["after"] == {"created_at": "2026-01-01T00:00:00Z"}


def test_buffered_live_message_is_emitted_after_catch_up_completes() -> None:
    # A live new-message that arrives mid-fetch is held back, then released
    # after the catch-up rows so the client renders history in order (§2.6).
    buf = CatchUpBuffer()

    assert buf.buffer_live({"id": "m3", "content": "live"}) == []

    emitted = buf.complete_fetch([{"id": "m1"}, {"id": "m2"}])

    assert [body["id"] for body in emitted] == ["m1", "m2", "m3"]


def test_catch_up_does_not_redeliver_a_message_already_seen_live() -> None:
    # The safety-window re-fetch overlaps messages the client already saw
    # live; dedupe by id, first-write-wins (§2.6 append-only merge).
    buf = CatchUpBuffer()
    buf.buffer_live({"id": "m2", "content": "live"})

    emitted = buf.complete_fetch([{"id": "m1"}, {"id": "m2"}])

    assert [body["id"] for body in emitted] == ["m1", "m2"]


def test_live_message_after_catch_up_is_emitted_immediately() -> None:
    buf = CatchUpBuffer()
    buf.complete_fetch([{"id": "m1"}])

    emitted = buf.buffer_live({"id": "m2", "content": "live"})

    assert [body["id"] for body in emitted] == ["m2"]


def test_live_message_after_catch_up_is_still_deduped() -> None:
    buf = CatchUpBuffer()
    buf.complete_fetch([{"id": "m1"}])

    assert buf.buffer_live({"id": "m1"}) == []  # already delivered by catch-up
    assert [b["id"] for b in buf.buffer_live({"id": "m2"})] == ["m2"]


def test_begin_catch_up_resumes_buffering_but_keeps_seen_ids() -> None:
    # On reconnect the watermark re-fetch overlaps already-delivered
    # messages; the seen-id set must survive so they are not re-delivered.
    buf = CatchUpBuffer()
    buf.complete_fetch([{"id": "m1"}])

    buf.begin_catch_up()  # reconnect: a new catch-up cycle starts

    assert buf.buffer_live({"id": "m2"}) == []  # buffering again
    emitted = buf.complete_fetch([{"id": "m1"}, {"id": "m2"}])
    assert [body["id"] for body in emitted] == ["m2"]  # m1 still deduped


# --- SessionMessagesWsClient (connection loop, fake-socket driven) ---

_SERVER_INFO = json.dumps({"type": "server_info", "body": {}})


class _FakeSocket:
    """A WebSocket stand-in mirroring the ``recv_data(control_frame=False)``
    slice of ``websocket-client`` the production code uses. See the same
    class in test_spawn_ws_client.py for the rationale.
    """

    def __init__(
        self,
        incoming: list[str],
        close_code: int | None = None,
        close_reason: str = "",
    ) -> None:
        self._incoming = list(incoming)
        self._close_code = close_code
        self._close_reason = close_reason
        self.sent: list[str] = []

    def send(self, data: str) -> None:
        self.sent.append(data)

    def recv_data(self, control_frame: bool = False) -> tuple[int, bytes]:
        if self._incoming:
            return (1, self._incoming.pop(0).encode("utf-8"))
        if self._close_code is None:
            return (8, b"")
        payload = self._close_code.to_bytes(2, "big") + self._close_reason.encode(
            "utf-8"
        )
        return (8, payload)

    def close(self) -> None:
        return None


def _fetch_response(rows: list[dict]) -> str:
    return json.dumps(
        {"type": "fetch_messages_response", "request_id": "catch-up", "rows": rows}
    )


def _new_message_frame(body: dict) -> str:
    return json.dumps(
        {"type": "update", "payload": {"body": {"t": "new-message", **body}}}
    )


def _client(socket: _FakeSocket, **overrides: object) -> SessionMessagesWsClient:
    kwargs: dict[str, object] = {
        "ws_url": "wss://agents.vicoa.ai/ws",
        "api_key": "secret-key",
        "instance_id": "i1",
        "cli_version": "9.9.9",
        "on_user_message": lambda body: None,
        "connect_fn": lambda *a, **k: socket,
    }
    kwargs.update(overrides)
    return SessionMessagesWsClient(**kwargs)  # type: ignore[arg-type]


def test_client_sends_hello_and_fetch_then_delivers_catch_up_messages() -> None:
    delivered: list[dict] = []
    socket = _FakeSocket(
        [
            _SERVER_INFO,
            _fetch_response(
                [{"id": "m1", "content": "hi", "created_at": "2026-05-21T12:00:00"}]
            ),
        ]
    )
    client = _client(socket, on_user_message=lambda body: delivered.append(body))

    client._connect_and_serve()

    sent = [json.loads(frame) for frame in socket.sent]
    assert sent[0] == {
        "type": "hello",
        "scope": "session-scoped",
        "instance_id": "i1",
    }
    assert sent[1]["type"] == "fetch_messages_request"
    assert sent[1]["instance_id"] == "i1"
    assert [body["id"] for body in delivered] == ["m1"]


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


def test_live_update_before_catch_up_response_is_delivered_after_it() -> None:
    delivered: list[dict] = []
    socket = _FakeSocket(
        [
            _SERVER_INFO,
            _new_message_frame({"id": "m2", "created_at": "2026-05-21T12:02:00"}),
            _fetch_response([{"id": "m1", "created_at": "2026-05-21T12:00:00"}]),
        ]
    )

    _client(
        socket, on_user_message=lambda body: delivered.append(body)
    )._connect_and_serve()

    assert [body["id"] for body in delivered] == ["m1", "m2"]


def test_client_replies_to_a_server_ping_with_a_pong() -> None:
    socket = _FakeSocket([_SERVER_INFO, json.dumps({"type": "ping"})])

    _client(socket)._connect_and_serve()

    assert json.loads(socket.sent[-1]) == {"type": "pong"}


def test_watermark_advances_to_the_latest_delivered_message() -> None:
    socket = _FakeSocket(
        [
            _SERVER_INFO,
            _fetch_response(
                [
                    {"id": "m1", "created_at": "2026-05-21T12:00:00"},
                    {"id": "m2", "created_at": "2026-05-21T12:05:00"},
                ]
            ),
        ]
    )
    client = _client(socket)

    client._connect_and_serve()

    assert client.watermark == {"created_at": "2026-05-21T12:05:00"}


def test_reconnect_sends_the_advanced_watermark_in_the_fetch_request() -> None:
    socket1 = _FakeSocket(
        [
            _SERVER_INFO,
            _fetch_response([{"id": "m1", "created_at": "2026-05-21T12:00:00"}]),
        ]
    )
    socket2 = _FakeSocket([_SERVER_INFO])
    queue = [socket1, socket2]
    client = _client(socket1, connect_fn=lambda *a, **k: queue.pop(0))

    client._connect_and_serve()  # first connection delivers m1
    client._connect_and_serve()  # reconnect

    reconnect_fetch = json.loads(socket2.sent[1])
    assert reconnect_fetch["after"] == {"created_at": "2026-05-21T12:00:00"}


def test_wait_until_ready_returns_false_before_fetch_response() -> None:
    # Before the catch-up response arrives, callers wanting to POST a message
    # and have it routed back must wait — otherwise the broadcast can land in
    # the subscribe/catch-up gap and be dropped.
    client = _client(_FakeSocket([]))

    assert client.wait_until_ready(0.01) is False


def test_wait_until_ready_is_set_after_catch_up_response() -> None:
    socket = _FakeSocket(
        [
            _SERVER_INFO,
            _fetch_response([{"id": "m1", "created_at": "2026-05-21T12:00:00"}]),
        ]
    )
    client = _client(socket)

    client._connect_and_serve()

    assert client.wait_until_ready(0.01) is True


def test_wait_until_ready_clears_on_reconnect_until_next_response() -> None:
    socket1 = _FakeSocket(
        [
            _SERVER_INFO,
            _fetch_response([{"id": "m1", "created_at": "2026-05-21T12:00:00"}]),
        ]
    )
    socket2 = _FakeSocket([_SERVER_INFO])  # no fetch response
    queue = [socket1, socket2]
    client = _client(socket1, connect_fn=lambda *a, **k: queue.pop(0))

    client._connect_and_serve()
    assert client.wait_until_ready(0.01) is True

    client._connect_and_serve()  # reconnect: catch-up restarts, no response
    assert client.wait_until_ready(0.01) is False


def test_resync_required_refetches_without_a_watermark() -> None:
    socket = _FakeSocket(
        [
            _SERVER_INFO,
            json.dumps(
                {
                    "type": "resync_required",
                    "request_id": "catch-up",
                    "entity": "messages",
                    "reason": "missing_history",
                }
            ),
        ]
    )
    client = _client(socket, initial_watermark={"created_at": "2026-05-21T12:00:00"})

    client._connect_and_serve()

    fetches = [
        json.loads(frame)
        for frame in socket.sent
        if json.loads(frame)["type"] == "fetch_messages_request"
    ]
    assert fetches[0]["after"] == {"created_at": "2026-05-21T12:00:00"}
    assert fetches[1]["after"] is None
    assert client.watermark is None


# ---------------------------------------------------------------------------
# Credential-revoked close (4401): same shape as spawn_ws_client — fatal-auth,
# not a transient drop. Run() re-raises out of its reconnect loop.
# ---------------------------------------------------------------------------


def test_session_connect_and_serve_raises_on_4401_close_during_handshake() -> None:
    socket = _FakeSocket(
        incoming=[], close_code=4401, close_reason="credential_revoked"
    )
    with pytest.raises(AuthenticationError):
        _client(socket)._connect_and_serve()


def test_session_connect_and_serve_raises_on_4401_close_in_serve_loop() -> None:
    socket = _FakeSocket(
        incoming=[_SERVER_INFO], close_code=4401, close_reason="credential_revoked"
    )
    with pytest.raises(AuthenticationError):
        _client(socket)._connect_and_serve()


def test_session_connect_and_serve_returns_silently_on_non_4401_close() -> None:
    for code in (None, 1001, 1006, 1008, 4400, 4403):
        socket = _FakeSocket(incoming=[], close_code=code)
        _client(socket)._connect_and_serve()  # returns, not raises
