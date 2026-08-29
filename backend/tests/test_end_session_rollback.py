"""Verify end_session_endpoint's exception path leaves no DB leakage
without an explicit db.rollback().

The PR removes db.rollback() from the except clause, relying on get_db()'s
finally: db.close() to handle cleanup. This test forces a failure AFTER
end_session has mutated instance.status / ended_at but BEFORE db.commit(),
then confirms the uncommitted mutations did not leak across sessions.
"""

from collections.abc import Iterator
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from servers.api.models import EndSessionRequest
from servers.api.routers import end_session_endpoint
from shared.database.enums import AgentStatus
from shared.database.models import AgentInstance, Message, User, UserAgent
from shared.database.session import SessionLocal

pytestmark = pytest.mark.integration


@pytest.fixture
def user_instance() -> Iterator[tuple[UUID, UUID]]:
    user_id, agent_id, instance_id = uuid4(), uuid4(), uuid4()
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.flush()
        db.add(UserAgent(id=agent_id, user_id=user_id, name=f"agent-{agent_id}"))
        db.add(
            AgentInstance(
                id=instance_id,
                user_agent_id=agent_id,
                user_id=user_id,
                status=AgentStatus.ACTIVE,
            )
        )
        db.commit()
    try:
        yield user_id, instance_id
    finally:
        with SessionLocal() as db:
            instance_ids = [
                row.id
                for row in db.query(AgentInstance.id)
                .filter(AgentInstance.user_id == user_id)
                .all()
            ]
            if instance_ids:
                db.query(Message).filter(
                    Message.agent_instance_id.in_(instance_ids)
                ).delete(synchronize_session=False)
            db.query(AgentInstance).filter(AgentInstance.user_id == user_id).delete(
                synchronize_session=False
            )
            db.query(UserAgent).filter(UserAgent.user_id == user_id).delete(
                synchronize_session=False
            )
            db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
            db.commit()


def _read_status(instance_id: UUID) -> AgentStatus:
    with SessionLocal() as db:
        inst = db.get(AgentInstance, instance_id)
        assert inst is not None
        return inst.status


def test_end_session_exception_does_not_leak_writes(
    user_instance: tuple[UUID, UUID],
) -> None:
    user_id, instance_id = user_instance

    # Sanity: starts ACTIVE.
    assert _read_status(instance_id) == AgentStatus.ACTIVE

    # Force a failure AFTER end_session's mutations but BEFORE db.commit() —
    # the worst-case for "did we need explicit rollback".
    with patch(
        "servers.api.routers._broadcast_instance_update",
        side_effect=RuntimeError("simulated post-mutation failure"),
    ):
        with SessionLocal() as db:
            with pytest.raises(HTTPException) as exc_info:
                end_session_endpoint(
                    request=EndSessionRequest(agent_instance_id=str(instance_id)),
                    user_id=str(user_id),
                    db=db,
                )
            assert exc_info.value.status_code == 500

    # The pending status/ended_at mutations must NOT have leaked.
    # If db.close() failed to roll back, this would be COMPLETED.
    assert _read_status(instance_id) == AgentStatus.ACTIVE
