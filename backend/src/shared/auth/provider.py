"""Which `AuthProvider` is active, and the front door both servers call.

Selection is by config, and the default is inferred rather than hardcoded: a
deployment that configured Supabase gets Supabase, one that did not gets the
built-in provider. That keeps the hosted deployment on its existing env vars and
lets `docker compose up` work with no auth configuration at all.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from shared.config.settings import settings

from .base import AuthProvider, Principal

logger = logging.getLogger(__name__)

SUPABASE = "supabase"
BUILTIN = "builtin"


def resolve_auth_provider_name() -> str:
    """The configured provider, or the one implied by what is configured."""
    configured = (settings.auth_provider or "").strip().lower()
    if configured:
        return configured
    return SUPABASE if settings.supabase_url and settings.supabase_anon_key else BUILTIN


@lru_cache(maxsize=1)
def get_auth_provider() -> AuthProvider:
    """The active provider. Cached — selection cannot change without a restart."""
    name = resolve_auth_provider_name()

    if name == SUPABASE:
        from .supabase_provider import SupabaseAuthProvider

        logger.info("Auth provider: supabase")
        return SupabaseAuthProvider()

    if name == BUILTIN:
        from .builtin_provider import BuiltinAuthProvider

        logger.info("Auth provider: builtin (no external identity provider)")
        return BuiltinAuthProvider()

    raise RuntimeError(
        f"Unknown AUTH_PROVIDER {name!r}; expected {SUPABASE!r} or {BUILTIN!r}"
    )


def reset_auth_provider() -> None:
    """Drop the cached provider (tests, and after changing settings)."""
    get_auth_provider.cache_clear()


def verify_user_token(token: str) -> Principal:
    """Verify an end-user session token against the active provider."""
    return get_auth_provider().verify_user_token(token)
