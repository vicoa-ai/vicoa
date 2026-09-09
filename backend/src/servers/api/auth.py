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
from shared.database.actor import Actor, set_session_actor
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
        principal = verify_agent_jwt(credentials.credentials, db)
    except TokenVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Attribution for generated task activity (collaboration §3.5). An API key
    # identifies a user, not an agent profile — `vicoa task update` looks the
    # same whether a human typed it or an agent ran it — so this attributes to
    # the user. Genuinely agent-authored writes (an agent posting a comment)
    # name their author explicitly instead of inheriting this.
    set_session_actor(db, Actor(type="user", id=principal.user_id))
    return principal


async def get_current_user_id(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> str:
    """The authenticated user's id, as a string (what the queries expect)."""
    return str(principal.user_id)
