"""`cancel_user_message` query + `POST .../messages/{id}/cancel` endpoint.

Lets a user cancel a message still sitting in `queued` state (see `f02e6e4`
for the `queued` stamp this races against, and `0424652` for the
`message-update` WS envelope this endpoint fires). Mirrors
`servers.shared.db.queries.mark_message_consumed`'s cancel-aware guard, with
the roles reversed: cancelling is a no-op once the agent has already
consumed the message (atomic cancel/consume race resolution). Runs on the
human-facing `backend` process, so the broadcast goes out over the
`post_broadcast` cross-process bridge rather than directly through
`connection_manager`. These tests hit a real database, so they are marked
`integration`.
"""

from collections.abc import Iterator
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from backend.api.agents import cancel_queued_message_endpoint
from backend.db.queries import cancel_user_message
from shared.database.enums import AgentStatus, InstanceAccessLevel, SenderType
from shared.database.models import (
    AgentInstance,
    Message,
    User,
    UserAgent,
    UserInstanceAccess,
)
from shared.database.session import SessionLocal

pytestmark = pytest.mark.integration


@pytest.fixture
def user_and_instance() -> Iterator[tuple[User, UUID]]:
    user_id, agent_id, instance_id = uuid4(), uuid4(), uuid4()
    email = f"{user_id}@test.vicoa"
    with SessionLocal() as db:
        db.add(User(id=user_id, email=email, display_name="Tester"))
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


# ---------------------------------------------------------------------------
# Query: cancel_user_message
# ---------------------------------------------------------------------------


def test_cancel_user_message_succeeds_when_queued(
    user_and_instance: tuple[User, UUID],
) -> None:
    _user, instance_id = user_and_instance
    message_id = _make_message(instance_id, {"queue": {"status": "queued"}})

    with SessionLocal() as db:
        cancelled = cancel_user_message(db, message_id)
        assert cancelled is True
        db.commit()

    with SessionLocal() as db:
        stored = db.query(Message).filter(Message.id == message_id).first()
        assert stored is not None
        assert stored.message_metadata["queue"]["status"] == "cancelled"
        assert "cancelled_at" in stored.message_metadata["queue"]


def test_cancel_user_message_succeeds_with_no_metadata(
    user_and_instance: tuple[User, UUID],
) -> None:
    # Regression guard: `message_metadata` defaults to Python `None`, and
    # this JSONB column doesn't set `none_as_null=True`, so "no metadata
    # yet" is stored as the JSON scalar `null`, not SQL NULL. This is the
    # majority case for USER messages — only ones sent while the instance is
    # ACTIVE get the `queue` stamp in the first place (see `f02e6e4`).
    # Mirrors
    # `test_message_consumed.py::test_mark_message_consumed_handles_no_metadata`.
    _user, instance_id = user_and_instance
    message_id = _make_message(instance_id, None)

    with SessionLocal() as db:
        cancelled = cancel_user_message(db, message_id)
        assert cancelled is True
        db.commit()

    with SessionLocal() as db:
        stored = db.query(Message).filter(Message.id == message_id).first()
        assert stored is not None
        assert stored.message_metadata["queue"]["status"] == "cancelled"
        assert "cancelled_at" in stored.message_metadata["queue"]


def test_cancel_user_message_is_noop_when_consumed(
    user_and_instance: tuple[User, UUID],
) -> None:
    _user, instance_id = user_and_instance
    message_id = _make_message(instance_id, {"queue": {"status": "consumed"}})

    with SessionLocal() as db:
        cancelled = cancel_user_message(db, message_id)
        assert cancelled is False
        db.commit()

    with SessionLocal() as db:
        stored = db.query(Message).filter(Message.id == message_id).first()
        assert stored is not None
        assert stored.message_metadata["queue"]["status"] == "consumed"


def test_cancel_user_message_is_noop_for_non_user_message(
    user_and_instance: tuple[User, UUID],
) -> None:
    _user, instance_id = user_and_instance
    message_id = _make_message(
        instance_id,
        {"queue": {"status": "queued"}},
        sender_type=SenderType.AGENT,
    )

    with SessionLocal() as db:
        cancelled = cancel_user_message(db, message_id)
        assert cancelled is False
        db.commit()

    with SessionLocal() as db:
        stored = db.query(Message).filter(Message.id == message_id).first()
        assert stored is not None
        assert stored.message_metadata["queue"]["status"] == "queued"


def test_cancel_user_message_preserves_sibling_metadata_keys(
    user_and_instance: tuple[User, UUID],
) -> None:
    # Guards the shared jsonb_set pattern (copied from
    # `servers.shared.db.queries.mark_message_consumed`, which a prior review
    # flagged as manually-verified-only): only the `queue` key should
    # change, every other top-level metadata key must survive untouched.
    _user, instance_id = user_and_instance
    message_id = _make_message(
        instance_id,
        {
            "attachments": [{"id": "att-1", "mime_type": "image/png"}],
            "queue": {"status": "queued"},
        },
    )

    with SessionLocal() as db:
        cancelled = cancel_user_message(db, message_id)
        assert cancelled is True
        db.commit()

    with SessionLocal() as db:
        stored = db.query(Message).filter(Message.id == message_id).first()
        assert stored is not None
        assert stored.message_metadata["queue"]["status"] == "cancelled"
        assert stored.message_metadata["attachments"] == [
            {"id": "att-1", "mime_type": "image/png"}
        ]


def test_cancel_user_message_returns_false_for_unknown_message() -> None:
    with SessionLocal() as db:
        assert cancel_user_message(db, uuid4()) is False


# ---------------------------------------------------------------------------
# Endpoint: POST /agent-instances/{instance_id}/messages/{message_id}/cancel
# ---------------------------------------------------------------------------


def test_cancel_endpoint_succeeds_when_queued(
    user_and_instance: tuple[User, UUID],
) -> None:
    user, instance_id = user_and_instance
    message_id = _make_message(instance_id, {"queue": {"status": "queued"}})

    with (
        patch("backend.api.agents.post_broadcast") as mock_broadcast,
        SessionLocal() as db,
    ):
        response = cancel_queued_message_endpoint(
            instance_id=instance_id,
            message_id=message_id,
            current_user=user,
            db=db,
        )

    assert response == {"cancelled": True}

    mock_broadcast.assert_called_once()
    broadcast_user_id, payload, rooms = mock_broadcast.call_args.args
    assert broadcast_user_id == str(user.id)
    assert payload["body"]["t"] == "message-update"
    assert payload["body"]["id"] == str(message_id)
    assert payload["body"]["message_metadata"]["queue"]["status"] == "cancelled"
    assert rooms == [
        f"user:{user.id}:user-scoped",
        f"user:{user.id}:session:{instance_id}",
    ]

    with SessionLocal() as db:
        stored = db.query(Message).filter(Message.id == message_id).first()
        assert stored is not None
        assert stored.message_metadata["queue"]["status"] == "cancelled"


def test_cancel_endpoint_succeeds_for_write_access_collaborator(
    user_and_instance: tuple[User, UUID],
) -> None:
    # Finding 1 regression guard: the access check must mirror
    # `create_user_message_endpoint`'s `get_instance_and_access` + WRITE
    # floor, not raw `AgentInstance.user_id` ownership — a collaborator
    # granted WRITE access via instance sharing (`UserInstanceAccess`) must
    # be able to cancel a message, not just the literal instance owner.
    owner, instance_id = user_and_instance
    message_id = _make_message(instance_id, {"queue": {"status": "queued"}})

    collaborator_id = uuid4()
    collaborator_email = f"{collaborator_id}@test.vicoa"
    with SessionLocal() as db:
        db.add(
            User(
                id=collaborator_id,
                email=collaborator_email,
                display_name="Collaborator",
            )
        )
        db.add(
            UserInstanceAccess(
                agent_instance_id=instance_id,
                shared_email=collaborator_email,
                user_id=collaborator_id,
                access=InstanceAccessLevel.WRITE,
                granted_by_user_id=owner.id,
            )
        )
        db.commit()

    # A detached User stands in for what `get_current_user` would inject —
    # mirrors the `user_and_instance` fixture's own `detached_user` pattern,
    # since `collaborator` above is expired/session-bound after `commit()`.
    collaborator = User(
        id=collaborator_id, email=collaborator_email, display_name="Collaborator"
    )

    try:
        with (
            patch("backend.api.agents.post_broadcast") as mock_broadcast,
            SessionLocal() as db,
        ):
            response = cancel_queued_message_endpoint(
                instance_id=instance_id,
                message_id=message_id,
                current_user=collaborator,
                db=db,
            )

        assert response == {"cancelled": True}
        mock_broadcast.assert_called_once()

        with SessionLocal() as db:
            stored = db.query(Message).filter(Message.id == message_id).first()
            assert stored is not None
            assert stored.message_metadata["queue"]["status"] == "cancelled"
    finally:
        # `UserInstanceAccess.user_id` cascades on delete, so removing the
        # collaborator user is enough to clean up the access grant too.
        with SessionLocal() as db:
            db.query(User).filter(User.id == collaborator.id).delete()
            db.commit()


def test_cancel_endpoint_rejected_when_consumed(
    user_and_instance: tuple[User, UUID],
) -> None:
    user, instance_id = user_and_instance
    message_id = _make_message(instance_id, {"queue": {"status": "consumed"}})

    with (
        patch("backend.api.agents.post_broadcast") as mock_broadcast,
        SessionLocal() as db,
    ):
        response = cancel_queued_message_endpoint(
            instance_id=instance_id,
            message_id=message_id,
            current_user=user,
            db=db,
        )

    assert response == {"cancelled": False}
    mock_broadcast.assert_not_called()

    with SessionLocal() as db:
        stored = db.query(Message).filter(Message.id == message_id).first()
        assert stored is not None
        assert stored.message_metadata["queue"]["status"] == "consumed"


def test_cancel_endpoint_404s_for_unknown_message(
    user_and_instance: tuple[User, UUID],
) -> None:
    user, instance_id = user_and_instance

    with (
        patch("backend.api.agents.post_broadcast") as mock_broadcast,
        SessionLocal() as db,
    ):
        with pytest.raises(HTTPException) as exc_info:
            cancel_queued_message_endpoint(
                instance_id=instance_id,
                message_id=uuid4(),
                current_user=user,
                db=db,
            )

    assert exc_info.value.status_code == 404
    mock_broadcast.assert_not_called()


def test_cancel_endpoint_404s_for_another_users_instance(
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
            cancel_queued_message_endpoint(
                instance_id=instance_id,
                message_id=message_id,
                current_user=other_user,
                db=db,
            )

    assert exc_info.value.status_code == 404
    mock_broadcast.assert_not_called()
