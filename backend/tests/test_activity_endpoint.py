"""Integration tests for GET /api/v1/activity (profile heatmap/streak).

Implemented in the `backend` app (backend.api.activity), served on api.vicoa.ai
— the host the web/desktop client targets. Needs a real database, so marked
integration.
"""

from collections.abc import Iterator
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from backend.api.activity import get_activity
from shared.database.enums import AgentStatus, SenderType
from shared.database.models import (
    AgentInstance,
    Message,
    User,
    UserAgent,
)
from shared.database.session import SessionLocal

pytestmark = pytest.mark.integration


def _add_message(
    db, instance_id: UUID, sender: SenderType, when: datetime, user_id: UUID | None
) -> None:
    db.add(
        Message(
            id=uuid4(),
            agent_instance_id=instance_id,
            sender_type=sender,
            sender_user_id=user_id if sender == SenderType.USER else None,
            content="x",
            created_at=when,  # naive UTC — matches the column
        )
    )


@pytest.fixture
def user_with_activity() -> Iterator[UUID]:
    """A user with one session and messages across three days:

    - 2026-07-13: two user messages + one agent message (agent excluded)
    - 2026-07-10: one user message
    """
    user_id, agent_id, instance_id = uuid4(), uuid4(), uuid4()
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.flush()
        db.add(UserAgent(id=agent_id, user_id=user_id, name="claude"))
        db.add(
            AgentInstance(
                id=instance_id,
                user_agent_id=agent_id,
                user_id=user_id,
                status=AgentStatus.ACTIVE,
                name="s",
            )
        )
        db.flush()
        _add_message(
            db, instance_id, SenderType.USER, datetime(2026, 7, 13, 9, 0), user_id
        )
        _add_message(
            db, instance_id, SenderType.USER, datetime(2026, 7, 13, 18, 0), user_id
        )
        _add_message(
            db, instance_id, SenderType.AGENT, datetime(2026, 7, 13, 18, 1), None
        )
        _add_message(
            db, instance_id, SenderType.USER, datetime(2026, 7, 10, 12, 0), user_id
        )
        db.commit()
    try:
        yield user_id
    finally:
        with SessionLocal() as db:
            db.query(Message).filter(Message.agent_instance_id == instance_id).delete()
            db.query(AgentInstance).filter(AgentInstance.user_id == user_id).delete()
            db.query(UserAgent).filter(UserAgent.user_id == user_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()


def test_activity_buckets_user_messages_by_day_and_totals(
    user_with_activity: UUID,
) -> None:
    user_id = user_with_activity
    with SessionLocal() as db:
        resp = get_activity(user_id=user_id, since=None, db=db)

    # daily + total_user_messages count only user-sent messages; the agent
    # message on 07-13 is excluded there but included in total_messages.
    assert resp.daily == {"2026-07-13": 2, "2026-07-10": 1}
    assert resp.total_user_messages == 3
    assert resp.total_messages == 4  # 3 user + 1 agent
    assert resp.total_sessions == 1


def test_activity_since_limits_daily_but_not_totals(user_with_activity: UUID) -> None:
    user_id = user_with_activity
    with SessionLocal() as db:
        resp = get_activity(user_id=user_id, since="2026-07-12", db=db)

    # 07-10 is before `since` -> dropped from daily; totals stay all-time.
    assert resp.daily == {"2026-07-13": 2}
    assert resp.total_user_messages == 3
    assert resp.total_messages == 4
    assert resp.total_sessions == 1


def test_activity_rejects_a_malformed_since(user_with_activity: UUID) -> None:
    from fastapi import HTTPException

    user_id = user_with_activity
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            get_activity(user_id=user_id, since="07/12/2026", db=db)
    assert exc.value.status_code == 400


def test_activity_is_scoped_to_the_requesting_user(user_with_activity: UUID) -> None:
    """A second user's messages must not leak into the first user's activity."""
    other_id, other_agent, other_instance = uuid4(), uuid4(), uuid4()
    with SessionLocal() as db:
        db.add(User(id=other_id, email=f"{other_id}@test.vicoa", display_name="o"))
        db.flush()
        db.add(UserAgent(id=other_agent, user_id=other_id, name="claude"))
        db.add(
            AgentInstance(
                id=other_instance,
                user_agent_id=other_agent,
                user_id=other_id,
                status=AgentStatus.ACTIVE,
                name="s2",
            )
        )
        db.flush()
        _add_message(
            db, other_instance, SenderType.USER, datetime(2026, 7, 13, 9, 0), other_id
        )
        db.commit()
    try:
        with SessionLocal() as db:
            resp = get_activity(user_id=user_with_activity, since=None, db=db)
        assert resp.total_sessions == 1  # not 2
        assert resp.daily == {"2026-07-13": 2, "2026-07-10": 1}
    finally:
        with SessionLocal() as db:
            db.query(Message).filter(
                Message.agent_instance_id == other_instance
            ).delete()
            db.query(AgentInstance).filter(AgentInstance.user_id == other_id).delete()
            db.query(UserAgent).filter(UserAgent.user_id == other_id).delete()
            db.query(User).filter(User.id == other_id).delete()
            db.commit()
