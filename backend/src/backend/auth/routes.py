import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent directory to path to import shared module
sys.path.append(str(Path(__file__).parent.parent.parent))

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from shared.config import settings
from shared.database.models import APIKey, User
from shared.database.session import get_db
from sqlalchemy.orm import Session

from ..db.queries import delete_user_account as delete_user_db
from .dependencies import (
    get_current_claims,
    get_current_user,
    get_optional_current_user,
)
from shared.auth import (
    AuthProviderError,
    Principal,
    get_auth_provider,
    resolve_auth_provider_name,
)
from shared.auth.agent_tokens import reset_revocation_cache
from .jwt_utils import create_api_key_jwt, get_token_hash
from .utils import update_user_profile

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


class UserProfile(BaseModel):
    id: str
    email: str
    display_name: str | None
    created_at: str


class UpdateProfileRequest(BaseModel):
    display_name: str | None


class CreateAPIKeyRequest(BaseModel):
    name: str
    expires_in_days: int | None = None


class APIKeyResponse(BaseModel):
    id: str
    name: str
    api_key: str  # Only returned on creation
    created_at: str
    expires_at: str | None


class APIKeyListItem(BaseModel):
    id: str
    name: str
    api_key: str
    created_at: str
    expires_at: str | None
    last_used_at: str | None
    is_active: bool


class SyncUserRequest(BaseModel):
    id: str
    email: str
    display_name: str | None


class AuthConfigResponse(BaseModel):
    provider: str
    allow_signup: bool
    require_email_verification: bool


@router.get("/config", response_model=AuthConfigResponse)
async def get_auth_config():
    """How to sign in to *this* deployment.

    Unauthenticated on purpose: a client has to know which provider it is
    talking to before it can authenticate at all, and none of this is secret.
    """
    provider = resolve_auth_provider_name()
    return AuthConfigResponse(
        provider=provider,
        allow_signup=(provider != "builtin") or settings.builtin_allow_signup,
        require_email_verification=(
            provider == "builtin" and settings.builtin_require_email_verification
        ),
    )


@router.post("/sync-user")
async def sync_user(
    request: SyncUserRequest,
    claims: Principal = Depends(get_current_claims),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sync user from Supabase to our database"""
    # The request body must claim the same identity as the JWT. We compare to
    # the JWT's sub (claims.user_id), not current_user.id, because the latter
    # may be a re-attached email-matched row whose id pre-dates this Supabase
    # identity.
    if str(claims.user_id) != request.id:
        raise HTTPException(status_code=403, detail="Cannot sync different user")

    # Update user profile if needed
    if current_user.display_name != request.display_name:
        current_user.display_name = request.display_name
        db.commit()

    return {"message": "User synced successfully"}


@router.get("/session")
async def get_session(user: User | None = Depends(get_optional_current_user)):
    """Get current session info"""
    if user:
        return UserProfile(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            created_at=user.created_at.isoformat(),
        )
    else:
        raise HTTPException(status_code=401, detail="Not authenticated")


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Get current user profile"""
    return UserProfile(
        id=str(current_user.id),
        email=current_user.email,
        display_name=current_user.display_name,
        created_at=current_user.created_at.isoformat(),
    )


@router.patch("/me", response_model=UserProfile)
async def update_current_user_profile(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update current user profile"""
    updated_user = update_user_profile(current_user.id, request.display_name, db)

    return UserProfile(
        id=str(updated_user.id),
        email=updated_user.email,
        display_name=updated_user.display_name,
        created_at=updated_user.created_at.isoformat(),
    )


@router.post("/api-keys", response_model=APIKeyResponse)
async def create_api_key(
    request: CreateAPIKeyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new API key for MCP authentication"""

    # Validate expiration
    max_expiration_days = 999999
    if (
        request.expires_in_days is not None
        and request.expires_in_days > max_expiration_days
    ):
        raise HTTPException(
            status_code=400,
            detail=f"API key expiration cannot exceed {max_expiration_days} days",
        )

    # Check if user already has 5+ active API keys
    active_keys_count = (
        db.query(APIKey)
        .filter(APIKey.user_id == current_user.id, APIKey.is_active)
        .count()
    )

    if active_keys_count >= 50:
        raise HTTPException(
            status_code=400, detail="Maximum of 50 active API keys allowed"
        )

    # Generate the JWT token
    try:
        jwt_token = create_api_key_jwt(
            user_id=str(current_user.id),
            expires_in_days=request.expires_in_days,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate API key: {str(e)}"
        )

    # Store API key metadata in database
    expires_at = None
    if request.expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=request.expires_in_days
        )

    api_key = APIKey(
        user_id=current_user.id,
        name=request.name,
        api_key_hash=get_token_hash(jwt_token),
        api_key=jwt_token,
        expires_at=expires_at,
    )

    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return APIKeyResponse(
        id=str(api_key.id),
        name=api_key.name,
        api_key=jwt_token,  # Only returned here!
        created_at=api_key.created_at.isoformat(),
        expires_at=api_key.expires_at.isoformat() if api_key.expires_at else None,
    )


@router.get("/api-keys", response_model=list[APIKeyListItem])
async def list_api_keys(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """List all API keys for the current user"""

    api_keys = (
        db.query(APIKey)
        .filter(APIKey.user_id == current_user.id)
        .order_by(APIKey.created_at.desc())
        .all()
    )

    return [
        APIKeyListItem(
            id=str(key.id),
            name=key.name,
            api_key=key.api_key,
            created_at=key.created_at.isoformat(),
            expires_at=key.expires_at.isoformat() if key.expires_at else None,
            last_used_at=key.last_used_at.isoformat() if key.last_used_at else None,
            is_active=key.is_active,
        )
        for key in api_keys
    ]


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke (deactivate) an API key"""

    api_key = (
        db.query(APIKey)
        .filter(APIKey.id == key_id, APIKey.user_id == current_user.id)
        .first()
    )

    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.is_active = False
    db.commit()
    # The agent servers cache "this key is live" answers for a minute; a user
    # who just clicked revoke should not have to wait for that to age out in
    # this process.
    reset_revocation_cache()

    return {"message": "API key revoked successfully"}


@router.post("/cli-key", response_model=APIKeyResponse)
async def create_cli_key(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new CLI-specific API key for the current user"""

    # Always generate a new CLI key
    try:
        jwt_token = create_api_key_jwt(
            user_id=str(current_user.id),
            expires_in_days=None,  # No expiration for CLI keys
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate API key: {str(e)}"
        )

    # Store the new CLI key
    api_key = APIKey(
        user_id=current_user.id,
        name="CLI Key",
        api_key_hash=get_token_hash(jwt_token),
        api_key=jwt_token,
        expires_at=None,  # No expiration
    )

    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return APIKeyResponse(
        id=str(api_key.id),
        name=api_key.name,
        api_key=jwt_token,
        created_at=api_key.created_at.isoformat(),
        expires_at=None,
    )


@router.delete("/me")
async def delete_user_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete the current user's account and all associated data"""
    user_id = current_user.id

    # Delete from database (including Stripe cancellation)
    try:
        delete_user_db(db, user_id)
    except Exception as e:
        logger.error(f"Failed to delete user {user_id} from database: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete user account")

    # Delete the identity itself. The provider treats an already-absent user as
    # success, so only a real failure lands in the except.
    try:
        get_auth_provider().delete_user(user_id)
        logger.info(f"Successfully deleted user {user_id} from the auth provider")
    except AuthProviderError as e:
        # Log the error but don't fail - DB deletion already succeeded
        logger.error(f"Failed to delete user {user_id} from the auth provider: {e}")
        # Return 207 Multi-Status to indicate partial success
        return {
            "message": "User account deleted from database but failed to delete from authentication provider",
            "status_code": 207,
        }

    return {"message": "User account successfully deleted"}
