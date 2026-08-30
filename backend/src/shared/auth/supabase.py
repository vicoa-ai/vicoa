"""Supabase clients, created lazily so a Supabase-free build never needs them.

The `supabase` wheel is imported inside the factories rather than at module
scope: with `AUTH_PROVIDER=builtin` a self-hosted deployment has no Supabase
project, and `shared.auth` is imported by both server processes on every boot.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from shared.config.settings import settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from supabase import Client


@lru_cache(maxsize=1)
def get_supabase_anon_client() -> "Client":
    """Return a cached Supabase client using the anon key."""

    if not settings.supabase_url or not settings.supabase_anon_key:
        raise RuntimeError("Supabase anon credentials are not configured")

    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_anon_key)


@lru_cache(maxsize=1)
def get_supabase_service_client() -> "Client":
    """Return a cached Supabase client using the service role key."""

    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Supabase service credentials are not configured")

    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_service_role_key)
