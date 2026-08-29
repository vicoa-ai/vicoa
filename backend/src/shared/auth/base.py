"""The auth seam: one `Principal` type, one `AuthProvider` protocol.

Vicoa authenticates two kinds of caller and keeps them separate on purpose:

* **users** (web / mobile / desktop) hold a token minted by an identity
  provider — Supabase in the hosted deployment, the built-in provider in a
  self-hosted one;
* **agents** (CLI, daemon, MCP clients) hold a long-lived RS256 API key that
  *we* mint and verify against our own public key (:mod:`shared.auth.agent_tokens`).

Both resolve to the same `users.id`, so everything downstream only ever needs
`Principal`. The `AuthProvider` protocol is the swap point: it is the only
place that knows which IdP is in play, which is what lets a self-hosted
deployment run with no Supabase project at all.

See ``plans/todos/pluggable-auth-open-source.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID


class TokenVerificationError(Exception):
    """Raised when a bearer token cannot be verified."""


class AuthProviderError(Exception):
    """Raised when an identity-provider admin call fails."""


PrincipalKind = Literal["user", "agent"]


@dataclass(slots=True)
class Principal:
    """Who is making this request.

    `kind` records *how* they proved it: ``"user"`` for an IdP-issued session
    token, ``"agent"`` for one of our own RS256 API keys. Callers that must not
    accept an API key (account deletion, key minting) check `kind`; everything
    else only reads `user_id`.
    """

    user_id: UUID
    kind: PrincipalKind = "user"
    email: str | None = None
    display_name: str | None = None


@dataclass(slots=True)
class ProviderUser:
    """Identity as the provider knows it, for the admin plane."""

    user_id: UUID
    email: str | None = None
    display_name: str | None = None


class AuthProvider(Protocol):
    """Everything the core needs from an identity provider.

    Implementations must not import anything from ``backend`` or ``servers`` —
    both server processes depend on this seam.
    """

    name: str

    def verify_user_token(self, token: str) -> Principal:
        """Verify an end-user session token. Raises `TokenVerificationError`."""
        ...

    def fetch_user(self, user_id: UUID) -> ProviderUser | None:
        """Read the provider's copy of an identity, or None when it is gone."""
        ...

    def update_user_profile(self, user_id: UUID, display_name: str | None) -> None:
        """Push a profile change back to the provider. No-op when it holds none."""
        ...

    def delete_user(self, user_id: UUID) -> None:
        """Delete the identity. Idempotent: already-absent is success.

        Raises `AuthProviderError` when the provider is reachable but refuses.
        """
        ...
