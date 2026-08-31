"""In-place renewal for the presented agent API key.

A running daemon calls ``POST /api/v1/auth/api-keys/current/renew`` periodically.
The server extends the *presented* key's ``expires_at`` in place — the token
string never changes — but only when it has fewer than ``RENEW_THRESHOLD_DAYS``
left, so the daemon can call freely and the request is a no-op until it's due.

This is why opaque CLI keys can expire in ``CLI_KEY_TTL_DAYS`` days without ever
forcing a re-login on a machine whose daemon is alive: the daemon keeps pushing
the expiry forward, while a *leaked* key (whose holder isn't renewing) still
lapses. Grandfathered no-exp JWTs never match the ``expires_at IS NOT NULL``
filter, so renewal leaves them untouched — they keep working forever.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from shared.auth import Principal, get_token_hash
from shared.auth.agent_tokens import (
    RENEW_EXTENSION_DAYS,
    RENEW_THRESHOLD_DAYS,
    invalidate_key_cache,
)
from shared.database.models import APIKey
from shared.database.session import get_db
from sqlalchemy.orm import Session

from .auth import get_current_principal, security

auth_keys_router = APIRouter(tags=["auth"])


class RenewResponse(BaseModel):
    renewed: bool
    expires_at: str | None


@auth_keys_router.post("/auth/api-keys/current/renew", response_model=RenewResponse)
async def renew_current_key(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    # Verifies the key (signature/opaque + revocation) and 401s an invalid one
    # before we touch the row. FastAPI resolves the shared `security` scheme
    # once, so `credentials` is exactly the token that was verified.
    _principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> RenewResponse:
    token_hash = get_token_hash(credentials.credentials)
    now = datetime.now(timezone.utc)
    new_expiry = now + timedelta(days=RENEW_EXTENSION_DAYS)
    threshold = now + timedelta(days=RENEW_THRESHOLD_DAYS)

    # Single conditional UPDATE: atomic CAS, idempotent under concurrent daemon
    # calls, and a no-op for keys with plenty of runway or no expiry at all.
    updated = (
        db.query(APIKey)
        .filter(
            APIKey.api_key_hash == token_hash,
            APIKey.is_active.is_(True),
            APIKey.expires_at.isnot(None),
            APIKey.expires_at <= threshold,
        )
        .update({APIKey.expires_at: new_expiry}, synchronize_session=False)
    )
    db.commit()

    if updated:
        # Only makes the key *more* live, but drop the cached liveness answer so
        # the returned expiry and the next verify agree immediately.
        invalidate_key_cache(token_hash)
        return RenewResponse(renewed=True, expires_at=new_expiry.isoformat())

    row = db.query(APIKey.expires_at).filter(APIKey.api_key_hash == token_hash).first()
    current_expiry = row.expires_at if row else None
    return RenewResponse(
        renewed=False,
        expires_at=current_expiry.isoformat() if current_expiry else None,
    )
