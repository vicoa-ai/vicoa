"""Integration tests for the backend message-write path (Phase 3 Slice 1).

`POST /agent-instances/{id}/messages` now commits inside `in_tx` and, on
commit, fires the §2.11 broadcast bridge so session/user-scoped WS clients
receive the new user message in realtime (websocket-migration §4 Phase 3).
These tests hit a real database, so they are marked `integration`.
"""

from collections.abc import Iterator
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException

from backend.api.agents import (
    create_user_message_endpoint,
    update_agent_status,
)
from backend.models import UserMessageRequest
from shared.database.enums import AgentStatus
from shared.database.models import AgentInstance, Message, User, UserAgent
from shared.database.session import SessionLocal

pytestmark = pytest.mark.integration


@pytest.fixture
def user_and_instance() -> Iterator[tuple[User, UUID]]:
    user_id, agent_id, instance_id = uuid4(), uuid4(), uuid4()
    email = f"{user_id}@test.vicoa"
    with SessionLocal() as db:
        db.add(User(id=user_id, email=email, display_name="Tester"))
        db.add(UserAgent(id=agent_id, user_id=user_id, name=f"agent-{agent_id}"))
        db.add(AgentInstance(id=instance_id, user_agent_id=agent_id, user_id=user_id))
        db.commit()
    # A detached User stands in for what `get_current_user` would inject.
    detached_user = User(id=user_id, email=email, display_name="Tester")
    try:
        yield detached_user, instance_id
    finally:
        with SessionLocal() as db:
            db.query(Message).filter(Message.agent_instance_id == instance_id).delete()
            db.query(AgentInstance).filter(AgentInstance.id == instance_id).delete()
            db.query(UserAgent).filter(UserAgent.id == agent_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()


def test_message_write_broadcasts_new_message_over_the_bridge(
    user_and_instance: tuple[User, UUID],
) -> None:
    user, instance_id = user_and_instance

    with (
        patch("backend.api.agents.post_broadcast") as mock_broadcast,
        SessionLocal() as db,
    ):
        response = create_user_message_endpoint(
            instance_id=instance_id,
            request=UserMessageRequest(content="hello agent"),
            background_tasks=BackgroundTasks(),
            current_user=user,
            db=db,
        )

    assert response.content == "hello agent"

    mock_broadcast.assert_called_once()
    broadcast_user_id, payload, rooms = mock_broadcast.call_args.args
    assert broadcast_user_id == str(user.id)
    assert payload["body"]["t"] == "new-message"
    assert payload["body"]["content"] == "hello agent"
    assert payload["entity_id"] == response.id
    assert rooms == [
        f"user:{user.id}:session:{instance_id}",
        f"user:{user.id}:user-scoped",
    ]

    with SessionLocal() as db:
        stored = db.query(Message).filter(Message.id == UUID(response.id)).first()
        assert stored is not None
        assert stored.content == "hello agent"


def test_message_write_to_unknown_instance_404s_and_does_not_broadcast(
    user_and_instance: tuple[User, UUID],
) -> None:
    user, _ = user_and_instance

    with (
        patch("backend.api.agents.post_broadcast") as mock_broadcast,
        SessionLocal() as db,
    ):
        with pytest.raises(HTTPException) as exc_info:
            create_user_message_endpoint(
                instance_id=uuid4(),  # not a real instance
                request=UserMessageRequest(content="nope"),
                background_tasks=BackgroundTasks(),
                current_user=user,
                db=db,
            )

    assert exc_info.value.status_code == 404
    # The write rolled back, so the after_commit broadcast must never fire.
    mock_broadcast.assert_not_called()


def test_backend_status_update_bridges_instance_update(
    user_and_instance: tuple[User, UUID],
) -> None:
    # A web-initiated instance write delivers an instance-update over the
    # §2.11 bridge so the user's other connections see it (Phase 4a).
    user, instance_id = user_and_instance

    with (
        patch("backend.api.agents.post_broadcast") as mock_broadcast,
        SessionLocal() as db,
    ):
        update_agent_status(
            instance_id=instance_id,
            status_update={"status": "REVIEWED"},
            current_user=user,
            db=db,
        )

    mock_broadcast.assert_called_once()
    _broadcast_user_id, payload, _rooms = mock_broadcast.call_args.args
    assert payload["entity"] == "agent_instances"
    assert payload["entity_id"] == str(instance_id)
    assert payload["body"]["t"] == "instance-update"
    assert payload["body"]["status"] == "REVIEWED"


def test_queued_stamp_when_instance_active(
    user_and_instance: tuple[User, UUID],
) -> None:
    # `user_and_instance` creates the AgentInstance with no explicit status,
    # so it takes the model default of AgentStatus.ACTIVE (models.py) — i.e.
    # the agent is mid-turn/busy when this message arrives.
    user, instance_id = user_and_instance

    with (
        patch("backend.api.agents.post_broadcast"),
        SessionLocal() as db,
    ):
        response = create_user_message_endpoint(
            instance_id=instance_id,
            request=UserMessageRequest(content="hello while busy"),
            background_tasks=BackgroundTasks(),
            current_user=user,
            db=db,
        )

    assert response.message_metadata is not None
    assert response.message_metadata["queue"]["status"] == "queued"

    with SessionLocal() as db:
        stored = db.query(Message).filter(Message.id == UUID(response.id)).first()
        assert stored is not None
        assert stored.message_metadata["queue"]["status"] == "queued"


def test_queued_stamp_omitted_when_instance_not_active(
    user_and_instance: tuple[User, UUID],
) -> None:
    # Flip the instance to AWAITING_INPUT before sending — the agent is
    # idle/waiting on the user, so the message is not queued behind
    # anything and should not carry the `queue` key.
    user, instance_id = user_and_instance
    with SessionLocal() as db:
        instance = (
            db.query(AgentInstance).filter(AgentInstance.id == instance_id).first()
        )
        assert instance is not None
        instance.status = AgentStatus.AWAITING_INPUT
        db.commit()

    with (
        patch("backend.api.agents.post_broadcast"),
        SessionLocal() as db,
    ):
        response = create_user_message_endpoint(
            instance_id=instance_id,
            request=UserMessageRequest(content="hello while idle"),
            background_tasks=BackgroundTasks(),
            current_user=user,
            db=db,
        )

    assert not (response.message_metadata or {}).get("queue")

    with SessionLocal() as db:
        stored = db.query(Message).filter(Message.id == UUID(response.id)).first()
        assert stored is not None
        assert not (stored.message_metadata or {}).get("queue")
