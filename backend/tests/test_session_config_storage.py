"""Integration tests for session_config persistence on agent_instances.

Covers plan plans/session-config-storage.md tier 3a — backend round-trip from
self-register POST through the DB column to the response shape and WS
broadcast. Hits a real Postgres, so marked `integration`.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from servers.api.models import RegisterAgentInstanceRequest
from servers.api.routers import register_agent_instance_endpoint
from shared.database.enums import AgentStatus
from shared.database.models import AgentInstance, Message, User, UserAgent
from shared.database.session import SessionLocal
from shared.websocket.connection_manager import Connection, connection_manager

pytestmark = pytest.mark.integration


CLAUDE_CONFIG = {
    "agent": "claude",
    "model": "claude-sonnet-4-6",
    "thinking_effort": "low",
    "permission_mode": "acceptEdits",
}


@pytest.fixture
def user_id() -> Iterator[UUID]:
    uid = uuid4()
    with SessionLocal() as db:
        db.add(User(id=uid, email=f"{uid}@test.vicoa", display_name="t"))
        db.commit()
    try:
        yield uid
    finally:
        with SessionLocal() as db:
            instance_ids = [
                row.id
                for row in db.query(AgentInstance.id)
                .filter(AgentInstance.user_id == uid)
                .all()
            ]
            if instance_ids:
                db.query(Message).filter(
                    Message.agent_instance_id.in_(instance_ids)
                ).delete(synchronize_session=False)
            db.query(AgentInstance).filter(AgentInstance.user_id == uid).delete()
            db.query(UserAgent).filter(UserAgent.user_id == uid).delete()
            db.query(User).filter(User.id == uid).delete()
            db.commit()


def _user_conn(user_id: UUID) -> Connection:
    return Connection(
        connection_id=uuid4().hex,
        user_id=str(user_id),
        scope="user-scoped",
        rooms=frozenset({f"user:{user_id}:user-scoped"}),
    )


def test_register_persists_session_config(user_id: UUID) -> None:
    """Tracer bullet: a fresh self-register with session_config writes the column
    and returns the same shape on the response."""
    new_id = uuid4()
    with SessionLocal() as db:
        response = register_agent_instance_endpoint(
            request=RegisterAgentInstanceRequest(
                agent_type="claude",
                agent_instance_id=str(new_id),
                session_config=CLAUDE_CONFIG,
            ),
            user_id=str(user_id),
            db=db,
        )

    assert response.session_config == CLAUDE_CONFIG

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == new_id).one()
        assert row.session_config == CLAUDE_CONFIG


def test_register_without_session_config_leaves_column_null(user_id: UUID) -> None:
    """Backwards compatibility: an old wrapper that omits session_config leaves
    the column null (legacy sessions degrade to the message-history scan)."""
    new_id = uuid4()
    with SessionLocal() as db:
        response = register_agent_instance_endpoint(
            request=RegisterAgentInstanceRequest(
                agent_type="claude",
                agent_instance_id=str(new_id),
            ),
            user_id=str(user_id),
            db=db,
        )

    assert response.session_config is None

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == new_id).one()
        assert row.session_config is None


def test_register_broadcast_includes_session_config(user_id: UUID) -> None:
    """The WS instance-created envelope carries session_config so connected
    clients (mobile chat header) can render the spawn-time config live."""
    new_id = uuid4()
    web = _user_conn(user_id)
    connection_manager.register(web)
    try:
        with SessionLocal() as db:
            register_agent_instance_endpoint(
                request=RegisterAgentInstanceRequest(
                    agent_type="claude",
                    agent_instance_id=str(new_id),
                    session_config=CLAUDE_CONFIG,
                ),
                user_id=str(user_id),
                db=db,
            )

        frame = web.outbox.get_nowait()
        assert frame["payload"]["entity"] == "agent_instances"
        assert frame["payload"]["body"]["t"] == "instance-created"
        assert frame["payload"]["body"]["session_config"] == CLAUDE_CONFIG
    finally:
        connection_manager.unregister(web)


def test_activate_existing_field_present_overwrites(user_id: UUID) -> None:
    """When a spawn-request pre-allocated the row and the wrapper sends
    session_config in its self-register, the wrapper's value is authoritative."""
    new_id = uuid4()
    with SessionLocal() as db:
        agent = UserAgent(user_id=user_id, name="claude")
        db.add(agent)
        db.flush()
        db.add(
            AgentInstance(
                id=new_id,
                user_agent_id=agent.id,
                user_id=user_id,
                status=AgentStatus.STARTING,
                instance_metadata={"spawn_starting": True},
                session_config=None,
            )
        )
        db.commit()

    with SessionLocal() as db:
        register_agent_instance_endpoint(
            request=RegisterAgentInstanceRequest(
                agent_type="claude",
                agent_instance_id=str(new_id),
                session_config=CLAUDE_CONFIG,
            ),
            user_id=str(user_id),
            db=db,
        )

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == new_id).one()
        assert row.status == AgentStatus.ACTIVE
        assert row.session_config == CLAUDE_CONFIG


def test_user_facing_detail_endpoint_includes_session_config(user_id: UUID) -> None:
    """The user-facing GET /agent-instances/{id} endpoint exposes session_config
    so the mobile chat header pill can render the spawn-time config without
    scanning the message history (plan §5.3)."""
    from backend.db.queries import get_agent_instance_detail

    new_id = uuid4()
    with SessionLocal() as db:
        agent = UserAgent(user_id=user_id, name="claude")
        db.add(agent)
        db.flush()
        db.add(
            AgentInstance(
                id=new_id,
                user_agent_id=agent.id,
                user_id=user_id,
                status=AgentStatus.ACTIVE,
                session_config=CLAUDE_CONFIG,
            )
        )
        db.commit()

    with SessionLocal() as db:
        detail = get_agent_instance_detail(db, new_id, user_id, message_limit=0)
    assert detail is not None
    assert detail.session_config == CLAUDE_CONFIG


def test_user_facing_list_endpoint_includes_session_config(user_id: UUID) -> None:
    """The user-facing list helper also exposes session_config on each item so
    the agent-list view shows correct config without per-row fetches."""
    from backend.db.queries import get_all_agent_instances

    new_id = uuid4()
    with SessionLocal() as db:
        agent = UserAgent(user_id=user_id, name="claude")
        db.add(agent)
        db.flush()
        db.add(
            AgentInstance(
                id=new_id,
                user_agent_id=agent.id,
                user_id=user_id,
                status=AgentStatus.ACTIVE,
                session_config=CLAUDE_CONFIG,
            )
        )
        db.commit()

    with SessionLocal() as db:
        items, _ = get_all_agent_instances(db, user_id, limit=10, offset=0)
    matching = [it for it in items if it.id == str(new_id)]
    assert matching, "expected the new instance to appear in the list"
    assert matching[0].session_config == CLAUDE_CONFIG


def test_activate_existing_field_absent_preserves(user_id: UUID) -> None:
    """When the wrapper does NOT send session_config (field absent in the JSON,
    e.g. older client), any pre-staged value on the spawn-request row survives."""
    new_id = uuid4()
    prestaged = {"agent": "claude", "model": "claude-opus-4-7"}
    with SessionLocal() as db:
        agent = UserAgent(user_id=user_id, name="claude")
        db.add(agent)
        db.flush()
        db.add(
            AgentInstance(
                id=new_id,
                user_agent_id=agent.id,
                user_id=user_id,
                status=AgentStatus.STARTING,
                instance_metadata={"spawn_starting": True},
                session_config=prestaged,
            )
        )
        db.commit()

    # model_validate from a raw dict that OMITS the session_config key entirely
    # mirrors the wire format from an old wrapper.
    request = RegisterAgentInstanceRequest.model_validate(
        {"agent_type": "claude", "agent_instance_id": str(new_id)}
    )
    with SessionLocal() as db:
        register_agent_instance_endpoint(
            request=request,
            user_id=str(user_id),
            db=db,
        )

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == new_id).one()
        assert row.session_config == prestaged
