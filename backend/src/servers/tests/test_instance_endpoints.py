"""Tests for the agent-facing instance API (servers/api/instances.py).

The human-facing equivalents are covered under backend/tests; this suite proves
the same list + transcript reads work under the agent RS256-JWT auth used by the
CLI (``vicoa session ls`` / ``vicoa session get``), including user scoping,
newest-first ordering, ``active_only``, and cursor pagination.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from servers.api.auth import get_current_user_id
from servers.api.instances import instance_router
from shared.database.enums import AgentStatus, SenderType
from shared.database.models import AgentInstance, Message, User, UserAgent
from shared.database.session import get_db


@pytest.fixture
def test_user(test_db):
    """The user seeded by the shared ``test_db`` fixture."""
    return test_db.query(User).first()


def _make_client(test_db, user_id):
    """A TestClient for a minimal app mounting only the instance router."""
    app = FastAPI()
    app.include_router(instance_router, prefix="/api/v1")

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = lambda: str(user_id)
    return TestClient(app)


@pytest.fixture
def client(test_db, test_user):
    return _make_client(test_db, test_user.id)


def _make_instance(test_db, status=AgentStatus.ACTIVE, name=None, started_at=None):
    user = test_db.query(User).first()
    user_agent = test_db.query(UserAgent).first()
    instance = AgentInstance(
        id=uuid4(),
        user_agent_id=user_agent.id,
        user_id=user.id,
        name=name,
        status=status,
        started_at=started_at or datetime.now(timezone.utc),
    )
    test_db.add(instance)
    test_db.commit()
    return instance


def _add_message(test_db, instance, content, sender_type, created_at, *, ask=False):
    msg = Message(
        id=uuid4(),
        agent_instance_id=instance.id,
        sender_type=sender_type,
        content=content,
        created_at=created_at,
        requires_user_input=ask,
    )
    test_db.add(msg)
    test_db.commit()
    return msg


class TestListSessions:
    def test_lists_owned_sessions_newest_first(self, client, test_db):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        _make_instance(test_db, name="older", started_at=base)
        _make_instance(test_db, name="newer", started_at=base + timedelta(hours=1))

        body = client.get("/api/v1/agent-instances").json()
        assert body["total"] == 2
        assert body["has_more"] is False
        assert [i["name"] for i in body["items"]] == ["newer", "older"]

    def test_active_only_drops_closed(self, client, test_db):
        _make_instance(test_db, status=AgentStatus.ACTIVE, name="live")
        _make_instance(test_db, status=AgentStatus.COMPLETED, name="done")

        all_body = client.get("/api/v1/agent-instances").json()
        assert {i["name"] for i in all_body["items"]} == {"live", "done"}

        active = client.get(
            "/api/v1/agent-instances", params={"active_only": "true"}
        ).json()
        assert [i["name"] for i in active["items"]] == ["live"]

    def test_limit_sets_has_more(self, client, test_db):
        for n in range(3):
            _make_instance(test_db, name=f"s{n}")
        body = client.get("/api/v1/agent-instances", params={"limit": 2}).json()
        assert len(body["items"]) == 2
        assert body["total"] == 3
        assert body["has_more"] is True


class TestTranscript:
    def test_returns_messages_oldest_first(self, client, test_db):
        inst = _make_instance(test_db)
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        _add_message(test_db, inst, "first", SenderType.AGENT, base)
        _add_message(
            test_db, inst, "reply", SenderType.USER, base + timedelta(minutes=1)
        )
        _add_message(
            test_db,
            inst,
            "need input?",
            SenderType.AGENT,
            base + timedelta(minutes=2),
            ask=True,
        )

        msgs = client.get(f"/api/v1/agent-instances/{inst.id}/messages").json()
        assert [m["content"] for m in msgs] == ["first", "reply", "need input?"]
        assert [m["sender_type"] for m in msgs] == ["AGENT", "USER", "AGENT"]
        assert msgs[-1]["requires_user_input"] is True

    def test_limit_returns_most_recent(self, client, test_db):
        inst = _make_instance(test_db)
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for n in range(3):
            _add_message(
                test_db, inst, f"m{n}", SenderType.AGENT, base + timedelta(minutes=n)
            )
        msgs = client.get(
            f"/api/v1/agent-instances/{inst.id}/messages", params={"limit": 1}
        ).json()
        assert [m["content"] for m in msgs] == ["m2"]

    def test_before_cursor_walks_backwards(self, client, test_db):
        inst = _make_instance(test_db)
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        ids = [
            _add_message(
                test_db, inst, f"m{n}", SenderType.AGENT, base + timedelta(minutes=n)
            ).id
            for n in range(3)
        ]
        # Everything strictly before the last message → the first two, in order.
        older = client.get(
            f"/api/v1/agent-instances/{inst.id}/messages",
            params={"before_message_id": str(ids[2])},
        ).json()
        assert [m["content"] for m in older] == ["m0", "m1"]

    def test_unknown_instance_404(self, client):
        assert (
            client.get(f"/api/v1/agent-instances/{uuid4()}/messages").status_code == 404
        )


class TestScoping:
    def test_stranger_sees_nothing(self, test_db, test_user):
        inst = _make_instance(test_db, name="private")
        _add_message(
            test_db,
            inst,
            "secret",
            SenderType.AGENT,
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        stranger = _make_client(test_db, uuid4())
        listing = stranger.get("/api/v1/agent-instances").json()
        assert listing["items"] == []
        assert listing["total"] == 0
        assert (
            stranger.get(f"/api/v1/agent-instances/{inst.id}/messages").status_code
            == 404
        )
