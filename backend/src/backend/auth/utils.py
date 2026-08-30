import sys
from pathlib import Path
from uuid import UUID

# Add parent directory to path to import shared module
sys.path.append(str(Path(__file__).parent.parent.parent))

from shared.database.models import User
from shared.database.users import ensure_local_user
from sqlalchemy.orm import Session

from shared.auth import get_auth_provider


def sync_user_from_provider(user_id: UUID, db: Session) -> User:
    """Sync user data from the auth provider into the local mirror row.

    Creates the row if missing (race-safe via ensure_local_user), then refreshes
    mutable fields (email, display_name) from the provider so the mirror tracks
    upstream identity changes. With the built-in provider there is no upstream —
    it reads the same row back and the refresh is a no-op.

    The `created` flag is deliberately discarded: this runs on the RevenueCat
    webhook path, and a purchase is the wrong moment to welcome someone. The
    welcome email fires from the auth dependency instead.
    """
    provider_user = get_auth_provider().fetch_user(user_id)

    if provider_user is None:
        raise ValueError(f"User {user_id} not found in the auth provider")

    email = provider_user.email
    display_name = provider_user.display_name

    user, _created = ensure_local_user(
        db, user_id, email=email, display_name=display_name
    )
    if user is None:
        raise ValueError(
            f"Cannot create local user {user_id}: auth provider returned no email"
        )

    changed = False
    if email and user.email != email:
        user.email = email
        changed = True
    if display_name and user.display_name != display_name:
        user.display_name = display_name
        changed = True
    if changed:
        db.commit()
        db.refresh(user)

    return user


def update_user_profile(user_id: UUID, display_name: str | None, db: Session) -> User:
    """Update user profile information"""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise ValueError(f"User {user_id} not found")

    if display_name is not None:
        user.display_name = display_name

    db.commit()
    db.refresh(user)

    # Mirror the change back to the identity provider, which keeps its own copy
    # of the display name. A no-op for the built-in provider, whose only copy is
    # the row just written.
    get_auth_provider().update_user_profile(user_id, display_name)

    return user
