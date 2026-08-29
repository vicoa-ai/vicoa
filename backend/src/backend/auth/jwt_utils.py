"""API-key JWT helpers.

The implementation moved to :mod:`shared.auth.agent_tokens` so that the agent
server, the MCP token verifier and the WebSocket handshake verify keys exactly
the same way this module mints them — including the revocation check they all
used to skip. These names are kept because they are what the backend's routes
and tests import.
"""

from __future__ import annotations

from typing import Any

from jose import JWTError

from shared.auth.agent_tokens import (
    create_agent_jwt,
    decode_vicoa_jwt,
    extract_user_id_from_token,
    get_token_hash,
)
from shared.auth.base import TokenVerificationError

__all__ = [
    "create_api_key_jwt",
    "verify_api_key_jwt",
    "get_token_hash",
    "extract_user_id_from_token",
]

create_api_key_jwt = create_agent_jwt


def verify_api_key_jwt(token: str) -> dict[str, Any]:
    """Verify an API key's signature and return its claims.

    Signature only — callers that are making an authorization decision should
    use `shared.auth.verify_agent_jwt`, which also honours revocation.
    """
    try:
        return decode_vicoa_jwt(token)
    except TokenVerificationError as exc:
        raise JWTError(str(exc)) from exc
