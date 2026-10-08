"""An automation pointed at an existing session continues that session.

Each run reaches the same session one of two ways: a message, when its agent
is connected, or a resume carrying the prompt, when it is not. Either way the
run row links that session, and nothing new is spawned.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest

from servers.scheduler import loop, session_dispatch
from servers.scheduler.dispatch import DispatchResult
from shared.database.automation_models import Automation, AutomationRun
from shared.database.enums import AgentStatus, SenderType
from shared.database.models import AgentInstance, AgentType, Machine, Message, User
from shared.websocket.rpc import RpcError

# The dispatcher and the loop open and commit their own sessions.
pytestmark = pytest.mark.committed_db


class FakeSockets:
    """Stands in for `connection_manager`: which sessions hold a socket, and
    what got broadcast."""

    def __init__(self) -> None:
        self.connected: set[str] = set()
        self.broadcasts: list[tuple[str, dict, list[str]]] = []

    def is_session_connected(self, instance_id: str) -> bool:
        return instance_id in self.connected

    def broadcast_update(self, user_id: str, payload: dict, rooms: list[str]) -> None:
        self.broadcasts.append((user_id, payload, rooms))


class FakeRpc:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, dict]] = []
        self.result: Any = {}
        self.error: RpcError | None = None

    async def call(self, user_id: str, machine_id: str, method: str, params: dict):
        self.calls.append((user_id, machine_id, method, params))
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def user(test_db) -> User:
    return test_db.query(User).first()


@pytest.fixture
def machine(test_db, user) -> Machine:
    row = Machine(id=uuid4(), user_id=user.id, display_name="laptop")
    test_db.add(row)
    test_db.commit()
    return row


@pytest.fixture
def session_row(test_db, user, machine) -> AgentInstance:
    agent_type = test_db.query(AgentType).first()
    row = AgentInstance(
        id=uuid4(),
        agent_type_id=agent_type.id,
        user_id=user.id,
        status=AgentStatus.AWAITING_INPUT,
        started_at=datetime.now(timezone.utc),
        machine_id=machine.id,
        project="~/repo",
        home_dir="/Users/me",
        session_config={"agent": "codex", "model": "gpt-5", "permission_mode": "auto"},
        instance_metadata={"codex_thread_id": "thread-1"},
    )
    test_db.add(row)
    test_db.commit()
    return row


@pytest.fixture
def automation(test_db, user, machine, session_row) -> Automation:
    row = Automation(
        id=uuid4(),
        user_id=user.id,
        title="check CI",
        prompt="Is CI green yet?",
        machine_id=machine.id,
        directory="/Users/me/repo",
        session_config={"agent": "codex"},
        agent_instance_id=session_row.id,
        schedule_kind="recurring",
        frequency={"kind": "hourly", "minute": 0},
        timezone="UTC",
        enabled=True,
        next_run_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    test_db.add(row)
    test_db.commit()
    return row


@pytest.fixture
def sockets(monkeypatch, db_session_factory) -> FakeSockets:
    fake = FakeSockets()
    monkeypatch.setattr(session_dispatch, "SessionLocal", db_session_factory)
    monkeypatch.setattr(loop, "SessionLocal", db_session_factory)
    monkeypatch.setattr(session_dispatch, "connection_manager", fake)
    return fake


@pytest.fixture
def rpc(monkeypatch) -> FakeRpc:
    fake = FakeRpc()
    monkeypatch.setattr(session_dispatch.rpc_router, "call", fake.call)
    return fake


async def _dispatch(user, automation, session_row) -> DispatchResult:
    return await session_dispatch.dispatch_to_session(
        user_id=user.id,
        automation_id=automation.id,
        instance_id=session_row.id,
        prompt=automation.prompt,
    )


def _messages(test_db, instance_id: UUID) -> list[Message]:
    test_db.expire_all()
    return (
        test_db.query(Message)
        .filter(Message.agent_instance_id == instance_id)
        .order_by(Message.created_at)
        .all()
    )


class TestRunningSession:
    @pytest.mark.asyncio
    async def test_posts_the_prompt_as_the_authors_message(
        self, test_db, user, automation, session_row, sockets, rpc
    ):
        sockets.connected.add(str(session_row.id))

        result = await _dispatch(user, automation, session_row)

        assert result.status == "fired"
        assert result.agent_instance_id == str(session_row.id)
        assert rpc.calls == []
        (message,) = _messages(test_db, session_row.id)
        assert message.content == "Is CI green yet?"
        assert message.sender_type == SenderType.USER
        assert message.sender_user_id == user.id
        assert message.message_metadata == {"automation_id": str(automation.id)}
        # Reaches the agent's own room, not only dashboards.
        (_, _, rooms) = sockets.broadcasts[0]
        assert f"user:{user.id}:session:{session_row.id}" in rooms

    @pytest.mark.asyncio
    async def test_queues_behind_a_running_turn(
        self, test_db, user, automation, session_row, sockets, rpc
    ):
        session_row.status = AgentStatus.ACTIVE
        test_db.commit()
        sockets.connected.add(str(session_row.id))

        await _dispatch(user, automation, session_row)

        (message,) = _messages(test_db, session_row.id)
        assert (message.message_metadata or {})["queue"] == {"status": "queued"}

    @pytest.mark.asyncio
    async def test_skips_while_its_last_prompt_is_still_queued(
        self, test_db, user, automation, session_row, sockets, rpc
    ):
        test_db.add(
            Message(
                agent_instance_id=session_row.id,
                sender_type=SenderType.USER,
                content="Is CI green yet?",
                message_metadata={
                    "automation_id": str(automation.id),
                    "queue": {"status": "queued"},
                },
            )
        )
        test_db.commit()
        sockets.connected.add(str(session_row.id))

        result = await _dispatch(user, automation, session_row)

        assert result.status == "skipped"
        assert len(_messages(test_db, session_row.id)) == 1

    @pytest.mark.asyncio
    async def test_a_consumed_prompt_does_not_block_the_next(
        self, test_db, user, automation, session_row, sockets, rpc
    ):
        test_db.add(
            Message(
                agent_instance_id=session_row.id,
                sender_type=SenderType.USER,
                content="Is CI green yet?",
                message_metadata={
                    "automation_id": str(automation.id),
                    "queue": {"status": "consumed"},
                },
            )
        )
        test_db.commit()
        sockets.connected.add(str(session_row.id))

        result = await _dispatch(user, automation, session_row)

        assert result.status == "fired"
        assert len(_messages(test_db, session_row.id)) == 2


class TestStoppedSession:
    @pytest.mark.asyncio
    async def test_resumes_it_with_the_prompt(
        self, test_db, user, machine, automation, session_row, sockets, rpc
    ):
        rpc.result = {"agent_instance_id": str(session_row.id)}

        result = await _dispatch(user, automation, session_row)

        assert result.status == "fired"
        assert result.agent_instance_id == str(session_row.id)
        ((uid, machine_id, method, params),) = rpc.calls
        assert (uid, machine_id, method) == (
            str(user.id),
            str(machine.id),
            "spawn-session",
        )
        assert params["directory"] == "/Users/me/repo"
        assert params["agent"] == "codex"
        assert params["resume"] == {
            "agent_instance_id": str(session_row.id),
            "agent_session_id": "thread-1",
        }
        # The session's own model and permission mode, plus the prompt.
        assert params["metadata"]["prompt"] == "Is CI green yet?"
        assert params["metadata"]["model"] == "gpt-5"
        assert params["metadata"]["permission_mode"] == "auto"
        # The wrapper posts the launch prompt itself.
        assert _messages(test_db, session_row.id) == []

    @pytest.mark.asyncio
    async def test_already_running_falls_back_to_a_message(
        self, test_db, user, automation, session_row, sockets, rpc
    ):
        rpc.result = {"agent_instance_id": str(session_row.id), "already_running": True}

        result = await _dispatch(user, automation, session_row)

        assert result.status == "fired"
        (message,) = _messages(test_db, session_row.id)
        assert message.content == "Is CI green yet?"

    @pytest.mark.asyncio
    async def test_machine_offline(self, user, automation, session_row, sockets, rpc):
        rpc.error = RpcError("no_handler")

        result = await _dispatch(user, automation, session_row)

        assert result.status == "missed_offline"

    @pytest.mark.asyncio
    async def test_daemon_error(self, user, automation, session_row, sockets, rpc):
        rpc.result = {"error": "codex is not installed"}

        result = await _dispatch(user, automation, session_row)

        assert result.status == "failed"
        assert result.detail == "codex is not installed"


class TestGoneSession:
    @pytest.mark.asyncio
    async def test_a_deleted_session_pauses_the_automation(
        self, test_db, user, automation, session_row, sockets, rpc
    ):
        session_row.status = AgentStatus.DELETED
        test_db.commit()

        result = await _dispatch(user, automation, session_row)

        assert result.status == "failed"
        assert result.disable is True
        assert rpc.calls == []


class TestLoop:
    def test_claim_carries_the_target(self, automation, session_row, sockets):
        (row,) = loop._claim_due_blocking()

        assert row["agent_instance_id"] == session_row.id

    @pytest.mark.asyncio
    async def test_run_links_the_session_and_spawns_nothing_new(
        self, test_db, user, automation, session_row, sockets, rpc, monkeypatch
    ):
        async def no_spawn(**kwargs):
            raise AssertionError("a session automation must not spawn")

        monkeypatch.setattr(loop, "dispatch_automation", no_spawn)
        sockets.connected.add(str(session_row.id))
        (row,) = loop._claim_due_blocking()

        await loop.AutomationScheduler()._process_row(row)

        test_db.expire_all()
        (run,) = test_db.query(AutomationRun).all()
        assert run.status == "fired"
        assert run.agent_instance_id == session_row.id

    @pytest.mark.asyncio
    async def test_a_gone_session_disables_the_automation(
        self, test_db, user, automation, session_row, sockets, rpc
    ):
        session_row.status = AgentStatus.DELETED
        test_db.commit()
        (row,) = loop._claim_due_blocking()

        await loop.AutomationScheduler()._process_row(row)

        test_db.expire_all()
        assert test_db.get(Automation, automation.id).enabled is False
        (run,) = test_db.query(AutomationRun).all()
        assert run.status == "failed"
