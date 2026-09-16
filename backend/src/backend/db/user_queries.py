"""Writes against the caller's own ``users`` row (collaboration P0).

Mirrors ``task_queries.set_project_icon`` / ``reset_project_icon``: the router
validates and stores the bytes, the query layer owns the transaction. Keeping
the commit here (rather than in ``backend/api/``) is also what keeps
``scripts/check_websocket_freeze.py`` happy.
"""

from sqlalchemy.orm import Session

from shared.database.models import User


def set_user_avatar(db: Session, user: User, *, avatar_image_uri: str) -> User:
    """Point a user at their uploaded avatar. ``'user'`` beats any OAuth seed."""
    user.avatar_image_uri = avatar_image_uri
    user.avatar_source = "user"
    db.commit()
    db.refresh(user)
    return user


def clear_user_avatar(db: Session, user: User) -> User:
    """Drop the image so the user renders as generated initials.

    ``avatar_source`` is pinned to ``'user'`` rather than NULL on purpose: NULL
    would make the account seed-eligible again, so the next sign-in would
    silently restore the OAuth picture the user just removed — the same trap
    ``reset_project_icon`` documents for the git seed.
    """
    user.avatar_image_uri = None
    user.avatar_source = "user"
    db.commit()
    db.refresh(user)
    return user


def set_user_avatar_emoji(db: Session, user: User, *, emoji: str | None) -> User:
    """Pick (or clear) the emoji shown when there is no avatar image.

    Independent of ``avatar_image_uri`` rather than a third ``avatar_source``
    value: the image wins while it exists, and clearing it should reveal an
    emoji the user chose earlier instead of silently discarding it.
    """
    user.avatar_emoji = emoji or None
    db.commit()
    db.refresh(user)
    return user
