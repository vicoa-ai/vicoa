"""Behavioral tests for the agent-token FK→401 classifier (p0-agent-jwt-no-db-validation).

The server process used to 500 on every write a deleted user's still-running
CLI made — one user, 88 events in 8 minutes (FLASK-1M/1N/1P family,
2026-06-07). The fix: on FK violations that name `*_user_id_fkey`, look up
the token's sub; if the user is gone, surface 401 so the CLI re-auths
instead of looping 500s through Sentry.

This file tests the pure classification layer. The wiring as a FastAPI
`@app.exception_handler(IntegrityError)` is exercised separately.
"""

from __future__ import annotations

import base64
import json

from fastapi import FastAPI
from sqlalchemy.exc import IntegrityError
from starlette.testclient import TestClient

from shared.auth.user_fk import (
    classify_user_fk_violation,
    make_user_gone_exception_handler,
)


class _FakeDiag:
    def __init__(self, constraint_name: str | None) -> None:
        self.constraint_name = constraint_name


class _FakePgError(Exception):
    """Minimal stand-in for psycopg2's DatabaseError that exposes `.diag`."""

    def __init__(self, constraint_name: str | None) -> None:
        super().__init__(constraint_name or "")
        self.diag = _FakeDiag(constraint_name)


def _integrity_error(constraint_name: str | None) -> IntegrityError:
    return IntegrityError(
        statement="INSERT INTO ...",
        params={},
        orig=_FakePgError(constraint_name),
    )


def _bearer(sub: str) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"RS256","typ":"JWT"}').rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).rstrip(b"=")
    return f"Bearer {header.decode()}.{payload.decode()}.sig"


def _always_absent(_: str) -> bool:
    return False


def test_returns_user_gone_when_user_id_fkey_violation_and_user_absent() -> None:
    exc = _integrity_error("machines_user_id_fkey")

    result = classify_user_fk_violation(
        exc,
        authorization_header=_bearer("00000000-0000-0000-0000-000000000001"),
        user_exists=_always_absent,
    )

    assert result == "user_gone"


def test_raises_when_user_id_fkey_violation_but_user_still_exists() -> None:
    """Don't mask real bugs. If the user row is present, the FK violation
    came from somewhere else (race, stale request) — let it 500 so it's
    visible in Sentry."""
    exc = _integrity_error("machines_user_id_fkey")

    result = classify_user_fk_violation(
        exc,
        authorization_header=_bearer("00000000-0000-0000-0000-000000000001"),
        user_exists=lambda _: True,
    )

    assert result == "raise"


def test_raises_when_constraint_is_not_a_user_id_fkey() -> None:
    """A unique violation or a different FK (e.g. agent_instance_id_fkey) is
    not ours to convert. Re-raise so the existing handlers see it."""
    for unrelated in (
        "api_keys_pkey",  # unique
        "messages_agent_instance_id_fkey",  # different FK
        "users_email_key",  # unique on a different column
        None,  # no constraint name at all
    ):
        exc = _integrity_error(unrelated)
        result = classify_user_fk_violation(
            exc,
            authorization_header=_bearer("00000000-0000-0000-0000-000000000001"),
            user_exists=_always_absent,
        )
        assert result == "raise", f"unexpected for constraint={unrelated!r}"


def test_raises_when_authorization_header_is_missing_or_unparseable() -> None:
    """Without a Bearer token we can't decide who the request claims to be —
    re-raise. (In practice the auth dependency would have already 401'd
    these; this is defensive.)"""
    exc = _integrity_error("machines_user_id_fkey")
    for header in (
        None,
        "",
        "Basic dXNlcjpwYXNz",  # wrong scheme
        "Bearer",  # no token
        "Bearer not-a-jwt-at-all",  # token can't be decoded
    ):
        result = classify_user_fk_violation(
            exc,
            authorization_header=header,
            user_exists=_always_absent,
        )
        assert result == "raise", f"unexpected for header={header!r}"


# --- wiring as a FastAPI exception handler ---


def _app_that_raises(constraint_name: str, user_exists) -> FastAPI:
    app = FastAPI()
    app.exception_handler(IntegrityError)(make_user_gone_exception_handler(user_exists))

    @app.post("/raise-fk")
    async def _raise() -> None:
        raise _integrity_error(constraint_name)

    return app


def test_handler_converts_user_gone_fk_to_401_via_test_client() -> None:
    app = _app_that_raises("machines_user_id_fkey", user_exists=_always_absent)

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(
            "/raise-fk",
            headers={"Authorization": _bearer("00000000-0000-0000-0000-000000000001")},
        )

    assert r.status_code == 401
    assert r.json() == {"detail": "user no longer exists"}


def test_handler_lets_unrelated_integrity_errors_through_as_500() -> None:
    """If the FK isn't *_user_id_fkey, the handler must not swallow it — the
    error should propagate so the existing 500 path stays visible."""
    app = _app_that_raises("api_keys_pkey", user_exists=_always_absent)

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(
            "/raise-fk",
            headers={"Authorization": _bearer("00000000-0000-0000-0000-000000000001")},
        )

    assert r.status_code == 500
