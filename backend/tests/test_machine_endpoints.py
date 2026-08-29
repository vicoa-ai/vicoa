"""Integration tests: machine PATCH (rename), DELETE (remove), GET-by-id.

Covers plans/machine-management.md D6/D15 (rename + hard-delete) and the
GET-by-id deep link. Hits a real Postgres, so marked `integration`.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from backend.api.machines import (
    delete_machine_endpoint,
    get_machine_endpoint,
    rename_machine_endpoint,
)
from backend.models import RenameMachineRequest
from shared.database.agent_instances import create_agent_instance
from shared.database.models import (
    AgentInstance,
    Machine,
    MachineSpawnRequest,
    User,
    UserAgent,
)
from shared.database.session import SessionLocal

pytestmark = pytest.mark.integration


@pytest.fixture
def user() -> Iterator[UUID]:
    uid = uuid4()
    with SessionLocal() as db:
        db.add(User(id=uid, email=f"{uid}@test.vicoa", display_name="t"))
        db.commit()
    try:
        yield uid
    finally:
        with SessionLocal() as db:
            db.query(AgentInstance).filter(AgentInstance.user_id == uid).delete()
            db.query(MachineSpawnRequest).filter(
                MachineSpawnRequest.requested_by_user_id == uid
            ).delete()
            db.query(UserAgent).filter(UserAgent.user_id == uid).delete()
            db.query(Machine).filter(Machine.user_id == uid).delete()
            db.query(User).filter(User.id == uid).delete()
            db.commit()


def _user_obj(db, user_id: UUID) -> User:
    return db.query(User).filter(User.id == user_id).one()


def test_delete_machine_removes_row_cascades_and_nulls_instances(
    user: UUID,
) -> None:
    """Hard delete (D6): the row is gone, its spawn_requests cascade away, but
    its sessions survive with machine_id SET NULL (D7) so they degrade to
    "machine removed" rather than being deleted."""
    user_id = user
    machine_id = uuid4()
    instance_id = uuid4()
    spawn_id = uuid4()

    with SessionLocal() as db:
        db.add(Machine(id=machine_id, user_id=user_id, hostname="h"))
        db.commit()
    with SessionLocal() as db:
        create_agent_instance(
            db,
            user_id,
            agent_name="claude",
            instance_id=instance_id,
            machine_id=machine_id,
        )
        db.add(
            MachineSpawnRequest(
                id=spawn_id,
                machine_id=machine_id,
                requested_by_user_id=user_id,
                directory="/code",
            )
        )
        db.commit()

    with SessionLocal() as db:
        result = delete_machine_endpoint(
            machine_id=str(machine_id),
            current_user=_user_obj(db, user_id),
            db=db,
        )
    assert result.status_code == 204

    with SessionLocal() as db:
        assert db.query(Machine).filter(Machine.id == machine_id).first() is None
        assert (
            db.query(MachineSpawnRequest)
            .filter(MachineSpawnRequest.id == spawn_id)
            .first()
            is None
        )
        inst = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        assert inst.machine_id is None


def test_delete_machine_owned_by_another_user_is_404(user: UUID) -> None:
    """Ownership scoping: deleting someone else's machine is a 404, not a
    silent cross-tenant delete."""
    user_id = user
    other_uid = uuid4()
    other_machine_id = uuid4()
    with SessionLocal() as db:
        db.add(User(id=other_uid, email=f"{other_uid}@test.vicoa", display_name="o"))
        db.commit()
    with SessionLocal() as db:
        db.add(Machine(id=other_machine_id, user_id=other_uid, hostname="other"))
        db.commit()

    try:
        with SessionLocal() as db:
            with pytest.raises(HTTPException) as exc:
                delete_machine_endpoint(
                    machine_id=str(other_machine_id),
                    current_user=_user_obj(db, user_id),
                    db=db,
                )
            assert exc.value.status_code == 404
        # The foreign machine is untouched.
        with SessionLocal() as db:
            assert (
                db.query(Machine).filter(Machine.id == other_machine_id).first()
                is not None
            )
    finally:
        with SessionLocal() as db:
            db.query(Machine).filter(Machine.user_id == other_uid).delete()
            db.query(User).filter(User.id == other_uid).delete()
            db.commit()


def test_rename_updates_name_trims_and_returns_summary(user: UUID) -> None:
    """Valid rename (D15): trims, persists display_name, returns the summary."""
    user_id = user
    machine_id = uuid4()
    with SessionLocal() as db:
        db.add(
            Machine(id=machine_id, user_id=user_id, hostname="h", display_name="old")
        )
        db.commit()

    with SessionLocal() as db:
        summary = rename_machine_endpoint(
            machine_id=str(machine_id),
            request=RenameMachineRequest(display_name="  New Name  "),
            current_user=_user_obj(db, user_id),
            db=db,
        )

    assert summary.machine_id == str(machine_id)
    assert summary.display_name == "New Name"
    with SessionLocal() as db:
        row = db.query(Machine).filter(Machine.id == machine_id).one()
        assert row.display_name == "New Name"


@pytest.mark.parametrize("bad_name", ["   ", "x" * 256])
def test_rename_invalid_name_is_400(user: UUID, bad_name: str) -> None:
    """Empty/whitespace and over-255 names are rejected with 400 (D15)."""
    user_id = user
    machine_id = uuid4()
    with SessionLocal() as db:
        db.add(Machine(id=machine_id, user_id=user_id, hostname="h"))
        db.commit()

    with SessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            rename_machine_endpoint(
                machine_id=str(machine_id),
                request=RenameMachineRequest(display_name=bad_name),
                current_user=_user_obj(db, user_id),
                db=db,
            )
        assert exc.value.status_code == 400


def test_rename_foreign_machine_is_404(user: UUID) -> None:
    """Renaming another user's machine is a 404."""
    user_id = user
    other_uid = uuid4()
    other_machine_id = uuid4()
    with SessionLocal() as db:
        db.add(User(id=other_uid, email=f"{other_uid}@test.vicoa", display_name="o"))
        db.commit()
    with SessionLocal() as db:
        db.add(Machine(id=other_machine_id, user_id=other_uid, hostname="other"))
        db.commit()

    try:
        with SessionLocal() as db:
            with pytest.raises(HTTPException) as exc:
                rename_machine_endpoint(
                    machine_id=str(other_machine_id),
                    request=RenameMachineRequest(display_name="hijack"),
                    current_user=_user_obj(db, user_id),
                    db=db,
                )
            assert exc.value.status_code == 404
    finally:
        with SessionLocal() as db:
            db.query(Machine).filter(Machine.user_id == other_uid).delete()
            db.query(User).filter(User.id == other_uid).delete()
            db.commit()


def test_rename_broadcasts_machine_update(user: UUID, monkeypatch) -> None:
    """A successful rename broadcasts machine-update so other connected clients
    re-render the new name without a refresh (D13/D15)."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        "backend.api.machines.post_broadcast",
        lambda uid, payload, rooms: calls.append((uid, payload, rooms)),
    )

    user_id = user
    machine_id = uuid4()
    with SessionLocal() as db:
        db.add(Machine(id=machine_id, user_id=user_id, hostname="h"))
        db.commit()

    with SessionLocal() as db:
        rename_machine_endpoint(
            machine_id=str(machine_id),
            request=RenameMachineRequest(display_name="Renamed"),
            current_user=_user_obj(db, user_id),
            db=db,
        )

    assert calls, "expected a machine-update broadcast"
    _, payload, _ = calls[-1]
    assert payload["body"]["t"] == "machine-update"
    assert payload["body"]["display_name"] == "Renamed"


def test_get_machine_returns_summary(user: UUID) -> None:
    """GET by id returns the machine summary for its owner (deep-link target)."""
    user_id = user
    machine_id = uuid4()
    with SessionLocal() as db:
        db.add(
            Machine(
                id=machine_id,
                user_id=user_id,
                hostname="host-x",
                display_name="My Mac",
            )
        )
        db.commit()

    with SessionLocal() as db:
        summary = get_machine_endpoint(
            machine_id=str(machine_id),
            current_user=_user_obj(db, user_id),
            db=db,
        )
    assert summary.machine_id == str(machine_id)
    assert summary.display_name == "My Mac"
    assert summary.hostname == "host-x"


def test_get_machine_foreign_is_404(user: UUID) -> None:
    """GET on another user's machine is a 404."""
    user_id = user
    other_uid = uuid4()
    other_machine_id = uuid4()
    with SessionLocal() as db:
        db.add(User(id=other_uid, email=f"{other_uid}@test.vicoa", display_name="o"))
        db.commit()
    with SessionLocal() as db:
        db.add(Machine(id=other_machine_id, user_id=other_uid, hostname="other"))
        db.commit()

    try:
        with SessionLocal() as db:
            with pytest.raises(HTTPException) as exc:
                get_machine_endpoint(
                    machine_id=str(other_machine_id),
                    current_user=_user_obj(db, user_id),
                    db=db,
                )
            assert exc.value.status_code == 404
    finally:
        with SessionLocal() as db:
            db.query(Machine).filter(Machine.user_id == other_uid).delete()
            db.query(User).filter(User.id == other_uid).delete()
            db.commit()
