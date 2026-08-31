"""Tests for authentication endpoints."""

from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch, Mock

from fastapi import BackgroundTasks
from sqlalchemy import event

from backend.auth.dependencies import get_current_user
from shared.auth.tokens import TokenClaims
from shared.database.models import User, APIKey


class TestAuthEndpoints:
    """Test authentication endpoints."""

    def test_get_session_unauthenticated(self, client):
        """Test getting session when not authenticated."""
        response = client.get("/api/v1/auth/session")
        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"

    def test_get_session_authenticated(self, authenticated_client, test_user):
        """Test getting session when authenticated."""
        response = authenticated_client.get("/api/v1/auth/session")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)
        assert data["email"] == test_user.email
        assert data["display_name"] == test_user.display_name

    def test_get_current_user_profile(self, authenticated_client, test_user):
        """Test getting current user profile."""
        response = authenticated_client.get("/api/v1/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)
        assert data["email"] == test_user.email
        assert data["display_name"] == test_user.display_name

    @patch("backend.auth.utils.get_auth_provider")
    def test_update_user_profile(
        self, mock_get_provider, authenticated_client, test_user, test_db
    ):
        """Test updating user profile."""
        # The profile write goes through the active auth provider, whichever
        # one that is.
        mock_provider = Mock()
        mock_get_provider.return_value = mock_provider

        new_display_name = "Updated Test User"
        response = authenticated_client.patch(
            "/api/v1/auth/me", json={"display_name": new_display_name}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == new_display_name

        # Verify in database
        test_db.refresh(test_user)
        assert test_user.display_name == new_display_name

        # Verify the provider was told about the change
        mock_provider.update_user_profile.assert_called_once()

    def test_sync_user(self, authenticated_client, test_user, test_db):
        """Test syncing user from Supabase."""
        response = authenticated_client.post(
            "/api/v1/auth/sync-user",
            json={
                "id": str(test_user.id),
                "email": test_user.email,
                "display_name": "Synced Name",
            },
        )
        assert response.status_code == 200
        assert response.json()["message"] == "User synced successfully"

        # Verify display name was updated
        test_db.refresh(test_user)
        assert test_user.display_name == "Synced Name"

    def test_sync_user_forbidden(self, authenticated_client, test_user):
        """Test syncing a different user is forbidden."""
        different_user_id = str(uuid4())
        response = authenticated_client.post(
            "/api/v1/auth/sync-user",
            json={
                "id": different_user_id,
                "email": "other@example.com",
                "display_name": "Other User",
            },
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Cannot sync different user"


class TestAPIKeyEndpoints:
    """Test API key management endpoints."""

    @patch("backend.auth.routes.create_api_key_jwt")
    def test_create_api_key(
        self, mock_create_jwt, authenticated_client, test_user, test_db
    ):
        """Test creating an API key."""
        mock_jwt_token = "test.jwt.token"
        mock_create_jwt.return_value = mock_jwt_token

        response = authenticated_client.post(
            "/api/v1/auth/api-keys",
            json={"name": "Test API Key", "expires_in_days": 30},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test API Key"
        assert data["api_key"] == mock_jwt_token
        assert "expires_at" in data

        # Verify in database
        api_key = test_db.query(APIKey).filter(APIKey.user_id == test_user.id).first()
        assert api_key is not None
        assert api_key.name == "Test API Key"
        assert api_key.is_active is True

    @patch("backend.auth.routes.create_api_key_jwt")
    def test_create_api_key_max_limit(
        self, mock_create_jwt, authenticated_client, test_user, test_db
    ):
        """Test creating API key when at max limit."""
        mock_create_jwt.return_value = "test.jwt.token"

        # Create 50 existing API keys
        for i in range(50):
            api_key = APIKey(
                id=uuid4(),
                user_id=test_user.id,
                name=f"Key {i}",
                api_key_hash="hash",
                api_key=f"token{i}",
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
            test_db.add(api_key)
        test_db.commit()

        response = authenticated_client.post(
            "/api/v1/auth/api-keys",
            json={"name": "One Too Many", "expires_in_days": 30},
        )

        assert response.status_code == 400
        assert "Maximum of 50 active API keys allowed" in response.json()["detail"]

    def test_list_api_keys(self, authenticated_client, test_user, test_db):
        """Test listing API keys."""
        # Create test API keys
        api_keys = []
        for i in range(3):
            api_key = APIKey(
                id=uuid4(),
                user_id=test_user.id,
                name=f"Key {i}",
                api_key_hash=f"hash{i}",
                api_key=f"token{i}",
                is_active=i != 2,  # Last one is inactive
                created_at=datetime.now(timezone.utc),
            )
            api_keys.append(api_key)
            test_db.add(api_key)
        test_db.commit()

        response = authenticated_client.get("/api/v1/auth/api-keys")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

        # Should be ordered by created_at desc
        assert data[0]["name"] == "Key 2"
        assert data[0]["is_active"] is False
        assert data[1]["name"] == "Key 1"
        assert data[1]["is_active"] is True

    def test_revoke_api_key(self, authenticated_client, test_user, test_db):
        """Test revoking an API key."""
        # Create test API key
        api_key = APIKey(
            id=uuid4(),
            user_id=test_user.id,
            name="Test Key",
            api_key_hash="hash",
            api_key="token",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(api_key)
        test_db.commit()

        response = authenticated_client.delete(f"/api/v1/auth/api-keys/{api_key.id}")
        assert response.status_code == 200
        assert response.json()["message"] == "API key revoked successfully"

        # Verify in database
        test_db.refresh(api_key)
        assert api_key.is_active is False

    def test_revoke_api_key_not_found(self, authenticated_client):
        """Test revoking a non-existent API key."""
        fake_id = str(uuid4())
        response = authenticated_client.delete(f"/api/v1/auth/api-keys/{fake_id}")
        assert response.status_code == 404
        assert response.json()["detail"] == "API key not found"

    def test_revoke_api_key_wrong_user(self, authenticated_client, test_db):
        """Test revoking another user's API key."""
        # Create another user
        other_user = User(
            id=uuid4(),
            email="other@example.com",
            display_name="Other User",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(other_user)

        # Create API key for other user
        api_key = APIKey(
            id=uuid4(),
            user_id=other_user.id,
            name="Other's Key",
            api_key_hash="hash",
            api_key="token",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(api_key)
        test_db.commit()

        response = authenticated_client.delete(f"/api/v1/auth/api-keys/{api_key.id}")
        assert response.status_code == 404
        assert response.json()["detail"] == "API key not found"


class TestAuthPathIsReadOnly:
    """Pins the steady-state auth path as read-only.

    `get_current_user` runs before the handler body. With the per-session
    `after_commit` listener (websocket-migration §2.7), any uncommitted write
    left on the request session would be committed by the handler's
    `db.commit()`, surprising callers. The steady-state (existing-user) path
    therefore must not write; the first-sign-in provisioning path is the
    documented exception (it self-commits its INSERT).
    """

    async def test_existing_user_auth_path_emits_no_writes(self, test_db, test_user):
        writes: list[str] = []

        def _record(conn, cursor, statement, parameters, context, executemany):
            verb = statement.lstrip().split(None, 1)[0].upper()
            if verb in ("INSERT", "UPDATE", "DELETE"):
                writes.append(statement)

        # before_cursor_execute sees every statement actually sent — including
        # one flushed by autoflush but not yet committed — so this catches the
        # write a `db.dirty` check would miss.
        event.listen(test_db.bind, "before_cursor_execute", _record)
        try:
            background_tasks = BackgroundTasks()
            user = await get_current_user(
                background_tasks=background_tasks,
                claims=TokenClaims(
                    user_id=test_user.id,
                    email=test_user.email,
                    display_name=test_user.display_name,
                ),
                db=test_db,
            )
        finally:
            event.remove(test_db.bind, "before_cursor_execute", _record)

        assert user.id == test_user.id
        assert writes == [], f"auth path must not write: {writes}"
        assert background_tasks.tasks == [], "existing user must not be welcomed again"


class TestCreateCliKey:
    """The CLI key is now an opaque, DB-backed, expiring token."""

    def test_cli_key_is_opaque_and_expiring(
        self, authenticated_client, test_user, test_db
    ):
        from datetime import datetime, timezone

        from shared.auth import get_token_hash
        from shared.auth.agent_tokens import CLI_KEY_TTL_DAYS

        response = authenticated_client.post("/api/v1/auth/cli-key")
        assert response.status_code == 200
        data = response.json()

        raw = data["api_key"]
        assert raw.startswith("vic_")
        assert data["expires_at"] is not None
        # ~90 days out (allow a day of slack for clock/serialization).
        expires_at = datetime.fromisoformat(data["expires_at"])
        days_left = (expires_at - datetime.now(timezone.utc)).days
        assert CLI_KEY_TTL_DAYS - 1 <= days_left <= CLI_KEY_TTL_DAYS

        # The raw secret is never stored: the row keeps only the hash and a
        # masked prefix, and the hash matches what the verifier will compute.
        row = (
            test_db.query(APIKey)
            .filter(APIKey.api_key_hash == get_token_hash(raw))
            .first()
        )
        assert row is not None
        assert row.user_id == test_user.id
        assert row.api_key != raw
        assert row.api_key.startswith("vic_")
        assert row.is_active is True
