"""JWT Bearer token authentication for FastMCP 3.x.

Replaces the removed BearerAuthProvider from fastmcp 2.x with a TokenVerifier
subclass. The validation itself is delegated to
:mod:`shared.auth.agent_tokens` — this used to be a fourth hand-rolled copy of
the RS256 decode, which meant a key revoked through the dashboard still worked
over MCP.
"""

from typing import Any

from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.utilities.logging import get_logger

from shared.auth import (
    TokenVerificationError,
    is_opaque_agent_token,
    verify_agent_token,
)
from shared.auth.agent_tokens import decode_vicoa_jwt


class JWTTokenVerifier(TokenVerifier):
    """Verifies Vicoa-issued RS256 API keys (signature, expiry, revocation)."""

    def __init__(self, required_scopes: list[str] | None = None):
        super().__init__(required_scopes=required_scopes)
        self._logger = get_logger(__name__)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            principal = verify_agent_token(token)
        except TokenVerificationError as exc:
            self._logger.debug("Token rejected: %s", exc)
            return None
        except Exception as exc:
            self._logger.debug("Token validation failed: %s", exc)
            return None

        # Opaque CLI keys carry no claims — they have no scopes, their identity
        # is the principal, and their expiry is enforced by the DB check on every
        # call (the MCP `expires_at` is only a client-side hint). Grandfathered
        # JWTs still expose their scope/exp/client_id claims.
        if is_opaque_agent_token(token):
            scopes: list[str] = []
            client_id = str(principal.user_id)
            exp = None
        else:
            claims: dict[str, Any] = decode_vicoa_jwt(token)
            scope_claim = claims.get("scope", "")
            scopes = (
                scope_claim.split()
                if isinstance(scope_claim, str)
                else list(scope_claim)
            )
            client_id = str(claims.get("client_id") or principal.user_id)
            exp = claims.get("exp")

        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(exp) if exp else None,
        )
