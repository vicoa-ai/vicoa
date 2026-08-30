"""Integration tests: agent_instances.machine_id links a session to its machine.

Covers plans/machine-management.md D7/D8 — a session created on a machine
records that machine's id, validated/ownership-scoped at registration, and
SET NULL when the machine is removed. Hits a real Postgres, so marked
`integration`.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from servers.api.models import RegisterAgentInstanceRequest
from servers.api.routers import register_agent_instance_endpoint
from shared.database.agent_instances import create_agent_instance
from shared.database.models import AgentInstance, Machine, User, UserAgent
from shared.database.session import SessionLocal

pytestmark = pytest.mark.integration


@pytest.fixture
def user_and_machine() -> Iterator[tuple[UUID, UUID]]:
    """A user owning one registered machine. Cleans up instances it spawns."""
    uid = uuid4()
    machine_id = uuid4()
    with SessionLocal() as db:
        db.add(User(id=uid, email=f"{uid}@test.vicoa", display_name="t"))
        db.commit()
    with SessionLocal() as db:
        db.add(Machine(id=machine_id, user_id=uid, hostname="host-1"))
        db.commit()
    try:
        yield uid, machine_id
    finally:
        with SessionLocal() as db:
            db.query(AgentInstance).filter(AgentInstance.user_id == uid).delete()
            db.query(UserAgent).filter(UserAgent.user_id == uid).delete()
            db.query(Machine).filter(Machine.user_id == uid).delete()
            db.query(User).filter(User.id == uid).delete()
            db.commit()


def test_create_agent_instance_persists_machine_id(
    user_and_machine: tuple[UUID, UUID],
) -> None:
    """Tracer bullet: create_agent_instance stamps the machine_id FK and it
    round-trips through the DB (proves the column + migration apply)."""
    user_id, machine_id = user_and_machine
    instance_id = uuid4()

    with SessionLocal() as db:
        create_agent_instance(
            db,
            user_id,
            agent_name="claude",
            instance_id=instance_id,
            machine_id=machine_id,
        )
        db.commit()

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        assert row.machine_id == machine_id


def test_create_agent_instance_without_machine_id_leaves_null(
    user_and_machine: tuple[UUID, UUID],
) -> None:
    """The machine link is optional — a standalone wrapper (no daemon) creates
    a session with no machine_id rather than failing."""
    user_id, _ = user_and_machine
    instance_id = uuid4()

    with SessionLocal() as db:
        create_agent_instance(db, user_id, agent_name="claude", instance_id=instance_id)
        db.commit()

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        assert row.machine_id is None


def test_registration_stamps_valid_owned_machine_id(
    user_and_machine: tuple[UUID, UUID],
) -> None:
    """A wrapper that reports the machine it runs on (D8) gets that machine
    linked to the new instance."""
    user_id, machine_id = user_and_machine
    instance_id = uuid4()

    with SessionLocal() as db:
        register_agent_instance_endpoint(
            request=RegisterAgentInstanceRequest(
                agent_type="claude",
                agent_instance_id=str(instance_id),
                machine_id=str(machine_id),
            ),
            user_id=str(user_id),
            db=db,
        )

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        assert row.machine_id == machine_id


def test_registration_nulls_machine_id_owned_by_another_user(
    user_and_machine: tuple[UUID, UUID],
) -> None:
    """Ownership scoping (D8): a machine_id belonging to a different user is
    silently dropped to null — never raises, never links across tenants."""
    user_id, _ = user_and_machine
    other_uid = uuid4()
    other_machine_id = uuid4()
    with SessionLocal() as db:
        db.add(User(id=other_uid, email=f"{other_uid}@test.vicoa", display_name="o"))
        db.commit()
    with SessionLocal() as db:
        db.add(Machine(id=other_machine_id, user_id=other_uid, hostname="other"))
        db.commit()

    instance_id = uuid4()
    try:
        with SessionLocal() as db:
            register_agent_instance_endpoint(
                request=RegisterAgentInstanceRequest(
                    agent_type="claude",
                    agent_instance_id=str(instance_id),
                    machine_id=str(other_machine_id),
                ),
                user_id=str(user_id),
                db=db,
            )

        with SessionLocal() as db:
            row = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
            assert row.machine_id is None
    finally:
        with SessionLocal() as db:
            db.query(Machine).filter(Machine.user_id == other_uid).delete()
            db.query(User).filter(User.id == other_uid).delete()
            db.commit()


def test_registration_nulls_unknown_machine_id(
    user_and_machine: tuple[UUID, UUID],
) -> None:
    """A stale machine_id (machine since removed) is dropped to null and the
    session is still created."""
    user_id, _ = user_and_machine
    instance_id = uuid4()

    with SessionLocal() as db:
        register_agent_instance_endpoint(
            request=RegisterAgentInstanceRequest(
                agent_type="claude",
                agent_instance_id=str(instance_id),
                machine_id=str(uuid4()),
            ),
            user_id=str(user_id),
            db=db,
        )

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        assert row.machine_id is None


def test_registration_response_exposes_machine_id(
    user_and_machine: tuple[UUID, UUID],
) -> None:
    """The instance response surfaces machine_id so the app can render the
    "Machine" row on the session info sheet (D14) without a second fetch."""
    user_id, machine_id = user_and_machine
    instance_id = uuid4()

    with SessionLocal() as db:
        response = register_agent_instance_endpoint(
            request=RegisterAgentInstanceRequest(
                agent_type="claude",
                agent_instance_id=str(instance_id),
                machine_id=str(machine_id),
            ),
            user_id=str(user_id),
            db=db,
        )

    assert response.machine_id == str(machine_id)


def test_app_facing_detail_exposes_machine_id(
    user_and_machine: tuple[UUID, UUID],
) -> None:
    """The app-facing GET /agent-instances/{id} detail exposes machine_id so the
    session info sheet can render the "Machine" row + deep link (D14)."""
    from backend.db.queries import get_agent_instance_detail

    user_id, machine_id = user_and_machine
    instance_id = uuid4()
    with SessionLocal() as db:
        create_agent_instance(
            db,
            user_id,
            agent_name="claude",
            instance_id=instance_id,
            machine_id=machine_id,
        )
        db.commit()

    with SessionLocal() as db:
        detail = get_agent_instance_detail(db, instance_id, user_id, message_limit=0)

    assert detail is not None
    assert detail.machine_id == str(machine_id)


def test_app_facing_list_exposes_machine_id(
    user_and_machine: tuple[UUID, UUID],
) -> None:
    """The app-facing instance list also exposes machine_id so the session list
    / machine cache can resolve a session's machine without per-row fetches."""
    from backend.db.queries import get_all_agent_instances

    user_id, machine_id = user_and_machine
    instance_id = uuid4()
    with SessionLocal() as db:
        create_agent_instance(
            db,
            user_id,
            agent_name="claude",
            instance_id=instance_id,
            machine_id=machine_id,
        )
        db.commit()

    with SessionLocal() as db:
        items, _ = get_all_agent_instances(db, user_id, limit=10, offset=0)

    matching = [it for it in items if it.id == str(instance_id)]
    assert matching, "expected the new instance to appear in the list"
    assert matching[0].machine_id == str(machine_id)


def test_legacy_spawn_request_stamps_machine_id(
    user_and_machine: tuple[UUID, UUID],
) -> None:
    """The legacy HTTP spawn path pre-allocates the instance server-side, so it
    must stamp machine_id itself (the wrapper's self-register only activates the
    existing row). Plan §3.2."""
    from backend.api.machines import create_spawn_request_endpoint
    from backend.models import SpawnSessionRequest

    user_id, machine_id = user_and_machine
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).one()
        response = create_spawn_request_endpoint(
            machine_id=str(machine_id),
            request=SpawnSessionRequest(directory="/code", agent="claude", prompt="Hi"),
            current_user=user,
            db=db,
        )

    with SessionLocal() as db:
        inst = (
            db.query(AgentInstance)
            .filter(AgentInstance.id == UUID(response.agent_instance_id))
            .one()
        )
        assert inst.machine_id == machine_id
