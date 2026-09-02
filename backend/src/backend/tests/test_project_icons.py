"""Project image-icon: upload/serve/delete, git-avatar seed, precedence (§4d/§4e)."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image

import shared.project_icons as icons
import shared.storage as storage_module
from shared.database import Project


def _png_bytes(width: int = 64, height: int = 64, color=(20, 120, 200)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), color=color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _seed_uses_test_engine(test_db, monkeypatch):
    """Bind the seed's own-session factory to the test container's engine.

    seed_project_icon() opens ``SessionLocal`` (module-level, bound to the
    settings DB) because it runs as a background task; point it at the test DB so
    both direct calls and GET /projects-triggered seeds hit the same database.
    """
    from sqlalchemy.orm import sessionmaker

    local = sessionmaker(bind=test_db.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr(icons, "SessionLocal", local)


@pytest.fixture
def fake_icon_storage(monkeypatch):
    """In-memory stand-in for the S3 icon object store."""
    store: dict[str, tuple[bytes, str]] = {}

    def upload(key, data, mime_type):
        store[key] = (data, mime_type)

    def download_object(key):
        return store[key]

    def delete_object(key):
        store.pop(key, None)

    monkeypatch.setattr(storage_module, "upload_attachment", upload)
    monkeypatch.setattr(storage_module, "download_object", download_object)
    monkeypatch.setattr(storage_module, "delete_object", delete_object)
    return store


class TestOwnerAvatarUrl:
    @pytest.mark.parametrize(
        "remote,expected",
        [
            (
                "git@github.com:vicoa-ai/vicoa.git",
                "https://github.com/vicoa-ai.png?size=200",
            ),
            (
                "https://github.com/vicoa-ai/vicoa.git",
                "https://github.com/vicoa-ai.png?size=200",
            ),
            (
                "https://github.com/vicoa-ai/vicoa",
                "https://github.com/vicoa-ai.png?size=200",
            ),
            (
                "ssh://git@github.com/octocat/hello",
                "https://github.com/octocat.png?size=200",
            ),
            ("git@gitlab.com:group/proj.git", "https://gitlab.com/group.png"),
        ],
    )
    def test_supported_hosts(self, remote, expected):
        assert icons.owner_avatar_url(remote) == expected

    @pytest.mark.parametrize(
        "remote",
        [
            None,
            "",
            "git@bitbucket.org:team/repo.git",  # unsupported host
            "https://example.com/a/b.git",  # unsupported host
            "not a url",
            "git@github.com:../evil",  # bad owner chars → skip
        ],
    )
    def test_unsupported_or_bad(self, remote):
        assert icons.owner_avatar_url(remote) is None


class _FakeResp:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


class _FakeClient:
    def __init__(self, content, *args, **kwargs):
        self._content = content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url):
        return _FakeResp(self._content)


class TestGitSeed:
    def _make_project(self, db, user_id, **kw):
        project = Project(user_id=user_id, name="alpha", **kw)
        db.add(project)
        db.commit()
        return project

    def test_seed_from_github_sets_git_source(
        self, test_db, test_user, fake_icon_storage, monkeypatch
    ):
        project = self._make_project(
            test_db, test_user.id, git_remote_url="git@github.com:vicoa-ai/alpha.git"
        )
        monkeypatch.setattr(
            icons.httpx, "Client", lambda *a, **k: _FakeClient(_png_bytes())
        )
        icons.seed_project_icon(project.id)
        test_db.expire_all()
        refreshed = test_db.get(Project, project.id)
        assert refreshed.icon_source == "git"
        assert refreshed.icon_image_uri == f"/api/v1/projects/{project.id}/icon"
        assert storage_module.project_icon_key(str(project.id)) in fake_icon_storage

    def test_seed_unsupported_remote_marks_attempted(
        self, test_db, test_user, fake_icon_storage
    ):
        project = self._make_project(
            test_db, test_user.id, git_remote_url="git@bitbucket.org:t/r.git"
        )
        icons.seed_project_icon(project.id)
        test_db.expire_all()
        refreshed = test_db.get(Project, project.id)
        assert refreshed.icon_source == "git"  # attempted → won't retry
        assert refreshed.icon_image_uri is None

    def test_seed_never_clobbers_user_icon(
        self, test_db, test_user, fake_icon_storage, monkeypatch
    ):
        project = self._make_project(
            test_db,
            test_user.id,
            git_remote_url="git@github.com:vicoa-ai/alpha.git",
            icon_source="user",
            icon_image_uri="/api/v1/projects/x/icon",
        )
        # Even if the fetch would succeed, a 'user' source is ineligible.
        monkeypatch.setattr(
            icons.httpx, "Client", lambda *a, **k: _FakeClient(_png_bytes())
        )
        icons.seed_project_icon(project.id)
        test_db.expire_all()
        refreshed = test_db.get(Project, project.id)
        assert refreshed.icon_source == "user"
        assert refreshed.icon_image_uri == "/api/v1/projects/x/icon"


class TestIconEndpoints:
    def _project(self, client):
        return client.post("/api/v1/projects", json={"name": "Alpha"}).json()

    def test_upload_get_delete_roundtrip(self, authenticated_client, fake_icon_storage):
        project = self._project(authenticated_client)
        pid = project["id"]

        resp = authenticated_client.put(
            f"/api/v1/projects/{pid}/icon",
            files={"file": ("icon.png", _png_bytes(), "image/png")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["icon_source"] == "user"
        assert body["icon_image_uri"] == f"/api/v1/projects/{pid}/icon"

        got = authenticated_client.get(f"/api/v1/projects/{pid}/icon")
        assert got.status_code == 200
        assert got.headers["content-type"] in ("image/jpeg", "image/png")

        deleted = authenticated_client.delete(f"/api/v1/projects/{pid}/icon")
        assert deleted.status_code == 200
        assert deleted.json()["icon_image_uri"] is None
        assert deleted.json()["icon_source"] is None
        assert (
            authenticated_client.get(f"/api/v1/projects/{pid}/icon").status_code == 404
        )

    def test_upload_rejects_non_image(self, authenticated_client, fake_icon_storage):
        project = self._project(authenticated_client)
        resp = authenticated_client.put(
            f"/api/v1/projects/{project['id']}/icon",
            files={"file": ("x.txt", b"not an image", "text/plain")},
        )
        assert resp.status_code == 400

    def test_icon_endpoints_are_user_scoped(
        self, authenticated_client, test_db, fake_icon_storage
    ):
        from shared.database.models import User

        other = User(
            id=uuid4(),
            email="other-icons@example.com",
            display_name="Other",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(other)
        test_db.flush()
        foreign = Project(user_id=other.id, name="Theirs")
        test_db.add(foreign)
        test_db.commit()
        resp = authenticated_client.put(
            f"/api/v1/projects/{foreign.id}/icon",
            files={"file": ("icon.png", _png_bytes(), "image/png")},
        )
        assert resp.status_code == 404


class TestAutoArchiveAndOrdering:
    def _project(self, db, user_id, name, created_days_ago=0):
        p = Project(
            user_id=user_id,
            name=name,
            created_at=datetime.now(timezone.utc) - timedelta(days=created_days_ago),
        )
        db.add(p)
        db.commit()
        return p

    def test_stale_project_autoarchives_but_task_bearing_survives(
        self, test_db, test_user
    ):
        from backend.db.task_queries import autoarchive_stale_projects
        from shared.database import Task

        stale = self._project(test_db, test_user.id, "Stale", created_days_ago=60)
        fresh = self._project(test_db, test_user.id, "Fresh", created_days_ago=1)
        with_task = self._project(test_db, test_user.id, "Busy", created_days_ago=60)
        test_db.add(
            Task(
                user_id=test_user.id,
                project_id=with_task.id,
                title="open",
                status="todo",
            )
        )
        test_db.commit()

        n = autoarchive_stale_projects(test_db, test_user.id, days=30)
        assert n == 1
        for p in (stale, fresh, with_task):
            test_db.refresh(p)
        assert stale.is_archived is True
        assert fresh.is_archived is False  # too young
        assert with_task.is_archived is False  # has an open task

    def test_list_orders_by_recent_activity(
        self, authenticated_client, test_db, test_user, test_user_agent
    ):
        from shared.database import AgentInstance
        from shared.database.enums import AgentStatus

        old = self._project(test_db, test_user.id, "Old", created_days_ago=2)
        recent = self._project(test_db, test_user.id, "Recent", created_days_ago=2)
        now = datetime.now(timezone.utc)
        for project, started in ((old, now - timedelta(days=1)), (recent, now)):
            test_db.add(
                AgentInstance(
                    id=uuid4(),
                    user_agent_id=test_user_agent.id,
                    user_id=test_user.id,
                    status=AgentStatus.ACTIVE,
                    project_id=project.id,
                    started_at=started,
                )
            )
        test_db.commit()

        names = [p["name"] for p in authenticated_client.get("/api/v1/projects").json()]
        # Inbox first, then most-recent activity.
        assert names[0] == "Inbox"
        assert names.index("Recent") < names.index("Old")
