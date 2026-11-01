"""Plan limits: counting, enforcement, and the one endpoint clients read.

The invariant these tests exist to protect is the open-build one: with no
overlay registered, nothing is metered. Every "denied" case below has to
monkeypatch a hook in first, and the first test checks that the *absence* of
one is unlimited rather than zero.
"""

from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from shared import hooks, limits
from shared.database import Machine
from shared.database.automation_models import Automation
from backend.db import automation_queries


@pytest.fixture
def no_plan_hooks(monkeypatch):
    """The open build: no overlay, so no limits."""
    monkeypatch.setattr(hooks, "_plan_limits_hooks", [])


@pytest.fixture
def plan(monkeypatch):
    """Register a plan, as the overlay would. Returns a setter."""

    def _set(**caps: int | None):
        monkeypatch.setattr(
            hooks, "_plan_limits_hooks", [lambda db, user_id: dict(caps)]
        )

    return _set


def _machine(db, user_id, name="box"):
    machine = Machine(user_id=user_id, display_name=name, hostname=f"{name}.local")
    db.add(machine)
    db.commit()
    return machine


def _automation(db, user_id, machine_id, title="nightly", enabled=True):
    row = Automation(
        user_id=user_id,
        title=title,
        prompt="do the thing",
        machine_id=machine_id,
        directory="/tmp",
        session_config={},
        schedule_kind="recurring",
        frequency={"kind": "daily", "at": "09:00"},
        timezone="UTC",
        enabled=enabled,
    )
    db.add(row)
    db.commit()
    return row


class TestOpenBuildIsUnmetered:
    def test_no_hook_means_unlimited(self, test_db, test_user, no_plan_hooks):
        for _ in range(5):
            _machine(test_db, test_user.id)
        limits.check_limit(test_db, test_user.id, limits.RESOURCE_MACHINES)

    def test_describe_reports_null_limits(self, test_db, test_user, no_plan_hooks):
        statuses = {s.key: s for s in limits.describe_limits(test_db, test_user.id)}
        assert set(statuses) == {
            limits.RESOURCE_MACHINES,
            limits.RESOURCE_AUTOMATIONS,
        }
        assert all(s.limit is None and s.unlimited for s in statuses.values())
        assert all(s.remaining is None for s in statuses.values())

    def test_a_key_the_plan_omits_is_unlimited(self, test_db, test_user, plan):
        """A partial plan mapping must not read as zero for the rest."""
        plan(machines=1)
        for _ in range(3):
            _machine(test_db, test_user.id)
        limits.check_limit(test_db, test_user.id, limits.RESOURCE_AUTOMATIONS)


class TestMachineLimit:
    def test_first_machine_allowed_second_refused(self, test_db, test_user, plan):
        plan(machines=1)
        limits.check_limit(test_db, test_user.id, limits.RESOURCE_MACHINES)
        _machine(test_db, test_user.id)
        with pytest.raises(hooks.CapabilityDenied) as exc:
            limits.check_limit(test_db, test_user.id, limits.RESOURCE_MACHINES)
        assert exc.value.capability == "limit.machines"

    def test_existing_over_limit_is_never_retroactive(self, test_db, test_user, plan):
        """A free account that had three machines before the cap existed keeps
        all three; only the fourth is refused. There is no sweep."""
        for i in range(3):
            _machine(test_db, test_user.id, name=f"box{i}")
        plan(machines=1)
        assert (
            test_db.query(Machine).filter(Machine.user_id == test_user.id).count() == 3
        )
        with pytest.raises(hooks.CapabilityDenied):
            limits.check_limit(test_db, test_user.id, limits.RESOURCE_MACHINES)

    def test_scoped_to_the_user(self, test_db, test_user, plan):
        other = uuid4()
        from shared.database.models import User

        test_db.add(User(id=other, email="other@example.com", display_name="Other"))
        test_db.commit()
        _machine(test_db, other, name="theirs")
        plan(machines=1)
        limits.check_limit(test_db, test_user.id, limits.RESOURCE_MACHINES)


class TestAutomationLimit:
    def test_create_is_metered_through_the_query_layer(self, test_db, test_user, plan):
        """Both the dashboard router and the CLI router call this function, so
        metering here is what keeps the two surfaces from drifting."""
        machine = _machine(test_db, test_user.id)
        plan(automations=1)
        automation_queries.create_automation(
            test_db,
            test_user.id,
            title="first",
            prompt="hi",
            machine_id=machine.id,
            directory="/tmp",
            session_config={},
            schedule_kind="recurring",
            frequency={"kind": "daily", "at": "09:00"},
        )
        with pytest.raises(hooks.CapabilityDenied) as exc:
            automation_queries.create_automation(
                test_db,
                test_user.id,
                title="second",
                prompt="hi",
                machine_id=machine.id,
                directory="/tmp",
                session_config={},
                schedule_kind="recurring",
                frequency={"kind": "daily", "at": "09:00"},
            )
        assert exc.value.capability == "limit.automations"

    def test_disabled_automations_still_count(self, test_db, test_user, plan):
        """The cap is on how many exist. If pausing freed a slot, the limit
        would be trivially dodged by keeping a pool of disabled rows."""
        machine = _machine(test_db, test_user.id)
        _automation(test_db, test_user.id, machine.id, enabled=False)
        plan(automations=1)
        with pytest.raises(hooks.CapabilityDenied):
            limits.check_limit(test_db, test_user.id, limits.RESOURCE_AUTOMATIONS)

    def test_pausing_an_automation_is_not_metered(self, test_db, test_user, plan):
        """Being at (or over) the cap must never block editing what you have."""
        machine = _machine(test_db, test_user.id)
        row = _automation(test_db, test_user.id, machine.id)
        plan(automations=1)
        updated = automation_queries.update_automation(
            test_db, test_user.id, row.id, {"enabled": False}
        )
        assert updated is not None and updated.enabled is False


class TestDenialCopy:
    def test_a_cap_of_one_reads_as_singular(self, test_db, test_user, plan):
        """ "Your plan includes 1 machines" is the kind of sentence a user
        screenshots. The noun agrees with the number."""
        plan(machines=1)
        _machine(test_db, test_user.id)
        with pytest.raises(hooks.CapabilityDenied) as exc:
            limits.check_limit(test_db, test_user.id, limits.RESOURCE_MACHINES)
        assert "1 machine." in exc.value.reason
        assert "machines" not in exc.value.reason

    def test_a_larger_cap_reads_as_plural(self, test_db, test_user, plan):
        machine = _machine(test_db, test_user.id)
        for i in range(2):
            _automation(test_db, test_user.id, machine.id, title=f"a{i}")
        plan(automations=2)
        with pytest.raises(hooks.CapabilityDenied) as exc:
            limits.check_limit(test_db, test_user.id, limits.RESOURCE_AUTOMATIONS)
        assert "2 automations" in exc.value.reason


class TestSingleResourceRead:
    def test_describe_limit_matches_describe_limits(self, test_db, test_user, plan):
        plan(machines=2)
        _machine(test_db, test_user.id)
        one = limits.describe_limit(test_db, test_user.id, limits.RESOURCE_MACHINES)
        many = next(
            s
            for s in limits.describe_limits(test_db, test_user.id)
            if s.key == limits.RESOURCE_MACHINES
        )
        assert one == many

    def test_unknown_resource_is_a_programming_error(self, test_db, test_user):
        with pytest.raises(KeyError):
            limits.check_limit(test_db, test_user.id, "not_a_resource")


class TestHookFailureModes:
    def test_a_broken_hook_denies_rather_than_gives_away(
        self, test_db, test_user, monkeypatch
    ):
        def broken(db, user_id):
            raise RuntimeError("billing is down")

        monkeypatch.setattr(hooks, "_plan_limits_hooks", [broken])
        with pytest.raises(hooks.CapabilityDenied):
            limits.check_limit(test_db, test_user.id, limits.RESOURCE_MACHINES)

    def test_a_database_error_is_not_a_billing_answer(
        self, test_db, test_user, monkeypatch
    ):
        """Same rule as `check_capability`: a flycast blip must surface as 503,
        not as "upgrade your plan" to someone who already pays."""

        def flaky(db, user_id):
            raise OperationalError("SELECT 1", {}, Exception("connection lost"))

        monkeypatch.setattr(hooks, "_plan_limits_hooks", [flaky])
        with pytest.raises(OperationalError):
            limits.check_limit(test_db, test_user.id, limits.RESOURCE_MACHINES)

    def test_most_permissive_hook_wins(self, test_db, test_user, monkeypatch):
        """A second hook grants (promo, grandfathering); it never restricts."""
        monkeypatch.setattr(
            hooks,
            "_plan_limits_hooks",
            [lambda db, uid: {"machines": 1}, lambda db, uid: {"machines": 5}],
        )
        for _ in range(4):
            _machine(test_db, test_user.id)
        limits.check_limit(test_db, test_user.id, limits.RESOURCE_MACHINES)

    def test_unlimited_beats_a_number(self, test_db, test_user, monkeypatch):
        monkeypatch.setattr(
            hooks,
            "_plan_limits_hooks",
            [lambda db, uid: {"machines": 1}, lambda db, uid: {"machines": None}],
        )
        for _ in range(3):
            _machine(test_db, test_user.id)
        limits.check_limit(test_db, test_user.id, limits.RESOURCE_MACHINES)


class TestLimitsEndpoints:
    def test_get_limits_shape(self, authenticated_client, test_user, plan):
        plan(machines=1, automations=10)
        response = authenticated_client.get("/api/v1/limits")
        assert response.status_code == 200
        rows = {row["key"]: row for row in response.json()["limits"]}
        assert set(rows) == {"machines", "automations"}
        assert rows["machines"]["limit"] == 1
        assert rows["machines"]["used"] == 0
        assert rows["machines"]["remaining"] == 1
        assert rows["machines"]["unlimited"] is False
        assert rows["automations"]["limit"] == 10

    def test_get_limits_unlimited_in_the_open_build(
        self, authenticated_client, no_plan_hooks
    ):
        rows = authenticated_client.get("/api/v1/limits").json()["limits"]
        assert all(row["limit"] is None and row["unlimited"] for row in rows)

    def test_denial_is_402_with_the_capability(
        self, authenticated_client, test_db, test_user, plan
    ):
        """The wire contract a client keys its paywall on: the status, the
        server's sentence, and the capability naming which cap was hit."""
        machine = _machine(test_db, test_user.id)
        _automation(test_db, test_user.id, machine.id)
        plan(automations=1)
        response = authenticated_client.post(
            "/api/v1/automations",
            json={
                "title": "one too many",
                "prompt": "go",
                "machine_id": str(machine.id),
                "directory": "/tmp",
                "session_config": {"agent": "claude"},
                "schedule_kind": "recurring",
                "frequency": {"kind": "daily", "time": "09:00"},
            },
        )
        assert response.status_code == 402
        body = response.json()
        assert body["capability"] == "limit.automations"
        assert "1 automation" in body["detail"]

    def test_the_same_action_is_allowed_under_the_cap(
        self, authenticated_client, test_db, test_user, plan
    ):
        """And the gate does not fire before the cap is actually reached."""
        machine = _machine(test_db, test_user.id)
        plan(automations=1)
        response = authenticated_client.post(
            "/api/v1/automations",
            json={
                "title": "the first one",
                "prompt": "go",
                "machine_id": str(machine.id),
                "directory": "/tmp",
                "session_config": {"agent": "claude"},
                "schedule_kind": "recurring",
                "frequency": {"kind": "daily", "time": "09:00"},
            },
        )
        assert response.status_code == 201, response.text
