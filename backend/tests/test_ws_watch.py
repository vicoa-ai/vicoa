"""Grant-gated watching over `/ws` (collaboration §9) — against a database.

The relay used to be owner-only end to end. A session shared with someone now
reaches them through `watch_instance` → the watcher room, grantee catch-up
through `fetch_messages_request`, and the shared rows through
`fetch_instances_request {scope: "all"}` — each gated by the one resolver the
REST lens uses. Revocation evicts: through `/_internal/access_changed` at once,
through the periodic revalidation otherwise.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from servers import watchers
from servers.api import ws_handler
from servers.api.ws_handler import (
    handle_fetch_instances_request,
    handle_fetch_messages_request,
    ws_router,
)
from shared.auth.tokens import TokenClaims
from shared.config import settings
from shared.database import (
    AgentInstance,
    AgentType,
    InstanceAccessLevel,
    Message,
    SenderType,
    User,
    UserInstanceAccess,
)
from shared.database.enums import AgentStatus
from shared.database.session import SessionLocal
from shared.websocket.connection_manager import Connection, connection_manager
from shared.websocket.envelope import build_instance_update
from shared.websocket.protocol import watcher_room

pytestmark = pytest.mark.integration

_FAKE_JWT = "header.payload.signature"


@dataclass
class World:
    owner: UUID
    grantee: UUID
    stranger: UUID
    instance: UUID
    share: UUID


@pytest.fixture
def world() -> Iterator[World]:
    owner, grantee, stranger = uuid4(), uuid4(), uuid4()
    agent, instance, share = uuid4(), uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        for uid in (owner, grantee, stranger):
            db.add(User(id=uid, email=f"{uid}@test.vicoa", display_name=str(uid)[:6]))
        db.flush()
        db.add(AgentType(id=agent, user_id=owner, name=f"claude-{agent}"))
        db.flush()
        db.add(
            AgentInstance(
                id=instance,
                agent_type_id=agent,
                user_id=owner,
                status=AgentStatus.ACTIVE,
                started_at=now,
                project="/Users/owner/src/secret-repo",
                home_dir="/Users/owner",
                session_config={"model": "opus", "cwd": "/Users/owner/src"},
            )
        )
        db.flush()
        db.add_all(
            [
                Message(
                    agent_instance_id=instance,
                    sender_type=SenderType.USER,
                    sender_user_id=owner,
                    content="please fix it",
                    requires_user_input=False,
                ),
                Message(
                    agent_instance_id=instance,
                    sender_type=SenderType.AGENT,
                    content="fixed",
                    requires_user_input=False,
                ),
            ]
        )
        db.add(
            UserInstanceAccess(
                id=share,
                agent_instance_id=instance,
                shared_email=f"{grantee}@test.vicoa",
                user_id=grantee,
                access=InstanceAccessLevel.READ,
                granted_by_user_id=owner,
            )
        )
        db.commit()
    try:
        yield World(owner, grantee, stranger, instance, share)
    finally:
        with SessionLocal() as db:
            db.query(UserInstanceAccess).filter(
                UserInstanceAccess.agent_instance_id == instance
            ).delete()
            db.query(Message).filter(Message.agent_instance_id == instance).delete()
            db.query(AgentInstance).filter(AgentInstance.id == instance).delete()
            db.query(AgentType).filter(AgentType.id == agent).delete()
            db.query(User).filter(User.id.in_([owner, grantee, stranger])).delete()
            db.commit()


@pytest.fixture
def connect() -> Iterator:
    """Register user-scoped connections on the process manager; unregister after."""
    made: list[Connection] = []

    def _make(user_id: UUID, scope: str = "user-scoped") -> Connection:
        conn = Connection(
            connection_id=uuid4().hex,
            user_id=str(user_id),
            scope=scope,
            rooms=frozenset({f"user:{user_id}:{scope}"}),
        )
        connection_manager.register(conn)
        made.append(conn)
        return conn

    yield _make
    for conn in made:
        connection_manager.unregister(conn)


def _drain(conn: Connection) -> list[dict]:
    frames = []
    while not conn.outbox.empty():
        frames.append(conn.outbox.get_nowait())
    return frames


async def test_a_grantee_can_watch_a_stranger_cannot(world: World, connect) -> None:
    grantee, stranger = connect(world.grantee), connect(world.stranger)
    frame = {
        "type": "watch_instance",
        "request_id": "r1",
        "instance_id": str(world.instance),
    }

    ok = await watchers.handle_watch_instance(grantee, frame)
    denied = await watchers.handle_watch_instance(stranger, frame)

    assert ok["ok"] is True and ok["role"] == "viewer"
    assert ok["request_id"] == "r1"
    assert str(world.instance) in grantee.watching
    # Not found and not yours read the same — no existence oracle.
    assert denied == {**denied, "ok": False, "role": None}
    assert stranger.watching == set()
    missing = await watchers.handle_watch_instance(
        stranger, {**frame, "instance_id": str(uuid4())}
    )
    assert missing["ok"] is False


async def test_the_owner_is_answered_but_never_joins(world: World, connect) -> None:
    owner = connect(world.owner)
    response = await watchers.handle_watch_instance(
        owner, {"type": "watch_instance", "instance_id": str(world.instance)}
    )
    assert response["ok"] is True and response["role"] == "owner"
    assert owner.watching == set()


async def test_an_agent_connection_cannot_watch(world: World, connect) -> None:
    session_conn = connect(world.grantee, scope="session-scoped")
    response = await watchers.handle_watch_instance(
        session_conn, {"type": "watch_instance", "instance_id": str(world.instance)}
    )
    assert response["ok"] is False


async def test_a_watcher_receives_the_narrowed_row(world: World, connect) -> None:
    grantee = connect(world.grantee)
    await watchers.handle_watch_instance(
        grantee, {"type": "watch_instance", "instance_id": str(world.instance)}
    )
    with SessionLocal() as db:
        row = db.get(AgentInstance, world.instance)
        assert row is not None
        payload = build_instance_update(row)
    connection_manager.broadcast_update(
        str(world.owner),
        payload,
        [f"user:{world.owner}:user-scoped", watcher_room(str(world.instance))],
    )
    [frame] = _drain(grantee)
    body = frame["payload"]["body"]
    assert body["home_dir"] is None and body["machine_id"] is None
    assert body["project"] == "secret-repo"
    assert body["session_config"] == {"model": "opus"}
    assert body["live_state"]


async def test_grantee_catch_up_returns_the_whole_conversation(
    world: World, connect
) -> None:
    grantee, stranger = connect(world.grantee), connect(world.stranger)
    frame = {
        "type": "fetch_messages_request",
        "request_id": "r",
        "instance_id": str(world.instance),
    }

    mine = await handle_fetch_messages_request(grantee, frame)
    theirs = await handle_fetch_messages_request(stranger, frame)

    assert [r["content"] for r in mine["rows"]] == ["please fix it", "fixed"]
    assert theirs["rows"] == []


async def test_an_agent_connection_stays_owner_only_for_catch_up(
    world: World, connect
) -> None:
    session_conn = connect(world.grantee, scope="session-scoped")
    response = await handle_fetch_messages_request(
        session_conn,
        {"type": "fetch_messages_request", "instance_id": str(world.instance)},
    )
    assert response["rows"] == []


async def test_fetch_instances_scope_all_adds_the_shared_row_narrowed(
    world: World, connect
) -> None:
    grantee = connect(world.grantee)

    default = await handle_fetch_instances_request(grantee, {"request_id": "a"})
    everything = await handle_fetch_instances_request(
        grantee, {"request_id": "b", "scope": "all"}
    )

    assert str(world.instance) not in {r["id"] for r in default["rows"]}
    [row] = [r for r in everything["rows"] if r["id"] == str(world.instance)]
    assert row["home_dir"] is None and row["machine_id"] is None
    assert row["project"] == "secret-repo"
    assert row["live_state"]


async def test_fetch_instances_scope_all_is_ignored_for_agents(
    world: World, connect
) -> None:
    session_conn = connect(world.grantee, scope="session-scoped")
    response = await handle_fetch_instances_request(session_conn, {"scope": "all"})
    assert str(world.instance) not in {r["id"] for r in response["rows"]}


async def test_revalidation_evicts_a_revoked_watcher(world: World, connect) -> None:
    grantee = connect(world.grantee)
    await watchers.handle_watch_instance(
        grantee, {"type": "watch_instance", "instance_id": str(world.instance)}
    )
    with SessionLocal() as db:
        assert watchers.revalidate_watchers(db) == 0
        db.query(UserInstanceAccess).filter(
            UserInstanceAccess.id == world.share
        ).delete()
        db.commit()
        assert watchers.revalidate_watchers(db) == 1

    assert grantee.watching == set()
    assert _drain(grantee) == [
        {
            "type": "watch_revoked",
            "instance_id": str(world.instance),
            "reason": "access_revoked",
        }
    ]


def test_access_changed_receiver(world: World, connect, monkeypatch) -> None:
    monkeypatch.setattr(settings, "internal_broadcast_token", "secret")
    app = FastAPI()
    app.include_router(ws_router)
    grantee = connect(world.grantee)
    connection_manager.watch(grantee, str(world.instance))
    grantee.access_cache[str(world.instance)] = (1e12, "viewer")  # a stale "yes"
    with SessionLocal() as db:
        db.query(UserInstanceAccess).filter(
            UserInstanceAccess.id == world.share
        ).delete()
        db.commit()
    body = {"user_ids": [str(world.grantee)], "instance_id": str(world.instance)}

    with TestClient(app) as client:
        assert client.post("/_internal/access_changed", json=body).status_code == 401
        response = client.post(
            "/_internal/access_changed",
            json=body,
            headers={"Authorization": "Bearer secret"},
        )

    assert response.json() == {"ok": True, "evicted": 1}
    assert grantee.access_cache == {}
    frames = _drain(grantee)
    assert frames[0]["type"] == "watch_revoked"
    assert frames[1]["type"] == "update"
    assert frames[1]["payload"]["body"] == {
        "t": "access-changed",
        "project_id": None,
        "instance_id": str(world.instance),
    }


def test_watch_over_a_real_socket(world: World, monkeypatch) -> None:
    def _verify(_token: str) -> TokenClaims:
        return TokenClaims(user_id=world.grantee)

    monkeypatch.setattr(ws_handler, "verify_user_token", _verify)
    app = FastAPI()
    app.include_router(ws_router)
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws", subprotocols=["vicoa-ws", f"vicoa-supabase.{_FAKE_JWT}"]
        ) as ws:
            ws.send_json({"type": "hello", "scope": "user-scoped"})
            assert ws.receive_json()["type"] == "server_info"
            ws.send_json(
                {
                    "type": "watch_instance",
                    "request_id": "w1",
                    "instance_id": str(world.instance),
                }
            )
            response = ws.receive_json()
            assert response["type"] == "watch_instance_response"
            assert response["ok"] is True and response["role"] == "viewer"
            assert connection_manager.has_watchers(str(world.instance))
            ws.send_json(
                {"type": "unwatch_instance", "instance_id": str(world.instance)}
            )
            ws.send_json({"type": "pong"})
    assert not connection_manager.has_watchers(str(world.instance))
