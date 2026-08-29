import logging
import sys
from pathlib import Path
from uuid import UUID

# Add parent directory to path to import shared module
sys.path.append(str(Path(__file__).parent.parent.parent))

from fastapi import BackgroundTasks, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from shared.database.models import User
from shared.database.session import get_db
from shared.database.users import ensure_local_user
from sqlalchemy.orm import Session

from shared.auth import Principal, verify_user_token
from shared.hooks import run_user_created_hooks

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)  # Don't auto-error so we can check cookies


class AuthError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=401, detail=detail)


def get_token_from_request(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = None,
) -> str | None:
    """Extract token from either Authorization header or session cookie"""
    # First try Authorization header
    if credentials and credentials.credentials:
        return credentials.credentials

    # Then try session cookie
    session_token = request.cookies.get("session_token")
    if session_token:
        return session_token

    return None


async def get_current_claims(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> Principal:
    """Verify the request's session token and return the caller's `Principal`.

    This endpoint family is the human-facing API, so it only ever accepts an
    end-user token from the active auth provider — never an agent API key,
    which would otherwise be able to mint more keys and delete the account.
    Centralizing verification here also means downstream dependencies read
    email/display_name straight off the claims instead of paying an extra
    identity-provider round-trip. FastAPI caches dependencies per-request, so
    this still only runs once per request.
    """
    token = get_token_from_request(request, credentials)

    if not token:
        raise AuthError("No authentication token provided")

    try:
        return verify_user_token(token)
    except Exception as exc:
        raise AuthError(f"Could not validate credentials: {str(exc)}") from exc


async def get_current_user_id(
    claims: Principal = Depends(get_current_claims),
) -> UUID:
    """Extract user ID from the verified token claims."""
    return claims.user_id


def _resolve_or_create_user(claims: Principal, db: Session) -> tuple[User | None, bool]:
    """Resolve the local users row for these claims, JIT-creating if absent.

    Delegates to the race-safe `ensure_local_user` primitive — concurrent first
    requests for the same brand-new user no longer 500 on duplicate-key, and
    exactly one of them gets created=True.
    """
    return ensure_local_user(
        db,
        user_id=claims.user_id,
        email=claims.email,
        display_name=claims.display_name,
    )


async def _run_user_created_hooks_bg(to_email: str, user_name: str) -> None:
    """Best-effort on-user-created side effects (e.g. the overlay welcome email),
    run after the response has gone out. No-op in the open build where the
    cloud overlay is absent."""
    try:
        await run_user_created_hooks(to_email, user_name)
    except Exception:
        logger.exception("on_user_created hook raised for %s", to_email)


def _schedule_user_created_hooks(background_tasks: BackgroundTasks, user: User) -> None:
    """Queue on-user-created hooks for a user who was just created.

    Reads email/display_name now rather than inside the task: by the time
    BackgroundTasks runs, `get_db` has closed the session and ORM attribute
    access is no longer safe.
    """
    background_tasks.add_task(
        _run_user_created_hooks_bg, user.email, user.display_name or ""
    )


def _schedule_signup_side_effects(
    background_tasks: BackgroundTasks, user: User
) -> None:
    """Everything that happens once, the moment a user's local row appears.

    All of it runs via the open core's ``on_user_created`` hooks — the overlay
    registers the welcome email and the marketing-list subscribe there. The open
    core carries no such wiring; each hook is isolated
    (``run_user_created_hooks``), so one failing cannot stop the others.
    """
    _schedule_user_created_hooks(background_tasks, user)


async def get_current_user(
    background_tasks: BackgroundTasks,
    claims: Principal = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> User:
    """Get current user, provisioning on first sign-in if needed."""
    user, created = _resolve_or_create_user(claims, db)
    if user is None:
        raise AuthError("User not found")
    if created:
        _schedule_signup_side_effects(background_tasks, user)
    return user


async def get_optional_current_user(
    request: Request,
    background_tasks: BackgroundTasks,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User | None:
    """Get current user if authenticated, otherwise return None"""
    token = get_token_from_request(request, credentials)

    if not token:
        return None

    try:
        claims = verify_user_token(token)
        user, created = _resolve_or_create_user(claims, db)
    except Exception:
        return None

    if user is not None and created:
        _schedule_signup_side_effects(background_tasks, user)
    return user
