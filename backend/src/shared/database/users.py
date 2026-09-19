"""Race-safe operations on the local users mirror table.

The users table mirrors Supabase auth identities (users.id == auth.users.id).
Rows are populated lazily on first request that needs one. ensure_local_user
is the canonical primitive — concurrent callers cannot 500 each other on
duplicate-key violations.
"""

import logging
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import User
from .session import SessionLocal

logger = logging.getLogger(__name__)


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


def backfill_display_name(user_id: UUID, display_name: str | None) -> None:
    """Background task: copy the IdP's name onto a row that has none.

    `ensure_local_user` writes `display_name` when it inserts the row and
    never again, so every account that signed up before its provider
    published a name — or before that claim was read — keeps a NULL forever.
    The name is what a person is called wherever they appear (a task's
    assignee, a comment, a shared page that opted into showing the owner);
    with none, those surfaces fall back to a placeholder. Supabase
    republishes the metadata on every token, so one write per user converges
    the whole userbase — the same argument as `seed_user_avatar`, and like it
    this runs in its own session (the auth path itself stays write-free),
    re-checks eligibility so concurrent enqueues are safe, and never raises.

    Never overwrites: a name set in Settings is the user's own choice and
    outranks whatever the identity provider still has on file.
    """
    name = (display_name or "").strip()
    if not name:
        return
    try:
        with SessionLocal() as db:
            user = db.get(User, user_id)
            if user is None or user.display_name:
                return
            user.display_name = name
            db.commit()
    except Exception:
        logger.exception("display-name backfill failed for %s", user_id)
