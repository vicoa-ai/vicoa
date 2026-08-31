"""The one implementation of Vicoa-issued RS256 tokens: mint, verify, revoke.

Before this module the same `jwt.decode(token, settings.jwt_public_key,
algorithms=["RS256"])` was copy-pasted into four call sites (the backend's
`jwt_utils`, the agent server's REST dependency, its WebSocket handshake, and
the MCP `TokenVerifier`). All four checked the signature and nothing else, so a
revoked API key kept working until `exp` — and most keys are minted with no
`exp` at all. Both problems are structural: one copy, one policy.

Two different tokens are signed with this keypair and must not be usable in
each other's place, so every payload carries a `typ` claim:

* ``typ: "agent"`` — a long-lived API key held by a CLI/daemon/MCP client. It is
  recorded in `api_keys` and can be revoked there.
* ``typ: "user"`` — a built-in-provider browser session
  (:mod:`shared.auth.builtin_provider`). Short-lived, never in `api_keys`.

Keys minted before the claim existed have no `typ`; they are still accepted as
agent tokens, which is why absence means "agent" and only an explicit mismatch
is rejected.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import JWTError, jwt

from shared.config.settings import settings

from .base import Principal, TokenVerificationError

logger = logging.getLogger(__name__)

TOKEN_TYPE_CLAIM = "typ"
AGENT_TOKEN_TYPE = "agent"
USER_TOKEN_TYPE = "user"

# Opaque CLI keys — the current shape for newly minted CLI/daemon credentials.
# Unlike the RS256 JWTs (which start ``eyJ`` and carry a self-verifying ``exp``),
# an opaque token is just a random string whose only backing is a row in
# ``api_keys``: its ``expires_at`` lives in the DB and can be extended in place
# (renewal), and a leaked key is capped at ``CLI_KEY_TTL_DAYS`` instead of being
# valid forever. Older no-exp JWTs are still accepted (grandfathered).
VIC_TOKEN_PREFIX = "vic_"
CLI_KEY_TTL_DAYS = 90
# Renewal policy (multica's PATRenewThreshold / PATRenewExtension): the server
# only extends a key that has fewer than RENEW_THRESHOLD_DAYS left, and extends
# it to RENEW_EXTENSION_DAYS from now. The daemon may call renew freely; the
# threshold makes the call a no-op until it's actually due.
RENEW_THRESHOLD_DAYS = 7
RENEW_EXTENSION_DAYS = 90

# How long a "this API key is still live" answer is trusted before the row is
# read again. Revocation is a rare, human-scale action, and the alternative is a
# `SELECT` on every request the agent server serves — so a short window buys
# back nearly all of the cost while capping the blast radius of a leaked key at
# a minute. Only *positive* answers are cached; a revoked key is rejected from
# the first request that sees the row gone.
_REVOCATION_CACHE_TTL = timedelta(seconds=60)
_REVOCATION_CACHE_MAX_SIZE = 4096


@dataclass(slots=True)
class _CacheEntry:
    """A cached "this key is live" answer.

    ``user_id`` is only carried for opaque tokens, whose identity has to come
    from the DB row — a JWT already carries its ``sub``, so its entry leaves
    ``user_id`` as ``None`` and the JWT path reads the subject from the token.
    """

    cached_until: datetime
    user_id: UUID | None = None


_active_key_cache: dict[str, _CacheEntry] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_opaque_agent_token() -> str:
    """Mint a random, DB-backed CLI key (``vic_`` + 160 bits of hex)."""
    return f"{VIC_TOKEN_PREFIX}{secrets.token_hex(20)}"


def is_opaque_agent_token(token: str) -> bool:
    """True for a ``vic_`` opaque key; False for an RS256 JWT (which starts ``eyJ``)."""
    return token.startswith(VIC_TOKEN_PREFIX)


def mask_agent_token(token: str) -> str:
    """A non-secret display form for the ``api_keys.api_key`` column.

    The full opaque secret is never stored (only its SHA256 hash is), so the
    column keeps just a recognizable prefix, e.g. ``vic_1a2b3c4d…``.
    """
    return f"{token[:12]}…"


def create_agent_jwt(
    user_id: str,
    expires_in_days: int | None = None,
    additional_claims: dict[str, Any] | None = None,
) -> str:
    """Mint an agent API key. `expires_in_days=None` means no `exp` claim."""
    if not settings.jwt_private_key:
        raise ValueError("JWT_PRIVATE_KEY not configured")

    now = _utc_now()
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        TOKEN_TYPE_CLAIM: AGENT_TOKEN_TYPE,
    }

    if expires_in_days is not None:
        payload["exp"] = int((now + timedelta(days=expires_in_days)).timestamp())

    if additional_claims:
        payload.update(additional_claims)

    return jwt.encode(payload, settings.jwt_private_key, algorithm="RS256")


def create_signed_jwt(payload: dict[str, Any]) -> str:
    """Sign an arbitrary payload with the Vicoa RS256 private key.

    Used by the built-in auth provider for user sessions; agent keys go through
    `create_agent_jwt`, which fills in the claims that make a key a key.
    """
    if not settings.jwt_private_key:
        raise ValueError("JWT_PRIVATE_KEY not configured")
    return jwt.encode(payload, settings.jwt_private_key, algorithm="RS256")


def decode_vicoa_jwt(token: str) -> dict[str, Any]:
    """Verify a token against our RS256 public key and return its claims.

    Signature, `exp` and `nbf` only — the caller decides what the claims mean.
    """
    if not settings.jwt_public_key:
        raise TokenVerificationError("JWT_PUBLIC_KEY not configured")
    if not token:
        raise TokenVerificationError("Missing token")

    try:
        # `algorithms` is pinned so a token cannot talk us into verifying an
        # RSA public key as an HMAC secret (alg confusion). `aud` is checked by
        # the caller that knows which audience it wants — python-jose otherwise
        # rejects any token carrying an `aud` claim it was not told about.
        return jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise TokenVerificationError(f"Invalid token: {exc}") from exc


def verify_agent_token(token: str, db: Any | None = None) -> Principal:
    """Verify an agent API key (opaque or JWT) and return its `Principal`.

    `db` is an optional SQLAlchemy session for the DB lookup; when the caller
    has none (the MCP token verifier, the WebSocket handshake) a short-lived one
    is opened for the lookup itself.

    Two token shapes are accepted:

    * **Opaque** (``vic_…``) — the current CLI key. No signature or claims, so
      its identity, liveness and expiry all come from its `api_keys` row.
    * **JWT** (``eyJ…``) — a grandfathered RS256 key. Signature-verified, then
      checked for revocation/expiry against `api_keys` (when enforcement is on).
    """
    if is_opaque_agent_token(token):
        return _verify_opaque_token(token, db)
    return _verify_jwt_agent_token(token, db)


# Backwards-compatible alias: the four call sites and the backend's `jwt_utils`
# imported the verifier under this name before opaque tokens existed.
verify_agent_jwt = verify_agent_token


def _verify_jwt_agent_token(token: str, db: Any | None) -> Principal:
    payload = decode_vicoa_jwt(token)

    token_type = payload.get(TOKEN_TYPE_CLAIM)
    if token_type is not None and token_type != AGENT_TOKEN_TYPE:
        raise TokenVerificationError(f"Token is not an agent key (typ={token_type!r})")

    sub = payload.get("sub")
    if not sub:
        raise TokenVerificationError("Token missing sub claim")
    try:
        user_id = UUID(str(sub))
    except (ValueError, AttributeError) as exc:
        raise TokenVerificationError("Token subject is not a user id") from exc

    if settings.enforce_api_key_revocation:
        _assert_key_not_revoked(token, db)

    return Principal(user_id=user_id, kind="agent")


def _verify_opaque_token(token: str, db: Any | None) -> Principal:
    """Verify a ``vic_`` opaque key against its `api_keys` row.

    Unlike a JWT, an opaque token carries no ``sub`` we could fall back on, so a
    DB error here cannot degrade to "allow" (as the JWT revocation lookup does)
    — the request is failed loudly (a 500 the daemon retries), never silently
    admitted and never turned into a spurious 401 that would look like a dead
    credential.
    """
    token_hash = get_token_hash(token)
    now = _utc_now()

    hit = _active_key_cache.get(token_hash)
    if hit is not None and now < hit.cached_until and hit.user_id is not None:
        return Principal(user_id=hit.user_id, kind="agent")

    if db is not None:
        row = _lookup_api_key_full(db, token_hash)
    else:
        from shared.database.session import SessionLocal

        session = SessionLocal()
        try:
            row = _lookup_api_key_full(session, token_hash)
        finally:
            session.close()

    if row is None:
        _active_key_cache.pop(token_hash, None)
        raise TokenVerificationError("API key not found or revoked")

    user_id_raw, is_active, expires_at = row
    if not is_active:
        _active_key_cache.pop(token_hash, None)
        raise TokenVerificationError("API key has been revoked")
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            _active_key_cache.pop(token_hash, None)
            raise TokenVerificationError("API key has expired")

    try:
        user_id = UUID(str(user_id_raw))
    except (ValueError, AttributeError) as exc:
        raise TokenVerificationError("API key row has no valid user") from exc

    if len(_active_key_cache) > _REVOCATION_CACHE_MAX_SIZE:
        _active_key_cache.clear()
    _active_key_cache[token_hash] = _CacheEntry(now + _REVOCATION_CACHE_TTL, user_id)
    return Principal(user_id=user_id, kind="agent")


def get_token_hash(token: str) -> str:
    """SHA256 of a token — what `api_keys.api_key_hash` stores."""
    return hashlib.sha256(token.encode()).hexdigest()


def extract_user_id_from_token(token: str) -> str:
    """Read `sub` **without verifying**, for lookups that precede verification.

    Never use the result as an authorization decision.
    """
    try:
        unverified_payload = jwt.get_unverified_claims(token)
        user_id = unverified_payload.get("sub")
        if user_id is None:
            raise JWTError("Token missing subject claim")
        return str(user_id)
    except Exception as exc:
        raise JWTError(f"Cannot extract user ID: {exc}") from exc


def reset_revocation_cache() -> None:
    """Drop the cached "key is live" answers (tests, and after a revoke)."""
    _active_key_cache.clear()


def invalidate_key_cache(token_hash: str) -> None:
    """Drop the cached answer for one key (e.g. after a renew extends its expiry)."""
    _active_key_cache.pop(token_hash, None)


def _assert_key_not_revoked(token: str, db: Any | None) -> None:
    """Raise unless `api_keys` still carries a live row for this token."""
    token_hash = get_token_hash(token)

    hit = _active_key_cache.get(token_hash)
    if hit is not None and _utc_now() < hit.cached_until:
        return

    if db is not None:
        live = _api_key_is_live(db, token_hash)
    else:
        from shared.database.session import SessionLocal

        session = SessionLocal()
        try:
            live = _api_key_is_live(session, token_hash)
        finally:
            session.close()

    if not live:
        _active_key_cache.pop(token_hash, None)
        raise TokenVerificationError("API key has been revoked")

    if len(_active_key_cache) > _REVOCATION_CACHE_MAX_SIZE:
        _active_key_cache.clear()
    # A JWT carries its own subject, so this entry needs no cached user_id.
    _active_key_cache[token_hash] = _CacheEntry(_utc_now() + _REVOCATION_CACHE_TTL)


def _lookup_api_key_full(
    db: Any, token_hash: str
) -> tuple[Any, bool, datetime | None] | None:
    """Return ``(user_id, is_active, expires_at)`` for this hash, or ``None``.

    Deliberately lets DB errors propagate — the opaque-token path has no ``sub``
    fallback, so it must fail loudly rather than admit an unverifiable key.
    """
    from shared.database.models import APIKey

    return (
        db.query(APIKey.user_id, APIKey.is_active, APIKey.expires_at)
        .filter(APIKey.api_key_hash == token_hash)
        .first()
    )


def _api_key_is_live(db: Any, token_hash: str) -> bool:
    """Whether an unrevoked, unexpired `api_keys` row exists for this hash.

    A DB error is treated as "live": the agent server must not lock every
    daemon out because Postgres hiccuped, and the signature has already been
    verified at this point.
    """
    from shared.database.models import APIKey

    try:
        row = (
            db.query(APIKey.is_active, APIKey.expires_at)
            .filter(APIKey.api_key_hash == token_hash)
            .first()
        )
    except Exception:
        logger.exception("API-key revocation lookup failed; allowing the request")
        return True

    if row is None:
        return False
    is_active, expires_at = row
    if not is_active:
        return False
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= _utc_now():
            return False
    return True
