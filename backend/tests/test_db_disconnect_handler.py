"""A transient database disconnect must not crash the handler on `/ws`.

The `SAOperationalError` handler used to read `request.method`. For a `/ws`
connection Starlette passes a `WebSocket`, which has no `.method`, so the
handler itself raised `AttributeError`: the real cause (a flycast disconnect)
was hidden behind it and the error was reported as unhandled. A WebSocket
handler's return value is also awaited as an ASGI response, so the HTTP 503
`JSONResponse` was never right there either.

Post-fix: HTTP still answers 503 + Retry-After; a WebSocket is closed with 1013
("try again later") through `_safe_close`, in whatever state the socket is in.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI, WebSocket
from psycopg2 import OperationalError as Psycopg2OperationalError
from sqlalchemy.exc import OperationalError as SAOperationalError
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from servers.db_disconnect import on_db_disconnect


def _disconnect() -> SAOperationalError:
    """The error a flycast proxy reset surfaces as."""
    return SAOperationalError(
        "SELECT 1",
        {},
        Psycopg2OperationalError("server closed the connection unexpectedly"),
    )


def _not_a_disconnect() -> SAOperationalError:
    """A real database failure the handler must not swallow."""
    return SAOperationalError(
        "SELECT 1", {}, Psycopg2OperationalError("password authentication failed")
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.exception_handler(SAOperationalError)(on_db_disconnect)

    @app.get("/http-disconnect")
    async def http_disconnect() -> None:
        raise _disconnect()

    @app.get("/http-other")
    async def http_other() -> None:
        raise _not_a_disconnect()

    @app.websocket("/ws-before-accept")
    async def ws_before_accept(websocket: WebSocket) -> None:
        # e.g. the credential check hitting the database before `accept()`
        raise _disconnect()

    @app.websocket("/ws-after-accept")
    async def ws_after_accept(websocket: WebSocket) -> None:
        # e.g. the ownership check or the serve loop after the handshake
        await websocket.accept()
        raise _disconnect()

    @app.websocket("/ws-already-closed")
    async def ws_already_closed(websocket: WebSocket) -> None:
        # Another close path won the race before the error escaped.
        await websocket.accept()
        await websocket.close(code=4400)
        raise _disconnect()

    @app.websocket("/ws-other")
    async def ws_other(websocket: WebSocket) -> None:
        await websocket.accept()
        raise _not_a_disconnect()

    with TestClient(app) as test_client:
        yield test_client


def test_http_disconnect_answers_503_with_retry_after(client: TestClient) -> None:
    response = client.get("/http-disconnect")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.json() == {
        "detail": "Database temporarily unavailable, please retry."
    }


def test_http_error_that_is_not_a_disconnect_is_not_swallowed(
    client: TestClient,
) -> None:
    with pytest.raises(SAOperationalError, match="password authentication failed"):
        client.get("/http-other")


def test_ws_disconnect_after_accept_closes_try_again_later(
    client: TestClient,
) -> None:
    """Pre-fix: `AttributeError: 'WebSocket' object has no attribute 'method'`."""
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws-after-accept") as ws:
            ws.receive_json()  # the close arrives here

    assert excinfo.value.code == 1013
    assert excinfo.value.reason == "db_unavailable"


def test_ws_disconnect_before_accept_rejects_the_handshake(
    client: TestClient,
) -> None:
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws-before-accept"):
            pass

    assert excinfo.value.code == 1013


def test_ws_disconnect_on_an_already_closed_socket_is_left_alone(
    client: TestClient,
) -> None:
    """`_safe_close` must not send a second close frame: the client keeps the
    code of the close that won the race, and nothing is raised."""
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws-already-closed") as ws:
            ws.receive_json()

    assert excinfo.value.code == 4400


def test_ws_error_that_is_not_a_disconnect_is_not_swallowed(
    client: TestClient,
) -> None:
    """Not a transient disconnect: the handler re-raises, so the server still
    sees the real error instead of a quiet 1013 that would hide it."""
    with pytest.raises(SAOperationalError, match="password authentication failed"):
        with client.websocket_connect("/ws-other") as ws:
            ws.receive_json()
