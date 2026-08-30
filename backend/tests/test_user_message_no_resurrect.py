"""Sending a message must not resurrect a dead session.

``create_user_message_with_access`` used to set ``status = ACTIVE``
unconditionally, so writing to a session whose agent was long gone flipped it
back to ACTIVE — meaning the user's own message is what made the corpse render
a "working" spinner, indefinitely.

The guard revives a terminal session only when its agent is still heartbeating
(the archive-a-live-session case). Otherwise the row stays terminal and the
client can surface it as stopped rather than busy.

Hits a real Postgres, so marked `integration`.
See plans/todos/session-liveness-and-resume.md.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from backend.db.queries import create_user_message_with_access
from shared.database.enums import AgentStatus
from shared.database.models import (
    AgentInstance,
    Message,
    User,
    UserAgent,
)
from shared.database.session import SessionLocal

pytestmark = pytest.mark.integration


@pytest.fixture
def user_and_agent() -> Iterator[tuple[UUID, UUID]]:
    uid = uuid4()
    agent_id = uuid4()
    with SessionLocal() as db:
        db.add(User(id=uid, email=f"{uid}@test.vicoa", display_name="t"))
        db.commit()
        db.add(UserAgent(id=agent_id, user_id=uid, name="claude"))
        db.commit()
    try:
        yield uid, agent_id
    finally:
        with SessionLocal() as db:
            instance_ids = [
                row.id
                for row in db.query(AgentInstance)
                .filter(AgentInstance.user_id == uid)
                .all()
            ]
            if instance_ids:
                db.query(AgentInstance).filter(
                    AgentInstance.id.in_(instance_ids)
                ).update({AgentInstance.last_read_message_id: None})
                db.commit()
                db.query(Message).filter(
                    Message.agent_instance_id.in_(instance_ids)
                ).delete(synchronize_session=False)
            db.query(AgentInstance).filter(AgentInstance.user_id == uid).delete()
            db.query(UserAgent).filter(UserAgent.user_id == uid).delete()
            db.query(User).filter(User.id == uid).delete()
            db.commit()


def _make_instance(
    uid: UUID,
    agent_id: UUID,
    status: AgentStatus,
    heartbeat_age_seconds: float | None,
) -> UUID:
    instance_id = uuid4()
    heartbeat = (
        None
        if heartbeat_age_seconds is None
        else datetime.now(timezone.utc) - timedelta(seconds=heartbeat_age_seconds)
    )
    with SessionLocal() as db:
        db.add(
            AgentInstance(
                id=instance_id,
                user_id=uid,
                user_agent_id=agent_id,
                status=status,
                last_heartbeat_at=heartbeat,
            )
        )
        db.commit()
    return instance_id


def _send_and_read_status(instance_id: UUID, uid: UUID) -> AgentStatus:
    with SessionLocal() as db:
        create_user_message_with_access(
            db=db, instance_id=instance_id, user_id=uid, content="hello?"
        )
        db.commit()
    with SessionLocal() as db:
        instance = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        return instance.status


@pytest.mark.parametrize(
    "terminal_status",
    [
        AgentStatus.COMPLETED,
        AgentStatus.FAILED,
        AgentStatus.KILLED,
        AgentStatus.DISCONNECTED,
    ],
)
def test_message_does_not_revive_dead_session(
    user_and_agent: tuple[UUID, UUID], terminal_status: AgentStatus
):
    """The core bug: a message to a long-dead session must not claim it's working."""
    uid, agent_id = user_and_agent
    instance_id = _make_instance(
        uid, agent_id, terminal_status, heartbeat_age_seconds=None
    )

    assert _send_and_read_status(instance_id, uid) is terminal_status


def test_message_does_not_revive_session_with_stale_heartbeat(
    user_and_agent: tuple[UUID, UUID],
):
    uid, agent_id = user_and_agent
    instance_id = _make_instance(
        uid, agent_id, AgentStatus.COMPLETED, heartbeat_age_seconds=3600
    )

    assert _send_and_read_status(instance_id, uid) is AgentStatus.COMPLETED


def test_message_revives_archived_session_whose_agent_is_still_alive(
    user_and_agent: tuple[UUID, UUID],
):
    """Archiving writes COMPLETED while the agent may still be running. Writing
    to it should hand the turn back to that live agent."""
    uid, agent_id = user_and_agent
    instance_id = _make_instance(
        uid, agent_id, AgentStatus.COMPLETED, heartbeat_age_seconds=5
    )

    assert _send_and_read_status(instance_id, uid) is AgentStatus.ACTIVE


def test_message_still_reactivates_awaiting_input(user_and_agent: tuple[UUID, UUID]):
    """The transition we must NOT break: answering an agent's question resumes it,
    regardless of heartbeat freshness."""
    uid, agent_id = user_and_agent
    instance_id = _make_instance(
        uid, agent_id, AgentStatus.AWAITING_INPUT, heartbeat_age_seconds=None
    )

    assert _send_and_read_status(instance_id, uid) is AgentStatus.ACTIVE


def test_message_is_still_persisted_for_a_dead_session(
    user_and_agent: tuple[UUID, UUID],
):
    """We stop lying about the status — we do not drop the user's message. It
    is delivered if the session is later resumed."""
    uid, agent_id = user_and_agent
    instance_id = _make_instance(
        uid, agent_id, AgentStatus.KILLED, heartbeat_age_seconds=None
    )

    _send_and_read_status(instance_id, uid)

    with SessionLocal() as db:
        messages = (
            db.query(Message).filter(Message.agent_instance_id == instance_id).all()
        )
    assert [m.content for m in messages] == ["hello?"]
