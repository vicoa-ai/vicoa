"""delete_user_account succeeds when the user has consumed a Superwall orphan.

The FK `superwall_orphan_events.consumed_user_id -> users.id` originally
defaulted to NO ACTION, so any consumed orphan event blocked
`DELETE /api/v1/auth/me` with a 500. Reproduced 2026-06-17 against the local
dev DB. The fix is `ON DELETE CASCADE` (the row is inert post-deletion
because `consumed_at` is already set, blocking re-application — see migration
`41f641820d6a`).

This integration test pins the new behavior: a user with a consumed orphan
event can be deleted, and the orphan row goes away with them.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from backend.db.queries import delete_user_account
from shared.database.models import User
from shared.database.session import SessionLocal
from shared.database.subscription_models import SuperwallOrphanEvent

pytestmark = pytest.mark.integration


@pytest.fixture
def cleanup_user() -> Iterator[UUID]:
    user_id = uuid4()
    try:
        yield user_id
    finally:
        with SessionLocal() as db:
            db.query(SuperwallOrphanEvent).filter(
                SuperwallOrphanEvent.consumed_user_id == user_id
            ).delete(synchronize_session=False)
            db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
            db.commit()


def test_delete_user_account_succeeds_when_user_consumed_a_superwall_orphan(
    cleanup_user: UUID,
) -> None:
    """The user has consumed a Superwall orphan event — pre-cascade this 500'd
    on `superwall_orphan_events_consumed_user_id_fkey`. Post-cascade it
    succeeds and the orphan row is gone."""
    user_id = cleanup_user
    orphan_id = uuid4()

    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.flush()
        db.add(
            SuperwallOrphanEvent(
                id=orphan_id,
                lookup_id="lookup-" + str(orphan_id),
                event_name="initial_purchase",
                payload="{}",
                consumed_user_id=user_id,
            )
        )
        db.commit()

    with SessionLocal() as db:
        # Pre-state sanity: the orphan exists and points at our user.
        assert (
            db.query(SuperwallOrphanEvent.id)
            .filter(SuperwallOrphanEvent.id == orphan_id)
            .first()
            is not None
        )

    with SessionLocal() as db:
        # Was 500 with FK violation before the migration; should be clean now.
        delete_user_account(db, user_id)

    with SessionLocal() as db:
        # User is gone…
        assert db.query(User.id).filter(User.id == user_id).first() is None
        # …and the orphan row cascaded away with them.
        assert (
            db.query(SuperwallOrphanEvent.id)
            .filter(SuperwallOrphanEvent.id == orphan_id)
            .first()
            is None
        )


def test_unconsumed_orphan_event_is_not_affected_by_other_users_deletion(
    cleanup_user: UUID,
) -> None:
    """An orphan with `consumed_user_id IS NULL` doesn't reference any user;
    deleting a random user must not touch it."""
    user_id = cleanup_user
    orphan_id = uuid4()

    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.flush()
        db.add(
            SuperwallOrphanEvent(
                id=orphan_id,
                lookup_id="lookup-" + str(orphan_id),
                event_name="initial_purchase",
                payload="{}",
                # consumed_user_id deliberately left NULL
            )
        )
        db.commit()

    try:
        with SessionLocal() as db:
            delete_user_account(db, user_id)

        with SessionLocal() as db:
            # Orphan survives — it never pointed at the deleted user.
            assert (
                db.query(SuperwallOrphanEvent.id)
                .filter(SuperwallOrphanEvent.id == orphan_id)
                .first()
                is not None
            )
    finally:
        # The cleanup_user fixture only wipes rows that point at user_id —
        # this orphan doesn't, so clean it up here.
        with SessionLocal() as db:
            db.query(SuperwallOrphanEvent).filter(
                SuperwallOrphanEvent.id == orphan_id
            ).delete(synchronize_session=False)
            db.commit()
