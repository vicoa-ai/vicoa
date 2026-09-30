"""Team-owned work (collaboration §3.2, §3.3, §3.6, §6): moving a project into
or out of a team, the key namespace and label vocabulary that follow it, team
avatars, handing a team to a new owner, and team agents."""

from datetime import datetime, timezone
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from PIL import Image

import shared.storage as storage_module
from backend.auth.dependencies import (
    get_current_claims,
    get_current_user,
    get_optional_current_user,
)
from backend.db import task_queries
from backend.main import app
from shared import hooks
from shared.agent_profile_resolution import resolve_automation_config
from shared.auth.tokens import TokenClaims
from shared.database import (
    Machine,
    Project,
    ProjectGrant,
    Task,
    TaskLabel,
    Team,
    TeamMember,
    User,
)
from shared.database.agent_profile_models import AgentProfile
from shared.database.automation_models import Automation


def _user(db, email: str, name: str) -> User:
    user = User(
        id=uuid4(),
        email=email,
        display_name=name,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    return user


_AUTH_DEPS = (get_current_user, get_optional_current_user, get_current_claims)


class _As:
    """Run requests as `user`, then restore the fixture's auth overrides."""

    def __init__(self, user: User):
        self.user = user
        self.saved: dict = {}

    def __enter__(self):
        user = self.user
        self.saved = {dep: app.dependency_overrides.get(dep) for dep in _AUTH_DEPS}
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_optional_current_user] = lambda: user
        app.dependency_overrides[get_current_claims] = lambda: TokenClaims(
            user_id=user.id, email=user.email, display_name=user.display_name
        )

    def __exit__(self, *_exc):
        for dep, previous in self.saved.items():
            if previous is None:
                app.dependency_overrides.pop(dep, None)
            else:
                app.dependency_overrides[dep] = previous


def _team(db, name: str, members: list[tuple[User, str]]) -> Team:
    team = Team(name=name, slug=f"{name.lower()}-{uuid4().hex[:6]}")
    db.add(team)
    db.flush()
    for user, role in members:
        db.add(
            TeamMember(
                team_id=team.id,
                user_id=user.id,
                invited_email=user.email,
                role=role,
                status="active",
                joined_at=datetime.now(timezone.utc),
            )
        )
    db.commit()
    return team


def _project(db, owner: User, name="Alpha", key="ALP", team: Team | None = None):
    project = Project(
        user_id=owner.id,
        name=name,
        key=key,
        task_counter=0,
        team_id=team.id if team else None,
    )
    db.add(project)
    db.commit()
    return project


def _label(db, owner: User, name: str, team: Team | None = None) -> TaskLabel:
    label = TaskLabel(
        user_id=owner.id, team_id=team.id if team else None, name=name, color="#aa3355"
    )
    db.add(label)
    db.commit()
    return label


def _task(db, project: Project, labels: list[TaskLabel] | None = None) -> Task:
    project.task_counter += 1
    task = Task(
        user_id=project.user_id,
        project_id=project.id,
        number=project.task_counter,
        title="Ship it",
    )
    task.labels = list(labels or [])
    db.add(task)
    db.commit()
    return task


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (32, 32), color=(10, 200, 90)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _no_capability_hooks(monkeypatch):
    """The open build: nothing registered, every seat check passes."""
    monkeypatch.setattr(hooks, "_capability_hooks", [])


@pytest.fixture
def seat_log(monkeypatch):
    """Record every capability check; deny when a test flips `deny`."""
    log: dict = {"calls": [], "deny": False}

    def hook(db, payer_id, capability, context):
        log["calls"].append((payer_id, capability, context))
        return "Out of seats" if log["deny"] and context.get("new_seat") else None

    monkeypatch.setattr(hooks, "_capability_hooks", [hook])
    return log


@pytest.fixture
def alice(test_user):
    return test_user


@pytest.fixture
def bob(test_db):
    return _user(test_db, "bob@example.com", "Bob")


@pytest.fixture
def carol(test_db):
    return _user(test_db, "carol@example.com", "Carol")


def _transfer(client, project: Project, team_id: UUID | None, **extra):
    return client.post(
        f"/api/v1/projects/{project.id}/transfer",
        json={"team_id": str(team_id) if team_id else None, **extra},
    )


class TestMoveIntoTeam:
    def test_owner_moves_project_and_members_see_it_as_their_own(
        self, authenticated_client, test_db, alice, bob
    ):
        team = _team(test_db, "Crew", [(alice, "owner"), (bob, "member")])
        project = _project(test_db, alice)

        resp = _transfer(authenticated_client, project, team.id)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["team_id"] == str(team.id)
        assert body["role"] == "owner"  # team owner ⇒ project owner
        assert body["owner"]["type"] == "team"
        assert body["followed"] is True

        with _As(bob):
            listed = {
                p["id"]: p for p in authenticated_client.get("/api/v1/projects").json()
            }
        assert listed[str(project.id)]["role"] == "editor"
        # A team's project is the member's own work, not "Shared with me".
        assert listed[str(project.id)]["followed"] is True
        assert listed[str(project.id)]["is_team_member"] is True

    def test_a_member_may_bring_their_own_project_and_becomes_editor(
        self, authenticated_client, test_db, alice, bob
    ):
        team = _team(test_db, "Crew", [(bob, "owner"), (alice, "member")])
        project = _project(test_db, alice)

        resp = _transfer(authenticated_client, project, team.id)
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == "editor"
        # …and can no longer take it back out: that is the team owner's call.
        assert _transfer(authenticated_client, project, None).status_code == 403

    def test_needs_membership_of_the_destination(
        self, authenticated_client, test_db, alice, bob
    ):
        team = _team(test_db, "Elsewhere", [(bob, "owner")])
        project = _project(test_db, alice)
        resp = _transfer(authenticated_client, project, team.id)
        assert resp.status_code == 404
        test_db.refresh(project)
        assert project.team_id is None

    def test_only_the_owner_may_move(self, authenticated_client, test_db, alice, bob):
        project = _project(test_db, alice)
        test_db.add(
            ProjectGrant(
                project_id=project.id,
                principal_type="user",
                principal_id=bob.id,
                role="admin",
                scopes=["tasks", "sessions"],
            )
        )
        test_db.commit()
        team = _team(test_db, "Bobs", [(bob, "owner")])
        with _As(bob):
            assert _transfer(authenticated_client, project, team.id).status_code == 403

    def test_stranger_gets_404(self, authenticated_client, test_db, alice, carol):
        project = _project(test_db, alice)
        with _As(carol):
            assert _transfer(authenticated_client, project, None).status_code == 404

    def test_a_grant_to_the_destination_team_is_dropped(
        self, authenticated_client, test_db, alice, bob
    ):
        team = _team(test_db, "Crew", [(alice, "owner"), (bob, "member")])
        project = _project(test_db, alice)
        test_db.add(
            ProjectGrant(
                project_id=project.id,
                principal_type="team",
                principal_id=team.id,
                role="viewer",
                scopes=["tasks"],
            )
        )
        test_db.commit()
        assert _transfer(authenticated_client, project, team.id).status_code == 200
        remaining = (
            test_db.query(ProjectGrant)
            .filter(ProjectGrant.project_id == project.id)
            .count()
        )
        assert remaining == 0


class TestKeyCollision:
    def test_taken_key_is_a_409_with_a_free_suggestion(
        self, authenticated_client, test_db, alice, bob
    ):
        team = _team(test_db, "Crew", [(alice, "owner"), (bob, "member")])
        _project(test_db, bob, name="Theirs", key="ALP", team=team)
        _project(test_db, bob, name="Theirs too", key="ALP2", team=team)
        project = _project(test_db, alice, key="ALP")

        resp = _transfer(authenticated_client, project, team.id)
        assert resp.status_code == 409
        body = resp.json()
        assert body["code"] == "project_key_taken"
        assert body["key"] == "ALP"
        assert body["suggested_key"] == "ALP3"
        test_db.refresh(project)
        assert project.team_id is None  # nothing moved

        resp = _transfer(authenticated_client, project, team.id, key="alp3")
        assert resp.status_code == 200, resp.text
        assert resp.json()["key"] == "ALP3"

    def test_a_chosen_key_that_is_also_taken_is_refused(
        self, authenticated_client, test_db, alice
    ):
        team = _team(test_db, "Crew", [(alice, "owner")])
        _project(test_db, alice, name="Theirs", key="ZED", team=team)
        project = _project(test_db, alice, key="ALP")
        resp = _transfer(authenticated_client, project, team.id, key="ZED")
        assert resp.status_code == 409
        assert resp.json()["suggested_key"] == "ZED2"

    def test_task_identifiers_follow_the_new_key(
        self, authenticated_client, test_db, alice
    ):
        team = _team(test_db, "Crew", [(alice, "owner")])
        _project(test_db, alice, name="Theirs", key="ALP", team=team)
        project = _project(test_db, alice, key="ALP")
        task = _task(test_db, project)
        assert (
            _transfer(authenticated_client, project, team.id, key="NEW").status_code
            == 200
        )
        resp = authenticated_client.get(f"/api/v1/tasks/{task.id}")
        assert resp.json()["identifier"] == "NEW-1"


class TestLabelsFollowTheBoard:
    def test_personal_labels_become_the_teams(
        self, authenticated_client, test_db, alice, bob
    ):
        team = _team(test_db, "Crew", [(alice, "owner"), (bob, "member")])
        existing = _label(test_db, bob, "Bug", team=team)
        bug = _label(test_db, alice, "bug")
        ux = _label(test_db, alice, "ux")
        project = _project(test_db, alice)
        task = _task(test_db, project, [bug, ux])

        assert _transfer(authenticated_client, project, team.id).status_code == 200

        test_db.expire_all()
        labels = {label.name: label for label in test_db.get(Task, task.id).labels}
        # Matched by name (case-insensitive) into the team's vocabulary …
        assert labels["Bug"].id == existing.id
        # … or copied into it, colour and all.
        assert labels["ux"].team_id == team.id
        assert labels["ux"].color == ux.color
        # The originals stay Alice's, for her other projects.
        assert test_db.get(TaskLabel, bug.id).team_id is None

        # A member can now edit the task's labels without tripping over labels
        # they cannot see.
        with _As(bob):
            resp = authenticated_client.patch(
                f"/api/v1/tasks/{task.id}",
                json={"label_ids": [str(labels["ux"].id)]},
            )
        assert resp.status_code == 200, resp.text


class TestMoveOutOfTeam:
    def test_team_owner_takes_it_personal(
        self, authenticated_client, test_db, alice, bob
    ):
        team = _team(test_db, "Crew", [(alice, "owner"), (bob, "member")])
        project = _project(test_db, bob, team=team)
        label = _label(test_db, bob, "infra", team=team)
        task = _task(test_db, project, [label])

        resp = _transfer(authenticated_client, project, None)
        assert resp.status_code == 200, resp.text
        assert resp.json()["team_id"] is None
        assert resp.json()["role"] == "owner"

        test_db.expire_all()
        moved = test_db.get(Project, project.id)
        assert moved.user_id == alice.id
        # tasks.user_id tracks the owning project's user_id.
        assert test_db.get(Task, task.id).user_id == alice.id
        [carried] = test_db.get(Task, task.id).labels
        assert carried.team_id is None and carried.user_id == alice.id

        with _As(bob):
            resp = authenticated_client.get(f"/api/v1/projects/{project.id}/summary")
        assert resp.status_code == 404

    def test_a_team_admin_cannot(self, authenticated_client, test_db, alice, bob):
        team = _team(test_db, "Crew", [(bob, "owner"), (alice, "admin")])
        project = _project(test_db, bob, team=team)
        assert _transfer(authenticated_client, project, None).status_code == 403


class TestOwnerOnlyLens:
    def test_cli_lens_drops_a_board_once_it_is_the_teams(
        self, authenticated_client, test_db, alice, bob
    ):
        """`tasks.user_id` stays the creator's on a team project, so the
        owner-only lens has to look at the project too — or a creator who
        left the team keeps reading its board from the CLI."""
        team = _team(test_db, "Crew", [(bob, "owner"), (alice, "member")])
        project = _project(test_db, alice)
        task = _task(test_db, project)
        assert task_queries.get_task(test_db, alice.id, task.id) is not None

        assert _transfer(authenticated_client, project, team.id).status_code == 200
        assert task_queries.get_task(test_db, alice.id, task.id) is None
        assert task_queries.list_tasks(test_db, alice.id) == []
        # The dashboard lens still reaches it through the membership.
        assert (
            task_queries.get_task(test_db, alice.id, task.id, sharing=True) is not None
        )


class TestSeatsFollowThePayer:
    def test_outside_editors_are_asked_of_the_new_payer(
        self, authenticated_client, test_db, alice, bob, carol, seat_log
    ):
        team = _team(test_db, "Crew", [(bob, "owner"), (alice, "member")])
        project = _project(test_db, alice)
        test_db.add(
            ProjectGrant(
                project_id=project.id,
                principal_type="user",
                principal_id=carol.id,
                role="editor",
                scopes=["tasks", "sessions"],
            )
        )
        test_db.commit()
        seat_log["deny"] = True

        resp = _transfer(authenticated_client, project, team.id)
        assert resp.status_code == 402
        payer, capability, context = seat_log["calls"][-1]
        assert payer == bob.id  # the team owner pays from now on
        assert capability == hooks.CAPABILITY_GRANT_WRITE
        assert context["new_seat"] is True
        # Bob + Alice (members) + Carol (outside editor).
        assert context["seats"] == 3
        test_db.refresh(project)
        assert project.team_id is None

    def test_no_new_seat_when_everyone_already_has_one(
        self, authenticated_client, test_db, alice, bob, seat_log
    ):
        team = _team(test_db, "Crew", [(alice, "owner"), (bob, "member")])
        project = _project(test_db, alice)
        test_db.add(
            ProjectGrant(
                project_id=project.id,
                principal_type="user",
                principal_id=bob.id,
                role="editor",
                scopes=["tasks", "sessions"],
            )
        )
        test_db.commit()
        seat_log["deny"] = True
        assert _transfer(authenticated_client, project, team.id).status_code == 200
        assert seat_log["calls"][-1][2]["new_seat"] is False


@pytest.fixture
def fake_storage(monkeypatch):
    store: dict[str, tuple[bytes, str]] = {}
    monkeypatch.setattr(
        storage_module,
        "upload_attachment",
        lambda key, data, mime_type: store.__setitem__(key, (data, mime_type)),
    )
    monkeypatch.setattr(storage_module, "download_object", lambda key: store[key])
    monkeypatch.setattr(
        storage_module, "delete_object", lambda key: store.pop(key, None)
    )
    return store


class TestTeamAvatar:
    def test_admin_uploads_anyone_signed_in_can_fetch(
        self, authenticated_client, test_db, alice, bob, carol, fake_storage
    ):
        team = _team(test_db, "Crew", [(alice, "owner"), (bob, "member")])
        resp = authenticated_client.put(
            f"/api/v1/teams/{team.id}/avatar",
            files={"file": ("a.png", _png(), "image/png")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["avatar_image_uri"] == f"/api/v1/teams/{team.id}/avatar"
        assert f"team-avatars/{team.id}" in fake_storage

        with _As(carol):
            resp = authenticated_client.get(f"/api/v1/teams/{team.id}/avatar")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/")

        resp = authenticated_client.delete(f"/api/v1/teams/{team.id}/avatar")
        assert resp.status_code == 200
        assert resp.json()["avatar_image_uri"] is None
        assert not fake_storage

    def test_a_member_cannot_change_it(
        self, authenticated_client, test_db, alice, bob, fake_storage
    ):
        team = _team(test_db, "Crew", [(bob, "owner"), (alice, "member")])
        resp = authenticated_client.put(
            f"/api/v1/teams/{team.id}/avatar",
            files={"file": ("a.png", _png(), "image/png")},
        )
        assert resp.status_code == 403
        assert not fake_storage

    def test_rejects_non_images(
        self, authenticated_client, test_db, alice, fake_storage
    ):
        team = _team(test_db, "Crew", [(alice, "owner")])
        resp = authenticated_client.put(
            f"/api/v1/teams/{team.id}/avatar",
            files={"file": ("a.txt", b"not an image", "text/plain")},
        )
        assert resp.status_code == 400


def _membership(db, team: Team, user: User) -> TeamMember:
    return (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team.id, TeamMember.user_id == user.id)
        .one()
    )


class TestOwnershipTransfer:
    def test_owner_hands_over_and_stays_admin(
        self, authenticated_client, test_db, alice, bob
    ):
        team = _team(test_db, "Crew", [(alice, "owner"), (bob, "member")])
        resp = authenticated_client.post(
            f"/api/v1/teams/{team.id}/transfer",
            json={"member_id": str(_membership(test_db, team, bob).id)},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == "admin"
        roles = {m["user_id"]: m["role"] for m in resp.json()["members"]}
        assert roles[str(bob.id)] == "owner"
        assert roles[str(alice.id)] == "admin"

    def test_only_the_owner(self, authenticated_client, test_db, alice, bob, carol):
        team = _team(
            test_db, "Crew", [(bob, "owner"), (alice, "admin"), (carol, "member")]
        )
        resp = authenticated_client.post(
            f"/api/v1/teams/{team.id}/transfer",
            json={"member_id": str(_membership(test_db, team, carol).id)},
        )
        assert resp.status_code == 403

    def test_not_to_a_pending_invite(self, authenticated_client, test_db, alice):
        team = _team(test_db, "Crew", [(alice, "owner")])
        pending = TeamMember(
            team_id=team.id,
            invited_email="later@example.com",
            role="member",
            status="invited",
        )
        test_db.add(pending)
        test_db.commit()
        resp = authenticated_client.post(
            f"/api/v1/teams/{team.id}/transfer", json={"member_id": str(pending.id)}
        )
        assert resp.status_code == 409

    def test_new_owner_must_have_the_seats(
        self, authenticated_client, test_db, alice, bob, carol, seat_log
    ):
        team = _team(
            test_db, "Crew", [(alice, "owner"), (bob, "member"), (carol, "member")]
        )
        seat_log["deny"] = True
        resp = authenticated_client.post(
            f"/api/v1/teams/{team.id}/transfer",
            json={"member_id": str(_membership(test_db, team, bob).id)},
        )
        assert resp.status_code == 402
        payer, capability, context = seat_log["calls"][-1]
        assert payer == bob.id
        assert capability == hooks.CAPABILITY_TEAM_SEAT
        assert context["seats"] == 3
        test_db.expire_all()
        assert _membership(test_db, team, alice).role == "owner"


def _agent(client, **overrides):
    body = {"name": "Reviewer", "agent": "claude", "system_prompt": "Be terse."}
    body.update(overrides)
    return client.post("/api/v1/agents", json=body)


class TestTeamAgents:
    def test_admin_creates_member_runs_but_cannot_edit(
        self, authenticated_client, test_db, alice, bob, carol
    ):
        team = _team(test_db, "Crew", [(alice, "owner"), (bob, "member")])
        resp = _agent(authenticated_client, team_id=str(team.id))
        assert resp.status_code == 201, resp.text
        agent = resp.json()
        assert agent["team_id"] == str(team.id)
        assert agent["can_edit"] is True

        with _As(bob):
            listed = authenticated_client.get("/api/v1/agents").json()
            assert [(a["id"], a["can_edit"]) for a in listed] == [(agent["id"], False)]
            resp = authenticated_client.patch(
                f"/api/v1/agents/{agent['id']}", json={"system_prompt": "Say yes."}
            )
            assert resp.status_code == 403
            assert (
                authenticated_client.delete(f"/api/v1/agents/{agent['id']}").status_code
                == 403
            )
            # A member cannot add to the team's list either.
            assert _agent(authenticated_client, team_id=str(team.id)).status_code == 403

        with _As(carol):
            assert authenticated_client.get("/api/v1/agents").json() == []
            assert (
                authenticated_client.get(f"/api/v1/agents/{agent['id']}").status_code
                == 404
            )
            assert _agent(authenticated_client, team_id=str(team.id)).status_code == 404

    def test_names_are_unique_per_owner(self, authenticated_client, test_db, alice):
        team = _team(test_db, "Crew", [(alice, "owner")])
        assert _agent(authenticated_client).status_code == 201
        # Same name in the team's list: a different owner, no clash.
        assert _agent(authenticated_client, team_id=str(team.id)).status_code == 201
        resp = _agent(authenticated_client, team_id=str(team.id))
        assert resp.status_code == 409
        assert "This team already has" in resp.json()["detail"]

    def test_move_personal_agent_into_team_and_back(
        self, authenticated_client, test_db, alice, bob
    ):
        team = _team(test_db, "Crew", [(alice, "owner"), (bob, "member")])
        agent = _agent(authenticated_client).json()
        resp = authenticated_client.patch(
            f"/api/v1/agents/{agent['id']}", json={"team_id": str(team.id)}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["team_id"] == str(team.id)
        with _As(bob):
            assert [a["id"] for a in authenticated_client.get("/api/v1/agents").json()]
        resp = authenticated_client.patch(
            f"/api/v1/agents/{agent['id']}", json={"team_id": None}
        )
        assert resp.status_code == 200
        assert resp.json()["team_id"] is None
        with _As(bob):
            assert authenticated_client.get("/api/v1/agents").json() == []

    def test_cli_lens_stays_personal(self, test_db, alice):
        from backend.db import agent_profile_queries

        team = _team(test_db, "Crew", [(alice, "owner")])
        test_db.add(
            AgentProfile(
                user_id=alice.id, team_id=team.id, name="Team one", agent="claude"
            )
        )
        test_db.commit()
        assert agent_profile_queries.list_agent_profiles(test_db, alice.id) == []
        assert (
            len(
                agent_profile_queries.list_agent_profiles(
                    test_db, alice.id, sharing=True
                )
            )
            == 1
        )


class TestTeamAgentsInAutomations:
    @pytest.fixture
    def machine(self, test_db, alice):
        machine = Machine(id=uuid4(), user_id=alice.id, display_name="laptop")
        test_db.add(machine)
        test_db.commit()
        return machine

    def _automation_body(self, machine, profile_id):
        return {
            "title": "nightly",
            "prompt": "tidy up",
            "machine_id": str(machine.id),
            "directory": "/repo",
            "session_config": {"agent": "claude"},
            "agent_profile_id": str(profile_id),
            "schedule_kind": "once",
            "run_at": "2099-01-01T00:00:00Z",
        }

    def test_members_may_reference_outsiders_may_not(
        self, authenticated_client, test_db, alice, bob, machine
    ):
        team = _team(test_db, "Crew", [(bob, "owner"), (alice, "member")])
        theirs = AgentProfile(
            user_id=bob.id, team_id=team.id, name="Team agent", agent="claude"
        )
        private = AgentProfile(user_id=bob.id, name="Bob's own", agent="claude")
        test_db.add_all([theirs, private])
        test_db.commit()

        resp = authenticated_client.post(
            "/api/v1/automations", json=self._automation_body(machine, theirs.id)
        )
        assert resp.status_code == 201, resp.text
        resp = authenticated_client.post(
            "/api/v1/automations", json=self._automation_body(machine, private.id)
        )
        assert resp.status_code == 404

    def test_dispatch_falls_back_once_the_owner_leaves_the_team(
        self, test_db, alice, bob, machine
    ):
        team = _team(test_db, "Crew", [(bob, "owner"), (alice, "member")])
        profile = AgentProfile(
            user_id=bob.id,
            team_id=team.id,
            name="Team agent",
            agent="claude",
            config={"agent": "claude", "model": "claude-opus-5"},
            system_prompt="Team rules.",
        )
        test_db.add(profile)
        test_db.commit()
        automation = Automation(
            user_id=alice.id,
            title="nightly",
            prompt="go",
            machine_id=machine.id,
            directory="/repo",
            session_config={"agent": "claude", "model": "claude-haiku-4-5"},
            agent_profile_id=profile.id,
            schedule_kind="once",
        )
        test_db.add(automation)
        test_db.commit()

        def resolve():
            return resolve_automation_config(
                test_db,
                agent_profile_id=automation.agent_profile_id,
                session_config=automation.session_config,
                owner_id=automation.user_id,
            )

        assert resolve().system_prompt == "Team rules."
        _membership(test_db, team, alice).status = "removed"
        test_db.commit()
        resolved = resolve()
        assert resolved.from_profile is False
        assert resolved.system_prompt is None
        assert resolved.session_config["model"] == "claude-haiku-4-5"


class TestDeletingATeamHandsWorkBack:
    def test_clashing_key_and_agent_name_make_room(
        self, authenticated_client, test_db, alice, bob
    ):
        team = _team(test_db, "Crew", [(alice, "owner"), (bob, "member")])
        _project(test_db, bob, name="Bob's", key="ALP")
        teams_project = _project(test_db, bob, name="Team's", key="ALP", team=team)
        test_db.add_all(
            [
                AgentProfile(user_id=bob.id, name="Reviewer", agent="claude"),
                AgentProfile(
                    user_id=bob.id, team_id=team.id, name="Reviewer", agent="claude"
                ),
            ]
        )
        test_db.commit()

        assert (
            authenticated_client.delete(f"/api/v1/teams/{team.id}").status_code == 204
        )

        test_db.expire_all()
        demoted = test_db.get(Project, teams_project.id)
        assert demoted.team_id is None
        assert demoted.user_id == bob.id
        assert demoted.key == "ALP2"
        names = sorted(
            p.name
            for p in test_db.query(AgentProfile).filter(AgentProfile.user_id == bob.id)
        )
        assert names == ["Reviewer", "Reviewer (Crew)"]


class TestDeletingACreatorsAccountKeepsTheTeamsWork:
    def test_team_rows_pass_to_the_team_owner(self, test_db, alice, bob):
        """`user_id` on a team's rows is "created by", and its FK CASCADEs:
        without the hand-over, Bob deleting his account would delete the
        team's project, every task on it, its labels and agents."""
        from backend.db.queries import delete_user_account

        team = _team(test_db, "Crew", [(alice, "owner"), (bob, "member")])
        project = _project(test_db, bob, team=team)
        label = _label(test_db, bob, "infra", team=team)
        task = _task(test_db, project, [label])
        agent = AgentProfile(
            user_id=bob.id, team_id=team.id, name="Ops", agent="claude"
        )
        test_db.add(agent)
        test_db.commit()
        ids = (project.id, task.id, label.id, agent.id)

        delete_user_account(test_db, bob.id)
        test_db.expire_all()

        assert test_db.get(Project, ids[0]).user_id == alice.id
        assert test_db.get(Task, ids[1]).user_id == alice.id
        assert test_db.get(TaskLabel, ids[2]).user_id == alice.id
        assert test_db.get(AgentProfile, ids[3]).user_id == alice.id
        assert [lbl.id for lbl in test_db.get(Task, ids[1]).labels] == [ids[2]]
