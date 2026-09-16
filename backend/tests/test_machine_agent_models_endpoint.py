"""Integration tests for the machine_agent_models cache end-to-end.

The agent-facing PATCH /agent-instances writes the cache write-on-change from
the wrapper's available_models report; the human-facing
GET /machines/{id}/agent-models reads it back for the new-session picker.
Needs a real database (JSONB), so marked integration.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from backend.api.machines import get_machine_agent_models_endpoint
from servers.api.models import PutMachineAgentModelsRequest, UpdateAgentInstanceRequest
from servers.api.routers import (
    put_machine_agent_models_endpoint,
    update_agent_instance_endpoint,
)
from shared.database.enums import AgentStatus
from shared.database.models import (
    AgentInstance,
    Machine,
    MachineAgentModels,
    Message,
    User,
    AgentType,
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
        db.add(AgentType(id=agent_id, user_id=user_id, name="cursor"))
        db.add(
            AgentInstance(
                id=instance_id,
                agent_type_id=agent_id,
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
            db.query(AgentType).filter(AgentType.user_id == user_id).delete()
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


# --- probe-sourced PUT + modes (agent-integration-followups §2b) ------------

_QWEN_MODELS = [{"id": "qwen3-coder", "label": "Qwen3 Coder"}]
_QWEN_MODES = [{"id": "default", "label": "Default"}, {"id": "plan", "label": "Plan"}]


def _put(machine_id: UUID, user_id: UUID, agent: str, body: dict) -> bool:
    request = PutMachineAgentModelsRequest.model_validate(body)
    with SessionLocal() as db:
        resp = put_machine_agent_models_endpoint(
            machine_id=str(machine_id),
            agent_type=agent,
            request=request,
            user_id=str(user_id),
            db=db,
        )
    return resp.updated


def _read(machine_id: UUID, user_id: UUID):
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).one()
        return get_machine_agent_models_endpoint(
            machine_id=str(machine_id), current_user=user, db=db
        )


def test_put_caches_probe_models_and_modes_for_an_agent_that_never_ran(
    user_machine_instance: tuple[UUID, UUID, UUID],
) -> None:
    user_id, machine_id, _instance_id = user_machine_instance
    assert _put(
        machine_id, user_id, "Qwen", {"models": _QWEN_MODELS, "modes": _QWEN_MODES}
    )
    # Same content again: write-on-change says no.
    assert not _put(
        machine_id, user_id, "qwen", {"models": _QWEN_MODELS, "modes": _QWEN_MODES}
    )

    resp = _read(machine_id, user_id)
    assert [m.id for m in resp.agent_models["qwen"]] == ["qwen3-coder"]
    assert [(m.id, m.label) for m in resp.agent_modes["qwen"]] == [
        ("default", "Default"),
        ("plan", "Plan"),
    ]


def test_session_patch_persists_available_modes_and_models_only_keeps_them(
    user_machine_instance: tuple[UUID, UUID, UUID],
) -> None:
    user_id, machine_id, instance_id = user_machine_instance
    with SessionLocal() as db:
        update_agent_instance_endpoint(
            instance_id=instance_id,
            update_data=UpdateAgentInstanceRequest.model_validate(
                {
                    "session_config": {
                        "agent": "cursor",
                        "available_models": _CURSOR_MODELS,
                        "available_modes": [
                            {"id": "agent", "label": "Agent"},
                            {"id": "plan", "label": "Plan"},
                        ],
                        "current_mode": "plan",
                    }
                }
            ),
            user_id=str(user_id),
            db=db,
        )
    resp = _read(machine_id, user_id)
    # The session's current mode leads the cached list (= the picker default).
    assert [m.id for m in resp.agent_modes["cursor"]] == ["plan", "agent"]

    # A later models-only report (older wrapper) must not erase the modes.
    _patch_models(
        instance_id, user_id, _CURSOR_MODELS + [{"id": "gpt-5.4", "label": "gpt-5.4"}]
    )
    resp = _read(machine_id, user_id)
    assert [m.id for m in resp.agent_models["cursor"]][-1] == "gpt-5.4"
    assert [m.id for m in resp.agent_modes["cursor"]] == ["plan", "agent"]


def test_put_is_user_scoped_and_validates(
    user_machine_instance: tuple[UUID, UUID, UUID],
) -> None:
    user_id, machine_id, _ = user_machine_instance
    other_user = uuid4()
    with SessionLocal() as db:
        db.add(User(id=other_user, email=f"{other_user}@test.vicoa", display_name="o"))
        db.commit()
    try:
        with pytest.raises(HTTPException) as exc:
            _put(machine_id, other_user, "qwen", {"models": _QWEN_MODELS})
        assert exc.value.status_code == 404
        with pytest.raises(HTTPException) as exc:
            _put(machine_id, user_id, "x" * 65, {"models": _QWEN_MODELS})
        assert exc.value.status_code == 400
        with pytest.raises(ValueError):  # pydantic: models must be non-empty
            PutMachineAgentModelsRequest.model_validate({"models": []})
        assert _read(machine_id, user_id).agent_models == {}
    finally:
        with SessionLocal() as db:
            db.query(User).filter(User.id == other_user).delete()
            db.commit()
