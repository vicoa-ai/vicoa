"""Importing sessions started outside Vicoa (servers/api/session_imports.py).

Covers the two contracts the daemon and the CLI rely on: an import creates a
resumable session with its history in order and nothing queued as a prompt,
and both endpoints recognise a native session that is already in Vicoa, so the
list can mark it and a second import returns the same row.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from servers.api.auth import get_current_user_id
from servers.api.session_imports import import_router
from servers.shared.db.queries import get_queued_user_messages
from shared.database.enums import AgentStatus, SenderType
from shared.database.models import AgentInstance, AgentType, Machine, Message, User
from shared.database.session import get_db

BASE = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)


def _make_client(test_db, user_id) -> TestClient:
    app = FastAPI()
    app.include_router(import_router, prefix="/api/v1")

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = lambda: str(user_id)
    return TestClient(app)


@pytest.fixture
def user(test_db) -> User:
    return test_db.query(User).first()


@pytest.fixture
def client(test_db, user) -> TestClient:
    return _make_client(test_db, user.id)


def _machine(test_db, user_id) -> Machine:
    machine = Machine(id=uuid4(), user_id=user_id, hostname="mac-mini.local")
    test_db.add(machine)
    test_db.commit()
    return machine


@pytest.fixture
def machine(test_db, user) -> Machine:
    return _machine(test_db, user.id)


def _other_user(test_db) -> User:
    other = User(
        id=uuid4(),
        email=f"other-{uuid4().hex[:8]}@example.com",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    test_db.add(other)
    test_db.commit()
    return other


def _payload(machine, agent="claude", native_id=None, **overrides):
    body = {
        "machine_id": str(machine.id),
        "agent": agent,
        "native_session_id": native_id or str(uuid4()),
        "project": "/Users/someone/projects/repo",
        "home_dir": "/Users/someone",
        "name": "Cap uploader retries",
        "source": "claude-desktop" if agent == "claude" else "codex_cli_rs",
        "source_label": "Claude desktop" if agent == "claude" else "Terminal",
        "messages": [
            {
                "sender": "user",
                "content": "Cap the retries",
                "created_at": BASE.isoformat(),
            },
            {
                "sender": "agent",
                "content": "Capped at 5.",
                "created_at": (BASE + timedelta(minutes=1)).isoformat(),
            },
        ],
    }
    body.update(overrides)
    return body


def _messages(test_db, instance_id):
    return (
        test_db.query(Message)
        .filter(Message.agent_instance_id == instance_id)
        .order_by(Message.created_at)
        .all()
    )


def _existing_instance(
    test_db,
    user_id,
    *,
    instance_id=None,
    machine=None,
    metadata=None,
    status=AgentStatus.AWAITING_INPUT,
):
    agent_type = test_db.query(AgentType).first()
    instance = AgentInstance(
        id=instance_id or uuid4(),
        agent_type_id=agent_type.id,
        user_id=user_id,
        status=status,
        machine_id=machine.id if machine else None,
        instance_metadata=metadata,
        started_at=datetime.now(timezone.utc),
    )
    test_db.add(instance)
    test_db.commit()
    return instance


class TestImportClaude:
    def test_creates_a_resumable_session_with_its_history(
        self, client, test_db, machine
    ):
        native_id = str(uuid4())
        response = client.post(
            "/api/v1/agent-instances/import",
            json=_payload(machine, native_id=native_id),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        # Resume names Claude's transcript by the instance id.
        assert body == {
            "agent_instance_id": native_id,
            "created": True,
            "message_count": 2,
        }

        instance = test_db.get(AgentInstance, body["agent_instance_id"])
        assert instance.status == AgentStatus.AWAITING_INPUT
        assert instance.machine_id == machine.id
        assert instance.project == "/Users/someone/projects/repo"
        assert instance.session_config == {"agent": "claude"}
        assert instance.name == "Cap uploader retries"
        assert instance.instance_metadata["source"] == "app"
        imported_from = instance.instance_metadata["imported_from"]
        assert imported_from["source"] == "claude-desktop"
        assert imported_from["source_label"] == "Claude desktop"
        assert imported_from["native_session_id"] == native_id
        assert instance.started_at.replace(tzinfo=timezone.utc) == BASE

        rows = _messages(test_db, instance.id)
        assert [(m.sender_type, m.content) for m in rows] == [
            (SenderType.USER, "Cap the retries"),
            (SenderType.AGENT, "Capped at 5."),
        ]
        assert instance.last_read_message_id == rows[-1].id
        # The old prompt must not come back to the agent as a new one.
        assert get_queued_user_messages(test_db, instance.id) == []

    def test_a_second_import_returns_the_same_session(self, client, test_db, machine):
        payload = _payload(machine)
        first = client.post("/api/v1/agent-instances/import", json=payload).json()
        second = client.post("/api/v1/agent-instances/import", json=payload).json()
        assert second == {
            "agent_instance_id": first["agent_instance_id"],
            "created": False,
            "message_count": 0,
        }
        assert len(_messages(test_db, first["agent_instance_id"])) == 2

    def test_rejects_an_id_that_is_not_a_uuid(self, client, machine):
        response = client.post(
            "/api/v1/agent-instances/import",
            json=_payload(machine, native_id="not-a-uuid"),
        )
        assert response.status_code == 400

    def test_refuses_an_id_another_account_holds(self, client, test_db, machine):
        other = _other_user(test_db)
        taken = _existing_instance(test_db, other.id)
        response = client.post(
            "/api/v1/agent-instances/import",
            json=_payload(machine, native_id=str(taken.id)),
        )
        assert response.status_code == 409

    def test_reuses_a_row_the_user_deleted(self, client, test_db, user, machine):
        deleted = _existing_instance(test_db, user.id, status=AgentStatus.DELETED)
        response = client.post(
            "/api/v1/agent-instances/import",
            json=_payload(machine, native_id=str(deleted.id)),
        )
        assert response.status_code == 200, response.text
        assert response.json()["created"] is True
        test_db.refresh(deleted)
        assert deleted.status == AgentStatus.AWAITING_INPUT
        assert deleted.machine_id == machine.id
        assert len(_messages(test_db, deleted.id)) == 2


class TestImportCodex:
    def test_records_the_thread_id_resume_reads(self, client, test_db, machine):
        thread_id = str(uuid4())
        body = client.post(
            "/api/v1/agent-instances/import",
            json=_payload(machine, agent="codex", native_id=thread_id),
        ).json()
        assert body["created"] is True
        assert body["agent_instance_id"] != thread_id
        instance = test_db.get(AgentInstance, body["agent_instance_id"])
        assert instance.instance_metadata["codex_thread_id"] == thread_id
        assert instance.session_config == {"agent": "codex"}

        again = client.post(
            "/api/v1/agent-instances/import",
            json=_payload(machine, agent="codex", native_id=thread_id),
        ).json()
        assert again["agent_instance_id"] == body["agent_instance_id"]
        assert again["created"] is False


class TestImportValidation:
    def test_unsupported_agent(self, client, machine):
        response = client.post(
            "/api/v1/agent-instances/import", json=_payload(machine, agent="cursor")
        )
        assert response.status_code == 400

    def test_machine_of_another_user(self, client, test_db):
        foreign = _machine(test_db, _other_user(test_db).id)
        response = client.post("/api/v1/agent-instances/import", json=_payload(foreign))
        assert response.status_code == 404

    def test_equal_timestamps_keep_their_order(self, client, test_db, machine):
        same = BASE.isoformat()
        payload = _payload(
            machine,
            messages=[
                {"sender": "user", "content": "first", "created_at": same},
                {"sender": "agent", "content": "second", "created_at": same},
                {"sender": "agent", "content": "third", "created_at": same},
            ],
        )
        body = client.post("/api/v1/agent-instances/import", json=payload).json()
        rows = _messages(test_db, body["agent_instance_id"])
        assert [m.content for m in rows] == ["first", "second", "third"]
        assert rows[0].created_at < rows[1].created_at < rows[2].created_at

    def test_long_names_are_trimmed(self, client, test_db, machine):
        body = client.post(
            "/api/v1/agent-instances/import", json=_payload(machine, name="x" * 400)
        ).json()
        instance = test_db.get(AgentInstance, body["agent_instance_id"])
        assert len(instance.name) == 255


class TestNativeLookup:
    def _lookup(self, client, machine, agent, ids):
        response = client.post(
            "/api/v1/agent-instances/native-lookup",
            json={
                "machine_id": str(machine.id),
                "agent": agent,
                "native_session_ids": ids,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()["matches"]

    def test_claude_matches_by_instance_id(self, client, test_db, user, machine):
        started_in_vicoa = _existing_instance(test_db, user.id, machine=machine)
        deleted = _existing_instance(test_db, user.id, status=AgentStatus.DELETED)
        unknown = str(uuid4())
        matches = self._lookup(
            client,
            machine,
            "claude",
            [str(started_in_vicoa.id), str(deleted.id), unknown, "junk"],
        )
        assert matches == {str(started_in_vicoa.id): str(started_in_vicoa.id)}

    def test_codex_matches_by_thread_id_on_that_machine(
        self, client, test_db, user, machine
    ):
        thread_id = str(uuid4())
        mine = _existing_instance(
            test_db, user.id, machine=machine, metadata={"codex_thread_id": thread_id}
        )
        other_machine = _machine(test_db, user.id)
        _existing_instance(
            test_db,
            user.id,
            machine=other_machine,
            metadata={"codex_thread_id": "elsewhere"},
        )
        assert self._lookup(client, machine, "codex", [thread_id, "elsewhere"]) == {
            thread_id: str(mine.id)
        }

    def test_codex_through_the_acp_adapter_counts(self, client, test_db, user, machine):
        thread_id = str(uuid4())
        via_acp = _existing_instance(
            test_db, user.id, machine=machine, metadata={"acp_session_id": thread_id}
        )
        assert self._lookup(client, machine, "codex", [thread_id]) == {
            thread_id: str(via_acp.id)
        }

    def test_other_users_sessions_never_match(self, client, test_db, machine):
        other = _other_user(test_db)
        theirs = _existing_instance(test_db, other.id)
        assert self._lookup(client, machine, "claude", [str(theirs.id)]) == {}

    def test_machine_of_another_user(self, client, test_db):
        foreign = _machine(test_db, _other_user(test_db).id)
        response = client.post(
            "/api/v1/agent-instances/native-lookup",
            json={
                "machine_id": str(foreign.id),
                "agent": "claude",
                "native_session_ids": [],
            },
        )
        assert response.status_code == 404
