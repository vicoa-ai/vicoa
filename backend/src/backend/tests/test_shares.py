"""Share links (collaboration §3.4 / §10.5, P4).

Two surfaces, both driven over HTTP:

* the owner API — who may mint / list / revoke a link (admin on the target,
  the same floor as the per-email session shares);
* the public API — what a token reaches, and the rule that every way a
  token can fail (unknown, revoked, expired, wrong audience, id not covered,
  DELETED target) answers the *same* 404, so the token space is not an
  oracle.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete as sa_delete
from sqlalchemy.orm import sessionmaker

from backend.auth.dependencies import (
    get_current_claims,
    get_current_user,
    get_optional_current_user,
)
from backend.db import share_queries
from backend.main import app
from shared import ratelimit, storage
from shared.auth.tokens import TokenClaims
from shared.database.actor import Actor, set_session_actor
from shared.database import (
    AgentInstance,
    AgentType,
    Message,
    MessageAttachment,
    Project,
    ProjectGrant,
    SenderType,
    ShareLink,
    Task,
    TaskLabel,
    User,
)
from shared.database.enums import AgentStatus

NOT_FOUND = {"detail": "Share not found"}


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


def _user(db, email: str, name: str) -> User:
    user = User(
        id=uuid4(),
        email=email,
        display_name=name,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    return user


def _message(db, instance: AgentInstance, content: str, *, sender=None) -> Message:
    msg = Message(
        agent_instance_id=instance.id,
        sender_type=SenderType.USER if sender is not None else SenderType.AGENT,
        sender_user_id=sender.id if sender is not None else None,
        content=content,
        requires_user_input=False,
    )
    db.add(msg)
    db.flush()
    return msg


class World:
    def __init__(self, db, owner: User) -> None:
        self.db = db
        self.owner = owner
        self.project = Project(
            user_id=owner.id, name="Shared Board", key="SHB", task_counter=3
        )
        db.add(self.project)
        db.flush()
        self.label = TaskLabel(user_id=owner.id, name="bug", color="#ff0000")
        db.add(self.label)
        db.flush()
        self.task = Task(
            user_id=owner.id,
            project_id=self.project.id,
            number=1,
            title="Do the thing",
            status="todo",
        )
        self.task_done = Task(
            user_id=owner.id,
            project_id=self.project.id,
            number=2,
            title="Done thing",
            status="done",
        )
        db.add_all([self.task, self.task_done])
        db.flush()
        self.task.labels.append(self.label)

        self.agent_type = AgentType(
            user_id=owner.id, name="claude code", is_active=True
        )
        db.add(self.agent_type)
        db.flush()
        self.instance = AgentInstance(
            agent_type_id=self.agent_type.id,
            user_id=owner.id,
            project_id=self.project.id,
            status=AgentStatus.ACTIVE,
            name="Fix the build",
            home_dir="/Users/owner",
            project="~/code/thing",
            session_config={
                "agent": "claude",
                "model": "opus",
                "permission_mode": "acceptEdits",
                "api_key": "should-not-leak",
            },
            instance_metadata={"worktree_name": "wt-1", "source": "app", "secret": 1},
        )
        self.archived = AgentInstance(
            agent_type_id=self.agent_type.id,
            user_id=owner.id,
            project_id=self.project.id,
            status=AgentStatus.COMPLETED,
            name="Old",
        )
        self.deleted = AgentInstance(
            agent_type_id=self.agent_type.id,
            user_id=owner.id,
            project_id=self.project.id,
            status=AgentStatus.DELETED,
            name="Gone",
        )
        self.other_instance = AgentInstance(
            agent_type_id=self.agent_type.id,
            user_id=owner.id,
            status=AgentStatus.ACTIVE,
            name="Unrelated",
        )
        db.add_all([self.instance, self.archived, self.deleted, self.other_instance])
        db.flush()
        self.m1 = _message(db, self.instance, "hello", sender=owner)
        self.m2 = _message(db, self.instance, "working on it")
        self.m3 = _message(db, self.instance, "done")
        self.other_message = _message(db, self.other_instance, "private")
        self.attachment = MessageAttachment(
            user_id=owner.id,
            agent_instance_id=self.instance.id,
            s3_key="k/1.png",
            mime_type="image/png",
            size_bytes=3,
        )
        self.other_attachment = MessageAttachment(
            user_id=owner.id,
            agent_instance_id=self.other_instance.id,
            s3_key="k/2.png",
            mime_type="image/png",
            size_bytes=3,
        )
        db.add_all([self.attachment, self.other_attachment])
        db.commit()


@pytest.fixture
def world(test_db, test_user) -> World:
    return World(test_db, test_user)


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(storage, "download_attachment", lambda key: b"png")
    ratelimit.public_share_limiter.reset()
    yield
    ratelimit.public_share_limiter.reset()


def _as(client: TestClient, user: User | None):
    """Authenticate `client` as `user` (None = anonymous) for the public
    router's optional dependency and the owner router's hard one."""
    for dep in (get_current_user, get_optional_current_user, get_current_claims):
        app.dependency_overrides.pop(dep, None)
    if user is None:
        app.dependency_overrides[get_optional_current_user] = lambda: None
        return client

    def override_user():
        return user

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_optional_current_user] = override_user
    app.dependency_overrides[get_current_claims] = lambda: TokenClaims(
        user_id=user.id, email=user.email, display_name=user.display_name
    )
    return client


def _mint(client: TestClient, body: dict) -> dict:
    response = client.post("/api/v1/shares", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Owner side
# ---------------------------------------------------------------------------


class TestOwnerApi:
    def test_create_session_link_and_list(self, client, world):
        _as(client, world.owner)
        link = _mint(
            client, {"kind": "session", "agent_instance_id": str(world.instance.id)}
        )
        assert len(link["token"]) == 43
        assert link["audience"] == "public"
        assert link["allow_comments"] is False
        # Both display flags are opt-in.
        assert link["show_owner"] is False
        assert link["show_branch"] is False
        assert link["created_by"]["name"] == "Test User"
        assert "email" not in link["created_by"]

        listed = client.get(
            f"/api/v1/shares?agent_instance_id={world.instance.id}"
        ).json()
        assert [row["id"] for row in listed] == [link["id"]]

    def test_request_shape_is_validated(self, client, world):
        _as(client, world.owner)
        bad = [
            {"kind": "session", "project_id": str(world.project.id)},
            {
                "kind": "project",
                "scopes": ["tasks"],
                "agent_instance_id": str(world.instance.id),
            },
            {
                "kind": "project",
                "scopes": ["sessions"],
                "project_id": str(world.project.id),
                "allow_comments": True,  # comments need the tasks scope
            },
            {
                # A project link must carry something.
                "kind": "project",
                "scopes": [],
                "project_id": str(world.project.id),
            },
            {
                "kind": "session",
                "agent_instance_id": str(world.instance.id),
                "scopes": ["tasks"],  # a session link has no scopes
            },
            {
                "kind": "project",
                "scopes": ["tasks"],
                "project_id": str(world.project.id),
                "filters": {"tasks": {"bogus": 1}},
            },
            {
                "kind": "project",
                "scopes": ["sessions"],
                "project_id": str(world.project.id),
                "filters": {"sessions": {"statuses": ["DELETED"]}},
            },
            {
                # Filters are keyed by scope now; a flat dict is not a shape.
                "kind": "project",
                "scopes": ["tasks"],
                "project_id": str(world.project.id),
                "filters": {"statuses": ["todo"]},
            },
        ]
        for body in bad:
            assert client.post("/api/v1/shares", json=body).status_code == 422, body

    def test_deleted_session_is_not_shareable(self, client, world):
        _as(client, world.owner)
        assert (
            client.post(
                "/api/v1/shares",
                json={"kind": "session", "agent_instance_id": str(world.deleted.id)},
            ).status_code
            == 404
        )

    @pytest.mark.parametrize(
        "role, expected",
        [
            (None, 404),  # stranger: invisible
            ("viewer", 403),
            ("editor", 403),
            ("admin", 201),
        ],
    )
    def test_minting_needs_admin_on_the_target(self, client, world, role, expected):
        subject = _user(world.db, "s@example.com", "Subject")
        if role is not None:
            world.db.add(
                ProjectGrant(
                    project_id=world.project.id,
                    principal_type="user",
                    principal_id=subject.id,
                    role=role,
                    scopes=["tasks", "sessions"],
                    granted_by_user_id=world.owner.id,
                )
            )
        world.db.commit()
        _as(client, subject)
        for body in (
            {"kind": "session", "agent_instance_id": str(world.instance.id)},
            {
                "kind": "project",
                "scopes": ["tasks"],
                "project_id": str(world.project.id),
            },
            {
                "kind": "project",
                "scopes": ["sessions"],
                "project_id": str(world.project.id),
            },
        ):
            assert client.post("/api/v1/shares", json=body).status_code == expected, (
                body
            )

    def test_scoped_admin_cannot_publish_the_area_they_cannot_see(self, client, world):
        subject = _user(world.db, "s@example.com", "Subject")
        world.db.add(
            ProjectGrant(
                project_id=world.project.id,
                principal_type="user",
                principal_id=subject.id,
                role="admin",
                scopes=["tasks"],
                granted_by_user_id=world.owner.id,
            )
        )
        world.db.commit()
        _as(client, subject)
        assert (
            client.post(
                "/api/v1/shares",
                json={
                    "kind": "project",
                    "scopes": ["tasks"],
                    "project_id": str(world.project.id),
                },
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/api/v1/shares",
                json={
                    "kind": "project",
                    "scopes": ["sessions"],
                    "project_id": str(world.project.id),
                },
            ).status_code
            == 404
        )

    def test_revoke_is_idempotent_and_drops_from_list(self, client, world):
        _as(client, world.owner)
        link = _mint(
            client,
            {
                "kind": "project",
                "scopes": ["tasks"],
                "project_id": str(world.project.id),
            },
        )
        assert client.delete(f"/api/v1/shares/{link['id']}").status_code == 204
        assert client.delete(f"/api/v1/shares/{link['id']}").status_code == 204
        assert client.get(f"/api/v1/shares?project_id={world.project.id}").json() == []
        row = world.db.get(ShareLink, UUID(link["id"]))
        assert row is not None and row.revoked_at is not None  # kept for audit

    def test_stranger_cannot_revoke_or_list(self, client, world):
        _as(client, world.owner)
        link = _mint(
            client, {"kind": "session", "agent_instance_id": str(world.instance.id)}
        )
        stranger = _user(world.db, "x@example.com", "X")
        world.db.commit()
        _as(client, stranger)
        assert client.delete(f"/api/v1/shares/{link['id']}").status_code == 404
        assert (
            client.get(
                f"/api/v1/shares?agent_instance_id={world.instance.id}"
            ).status_code
            == 404
        )
        # The link still works for everyone.
        _as(client, None)
        assert client.get(f"/api/v1/public/shares/{link['token']}").status_code == 200

    def test_list_needs_exactly_one_target(self, client, world):
        _as(client, world.owner)
        assert client.get("/api/v1/shares").status_code == 400


# ---------------------------------------------------------------------------
# Public side: the uniform 404
# ---------------------------------------------------------------------------


class TestUniform404:
    def _session_link(self, client, world, **extra) -> dict:
        _as(client, world.owner)
        return _mint(
            client,
            {"kind": "session", "agent_instance_id": str(world.instance.id), **extra},
        )

    def test_unknown_revoked_expired_all_identical(self, client, world):
        live = self._session_link(client, world)
        revoked = self._session_link(client, world)
        expired = self._session_link(client, world, expires_in_days=1)
        client.delete(f"/api/v1/shares/{revoked['id']}")
        row = world.db.get(ShareLink, UUID(expired["id"]))
        assert row is not None
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        world.db.commit()

        _as(client, None)
        bodies = set()
        for token in ("nope", "x" * 43, "x" * 200, revoked["token"], expired["token"]):
            response = client.get(f"/api/v1/public/shares/{token}")
            assert response.status_code == 404, token
            bodies.add(response.text)
            assert response.headers["cache-control"] == "private, no-store"
            assert "noindex" in response.headers["x-robots-tag"]
        assert bodies == {'{"detail":"Share not found"}'}
        assert client.get(f"/api/v1/public/shares/{live['token']}").status_code == 200

    def test_authenticated_audience_is_404_to_anonymous(self, client, world):
        link = self._session_link(client, world, audience="authenticated")
        _as(client, None)
        assert client.get(f"/api/v1/public/shares/{link['token']}").json() == NOT_FOUND
        visitor = _user(world.db, "v@example.com", "Visitor")
        world.db.commit()
        _as(client, visitor)
        body = client.get(f"/api/v1/public/shares/{link['token']}").json()
        assert body["audience"] == "authenticated"
        assert body["viewer"]["name"] == "Visitor"

    def test_deleted_session_disappears_behind_a_live_link(self, client, world):
        link = self._session_link(client, world)
        world.instance.status = AgentStatus.DELETED
        world.db.commit()
        _as(client, None)
        assert client.get(f"/api/v1/public/shares/{link['token']}").json() == NOT_FOUND

    def test_deleting_the_target_cascades(self, client, world):
        link = self._session_link(client, world)
        # A DB-level delete (what the API's delete path and account deletion
        # do), so the ON DELETE CASCADE on share_links is what's under test.
        world.db.execute(
            sa_delete(AgentInstance).where(AgentInstance.id == world.instance.id)
        )
        world.db.commit()
        _as(client, None)
        assert client.get(f"/api/v1/public/shares/{link['token']}").json() == NOT_FOUND
        assert world.db.get(ShareLink, UUID(link["id"])) is None

    def test_ids_the_link_does_not_cover_are_404(self, client, world):
        link = self._session_link(client, world)
        t = link["token"]
        _as(client, None)
        # Another session of the same owner, a foreign attachment, a task
        # (no board on a session link), a made-up id.
        for path in (
            f"/sessions/{world.other_instance.id}",
            f"/sessions/{world.other_instance.id}/messages",
            f"/attachments/{world.other_attachment.id}",
            f"/tasks/{world.task.id}/timeline",
            "/board",
            f"/sessions/{uuid4()}/messages",
        ):
            response = client.get(f"/api/v1/public/shares/{t}{path}")
            assert response.status_code == 404, path
            assert response.json() == NOT_FOUND, path


# ---------------------------------------------------------------------------
# Public side: session links
# ---------------------------------------------------------------------------


class TestPublicSession:
    @pytest.fixture
    def token(self, client, world) -> str:
        _as(client, world.owner)
        link = _mint(
            client, {"kind": "session", "agent_instance_id": str(world.instance.id)}
        )
        _as(client, None)
        return link["token"]

    def test_meta_strips_what_a_viewer_must_not_see(self, client, world, token):
        body = client.get(f"/api/v1/public/shares/{token}").json()
        assert body["kind"] == "session"
        # A default link says nothing about who shared it, nor the branch.
        assert body["owner"] is None
        assert body["viewer_is_owner"] is False
        session = body["session"]
        assert session["name"] == "Fix the build"
        assert session["agent_type_name"] == "claude code"
        assert session["worktree_name"] is None
        assert session["message_count"] == 3
        # The display subset only — never the raw config or metadata.
        assert session["session_config"] == {
            "agent": "claude",
            "model": "opus",
            "permission_mode": "acceptEdits",
        }
        for key in ("home_dir", "machine_id", "instance_metadata", "project"):
            assert key not in session
        assert body["viewer"] is None

    def test_display_flags_opt_in_owner_and_branch(self, client, world):
        _as(client, world.owner)
        link = _mint(
            client,
            {
                "kind": "session",
                "agent_instance_id": str(world.instance.id),
                "show_owner": True,
                "show_branch": True,
            },
        )
        assert link["show_owner"] is True and link["show_branch"] is True
        # The owner looking at their own link: the page may deep-link back.
        mine = client.get(f"/api/v1/public/shares/{link['token']}").json()
        assert mine["viewer_is_owner"] is True
        _as(client, None)
        body = client.get(f"/api/v1/public/shares/{link['token']}").json()
        assert body["owner"] == {
            "type": "user",
            "id": str(world.owner.id),
            "name": "Test User",
            "avatar_image_uri": None,
            "emoji": None,
            "updated_at": body["owner"]["updated_at"],
        }
        assert "email" not in body["owner"]
        assert body["viewer_is_owner"] is False
        assert body["session"]["worktree_name"] == "wt-1"
        # The per-session poll and the project list honour the same flag.
        polled = client.get(
            f"/api/v1/public/shares/{link['token']}/sessions/{world.instance.id}"
        ).json()
        assert polled["worktree_name"] == "wt-1"
        _as(client, world.owner)
        plain = _mint(
            client,
            {
                "kind": "project",
                "scopes": ["sessions"],
                "project_id": str(world.project.id),
            },
        )
        _as(client, None)
        rows = client.get(f"/api/v1/public/shares/{plain['token']}/sessions").json()
        assert all(row["worktree_name"] is None for row in rows["items"])

    def test_messages_first_page_then_poll_watermark(self, client, world, token):
        base = f"/api/v1/public/shares/{token}/sessions/{world.instance.id}/messages"
        page = client.get(f"{base}?limit=2").json()
        assert [m["content"] for m in page["messages"]] == ["working on it", "done"]
        assert page["has_more"] is True
        for m in page["messages"]:
            assert "sender_user_email" not in m
            assert "sender_user_id" not in m
        # Older history via before=.
        older = client.get(f"{base}?before={page['messages'][0]['id']}").json()
        assert [m["content"] for m in older["messages"]] == ["hello"]
        assert older["has_more"] is False
        assert older["messages"][0]["sender_user_display_name"] == "Test User"
        assert older["messages"][0]["created_at"].endswith("Z")
        # Steady-state poll: nothing new → empty page.
        tail = page["messages"][-1]["id"]
        assert client.get(f"{base}?after={tail}").json() == {
            "messages": [],
            "has_more": False,
        }
        _message(world.db, world.instance, "one more")
        world.db.commit()
        poll = client.get(f"{base}?after={tail}").json()
        assert [m["content"] for m in poll["messages"]] == ["one more"]
        # A cursor from another session is unknown, not a leak.
        assert client.get(f"{base}?after={world.other_message.id}").json() == {
            "messages": [],
            "has_more": False,
        }
        assert client.get(f"{base}?after={tail}&before={tail}").status_code == 400

    def test_attachment_served_only_when_covered(self, client, world, token):
        ok = client.get(
            f"/api/v1/public/shares/{token}/attachments/{world.attachment.id}"
        )
        assert ok.status_code == 200
        assert ok.content == b"png"
        assert ok.headers["cache-control"] == "private, no-store"
        assert ok.headers["content-type"] == "image/png"
        assert (
            client.get(
                f"/api/v1/public/shares/{token}/attachments/{world.other_attachment.id}"
            ).status_code
            == 404
        )

    def test_sessions_list_on_a_session_link_is_just_that_session(
        self, client, world, token
    ):
        page = client.get(f"/api/v1/public/shares/{token}/sessions").json()
        assert [s["id"] for s in page["items"]] == [str(world.instance.id)]

    def test_view_counted_once_per_client_window(
        self, client, world, token, monkeypatch
    ):
        # The background bump opens its own session; point it at the test DB.
        monkeypatch.setattr(
            share_queries, "SessionLocal", sessionmaker(bind=world.db.get_bind())
        )
        for _ in range(3):
            assert client.get(f"/api/v1/public/shares/{token}").status_code == 200
        world.db.expire_all()
        row = world.db.query(ShareLink).filter(ShareLink.token == token).one()
        assert row.view_count == 1
        assert row.last_accessed_at is not None


# ---------------------------------------------------------------------------
# Public side: project sessions
# ---------------------------------------------------------------------------


class TestPublicProjectSessions:
    def _link(self, client, world, filters=None) -> str:
        _as(client, world.owner)
        body = {
            "kind": "project",
            "scopes": ["sessions"],
            "project_id": str(world.project.id),
        }
        if filters is not None:
            body["filters"] = {"sessions": filters}
        link = _mint(client, body)
        _as(client, None)
        return link["token"]

    def test_default_excludes_archived_and_deleted(self, client, world):
        token = self._link(client, world)
        meta = client.get(f"/api/v1/public/shares/{token}").json()
        assert meta["project"] == {
            "id": str(world.project.id),
            "name": "Shared Board",
            "key": "SHB",
            "color": None,
            "icon": None,
        }
        page = client.get(f"/api/v1/public/shares/{token}/sessions").json()
        assert [s["id"] for s in page["items"]] == [str(world.instance.id)]
        assert page["total"] == 1
        # Transcript reachable for a covered session, not for the others.
        base = f"/api/v1/public/shares/{token}/sessions"
        assert client.get(f"{base}/{world.instance.id}/messages").status_code == 200
        assert client.get(f"{base}/{world.archived.id}/messages").status_code == 404
        assert client.get(f"{base}/{world.deleted.id}/messages").status_code == 404
        assert (
            client.get(f"{base}/{world.other_instance.id}/messages").status_code == 404
        )

    def test_statuses_filter_replaces_the_default(self, client, world):
        token = self._link(client, world, {"statuses": ["COMPLETED"]})
        page = client.get(f"/api/v1/public/shares/{token}/sessions").json()
        assert [s["id"] for s in page["items"]] == [str(world.archived.id)]

    def test_new_sessions_appear_and_date_filter_is_live(self, client, world):
        token = self._link(
            client,
            world,
            {"date_from": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()},
        )
        late = AgentInstance(
            agent_type_id=world.agent_type.id,
            user_id=world.owner.id,
            project_id=world.project.id,
            status=AgentStatus.ACTIVE,
            name="Later",
        )
        early = AgentInstance(
            agent_type_id=world.agent_type.id,
            user_id=world.owner.id,
            project_id=world.project.id,
            status=AgentStatus.ACTIVE,
            name="Ancient",
            started_at=datetime(2020, 1, 1),
        )
        world.db.add_all([late, early])
        world.db.commit()
        page = client.get(f"/api/v1/public/shares/{token}/sessions").json()
        ids = {s["id"] for s in page["items"]}
        assert str(late.id) in ids and str(world.instance.id) in ids
        assert str(early.id) not in ids

    def test_board_is_not_exposed_on_a_sessions_link(self, client, world):
        token = self._link(client, world)
        assert client.get(f"/api/v1/public/shares/{token}/board").json() == NOT_FOUND


# ---------------------------------------------------------------------------
# Public side: project board + the single write
# ---------------------------------------------------------------------------


class TestPublicBoard:
    def _link(self, client, world, **extra) -> dict:
        _as(client, world.owner)
        if "filters" in extra:
            extra["filters"] = {"tasks": extra["filters"]}
        link = _mint(
            client,
            {
                "kind": "project",
                "scopes": ["tasks"],
                "project_id": str(world.project.id),
                **extra,
            },
        )
        _as(client, None)
        return link

    def test_board_tasks_labels_and_filters(self, client, world):
        token = self._link(client, world)["token"]
        board = client.get(f"/api/v1/public/shares/{token}/board").json()
        assert board["project"]["key"] == "SHB"
        assert {t["identifier"] for t in board["tasks"]} == {"SHB-1", "SHB-2"}
        assert [label["name"] for label in board["labels"]] == ["bug"]
        # Sessions are never exposed on a board link.
        assert (
            client.get(f"/api/v1/public/shares/{token}/sessions").json()["items"] == []
        )
        assert (
            client.get(
                f"/api/v1/public/shares/{token}/sessions/{world.instance.id}/messages"
            ).status_code
            == 404
        )

        filtered = self._link(client, world, filters={"statuses": ["todo"]})["token"]
        board = client.get(f"/api/v1/public/shares/{filtered}/board").json()
        assert [t["identifier"] for t in board["tasks"]] == ["SHB-1"]
        # A filtered-out task is invisible, not forbidden.
        assert (
            client.get(
                f"/api/v1/public/shares/{filtered}/tasks/{world.task_done.id}/timeline"
            ).json()
            == NOT_FOUND
        )
        by_label = self._link(
            client, world, filters={"label_ids": [str(world.label.id)]}
        )["token"]
        board = client.get(f"/api/v1/public/shares/{by_label}/board").json()
        assert [t["identifier"] for t in board["tasks"]] == ["SHB-1"]

    def test_timeline_readable_comments_gated(self, client, world):
        token = self._link(client, world)["token"]
        timeline = client.get(
            f"/api/v1/public/shares/{token}/tasks/{world.task.id}/timeline"
        )
        assert timeline.status_code == 200
        assert timeline.json()["comments"] == []
        # A public link never takes a comment — from anyone.
        visitor = _user(world.db, "v@example.com", "Visitor")
        world.db.commit()
        _as(client, visitor)
        response = client.post(
            f"/api/v1/public/shares/{token}/tasks/{world.task.id}/comments",
            json={"body": "hi"},
        )
        assert response.status_code == 403

    def test_allow_comments_is_the_one_write(self, client, world):
        # Comments do not need the authenticated audience: a public board can
        # take them, from visitors who sign in.
        link = self._link(client, world, allow_comments=True)
        token = link["token"]
        meta_anon = client.get(f"/api/v1/public/shares/{token}").json()
        assert meta_anon["allow_comments"] is False  # not for *this* visitor
        assert meta_anon["comments_available"] is True  # the sign-in prompt
        assert (
            client.post(
                f"/api/v1/public/shares/{token}/tasks/{world.task.id}/comments",
                json={"body": "anon"},
            ).status_code
            == 401
        )

        visitor = _user(world.db, "v@example.com", "Visitor")
        world.db.commit()
        _as(client, visitor)
        meta = client.get(f"/api/v1/public/shares/{token}").json()
        assert meta["allow_comments"] is True and meta["comments_available"] is True
        response = client.post(
            f"/api/v1/public/shares/{token}/tasks/{world.task.id}/comments",
            json={"body": "looks good"},
        )
        assert response.status_code == 201, response.text
        comments = response.json()["comments"]
        assert [c["body"] for c in comments] == ["looks good"]
        assert comments[0]["author"]["name"] == "Visitor"
        assert "email" not in comments[0]["author"]
        # Attributed to the real account, no grant row created.
        assert (
            world.db.query(ProjectGrant)
            .filter(ProjectGrant.principal_id == visitor.id)
            .count()
            == 0
        )
        # Nothing else is writable: the dashboard task routes still 404 for
        # the visitor (they hold no standing on the project).
        assert client.get(f"/api/v1/tasks/{world.task.id}").status_code == 404
        assert (
            client.patch(
                f"/api/v1/tasks/{world.task.id}", json={"title": "x"}
            ).status_code
            == 404
        )
        # Revoke → dead instantly, including for the commenter.
        _as(client, world.owner)
        client.delete(f"/api/v1/shares/{link['id']}")
        _as(client, visitor)
        assert (
            client.post(
                f"/api/v1/public/shares/{token}/tasks/{world.task.id}/comments",
                json={"body": "again"},
            ).json()
            == NOT_FOUND
        )

    def _owner_footprint(self, client, world):
        """The owner assigns themselves, changes status and comments, so their
        principal sits in every slot of the public payload."""
        _as(client, world.owner)
        # `_as` bypasses the real dependency, which is what stamps the actor
        # the activity listener attributes rows to.
        set_session_actor(world.db, Actor(type="user", id=world.owner.id))
        try:
            assert (
                client.patch(
                    f"/api/v1/tasks/{world.task.id}",
                    json={
                        "assignee_type": "user",
                        "assignee_id": str(world.owner.id),
                        "status": "in_progress",
                    },
                ).status_code
                == 200
            )
        finally:
            set_session_actor(world.db, None)
        assert (
            client.post(
                f"/api/v1/tasks/{world.task.id}/comments", json={"body": "mine"}
            ).status_code
            == 201
        )
        assert (
            client.put(
                f"/api/v1/tasks/{world.task.id}/reactions",
                json={
                    "target_type": "task",
                    "target_id": str(world.task.id),
                    "emoji": "👍",
                },
            ).status_code
            == 200
        )

    def _public_task_and_timeline(self, client, world, token):
        _as(client, None)
        board = client.get(f"/api/v1/public/shares/{token}/board").json()
        task = next(t for t in board["tasks"] if t["id"] == str(world.task.id))
        timeline = client.get(
            f"/api/v1/public/shares/{token}/tasks/{world.task.id}/timeline"
        ).json()
        return task, timeline

    def test_hidden_owner_is_hidden_everywhere(self, client, world):
        """`show_owner=False` anonymises the owner in every principal slot —
        assignee, comment author, activity actor, reactor — not just the
        sidebar card; the page reads "Owner" and carries no id or avatar."""
        self._owner_footprint(client, world)
        token = self._link(client, world)["token"]  # show_owner defaults off
        task, timeline = self._public_task_and_timeline(client, world, token)

        anon = {"type": "user", "id": None, "name": "Owner"}
        assert {k: task["assignee"][k] for k in anon} == anon
        assert task["assignee"]["avatar_image_uri"] is None
        assert task["assignee_id"] is None
        assert timeline["comments"][0]["author"]["name"] == "Owner"
        assert timeline["comments"][0]["author"]["id"] is None
        actors = {row["actor"]["name"] for row in timeline["activity"] if row["actor"]}
        assert actors == {"Owner"}
        assert [r["name"] for r in timeline["reactions"][0]["reactors"]] == ["Owner"]
        assert (
            str(world.owner.id)
            not in client.get(f"/api/v1/public/shares/{token}/board").text
        )

    def test_shown_owner_keeps_name_and_id(self, client, world):
        self._owner_footprint(client, world)
        token = self._link(client, world, show_owner=True)["token"]
        task, timeline = self._public_task_and_timeline(client, world, token)
        assert task["assignee"]["name"] == "Test User"
        assert task["assignee"]["id"] == str(world.owner.id)
        assert timeline["comments"][0]["author"]["name"] == "Test User"
        actors = {row["actor"]["name"] for row in timeline["activity"] if row["actor"]}
        assert actors == {"Test User"}

    def test_shown_owner_without_display_name_reads_owner(self, client, world):
        """A shown owner with no display name is "Owner", never "Unknown"; the
        avatar and id stay because the link opted in."""
        world.owner.display_name = None
        world.db.commit()
        self._owner_footprint(client, world)
        token = self._link(client, world, show_owner=True)["token"]
        task, timeline = self._public_task_and_timeline(client, world, token)
        assert task["assignee"]["name"] == "Owner"
        assert task["assignee"]["id"] == str(world.owner.id)
        assert timeline["comments"][0]["author"]["name"] == "Owner"

    def test_visitor_comments_keep_their_name_when_owner_is_hidden(self, client, world):
        self._owner_footprint(client, world)
        token = self._link(client, world, allow_comments=True)["token"]
        visitor = _user(world.db, "v@example.com", "Visitor")
        world.db.commit()
        _as(client, visitor)
        timeline = client.post(
            f"/api/v1/public/shares/{token}/tasks/{world.task.id}/comments",
            json={"body": "theirs"},
        ).json()
        by_author = {c["body"]: c["author"] for c in timeline["comments"]}
        assert by_author["mine"]["name"] == "Owner" and by_author["mine"]["id"] is None
        assert by_author["theirs"]["name"] == "Visitor"
        assert by_author["theirs"]["id"] == str(visitor.id)

    def test_comment_needs_a_covered_task(self, client, world):
        token = self._link(
            client,
            world,
            audience="authenticated",
            allow_comments=True,
            filters={"statuses": ["todo"]},
        )["token"]
        visitor = _user(world.db, "v@example.com", "Visitor")
        world.db.commit()
        _as(client, visitor)
        assert (
            client.post(
                f"/api/v1/public/shares/{token}/tasks/{world.task_done.id}/comments",
                json={"body": "hi"},
            ).json()
            == NOT_FOUND
        )


# ---------------------------------------------------------------------------
# Public side: one project link, both halves
# ---------------------------------------------------------------------------


class TestProjectScopes:
    """A project is shared once, with a content selection — not once per kind
    of content. Every project-shaped endpoint asks the link what it carries."""

    def _link(self, client, world, scopes, **extra) -> dict:
        _as(client, world.owner)
        link = _mint(
            client,
            {
                "kind": "project",
                "scopes": scopes,
                "project_id": str(world.project.id),
                **extra,
            },
        )
        _as(client, None)
        return link

    def test_both_scopes_are_one_link(self, client, world):
        link = self._link(client, world, ["sessions", "tasks"])
        assert link["scopes"] == ["tasks", "sessions"]  # stored in a stable order
        token = link["token"]
        meta = client.get(f"/api/v1/public/shares/{token}").json()
        assert meta["kind"] == "project"
        assert sorted(meta["scopes"]) == ["sessions", "tasks"]
        # One token reaches both halves.
        board = client.get(f"/api/v1/public/shares/{token}/board").json()
        assert {t["identifier"] for t in board["tasks"]} == {"SHB-1", "SHB-2"}
        page = client.get(f"/api/v1/public/shares/{token}/sessions").json()
        assert [s["id"] for s in page["items"]] == [str(world.instance.id)]

    def test_each_half_is_filtered_under_its_own_key(self, client, world):
        token = self._link(
            client,
            world,
            ["sessions", "tasks"],
            filters={
                "tasks": {"statuses": ["todo"]},
                "sessions": {"statuses": ["COMPLETED"]},
            },
        )["token"]
        board = client.get(f"/api/v1/public/shares/{token}/board").json()
        assert [t["identifier"] for t in board["tasks"]] == ["SHB-1"]
        page = client.get(f"/api/v1/public/shares/{token}/sessions").json()
        # The archived session is the only COMPLETED one.
        assert [s["id"] for s in page["items"]] == [str(world.archived.id)]

    def test_a_scope_the_link_does_not_carry_is_404(self, client, world):
        """Not "forbidden" — the same 404 an unknown token gets (§10.5)."""
        tasks_only = self._link(client, world, ["tasks"])["token"]
        assert (
            client.get(f"/api/v1/public/shares/{tasks_only}/sessions").json()["items"]
            == []
        )
        assert (
            client.get(
                f"/api/v1/public/shares/{tasks_only}/sessions/{world.instance.id}"
            ).json()
            == NOT_FOUND
        )
        sessions_only = self._link(client, world, ["sessions"])["token"]
        assert (
            client.get(f"/api/v1/public/shares/{sessions_only}/board").json()
            == NOT_FOUND
        )
        assert (
            client.get(
                f"/api/v1/public/shares/{sessions_only}/tasks/{world.task.id}/timeline"
            ).json()
            == NOT_FOUND
        )

    def test_dropping_a_scope_drops_its_filters(self, client, world):
        """Filters for a half the link does not carry are not stored — they
        would be dead weight that a later scope change silently revived."""
        link = self._link(
            client,
            world,
            ["tasks"],
            filters={
                "tasks": {"statuses": ["todo"]},
                "sessions": {"statuses": ["COMPLETED"]},
            },
        )
        assert link["filters"] == {"tasks": {"statuses": ["todo"]}}


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_bucket_drains_then_429_with_retry_after(self, client, world, monkeypatch):
        _as(client, world.owner)
        token = _mint(
            client, {"kind": "session", "agent_instance_id": str(world.instance.id)}
        )["token"]
        _as(client, None)
        tight = ratelimit.TokenBucketLimiter(rate=1 / 60, burst=3)
        monkeypatch.setattr(ratelimit, "public_share_limiter", tight)
        for _ in range(3):
            assert client.get(f"/api/v1/public/shares/{token}").status_code == 200
        blocked = client.get(f"/api/v1/public/shares/{token}")
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1
        # The owner API is untouched by the public bucket.
        _as(client, world.owner)
        assert (
            client.get(
                f"/api/v1/shares?agent_instance_id={world.instance.id}"
            ).status_code
            == 200
        )

    def test_client_key_prefers_the_configured_proxy_header(self, monkeypatch):
        from starlette.requests import Request as StarletteRequest

        from shared.config import settings

        def req(headers: dict[str, str]) -> StarletteRequest:
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [
                    (k.lower().encode(), v.encode()) for k, v in headers.items()
                ],
                "client": ("10.0.0.1", 1234),
            }
            return StarletteRequest(scope)

        monkeypatch.setattr(settings, "client_ip_header", "Fly-Client-IP")
        assert (
            ratelimit.client_ip(req({"Fly-Client-IP": "203.0.113.9"})) == "203.0.113.9"
        )
        assert ratelimit.client_ip(req({"X-Forwarded-For": "1.1.1.1"})) == "10.0.0.1"
        monkeypatch.setattr(settings, "client_ip_header", "X-Forwarded-For")
        assert (
            ratelimit.client_ip(req({"X-Forwarded-For": "1.1.1.1, 2.2.2.2"}))
            == "1.1.1.1"
        )
        monkeypatch.setattr(settings, "client_ip_header", "")
        assert ratelimit.client_ip(req({"Fly-Client-IP": "203.0.113.9"})) == "10.0.0.1"

    def test_limiter_refills(self):
        limiter = ratelimit.TokenBucketLimiter(rate=1000, burst=1)
        assert limiter.acquire("a") is None
        wait = limiter.acquire("a")
        assert wait is not None and 0 < wait <= 0.001
        assert limiter.acquire("b") is None  # separate key


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def test_resolve_share_never_widens(world):
    """The resolver is the only place a token turns into a grant; its failure
    modes are all None."""
    from shared import access

    db = world.db
    link = ShareLink(
        token="t" * 43,
        created_by_user_id=world.owner.id,
        kind="session",
        agent_instance_id=world.instance.id,
        audience="authenticated",
    )
    db.add(link)
    db.commit()
    assert access.resolve_share(db, "t" * 43) is None  # anonymous
    grant = access.resolve_share(db, "t" * 43, user_id=world.owner.id)
    assert grant is not None and grant.instance_id == world.instance.id
    assert grant.allow_comments is False
    # A session link carries no project scopes, so every project-shaped
    # question it is asked answers "no".
    assert grant.scopes == frozenset()
    assert not grant.covers("tasks") and not grant.covers("sessions")
    assert access.resolve_share(db, "", user_id=world.owner.id) is None
    assert access.resolve_share(db, "t" * 44, user_id=world.owner.id) is None
    link.revoked_at = datetime.now(timezone.utc)
    db.commit()
    assert access.resolve_share(db, "t" * 43, user_id=world.owner.id) is None


def test_should_count_view_window():
    link_id = uuid4()
    assert share_queries.should_count_view(link_id, "1.2.3.4") is True
    assert share_queries.should_count_view(link_id, "1.2.3.4") is False
    assert share_queries.should_count_view(link_id, "5.6.7.8") is True


def test_account_deletion_takes_the_links_with_it(client, world, monkeypatch):
    """§10.8: deleting the owner kills every link they minted — the public page
    answers the uniform 404 the moment the row is gone."""
    from backend.db.queries import delete_user_account

    monkeypatch.setattr(
        "backend.db.queries.run_user_delete_hooks", lambda *a, **k: None
    )
    _as(client, world.owner)
    token = _mint(
        client,
        {"kind": "project", "scopes": ["tasks"], "project_id": str(world.project.id)},
    )["token"]
    owner_id = world.owner.id
    delete_user_account(world.db, owner_id)
    assert world.db.query(ShareLink).count() == 0
    _as(client, None)
    assert client.get(f"/api/v1/public/shares/{token}").json() == NOT_FOUND
