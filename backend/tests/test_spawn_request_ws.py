"""Integration test for spawn-request delivery over WebSocket (Phase 2).

`POST /machines/{id}/spawn-requests` now emits a `spawn-request` update to the
machine room via in_tx + after_commit (websocket-migration §4 Phase 2). This
hits a real database, so it is marked `integration` and runs in CI.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from shared.database.models import (
    AgentInstance,
    Machine,
    MachineSpawnRequest,
    User,
    UserAgent,
)
from shared.database.session import SessionLocal
from shared.websocket.connection_manager import Connection, connection_manager
from servers.api.models import SpawnSessionRequest
from servers.api.routers import create_spawn_request_endpoint

pytestmark = pytest.mark.integration


@pytest.fixture
def user_and_machine() -> Iterator[tuple[UUID, UUID]]:
    user_id, machine_id = uuid4(), uuid4()
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        # Machine has no relationship() to User, so SQLAlchemy's unit of work
        # does not order the User insert first — flush the parent to pin it.
        db.flush()
        db.add(Machine(id=machine_id, user_id=user_id))
        db.commit()
    try:
        yield user_id, machine_id
    finally:
        # The spawn endpoint also creates a UserAgent, AgentInstance, and
        # MachineSpawnRequest; delete child rows before the User in FK order
        # (these FKs are not all ON DELETE CASCADE).
        with SessionLocal() as db:
            db.query(MachineSpawnRequest).filter(
                MachineSpawnRequest.requested_by_user_id == user_id
            ).delete()
            db.query(AgentInstance).filter(AgentInstance.user_id == user_id).delete()
            db.query(Machine).filter(Machine.user_id == user_id).delete()
            db.query(UserAgent).filter(UserAgent.user_id == user_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()


def test_spawn_request_is_broadcast_to_the_machine_room(
    user_and_machine: tuple[UUID, UUID],
) -> None:
    user_id, machine_id = user_and_machine
    daemon = Connection(
        connection_id=uuid4().hex,
        user_id=str(user_id),
        scope="machine-scoped",
        rooms=frozenset({f"user:{user_id}:machine:{machine_id}"}),
    )
    connection_manager.register(daemon)
    try:
        with SessionLocal() as db:
            response = create_spawn_request_endpoint(
                machine_id=str(machine_id),
                request=SpawnSessionRequest(directory="/code", prompt="hi"),
                user_id=str(user_id),
                db=db,
            )

        frame = daemon.outbox.get_nowait()
        assert frame["type"] == "update"
        assert frame["payload"]["entity"] == "machine_spawn_requests"
        assert frame["payload"]["entity_id"] == response.request_id
        assert frame["payload"]["body"]["t"] == "spawn-request"
        assert frame["payload"]["body"]["directory"] == "/code"
    finally:
        connection_manager.unregister(daemon)
