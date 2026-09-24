"""A spawn request's pre-staged session must carry its machine link.

`agent_instances.machine_id` is what every machine-scoped feature routes on —
terminal, files/git panel, git branch badge, file search — and the first tier
of the project matcher. Nothing downstream can fill it in later: registration's
idempotent "row exists" branch and the PATCH endpoint both leave it alone, and
a resume skips registration entirely. So a row staged without it is
machine-less for life, and its session view is dead on arrival.

That is exactly what the agent-facing route (`vicoa session start`,
`vicoa_start_session`) did while it was a drifted copy of the human-facing one.
Both routes now go through `shared.database.spawn_requests`; these tests pin
the link on each of them, plus the registration backfill that covers a row
staged by an older client.

Hits a real database, so it is marked `integration` and runs in CI.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from backend.api.machines import (
    create_spawn_request_endpoint as create_spawn_request_for_user,
)
from backend.models import SpawnSessionRequest as UserSpawnSessionRequest
from servers.api.models import (
    RegisterAgentInstanceRequest,
    SpawnSessionRequest as AgentSpawnSessionRequest,
)
from servers.api.routers import (
    create_spawn_request_endpoint as create_spawn_request_for_agent,
    register_agent_instance_endpoint,
)
from shared.database.agent_instances import create_agent_instance
from shared.database.enums import AgentStatus
from shared.database.models import (
    AgentInstance,
    AgentType,
    Machine,
    MachineSpawnRequest,
    User,
)
from shared.database.session import SessionLocal

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
        # Delete child rows before the User in FK order (these FKs are not all
        # ON DELETE CASCADE).
        with SessionLocal() as db:
            db.query(MachineSpawnRequest).filter(
                MachineSpawnRequest.requested_by_user_id == user_id
            ).delete()
            db.query(AgentInstance).filter(AgentInstance.user_id == user_id).delete()
            db.query(Machine).filter(Machine.user_id == user_id).delete()
            db.query(AgentType).filter(AgentType.user_id == user_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()


def _machine_id_of(instance_id: str) -> UUID | None:
    with SessionLocal() as db:
        instance = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        return instance.machine_id


def test_agent_facing_spawn_links_the_session_to_the_machine(
    user_and_machine: tuple[UUID, UUID],
) -> None:
    """`vicoa session start` / `vicoa_start_session` — the route that drifted."""
    user_id, machine_id = user_and_machine

    with SessionLocal() as db:
        response = create_spawn_request_for_agent(
            machine_id=str(machine_id),
            request=AgentSpawnSessionRequest(directory="/code", prompt="hi"),
            user_id=str(user_id),
            db=db,
        )

    assert _machine_id_of(response.agent_instance_id) == machine_id


def test_user_facing_spawn_links_the_session_to_the_machine(
    user_and_machine: tuple[UUID, UUID],
) -> None:
    """The dashboard/mobile twin, pinned so the pair can't drift the other way."""
    user_id, machine_id = user_and_machine

    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).one()
        response = create_spawn_request_for_user(
            machine_id=str(machine_id),
            request=UserSpawnSessionRequest(directory="/code", prompt="hi"),
            current_user=user,
            db=db,
        )

    assert _machine_id_of(response.agent_instance_id) == machine_id


def test_registration_backfills_a_missing_machine_link(
    user_and_machine: tuple[UUID, UUID],
) -> None:
    """A row staged without a machine gets one from the wrapper's own report.

    Registration is the last point at which anything can repair the link, so it
    covers rows staged by a client too old to send one.
    """
    user_id, machine_id = user_and_machine

    with SessionLocal() as db:
        instance = create_agent_instance(
            db,
            user_id,
            agent_name="claude",
            instance_id=uuid4(),
            instance_metadata={"spawn_starting": True},
            machine_id=None,
            status=AgentStatus.STARTING,
        )
        instance_id = str(instance.id)
        db.commit()

    with SessionLocal() as db:
        register_agent_instance_endpoint(
            request=RegisterAgentInstanceRequest(
                agent_type="claude",
                agent_instance_id=instance_id,
                machine_id=str(machine_id),
            ),
            user_id=str(user_id),
            db=db,
        )

    assert _machine_id_of(instance_id) == machine_id


def test_registration_keeps_the_staged_machine_link(
    user_and_machine: tuple[UUID, UUID],
) -> None:
    """The backfill only ever fills a NULL — the staged machine wins."""
    user_id, machine_id = user_and_machine
    other_machine_id = uuid4()

    with SessionLocal() as db:
        db.add(Machine(id=other_machine_id, user_id=user_id))
        instance = create_agent_instance(
            db,
            user_id,
            agent_name="claude",
            instance_id=uuid4(),
            instance_metadata={"spawn_starting": True},
            machine_id=machine_id,
            status=AgentStatus.STARTING,
        )
        instance_id = str(instance.id)
        db.commit()

    with SessionLocal() as db:
        register_agent_instance_endpoint(
            request=RegisterAgentInstanceRequest(
                agent_type="claude",
                agent_instance_id=instance_id,
                machine_id=str(other_machine_id),
            ),
            user_id=str(user_id),
            db=db,
        )

    assert _machine_id_of(instance_id) == machine_id
