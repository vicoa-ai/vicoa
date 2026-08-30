"""`mark_message_consumed` query + `PATCH /messages/{id}/consumed` endpoint.

Completes the queued->consumed transition (see `f02e6e4` for the `queued`
stamp and `0424652` for the `message-update` WS envelope this endpoint
fires). These tests hit a real database, so they are marked `integration`.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from servers.api.routers import mark_message_consumed_endpoint
from servers.shared.db.queries import mark_message_consumed
from shared.database.enums import AgentStatus, SenderType
from shared.database.models import AgentInstance, Message, User, UserAgent
from shared.database.session import SessionLocal
from shared.websocket.connection_manager import Connection, connection_manager

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
            db.query(Message).filter(Message.agent_instance_id == instance_id).delete()
            db.query(AgentInstance).filter(AgentInstance.id == instance_id).delete()
            db.query(UserAgent).filter(UserAgent.id == agent_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()


def _make_user_message(instance_id: UUID, metadata: dict | None) -> UUID:
    message_id = uuid4()
    with SessionLocal() as db:
        db.add(
            Message(
                id=message_id,
                agent_instance_id=instance_id,
                sender_type=SenderType.USER,
                content="hello",
                requires_user_input=False,
                message_metadata=metadata,
            )
        )
        db.commit()
    return message_id


def _user_conn(user_id: UUID) -> Connection:
    return Connection(
        connection_id=uuid4().hex,
        user_id=str(user_id),
        scope="user-scoped",
        rooms=frozenset({f"user:{user_id}:user-scoped"}),
    )


def _drain(conn: Connection) -> list[dict]:
    frames: list[dict] = []
    while True:
        try:
            frames.append(conn.outbox.get_nowait())
        except Exception:  # noqa: BLE001 - QueueEmpty ends the drain
            break
    return frames


# ---------------------------------------------------------------------------
# Query: mark_message_consumed
# ---------------------------------------------------------------------------


def test_mark_message_consumed_sets_status(
    user_instance: tuple[UUID, UUID],
) -> None:
    _user_id, instance_id = user_instance
    message_id = _make_user_message(instance_id, {"queue": {"status": "queued"}})

    with SessionLocal() as db:
        updated = mark_message_consumed(db, message_id)
        assert updated is not None
        assert updated.message_metadata["queue"]["status"] == "consumed"
        assert "consumed_at" in updated.message_metadata["queue"]
        db.commit()

    with SessionLocal() as db:
        stored = db.query(Message).filter(Message.id == message_id).first()
        assert stored is not None
        assert stored.message_metadata["queue"]["status"] == "consumed"


def test_mark_message_consumed_does_not_override_cancelled(
    user_instance: tuple[UUID, UUID],
) -> None:
    _user_id, instance_id = user_instance
    message_id = _make_user_message(instance_id, {"queue": {"status": "cancelled"}})

    with SessionLocal() as db:
        updated = mark_message_consumed(db, message_id)
        assert updated is not None
        assert updated.message_metadata["queue"]["status"] == "cancelled"
        db.commit()

    with SessionLocal() as db:
        stored = db.query(Message).filter(Message.id == message_id).first()
        assert stored is not None
        assert stored.message_metadata["queue"]["status"] == "cancelled"


def test_mark_message_consumed_handles_no_metadata(
    user_instance: tuple[UUID, UUID],
) -> None:
    # Regression guard: `message_metadata` defaults to Python `None`, and the
    # JSONB column doesn't set `none_as_null=True`, so "no metadata yet" is
    # stored as the JSON scalar `null` rather than SQL NULL. A naive
    # `coalesce(message_metadata, '{}'::jsonb)` does not catch that and
    # `jsonb_set` raises `cannot set path in scalar` on the majority of
    # messages, which never had `queue` metadata stamped in the first place
    # (see `f02e6e4`: only messages sent while the agent is ACTIVE get it).
    _user_id, instance_id = user_instance
    message_id = _make_user_message(instance_id, None)

    with SessionLocal() as db:
        updated = mark_message_consumed(db, message_id)
        assert updated is not None
        assert updated.message_metadata["queue"]["status"] == "consumed"
        db.commit()


def test_mark_message_consumed_returns_none_for_unknown_message() -> None:
    with SessionLocal() as db:
        assert mark_message_consumed(db, uuid4()) is None


# ---------------------------------------------------------------------------
# Endpoint: PATCH /messages/{message_id}/consumed
# ---------------------------------------------------------------------------


async def test_consumed_endpoint_marks_status_and_broadcasts(
    user_instance: tuple[UUID, UUID],
) -> None:
    user_id, instance_id = user_instance
    message_id = _make_user_message(instance_id, {"queue": {"status": "queued"}})

    web = _user_conn(user_id)
    connection_manager.register(web)
    try:
        with SessionLocal() as db:
            response = await mark_message_consumed_endpoint(
                message_id=message_id, user_id=str(user_id), db=db
            )

        assert response == {"success": True, "message_id": str(message_id)}

        bodies = [f["payload"]["body"] for f in _drain(web)]
        update_body = next(b for b in bodies if b.get("t") == "message-update")
        assert update_body["id"] == str(message_id)
        assert update_body["message_metadata"]["queue"]["status"] == "consumed"
    finally:
        connection_manager.unregister(web)

    with SessionLocal() as db:
        stored = db.query(Message).filter(Message.id == message_id).first()
        assert stored is not None
        assert stored.message_metadata["queue"]["status"] == "consumed"


async def test_consumed_endpoint_is_idempotent(
    user_instance: tuple[UUID, UUID],
) -> None:
    user_id, instance_id = user_instance
    message_id = _make_user_message(instance_id, {"queue": {"status": "queued"}})

    with SessionLocal() as db:
        first = await mark_message_consumed_endpoint(
            message_id=message_id, user_id=str(user_id), db=db
        )
    with SessionLocal() as db:
        second = await mark_message_consumed_endpoint(
            message_id=message_id, user_id=str(user_id), db=db
        )

    assert first == second == {"success": True, "message_id": str(message_id)}

    with SessionLocal() as db:
        stored = db.query(Message).filter(Message.id == message_id).first()
        assert stored is not None
        assert stored.message_metadata["queue"]["status"] == "consumed"


async def test_consumed_endpoint_404s_for_another_users_message(
    user_instance: tuple[UUID, UUID],
) -> None:
    _user_id, instance_id = user_instance
    message_id = _make_user_message(instance_id, None)

    from fastapi import HTTPException

    with SessionLocal() as db:
        with pytest.raises(HTTPException) as exc_info:
            await mark_message_consumed_endpoint(
                message_id=message_id, user_id=str(uuid4()), db=db
            )

    assert exc_info.value.status_code == 404
