"""Shared authentication: one `Principal`, one provider seam, one agent verifier."""

from .agent_tokens import (
    create_agent_jwt,
    extract_user_id_from_token,
    get_token_hash,
    verify_agent_jwt,
)
from .base import (
    AuthProvider,
    AuthProviderError,
    Principal,
    PrincipalKind,
    ProviderUser,
    TokenVerificationError,
)
from .provider import (
    get_auth_provider,
    reset_auth_provider,
    resolve_auth_provider_name,
    verify_user_token,
)
from .supabase import get_supabase_anon_client, get_supabase_service_client
from .tokens import TokenClaims, verify_supabase_access_token

__all__ = [
    "AuthProvider",
    "AuthProviderError",
    "Principal",
    "PrincipalKind",
    "ProviderUser",
    "TokenClaims",
    "TokenVerificationError",
    "create_agent_jwt",
    "extract_user_id_from_token",
    "get_auth_provider",
    "get_supabase_anon_client",
    "get_supabase_service_client",
    "get_token_hash",
    "reset_auth_provider",
    "resolve_auth_provider_name",
    "verify_agent_jwt",
    "verify_supabase_access_token",
    "verify_user_token",
]
