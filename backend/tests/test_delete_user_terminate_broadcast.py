"""Phase 2b: delete_user_account fires terminate NOTIFY for every live
agent instance before cascading the user's rows.

Without this, a still-running CLI / headless wrapper keeps polling against
its now-deleted instance — producing the 400-on-/messages/pending storm
documented in plans/bugs/p0-agent-jwt-no-db-validation.md (2026-06-15
update). Phase 1's reactive FK bouncer only catches writes; reads slip
through silently.

The signal is transactional — NOTIFY only fires on commit, so a rollback
of the user-delete cleanly suppresses the broadcast.
"""

from collections.abc import Iterator
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from backend.db.queries import delete_user_account
from shared.database.enums import AgentStatus
from shared.database.models import (
    AgentInstance,
    Message,
    User,
    UserAgent,
)
from shared.database.session import SessionLocal

pytestmark = pytest.mark.integration


def _seed_user_with_instances(user_id: UUID, statuses: list[AgentStatus]) -> list[UUID]:
    """Insert a user, one UserAgent, and one AgentInstance per status. Returns instance ids."""
    agent_id = uuid4()
    instance_ids = [uuid4() for _ in statuses]
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.flush()
        db.add(UserAgent(id=agent_id, user_id=user_id, name=f"agent-{agent_id}"))
        for instance_id, status in zip(instance_ids, statuses, strict=True):
            db.add(
                AgentInstance(
                    id=instance_id,
                    user_agent_id=agent_id,
                    user_id=user_id,
                    status=status,
                )
            )
        db.commit()
    return instance_ids


@pytest.fixture
def cleanup_user() -> Iterator[UUID]:
    """Yield a fresh user_id; on teardown remove any rows the test (or SUT)
    left behind. The happy path is that delete_user_account already
    cascaded everything, so these deletes are no-ops."""
    user_id = uuid4()
    try:
        yield user_id
    finally:
        with SessionLocal() as db:
            ids = [
                row.id
                for row in db.query(AgentInstance.id)
                .filter(AgentInstance.user_id == user_id)
                .all()
            ]
            if ids:
                db.query(Message).filter(Message.agent_instance_id.in_(ids)).delete(
                    synchronize_session=False
                )
            db.query(AgentInstance).filter(AgentInstance.user_id == user_id).delete(
                synchronize_session=False
            )
            db.query(UserAgent).filter(UserAgent.user_id == user_id).delete(
                synchronize_session=False
            )
            db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
            db.commit()


def test_delete_user_account_fires_terminate_for_each_live_instance(
    cleanup_user: UUID,
) -> None:
    user_id = cleanup_user
    live_ids = _seed_user_with_instances(
        user_id,
        [AgentStatus.ACTIVE, AgentStatus.AWAITING_INPUT],
    )

    with (
        patch("backend.db.queries._notify_terminate") as notify,
        SessionLocal() as db,
    ):
        delete_user_account(db, user_id)

    notified = {call.args[1] for call in notify.call_args_list}
    assert notified == set(live_ids)


def test_delete_user_account_skips_already_terminal_instances(
    cleanup_user: UUID,
) -> None:
    user_id = cleanup_user
    seeded = _seed_user_with_instances(
        user_id,
        [
            AgentStatus.ACTIVE,
            AgentStatus.DELETED,
            AgentStatus.COMPLETED,
            AgentStatus.FAILED,
        ],
    )
    live_id = seeded[0]

    with (
        patch("backend.db.queries._notify_terminate") as notify,
        SessionLocal() as db,
    ):
        delete_user_account(db, user_id)

    notified = {call.args[1] for call in notify.call_args_list}
    assert notified == {live_id}


def test_delete_user_account_with_no_instances_does_not_notify(
    cleanup_user: UUID,
) -> None:
    user_id = cleanup_user
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.commit()

    with (
        patch("backend.db.queries._notify_terminate") as notify,
        SessionLocal() as db,
    ):
        delete_user_account(db, user_id)

    notify.assert_not_called()


# ---------------------------------------------------------------------------
# Layer B — WS close via internal bridge (Phase 2b extension)
# ---------------------------------------------------------------------------


def test_delete_user_account_calls_post_close_user_after_commit(
    cleanup_user: UUID,
) -> None:
    """After the cascade commits, the backend pings the server process to
    close every live WS connection owned by this user — so the daemon drops
    within milliseconds instead of waiting for its next REST call to bounce."""
    user_id = cleanup_user
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.commit()

    with (
        patch("backend.broadcast_bridge.post_close_user") as close,
        SessionLocal() as db,
    ):
        delete_user_account(db, user_id)

    close.assert_called_once_with(str(user_id))


def test_delete_user_account_bridge_failure_does_not_raise(
    cleanup_user: UUID,
) -> None:
    """The DB delete already committed — a bridge exception must NOT propagate.
    The user is gone; the worst case is delayed WS teardown that PR #45's
    reactive bouncer still catches on the next REST write."""
    user_id = cleanup_user
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.commit()

    with (
        patch(
            "backend.broadcast_bridge.post_close_user",
            side_effect=RuntimeError("bridge down"),
        ),
        SessionLocal() as db,
    ):
        # Must not raise — caller (auth route) treats raise as deletion failure.
        delete_user_account(db, user_id)
