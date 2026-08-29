"""Classify SQLAlchemy IntegrityErrors that mean "the auth'd user is gone".

The agent-facing server process validates the CLI JWT by signature only, with
no DB lookup. When a user deletes their account but their CLI keeps running,
every write FK-violates `*_user_id_fkey` and 500s, polluting Sentry and
spinning the CLI's retry loop (p0-agent-jwt-no-db-validation, 2026-06-07).

The reactive fix: on FK violations naming `*_user_id_fkey`, look up the
token's `sub`; if absent in `users`, surface 401 so the CLI re-auths.

This module is the pure classifier — the FastAPI `exception_handler`
wiring lives in `servers/app.py` and supplies `user_exists` from a real DB
session.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import Request
from fastapi.responses import JSONResponse
from jose import JWTError
from sqlalchemy.exc import IntegrityError

from .agent_tokens import extract_user_id_from_token

Verdict = Literal["raise", "user_gone"]


def classify_user_fk_violation(
    exc: IntegrityError,
    authorization_header: str | None,
    user_exists: Callable[[str], bool],
) -> Verdict:
    """Decide whether to surface a FK violation as 401 "user gone" or re-raise."""
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if not constraint or not constraint.endswith("_user_id_fkey"):
        return "raise"

    sub = _extract_sub(authorization_header)
    if sub is None:
        return "raise"

    if user_exists(sub):
        return "raise"

    return "user_gone"


def make_user_gone_exception_handler(
    user_exists: Callable[[str], bool],
) -> Callable[[Request, IntegrityError], Awaitable[JSONResponse]]:
    """Build a FastAPI `exception_handler(IntegrityError)` callable.

    `user_exists(sub)` is called with the JWT subject extracted from the
    request's Authorization header. It should perform a `SELECT 1 FROM users
    WHERE id = sub` (or equivalent). Kept as an injected dependency so this
    module doesn't import the database session — and so tests can drive
    every branch without testcontainers.
    """

    async def _handler(request: Request, exc: IntegrityError) -> JSONResponse:
        verdict = classify_user_fk_violation(
            exc,
            authorization_header=request.headers.get("authorization"),
            user_exists=user_exists,
        )
        if verdict == "user_gone":
            return JSONResponse(
                status_code=401,
                content={"detail": "user no longer exists"},
            )
        raise exc

    return _handler


def _extract_sub(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None
    parts = authorization_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    try:
        return extract_user_id_from_token(parts[1])
    except JWTError:
        return None
