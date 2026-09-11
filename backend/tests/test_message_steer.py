"""`steer_user_message` query + `POST .../messages/{id}/steer` endpoint.

The queue bar's Steer button: a user asks for a message still sitting in
`queued` state to be delivered into the agent's running turn. The endpoint
only flips the row to `queue.status=steer` and broadcasts the patch (see
`test_message_cancel.py` for the sibling cancel flow); the daemon does the
delivery and settles the row afterwards (`test_message_consumed.py` covers
the `consumed`+`steered` and `requeue` halves). The strict `queued` guard
means a message already consumed, cancelled, or steering is never
re-stamped. These tests hit a real database, so they are marked
`integration`.
"""

from collections.abc import Iterator
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from backend.api.agents import steer_queued_message_endpoint
from backend.db.queries import steer_user_message
from shared.database.enums import AgentStatus, SenderType
from shared.database.models import AgentInstance, AgentType, Message, User
from shared.database.session import SessionLocal

pytestmark = pytest.mark.integration


@pytest.fixture
def user_and_instance() -> Iterator[tuple[User, UUID]]:
    user_id, agent_id, instance_id = uuid4(), uuid4(), uuid4()
    email = f"{user_id}@test.vicoa"
    with SessionLocal() as db:
        db.add(User(id=user_id, email=email, display_name="Tester"))
        db.add(AgentType(id=agent_id, user_id=user_id, name=f"agent-{agent_id}"))
        db.add(
            AgentInstance(
                id=instance_id,
                agent_type_id=agent_id,
                user_id=user_id,
                status=AgentStatus.ACTIVE,
            )
        )
        db.commit()
    detached_user = User(id=user_id, email=email, display_name="Tester")
    try:
        yield detached_user, instance_id
    finally:
        with SessionLocal() as db:
            db.query(Message).filter(Message.agent_instance_id == instance_id).delete()
            db.query(AgentInstance).filter(AgentInstance.id == instance_id).delete()
            db.query(AgentType).filter(AgentType.id == agent_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()


def _make_message(
    instance_id: UUID,
    metadata: dict | None,
    sender_type: SenderType = SenderType.USER,
) -> UUID:
    message_id = uuid4()
    with SessionLocal() as db:
        db.add(
            Message(
                id=message_id,
                agent_instance_id=instance_id,
                sender_type=sender_type,
                content="hello",
                requires_user_input=False,
                message_metadata=metadata,
            )
        )
        db.commit()
    return message_id


def _stored_queue(message_id: UUID) -> dict:
    with SessionLocal() as db:
        stored = db.query(Message).filter(Message.id == message_id).first()
        assert stored is not None
        return (stored.message_metadata or {}).get("queue") or {}


# ---------------------------------------------------------------------------
# Query: steer_user_message
# ---------------------------------------------------------------------------


def test_steer_user_message_flips_a_queued_message(
    user_and_instance: tuple[User, UUID],
) -> None:
    _user, instance_id = user_and_instance
    message_id = _make_message(instance_id, {"queue": {"status": "queued"}})

    with SessionLocal() as db:
        assert steer_user_message(db, message_id) is True
        db.commit()

    queue = _stored_queue(message_id)
    assert queue["status"] == "steer"
    assert "steer_requested_at" in queue


@pytest.mark.parametrize("status", ["consumed", "cancelled", "steer"])
def test_steer_user_message_is_noop_unless_queued(
    user_and_instance: tuple[User, UUID], status: str
) -> None:
    _user, instance_id = user_and_instance
    message_id = _make_message(instance_id, {"queue": {"status": status}})

    with SessionLocal() as db:
        assert steer_user_message(db, message_id) is False
        db.commit()

    assert _stored_queue(message_id)["status"] == status


def test_steer_user_message_is_noop_with_no_queue_metadata(
    user_and_instance: tuple[User, UUID],
) -> None:
    # A message that was never queued (sent while the agent was idle) has
    # nothing to steer; unlike cancel, this must not invent a queue entry.
    _user, instance_id = user_and_instance
    message_id = _make_message(instance_id, None)

    with SessionLocal() as db:
        assert steer_user_message(db, message_id) is False
        db.commit()

    assert _stored_queue(message_id) == {}


def test_steer_user_message_is_noop_for_non_user_message(
    user_and_instance: tuple[User, UUID],
) -> None:
    _user, instance_id = user_and_instance
    message_id = _make_message(
        instance_id, {"queue": {"status": "queued"}}, sender_type=SenderType.AGENT
    )

    with SessionLocal() as db:
        assert steer_user_message(db, message_id) is False
        db.commit()

    assert _stored_queue(message_id)["status"] == "queued"


def test_steer_user_message_preserves_sibling_metadata_keys(
    user_and_instance: tuple[User, UUID],
) -> None:
    _user, instance_id = user_and_instance
    message_id = _make_message(
        instance_id,
        {"queue": {"status": "queued"}, "attachments": [{"id": "att-1"}]},
    )

    with SessionLocal() as db:
        assert steer_user_message(db, message_id) is True
        db.commit()

    with SessionLocal() as db:
        stored = db.query(Message).filter(Message.id == message_id).first()
        assert stored is not None
        assert stored.message_metadata["attachments"] == [{"id": "att-1"}]
        assert stored.message_metadata["queue"]["status"] == "steer"


def test_steer_user_message_returns_false_for_unknown_message() -> None:
    with SessionLocal() as db:
        assert steer_user_message(db, uuid4()) is False


# ---------------------------------------------------------------------------
# Endpoint: POST /agent-instances/{instance_id}/messages/{message_id}/steer
# ---------------------------------------------------------------------------


def test_steer_endpoint_flips_and_broadcasts_when_queued(
    user_and_instance: tuple[User, UUID],
) -> None:
    user, instance_id = user_and_instance
    message_id = _make_message(instance_id, {"queue": {"status": "queued"}})

    with (
        patch("backend.api.agents.post_broadcast") as mock_broadcast,
        SessionLocal() as db,
    ):
        response = steer_queued_message_endpoint(
            instance_id=instance_id,
            message_id=message_id,
            current_user=user,
            db=db,
        )

    assert response == {"steered": True}

    mock_broadcast.assert_called_once()
    broadcast_user_id, payload, rooms = mock_broadcast.call_args.args
    assert broadcast_user_id == str(user.id)
    assert payload["body"]["t"] == "message-update"
    assert payload["body"]["id"] == str(message_id)
    assert payload["body"]["message_metadata"]["queue"]["status"] == "steer"
    assert rooms == [
        f"user:{user.id}:user-scoped",
        f"user:{user.id}:session:{instance_id}",
    ]
    assert _stored_queue(message_id)["status"] == "steer"


def test_steer_endpoint_rejected_when_already_consumed(
    user_and_instance: tuple[User, UUID],
) -> None:
    user, instance_id = user_and_instance
    message_id = _make_message(instance_id, {"queue": {"status": "consumed"}})

    with (
        patch("backend.api.agents.post_broadcast") as mock_broadcast,
        SessionLocal() as db,
    ):
        response = steer_queued_message_endpoint(
            instance_id=instance_id,
            message_id=message_id,
            current_user=user,
            db=db,
        )

    assert response == {"steered": False}
    mock_broadcast.assert_not_called()
    assert _stored_queue(message_id)["status"] == "consumed"


def test_steer_endpoint_404s_for_unknown_message(
    user_and_instance: tuple[User, UUID],
) -> None:
    user, instance_id = user_and_instance

    with (
        patch("backend.api.agents.post_broadcast") as mock_broadcast,
        SessionLocal() as db,
    ):
        with pytest.raises(HTTPException) as exc_info:
            steer_queued_message_endpoint(
                instance_id=instance_id,
                message_id=uuid4(),
                current_user=user,
                db=db,
            )

    assert exc_info.value.status_code == 404
    mock_broadcast.assert_not_called()


def test_steer_endpoint_404s_for_another_users_instance(
    user_and_instance: tuple[User, UUID],
) -> None:
    _user, instance_id = user_and_instance
    message_id = _make_message(instance_id, {"queue": {"status": "queued"}})
    other_user = User(id=uuid4(), email=f"{uuid4()}@test.vicoa", display_name="Other")

    with (
        patch("backend.api.agents.post_broadcast") as mock_broadcast,
        SessionLocal() as db,
    ):
        with pytest.raises(HTTPException) as exc_info:
            steer_queued_message_endpoint(
                instance_id=instance_id,
                message_id=message_id,
                current_user=other_user,
                db=db,
            )

    assert exc_info.value.status_code == 404
    mock_broadcast.assert_not_called()
    assert _stored_queue(message_id)["status"] == "queued"
