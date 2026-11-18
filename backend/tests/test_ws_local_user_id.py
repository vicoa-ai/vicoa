"""A browser socket is keyed by the `users.id` the dashboard API resolves.

When an identity-provider account is re-created with the same email (deleted,
then signed up again), the provider issues a new id while the dashboard API
keeps serving the older row (`find_local_user`). The user's machines, sessions
and daemon API keys all carry the row's id, and a socket's rooms and RPC
routing are keyed by the id it was given at the handshake. So the socket must
get the row's id too: with the token's id the dashboard showed the user's
machine online while every RPC to it failed with `no_handler`.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from servers.api import ws_handler
from servers.api.ws_handler import ws_router
from shared.auth.tokens import TokenClaims
from shared.database.models import User
from shared.database.session import SessionLocal
from shared.database.users import find_local_user

pytestmark = pytest.mark.integration

_FAKE_JWT = "header.payload.signature"


@pytest.fixture
def existing_row() -> Iterator[tuple[UUID, str]]:
    """A `users` row, as `(id, email)`."""
    row_id = uuid4()
    email = f"{row_id}@test.vicoa"
    with SessionLocal() as db:
        db.add(User(id=row_id, email=email, display_name="t"))
        db.commit()
    try:
        yield row_id, email
    finally:
        with SessionLocal() as db:
            db.query(User).filter(User.id == row_id).delete(synchronize_session=False)
            db.commit()


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(ws_router)
    with TestClient(app) as test_client:
        yield test_client


def _token_for(user_id: UUID, email: str | None):
    def _verify(_token: str) -> TokenClaims:
        return TokenClaims(user_id=user_id, email=email)

    return _verify


def _handshake_user_id(client: TestClient) -> str:
    with client.websocket_connect(
        "/ws", subprotocols=["vicoa-ws", f"vicoa-supabase.{_FAKE_JWT}"]
    ) as ws:
        ws.send_json({"type": "hello", "scope": "user-scoped"})
        info = ws.receive_json()
    assert info["type"] == "server_info"
    return info["body"]["user_id"]


# ---------------------------------------------------------------------------
# find_local_user
# ---------------------------------------------------------------------------


def test_find_local_user_matches_the_id_first(existing_row: tuple[UUID, str]) -> None:
    row_id, _email = existing_row
    with SessionLocal() as db:
        user = find_local_user(db, row_id, f"{uuid4()}@test.vicoa")
    assert user is not None and user.id == row_id


def test_find_local_user_falls_back_to_the_email(
    existing_row: tuple[UUID, str],
) -> None:
    row_id, email = existing_row
    with SessionLocal() as db:
        user = find_local_user(db, uuid4(), email)
    assert user is not None and user.id == row_id


def test_find_local_user_without_a_match_is_none() -> None:
    with SessionLocal() as db:
        assert find_local_user(db, uuid4(), None) is None
        assert find_local_user(db, uuid4(), f"{uuid4()}@test.vicoa") is None


# ---------------------------------------------------------------------------
# The handshake
# ---------------------------------------------------------------------------


def test_handshake_keeps_the_token_id_of_an_existing_row(
    client: TestClient,
    existing_row: tuple[UUID, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row_id, email = existing_row
    monkeypatch.setattr(ws_handler, "verify_user_token", _token_for(row_id, email))

    assert _handshake_user_id(client) == str(row_id)


def test_handshake_takes_the_row_id_for_a_recreated_account(
    client: TestClient,
    existing_row: tuple[UUID, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new provider id with the row's email: the socket gets the row's id,
    the same row the dashboard API serves this token."""
    row_id, email = existing_row
    monkeypatch.setattr(ws_handler, "verify_user_token", _token_for(uuid4(), email))

    assert _handshake_user_id(client) == str(row_id)


def test_handshake_keeps_the_token_id_before_the_row_exists(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A new account whose row the dashboard API has not created yet keeps
    its own id, and the handshake does not create the row: creating it is
    the dashboard's, where signup side effects hang off it."""
    token_id = uuid4()
    monkeypatch.setattr(
        ws_handler,
        "verify_user_token",
        _token_for(token_id, f"{token_id}@test.vicoa"),
    )

    assert _handshake_user_id(client) == str(token_id)
    with SessionLocal() as db:
        assert db.get(User, token_id) is None
