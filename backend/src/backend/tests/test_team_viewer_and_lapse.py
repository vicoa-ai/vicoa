"""The Team tier in the open core (collaboration §6): the free `viewer` team
role, who takes a seat, owning a team as a capability, and the lapse/restore
mechanics the billing overlay drives when a Team subscription ends or returns.

The core decides *who* holds a seat and flips rows; pricing (who has their own
Pro, how many seats were bought) is the overlay's and is pinned in its tests.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.db import collab_queries
from backend.tests.test_team_ownership import _As, _label, _project, _team, _user
from shared import access, hooks
from shared.agent_profile_resolution import usable_profile_filter
from shared.database import (
    AgentInstance,
    AgentType,
    ProjectGrant,
    TeamInstanceAccess,
    TeamMember,
    UserInstanceAccess,
)
from shared.database.agent_profile_models import AgentProfile
from shared.database.enums import AgentStatus, InstanceAccessLevel


@pytest.fixture(autouse=True)
def _no_capability_hooks(monkeypatch):
    """The open build: nothing registered unless a test installs a hook."""
    monkeypatch.setattr(hooks, "_capability_hooks", [])


def _recording_hook(monkeypatch, deny: set[str] | None = None) -> list[tuple]:
    seen: list[tuple] = []

    def hook(db, user_id, capability, context):
        seen.append((user_id, capability, context))
        if deny and capability in deny:
            return f"{capability} denied"
        return None

    monkeypatch.setattr(hooks, "_capability_hooks", [hook])
    return seen


def _instance(db, owner, project=None) -> AgentInstance:
    agent_type = AgentType(user_id=owner.id, name=f"claude {uuid4().hex[:4]}")
    db.add(agent_type)
    db.flush()
    instance = AgentInstance(
        agent_type_id=agent_type.id,
        user_id=owner.id,
        project_id=project.id if project else None,
        status=AgentStatus.ACTIVE,
        started_at=datetime.now(timezone.utc),
    )
    db.add(instance)
    db.commit()
    return instance


def _member_row(db, team, user) -> TeamMember:
    return (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team.id, TeamMember.user_id == user.id)
        .one()
    )


class TestViewerRole:
    def test_viewer_reads_and_comments_but_cannot_edit(self, test_db):
        owner = _user(test_db, "owner@example.com", "Owner")
        viewer = _user(test_db, "viewer@example.com", "Viewer")
        team = _team(test_db, "Crew", [(owner, "owner"), (viewer, "viewer")])
        project = _project(test_db, owner, team=team)

        assert access.project_role(test_db, viewer.id, project) == "commenter"
        assert project.id in access.visible_project_ids(test_db, viewer.id)
        # An editor floor (session filing, task edits) never matches a viewer.
        assert project.id not in access.visible_project_ids(
            test_db, viewer.id, min_role="editor"
        )

    def test_viewer_cannot_prompt_a_team_session(self, test_db):
        owner = _user(test_db, "owner@example.com", "Owner")
        viewer = _user(test_db, "viewer@example.com", "Viewer")
        team = _team(test_db, "Crew", [(owner, "owner"), (viewer, "viewer")])
        project = _project(test_db, owner, team=team)
        instance = _instance(test_db, owner, project)

        assert access.instance_role(test_db, viewer.id, instance) == "commenter"
        assert (
            access.instance_access(test_db, viewer.id, instance)
            == InstanceAccessLevel.READ
        )

    def test_a_grant_to_the_team_is_capped_for_its_viewers(self, test_db):
        owner = _user(test_db, "owner@example.com", "Owner")
        member = _user(test_db, "member@example.com", "Member")
        viewer = _user(test_db, "viewer@example.com", "Viewer")
        team = _team(test_db, "Crew", [(member, "owner"), (viewer, "viewer")])
        project = _project(test_db, owner)
        test_db.add(
            ProjectGrant(
                project_id=project.id,
                principal_type="team",
                principal_id=team.id,
                role="editor",
            )
        )
        test_db.commit()

        assert access.project_role(test_db, member.id, project) == "editor"
        assert access.project_role(test_db, viewer.id, project) == "commenter"
        assert project.id not in access.visible_project_ids(
            test_db, viewer.id, min_role="editor"
        )

    def test_a_session_shared_with_the_team_is_read_only_for_viewers(self, test_db):
        owner = _user(test_db, "owner@example.com", "Owner")
        viewer = _user(test_db, "viewer@example.com", "Viewer")
        team = _team(test_db, "Crew", [(owner, "owner"), (viewer, "viewer")])
        instance = _instance(test_db, owner)
        test_db.add(
            TeamInstanceAccess(
                agent_instance_id=instance.id,
                team_id=team.id,
                access=InstanceAccessLevel.WRITE,
                granted_by_user_id=owner.id,
            )
        )
        test_db.commit()

        assert (
            access.session_share_access(test_db, instance, viewer.id)
            == InstanceAccessLevel.READ
        )
        assert access.instance_roles(test_db, viewer.id, [instance]) == {
            instance.id: "viewer"
        }

    def test_viewer_cannot_change_team_labels(self, client, test_db):
        owner = _user(test_db, "owner@example.com", "Owner")
        viewer = _user(test_db, "viewer@example.com", "Viewer")
        team = _team(test_db, "Crew", [(owner, "owner"), (viewer, "viewer")])
        label = _label(test_db, owner, "bug", team=team)
        with _As(viewer):
            created = client.post(
                "/api/v1/task-labels",
                json={"name": "chore", "color": "#112233", "team_id": str(team.id)},
            )
            edited = client.patch(
                f"/api/v1/task-labels/{label.id}", json={"name": "defect"}
            )
        assert created.status_code == 403, created.text
        assert edited.status_code == 403, edited.text

    def test_viewer_cannot_run_team_agents(self, test_db):
        owner = _user(test_db, "owner@example.com", "Owner")
        viewer = _user(test_db, "viewer@example.com", "Viewer")
        team = _team(test_db, "Crew", [(owner, "owner"), (viewer, "viewer")])
        profile = AgentProfile(
            user_id=owner.id, team_id=team.id, name="Reviewer", agent="claude"
        )
        test_db.add(profile)
        test_db.commit()

        usable = {
            p.id
            for p in test_db.query(AgentProfile).filter(
                usable_profile_filter(viewer.id)
            )
        }
        assert profile.id not in usable

    def test_viewer_cannot_bring_a_project_into_the_team(self, client, test_db):
        owner = _user(test_db, "owner@example.com", "Owner")
        viewer = _user(test_db, "viewer@example.com", "Viewer")
        team = _team(test_db, "Crew", [(owner, "owner"), (viewer, "viewer")])
        mine = _project(test_db, viewer, name="Mine", key="MIN")
        with _As(viewer):
            response = client.post(
                f"/api/v1/projects/{mine.id}/transfer", json={"team_id": str(team.id)}
            )
        assert response.status_code == 403, response.text

    def test_a_viewer_may_leave_but_not_remove_others(self, client, test_db):
        owner = _user(test_db, "owner@example.com", "Owner")
        viewer = _user(test_db, "viewer@example.com", "Viewer")
        other = _user(test_db, "other@example.com", "Other")
        team = _team(
            test_db, "Crew", [(owner, "owner"), (viewer, "viewer"), (other, "member")]
        )
        with _As(viewer):
            removed = client.delete(
                f"/api/v1/teams/{team.id}/members/{_member_row(test_db, team, other).id}"
            )
            left = client.delete(
                f"/api/v1/teams/{team.id}/members/{_member_row(test_db, team, viewer).id}"
            )
        assert removed.status_code == 403, removed.text
        assert left.status_code == 204, left.text


class TestSeats:
    def test_viewers_take_no_seat(self, test_db):
        owner = _user(test_db, "owner@example.com", "Owner")
        member = _user(test_db, "member@example.com", "Member")
        viewer = _user(test_db, "viewer@example.com", "Viewer")
        _team(
            test_db, "Crew", [(owner, "owner"), (member, "member"), (viewer, "viewer")]
        )
        assert collab_queries.seat_keys(test_db, owner.id) == {
            f"user:{owner.id}",
            f"user:{member.id}",
        }

    def test_inviting_a_viewer_is_never_metered(
        self, authenticated_client, test_db, monkeypatch
    ):
        team = authenticated_client.post("/api/v1/teams", json={"name": "Crew"}).json()
        seen = _recording_hook(monkeypatch, deny={hooks.CAPABILITY_TEAM_SEAT})
        invited = authenticated_client.post(
            f"/api/v1/teams/{team['id']}/members",
            json={"email": "looker@example.com", "role": "viewer"},
        )
        assert invited.status_code == 201, invited.text
        assert invited.json()["role"] == "viewer"
        assert seen == []

        link = authenticated_client.post(
            f"/api/v1/teams/{team['id']}/invites", json={"role": "viewer"}
        )
        assert link.status_code == 201, link.text
        joiner = _user(test_db, "joiner@example.com", "Joiner")
        with _As(joiner):
            joined = authenticated_client.post(
                f"/api/v1/team-invites/{link.json()['token']}/accept"
            )
        assert joined.status_code == 200, joined.text
        assert seen == []

    def test_promoting_a_viewer_takes_a_seat_demoting_does_not(
        self, authenticated_client, test_db, test_user, monkeypatch
    ):
        viewer = _user(test_db, "viewer@example.com", "Viewer")
        team = _team(test_db, "Crew", [(test_user, "owner"), (viewer, "viewer")])
        row = _member_row(test_db, team, viewer)
        seen = _recording_hook(monkeypatch)

        promoted = authenticated_client.patch(
            f"/api/v1/teams/{team.id}/members/{row.id}", json={"role": "member"}
        )
        assert promoted.status_code == 200, promoted.text
        assert [c for _, c, _ in seen] == [hooks.CAPABILITY_TEAM_SEAT]
        assert seen[0][2]["new_keys"] == [f"user:{viewer.id}"]

        seen.clear()
        demoted = authenticated_client.patch(
            f"/api/v1/teams/{team.id}/members/{row.id}", json={"role": "viewer"}
        )
        assert demoted.status_code == 200, demoted.text
        assert seen == []

    def test_a_denied_promotion_changes_nothing(
        self, authenticated_client, test_db, test_user, monkeypatch
    ):
        viewer = _user(test_db, "viewer@example.com", "Viewer")
        team = _team(test_db, "Crew", [(test_user, "owner"), (viewer, "viewer")])
        row = _member_row(test_db, team, viewer)
        _recording_hook(monkeypatch, deny={hooks.CAPABILITY_TEAM_SEAT})
        response = authenticated_client.patch(
            f"/api/v1/teams/{team.id}/members/{row.id}", json={"role": "admin"}
        )
        assert response.status_code == 402
        test_db.refresh(row)
        assert row.role == "viewer"


class TestOwningATeam:
    def test_creating_a_team_asks_to_own_one(self, authenticated_client, monkeypatch):
        seen = _recording_hook(monkeypatch, deny={hooks.CAPABILITY_TEAM_OWN})
        response = authenticated_client.post("/api/v1/teams", json={"name": "Crew"})
        assert response.status_code == 402
        assert response.json()["capability"] == hooks.CAPABILITY_TEAM_OWN
        assert seen[0][2]["action"] == "create_team"

    def test_the_new_owner_is_asked_too(
        self, authenticated_client, test_db, test_user, monkeypatch
    ):
        heir = _user(test_db, "heir@example.com", "Heir")
        team = _team(test_db, "Crew", [(test_user, "owner"), (heir, "viewer")])
        seen = _recording_hook(monkeypatch, deny={hooks.CAPABILITY_TEAM_OWN})
        response = authenticated_client.post(
            f"/api/v1/teams/{team.id}/transfer",
            json={"member_id": str(_member_row(test_db, team, heir).id)},
        )
        assert response.status_code == 402
        assert seen[0][0] == heir.id
        assert seen[0][2]["action"] == "transfer_ownership"
        assert _member_row(test_db, team, heir).role == "viewer"


class TestLapse:
    @pytest.fixture
    def pool(self, test_db):
        """A payer with an editing member, an admin, a viewer, a pending
        invite, an outside editor and a WRITE session share."""
        payer = _user(test_db, "payer@example.com", "Payer")
        member = _user(test_db, "member@example.com", "Member")
        admin = _user(test_db, "admin@example.com", "Admin")
        viewer = _user(test_db, "viewer@example.com", "Viewer")
        outside = _user(test_db, "outside@example.com", "Outside")
        writer = _user(test_db, "writer@example.com", "Writer")
        team = _team(
            test_db,
            "Crew",
            [
                (payer, "owner"),
                (member, "member"),
                (admin, "admin"),
                (viewer, "viewer"),
            ],
        )
        test_db.add(
            TeamMember(
                team_id=team.id,
                invited_email="pending@example.com",
                role="member",
                status="invited",
            )
        )
        team_project = _project(test_db, payer, name="Team", key="TEA", team=team)
        personal = _project(test_db, payer, name="Mine", key="MIN")
        test_db.add(
            ProjectGrant(
                project_id=personal.id,
                principal_type="user",
                principal_id=outside.id,
                role="editor",
            )
        )
        instance = _instance(test_db, payer)
        test_db.add(
            UserInstanceAccess(
                agent_instance_id=instance.id,
                shared_email=writer.email,
                user_id=writer.id,
                access=InstanceAccessLevel.WRITE,
                granted_by_user_id=payer.id,
            )
        )
        test_db.commit()
        return {
            "payer": payer,
            "member": member,
            "admin": admin,
            "viewer": viewer,
            "outside": outside,
            "writer": writer,
            "team": team,
            "team_project": team_project,
            "personal": personal,
            "instance": instance,
        }

    def test_holders_are_everyone_paid_for_but_the_payer(self, test_db, pool):
        holders = collab_queries.seat_holders(test_db, pool["payer"].id)
        assert {h.key for h in holders} == {
            f"user:{pool['member'].id}",
            f"user:{pool['admin'].id}",
            f"user:{pool['outside'].id}",
            f"user:{pool['writer'].id}",
            "email:pending@example.com",
        }
        assert all(h.live and not h.lapsed for h in holders)

    def test_lapse_drops_to_read_and_comment_and_restore_brings_it_back(
        self, test_db, pool
    ):
        payer, member, admin = pool["payer"], pool["member"], pool["admin"]
        outside, writer, team = pool["outside"], pool["writer"], pool["team"]
        keys = {
            f"user:{member.id}",
            f"user:{admin.id}",
            f"user:{outside.id}",
            f"user:{writer.id}",
            "email:pending@example.com",
        }
        assert collab_queries.lapse_seats(test_db, payer.id, keys) == 5

        assert collab_queries.seat_keys(test_db, payer.id) == {f"user:{payer.id}"}
        assert access.project_role(test_db, member.id, pool["team_project"]) == (
            "commenter"
        )
        assert access.project_role(test_db, admin.id, pool["team_project"]) == (
            "commenter"
        )
        assert access.project_role(test_db, outside.id, pool["personal"]) == (
            "commenter"
        )
        assert (
            access.instance_access(test_db, writer.id, pool["instance"])
            == InstanceAccessLevel.READ
        )
        assert _member_row(test_db, team, admin).lapsed_role == "admin"
        pending = (
            test_db.query(TeamMember)
            .filter(TeamMember.invited_email == "pending@example.com")
            .one()
        )
        assert (pending.role, pending.lapsed_role) == ("viewer", "member")
        # The real viewer was never paid for, so it is not touched.
        assert _member_row(test_db, team, pool["viewer"]).lapsed_role is None
        holders = collab_queries.seat_holders(test_db, payer.id)
        assert all(h.lapsed and not h.live for h in holders)

        assert collab_queries.restore_seats(test_db, payer.id, keys) == 5
        assert access.project_role(test_db, member.id, pool["team_project"]) == (
            "editor"
        )
        assert access.project_role(test_db, admin.id, pool["team_project"]) == "admin"
        assert access.project_role(test_db, outside.id, pool["personal"]) == "editor"
        assert (
            access.instance_access(test_db, writer.id, pool["instance"])
            == InstanceAccessLevel.WRITE
        )
        assert len(collab_queries.seat_keys(test_db, payer.id)) == 6

    def test_lapse_is_per_person(self, test_db, pool):
        payer, member = pool["payer"], pool["member"]
        collab_queries.lapse_seats(test_db, payer.id, {f"user:{member.id}"})
        assert access.project_role(test_db, member.id, pool["team_project"]) == (
            "commenter"
        )
        assert access.project_role(test_db, pool["admin"].id, pool["team_project"]) == (
            "admin"
        )

    def test_an_explicit_role_ends_a_lapse(self, client, test_db, pool, monkeypatch):
        payer, member, team = pool["payer"], pool["member"], pool["team"]
        collab_queries.lapse_seats(test_db, payer.id, {f"user:{member.id}"})
        row = _member_row(test_db, team, member)
        seen = _recording_hook(monkeypatch)
        with _As(payer):
            response = client.patch(
                f"/api/v1/teams/{team.id}/members/{row.id}", json={"role": "member"}
            )
        assert response.status_code == 200, response.text
        # Back into a seat role, so it is metered like any promotion.
        assert [c for _, c, _ in seen] == [hooks.CAPABILITY_TEAM_SEAT]
        test_db.refresh(row)
        assert (row.role, row.lapsed_role) == ("member", None)

    def test_the_team_page_says_who_lapsed(self, client, test_db, pool):
        payer, member, team = pool["payer"], pool["member"], pool["team"]
        collab_queries.lapse_seats(test_db, payer.id, {f"user:{member.id}"})
        with _As(payer):
            body = client.get(f"/api/v1/teams/{team.id}").json()
        row = next(m for m in body["members"] if m["user_id"] == str(member.id))
        assert (row["role"], row["lapsed_role"]) == ("viewer", "member")

    def test_lapsed_payers_finds_whose_pool_to_revisit(self, test_db, pool):
        payer = pool["payer"]
        for who in ("member", "outside", "writer"):
            collab_queries.lapse_seats(test_db, payer.id, {f"user:{pool[who].id}"})
            assert collab_queries.lapsed_payer_ids(test_db, pool[who].id) == {payer.id}
        assert collab_queries.lapsed_payer_ids(test_db, pool["admin"].id) == set()


def test_a_viewer_is_the_last_heir(client, test_db):
    from backend.db.queries import delete_user_account

    owner = _user(test_db, "owner@example.com", "Owner")
    viewer = _user(test_db, "viewer@example.com", "Viewer")
    member = _user(test_db, "member@example.com", "Member")
    team = _team(test_db, "Crew", [(owner, "owner"), (viewer, "viewer")])
    test_db.add(
        TeamMember(
            team_id=team.id,
            user_id=member.id,
            invited_email=member.email,
            role="member",
            status="active",
            joined_at=datetime.now(timezone.utc),
        )
    )
    test_db.commit()
    delete_user_account(test_db, owner.id)
    assert _member_row(test_db, team, member).role == "owner"
    assert _member_row(test_db, team, viewer).role == "viewer"
