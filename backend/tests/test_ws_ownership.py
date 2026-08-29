"""Integration tests for the /ws hello-time ownership check (§2.9).

A session/machine-scoped connection must prove the instance/machine belongs
to the authenticated user — otherwise a token holder could subscribe to
someone else's session. These tests hit a real database, so they are marked
`integration` and run in CI (the suite needs Postgres + `alembic upgrade
head`); `make test-unit` skips them.
"""

from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from shared.auth.tokens import TokenClaims
from shared.database.enums import AgentStatus
from shared.database.models import AgentInstance, Machine, User, UserAgent
from shared.database.session import SessionLocal
from servers.api import ws_handler
from servers.api.ws_handler import ws_router

pytestmark = pytest.mark.integration

_FAKE_JWT = "header.payload.signature"


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(ws_router)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def owned_rows() -> Iterator[tuple[UUID, UUID, UUID]]:
    """Create a user who owns one agent instance and one machine."""
    owner_id, agent_id, instance_id, machine_id = (uuid4() for _ in range(4))
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add(User(id=owner_id, email=f"{owner_id}@test.vicoa", display_name="t"))
        # Machine has no relationship() to User, so SQLAlchemy's unit of work
        # does not order the User insert first — flush the parent to pin it.
        db.flush()
        db.add(UserAgent(id=agent_id, user_id=owner_id, name="Claude", is_active=True))
        db.add(
            AgentInstance(
                id=instance_id,
                user_agent_id=agent_id,
                user_id=owner_id,
                status=AgentStatus.ACTIVE,
                started_at=now,
            )
        )
        db.add(Machine(id=machine_id, user_id=owner_id))
        db.commit()
    try:
        yield owner_id, instance_id, machine_id
    finally:
        # Delete child rows before the User in FK order (these FKs are not
        # all ON DELETE CASCADE).
        with SessionLocal() as db:
            db.query(AgentInstance).filter(AgentInstance.user_id == owner_id).delete()
            db.query(Machine).filter(Machine.user_id == owner_id).delete()
            db.query(UserAgent).filter(UserAgent.user_id == owner_id).delete()
            db.query(User).filter(User.id == owner_id).delete()
            db.commit()


def _verifier_for(user_id: UUID):
    def _verify(token: str) -> TokenClaims:
        return TokenClaims(user_id=user_id)

    return _verify


def _connect(client: TestClient, hello: dict) -> None:
    with client.websocket_connect(
        "/ws", subprotocols=["vicoa-ws", f"vicoa-supabase.{_FAKE_JWT}"]
    ) as ws:
        ws.send_json(hello)
        info = ws.receive_json()
    assert info["type"] == "server_info"


def test_session_owner_connection_is_accepted(
    client: TestClient,
    owned_rows: tuple[UUID, UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id, instance_id, _ = owned_rows
    monkeypatch.setattr(ws_handler, "verify_user_token", _verifier_for(owner_id))

    _connect(
        client,
        {"type": "hello", "scope": "session-scoped", "instance_id": str(instance_id)},
    )


def test_session_connection_for_another_users_instance_is_rejected(
    client: TestClient,
    owned_rows: tuple[UUID, UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, instance_id, _ = owned_rows
    monkeypatch.setattr(ws_handler, "verify_user_token", _verifier_for(uuid4()))

    with pytest.raises(WebSocketDisconnect):
        _connect(
            client,
            {
                "type": "hello",
                "scope": "session-scoped",
                "instance_id": str(instance_id),
            },
        )


def test_machine_connection_for_another_users_machine_is_rejected(
    client: TestClient,
    owned_rows: tuple[UUID, UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, machine_id = owned_rows
    monkeypatch.setattr(ws_handler, "verify_user_token", _verifier_for(uuid4()))

    with pytest.raises(WebSocketDisconnect):
        _connect(
            client,
            {"type": "hello", "scope": "machine-scoped", "machine_id": str(machine_id)},
        )
