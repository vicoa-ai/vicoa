"""`AuthProvider` backed by Supabase — the hosted deployment's identity source.

Verification is **local**. It used to be a `supabase.auth.get_user(token)` call,
i.e. a network round-trip to GoTrue on every cache miss: latency on the request
path, a hard runtime dependency on Supabase being reachable, and a five-minute
window in which a token was trusted without re-checking `exp`. The access token
is a JWT that already carries everything we read (`sub`, `email`,
`user_metadata`), so the only thing the round-trip bought was the signature
check — which we can do ourselves.

Which key does the checking depends on how the Supabase project is configured,
and the token's own `alg` header says which:

* `HS256` — the legacy shared secret (`SUPABASE_JWT_SECRET`). Treat it as a
  signing key: it both signs and verifies, so it must never be shipped to a
  client or logged.
* `RS256` / `ES256` — the project has asymmetric signing keys on, and the public
  half is published at the project's JWKS endpoint. Nothing secret to hold; this
  is the better posture and the direction to migrate.

If neither is available (no secret configured, project still symmetric) the
provider falls back to the old network call, so an existing deployment keeps
working with no config change.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from jose import JWTError, jwt

from shared.config.settings import settings

from .base import AuthProviderError, Principal, ProviderUser, TokenVerificationError
from .supabase import get_supabase_anon_client, get_supabase_service_client

logger = logging.getLogger(__name__)

SUPABASE_AUDIENCE = "authenticated"
_ASYMMETRIC_ALGORITHMS = ("RS256", "ES256", "EdDSA")
_JWKS_TTL = timedelta(minutes=10)
_JWKS_TIMEOUT_SECONDS = 5

# Only the network fallback is cached. Local verification is microseconds and
# re-reads `exp` every time, so caching it would only re-introduce the window
# this provider exists to close.
_REMOTE_CACHE_TTL = timedelta(minutes=5)
_REMOTE_CACHE_MAX_SIZE = 2048


class _NoLocalKeyMaterial(Exception):
    """The token cannot be verified locally — fall back to the network."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SupabaseAuthProvider:
    """Verify Supabase access tokens; delegate profile admin to GoTrue."""

    name = "supabase"

    def __init__(self) -> None:
        self._jwks: dict[str, Any] | None = None
        self._jwks_fetched_at: datetime | None = None
        self._jwks_lock = threading.Lock()
        self._remote_cache: dict[str, tuple[Principal, datetime]] = {}

    # --- verification ---------------------------------------------------

    def verify_user_token(self, token: str) -> Principal:
        if not token:
            raise TokenVerificationError("Missing access token")

        try:
            return self._verify_locally(token)
        except _NoLocalKeyMaterial as exc:
            logger.debug("Local Supabase verification unavailable: %s", exc)

        return self._verify_over_network(token)

    def _verify_locally(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except JWTError as exc:
            raise TokenVerificationError(f"Malformed access token: {exc}") from exc

        alg = header.get("alg")
        if alg == "HS256":
            key: Any = settings.supabase_jwt_secret
            if not key:
                raise _NoLocalKeyMaterial("SUPABASE_JWT_SECRET is not set")
        elif alg in _ASYMMETRIC_ALGORITHMS:
            key = self._jwk_for(header.get("kid"))
        else:
            raise TokenVerificationError(f"Unsupported token algorithm {alg!r}")

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[alg],
                audience=SUPABASE_AUDIENCE,
                # `iss` is checked below against the configured project URL;
                # python-jose's own check wants an exact string, which breaks
                # the moment SUPABASE_URL carries a trailing slash.
                options={"verify_iss": False},
            )
        except JWTError as exc:
            raise TokenVerificationError(f"Invalid access token: {exc}") from exc

        self._assert_issuer(claims.get("iss"))
        return _principal_from_claims(claims)

    def _assert_issuer(self, issuer: Any) -> None:
        """Reject a token signed for a different Supabase project.

        Compared by host, not string equality: the configured URL and the `iss`
        claim differ in path (`/auth/v1`) and often in trailing slash.
        """
        if not settings.supabase_url:
            return
        expected = urlparse(settings.supabase_url).netloc
        actual = urlparse(str(issuer or "")).netloc
        if expected and actual and expected != actual:
            raise TokenVerificationError(
                f"Token issued by {actual!r}, expected {expected!r}"
            )

    def _jwk_for(self, kid: str | None) -> dict[str, Any]:
        jwks = self._get_jwks(force_refresh=False)
        key = _find_key(jwks, kid)
        if key is None:
            # A rotated-in key we have not seen: refresh once, then fail closed.
            jwks = self._get_jwks(force_refresh=True)
            key = _find_key(jwks, kid)
        if key is None:
            raise _NoLocalKeyMaterial(f"no JWKS entry for kid={kid!r}")
        return key

    def _get_jwks(self, *, force_refresh: bool) -> dict[str, Any]:
        with self._jwks_lock:
            fresh = (
                self._jwks_fetched_at is not None
                and _utc_now() - self._jwks_fetched_at < _JWKS_TTL
            )
            if self._jwks is not None and fresh and not force_refresh:
                return self._jwks

            if not settings.supabase_url:
                self._jwks = {"keys": []}
                self._jwks_fetched_at = _utc_now()
                return self._jwks

            url = settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
            # Keep serving the previous key set rather than locking every
            # request out on a transient fetch failure.
            keys: dict[str, Any] = self._jwks or {"keys": []}
            try:
                with urllib.request.urlopen(  # noqa: S310 - fixed https project URL
                    url, timeout=_JWKS_TIMEOUT_SECONDS
                ) as response:
                    keys = json.loads(response.read().decode("utf-8"))
            except (urllib.error.URLError, ValueError, OSError) as exc:
                logger.warning("Supabase JWKS fetch failed (%s): %s", url, exc)
            self._jwks = keys
            self._jwks_fetched_at = _utc_now()
            return keys

    def _verify_over_network(self, token: str) -> Principal:
        cached = self._remote_cache.get(token)
        if cached:
            principal, expires_at = cached
            if _utc_now() < expires_at:
                return principal
            del self._remote_cache[token]

        try:
            supabase = get_supabase_anon_client()
            user_response = supabase.auth.get_user(token)
        except Exception as exc:  # pragma: no cover - defensive path
            raise TokenVerificationError(f"Failed to validate token: {exc}") from exc

        if not user_response or not getattr(user_response, "user", None):
            raise TokenVerificationError("Invalid access token")

        try:
            user_id = UUID(user_response.user.id)
        except Exception as exc:  # pragma: no cover - malformed data
            raise TokenVerificationError("Token missing valid subject") from exc

        principal = Principal(
            user_id=user_id,
            kind="user",
            email=user_response.user.email,
            display_name=_display_name(user_response.user.user_metadata or {}),
        )

        if len(self._remote_cache) > _REMOTE_CACHE_MAX_SIZE:
            self._remote_cache.clear()
        self._remote_cache[token] = (principal, _utc_now() + _REMOTE_CACHE_TTL)
        return principal

    # --- admin plane ----------------------------------------------------

    def fetch_user(self, user_id: UUID) -> ProviderUser | None:
        try:
            response = get_supabase_service_client().auth.admin.get_user_by_id(
                str(user_id)
            )
        except Exception as exc:
            if _is_not_found(exc):
                return None
            raise AuthProviderError(f"Supabase lookup failed: {exc}") from exc

        if not response or not getattr(response, "user", None):
            return None
        return ProviderUser(
            user_id=user_id,
            email=response.user.email,
            display_name=(response.user.user_metadata or {}).get("display_name"),
        )

    def update_user_profile(self, user_id: UUID, display_name: str | None) -> None:
        try:
            get_supabase_service_client().auth.admin.update_user_by_id(
                str(user_id), {"user_metadata": {"display_name": display_name}}
            )
        except Exception as exc:
            raise AuthProviderError(f"Supabase profile update failed: {exc}") from exc

    def delete_user(self, user_id: UUID) -> None:
        try:
            get_supabase_service_client().auth.admin.delete_user(str(user_id))
        except Exception as exc:
            if _is_not_found(exc):
                # Already gone (prior partial delete, or removed via the
                # dashboard) — the desired end state, so this is success.
                logger.info("User %s already absent from Supabase auth", user_id)
                return
            raise AuthProviderError(f"Supabase delete failed: {exc}") from exc


def _principal_from_claims(claims: dict[str, Any]) -> Principal:
    sub = claims.get("sub")
    try:
        user_id = UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise TokenVerificationError("Token missing valid subject") from exc

    return Principal(
        user_id=user_id,
        kind="user",
        email=claims.get("email"),
        display_name=_display_name(claims.get("user_metadata") or {}),
    )


def _display_name(metadata: dict[str, Any]) -> str | None:
    return (
        metadata.get("display_name")
        or metadata.get("full_name")
        or metadata.get("name")
    )


def _find_key(jwks: dict[str, Any], kid: str | None) -> dict[str, Any] | None:
    keys = jwks.get("keys") or []
    if not keys:
        return None
    if kid is None:
        return keys[0] if len(keys) == 1 else None
    for key in keys:
        if key.get("kid") == kid:
            return key
    return None


def _is_not_found(exc: Exception) -> bool:
    return "user not found" in str(exc).lower()
