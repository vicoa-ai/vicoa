"""Authentication dependencies for the agent-facing server.

Callers here are CLI wrappers, machine daemons and MCP clients, so the only
credential accepted is a Vicoa-minted RS256 API key. The verification itself
lives in :mod:`shared.auth.agent_tokens` — this module is just the FastAPI
wrapper around it.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from shared.auth import Principal, TokenVerificationError, verify_agent_jwt
from shared.database.session import get_db
from sqlalchemy.orm import Session

# Bearer token security scheme
security = HTTPBearer()


async def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> Principal:
    """Verify the bearer API key and return the caller.

    The request's session is handed to the verifier so the revocation lookup
    reuses it rather than opening a second one.
    """
    try:
        return verify_agent_jwt(credentials.credentials, db)
    except TokenVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_id(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> str:
    """The authenticated user's id, as a string (what the queries expect)."""
    return str(principal.user_id)
