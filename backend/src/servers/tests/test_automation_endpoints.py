"""Tests for the agent-facing automations API (servers/api/automations.py).

The human-facing equivalent is covered in backend/tests; this suite proves the
same CRUD works under the agent RS256-JWT auth used by the CLI, including
schedule handling, machine scoping, and user scoping.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.database.agent_profile_models import AgentProfile
from shared.database.enums import AgentStatus
from shared.database.models import AgentInstance, AgentType, Machine, User
from shared.database.session import get_db
from servers.api.auth import get_current_user_id
from servers.api.automations import automation_router


@pytest.fixture
def test_user(test_db):
    """The user seeded by the shared ``test_db`` fixture."""
    return test_db.query(User).first()


@pytest.fixture
def test_machine(test_db, test_user):
    """A machine owned by the seeded user — automations must target one."""
    machine = Machine(user_id=test_user.id, display_name="Test box")
    test_db.add(machine)
    test_db.commit()
    return machine


def _make_client(test_db, user_id):
    """A TestClient for a minimal app mounting only the automation router."""
    app = FastAPI()
    app.include_router(automation_router, prefix="/api/v1")

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = lambda: str(user_id)
    return TestClient(app)


@pytest.fixture
def client(test_db, test_user):
    return _make_client(test_db, test_user.id)


def _daily_body(machine, **overrides):
    body = {
        "title": "Nightly triage",
        "prompt": "Triage the backlog",
        "machine_id": str(machine.id),
        "directory": "/repo",
        "session_config": {"agent": "claude", "model": "opus"},
        "schedule_kind": "recurring",
        "frequency": {"kind": "daily", "time": "09:00"},
    }
    body.update(overrides)
    return body


class TestAutomationCrud:
    def test_create_recurring_daily(self, client, test_machine):
        resp = client.post("/api/v1/automations", json=_daily_body(test_machine))
        assert resp.status_code == 201, resp.text
        a = resp.json()
        assert a["title"] == "Nightly triage"
        assert a["enabled"] is True
        assert a["schedule_kind"] == "recurring"
        assert a["next_run_at"] is not None  # computed from the frequency

    def test_create_once(self, client, test_machine):
        body = _daily_body(
            test_machine,
            schedule_kind="once",
            frequency=None,
            run_at="2999-01-01T09:00:00Z",
        )
        resp = client.post("/api/v1/automations", json=body)
        assert resp.status_code == 201, resp.text
        assert resp.json()["next_run_at"].startswith("2999-01-01T09:00:00")

    def test_create_recurring_requires_frequency(self, client, test_machine):
        body = _daily_body(test_machine, frequency=None)
        resp = client.post("/api/v1/automations", json=body)
        assert resp.status_code == 422  # model validator: frequency required

    def test_create_once_requires_run_at(self, client, test_machine):
        body = _daily_body(test_machine, schedule_kind="once", frequency=None)
        resp = client.post("/api/v1/automations", json=body)
        assert resp.status_code == 422  # model validator: run_at required

    def test_create_rejects_config_without_agent(self, client, test_machine):
        body = _daily_body(test_machine, session_config={"model": "opus"})
        resp = client.post("/api/v1/automations", json=body)
        assert resp.status_code == 422  # session_config.agent required

    def test_create_unknown_machine_is_404(self, client):
        body = {
            "title": "Homeless",
            "prompt": "x",
            "machine_id": str(uuid4()),
            "directory": "/repo",
            "session_config": {"agent": "claude"},
            "schedule_kind": "recurring",
            "frequency": {"kind": "daily", "time": "09:00"},
        }
        resp = client.post("/api/v1/automations", json=body)
        assert resp.status_code == 404

    def test_list_and_get_roundtrip(self, client, test_machine):
        created = client.post(
            "/api/v1/automations", json=_daily_body(test_machine)
        ).json()
        listed = client.get("/api/v1/automations").json()
        assert [a["id"] for a in listed] == [created["id"]]

        got = client.get(f"/api/v1/automations/{created['id']}")
        assert got.status_code == 200
        assert got.json()["id"] == created["id"]

    def test_update_only_touches_sent_fields(self, client, test_machine):
        created = client.post(
            "/api/v1/automations", json=_daily_body(test_machine)
        ).json()
        resp = client.patch(
            f"/api/v1/automations/{created['id']}", json={"title": "Renamed"}
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()
        assert updated["title"] == "Renamed"
        assert updated["prompt"] == "Triage the backlog"  # untouched
        assert updated["next_run_at"] == created["next_run_at"]  # schedule untouched

    def test_pause_preserves_next_run(self, client, test_machine):
        created = client.post(
            "/api/v1/automations", json=_daily_body(test_machine)
        ).json()
        paused = client.patch(
            f"/api/v1/automations/{created['id']}", json={"enabled": False}
        ).json()
        assert paused["enabled"] is False
        # Toggling enabled must NOT recompute the fire time.
        assert paused["next_run_at"] == created["next_run_at"]

    def test_update_schedule_recomputes_next_run(self, client, test_machine):
        created = client.post(
            "/api/v1/automations", json=_daily_body(test_machine)
        ).json()
        switched = client.patch(
            f"/api/v1/automations/{created['id']}",
            json={"schedule_kind": "once", "run_at": "2999-01-01T09:00:00Z"},
        ).json()
        assert switched["schedule_kind"] == "once"
        assert switched["next_run_at"].startswith("2999-01-01T09:00:00")

    def test_delete_then_404(self, client, test_machine):
        created = client.post(
            "/api/v1/automations", json=_daily_body(test_machine)
        ).json()
        assert client.delete(f"/api/v1/automations/{created['id']}").status_code == 204
        assert client.get(f"/api/v1/automations/{created['id']}").status_code == 404

    def test_create_links_a_saved_agent(self, client, test_db, test_user, test_machine):
        """`vicoa automation create --agent-profile` sends the id on create; it
        used to be accepted and then dropped, so only a later PATCH linked it."""
        profile = AgentProfile(
            id=uuid4(),
            user_id=test_user.id,
            name="Reviewer",
            agent="claude",
            config={"agent": "claude", "model": "opus"},
        )
        test_db.add(profile)
        test_db.commit()

        resp = client.post(
            "/api/v1/automations",
            json=_daily_body(test_machine, agent_profile_id=str(profile.id)),
        )

        assert resp.status_code == 201, resp.text
        assert resp.json()["agent_profile_id"] == str(profile.id)


class TestAutomationRuns:
    def test_runs_empty_for_new_automation(self, client, test_machine):
        created = client.post(
            "/api/v1/automations", json=_daily_body(test_machine)
        ).json()
        resp = client.get(f"/api/v1/automations/{created['id']}/runs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_runs_unknown_automation_is_404(self, client):
        assert client.get(f"/api/v1/automations/{uuid4()}/runs").status_code == 404


class TestScoping:
    def test_other_user_cannot_read_automation(self, test_db, test_user, test_machine):
        owner_client = _make_client(test_db, test_user.id)
        created = owner_client.post(
            "/api/v1/automations", json=_daily_body(test_machine)
        ).json()

        stranger_client = _make_client(test_db, uuid4())
        assert (
            stranger_client.get(f"/api/v1/automations/{created['id']}").status_code
            == 404
        )
        assert stranger_client.get("/api/v1/automations").json() == []

    def test_cannot_target_another_users_machine(
        self, test_db, test_user, test_machine
    ):
        # test_machine belongs to test_user; a stranger creating against it 404s.
        stranger_client = _make_client(test_db, uuid4())
        resp = stranger_client.post(
            "/api/v1/automations", json=_daily_body(test_machine)
        )
        assert resp.status_code == 404


class TestSessionTarget:
    """`agent_instance_id` runs every fire in one of the author's sessions,
    which then supplies the machine, folder and agent."""

    @pytest.fixture
    def target(self, test_db, test_user, test_machine) -> AgentInstance:
        row = AgentInstance(
            id=uuid4(),
            agent_type_id=test_db.query(AgentType).first().id,
            user_id=test_user.id,
            status=AgentStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            name="Fix flaky test",
            machine_id=test_machine.id,
            project="~/repo",
            home_dir="/Users/me",
            session_config={"model": "opus", "permission_mode": "auto"},
        )
        test_db.add(row)
        test_db.commit()
        return row

    def _body(self, **overrides):
        body = {
            "title": "Keep going",
            "prompt": "Carry on",
            "schedule_kind": "recurring",
            "frequency": {"kind": "daily", "time": "09:00"},
        }
        body.update(overrides)
        return body

    def test_create_takes_the_sessions_machine_folder_and_agent(
        self, client, test_machine, target
    ):
        resp = client.post(
            "/api/v1/automations", json=self._body(agent_instance_id=str(target.id))
        )

        assert resp.status_code == 201, resp.text
        a = resp.json()
        assert a["agent_instance_id"] == str(target.id)
        assert a["agent_instance_name"] == "Fix flaky test"
        assert a["machine_id"] == str(test_machine.id)
        assert a["directory"] == "/Users/me/repo"
        # The agent comes from the agent type name when the config never
        # recorded one ("Claude Code" in the shared fixture).
        assert a["session_config"]["agent"] == "claude"
        assert a["session_config"]["model"] == "opus"
        assert a["worktree"] is None

    def test_what_is_sent_alongside_a_session_is_ignored(
        self, client, test_machine, target
    ):
        resp = client.post(
            "/api/v1/automations",
            json=_daily_body(
                test_machine,
                agent_instance_id=str(target.id),
                directory="/elsewhere",
                worktree={"mode": "new"},
            ),
        )

        assert resp.status_code == 201, resp.text
        assert resp.json()["directory"] == "/Users/me/repo"
        assert resp.json()["worktree"] is None

    def test_without_a_session_the_new_session_fields_are_required(self, client):
        resp = client.post("/api/v1/automations", json=self._body())
        assert resp.status_code == 422

    def test_another_users_session_is_404(self, test_db, target):
        stranger = _make_client(test_db, uuid4())
        resp = stranger.post(
            "/api/v1/automations", json=self._body(agent_instance_id=str(target.id))
        )
        assert resp.status_code == 404

    def test_a_deleted_session_is_404(self, client, test_db, target):
        target.status = AgentStatus.DELETED
        test_db.commit()
        resp = client.post(
            "/api/v1/automations", json=self._body(agent_instance_id=str(target.id))
        )
        assert resp.status_code == 404

    def test_a_session_with_no_machine_is_400(self, client, test_db, target):
        target.machine_id = None
        test_db.commit()
        resp = client.post(
            "/api/v1/automations", json=self._body(agent_instance_id=str(target.id))
        )
        assert resp.status_code == 400

    def test_switch_to_a_session_and_back(self, client, test_machine, target):
        created = client.post(
            "/api/v1/automations", json=_daily_body(test_machine)
        ).json()
        url = f"/api/v1/automations/{created['id']}"

        to_session = client.patch(url, json={"agent_instance_id": str(target.id)})
        assert to_session.status_code == 200, to_session.text
        assert to_session.json()["directory"] == "/Users/me/repo"

        # While a session is the target, it alone decides where runs happen.
        ignored = client.patch(url, json={"directory": "/elsewhere"})
        assert ignored.json()["directory"] == "/Users/me/repo"

        back = client.patch(url, json={"agent_instance_id": None, "directory": "/repo"})
        assert back.json()["agent_instance_id"] is None
        assert back.json()["agent_instance_name"] is None
        assert back.json()["directory"] == "/repo"
