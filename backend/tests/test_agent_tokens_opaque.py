"""Pure unit tests for the dual-mode agent-token verifier (no DB container).

Opaque ``vic_`` keys have no signature or ``sub`` — their identity, liveness and
expiry come from the ``api_keys`` row — so these tests drive the verifier with a
tiny fake session that stands in for the row lookup. The JWT path is exercised
only at the dispatch level here; its end-to-end behaviour is covered by the
DB-backed suites.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from shared.auth import (
    TokenVerificationError,
    create_opaque_agent_token,
    is_opaque_agent_token,
    verify_agent_token,
)
from shared.auth import agent_tokens


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _FakeQuery:
    def __init__(self, row: object) -> None:
        self._row = row

    def filter(self, *a: object, **k: object) -> "_FakeQuery":
        return self

    def first(self) -> object:
        return self._row


class _FakeDB:
    """Implements just the ``.query(...).filter(...).first()`` chain used by
    ``_lookup_api_key_full``. Pass ``raise_exc`` to simulate a DB outage."""

    def __init__(self, row: object = None, raise_exc: Exception | None = None) -> None:
        self._row = row
        self._raise = raise_exc

    def query(self, *a: object, **k: object) -> _FakeQuery:
        if self._raise is not None:
            raise self._raise
        return _FakeQuery(self._row)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    agent_tokens.reset_revocation_cache()
    yield
    agent_tokens.reset_revocation_cache()


def test_token_shape_detection() -> None:
    assert is_opaque_agent_token(create_opaque_agent_token())
    assert not is_opaque_agent_token("eyJhbGciOiJSUzI1NiJ9.payload.sig")


def test_live_opaque_token_yields_principal() -> None:
    user_id = uuid4()
    token = create_opaque_agent_token()
    db = _FakeDB(row=(user_id, True, _now() + timedelta(days=30)))

    principal = verify_agent_token(token, db)

    assert principal.user_id == user_id
    assert principal.kind == "agent"


def test_opaque_token_with_null_expiry_is_accepted() -> None:
    user_id = uuid4()
    db = _FakeDB(row=(user_id, True, None))
    assert verify_agent_token(create_opaque_agent_token(), db).user_id == user_id


def test_missing_row_is_rejected() -> None:
    db = _FakeDB(row=None)
    with pytest.raises(TokenVerificationError):
        verify_agent_token(create_opaque_agent_token(), db)


def test_inactive_row_is_rejected() -> None:
    db = _FakeDB(row=(uuid4(), False, _now() + timedelta(days=30)))
    with pytest.raises(TokenVerificationError):
        verify_agent_token(create_opaque_agent_token(), db)


def test_expired_row_is_rejected() -> None:
    db = _FakeDB(row=(uuid4(), True, _now() - timedelta(seconds=1)))
    with pytest.raises(TokenVerificationError):
        verify_agent_token(create_opaque_agent_token(), db)


def test_db_error_rejects_and_never_silently_admits() -> None:
    """Unlike the JWT path (which treats a DB hiccup as 'live'), an opaque key
    has no ``sub`` fallback — a lookup failure must propagate, not admit."""
    boom = RuntimeError("db down")
    db = _FakeDB(raise_exc=boom)
    with pytest.raises(RuntimeError):
        verify_agent_token(create_opaque_agent_token(), db)


def test_positive_answer_is_cached_with_user_id() -> None:
    """A second verify inside the TTL returns from cache — no second lookup."""
    user_id = uuid4()
    token = create_opaque_agent_token()

    calls = {"n": 0}

    class _CountingDB(_FakeDB):
        def query(self, *a: object, **k: object) -> _FakeQuery:
            calls["n"] += 1
            return _FakeQuery((user_id, True, None))

    db = _CountingDB()
    assert verify_agent_token(token, db).user_id == user_id
    assert verify_agent_token(token, db).user_id == user_id
    assert calls["n"] == 1  # second call served from cache


def test_invalidate_key_cache_forces_a_reread() -> None:
    user_id = uuid4()
    token = create_opaque_agent_token()
    calls = {"n": 0}

    class _CountingDB(_FakeDB):
        def query(self, *a: object, **k: object) -> _FakeQuery:
            calls["n"] += 1
            return _FakeQuery((user_id, True, None))

    db = _CountingDB()
    verify_agent_token(token, db)
    agent_tokens.invalidate_key_cache(agent_tokens.get_token_hash(token))
    verify_agent_token(token, db)
    assert calls["n"] == 2


def test_dispatch_routes_by_token_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """``verify_agent_token`` sends ``vic_`` tokens to the opaque path and
    everything else (JWTs) to the JWT path."""
    seen: list[str] = []
    monkeypatch.setattr(
        agent_tokens, "_verify_opaque_token", lambda t, db: seen.append("opaque")
    )
    monkeypatch.setattr(
        agent_tokens, "_verify_jwt_agent_token", lambda t, db: seen.append("jwt")
    )

    verify_agent_token(create_opaque_agent_token(), None)
    verify_agent_token("eyJ.a.b", None)

    assert seen == ["opaque", "jwt"]
