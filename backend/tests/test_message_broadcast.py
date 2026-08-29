"""Integration tests: server message/input writes broadcast over WS (Phase 4a).

Agent messages and CLI-user messages emit a `new-message` update, and
request-user-input emits an `instance-update` (status -> AWAITING_INPUT), to
the user-scoped room (websocket-migration §2.5, §4 Phase 4a).
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi import BackgroundTasks

from servers.api.models import CreateMessageRequest, CreateUserMessageRequest
from servers.api.routers import (
    create_agent_message_endpoint,
    create_user_message_endpoint,
    request_user_input_endpoint,
)
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


def _user_conn(user_id: UUID) -> Connection:
    return Connection(
        connection_id=uuid4().hex,
        user_id=str(user_id),
        scope="user-scoped",
        rooms=frozenset({f"user:{user_id}:user-scoped"}),
    )


def _session_conn(user_id: UUID, instance_id: UUID) -> Connection:
    return Connection(
        connection_id=uuid4().hex,
        user_id=str(user_id),
        scope="session-scoped",
        rooms=frozenset({f"user:{user_id}:session:{instance_id}"}),
    )


def _drain(conn: Connection) -> list[dict]:
    frames: list[dict] = []
    while True:
        try:
            frames.append(conn.outbox.get_nowait())
        except Exception:  # noqa: BLE001 - QueueEmpty ends the drain
            break
    return frames


async def test_agent_message_broadcasts_new_message(
    user_instance: tuple[UUID, UUID],
) -> None:
    user_id, instance_id = user_instance
    web = _user_conn(user_id)
    connection_manager.register(web)
    try:
        with SessionLocal() as db:
            await create_agent_message_endpoint(
                request=CreateMessageRequest(
                    agent_instance_id=str(instance_id),
                    content="agent reply",
                    agent_type="claude",
                ),
                user_id=str(user_id),
                db=db,
            )

        bodies = [f["payload"]["body"] for f in _drain(web)]
        new_message = next(b for b in bodies if b.get("t") == "new-message")
        assert new_message["content"] == "agent reply"
    finally:
        connection_manager.unregister(web)


async def test_agent_message_skips_session_room(
    user_instance: tuple[UUID, UUID],
) -> None:
    # The CLI wrapper sits in the session-scoped room and *produces* the
    # agent side of the conversation. Re-broadcasting agent messages into
    # that room would be received by `session_ws_client` as a fresh
    # `new-message` body and injected back into Claude's PTY — the bug
    # that surfaced as "normal vicoa reads the agent message into the
    # chat" after Phase 4a. Lock the user-scoped-only routing.
    user_id, instance_id = user_instance
    wrapper = _session_conn(user_id, instance_id)
    connection_manager.register(wrapper)
    try:
        with SessionLocal() as db:
            await create_agent_message_endpoint(
                request=CreateMessageRequest(
                    agent_instance_id=str(instance_id),
                    content="agent reply",
                    agent_type="claude",
                ),
                user_id=str(user_id),
                db=db,
            )

        bodies = [f["payload"]["body"] for f in _drain(wrapper)]
        assert not any(b.get("t") == "new-message" for b in bodies)
    finally:
        connection_manager.unregister(wrapper)


def test_server_user_message_reaches_session_room(
    user_instance: tuple[UUID, UUID],
) -> None:
    # Counterpart to the agent-message routing: user messages MUST still
    # reach the wrapper's session room, since that is how the wrapper learns
    # to forward the user's reply into Claude's PTY. A blanket
    # "agent messages skip session room" fix that also dropped user
    # messages would silently break inbound web/app replies.
    user_id, instance_id = user_instance
    wrapper = _session_conn(user_id, instance_id)
    connection_manager.register(wrapper)
    try:
        with SessionLocal() as db:
            create_user_message_endpoint(
                request=CreateUserMessageRequest(
                    agent_instance_id=str(instance_id), content="hello from web"
                ),
                background_tasks=BackgroundTasks(),
                user_id=str(user_id),
                db=db,
            )

        bodies = [f["payload"]["body"] for f in _drain(wrapper)]
        new_message = next(b for b in bodies if b.get("t") == "new-message")
        assert new_message["content"] == "hello from web"
        assert new_message["sender_type"] == "USER"
    finally:
        connection_manager.unregister(wrapper)


def test_server_user_message_broadcasts_new_message(
    user_instance: tuple[UUID, UUID],
) -> None:
    user_id, instance_id = user_instance
    web = _user_conn(user_id)
    connection_manager.register(web)
    try:
        with SessionLocal() as db:
            create_user_message_endpoint(
                request=CreateUserMessageRequest(
                    agent_instance_id=str(instance_id), content="cli user msg"
                ),
                background_tasks=BackgroundTasks(),
                user_id=str(user_id),
                db=db,
            )

        bodies = [f["payload"]["body"] for f in _drain(web)]
        new_message = next(b for b in bodies if b.get("t") == "new-message")
        assert new_message["content"] == "cli user msg"
    finally:
        connection_manager.unregister(web)


async def test_request_user_input_broadcasts_instance_update(
    user_instance: tuple[UUID, UUID],
) -> None:
    user_id, instance_id = user_instance
    message_id = uuid4()
    with SessionLocal() as db:
        db.add(
            Message(
                id=message_id,
                agent_instance_id=instance_id,
                sender_type=SenderType.AGENT,
                content="a question",
                requires_user_input=False,
            )
        )
        db.commit()

    web = _user_conn(user_id)
    connection_manager.register(web)
    try:
        with SessionLocal() as db:
            await request_user_input_endpoint(
                message_id=message_id, user_id=str(user_id), db=db
            )

        bodies = [f["payload"]["body"] for f in _drain(web)]
        instance_update = next(b for b in bodies if b.get("t") == "instance-update")
        assert instance_update["status"] == "AWAITING_INPUT"
    finally:
        connection_manager.unregister(web)
