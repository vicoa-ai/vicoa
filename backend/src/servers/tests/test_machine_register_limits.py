"""Machine registration under a plan limit (`shared.limits`).

The cap is on *new hosts*. The regression this suite guards is the other half:
a daemon that restarts, re-authenticates or rotates its key must keep
registering even when the account is at — or over — its limit, because that
path resolves to a row that already exists and is not an addition at all.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared import hooks
from shared.access_handlers import install_access_exception_handlers
from shared.database.models import Machine, User
from shared.database.session import get_db
from servers.api.auth import get_current_user_id
from servers.api.routers import agent_router


@pytest.fixture
def test_user(test_db):
    return test_db.query(User).first()


@pytest.fixture
def client(test_db, test_user):
    app = FastAPI()
    app.include_router(agent_router, prefix="/api/v1")
    # The real `servers.app` installs these; without them a CapabilityDenied
    # would surface as a 500 here and the 402 contract would go untested.
    install_access_exception_handlers(app)

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = lambda: str(test_user.id)
    return TestClient(app)


@pytest.fixture
def plan(monkeypatch):
    def _set(**caps: int | None):
        monkeypatch.setattr(
            hooks, "_plan_limits_hooks", [lambda db, user_id: dict(caps)]
        )

    return _set


def _body(**overrides):
    body = {
        "hostname": "laptop.local",
        "platform": "darwin",
        "hardware_id": "hw-1",
    }
    body.update(overrides)
    return body


class TestMachineRegistrationLimit:
    def test_first_machine_registers(self, client, plan):
        plan(machines=1)
        assert client.post("/api/v1/machines/register", json=_body()).status_code == 200

    def test_second_host_is_refused_with_402(self, client, plan, test_db, test_user):
        plan(machines=1)
        assert client.post("/api/v1/machines/register", json=_body()).status_code == 200
        response = client.post(
            "/api/v1/machines/register",
            json=_body(hardware_id="hw-2", hostname="desktop.local"),
        )
        assert response.status_code == 402
        assert response.json()["capability"] == "limit.machines"
        # And nothing was written for the refused host.
        assert (
            test_db.query(Machine).filter(Machine.user_id == test_user.id).count() == 1
        )

    def test_re_register_of_a_known_host_is_never_metered(self, client, plan):
        """The daemon restart / re-auth path. It must work at the limit."""
        plan(machines=1)
        first = client.post("/api/v1/machines/register", json=_body())
        assert first.status_code == 200
        again = client.post("/api/v1/machines/register", json=_body())
        assert again.status_code == 200
        assert again.json()["machine_id"] == first.json()["machine_id"]

    def test_re_register_works_even_when_already_over_the_limit(
        self, client, plan, test_db, test_user
    ):
        """An account that had several machines before the cap existed: every
        one of them keeps reconnecting, only a new host is refused."""
        for i in range(3):
            test_db.add(
                Machine(
                    user_id=test_user.id,
                    hostname=f"box{i}.local",
                    hardware_id=f"hw-{i}",
                )
            )
        test_db.commit()
        plan(machines=1)
        assert (
            client.post(
                "/api/v1/machines/register", json=_body(hardware_id="hw-1")
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/machines/register", json=_body(hardware_id="hw-new")
            ).status_code
            == 402
        )

    def test_unmetered_without_an_overlay(self, client, monkeypatch):
        monkeypatch.setattr(hooks, "_plan_limits_hooks", [])
        for i in range(4):
            assert (
                client.post(
                    "/api/v1/machines/register", json=_body(hardware_id=f"hw-{i}")
                ).status_code
                == 200
            )
