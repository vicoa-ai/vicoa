"""Race-safe operations on the local users mirror table.

The users table mirrors Supabase auth identities (users.id == auth.users.id).
Rows are populated lazily on first request that needs one. ensure_local_user
is the canonical primitive — concurrent callers cannot 500 each other on
duplicate-key violations.
"""

from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import User


def ensure_local_user(
    db: Session,
    user_id: UUID,
    email: str | None = None,
    display_name: str | None = None,
) -> tuple[User | None, bool]:
    """Insert a mirror row for `user_id` if missing, then return `(user, created)`.

    `created` is True only for the caller whose INSERT actually landed the row.
    Concurrent first requests for the same user all get the row back, but exactly
    one of them sees created=True — so it is safe as a once-per-user trigger
    (the welcome email hangs off it).

    Returns (None, False) when the row does not exist AND no email was supplied
    (User.email is NOT NULL, so creation is impossible).

    Preserves the email-fallback semantic from the original JIT helpers: if
    a row with the same email but a different id exists (Supabase auth.users
    was recreated after a delete or via a different provider), the existing
    row is returned rather than creating a new one.
    """
    existing = db.query(User).filter(User.id == user_id).first()
    if existing:
        return existing, False

    if email:
        by_email = db.query(User).filter(User.email == email).first()
        if by_email:
            return by_email, False
    else:
        return None, False

    stmt = (
        insert(User)
        .values(id=user_id, email=email, display_name=display_name)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    # ON CONFLICT DO NOTHING inserts one row or zero, so rowcount is what tells
    # this caller whether it won the race to create the user.
    created = db.execute(stmt).rowcount == 1
    db.commit()

    user = db.query(User).filter(User.id == user_id).first()
    return user, created and user is not None
