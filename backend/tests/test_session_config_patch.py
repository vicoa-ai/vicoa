"""Integration tests for the PATCH /agent-instances/{id} session_config path.

Extending the existing rename endpoint (UpdateAgentInstanceRequest) with
optional `session_config` so the Claude TUI wrapper's JSONLMonitor can
patch the row whenever it observes a model/permission_mode change in the
Claude jsonl. Plan: TUI follow-up, plans/session-config-storage.md §3.3
(Post-init PATCH path).

Partial-update semantics: only fields the request explicitly carries
overwrite the row. Other session_config keys are preserved.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from servers.api.models import UpdateAgentInstanceRequest
from servers.api.routers import update_agent_instance_endpoint
from shared.database.enums import AgentStatus
from shared.database.models import AgentInstance, Message, User, UserAgent
from shared.database.session import SessionLocal

pytestmark = pytest.mark.integration


@pytest.fixture
def user_and_instance() -> Iterator[tuple[UUID, UUID]]:
    user_id, agent_id, instance_id = uuid4(), uuid4(), uuid4()
    initial = {
        "agent": "claude",
        "model": "claude-sonnet-4-6",
        "thinking_effort": "low",
        "permission_mode": "default",
    }
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.flush()
        db.add(UserAgent(id=agent_id, user_id=user_id, name="claude"))
        db.add(
            AgentInstance(
                id=instance_id,
                user_agent_id=agent_id,
                user_id=user_id,
                status=AgentStatus.ACTIVE,
                name="orig",
                session_config=initial,
            )
        )
        db.commit()
    try:
        yield user_id, instance_id
    finally:
        with SessionLocal() as db:
            db.query(Message).filter(Message.agent_instance_id == instance_id).delete()
            db.query(AgentInstance).filter(AgentInstance.user_id == user_id).delete()
            db.query(UserAgent).filter(UserAgent.user_id == user_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()


def test_patch_session_config_merges_into_existing(
    user_and_instance: tuple[UUID, UUID],
) -> None:
    """A PATCH carrying only `model` overwrites just that key; other keys on
    the existing session_config (thinking_effort, permission_mode) survive.
    This is the JSONLMonitor's primary call: 'I observed a new model'."""
    user_id, instance_id = user_and_instance
    request = UpdateAgentInstanceRequest.model_validate(
        {"session_config": {"model": "claude-opus-4-7"}}
    )
    with SessionLocal() as db:
        update_agent_instance_endpoint(
            instance_id=instance_id,
            update_data=request,
            user_id=str(user_id),
            db=db,
        )

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        assert row.session_config == {
            "agent": "claude",
            "model": "claude-opus-4-7",
            "thinking_effort": "low",
            "permission_mode": "default",
        }
        # Rename payload was absent, so name is untouched.
        assert row.name == "orig"


def test_patch_name_only_leaves_session_config_intact(
    user_and_instance: tuple[UUID, UUID],
) -> None:
    """The original rename use case still works — session_config absent from
    the PATCH preserves the row's existing value (no accidental erase)."""
    user_id, instance_id = user_and_instance
    request = UpdateAgentInstanceRequest.model_validate({"name": "renamed"})
    with SessionLocal() as db:
        update_agent_instance_endpoint(
            instance_id=instance_id,
            update_data=request,
            user_id=str(user_id),
            db=db,
        )

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        assert row.name == "renamed"
        assert row.session_config["model"] == "claude-sonnet-4-6"
        assert row.session_config["permission_mode"] == "default"


def test_patch_session_config_on_null_column_initializes(
    user_and_instance: tuple[UUID, UUID],
) -> None:
    """Legacy row with session_config=null: a PATCH initializes the column
    rather than skipping. The merge starts from {} when the row is null."""
    user_id, instance_id = user_and_instance
    with SessionLocal() as db:
        db.query(AgentInstance).filter(AgentInstance.id == instance_id).update(
            {"session_config": None}
        )
        db.commit()

    request = UpdateAgentInstanceRequest.model_validate(
        {"session_config": {"agent": "claude", "model": "claude-opus-4-7"}}
    )
    with SessionLocal() as db:
        update_agent_instance_endpoint(
            instance_id=instance_id,
            update_data=request,
            user_id=str(user_id),
            db=db,
        )

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        assert row.session_config == {
            "agent": "claude",
            "model": "claude-opus-4-7",
        }


def test_patch_response_includes_session_config(
    user_and_instance: tuple[UUID, UUID],
) -> None:
    """Response shape gives the wrapper the merged result back so it can
    skip a follow-up GET to confirm the write."""
    user_id, instance_id = user_and_instance
    request = UpdateAgentInstanceRequest.model_validate(
        {"session_config": {"permission_mode": "acceptEdits"}}
    )
    with SessionLocal() as db:
        response = update_agent_instance_endpoint(
            instance_id=instance_id,
            update_data=request,
            user_id=str(user_id),
            db=db,
        )
    assert response.session_config is not None
    assert response.session_config["permission_mode"] == "acceptEdits"
    # Preserved keys come back too.
    assert response.session_config["model"] == "claude-sonnet-4-6"


def test_patch_instance_metadata_merges_and_preserves_siblings(
    user_and_instance: tuple[UUID, UUID],
) -> None:
    """The headless runners PATCH {"usage": {...}} onto instance_metadata each
    turn. That must merge in like session_config — a pre-existing sibling key
    (e.g. `source`) survives, and a later usage PATCH overwrites only `usage`."""
    user_id, instance_id = user_and_instance
    with SessionLocal() as db:
        db.query(AgentInstance).filter(AgentInstance.id == instance_id).update(
            {"instance_metadata": {"source": "app"}}
        )
        db.commit()

    usage = {"context": {"used_tokens": 100, "max_tokens": 200000, "cost_usd": None}}
    request = UpdateAgentInstanceRequest.model_validate(
        {"instance_metadata": {"usage": usage}}
    )
    with SessionLocal() as db:
        update_agent_instance_endpoint(
            instance_id=instance_id,
            update_data=request,
            user_id=str(user_id),
            db=db,
        )

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        assert row.instance_metadata == {"source": "app", "usage": usage}
        # session_config is untouched by an instance_metadata-only PATCH.
        assert row.session_config["model"] == "claude-sonnet-4-6"

    # A second usage PATCH replaces the whole usage blob, keeps `source`.
    usage2 = {"context": {"used_tokens": 150, "max_tokens": 200000, "cost_usd": 0.1}}
    request2 = UpdateAgentInstanceRequest.model_validate(
        {"instance_metadata": {"usage": usage2}}
    )
    with SessionLocal() as db:
        update_agent_instance_endpoint(
            instance_id=instance_id,
            update_data=request2,
            user_id=str(user_id),
            db=db,
        )
    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        assert row.instance_metadata == {"source": "app", "usage": usage2}
