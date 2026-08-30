"""Integration tests: machine writes broadcast `machine-update` (Phase 4a).

`POST /machines/register`, `/heartbeat`, and `PATCH /recent-directories` now
commit inside `in_tx` and emit a `machine-update` to the user-scoped room so
the web client sees machine changes live (websocket-migration §2.5, §4
Phase 4a). These hit a real database, so they are marked `integration`.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from servers.api.models import (
    HeartbeatMachineRequest,
    RegisterMachineRequest,
    UpdateMachineRecentDirectoryRequest,
)
from servers.api.routers import (
    heartbeat_machine_endpoint,
    register_machine_endpoint,
    update_machine_recent_directories_endpoint,
)
from shared.database.models import Machine, User
from shared.database.session import SessionLocal
from shared.websocket.connection_manager import Connection, connection_manager

pytestmark = pytest.mark.integration


@pytest.fixture
def web_user() -> Iterator[UUID]:
    user_id = uuid4()
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.commit()
    try:
        yield user_id
    finally:
        with SessionLocal() as db:
            db.query(Machine).filter(Machine.user_id == user_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()


def _user_conn(user_id: UUID) -> Connection:
    return Connection(
        connection_id=uuid4().hex,
        user_id=str(user_id),
        scope="user-scoped",
        rooms=frozenset({f"user:{user_id}:user-scoped"}),
    )


def test_machine_register_broadcasts_machine_update(web_user: UUID) -> None:
    user_id = web_user
    web = _user_conn(user_id)
    connection_manager.register(web)
    try:
        with SessionLocal() as db:
            register_machine_endpoint(
                request=RegisterMachineRequest(hostname="host-1"),
                user_id=str(user_id),
                db=db,
            )

        frame = web.outbox.get_nowait()
        assert frame["type"] == "update"
        assert frame["payload"]["entity"] == "machines"
        assert frame["payload"]["body"]["t"] == "machine-update"
        assert frame["payload"]["body"]["hostname"] == "host-1"
    finally:
        connection_manager.unregister(web)


def _insert_machine(user_id: UUID) -> UUID:
    machine_id = uuid4()
    with SessionLocal() as db:
        db.add(Machine(id=machine_id, user_id=user_id, hostname="seed"))
        db.commit()
    return machine_id


def test_machine_heartbeat_broadcasts_machine_update(web_user: UUID) -> None:
    user_id = web_user
    machine_id = _insert_machine(user_id)
    web = _user_conn(user_id)
    connection_manager.register(web)
    try:
        with SessionLocal() as db:
            heartbeat_machine_endpoint(
                machine_id=str(machine_id),
                request=HeartbeatMachineRequest(),
                user_id=str(user_id),
                db=db,
            )

        frame = web.outbox.get_nowait()
        assert frame["payload"]["entity"] == "machines"
        assert frame["payload"]["entity_id"] == str(machine_id)
        assert frame["payload"]["body"]["t"] == "machine-update"
    finally:
        connection_manager.unregister(web)


def test_machine_recent_directories_broadcasts_machine_update(
    web_user: UUID,
) -> None:
    user_id = web_user
    machine_id = _insert_machine(user_id)
    web = _user_conn(user_id)
    connection_manager.register(web)
    try:
        with SessionLocal() as db:
            update_machine_recent_directories_endpoint(
                machine_id=str(machine_id),
                request=UpdateMachineRecentDirectoryRequest(cwd="/code"),
                user_id=str(user_id),
                db=db,
            )

        frame = web.outbox.get_nowait()
        assert frame["payload"]["body"]["t"] == "machine-update"
    finally:
        connection_manager.unregister(web)
