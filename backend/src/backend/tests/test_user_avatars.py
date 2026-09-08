"""User avatars: upload/serve/delete, the OAuth seed, and re-seed precedence.

The sibling of test_project_icons.py — same pipeline, same invariant that a
'user' upload is never clobbered by a re-seed.
"""

from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image

import shared.avatars as avatars
import shared.storage as storage_module
from shared.database.models import User


def _png_bytes(width: int = 64, height: int = 64, color=(20, 120, 200)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), color=color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _seed_uses_test_engine(test_db, monkeypatch):
    """Bind the seed's own-session factory to the test container's engine.

    seed_user_avatar() opens ``SessionLocal`` (module-level, bound to the
    settings DB) because it runs as a background task; point it at the test DB.
    """
    from sqlalchemy.orm import sessionmaker

    local = sessionmaker(bind=test_db.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr(avatars, "SessionLocal", local)


@pytest.fixture
def fake_avatar_storage(monkeypatch):
    """In-memory stand-in for the S3 object store."""
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


class TestAllowedAvatarUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://lh3.googleusercontent.com/a/ACg8ocK=s96-c",
            "https://avatars.githubusercontent.com/u/12345?v=4",
            "https://secure.gravatar.com/avatar/abc",
        ],
    )
    def test_allowlisted_hosts_pass_through(self, url):
        assert avatars.allowed_avatar_url(url) == url

    @pytest.mark.parametrize(
        "url",
        [
            None,
            "",
            "http://lh3.googleusercontent.com/a/x",  # not https
            "https://evil.example/a.png",  # unknown host
            "https://lh3.googleusercontent.com.evil.example/a.png",  # suffix trick
            # userinfo trick: the real host is evil.example, not the allowlisted one
            "https://lh3.googleusercontent.com@evil.example/a.png",
            "file:///etc/passwd",
            "https://127.0.0.1/a.png",
            "https://[::1]/a.png",
        ],
    )
    def test_everything_else_is_refused(self, url):
        assert avatars.allowed_avatar_url(url) is None


class _FakeResp:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


class _FakeClient:
    def __init__(self, content):
        self._content = content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url):
        return _FakeResp(self._content)


GOOGLE_AVATAR = "https://lh3.googleusercontent.com/a/ACg8ocK=s96-c"


class TestOAuthSeed:
    def test_seed_from_google_sets_oauth_source(
        self, test_db, test_user, fake_avatar_storage, monkeypatch
    ):
        monkeypatch.setattr(
            avatars.httpx, "Client", lambda *a, **k: _FakeClient(_png_bytes())
        )
        avatars.seed_user_avatar(test_user.id, GOOGLE_AVATAR)
        test_db.expire_all()
        refreshed = test_db.get(User, test_user.id)
        assert refreshed.avatar_source == "oauth"
        assert refreshed.avatar_image_uri == f"/api/v1/users/{test_user.id}/avatar"
        assert storage_module.user_avatar_key(str(test_user.id)) in fake_avatar_storage

    def test_seed_without_a_url_marks_attempted(
        self, test_db, test_user, fake_avatar_storage
    ):
        # Apple sign-in publishes no picture at all — the common case.
        avatars.seed_user_avatar(test_user.id, None)
        test_db.expire_all()
        refreshed = test_db.get(User, test_user.id)
        assert refreshed.avatar_source == "oauth"  # attempted → won't retry
        assert refreshed.avatar_image_uri is None

    def test_disallowed_host_is_never_fetched(
        self, test_db, test_user, fake_avatar_storage, monkeypatch
    ):
        def explode(*a, **k):
            raise AssertionError("must not fetch a non-allowlisted host")

        monkeypatch.setattr(avatars.httpx, "Client", explode)
        avatars.seed_user_avatar(test_user.id, "https://evil.example/a.png")
        test_db.expire_all()
        assert test_db.get(User, test_user.id).avatar_image_uri is None

    def test_seed_never_clobbers_a_user_upload(
        self, test_db, test_user, fake_avatar_storage, monkeypatch
    ):
        test_user.avatar_source = "user"
        test_user.avatar_image_uri = f"/api/v1/users/{test_user.id}/avatar"
        test_db.commit()
        monkeypatch.setattr(
            avatars.httpx, "Client", lambda *a, **k: _FakeClient(_png_bytes())
        )
        avatars.seed_user_avatar(test_user.id, GOOGLE_AVATAR)
        test_db.expire_all()
        refreshed = test_db.get(User, test_user.id)
        assert refreshed.avatar_source == "user"
        assert refreshed.avatar_image_uri == f"/api/v1/users/{test_user.id}/avatar"

    def test_failed_fetch_marks_attempted_and_leaves_no_image(
        self, test_db, test_user, fake_avatar_storage, monkeypatch
    ):
        class _Boom(_FakeClient):
            def get(self, url):
                raise avatars.httpx.ConnectError("nope")

        monkeypatch.setattr(avatars.httpx, "Client", lambda *a, **k: _Boom(b""))
        avatars.seed_user_avatar(test_user.id, GOOGLE_AVATAR)
        test_db.expire_all()
        refreshed = test_db.get(User, test_user.id)
        assert refreshed.avatar_source == "oauth"
        assert refreshed.avatar_image_uri is None

    def test_non_image_bytes_are_rejected(
        self, test_db, test_user, fake_avatar_storage, monkeypatch
    ):
        monkeypatch.setattr(
            avatars.httpx, "Client", lambda *a, **k: _FakeClient(b"not an image")
        )
        avatars.seed_user_avatar(test_user.id, GOOGLE_AVATAR)
        test_db.expire_all()
        assert test_db.get(User, test_user.id).avatar_image_uri is None
        assert not fake_avatar_storage


class TestAvatarEndpoints:
    def test_upload_get_delete_roundtrip(
        self, authenticated_client, test_user, fake_avatar_storage
    ):
        resp = authenticated_client.put(
            "/api/v1/me/avatar",
            files={"file": ("me.png", _png_bytes(), "image/png")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["avatar_source"] == "user"
        assert body["avatar_image_uri"] == f"/api/v1/users/{test_user.id}/avatar"
        # The avatar payload must never carry an email (privacy, plan P0).
        assert "email" not in body

        got = authenticated_client.get(f"/api/v1/users/{test_user.id}/avatar")
        assert got.status_code == 200
        assert got.headers["content-type"] in ("image/jpeg", "image/png")

        deleted = authenticated_client.delete("/api/v1/me/avatar")
        assert deleted.status_code == 200
        assert deleted.json()["avatar_image_uri"] is None
        # Pinned, so the next sign-in does not restore the OAuth picture.
        assert deleted.json()["avatar_source"] == "user"
        assert (
            authenticated_client.get(f"/api/v1/users/{test_user.id}/avatar").status_code
            == 404
        )

    def test_upload_rejects_non_image(self, authenticated_client, fake_avatar_storage):
        resp = authenticated_client.put(
            "/api/v1/me/avatar",
            files={"file": ("x.txt", b"not an image", "text/plain")},
        )
        assert resp.status_code == 400
        assert not fake_avatar_storage

    def test_avatar_appears_on_the_profile_endpoint(
        self, authenticated_client, fake_avatar_storage
    ):
        authenticated_client.put(
            "/api/v1/me/avatar",
            files={"file": ("me.png", _png_bytes(), "image/png")},
        )
        profile = authenticated_client.get("/api/v1/auth/me").json()
        assert profile["avatar_source"] == "user"
        assert profile["avatar_image_uri"].endswith("/avatar")
        # updated_at is the client's cache-buster for the stable avatar URL.
        assert profile["updated_at"]

    def test_missing_avatar_and_unknown_user_are_both_404(
        self, authenticated_client, test_db, fake_avatar_storage
    ):
        other = User(
            id=uuid4(),
            email="other-avatar@example.com",
            display_name="Other",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(other)
        test_db.commit()
        assert (
            authenticated_client.get(f"/api/v1/users/{other.id}/avatar").status_code
            == 404
        )
        assert (
            authenticated_client.get(f"/api/v1/users/{uuid4()}/avatar").status_code
            == 404
        )
