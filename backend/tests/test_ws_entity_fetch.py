"""Constructed-fixture suite for fetch_instances / fetch_machines catch-up.

`fetch_user_instances` / `fetch_user_machines` are the server-side SELECTs
behind the `fetch_instances_request` / `fetch_machines_request` WS frames
(websocket-migration §4 Phase 4a, §2.6). They are user-wide, watermarked by
`updated_at`, and return rows in the canonical envelope-body shape.

These tests hit a real database, so they are marked `integration`.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from servers.api.ws_handler import (
    handle_fetch_instances_request,
    handle_fetch_machines_request,
)
from servers.shared.db.queries import fetch_user_instances, fetch_user_machines
from shared.database.models import AgentInstance, Machine, User, UserAgent
from shared.database.session import SessionLocal
from shared.websocket import Connection

pytestmark = pytest.mark.integration

BASE = datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def fetch_user() -> Iterator[tuple[UUID, UUID]]:
    """A persisted user + user-agent; yields (user_id, agent_id)."""
    user_id, agent_id = uuid4(), uuid4()
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.flush()  # Machine has no relationship() to User — pin insert order.
        db.add(UserAgent(id=agent_id, user_id=user_id, name=f"agent-{agent_id}"))
        db.commit()
    try:
        yield user_id, agent_id
    finally:
        with SessionLocal() as db:
            db.query(AgentInstance).filter(AgentInstance.user_id == user_id).delete()
            db.query(Machine).filter(Machine.user_id == user_id).delete()
            db.query(UserAgent).filter(UserAgent.user_id == user_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()


def _add_instances(
    user_id: UUID, agent_id: UUID, specs: list[tuple[str, datetime]]
) -> None:
    with SessionLocal() as db:
        for name, updated_at in specs:
            db.add(
                AgentInstance(
                    id=uuid4(),
                    user_agent_id=agent_id,
                    user_id=user_id,
                    name=name,
                    updated_at=updated_at,
                )
            )
        db.commit()


def test_instance_watermark_fetch_returns_recently_updated_instances(
    fetch_user: tuple[UUID, UUID],
) -> None:
    user_id, agent_id = fetch_user
    _add_instances(
        user_id,
        agent_id,
        [
            ("old", BASE - timedelta(hours=1)),
            ("recent", BASE + timedelta(minutes=5)),
        ],
    )

    with SessionLocal() as db:
        rows = fetch_user_instances(db, user_id, updated_after=BASE.isoformat())

    assert [row["name"] for row in rows] == ["recent"]


def test_instance_fetch_with_no_watermark_returns_all_instances(
    fetch_user: tuple[UUID, UUID],
) -> None:
    user_id, agent_id = fetch_user
    _add_instances(
        user_id,
        agent_id,
        [("a", BASE - timedelta(hours=2)), ("b", BASE + timedelta(minutes=1))],
    )

    with SessionLocal() as db:
        rows = fetch_user_instances(db, user_id, updated_after=None)

    assert sorted(row["name"] for row in rows) == ["a", "b"]


def test_instance_fetch_excludes_another_users_instances(
    fetch_user: tuple[UUID, UUID],
) -> None:
    user_id, agent_id = fetch_user
    _add_instances(user_id, agent_id, [("mine", BASE + timedelta(minutes=1))])

    with SessionLocal() as db:
        rows = fetch_user_instances(db, uuid4(), updated_after=None)

    assert rows == []


def _add_machines(user_id: UUID, specs: list[tuple[str, datetime]]) -> None:
    with SessionLocal() as db:
        for display_name, updated_at in specs:
            db.add(
                Machine(
                    id=uuid4(),
                    user_id=user_id,
                    display_name=display_name,
                    updated_at=updated_at,
                )
            )
        db.commit()


def test_machine_watermark_fetch_returns_recently_updated_machines(
    fetch_user: tuple[UUID, UUID],
) -> None:
    user_id, _ = fetch_user
    _add_machines(
        user_id,
        [
            ("old", BASE - timedelta(hours=1)),
            ("recent", BASE + timedelta(minutes=5)),
        ],
    )

    with SessionLocal() as db:
        rows = fetch_user_machines(db, user_id, updated_after=BASE.isoformat())

    assert [row["display_name"] for row in rows] == ["recent"]


def test_machine_fetch_with_no_watermark_excludes_another_users_machines(
    fetch_user: tuple[UUID, UUID],
) -> None:
    user_id, _ = fetch_user
    _add_machines(user_id, [("mine", BASE)])

    with SessionLocal() as db:
        assert fetch_user_machines(db, user_id, updated_after=None)
        assert fetch_user_machines(db, uuid4(), updated_after=None) == []


# --- handlers (run against a user-scoped Connection) ---


def _user_conn(user_id: UUID) -> Connection:
    return Connection(
        connection_id=uuid4().hex,
        user_id=str(user_id),
        scope="user-scoped",
        rooms=frozenset({f"user:{user_id}:user-scoped"}),
    )


async def test_handler_answers_a_fetch_instances_request(
    fetch_user: tuple[UUID, UUID],
) -> None:
    user_id, agent_id = fetch_user
    _add_instances(user_id, agent_id, [("inst-a", BASE + timedelta(minutes=1))])

    response = await handle_fetch_instances_request(
        _user_conn(user_id),
        {
            "type": "fetch_instances_request",
            "request_id": "fi1",
            "updated_after": None,
        },
    )

    assert response["type"] == "fetch_instances_response"
    assert response["request_id"] == "fi1"
    assert [row["name"] for row in response["rows"]] == ["inst-a"]


async def test_handler_answers_a_fetch_machines_request(
    fetch_user: tuple[UUID, UUID],
) -> None:
    user_id, _ = fetch_user
    _add_machines(user_id, [("box-a", BASE + timedelta(minutes=1))])

    response = await handle_fetch_machines_request(
        _user_conn(user_id),
        {
            "type": "fetch_machines_request",
            "request_id": "fm1",
            "updated_after": None,
        },
    )

    assert response["type"] == "fetch_machines_response"
    assert response["request_id"] == "fm1"
    assert [row["display_name"] for row in response["rows"]] == ["box-a"]


def test_ws_round_trip_answers_a_fetch_instances_request(
    fetch_user: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # End-to-end over a real socket: a user-scoped connection's
    # fetch_instances_request frame is dispatched and answered.
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from servers.api import ws_handler
    from shared.auth.tokens import TokenClaims

    user_id, agent_id = fetch_user
    _add_instances(user_id, agent_id, [("rt-inst", BASE + timedelta(minutes=1))])
    monkeypatch.setattr(
        ws_handler,
        "verify_user_token",
        lambda _token: TokenClaims(user_id=user_id),
    )

    app = FastAPI()
    app.include_router(ws_handler.ws_router)
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws", subprotocols=["vicoa-ws", "vicoa-supabase.h.p.s"]
        ) as ws:
            ws.send_json({"type": "hello", "scope": "user-scoped"})
            assert ws.receive_json()["type"] == "server_info"
            ws.send_json(
                {
                    "type": "fetch_instances_request",
                    "request_id": "rt",
                    "updated_after": None,
                }
            )
            response = ws.receive_json()

    assert response["type"] == "fetch_instances_response"
    assert [row["name"] for row in response["rows"]] == ["rt-inst"]
