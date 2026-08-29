"""Endpoint tests for the /ws handshake and the broadcast bridge (Phase 1).

These cover the paths that need no database — token auth, the hello handshake,
server_info, and the _internal/broadcast receiver. The session/machine-scoped
ownership checks (§2.9) need Postgres and are exercised in CI.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from jose import jwt as jose_jwt
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from shared.auth.tokens import TokenClaims, TokenVerificationError
from shared.auth.ws import WsAuthError, WsCredentials
from shared.config import settings
from shared.websocket.connection_manager import Connection, connection_manager
from servers.api import ws_handler
from servers.api.ws_handler import ws_router

_FAKE_JWT = "header.payload.signature"

# An RS256 keypair for signing test agent (vicoa-key) tokens.
_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_AGENT_PRIVATE_PEM = _RSA_KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
_AGENT_PUBLIC_PEM = (
    _RSA_KEY.public_key()
    .public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    .decode()
)


def _agent_token(claims: dict) -> str:
    return jose_jwt.encode(claims, _AGENT_PRIVATE_PEM, algorithm="RS256")


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(ws_router)
    with TestClient(app) as test_client:
        yield test_client


def _supabase_returns(user_id: UUID):
    def _verify(token: str) -> TokenClaims:
        return TokenClaims(user_id=user_id)

    return _verify


def test_verify_credentials_accepts_a_supabase_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    monkeypatch.setattr(ws_handler, "verify_user_token", _supabase_returns(user_id))

    result = ws_handler.verify_ws_credentials(
        WsCredentials("vicoa-supabase", _FAKE_JWT, None)
    )

    assert result == str(user_id)


def test_verify_credentials_accepts_a_signed_agent_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "jwt_public_key", _AGENT_PUBLIC_PEM)
    # Signature-only assertion; the `api_keys` revocation check has its own
    # tests (src/backend/tests/test_agent_tokens.py) and would need a database.
    monkeypatch.setattr(settings, "enforce_api_key_revocation", False)
    user_id = uuid4()
    token = _agent_token({"sub": str(user_id)})

    result = ws_handler.verify_ws_credentials(WsCredentials("vicoa-key", token, None))

    assert result == str(user_id)


def test_verify_credentials_rejects_a_malformed_agent_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "jwt_public_key", _AGENT_PUBLIC_PEM)

    with pytest.raises(WsAuthError):
        ws_handler.verify_ws_credentials(WsCredentials("vicoa-key", "not.a.jwt", None))


def test_verify_credentials_rejects_an_agent_token_without_sub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "jwt_public_key", _AGENT_PUBLIC_PEM)
    token = _agent_token({"role": "agent"})

    with pytest.raises(WsAuthError, match="sub"):
        ws_handler.verify_ws_credentials(WsCredentials("vicoa-key", token, None))


def test_user_scoped_connection_receives_server_info(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = uuid4()
    monkeypatch.setattr(ws_handler, "verify_user_token", _supabase_returns(user_id))

    with client.websocket_connect(
        "/ws", subprotocols=["vicoa-ws", f"vicoa-supabase.{_FAKE_JWT}"]
    ) as ws:
        ws.send_json({"type": "hello", "scope": "user-scoped"})
        info = ws.receive_json()

    assert info["type"] == "server_info"
    assert info["body"]["user_id"] == str(user_id)


def test_connection_without_credentials_is_rejected(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", subprotocols=["vicoa-ws"]):
            pass


def test_invalid_supabase_token_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _reject(token: str) -> TokenClaims:
        raise TokenVerificationError("bad token")

    monkeypatch.setattr(ws_handler, "verify_user_token", _reject)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/ws", subprotocols=["vicoa-ws", f"vicoa-supabase.{_FAKE_JWT}"]
        ):
            pass


def test_disallowed_origin_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ws_handler, "verify_user_token", _supabase_returns(uuid4()))

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/ws",
            subprotocols=["vicoa-ws", f"vicoa-supabase.{_FAKE_JWT}"],
            headers={"origin": "https://evil.example"},
        ):
            pass


def test_internal_broadcast_requires_the_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "internal_broadcast_token", "the-secret")
    body = {"user_id": "u1", "payload": {}, "rooms": []}

    assert client.post("/_internal/broadcast", json=body).status_code == 401
    assert (
        client.post(
            "/_internal/broadcast",
            json=body,
            headers={"Authorization": "Bearer wrong"},
        ).status_code
        == 401
    )


def test_internal_broadcast_delivers_to_a_registered_connection(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "internal_broadcast_token", "the-secret")
    conn = Connection(
        connection_id=uuid4().hex,
        user_id="u-bcast",
        scope="user-scoped",
        rooms=frozenset({"user:u-bcast:user-scoped"}),
    )
    connection_manager.register(conn)
    try:
        response = client.post(
            "/_internal/broadcast",
            json={
                "user_id": "u-bcast",
                "payload": {"entity": "messages"},
                "rooms": ["user:u-bcast:user-scoped"],
            },
            headers={"Authorization": "Bearer the-secret"},
        )
        assert response.status_code == 200
        assert conn.outbox.get_nowait() == {
            "type": "update",
            "payload": {"entity": "messages"},
        }
    finally:
        connection_manager.unregister(conn)
