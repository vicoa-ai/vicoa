"""A claimed run that raises still leaves a trace.

The claim moves `next_run_at` on before the run dispatches, and the sweep
gathers runs with `return_exceptions=True`. So an exception anywhere in a run
used to drop it silently: no history row, no log line, and the slot was gone.
Now a dispatch that raises is recorded as `failed` with a short reason, and a
record that raises is at least logged.
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from servers.scheduler import loop
from servers.scheduler.dispatch import DispatchResult
from shared.database.automation_models import Automation, AutomationRun
from shared.database.enums import AgentStatus
from shared.database.models import AgentInstance, AgentType, Machine, User

# The loop opens and commits its own sessions.
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


def _due(test_db, user, machine, **overrides) -> Automation:
    fields = dict(
        id=uuid4(),
        user_id=user.id,
        title="nightly",
        prompt="tidy up",
        machine_id=machine.id,
        directory="/Users/me/repo",
        session_config={"agent": "claude"},
        schedule_kind="recurring",
        frequency={"kind": "hourly", "minute": 0},
        timezone="UTC",
        enabled=True,
        next_run_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    fields.update(overrides)
    row = Automation(**fields)
    test_db.add(row)
    test_db.commit()
    return row


def _runs(test_db) -> list[AutomationRun]:
    test_db.expire_all()
    return test_db.query(AutomationRun).all()


async def _raise_connection_lost(**kwargs) -> DispatchResult:
    raise ConnectionError("connection to the database was lost\nSQL: SELECT 1")


class TestDispatchRaises:
    @pytest.mark.asyncio
    async def test_records_a_failed_run_and_logs_it(
        self, test_db, bound_session, user, machine, monkeypatch, caplog
    ):
        automation = _due(test_db, user, machine)
        monkeypatch.setattr(loop, "dispatch_automation", _raise_connection_lost)
        (row,) = loop._claim_due_blocking()

        with caplog.at_level(logging.ERROR, logger=loop.__name__):
            await loop.AutomationScheduler()._process_row(row)

        (run,) = _runs(test_db)
        assert run.automation_id == automation.id
        assert run.status == "failed"
        # One line for the run history; the traceback is in the log.
        assert run.detail == "error: connection to the database was lost"
        assert run.planned_at == row["planned_at"]
        assert run.agent_instance_id is None
        test_db.expire_all()
        stored = test_db.get(Automation, automation.id)
        assert stored.last_run_status == "failed"
        # A failed run is not a reason to stop the schedule.
        assert stored.enabled is True
        (record,) = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert str(automation.id) in record.getMessage()
        assert record.exc_info is not None

    @pytest.mark.asyncio
    async def test_a_session_target_that_raises_is_recorded_too(
        self, test_db, bound_session, user, machine, monkeypatch
    ):
        agent_type = test_db.query(AgentType).first()
        session = AgentInstance(
            id=uuid4(),
            agent_type_id=agent_type.id,
            user_id=user.id,
            status=AgentStatus.AWAITING_INPUT,
            started_at=datetime.now(timezone.utc),
            machine_id=machine.id,
        )
        test_db.add(session)
        test_db.commit()
        _due(test_db, user, machine, agent_instance_id=session.id)
        monkeypatch.setattr(loop, "dispatch_to_session", _raise_connection_lost)
        (row,) = loop._claim_due_blocking()

        await loop.AutomationScheduler()._process_row(row)

        (run,) = _runs(test_db)
        assert run.status == "failed"
        assert run.detail == "error: connection to the database was lost"

    @pytest.mark.asyncio
    async def test_an_exception_with_no_message_names_its_type(
        self, test_db, bound_session, user, machine, monkeypatch
    ):
        async def bare(**kwargs) -> DispatchResult:
            raise KeyError()

        _due(test_db, user, machine)
        monkeypatch.setattr(loop, "dispatch_automation", bare)
        (row,) = loop._claim_due_blocking()

        await loop.AutomationScheduler()._process_row(row)

        (run,) = _runs(test_db)
        assert run.detail == "error: KeyError"

    @pytest.mark.asyncio
    async def test_a_long_reason_is_cut_short(
        self, test_db, bound_session, user, machine, monkeypatch
    ):
        async def long_error(**kwargs) -> DispatchResult:
            raise RuntimeError("x" * 1000)

        _due(test_db, user, machine)
        monkeypatch.setattr(loop, "dispatch_automation", long_error)
        (row,) = loop._claim_due_blocking()

        await loop.AutomationScheduler()._process_row(row)

        (run,) = _runs(test_db)
        assert run.detail is not None
        assert len(run.detail) == loop.ERROR_DETAIL_MAX
        assert run.detail.startswith("error: xxx")


class TestRecordRaises:
    @pytest.mark.asyncio
    async def test_is_logged_and_does_not_escape(
        self, test_db, bound_session, user, machine, monkeypatch, caplog
    ):
        automation = _due(test_db, user, machine)

        async def fired(**kwargs) -> DispatchResult:
            return DispatchResult(status="fired")

        def broken_record(*args) -> None:
            raise ConnectionError("connection to the database was lost")

        monkeypatch.setattr(loop, "dispatch_automation", fired)
        monkeypatch.setattr(loop, "_record_run_blocking", broken_record)
        (row,) = loop._claim_due_blocking()

        with caplog.at_level(logging.ERROR, logger=loop.__name__):
            await loop.AutomationScheduler()._process_row(row)

        (record,) = [r for r in caplog.records if r.levelno == logging.ERROR]
        message = record.getMessage()
        assert str(automation.id) in message
        # The log says what was lost: this run had fired.
        assert "fired" in message
        assert record.exc_info is not None


class TestLinkLookupRaises:
    @pytest.mark.asyncio
    async def test_a_fired_run_stays_fired_without_its_link(
        self, test_db, bound_session, user, machine, monkeypatch, caplog
    ):
        """The session was started: losing the lookup that links it must not
        turn the run into a failed one."""
        _due(test_db, user, machine)

        async def fired(**kwargs) -> DispatchResult:
            return DispatchResult(status="fired", agent_instance_id=str(uuid4()))

        def broken_lookup(instance_id) -> bool:
            raise ConnectionError("connection to the database was lost")

        monkeypatch.setattr(loop, "dispatch_automation", fired)
        monkeypatch.setattr(loop, "_instance_exists_blocking", broken_lookup)
        (row,) = loop._claim_due_blocking()

        with caplog.at_level(logging.ERROR, logger=loop.__name__):
            await loop.AutomationScheduler()._process_row(row)

        (run,) = _runs(test_db)
        assert run.status == "fired"
        assert run.agent_instance_id is None
        assert any(r.exc_info for r in caplog.records if r.levelno == logging.ERROR)
