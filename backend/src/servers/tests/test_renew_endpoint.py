"""DB-backed tests for the in-place key-renewal endpoint.

The daemon calls ``POST /api/v1/auth/api-keys/current/renew`` with its own
opaque key. The server extends ``expires_at`` in place, but only when the key
has fewer than ``RENEW_THRESHOLD_DAYS`` left — so the token string never changes
and a healthy key is left untouched. Verification of the presented key runs for
real against the test DB (no auth override), so a revoked key is rejected.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.auth import get_token_hash
from shared.auth.agent_tokens import (
    RENEW_EXTENSION_DAYS,
    RENEW_THRESHOLD_DAYS,
    create_opaque_agent_token,
    reset_revocation_cache,
)
from shared.database.models import APIKey, User
from shared.database.session import get_db
from servers.api.auth_keys import auth_keys_router


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def client(test_db):
    """Minimal app mounting only the renew router; auth runs for real so the
    presented bearer must resolve to a live ``api_keys`` row in ``test_db``."""
    app = FastAPI()
    app.include_router(auth_keys_router, prefix="/api/v1")

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    reset_revocation_cache()
    return TestClient(app)


def _make_key(test_db, expires_at) -> str:
    """Insert a live opaque key with the given expiry; return the raw token."""
    user = test_db.query(User).first()
    raw = create_opaque_agent_token()
    test_db.add(
        APIKey(
            id=uuid4(),
            user_id=user.id,
            name="CLI Key",
            api_key_hash=get_token_hash(raw),
            api_key="vic_masked…",
            is_active=True,
            expires_at=expires_at,
            created_at=_now(),
        )
    )
    test_db.commit()
    return raw


def _auth(raw: str) -> dict:
    return {"Authorization": f"Bearer {raw}"}


def test_key_within_threshold_is_renewed(test_db, client):
    raw = _make_key(test_db, _now() + timedelta(days=3))

    resp = client.post("/api/v1/auth/api-keys/current/renew", headers=_auth(raw))

    assert resp.status_code == 200
    body = resp.json()
    assert body["renewed"] is True
    new_expiry = datetime.fromisoformat(body["expires_at"])
    assert (new_expiry - _now()).days >= RENEW_EXTENSION_DAYS - 1

    row = test_db.query(APIKey).filter(APIKey.api_key_hash == get_token_hash(raw)).one()
    test_db.refresh(row)
    assert (row.expires_at.replace(tzinfo=timezone.utc) - _now()).days >= (
        RENEW_EXTENSION_DAYS - 1
    )


def test_key_outside_threshold_is_untouched(test_db, client):
    far = _now() + timedelta(days=RENEW_THRESHOLD_DAYS + 30)
    raw = _make_key(test_db, far)

    resp = client.post("/api/v1/auth/api-keys/current/renew", headers=_auth(raw))

    assert resp.status_code == 200
    assert resp.json()["renewed"] is False

    row = test_db.query(APIKey).filter(APIKey.api_key_hash == get_token_hash(raw)).one()
    test_db.refresh(row)
    # Unchanged (within a couple of seconds of the original far-off expiry).
    stored = row.expires_at.replace(tzinfo=timezone.utc)
    assert abs((stored - far).total_seconds()) < 2


def test_no_expiry_key_is_left_null(test_db, client):
    raw = _make_key(test_db, None)

    resp = client.post("/api/v1/auth/api-keys/current/renew", headers=_auth(raw))

    assert resp.status_code == 200
    body = resp.json()
    assert body["renewed"] is False
    assert body["expires_at"] is None


def test_revoked_key_is_rejected(test_db, client):
    raw = _make_key(test_db, _now() + timedelta(days=3))
    row = test_db.query(APIKey).filter(APIKey.api_key_hash == get_token_hash(raw)).one()
    row.is_active = False
    test_db.commit()
    reset_revocation_cache()

    resp = client.post("/api/v1/auth/api-keys/current/renew", headers=_auth(raw))
    assert resp.status_code == 401


def test_unknown_key_is_rejected(client):
    resp = client.post(
        "/api/v1/auth/api-keys/current/renew",
        headers=_auth(create_opaque_agent_token()),
    )
    assert resp.status_code == 401
