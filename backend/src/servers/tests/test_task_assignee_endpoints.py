"""`vicoa task … --assignee` on the agent-facing API.

The CLI sends a shorthand — `me`, `self`, `none`, an agent's name or an id —
and the server resolves it, so neither an agent nor a person has to know a
user id. Assigning an agent from the CLI starts it, like the dashboard does,
unless `start` is false; the same assignment from inside an agent's own
session starts nothing (only a person starts a run).
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from servers.api.auth import get_current_user_id
from servers.api.tasks import task_router
from shared.database import TaskDispatch
from shared.database.actor import Actor, set_session_actor
from shared.database.agent_profile_models import AgentProfile
from shared.database.enums import AgentStatus
from shared.database.models import AgentInstance, AgentType, User
from shared.database.session import get_db


@pytest.fixture
def test_user(test_db):
    return test_db.query(User).first()


@pytest.fixture
def client(test_db, test_user):
    """Like `test_task_endpoints._make_client`, but the auth stand-in also
    stamps the request's actor the way the real `get_current_user_id` does —
    whether a run starts depends on who acted."""
    app = FastAPI()
    app.include_router(task_router, prefix="/api/v1")

    def override_get_db():
        yield test_db

    def override_user(db: Session = Depends(get_db)) -> str:
        set_session_actor(db, Actor(type="user", id=test_user.id))
        return str(test_user.id)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = override_user
    return TestClient(app)


@pytest.fixture
def profile(test_db, test_user):
    row = AgentProfile(user_id=test_user.id, name="reviewer", agent="claude")
    test_db.add(row)
    test_db.commit()
    return row


@pytest.fixture
def profile_session(test_db, test_user, profile):
    agent_type = test_db.query(AgentType).first()
    row = AgentInstance(
        id=uuid4(),
        agent_type_id=agent_type.id,
        user_id=test_user.id,
        status=AgentStatus.ACTIVE,
        started_at=datetime.now(timezone.utc),
        agent_profile_id=profile.id,
    )
    test_db.add(row)
    test_db.commit()
    return row


def _task(client, **body):
    resp = client.post("/api/v1/tasks", json={"title": "t", "status": "todo", **body})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_me_assigns_the_keys_user(client, test_user):
    task = _task(client)
    resp = client.patch(f"/api/v1/tasks/{task['id']}", json={"assignee": "me"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["assignee_type"], body["assignee_id"]) == ("user", str(test_user.id))


def test_an_agent_by_name_starts_it(client, test_db, profile):
    task = _task(client)
    resp = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"assignee": "Reviewer"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["assignee_id"] == str(profile.id)
    assert body["dispatch"]["state"] == "queued"
    assert test_db.query(TaskDispatch).one().mode == "ownership"


def test_no_start_assigns_only(client, test_db, profile):
    task = _task(client)
    resp = client.patch(
        f"/api/v1/tasks/{task['id']}", json={"assignee": "reviewer", "start": False}
    )
    assert resp.status_code == 200, resp.text
    assert test_db.query(TaskDispatch).count() == 0


def test_self_from_the_agents_own_session_starts_nothing(
    client, test_db, profile, profile_session
):
    # The session is the agent's own: its write is signed as the agent, and
    # an agent's action never starts a run.
    task = _task(client)
    resp = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"assignee": "self", "agent_instance_id": str(profile_session.id)},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["assignee_id"] == str(profile.id)
    assert test_db.query(TaskDispatch).count() == 0


def test_self_needs_an_agent_session(client):
    task = _task(client)
    resp = client.patch(f"/api/v1/tasks/{task['id']}", json={"assignee": "self"})
    assert resp.status_code == 400


def test_an_unknown_name_is_404(client):
    task = _task(client)
    resp = client.patch(f"/api/v1/tasks/{task['id']}", json={"assignee": "nobody-here"})
    assert resp.status_code == 404


def test_shorthand_and_pair_together_is_400(client, test_user):
    task = _task(client)
    resp = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={
            "assignee": "me",
            "assignee_type": "user",
            "assignee_id": str(test_user.id),
        },
    )
    assert resp.status_code == 400


def test_none_clears(client):
    task = _task(client, assignee="me")
    assert task["assignee_type"] == "user"
    resp = client.patch(f"/api/v1/tasks/{task['id']}", json={"assignee": "none"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["assignee_id"] is None


def test_list_assigned_to_me(client):
    mine = _task(client, assignee="me")
    _task(client)
    listed = client.get("/api/v1/tasks", params={"assignee": "me"}).json()
    assert [t["id"] for t in listed] == [mine["id"]]
    unassigned = client.get("/api/v1/tasks", params={"assignee": "none"}).json()
    assert mine["id"] not in {t["id"] for t in unassigned}
