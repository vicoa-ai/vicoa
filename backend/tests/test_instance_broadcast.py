"""Integration tests: instance writes broadcast instance updates (Phase 4a).

Server-side `agent_instances` write endpoints now commit inside `in_tx` and
emit an `instance-update` / `instance-created` to the user-scoped room so the
web client sees agent changes live (websocket-migration §2.5, §4 Phase 4a).
These hit a real database, so they are marked `integration`.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from servers.api.models import (
    EndSessionRequest,
    RegisterAgentInstanceRequest,
    UpdateAgentInstanceRequest,
)
from servers.api.routers import (
    end_session_endpoint,
    heartbeat_instance,
    register_agent_instance_endpoint,
    update_agent_instance_endpoint,
    update_agent_instance_status_endpoint,
)
from shared.database.enums import AgentStatus
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
        # Broad cleanup: some endpoints (register) create extra instances and
        # user-agents, so delete everything owned by the user in FK order.
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
            db.query(AgentInstance).filter(AgentInstance.user_id == user_id).delete()
            db.query(UserAgent).filter(UserAgent.user_id == user_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()


def _user_conn(user_id: UUID) -> Connection:
    return Connection(
        connection_id=uuid4().hex,
        user_id=str(user_id),
        scope="user-scoped",
        rooms=frozenset({f"user:{user_id}:user-scoped"}),
    )


def test_rename_broadcasts_instance_update(
    user_instance: tuple[UUID, UUID],
) -> None:
    user_id, instance_id = user_instance
    web = _user_conn(user_id)
    connection_manager.register(web)
    try:
        with SessionLocal() as db:
            update_agent_instance_endpoint(
                instance_id=instance_id,
                update_data=UpdateAgentInstanceRequest(name="renamed"),
                user_id=str(user_id),
                db=db,
            )

        frame = web.outbox.get_nowait()
        assert frame["payload"]["entity"] == "agent_instances"
        assert frame["payload"]["entity_id"] == str(instance_id)
        assert frame["payload"]["body"]["t"] == "instance-update"
        assert frame["payload"]["body"]["name"] == "renamed"
    finally:
        connection_manager.unregister(web)


def test_heartbeat_broadcasts_instance_update(
    user_instance: tuple[UUID, UUID],
) -> None:
    user_id, instance_id = user_instance
    web = _user_conn(user_id)
    connection_manager.register(web)
    try:
        with SessionLocal() as db:
            heartbeat_instance(
                agent_instance_id=instance_id, user_id=str(user_id), db=db
            )

        frame = web.outbox.get_nowait()
        assert frame["payload"]["entity_id"] == str(instance_id)
        assert frame["payload"]["body"]["t"] == "instance-update"
    finally:
        connection_manager.unregister(web)


def test_end_session_broadcasts_instance_update(
    user_instance: tuple[UUID, UUID],
) -> None:
    user_id, instance_id = user_instance
    web = _user_conn(user_id)
    connection_manager.register(web)
    try:
        with SessionLocal() as db:
            end_session_endpoint(
                request=EndSessionRequest(agent_instance_id=str(instance_id)),
                user_id=str(user_id),
                db=db,
            )

        frame = web.outbox.get_nowait()
        assert frame["payload"]["entity_id"] == str(instance_id)
        assert frame["payload"]["body"]["t"] == "instance-update"
        assert frame["payload"]["body"]["status"] == "COMPLETED"
    finally:
        connection_manager.unregister(web)


def test_status_update_broadcasts_instance_update(
    user_instance: tuple[UUID, UUID],
) -> None:
    user_id, instance_id = user_instance
    web = _user_conn(user_id)
    connection_manager.register(web)
    try:
        with SessionLocal() as db:
            update_agent_instance_status_endpoint(
                instance_id=instance_id,
                status_data={"status": "AWAITING_INPUT"},
                user_id=str(user_id),
                db=db,
            )

        frame = web.outbox.get_nowait()
        assert frame["payload"]["entity_id"] == str(instance_id)
        assert frame["payload"]["body"]["t"] == "instance-update"
        assert frame["payload"]["body"]["status"] == "AWAITING_INPUT"
    finally:
        connection_manager.unregister(web)


def test_register_broadcasts_instance_created(
    user_instance: tuple[UUID, UUID],
) -> None:
    user_id, _ = user_instance
    new_id = uuid4()
    web = _user_conn(user_id)
    connection_manager.register(web)
    try:
        with SessionLocal() as db:
            register_agent_instance_endpoint(
                request=RegisterAgentInstanceRequest(
                    agent_type="claude", agent_instance_id=str(new_id)
                ),
                user_id=str(user_id),
                db=db,
            )

        frame = web.outbox.get_nowait()
        assert frame["payload"]["entity"] == "agent_instances"
        assert frame["payload"]["entity_id"] == str(new_id)
        assert frame["payload"]["body"]["t"] == "instance-created"
    finally:
        connection_manager.unregister(web)
