"""Backwards-compatible names for the pre-`AuthProvider` token helpers.

`TokenClaims` is now `Principal` (:mod:`shared.auth.base`) and verification goes
through whichever provider is configured. Both names are kept because they are
spread across call sites and tests; new code should use `Principal` and
`verify_user_token`.
"""

from __future__ import annotations

from .base import Principal, TokenVerificationError
from .provider import verify_user_token

# `Principal` is a superset of the old TokenClaims (it adds `kind`, which
# defaults to "user"), so existing constructions keep working unchanged.
TokenClaims = Principal

# The old name for provider-backed verification. It no longer implies Supabase.
verify_supabase_access_token = verify_user_token

__all__ = [
    "Principal",
    "TokenClaims",
    "TokenVerificationError",
    "verify_supabase_access_token",
    "verify_user_token",
]
