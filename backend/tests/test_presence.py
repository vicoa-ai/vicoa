"""Heartbeat ticks are in-memory touches; the DB lease is renewed in batches.

Unit tests cover the registry itself. The integration tests drive the real
heartbeat endpoints against the dev database and assert the contract that
matters for CPU: a steady-state tick writes nothing, the batched flush writes
once per row, and the flush can never touch a row the ticking user doesn't own.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from servers.api.models import HeartbeatMachineRequest
from servers.api.routers import heartbeat_instance, heartbeat_machine_endpoint
from servers.presence import PresenceRegistry, flush_leases, presence
from shared.database.enums import AgentStatus
from shared.database.models import AgentInstance, AgentType, Machine, User
from shared.database.session import SessionLocal
from shared.websocket.connection_manager import Connection, connection_manager


# ----- unit: registry -----


def test_touch_marks_known_and_dirty() -> None:
    reg = PresenceRegistry()
    iid, uid = uuid4(), uuid4()
    assert not reg.instance_is_known(iid, uid)

    seen = reg.touch_instance(iid, uid)

    assert reg.instance_is_known(iid, uid)
    assert reg.instance_last_seen(iid) == seen
    instances, machines = reg.drain_dirty()
    assert instances == [(iid, uid)]
    assert machines == []
    # Drained: a second drain is empty until the next touch.
    assert reg.drain_dirty() == ([], [])


def test_known_is_per_owner() -> None:
    """A cached ownership never vouches for a different user."""
    reg = PresenceRegistry()
    iid = uuid4()
    reg.touch_instance(iid, uuid4())
    assert not reg.instance_is_known(iid, uuid4())


def test_repeat_touch_coalesces_into_one_dirty_entry() -> None:
    reg = PresenceRegistry()
    iid, uid = uuid4(), uuid4()
    reg.touch_instance(iid, uid)
    reg.touch_instance(iid, uid)
    reg.touch_machine(uuid4(), uid)
    instances, machines = reg.drain_dirty()
    assert len(instances) == 1
    assert len(machines) == 1


def test_requeue_restores_dirty_pairs() -> None:
    reg = PresenceRegistry()
    iid, mid, uid = uuid4(), uuid4(), uuid4()
    reg.touch_instance(iid, uid)
    reg.touch_machine(mid, uid)
    instances, machines = reg.drain_dirty()
    reg.requeue(instances, machines)
    assert reg.drain_dirty() == ([(iid, uid)], [(mid, uid)])


# ----- integration: endpoints + flush -----


@pytest.fixture
def user_instance() -> Iterator[tuple[UUID, UUID]]:
    user_id, agent_id, instance_id = uuid4(), uuid4(), uuid4()
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.flush()
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
    presence.clear()
    try:
        yield user_id, instance_id
    finally:
        presence.clear()
        with SessionLocal() as db:
            db.query(AgentInstance).filter(AgentInstance.user_id == user_id).delete()
            db.query(Machine).filter(Machine.user_id == user_id).delete()
            db.query(AgentType).filter(AgentType.user_id == user_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()


def _heartbeat_column(instance_id: UUID) -> datetime | None:
    with SessionLocal() as db:
        row = db.get(AgentInstance, instance_id)
        assert row is not None
        return row.last_heartbeat_at


def _user_conn(user_id: UUID) -> Connection:
    return Connection(
        connection_id=uuid4().hex,
        user_id=str(user_id),
        scope="user-scoped",
        rooms=frozenset({f"user:{user_id}:user-scoped"}),
    )


@pytest.mark.integration
def test_tick_does_not_write_until_flush(user_instance: tuple[UUID, UUID]) -> None:
    user_id, instance_id = user_instance
    assert _heartbeat_column(instance_id) is None

    with SessionLocal() as db:
        body = heartbeat_instance(
            agent_instance_id=instance_id, user_id=str(user_id), db=db
        )
    assert body["agent_instance_id"] == str(instance_id)
    # The tick was recorded in memory only.
    assert presence.instance_is_known(instance_id, user_id)
    assert _heartbeat_column(instance_id) is None

    with SessionLocal() as db:
        assert flush_leases(db, presence) == (1, 0)
    stamped = _heartbeat_column(instance_id)
    assert stamped is not None
    assert datetime.now(timezone.utc) - stamped.replace(
        tzinfo=timezone.utc
    ) < timedelta(seconds=30)
    # Nothing dirty remains, so the next flush is a no-op.
    with SessionLocal() as db:
        assert flush_leases(db, presence) == (0, 0)


@pytest.mark.integration
def test_tick_rejects_unowned_instance(user_instance: tuple[UUID, UUID]) -> None:
    _, instance_id = user_instance
    stranger = uuid4()
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            heartbeat_instance(
                agent_instance_id=instance_id, user_id=str(stranger), db=db
            )
    assert exc.value.status_code == 404
    assert not presence.instance_is_known(instance_id, stranger)


@pytest.mark.integration
def test_tick_rejects_unknown_instance(user_instance: tuple[UUID, UUID]) -> None:
    user_id, _ = user_instance
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            heartbeat_instance(agent_instance_id=uuid4(), user_id=str(user_id), db=db)
    assert exc.value.status_code == 404


@pytest.mark.integration
def test_flush_is_scoped_by_owner_pair(user_instance: tuple[UUID, UUID]) -> None:
    """A poisoned registry entry (wrong owner) must not update the row."""
    _, instance_id = user_instance
    reg = PresenceRegistry()
    reg.touch_instance(instance_id, uuid4())
    with SessionLocal() as db:
        assert flush_leases(db, reg) == (0, 0)
    assert _heartbeat_column(instance_id) is None


@pytest.mark.integration
def test_tick_broadcasts_only_when_a_dashboard_is_connected(
    user_instance: tuple[UUID, UUID],
) -> None:
    user_id, instance_id = user_instance
    # Nobody listening: no frame, and no row read needed to build one.
    with SessionLocal() as db:
        heartbeat_instance(agent_instance_id=instance_id, user_id=str(user_id), db=db)

    web = _user_conn(user_id)
    connection_manager.register(web)
    try:
        with SessionLocal() as db:
            heartbeat_instance(
                agent_instance_id=instance_id, user_id=str(user_id), db=db
            )
        frame = web.outbox.get_nowait()
        body = frame["payload"]["body"]
        assert body["t"] == "instance-update"
        assert body["id"] == str(instance_id)
        # The wire carries the in-memory tick time even though the column is
        # still unflushed.
        assert body["last_heartbeat_at"] is not None
        assert web.outbox.empty()
    finally:
        connection_manager.unregister(web)
    assert _heartbeat_column(instance_id) is None


@pytest.mark.integration
def test_machine_tick_writes_only_on_metadata_change(
    user_instance: tuple[UUID, UUID],
) -> None:
    user_id, _ = user_instance
    machine_id = uuid4()
    with SessionLocal() as db:
        db.add(Machine(id=machine_id, user_id=user_id, hostname="seed"))
        db.commit()

    def _row() -> Machine:
        with SessionLocal() as db:
            row = db.get(Machine, machine_id)
            assert row is not None
            db.expunge(row)
            return row

    # First tick carries new metadata: merged and written, timestamp stamped.
    with SessionLocal() as db:
        heartbeat_machine_endpoint(
            machine_id=str(machine_id),
            request=HeartbeatMachineRequest(metadata={"last_pid": 42}),
            user_id=str(user_id),
            db=db,
        )
    first = _row()
    assert first.machine_metadata == {"last_pid": 42}
    assert first.last_heartbeat_at is not None

    # Same metadata again: no write at all — the column does not move.
    with SessionLocal() as db:
        resp = heartbeat_machine_endpoint(
            machine_id=str(machine_id),
            request=HeartbeatMachineRequest(metadata={"last_pid": 42}),
            user_id=str(user_id),
            db=db,
        )
    assert resp.machine_id == str(machine_id)
    assert _row().last_heartbeat_at == first.last_heartbeat_at

    # The lease flush is what advances it.
    with SessionLocal() as db:
        assert flush_leases(db, presence) == (0, 1)
    assert _row().last_heartbeat_at != first.last_heartbeat_at


@pytest.mark.integration
def test_machine_tick_rejects_unowned(user_instance: tuple[UUID, UUID]) -> None:
    user_id, _ = user_instance
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            heartbeat_machine_endpoint(
                machine_id=str(uuid4()),
                request=HeartbeatMachineRequest(),
                user_id=str(user_id),
                db=db,
            )
    assert exc.value.status_code == 404
