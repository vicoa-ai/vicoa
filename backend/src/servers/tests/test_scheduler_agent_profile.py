"""An automation that runs a saved agent has to start a session that *is* that
agent.

The sweep resolves the profile for its config and instructions, and it also has
to hand the profile id on to the session it starts. Without it the session reads
as a plain one: no agent on the session page, no entry in the agent's Run
history, and its task comments signed by the user instead of the agent.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from servers.scheduler import loop
from servers.scheduler.dispatch import DispatchResult
from shared.database.agent_profile_models import AgentProfile
from shared.database.automation_models import Automation
from shared.database.models import Machine, User

# `_claim_due_blocking` opens and commits its own session.
pytestmark = pytest.mark.committed_db


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
def bound_session(db_session_factory, monkeypatch):
    monkeypatch.setattr(loop, "SessionLocal", db_session_factory)
    return db_session_factory


def _profile(test_db, user, **overrides) -> AgentProfile:
    fields = dict(
        id=uuid4(),
        user_id=user.id,
        name="Reviewer",
        agent="claude",
        config={"agent": "claude", "model": "claude-opus-5"},
        system_prompt="Prefer small, reviewable diffs.",
    )
    fields.update(overrides)
    row = AgentProfile(**fields)
    test_db.add(row)
    test_db.commit()
    return row


def _due(test_db, user, machine, profile_id) -> Automation:
    row = Automation(
        id=uuid4(),
        user_id=user.id,
        title="nightly",
        prompt="tidy up",
        machine_id=machine.id,
        directory="/repo",
        session_config={"agent": "claude", "model": "claude-haiku-4-5"},
        agent_profile_id=profile_id,
        schedule_kind="once",
        timezone="UTC",
        enabled=True,
        next_run_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    test_db.add(row)
    test_db.commit()
    return row


class TestClaim:
    def test_a_live_profile_rides_along(self, test_db, bound_session, user, machine):
        profile = _profile(test_db, user)
        _due(test_db, user, machine, profile.id)

        (row,) = loop._claim_due_blocking()

        assert row["agent_profile_id"] == profile.id
        assert row["system_prompt"] == "Prefer small, reviewable diffs."

    def test_an_archived_profile_does_not(self, test_db, bound_session, user, machine):
        """The run falls back to the stored snapshot, so it is not that agent's
        run and must not be labelled as one."""
        profile = _profile(test_db, user, is_archived=True)
        _due(test_db, user, machine, profile.id)

        (row,) = loop._claim_due_blocking()

        assert row["agent_profile_id"] is None

    def test_no_profile(self, test_db, bound_session, user, machine):
        _due(test_db, user, machine, None)

        (row,) = loop._claim_due_blocking()

        assert row["agent_profile_id"] is None


class TestProcessRow:
    @pytest.fixture
    def stamps(self, monkeypatch):
        calls: list[tuple[str, str, str]] = []

        async def fake_dispatch(**kwargs):
            return DispatchResult(status="fired", agent_instance_id="inst-1")

        async def no_wait(self, instance_id):
            return None

        monkeypatch.setattr(loop, "dispatch_automation", fake_dispatch)
        monkeypatch.setattr(loop.AutomationScheduler, "_await_instance", no_wait)
        monkeypatch.setattr(loop, "_record_run_blocking", lambda *a: None)
        monkeypatch.setattr(
            loop,
            "stamp_agent_profile_in_background",
            lambda *args: calls.append(args),
        )
        return calls

    def _row(self, profile_id):
        return {
            "id": uuid4(),
            "user_id": uuid4(),
            "machine_id": uuid4(),
            "directory": "/repo",
            "worktree": None,
            "session_config": {"agent": "claude"},
            "system_prompt": None,
            "agent_profile_id": profile_id,
            "prompt": "go",
            "planned_at": datetime.now(timezone.utc),
        }

    @pytest.mark.asyncio
    async def test_a_fired_run_stamps_its_session(self, stamps):
        row = self._row(uuid4())

        await loop.AutomationScheduler()._process_row(row)

        assert stamps == [(str(row["user_id"]), "inst-1", str(row["agent_profile_id"]))]

    @pytest.mark.asyncio
    async def test_a_plain_run_stamps_nothing(self, stamps):
        await loop.AutomationScheduler()._process_row(self._row(None))

        assert stamps == []
