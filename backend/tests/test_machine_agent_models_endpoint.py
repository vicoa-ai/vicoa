"""Integration tests for the machine_agent_models cache end-to-end.

The agent-facing PATCH /agent-instances writes the cache write-on-change from
the wrapper's available_models report; the human-facing
GET /machines/{id}/agent-models reads it back for the new-session picker.
Needs a real database (JSONB), so marked integration.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from backend.api.machines import get_machine_agent_models_endpoint
from servers.api.models import UpdateAgentInstanceRequest
from servers.api.routers import update_agent_instance_endpoint
from shared.database.enums import AgentStatus
from shared.database.models import (
    AgentInstance,
    Machine,
    MachineAgentModels,
    Message,
    User,
    UserAgent,
)
from shared.database.session import SessionLocal

pytestmark = pytest.mark.integration

_CURSOR_MODELS = [
    {"id": "default[]", "label": "Auto"},
    {"id": "composer-2.5[fast=true]", "label": "composer-2.5"},
]


@pytest.fixture
def user_machine_instance() -> Iterator[tuple[UUID, UUID, UUID]]:
    user_id, agent_id, machine_id, instance_id = uuid4(), uuid4(), uuid4(), uuid4()
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.flush()
        db.add(Machine(id=machine_id, user_id=user_id, display_name="M"))
        db.add(UserAgent(id=agent_id, user_id=user_id, name="cursor"))
        db.add(
            AgentInstance(
                id=instance_id,
                user_agent_id=agent_id,
                user_id=user_id,
                machine_id=machine_id,
                status=AgentStatus.ACTIVE,
                name="s",
                session_config={"agent": "cursor"},
            )
        )
        db.commit()
    try:
        yield user_id, machine_id, instance_id
    finally:
        with SessionLocal() as db:
            db.query(MachineAgentModels).filter(
                MachineAgentModels.user_id == user_id
            ).delete()
            db.query(Message).filter(Message.agent_instance_id == instance_id).delete()
            db.query(AgentInstance).filter(AgentInstance.user_id == user_id).delete()
            db.query(UserAgent).filter(UserAgent.user_id == user_id).delete()
            db.query(Machine).filter(Machine.user_id == user_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()


def _patch_models(instance_id: UUID, user_id: UUID, models: list[dict]) -> None:
    request = UpdateAgentInstanceRequest.model_validate(
        {
            "session_config": {
                "agent": "cursor",
                "available_models": models,
                "current_model": models[-1]["id"] if models else None,
            }
        }
    )
    with SessionLocal() as db:
        update_agent_instance_endpoint(
            instance_id=instance_id, update_data=request, user_id=str(user_id), db=db
        )


def test_patch_caches_models_and_read_endpoint_returns_them(
    user_machine_instance: tuple[UUID, UUID, UUID],
) -> None:
    user_id, machine_id, instance_id = user_machine_instance
    _patch_models(instance_id, user_id, _CURSOR_MODELS)

    with SessionLocal() as db:
        row = (
            db.query(MachineAgentModels)
            .filter(
                MachineAgentModels.machine_id == machine_id,
                MachineAgentModels.agent_type == "cursor",
            )
            .one()
        )
        assert row.models == _CURSOR_MODELS

    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).one()
        resp = get_machine_agent_models_endpoint(
            machine_id=str(machine_id), current_user=user, db=db
        )
    assert "cursor" in resp.agent_models
    assert [m.id for m in resp.agent_models["cursor"]] == [
        "default[]",
        "composer-2.5[fast=true]",
    ]


def test_unchanged_models_do_not_rewrite(
    user_machine_instance: tuple[UUID, UUID, UUID],
) -> None:
    """Write-on-change: a second identical report leaves updated_at untouched."""
    user_id, machine_id, instance_id = user_machine_instance
    _patch_models(instance_id, user_id, _CURSOR_MODELS)
    with SessionLocal() as db:
        first = (
            db.query(MachineAgentModels)
            .filter(MachineAgentModels.machine_id == machine_id)
            .one()
        )
        first_updated = first.updated_at

    _patch_models(instance_id, user_id, _CURSOR_MODELS)
    with SessionLocal() as db:
        again = (
            db.query(MachineAgentModels)
            .filter(MachineAgentModels.machine_id == machine_id)
            .one()
        )
        assert again.updated_at == first_updated


def test_patch_without_machine_id_skips_cache(
    user_machine_instance: tuple[UUID, UUID, UUID],
) -> None:
    """An instance with no machine_id can't be keyed -> nothing cached."""
    user_id, _machine_id, instance_id = user_machine_instance
    with SessionLocal() as db:
        db.query(AgentInstance).filter(AgentInstance.id == instance_id).update(
            {"machine_id": None}
        )
        db.commit()

    _patch_models(instance_id, user_id, _CURSOR_MODELS)
    with SessionLocal() as db:
        count = (
            db.query(MachineAgentModels)
            .filter(MachineAgentModels.user_id == user_id)
            .count()
        )
        assert count == 0
