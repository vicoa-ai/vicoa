"""WS handshake closes with 4401 "credential_revoked" when the user is gone.

The server's WS handler runs an ownership check at handshake time (§2.9). If
the row isn't owned by the JWT's user, it closes the socket. Pre-fix it
always used 4403 — so a daemon whose user was deleted couldn't distinguish
"the row I asked for is wrong" from "my credential is dead", and the WS
client treated the close as a transient drop and reconnected forever (the
2026-06-17 storm against the local backend).

Post-fix the handler does one extra PK lookup on the failure path: user
gone -> 4401, otherwise -> 4403. The daemon's WS client converts 4401 to
``AuthenticationError`` so the reconnect loop bails out — see the
``_raise_if_credential_revoked`` tests in test_spawn_ws_client and
test_session_ws_client for the matching client-side half.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from servers.api import ws_handler
from servers.api.ws_handler import _user_exists, ws_router
from shared.auth.tokens import TokenClaims
from shared.database.models import AgentInstance, Machine, User, UserAgent
from shared.database.session import SessionLocal

pytestmark = pytest.mark.integration

_FAKE_JWT = "header.payload.signature"


# ---------------------------------------------------------------------------
# _user_exists helper (the new PK lookup on the failure path)
# ---------------------------------------------------------------------------


@pytest.fixture
def live_user() -> Iterator[UUID]:
    user_id = uuid4()
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.commit()
    try:
        yield user_id
    finally:
        with SessionLocal() as db:
            db.query(AgentInstance).filter(AgentInstance.user_id == user_id).delete(
                synchronize_session=False
            )
            db.query(UserAgent).filter(UserAgent.user_id == user_id).delete(
                synchronize_session=False
            )
            db.query(Machine).filter(Machine.user_id == user_id).delete(
                synchronize_session=False
            )
            db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
            db.commit()


def test_user_exists_returns_true_for_live_user(live_user: UUID) -> None:
    with SessionLocal() as db:
        assert _user_exists(db, str(live_user)) is True


def test_user_exists_returns_false_for_missing_user() -> None:
    with SessionLocal() as db:
        assert _user_exists(db, str(uuid4())) is False


def test_user_exists_returns_false_for_malformed_user_id() -> None:
    with SessionLocal() as db:
        assert _user_exists(db, "not-a-uuid") is False


# ---------------------------------------------------------------------------
# WS handshake close-code selection: 4401 (user gone) vs 4403 (wrong owner)
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(ws_router)
    with TestClient(app) as test_client:
        yield test_client


def _verifier_for(user_id: UUID):
    def _verify(_token: str) -> TokenClaims:
        return TokenClaims(user_id=user_id)

    return _verify


def test_ws_handshake_closes_4401_when_user_gone(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No User row exists for the JWT subject AND no Machine row exists for the
    machine_id. Pre-fix this 4403'd, the daemon treated it as wrong-row and
    reconnected forever. Post-fix the handler PKs `users`, finds the row gone,
    and closes 4401 credential_revoked."""
    ghost_user_id = uuid4()
    ghost_machine_id = uuid4()
    monkeypatch.setattr(ws_handler, "verify_user_token", _verifier_for(ghost_user_id))

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(
            "/ws", subprotocols=["vicoa-ws", f"vicoa-supabase.{_FAKE_JWT}"]
        ) as ws:
            ws.send_json(
                {
                    "type": "hello",
                    "scope": "machine-scoped",
                    "machine_id": str(ghost_machine_id),
                }
            )
            ws.receive_json()  # close arrives here

    assert excinfo.value.code == 4401
    assert excinfo.value.reason == "credential_revoked"


def test_ws_handshake_closes_4403_when_user_alive_but_owner_wrong(
    client: TestClient,
    live_user: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User exists in `users` but doesn't own the requested machine — the
    credential is fine, the protocol is being misused. Must stay 4403 so the
    daemon's 4401-handling doesn't misinterpret it as fatal-auth."""
    monkeypatch.setattr(ws_handler, "verify_user_token", _verifier_for(live_user))
    nonexistent_machine_id = uuid4()

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(
            "/ws", subprotocols=["vicoa-ws", f"vicoa-supabase.{_FAKE_JWT}"]
        ) as ws:
            ws.send_json(
                {
                    "type": "hello",
                    "scope": "machine-scoped",
                    "machine_id": str(nonexistent_machine_id),
                }
            )
            ws.receive_json()

    assert excinfo.value.code == 4403
