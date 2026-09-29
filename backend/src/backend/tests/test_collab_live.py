"""Sharing on the dashboard API: live updates and writing to shared sessions.

* Every change to someone's access — a project grant, a session share, a team
  membership — tells the relay who it affected, once the change commits, so
  their dashboards refetch and their watcher rooms are re-checked.
* The session detail names its participants (owner + everyone who wrote), the
  input to the avatar stack and "Prompted by".
* A grantee's detail carries no `git_diff`: the Files/Git panel is owner-only.
* A grantee can follow a shared project into their own project list.

Role floors live in `test_authz_matrix.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.auth.dependencies import (
    get_current_claims,
    get_current_user,
    get_optional_current_user,
)
from backend.main import app
from shared import access
from shared.auth.tokens import TokenClaims
from shared.database import (
    AgentInstance,
    AgentType,
    Project,
    ProjectGrant,
    Team,
    TeamMember,
    User,
    UserInstanceAccess,
)
from shared.database.enums import AgentStatus, InstanceAccessLevel


def _user(db, email: str, name: str) -> User:
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(), email=email, display_name=name, created_at=now, updated_at=now
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def owner(test_user) -> User:
    return test_user


@pytest.fixture
def other(test_db) -> User:
    return _user(test_db, "other@example.com", "Other")


@pytest.fixture
def project(test_db, owner) -> Project:
    project = Project(user_id=owner.id, name="alpha", key="ALP")
    test_db.add(project)
    test_db.commit()
    return project


@pytest.fixture
def instance(test_db, owner, project) -> AgentInstance:
    agent_type = AgentType(user_id=owner.id, name="claude code", is_active=True)
    test_db.add(agent_type)
    test_db.flush()
    instance = AgentInstance(
        agent_type_id=agent_type.id,
        user_id=owner.id,
        project_id=project.id,
        project="/home/owner/alpha",
        status=AgentStatus.ACTIVE,
        started_at=datetime.now(timezone.utc),
        git_diff=(
            "diff --git a/secret.txt b/secret.txt\n"
            "index 1234567..89abcde 100644\n"
            "--- a/secret.txt\n+++ b/secret.txt\n@@ -1 +1 @@\n-old\n+new\n"
        ),
    )
    test_db.add(instance)
    test_db.commit()
    return instance


@pytest.fixture
def as_user(client) -> Iterator[Callable[[User], TestClient]]:
    def switch(user: User) -> TestClient:
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_optional_current_user] = lambda: user
        app.dependency_overrides[get_current_claims] = lambda: TokenClaims(
            user_id=user.id, email=user.email, display_name=user.display_name
        )
        return client

    yield switch
    for dep in (get_current_user, get_optional_current_user, get_current_claims):
        app.dependency_overrides.pop(dep, None)


@pytest.fixture
def relay(monkeypatch) -> list[dict]:
    """Every access-changed notification that would reach the relay."""
    calls: list[dict] = []

    def record(user_ids, *, project_id=None, instance_id=None):
        calls.append(
            {
                "user_ids": set(user_ids),
                "project_id": project_id,
                "instance_id": instance_id,
            }
        )

    monkeypatch.setattr("backend.db.access_events.post_access_changed", record)
    monkeypatch.setattr("backend.api.agents.post_broadcast", lambda *a, **k: None)
    monkeypatch.setattr(
        "backend.api.agents.update_session_title_if_needed", lambda **k: None
    )
    return calls


def _team(db, *members: tuple[User, str, str]) -> Team:
    team = Team(name="Crew", slug=f"crew-{uuid4().hex[:6]}")
    db.add(team)
    db.flush()
    for user, role, status in members:
        db.add(
            TeamMember(
                team_id=team.id,
                user_id=user.id,
                invited_email=user.email,
                role=role,
                status=status,
            )
        )
    db.commit()
    return team


# --- grant-change liveness ------------------------------------------------------


class TestAccessChangesReachTheRelay:
    def test_project_grant_lifecycle(self, as_user, owner, other, project, relay):
        client = as_user(owner)
        created = client.post(
            f"/api/v1/projects/{project.id}/grants",
            json={"email": other.email, "role": "viewer"},
        )
        assert created.status_code == 201, created.text
        grant_id = created.json()["id"]
        client.patch(
            f"/api/v1/projects/{project.id}/grants/{grant_id}",
            json={"role": "editor"},
        )
        client.delete(f"/api/v1/projects/{project.id}/grants/{grant_id}")

        expected = {"user_ids": {str(other.id)}, "project_id": str(project.id)}
        assert len(relay) == 3
        for call in relay:
            assert call["user_ids"] == expected["user_ids"]
            assert call["project_id"] == expected["project_id"]

    def test_a_pending_invite_tells_nobody(self, as_user, owner, project, relay):
        response = as_user(owner).post(
            f"/api/v1/projects/{project.id}/grants",
            json={"email": "not-yet@example.com", "role": "viewer"},
        )
        assert response.status_code == 201
        assert relay == []

    def test_a_team_grant_reaches_its_active_members_only(
        self, test_db, as_user, owner, other, project, relay
    ):
        invited = _user(test_db, "invited@example.com", "Invited")
        team = _team(
            test_db,
            (owner, "owner", "active"),
            (other, "member", "active"),
            (invited, "member", "invited"),
        )
        response = as_user(owner).post(
            f"/api/v1/projects/{project.id}/grants",
            json={"team_id": str(team.id), "role": "viewer"},
        )
        assert response.status_code == 201, response.text
        [call] = relay
        assert call["user_ids"] == {str(owner.id), str(other.id)}

    def test_a_failed_write_tells_nobody(
        self, test_db, as_user, owner, other, project, relay
    ):
        test_db.add(
            ProjectGrant(
                project_id=project.id,
                principal_type="user",
                principal_id=other.id,
                role="viewer",
                scopes=["tasks", "sessions"],
            )
        )
        test_db.commit()
        duplicate = as_user(owner).post(
            f"/api/v1/projects/{project.id}/grants",
            json={"email": other.email, "role": "editor"},
        )
        assert duplicate.status_code == 409
        assert relay == []

    def test_leaving(self, test_db, as_user, other, project, relay):
        test_db.add(
            ProjectGrant(
                project_id=project.id,
                principal_type="user",
                principal_id=other.id,
                role="viewer",
                scopes=["sessions"],
            )
        )
        test_db.commit()
        assert (
            as_user(other).post(f"/api/v1/projects/{project.id}/leave").status_code
            == 204
        )
        assert relay == [
            {
                "user_ids": {str(other.id)},
                "project_id": str(project.id),
                "instance_id": None,
            }
        ]

    def test_session_share_lifecycle(self, as_user, owner, other, instance, relay):
        client = as_user(owner)
        created = client.post(
            f"/api/v1/agent-instances/{instance.id}/access",
            json={"email": other.email, "access": "READ"},
        )
        assert created.status_code == 200, created.text
        access_id = created.json()["id"]
        client.patch(
            f"/api/v1/agent-instances/{instance.id}/access/{access_id}",
            json={"access": "WRITE"},
        )
        client.delete(f"/api/v1/agent-instances/{instance.id}/access/{access_id}")

        assert len(relay) == 3
        for call in relay:
            assert call["user_ids"] == {str(other.id)}
            assert call["instance_id"] == str(instance.id)

    def test_team_membership(self, test_db, as_user, owner, other, relay):
        team = _team(test_db, (owner, "owner", "active"), (other, "member", "active"))
        member = (
            test_db.query(TeamMember)
            .filter(TeamMember.team_id == team.id, TeamMember.user_id == other.id)
            .one()
        )
        response = as_user(owner).delete(f"/api/v1/teams/{team.id}/members/{member.id}")
        assert response.status_code == 204, response.text
        assert [c["user_ids"] for c in relay] == [{str(other.id)}]


# --- participants and the grantee view -------------------------------------------


class TestParticipants:
    def test_solo_session_has_only_the_owner(self, as_user, owner, instance):
        detail = as_user(owner).get(f"/api/v1/agent-instances/{instance.id}").json()
        assert [p["id"] for p in detail["participants"]] == [str(owner.id)]

    def test_a_collaborator_who_wrote_joins_the_list(
        self, test_db, as_user, owner, other, instance, relay
    ):
        test_db.add(
            UserInstanceAccess(
                agent_instance_id=instance.id,
                shared_email=other.email,
                user_id=other.id,
                access=InstanceAccessLevel.WRITE,
                granted_by_user_id=owner.id,
            )
        )
        test_db.commit()
        sent = as_user(other).post(
            f"/api/v1/agent-instances/{instance.id}/messages",
            json={"content": "hello from other"},
        )
        assert sent.status_code == 200, sent.text
        assert (
            as_user(owner)
            .post(
                f"/api/v1/agent-instances/{instance.id}/messages",
                json={"content": "and from the owner"},
            )
            .status_code
            == 200
        )

        for viewer in (owner, other):
            detail = (
                as_user(viewer).get(f"/api/v1/agent-instances/{instance.id}").json()
            )
            people = detail["participants"]
            assert [p["id"] for p in people] == [str(owner.id), str(other.id)]
            assert [p["name"] for p in people] == ["Test User", "Other"]
            # A principal never carries an address (§10.4).
            assert all("email" not in p for p in people)

    def test_list_rows_name_participants_only_once_someone_else_wrote(
        self, test_db, as_user, owner, other, instance, relay
    ):
        def row(viewer: User, scope: str) -> dict:
            items = (
                as_user(viewer)
                .get("/api/v1/agent-instances", params={"scope": scope})
                .json()
            )
            items = items["items"] if isinstance(items, dict) else items
            [found] = [i for i in items if i["id"] == str(instance.id)]
            return found

        test_db.add(
            UserInstanceAccess(
                agent_instance_id=instance.id,
                shared_email=other.email,
                user_id=other.id,
                access=InstanceAccessLevel.WRITE,
                granted_by_user_id=owner.id,
            )
        )
        test_db.commit()
        # The owner's own messages keep the row solo: nothing new to draw.
        as_user(owner).post(
            f"/api/v1/agent-instances/{instance.id}/messages",
            json={"content": "from the owner"},
        )
        assert row(owner, "me")["participants"] == []
        assert row(other, "shared")["participants"] == []

        as_user(other).post(
            f"/api/v1/agent-instances/{instance.id}/messages",
            json={"content": "from other"},
        )
        for viewer, scope in ((owner, "me"), (other, "shared"), (other, "all")):
            people = row(viewer, scope)["participants"]
            assert [p["id"] for p in people] == [str(owner.id), str(other.id)]
            assert all("email" not in p for p in people)

    def test_the_grantee_detail_has_no_git_diff(
        self, test_db, as_user, owner, other, instance
    ):
        test_db.add(
            UserInstanceAccess(
                agent_instance_id=instance.id,
                shared_email=other.email,
                user_id=other.id,
                access=InstanceAccessLevel.READ,
                granted_by_user_id=owner.id,
            )
        )
        test_db.commit()
        mine = as_user(owner).get(f"/api/v1/agent-instances/{instance.id}").json()
        theirs = as_user(other).get(f"/api/v1/agent-instances/{instance.id}").json()
        assert mine["git_diff"]
        assert theirs["git_diff"] is None
        assert theirs["viewer_role"] == "viewer"


# --- collaborators' sessions in a project you own ---------------------------------


class TestCollaboratorsInYourProject:
    """A collaborator who starts a session in your project (the matcher files
    it there by remote) is visible to you — it is what the sidebar's Team row
    lists under that project — and you are its admin, never its owner."""

    @pytest.fixture
    def theirs(self, test_db, other, project) -> AgentInstance:
        test_db.add(
            ProjectGrant(
                project_id=project.id,
                principal_type="user",
                principal_id=other.id,
                role="editor",
                scopes=["sessions"],
            )
        )
        agent_type = AgentType(user_id=other.id, name="claude code", is_active=True)
        test_db.add(agent_type)
        test_db.flush()
        instance = AgentInstance(
            agent_type_id=agent_type.id,
            user_id=other.id,
            project_id=project.id,
            project="/home/other/alpha",
            status=AgentStatus.ACTIVE,
            started_at=datetime.now(timezone.utc),
        )
        test_db.add(instance)
        test_db.commit()
        return instance

    @staticmethod
    def _ids(client: TestClient, scope: str) -> dict[str, dict]:
        body = client.get("/api/v1/agent-instances", params={"scope": scope}).json()
        return {row["id"]: row for row in body["items"]}

    def test_the_project_owner_lists_it_as_someone_elses(
        self, as_user, owner, other, theirs
    ):
        mine = as_user(owner)
        assert str(theirs.id) not in self._ids(mine, "me")
        row = self._ids(mine, "shared")[str(theirs.id)]
        assert row["owner"]["id"] == str(other.id)
        assert row["viewer_role"] == "admin"
        # Still the grantee view: nothing that locates their machine.
        assert row["machine_id"] is None
        assert row["project"] == "alpha"

    def test_owning_the_project_makes_you_admin_not_owner(self, test_db, owner, theirs):
        # The relay keys "already in your own rooms" on 'owner'; a project
        # owner must be able to watch a collaborator's session instead.
        assert access.instance_role(test_db, owner.id, theirs) == "admin"
        assert access.instance_roles(test_db, owner.id, [theirs]) == {
            theirs.id: "admin"
        }


# --- following a shared project ------------------------------------------------


class TestFollow:
    def _share(self, test_db, project: Project, user: User, scopes: list[str]) -> None:
        test_db.add(
            ProjectGrant(
                project_id=project.id,
                principal_type="user",
                principal_id=user.id,
                role="viewer",
                scopes=scopes,
            )
        )
        test_db.commit()

    @staticmethod
    def _listed(client: TestClient, project_id: UUID) -> dict:
        [row] = [
            p
            for p in client.get("/api/v1/projects").json()
            if p["id"] == str(project_id)
        ]
        return row

    def test_follow_and_unfollow(self, test_db, as_user, other, project):
        self._share(test_db, project, other, ["sessions"])
        client = as_user(other)
        assert self._listed(client, project.id)["followed"] is False

        followed = client.put(f"/api/v1/projects/{project.id}/follow")
        assert followed.status_code == 200, followed.text
        assert followed.json()["followed"] is True
        assert self._listed(client, project.id)["followed"] is True
        # Idempotent.
        assert client.put(f"/api/v1/projects/{project.id}/follow").status_code == 200

        unfollowed = client.delete(f"/api/v1/projects/{project.id}/follow")
        assert unfollowed.json()["followed"] is False
        assert self._listed(client, project.id)["followed"] is False

    def test_the_owners_view_is_untouched(
        self, test_db, as_user, owner, other, project
    ):
        self._share(test_db, project, other, ["sessions"])
        as_user(other).put(f"/api/v1/projects/{project.id}/follow")
        mine = as_user(owner)
        assert self._listed(mine, project.id)["followed"] is True
        # An owner's own project is always listed; unfollowing is a no-op.
        assert mine.delete(f"/api/v1/projects/{project.id}/follow").json()["followed"]

    def test_a_stranger_gets_404(self, test_db, as_user, project):
        stranger = _user(test_db, "stranger@example.com", "Stranger")
        assert (
            as_user(stranger).put(f"/api/v1/projects/{project.id}/follow").status_code
            == 404
        )
