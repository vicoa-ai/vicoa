"""People sharing (collaboration P5): project grants over REST, team shares of
one session, invite-before-signup claims, seat accounting, and what someone a
session was shared with may see of it.

The role floors themselves live in `test_authz_matrix.py`; this module covers
the behaviour a floor cannot express — list shapes, 409s, the seat context the
overlay prices, and the grantee redaction.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.auth.dependencies import (
    get_current_claims,
    get_current_user,
    get_optional_current_user,
)
from backend.db import collab_queries
from backend.main import app
from shared import access, hooks
from shared.auth.tokens import TokenClaims
from shared.database import (
    AgentInstance,
    AgentType,
    Machine,
    Message,
    Project,
    ProjectDirectory,
    ProjectGrant,
    SenderType,
    Team,
    TeamInstanceAccess,
    TeamMember,
    User,
    UserInstanceAccess,
)
from shared.database.enums import AgentStatus, InstanceAccessLevel


def _user(db, email: str, name: str | None = None) -> User:
    user = User(
        id=uuid4(),
        email=email,
        display_name=name or email.split("@")[0].title(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    return user


def _team(db, name: str, *members: tuple[User, str, str]) -> Team:
    team = Team(name=name, slug=f"{name.lower()}-{uuid4().hex[:6]}")
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


def _grant(
    db,
    project: Project,
    principal_id: UUID | None,
    role: str,
    *,
    principal_type: str = "user",
    email: str | None = None,
    scopes: list[str] | None = None,
) -> ProjectGrant:
    grant = ProjectGrant(
        project_id=project.id,
        principal_type=principal_type,
        principal_id=principal_id,
        invited_email=email,
        role=role,
        scopes=scopes or ["tasks", "sessions"],
    )
    db.add(grant)
    db.commit()
    return grant


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
    machine = Machine(user_id=owner.id, display_name="laptop", hostname="laptop.local")
    test_db.add(machine)
    test_db.flush()
    instance = AgentInstance(
        agent_type_id=agent_type.id,
        user_id=owner.id,
        project_id=project.id,
        project="/home/nick/alpha",
        home_dir="/home/nick",
        machine_id=machine.id,
        status=AgentStatus.ACTIVE,
        started_at=datetime.now(timezone.utc),
        instance_metadata={
            "worktree_name": "feature",
            "repo_root": "/home/nick/alpha",
            "source": "desktop",
        },
        session_config={"agent": "claude", "model": "opus", "env": {"TOKEN": "x"}},
    )
    test_db.add(instance)
    test_db.commit()
    return instance


@pytest.fixture
def as_user(client) -> Iterator[Callable[[User], TestClient]]:
    """`as_user(u)` → the shared client, now authenticated as `u`."""

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
def seat_calls(monkeypatch) -> list[tuple[UUID, str, dict]]:
    """Record every capability check; allow all of them."""
    calls: list[tuple[UUID, str, dict]] = []

    def hook(db, user_id, capability, context):
        del db
        calls.append((user_id, capability, dict(context)))
        return None

    monkeypatch.setattr(hooks, "_capability_hooks", [hook])
    return calls


# --- People list --------------------------------------------------------------


class TestPeopleList:
    def test_owner_row_then_grants_with_emails_beside_principals(
        self, test_db, as_user, owner, other, project
    ):
        crew = _team(
            test_db, "Crew", (owner, "owner", "active"), (other, "member", "active")
        )
        _grant(test_db, project, other.id, "editor")
        _grant(test_db, project, None, "viewer", email="later@example.com")
        _grant(test_db, project, crew.id, "commenter", principal_type="team")

        response = as_user(owner).get(f"/api/v1/projects/{project.id}/grants")
        assert response.status_code == 200, response.text
        rows = response.json()

        assert rows[0]["is_owner"] and rows[0]["role"] == "owner"
        assert rows[0]["is_self"] is True
        assert rows[0]["email"] == owner.email
        assert rows[0]["id"] is None

        person, pending, team = rows[1:]
        assert person["principal"] == {
            "type": "user",
            "id": str(other.id),
            "name": "Other",
            "avatar_image_uri": None,
            "emoji": None,
            "updated_at": person["principal"]["updated_at"],
        }
        # The address rides beside the principal, never inside it (§10.4).
        assert person["email"] == other.email
        assert "email" not in person["principal"]
        assert pending["pending"] is True and pending["email"] == "later@example.com"
        assert pending["principal"]["id"] is None
        assert team["principal"]["type"] == "team"
        assert team["member_count"] == 2 and team["email"] is None

    def test_a_viewer_cannot_list(self, test_db, as_user, other, project):
        _grant(test_db, project, other.id, "viewer")
        response = as_user(other).get(f"/api/v1/projects/{project.id}/grants")
        assert response.status_code == 403


# --- Writing grants -----------------------------------------------------------


class TestGrantWrites:
    def test_email_of_an_existing_account_attaches_immediately(
        self, as_user, owner, other, project
    ):
        response = as_user(owner).post(
            f"/api/v1/projects/{project.id}/grants",
            json={
                "email": " Other@Example.com ",
                "role": "commenter",
                "scopes": ["tasks"],
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["principal"]["id"] == str(other.id)
        assert body["pending"] is False
        assert body["scopes"] == ["tasks"]
        # No mail transport in tests ⇒ the dialog must say so.
        assert body["email_sent"] is False

    def test_duplicate_is_409_and_owner_is_400(
        self, test_db, as_user, owner, other, project
    ):
        _grant(test_db, project, other.id, "viewer")
        client = as_user(owner)
        dup = client.post(
            f"/api/v1/projects/{project.id}/grants",
            json={"email": other.email, "role": "editor"},
        )
        assert dup.status_code == 409
        self_grant = client.post(
            f"/api/v1/projects/{project.id}/grants",
            json={"email": owner.email, "role": "viewer"},
        )
        assert self_grant.status_code == 400

    def test_exactly_one_principal(self, as_user, owner, project):
        both = as_user(owner).post(
            f"/api/v1/projects/{project.id}/grants",
            json={"email": "a@example.com", "team_id": str(uuid4()), "role": "viewer"},
        )
        assert both.status_code == 422

    def test_team_must_be_one_the_granter_is_in(
        self, test_db, as_user, owner, other, project
    ):
        theirs = _team(test_db, "Theirs", (other, "owner", "active"))
        response = as_user(owner).post(
            f"/api/v1/projects/{project.id}/grants",
            json={"team_id": str(theirs.id), "role": "viewer"},
        )
        assert response.status_code == 400

    def test_patch_role_and_scopes(self, test_db, as_user, owner, other, project):
        grant = _grant(test_db, project, other.id, "viewer")
        response = as_user(owner).patch(
            f"/api/v1/projects/{project.id}/grants/{grant.id}",
            json={"role": "editor", "scopes": ["sessions", "tasks"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["role"] == "editor"
        # Stored in canonical order whatever the request's order was.
        assert response.json()["scopes"] == ["tasks", "sessions"]
        assert access.project_role(test_db, other.id, project) == "editor"

    def test_patch_unknown_grant_is_404(self, as_user, owner, project):
        response = as_user(owner).patch(
            f"/api/v1/projects/{project.id}/grants/{uuid4()}", json={"role": "viewer"}
        )
        assert response.status_code == 404

    def test_delete(self, test_db, as_user, owner, other, project):
        grant = _grant(test_db, project, other.id, "viewer")
        client = as_user(owner)
        assert (
            client.delete(
                f"/api/v1/projects/{project.id}/grants/{grant.id}"
            ).status_code
            == 204
        )
        assert access.project_role(test_db, other.id, project) is None
        assert (
            client.delete(
                f"/api/v1/projects/{project.id}/grants/{grant.id}"
            ).status_code
            == 404
        )


class TestLeave:
    def test_a_direct_grantee_leaves(self, test_db, as_user, other, project):
        _grant(test_db, project, other.id, "viewer")
        client = as_user(other)
        assert client.post(f"/api/v1/projects/{project.id}/leave").status_code == 204
        ids = {p["id"] for p in client.get("/api/v1/projects").json()}
        assert str(project.id) not in ids

    def test_owner_and_team_standing_cannot_leave(
        self, test_db, as_user, owner, other, project
    ):
        assert (
            as_user(owner).post(f"/api/v1/projects/{project.id}/leave").status_code
            == 409
        )
        crew = _team(
            test_db, "Crew", (owner, "owner", "active"), (other, "member", "active")
        )
        _grant(test_db, project, crew.id, "viewer", principal_type="team")
        assert (
            as_user(other).post(f"/api/v1/projects/{project.id}/leave").status_code
            == 409
        )

    def test_a_stranger_gets_404(self, test_db, as_user, project):
        stranger = _user(test_db, "stranger@example.com")
        assert (
            as_user(stranger).post(f"/api/v1/projects/{project.id}/leave").status_code
            == 404
        )


# --- Invite before signup -----------------------------------------------------


class TestClaimPendingInvites:
    def test_grants_and_session_shares_attach(self, test_db, owner, project, instance):
        _grant(test_db, project, None, "viewer", email="later@example.com")
        test_db.add(
            UserInstanceAccess(
                agent_instance_id=instance.id,
                shared_email="Later@Example.com",
                access=InstanceAccessLevel.READ,
                granted_by_user_id=owner.id,
            )
        )
        test_db.commit()
        newcomer = _user(test_db, "later@example.com")

        assert collab_queries.claim_pending_invites(test_db, newcomer) == 2
        assert access.project_role(test_db, newcomer.id, project) == "viewer"
        share = test_db.query(UserInstanceAccess).one()
        assert share.user_id == newcomer.id
        # Idempotent.
        assert collab_queries.claim_pending_invites(test_db, newcomer) == 0

    def test_an_explicit_grant_wins_over_a_stale_invite(self, test_db, other, project):
        _grant(test_db, project, other.id, "editor")
        _grant(test_db, project, None, "viewer", email="OTHER@example.com")
        # The second row's email differs only in case, so it is not blocked
        # by the email uniqueness of the first (that one has no invited_email).
        assert collab_queries.claim_pending_invites(test_db, other) == 0
        rows = test_db.query(ProjectGrant).filter_by(project_id=project.id).all()
        assert [(r.principal_id, r.role) for r in rows] == [(other.id, "editor")]

    def test_blank_email_claims_nothing(self, test_db):
        blank = _user(test_db, "")
        assert collab_queries.claim_pending_invites(test_db, blank) == 0

    def test_the_invitations_endpoint_claims(self, test_db, as_user, project):
        _grant(test_db, project, None, "commenter", email="webhook@example.com")
        # An account created by a path that skipped the signup hook.
        webhook_made = _user(test_db, "webhook@example.com")
        assert as_user(webhook_made).get("/api/v1/teams/invitations").status_code == 200
        assert access.project_role(test_db, webhook_made.id, project) == "commenter"


# --- Seats --------------------------------------------------------------------


class TestSeats:
    def test_seat_keys_count_members_and_outside_editors_only(
        self, test_db, owner, other, project, instance
    ):
        editor = _user(test_db, "editor@example.com")
        viewer = _user(test_db, "viewer@example.com")
        writer = _user(test_db, "writer@example.com")
        reader = _user(test_db, "reader@example.com")
        crew = _team(
            test_db,
            "Crew",
            (owner, "owner", "active"),
            (other, "member", "invited"),
        )
        removed = _user(test_db, "removed@example.com")
        test_db.add(
            TeamMember(
                team_id=crew.id,
                user_id=removed.id,
                role="member",
                status="removed",
            )
        )
        _grant(test_db, project, editor.id, "editor")
        _grant(test_db, project, viewer.id, "viewer")
        _grant(test_db, project, None, "admin", email="Pending@Example.com")
        # Already a member: one person, one seat.
        _grant(test_db, project, other.id, "admin", email=None)
        _grant(test_db, project, crew.id, "editor", principal_type="team")
        for user, level in (
            (writer, InstanceAccessLevel.WRITE),
            (reader, InstanceAccessLevel.READ),
        ):
            test_db.add(
                UserInstanceAccess(
                    agent_instance_id=instance.id,
                    shared_email=user.email,
                    user_id=user.id,
                    access=level,
                    granted_by_user_id=owner.id,
                )
            )
        test_db.commit()

        assert collab_queries.seat_keys(test_db, owner.id) == {
            f"user:{owner.id}",
            f"user:{other.id}",
            f"user:{editor.id}",
            "email:pending@example.com",
            f"user:{writer.id}",
        }

    def test_editor_grant_reports_the_seat_it_would_add(
        self, as_user, owner, other, project, seat_calls
    ):
        response = as_user(owner).post(
            f"/api/v1/projects/{project.id}/grants",
            json={"email": other.email, "role": "editor"},
        )
        assert response.status_code == 201, response.text
        ((payer, capability, context),) = seat_calls
        assert payer == owner.id
        assert capability == hooks.CAPABILITY_GRANT_WRITE
        assert context["seats"] == 2 and context["new_seat"] is True

    def test_viewer_grant_never_asks(self, as_user, owner, other, project, seat_calls):
        as_user(owner).post(
            f"/api/v1/projects/{project.id}/grants",
            json={"email": other.email, "role": "viewer"},
        )
        assert seat_calls == []

    def test_promotion_asks_once_and_a_scope_change_never(
        self, test_db, as_user, owner, other, project, seat_calls
    ):
        grant = _grant(test_db, project, other.id, "viewer")
        client = as_user(owner)
        url = f"/api/v1/projects/{project.id}/grants/{grant.id}"
        client.patch(url, json={"role": "editor"})
        client.patch(url, json={"role": "admin"})
        client.patch(url, json={"scopes": ["tasks"]})
        assert [c[1] for c in seat_calls] == [hooks.CAPABILITY_GRANT_WRITE]

    def test_a_denial_is_402_with_the_capability(
        self, as_user, owner, other, project, monkeypatch
    ):
        monkeypatch.setattr(
            hooks, "_capability_hooks", [lambda db, u, cap, ctx: "Seat limit reached"]
        )
        response = as_user(owner).post(
            f"/api/v1/projects/{project.id}/grants",
            json={"email": other.email, "role": "editor"},
        )
        assert response.status_code == 402
        assert response.json() == {
            "detail": "Seat limit reached",
            "capability": hooks.CAPABILITY_GRANT_WRITE,
        }

    def test_write_session_share_is_metered_read_is_not(
        self, as_user, owner, other, instance, seat_calls
    ):
        client = as_user(owner)
        url = f"/api/v1/agent-instances/{instance.id}/access"
        read = client.post(url, json={"email": other.email, "access": "READ"})
        assert read.status_code == 200, read.text
        assert seat_calls == []
        client.patch(f"{url}/{read.json()['id']}", json={"access": "WRITE"})
        ((payer, capability, context),) = seat_calls
        assert payer == owner.id and capability == hooks.CAPABILITY_GRANT_WRITE
        assert context["new_seat"] is True


# --- Team shares of one session -----------------------------------------------


class TestTeamSessionShares:
    def test_share_with_a_team_reaches_its_active_members(
        self, test_db, as_user, owner, other, instance
    ):
        crew = _team(
            test_db, "Crew", (owner, "owner", "active"), (other, "member", "active")
        )
        client = as_user(owner)
        response = client.post(
            f"/api/v1/agent-instances/{instance.id}/access",
            json={"team_id": str(crew.id), "access": "READ"},
        )
        assert response.status_code == 200, response.text
        row = response.json()
        assert row["principal_type"] == "team"
        assert row["team_id"] == str(crew.id)
        assert row["member_count"] == 2
        assert access.instance_role(test_db, other.id, instance) == "viewer"

        listed = client.get(f"/api/v1/agent-instances/{instance.id}/access").json()
        assert [r["principal_type"] for r in listed] == ["user", "team"]
        assert listed[0]["is_owner"] is True

        update = client.patch(
            f"/api/v1/agent-instances/{instance.id}/access/{row['id']}",
            json={"access": "WRITE"},
        )
        assert update.json()["access"] == "WRITE"
        assert access.instance_role(test_db, other.id, instance) == "editor"

        assert (
            client.delete(
                f"/api/v1/agent-instances/{instance.id}/access/{row['id']}"
            ).status_code
            == 200
        )
        assert test_db.query(TeamInstanceAccess).count() == 0
        assert access.instance_role(test_db, other.id, instance) is None

    def test_a_team_the_caller_is_not_in_is_404(
        self, test_db, as_user, owner, other, instance
    ):
        theirs = _team(test_db, "Theirs", (other, "owner", "active"))
        response = as_user(owner).post(
            f"/api/v1/agent-instances/{instance.id}/access",
            json={"team_id": str(theirs.id)},
        )
        assert response.status_code == 404

    def test_blank_email_is_rejected(self, as_user, owner, instance):
        response = as_user(owner).post(
            f"/api/v1/agent-instances/{instance.id}/access", json={"email": "   "}
        )
        assert response.status_code == 422


# --- What a grantee sees ------------------------------------------------------


class TestGranteeView:
    def test_shared_list_is_redacted_and_names_the_owner(
        self, test_db, as_user, owner, other, project, instance
    ):
        _grant(test_db, project, other.id, "viewer", scopes=["sessions"])
        response = as_user(other).get("/api/v1/agent-instances?scope=shared")
        assert response.status_code == 200, response.text
        (row,) = response.json()["items"]
        assert row["owner"]["id"] == str(owner.id)
        assert row["owner"]["name"] == owner.display_name
        assert row["viewer_role"] == "viewer"
        assert row["home_dir"] is None and row["machine_id"] is None
        assert row["project"] == "alpha"
        assert row["instance_metadata"] == {
            "worktree_name": "feature",
            "source": "desktop",
        }
        assert row["session_config"] == {"agent": "claude", "model": "opus"}
        assert row["worktree_name"] == "feature"

    def test_own_rows_are_untouched(self, as_user, owner, instance):
        (row,) = as_user(owner).get("/api/v1/agent-instances?scope=all").json()["items"]
        assert row["owner"] is None and row["viewer_role"] is None
        assert row["home_dir"] == "/home/nick"
        assert row["instance_metadata"]["repo_root"] == "/home/nick/alpha"

    def test_detail_and_messages_hide_emails_from_grantees(
        self, test_db, as_user, owner, other, project, instance
    ):
        _grant(test_db, project, other.id, "viewer")
        base = datetime.now(timezone.utc)
        messages = []
        for n in range(3):
            message = Message(
                agent_instance_id=instance.id,
                sender_type=SenderType.USER,
                sender_user_id=owner.id,
                content=f"m{n}",
                requires_user_input=False,
                created_at=base + timedelta(seconds=n),
            )
            test_db.add(message)
            messages.append(message)
        test_db.commit()

        detail = as_user(other).get(f"/api/v1/agent-instances/{instance.id}").json()
        assert detail["is_owner"] is False
        assert detail["owner"]["id"] == str(owner.id)
        assert detail["machine_id"] is None and detail["home_dir"] is None
        assert {m["sender_user_email"] for m in detail["messages"]} == {None}
        assert {m["sender_user_display_name"] for m in detail["messages"]} == {
            owner.display_name
        }

        newer = (
            as_user(other)
            .get(
                f"/api/v1/agent-instances/{instance.id}/messages",
                params={"after_message_id": str(messages[0].id)},
            )
            .json()
        )
        assert [m["content"] for m in newer] == ["m1", "m2"]
        assert {m["sender_user_email"] for m in newer} == {None}

        own = as_user(owner).get(f"/api/v1/agent-instances/{instance.id}").json()
        assert {m["sender_user_email"] for m in own["messages"]} == {owner.email}

    def test_project_response_names_the_owner_and_hides_their_directories(
        self, test_db, as_user, owner, other, project
    ):
        owner_box = Machine(user_id=owner.id, display_name="owner-box", hostname="o")
        other_box = Machine(user_id=other.id, display_name="other-box", hostname="t")
        test_db.add_all([owner_box, other_box])
        test_db.flush()
        test_db.add_all(
            [
                ProjectDirectory(
                    project_id=project.id,
                    user_id=owner.id,
                    machine_id=owner_box.id,
                    local_path="/home/nick/alpha",
                ),
                ProjectDirectory(
                    project_id=project.id,
                    user_id=other.id,
                    machine_id=other_box.id,
                    local_path="/src/alpha",
                ),
            ]
        )
        _grant(test_db, project, other.id, "editor")

        mine = next(
            p
            for p in as_user(other).get("/api/v1/projects").json()
            if p["id"] == str(project.id)
        )
        assert mine["owner"]["id"] == str(owner.id)
        assert mine["role"] == "editor"
        assert [d["local_path"] for d in mine["directories"]] == ["/src/alpha"]

        theirs = next(
            p
            for p in as_user(owner).get("/api/v1/projects").json()
            if p["id"] == str(project.id)
        )
        assert theirs["owner"] is None
        assert [d["local_path"] for d in theirs["directories"]] == ["/home/nick/alpha"]


# --- Team invite email --------------------------------------------------------


class TestTeamInviteEmail:
    def test_no_transport_says_so_and_hands_back_the_page(
        self, test_db, as_user, owner
    ):
        crew = _team(test_db, "Crew", (owner, "owner", "active"))
        response = as_user(owner).post(
            f"/api/v1/teams/{crew.id}/members", json={"email": "new@example.com"}
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["email_sent"] is False
        assert body["join_url"].endswith("/dashboard/settings?tab=teams")

    def test_with_transport_the_invite_is_mailed(
        self, test_db, as_user, owner, monkeypatch
    ):
        sent: list[tuple] = []

        async def fake_send(*args):
            sent.append(args)
            return True

        monkeypatch.setattr("backend.api.teams.email_is_configured", lambda: True)
        monkeypatch.setattr("backend.api.teams.send_team_invite_email", fake_send)
        crew = _team(test_db, "Crew", (owner, "owner", "active"))
        response = as_user(owner).post(
            f"/api/v1/teams/{crew.id}/members",
            json={"email": "new@example.com", "role": "admin"},
        )
        assert response.json()["email_sent"] is True
        ((to, inviter, team_name, role, url),) = sent
        assert (to, inviter, team_name, role) == (
            "new@example.com",
            owner.display_name,
            "Crew",
            "admin",
        )
        assert url.endswith("/dashboard/settings?tab=teams")

    def test_project_grant_is_mailed_too(self, as_user, owner, project, monkeypatch):
        sent: list[tuple] = []

        async def fake_send(*args):
            sent.append(args)
            return True

        monkeypatch.setattr(
            "backend.api.project_grants.email_is_configured", lambda: True
        )
        monkeypatch.setattr(
            "backend.api.project_grants.send_project_invite_email", fake_send
        )
        response = as_user(owner).post(
            f"/api/v1/projects/{project.id}/grants",
            json={"email": "fresh@example.com", "role": "viewer"},
        )
        assert response.json()["email_sent"] is True
        assert sent[0][0] == "fresh@example.com"
        assert sent[0][2] == "alpha"
