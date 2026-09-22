"""Tests for the agent-facing share-link API (servers/api/shares.py).

The link mechanics (token, expiry, viewer) are covered by
backend/tests/test_shares.py; what is only reachable here is the owner-only
gate: an API key can mint, list and revoke links on the caller's *own*
sessions and projects and nothing else — including a session the caller
could reach through a grant on the dashboard.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.database import (
    AgentInstance,
    AgentType,
    Project,
    ProjectGrant,
    ShareLink,
    User,
)
from shared.database.enums import AgentStatus
from shared.database.session import get_db
from servers.api.auth import get_current_user_id
from servers.api.shares import share_router


@pytest.fixture
def test_user(test_db):
    return test_db.query(User).first()


def _make_client(test_db, user_id):
    app = FastAPI()
    app.include_router(share_router, prefix="/api/v1")

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = lambda: str(user_id)
    return TestClient(app)


@pytest.fixture
def client(test_db, test_user):
    return _make_client(test_db, test_user.id)


def _user(db, email):
    user = User(
        id=uuid4(),
        email=email,
        display_name=email.split("@")[0],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    return user


def _instance(db, user, *, status=AgentStatus.ACTIVE, project=None):
    agent_type = db.query(AgentType).filter(AgentType.user_id == user.id).first()
    if agent_type is None:
        agent_type = AgentType(user_id=user.id, name="claude", is_active=True)
        db.add(agent_type)
        db.flush()
    instance = AgentInstance(
        agent_type_id=agent_type.id,
        user_id=user.id,
        status=status,
        name="Fix the build",
        project_id=project.id if project is not None else None,
    )
    db.add(instance)
    db.commit()
    return instance


def _session_body(instance, **extra):
    return {"kind": "session", "agent_instance_id": str(instance.id), **extra}


class TestCreate:
    def test_owner_mints_a_session_link(self, client, test_db, test_user):
        instance = _instance(test_db, test_user)
        resp = client.post("/api/v1/shares", json=_session_body(instance))
        assert resp.status_code == 201, resp.text
        link = resp.json()
        assert link["kind"] == "session"
        assert link["agent_instance_id"] == str(instance.id)
        assert link["audience"] == "public"
        assert link["show_owner"] is False and link["show_branch"] is False
        assert link["expires_at"] is None
        assert len(link["token"]) > 20

    def test_options_round_trip(self, client, test_db, test_user):
        instance = _instance(test_db, test_user)
        link = client.post(
            "/api/v1/shares",
            json=_session_body(
                instance,
                audience="authenticated",
                show_owner=True,
                show_branch=True,
                expires_in_days=7,
            ),
        ).json()
        assert link["audience"] == "authenticated"
        assert link["show_owner"] is True and link["show_branch"] is True
        assert link["expires_at"] is not None

    def test_someone_elses_session_is_404(self, client, test_db):
        other = _user(test_db, "other@example.com")
        theirs = _instance(test_db, other)
        resp = client.post("/api/v1/shares", json=_session_body(theirs))
        assert resp.status_code == 404

    def test_a_granted_session_is_still_404_here(self, test_db, test_user):
        """The dashboard would let an `admin` grantee mint a link; the API-key
        surface stays owner-only, so a grant buys nothing here."""
        owner = _user(test_db, "owner@example.com")
        project = Project(user_id=owner.id, name="Theirs")
        test_db.add(project)
        test_db.flush()
        test_db.add(
            ProjectGrant(
                project_id=project.id,
                principal_type="user",
                principal_id=test_user.id,
                role="admin",
                scopes=["sessions", "tasks"],
                granted_by_user_id=owner.id,
            )
        )
        test_db.commit()
        theirs = _instance(test_db, owner, project=project)
        grantee = _make_client(test_db, test_user.id)
        resp = grantee.post("/api/v1/shares", json=_session_body(theirs))
        assert resp.status_code == 404

    def test_deleted_session_is_404(self, client, test_db, test_user):
        gone = _instance(test_db, test_user, status=AgentStatus.DELETED)
        assert (
            client.post("/api/v1/shares", json=_session_body(gone)).status_code == 404
        )

    def test_project_link_needs_a_personal_project_of_the_caller(
        self, client, test_db, test_user
    ):
        mine = Project(user_id=test_user.id, name="Mine")
        test_db.add(mine)
        test_db.commit()
        resp = client.post(
            "/api/v1/shares",
            json={"kind": "project", "project_id": str(mine.id), "scopes": ["tasks"]},
        )
        assert resp.status_code == 201, resp.text
        resp = client.post(
            "/api/v1/shares",
            json={"kind": "project", "project_id": str(uuid4()), "scopes": ["tasks"]},
        )
        assert resp.status_code == 404


class TestListAndRevoke:
    def test_list_shows_live_links_newest_first(self, client, test_db, test_user):
        instance = _instance(test_db, test_user)
        first = client.post("/api/v1/shares", json=_session_body(instance)).json()
        second = client.post(
            "/api/v1/shares", json=_session_body(instance, show_branch=True)
        ).json()
        rows = client.get(
            "/api/v1/shares", params={"agent_instance_id": str(instance.id)}
        ).json()
        assert [row["id"] for row in rows] == [second["id"], first["id"]]

    def test_list_needs_exactly_one_target(self, client):
        assert client.get("/api/v1/shares").status_code == 400

    def test_list_on_someone_elses_session_is_404(self, client, test_db):
        other = _user(test_db, "other@example.com")
        theirs = _instance(test_db, other)
        resp = client.get(
            "/api/v1/shares", params={"agent_instance_id": str(theirs.id)}
        )
        assert resp.status_code == 404

    def test_revoke_drops_the_link_from_the_list(self, client, test_db, test_user):
        instance = _instance(test_db, test_user)
        link = client.post("/api/v1/shares", json=_session_body(instance)).json()
        assert client.delete(f"/api/v1/shares/{link['id']}").status_code == 204
        rows = client.get(
            "/api/v1/shares", params={"agent_instance_id": str(instance.id)}
        ).json()
        assert rows == []
        # The row stays for audit, revoked.
        assert test_db.get(ShareLink, link["id"]).revoked_at is not None
        # Idempotent.
        assert client.delete(f"/api/v1/shares/{link['id']}").status_code == 204

    def test_revoking_someone_elses_link_is_404(self, client, test_db):
        other = _user(test_db, "other@example.com")
        theirs = _instance(test_db, other)
        link = (
            _make_client(test_db, other.id)
            .post("/api/v1/shares", json=_session_body(theirs))
            .json()
        )
        assert client.delete(f"/api/v1/shares/{link['id']}").status_code == 404
        assert test_db.get(ShareLink, link["id"]).revoked_at is None

    def test_unknown_link_is_404(self, client):
        assert client.delete(f"/api/v1/shares/{uuid4()}").status_code == 404
