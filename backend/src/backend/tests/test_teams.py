"""Teams API (collaboration §3.2): create, slugs, email invites, accept/decline,
roles, removal, join links, seat gating."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.auth.dependencies import (
    get_current_claims,
    get_current_user,
    get_optional_current_user,
)
from backend.db import collab_queries
from backend.main import app
from shared import hooks
from shared.auth.tokens import TokenClaims
from shared.database import Team, TeamInvite, TeamMember, User


def _user(db, email: str, name: str = "Someone") -> User:
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
    """Context manager: run requests as `user`, then restore whatever auth
    overrides were in place (the `authenticated_client` fixture's)."""

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


def _create_team(client, name="Collab Crew"):
    response = client.post("/api/v1/teams", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture(autouse=True)
def _no_capability_hooks(monkeypatch):
    """The open build: nothing registered, every seat check passes."""
    monkeypatch.setattr(hooks, "_capability_hooks", [])


class TestCreateAndList:
    def test_create_team_and_list(self, authenticated_client, test_user):
        team = _create_team(authenticated_client)
        assert team["name"] == "Collab Crew"
        assert team["slug"] == "collab-crew"
        assert team["role"] == "owner"
        assert team["member_count"] == 1
        (owner_row,) = team["members"]
        assert owner_row["user_id"] == str(test_user.id)
        assert owner_row["role"] == "owner"
        assert owner_row["status"] == "active"
        assert owner_row["email"] == test_user.email  # owners see emails

        listed = authenticated_client.get("/api/v1/teams").json()
        assert [t["id"] for t in listed] == [team["id"]]
        assert listed[0]["member_count"] == 1

        detail = authenticated_client.get(f"/api/v1/teams/{team['id']}").json()
        assert detail["members"] == team["members"]

    def test_slug_is_derived_not_chosen_and_collisions_suffix(
        self, authenticated_client
    ):
        first = _create_team(authenticated_client, "Ops Team!")
        second = _create_team(authenticated_client, "ops team")
        third = _create_team(authenticated_client, "OPS   TEAM")
        assert first["slug"] == "ops-team"
        assert second["slug"] == "ops-team-2"
        assert third["slug"] == "ops-team-3"

    def test_reserved_and_unusable_names_fall_back(self, authenticated_client):
        assert _create_team(authenticated_client, "Admin")["slug"] == "team"
        assert _create_team(authenticated_client, "工作")["slug"] == "team-2"

    def test_no_slug_lookup_route(self, authenticated_client):
        """D-D: the namespace is reserved, not exposed. Nothing resolves a slug."""
        _create_team(authenticated_client, "Findable")
        for path in ("/api/v1/teams/findable", "/api/v1/t/findable"):
            response = authenticated_client.get(path)
            assert response.status_code in (404, 422), path

    def test_non_member_cannot_see_team(self, authenticated_client, client, test_db):
        team = _create_team(authenticated_client)
        outsider = _user(test_db, "outsider@example.com")
        with _As(outsider):
            assert client.get(f"/api/v1/teams/{team['id']}").status_code == 404
            assert client.get("/api/v1/teams").json() == []
            assert (
                client.patch(
                    f"/api/v1/teams/{team['id']}", json={"name": "x"}
                ).status_code
                == 404
            )
            assert client.delete(f"/api/v1/teams/{team['id']}").status_code == 404


class TestEmailInvites:
    def test_invite_existing_user_is_pending_until_accepted(
        self, authenticated_client, client, test_db
    ):
        team = _create_team(authenticated_client)
        mate = _user(test_db, "teammate@example.com", "Teammate")

        response = authenticated_client.post(
            f"/api/v1/teams/{team['id']}/members",
            json={"email": "Teammate@Example.com", "role": "admin"},
        )
        assert response.status_code == 201, response.text
        member = response.json()
        assert member["user_id"] == str(mate.id)
        assert member["status"] == "invited"
        assert member["role"] == "admin"

        # Pending ⇒ confers nothing yet.
        with _As(mate):
            assert client.get(f"/api/v1/teams/{team['id']}").status_code == 404
            assert client.get("/api/v1/teams").json() == []
            invitations = client.get("/api/v1/teams/invitations").json()
            assert [i["team_id"] for i in invitations] == [team["id"]]
            assert invitations[0]["invited_by_display_name"] == "Test User"

            accepted = client.post(f"/api/v1/teams/{team['id']}/members/accept")
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()["role"] == "admin"
            assert client.get(f"/api/v1/teams/{team['id']}").status_code == 200
            assert client.get("/api/v1/teams/invitations").json() == []

    def test_invite_unknown_email_attaches_at_signup(
        self, authenticated_client, client, test_db
    ):
        team = _create_team(authenticated_client)
        response = authenticated_client.post(
            f"/api/v1/teams/{team['id']}/members",
            json={"email": "future-user@example.com"},
        )
        assert response.status_code == 201
        assert response.json()["user_id"] is None
        assert response.json()["email"] == "future-user@example.com"
        assert response.json()["role"] == "member"

        # They sign up later: matched by email, accept works, row is attached.
        newcomer = _user(test_db, "Future-User@example.com", "Newcomer")
        with _As(newcomer):
            assert [
                i["team_id"] for i in client.get("/api/v1/teams/invitations").json()
            ] == [team["id"]]
            assert (
                client.post(f"/api/v1/teams/{team['id']}/members/accept").status_code
                == 200
            )
        row = (
            test_db.query(TeamMember)
            .filter(TeamMember.team_id == team["id"], TeamMember.user_id == newcomer.id)
            .one()
        )
        assert row.status == "active"
        assert row.joined_at is not None

    def test_decline_removes_the_row(self, authenticated_client, client, test_db):
        team = _create_team(authenticated_client)
        mate = _user(test_db, "mate@example.com")
        authenticated_client.post(
            f"/api/v1/teams/{team['id']}/members", json={"email": mate.email}
        )
        with _As(mate):
            assert (
                client.post(f"/api/v1/teams/{team['id']}/members/decline").status_code
                == 204
            )
            assert client.get("/api/v1/teams/invitations").json() == []
        assert (
            test_db.query(TeamMember)
            .filter(TeamMember.team_id == team["id"], TeamMember.user_id == mate.id)
            .count()
            == 0
        )

    def test_duplicate_invite_conflicts(self, authenticated_client, test_db):
        team = _create_team(authenticated_client)
        _user(test_db, "dup@example.com")
        first = authenticated_client.post(
            f"/api/v1/teams/{team['id']}/members", json={"email": "dup@example.com"}
        )
        assert first.status_code == 201
        again = authenticated_client.post(
            f"/api/v1/teams/{team['id']}/members", json={"email": "DUP@example.com"}
        )
        assert again.status_code == 409

    def test_only_owner_hands_out_admin(self, authenticated_client, client, test_db):
        team = _create_team(authenticated_client)
        admin = _user(test_db, "admin@example.com")
        authenticated_client.post(
            f"/api/v1/teams/{team['id']}/members",
            json={"email": admin.email, "role": "admin"},
        )
        with _As(admin):
            client.post(f"/api/v1/teams/{team['id']}/members/accept")
            # An admin can invite members…
            ok = client.post(
                f"/api/v1/teams/{team['id']}/members",
                json={"email": "m@example.com"},
            )
            assert ok.status_code == 201
            # …but not admins.
            denied = client.post(
                f"/api/v1/teams/{team['id']}/members",
                json={"email": "a2@example.com", "role": "admin"},
            )
            assert denied.status_code == 403

    def test_member_cannot_invite(self, authenticated_client, client, test_db):
        team = _create_team(authenticated_client)
        member = _user(test_db, "member@example.com")
        authenticated_client.post(
            f"/api/v1/teams/{team['id']}/members", json={"email": member.email}
        )
        with _As(member):
            client.post(f"/api/v1/teams/{team['id']}/members/accept")
            denied = client.post(
                f"/api/v1/teams/{team['id']}/members", json={"email": "x@example.com"}
            )
            assert denied.status_code == 403
            # Members don't see other members' emails.
            detail = client.get(f"/api/v1/teams/{team['id']}").json()
            emails = {m["email"] for m in detail["members"]}
            assert emails == {None}


class TestRolesAndRemoval:
    def _team_with(self, authenticated_client, client, test_db, *, role):
        team = _create_team(authenticated_client)
        user = _user(test_db, f"{role}-{uuid4().hex[:6]}@example.com")
        member = authenticated_client.post(
            f"/api/v1/teams/{team['id']}/members",
            json={"email": user.email, "role": role},
        ).json()
        with _As(user):
            client.post(f"/api/v1/teams/{team['id']}/members/accept")
        return team, user, member

    def test_owner_changes_roles_but_not_ownership(
        self, authenticated_client, client, test_db
    ):
        team, _, member = self._team_with(
            authenticated_client, client, test_db, role="member"
        )
        promoted = authenticated_client.patch(
            f"/api/v1/teams/{team['id']}/members/{member['id']}", json={"role": "admin"}
        )
        assert promoted.status_code == 200
        assert promoted.json()["role"] == "admin"

        owner_row = next(
            m
            for m in authenticated_client.get(f"/api/v1/teams/{team['id']}").json()[
                "members"
            ]
            if m["role"] == "owner"
        )
        assert (
            authenticated_client.patch(
                f"/api/v1/teams/{team['id']}/members/{owner_row['id']}",
                json={"role": "member"},
            ).status_code
            == 409
        )

    def test_admin_cannot_change_roles(self, authenticated_client, client, test_db):
        team, admin, _ = self._team_with(
            authenticated_client, client, test_db, role="admin"
        )
        other = _user(test_db, "other@example.com")
        row = authenticated_client.post(
            f"/api/v1/teams/{team['id']}/members", json={"email": other.email}
        ).json()
        with _As(admin):
            assert (
                client.patch(
                    f"/api/v1/teams/{team['id']}/members/{row['id']}",
                    json={"role": "admin"},
                ).status_code
                == 403
            )

    def test_removal_rules(self, authenticated_client, client, test_db):
        team, admin, admin_row = self._team_with(
            authenticated_client, client, test_db, role="admin"
        )
        other_admin = _user(test_db, "admin2@example.com")
        other_admin_row = authenticated_client.post(
            f"/api/v1/teams/{team['id']}/members",
            json={"email": other_admin.email, "role": "admin"},
        ).json()
        member = _user(test_db, "member@example.com")
        member_row = authenticated_client.post(
            f"/api/v1/teams/{team['id']}/members", json={"email": member.email}
        ).json()
        owner_row = next(
            m
            for m in authenticated_client.get(f"/api/v1/teams/{team['id']}").json()[
                "members"
            ]
            if m["role"] == "owner"
        )

        with _As(admin):
            # Admins can't remove admins…
            assert (
                client.delete(
                    f"/api/v1/teams/{team['id']}/members/{other_admin_row['id']}"
                ).status_code
                == 403
            )
            # …can remove members…
            assert (
                client.delete(
                    f"/api/v1/teams/{team['id']}/members/{member_row['id']}"
                ).status_code
                == 204
            )
            # …never the owner…
            assert (
                client.delete(
                    f"/api/v1/teams/{team['id']}/members/{owner_row['id']}"
                ).status_code
                == 409
            )
            # …and can leave.
            assert (
                client.delete(
                    f"/api/v1/teams/{team['id']}/members/{admin_row['id']}"
                ).status_code
                == 204
            )
            assert client.get(f"/api/v1/teams/{team['id']}").status_code == 404

        # Removed rows are kept and revived on re-invite (one row per user).
        removed = (
            test_db.query(TeamMember)
            .filter(TeamMember.team_id == team["id"], TeamMember.user_id == admin.id)
            .one()
        )
        assert removed.status == "removed"
        again = authenticated_client.post(
            f"/api/v1/teams/{team['id']}/members", json={"email": admin.email}
        )
        assert again.status_code == 201
        assert again.json()["id"] == str(removed.id)
        assert again.json()["status"] == "invited"

    def test_delete_team_is_owner_only_and_sweeps_grants(
        self, authenticated_client, client, test_db, test_user
    ):
        from backend.db import task_queries
        from shared.database import ProjectGrant

        team, admin, _ = self._team_with(
            authenticated_client, client, test_db, role="admin"
        )
        project = task_queries.create_project(test_db, test_user.id, name="P")
        collab_queries.create_project_grant(
            test_db,
            test_user.id,
            project,
            principal_type="team",
            principal_id=team["id"],
            role="viewer",
        )
        with _As(admin):
            assert client.delete(f"/api/v1/teams/{team['id']}").status_code == 403
        assert (
            authenticated_client.delete(f"/api/v1/teams/{team['id']}").status_code
            == 204
        )
        assert test_db.query(Team).filter(Team.id == team["id"]).count() == 0
        assert (
            test_db.query(ProjectGrant)
            .filter(ProjectGrant.principal_id == team["id"])
            .count()
            == 0
        )


class TestInviteLinks:
    def test_link_lifecycle(self, authenticated_client, client, test_db):
        team = _create_team(authenticated_client)
        created = authenticated_client.post(
            f"/api/v1/teams/{team['id']}/invites",
            json={"role": "member", "max_uses": 1},
        )
        assert created.status_code == 201, created.text
        invite = created.json()
        assert len(invite["token"]) == 43
        assert invite["uses"] == 0

        joiner = _user(test_db, "joiner@example.com", "Joiner")
        with _As(joiner):
            preview = client.get(f"/api/v1/team-invites/{invite['token']}")
            assert preview.status_code == 200
            assert preview.json()["name"] == "Collab Crew"
            assert preview.json()["member_count"] == 1

            accepted = client.post(f"/api/v1/team-invites/{invite['token']}/accept")
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()["role"] == "member"
            assert client.get(f"/api/v1/teams/{team['id']}").status_code == 200

        # max_uses=1 is now spent — for anyone, the joiner included — and it
        # looks exactly like an unknown token.
        second = _user(test_db, "second@example.com")
        for who in (joiner, second):
            with _As(who):
                assert (
                    client.post(
                        f"/api/v1/team-invites/{invite['token']}/accept"
                    ).status_code
                    == 404
                )
        with _As(second):
            assert (
                client.get(f"/api/v1/team-invites/{invite['token']}").status_code == 404
            )
            assert client.get("/api/v1/team-invites/nope").status_code == 404

        listed = authenticated_client.get(f"/api/v1/teams/{team['id']}/invites").json()
        assert listed[0]["uses"] == 1

    def test_revoked_and_expired_look_unknown(
        self, authenticated_client, client, test_db
    ):
        team = _create_team(authenticated_client)
        revoked = authenticated_client.post(
            f"/api/v1/teams/{team['id']}/invites", json={}
        ).json()
        assert (
            authenticated_client.delete(
                f"/api/v1/teams/{team['id']}/invites/{revoked['id']}"
            ).status_code
            == 204
        )
        expired = authenticated_client.post(
            f"/api/v1/teams/{team['id']}/invites", json={"expires_in_days": 1}
        ).json()
        row = test_db.query(TeamInvite).filter(TeamInvite.id == expired["id"]).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        test_db.commit()

        visitor = _user(test_db, "visitor@example.com")
        with _As(visitor):
            for token in (revoked["token"], expired["token"], "garbage"):
                assert client.get(f"/api/v1/team-invites/{token}").status_code == 404
                assert (
                    client.post(f"/api/v1/team-invites/{token}/accept").status_code
                    == 404
                )
        # Revoked links drop out of the list; expired ones stay until revoked.
        listed = authenticated_client.get(f"/api/v1/teams/{team['id']}/invites").json()
        assert [i["id"] for i in listed] == [expired["id"]]

    def test_members_cannot_mint_links(self, authenticated_client, client, test_db):
        team = _create_team(authenticated_client)
        member = _user(test_db, "member@example.com")
        authenticated_client.post(
            f"/api/v1/teams/{team['id']}/members", json={"email": member.email}
        )
        with _As(member):
            client.post(f"/api/v1/teams/{team['id']}/members/accept")
            assert (
                client.post(f"/api/v1/teams/{team['id']}/invites", json={}).status_code
                == 403
            )
            assert client.get(f"/api/v1/teams/{team['id']}/invites").status_code == 403


class TestSeatGating:
    """The overlay seam (§6): a registered capability hook can deny a seat and
    the API answers 402. With nothing registered, everything passes."""

    def test_denied_seat_is_402(self, authenticated_client, monkeypatch, test_db):
        seen: list[tuple[str, dict]] = []

        def hook(db, user_id, capability, context):
            seen.append((capability, context))
            if context.get("seats", 0) > 1:
                return "Team seats need the Teams plan"
            return None

        monkeypatch.setattr(hooks, "_capability_hooks", [hook])
        team = _create_team(authenticated_client)  # 1 seat: allowed
        denied = authenticated_client.post(
            f"/api/v1/teams/{team['id']}/members", json={"email": "two@example.com"}
        )
        assert denied.status_code == 402, denied.text
        assert denied.json() == {
            "detail": "Team seats need the Teams plan",
            "capability": hooks.CAPABILITY_TEAM_SEAT,
        }
        assert [c for c, _ in seen] == [
            hooks.CAPABILITY_TEAM_SEAT,
            hooks.CAPABILITY_TEAM_SEAT,
        ]
        assert seen[1][1]["seats"] == 2
        # Nothing was written.
        assert (
            test_db.query(TeamMember).filter(TeamMember.team_id == team["id"]).count()
            == 1
        )

    def test_join_link_is_gated_too(
        self, authenticated_client, client, test_db, monkeypatch
    ):
        team = _create_team(authenticated_client)
        invite = authenticated_client.post(
            f"/api/v1/teams/{team['id']}/invites", json={}
        ).json()
        monkeypatch.setattr(
            hooks, "_capability_hooks", [lambda db, u, cap, ctx: "no seats"]
        )
        joiner = _user(test_db, "joiner@example.com")
        with _As(joiner):
            assert (
                client.post(
                    f"/api/v1/team-invites/{invite['token']}/accept"
                ).status_code
                == 402
            )
