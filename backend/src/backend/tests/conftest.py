"""Pytest configuration and fixtures for backend tests."""

import os
import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from shared.config import settings
from shared.database.models import Base, User, UserAgent, AgentInstance
from shared.database.enums import AgentStatus
from backend.main import app
from backend.auth.dependencies import (
    get_current_claims,
    get_current_user,
    get_optional_current_user,
)
from shared.auth.tokens import TokenClaims
from shared.database.session import get_db


@pytest.fixture(scope="session")
def postgres_container():
    """Create a PostgreSQL container for testing - shared across all tests."""
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest.fixture
def test_db(postgres_container):
    """Create a test database session using PostgreSQL."""
    # Get connection URL from container
    db_url = postgres_container.get_connection_url()

    # Create engine and tables
    engine = create_engine(db_url)
    Base.metadata.create_all(bind=engine)

    # Create session
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSessionLocal()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def test_user(test_db):
    """Create a test user."""
    user = User(
        id=uuid4(),
        email="test@example.com",
        display_name="Test User",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def test_user_agent(test_db, test_user):
    """Create a test user agent."""
    user_agent = UserAgent(
        id=uuid4(),
        user_id=test_user.id,
        name="claude code",  # Lowercase as per the actual implementation
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    test_db.add(user_agent)
    test_db.commit()
    return user_agent


@pytest.fixture
def test_agent_instance(test_db, test_user, test_user_agent):
    """Create a test agent instance."""
    instance = AgentInstance(
        id=uuid4(),
        user_agent_id=test_user_agent.id,
        user_id=test_user.id,
        status=AgentStatus.ACTIVE,
        started_at=datetime.now(timezone.utc),
    )
    test_db.add(instance)
    test_db.commit()
    return instance


@pytest.fixture
def client(test_db):
    """Create a test client with database override."""

    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client(client, test_user):
    """Create a test client with authentication."""

    def override_get_current_user():
        return test_user

    def override_get_optional_current_user():
        return test_user

    def override_get_current_claims():
        return TokenClaims(
            user_id=test_user.id,
            email=test_user.email,
            display_name=test_user.display_name,
        )

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_optional_current_user] = (
        override_get_optional_current_user
    )
    app.dependency_overrides[get_current_claims] = override_get_current_claims

    yield client

    # Clear only the auth overrides, keep the db override
    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]
    if get_optional_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_optional_current_user]
    if get_current_claims in app.dependency_overrides:
        del app.dependency_overrides[get_current_claims]


@pytest.fixture
def mock_supabase_client():
    """Mock Supabase client for auth tests."""
    mock = Mock()
    mock.auth = Mock()
    mock.auth.get_user = Mock()
    return mock


@pytest.fixture(autouse=True)
def reset_env():
    """Reset environment variables for each test."""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture(autouse=True)
def _block_real_email_providers(monkeypatch):
    """Prevent tests from accidentally hitting a production email service.

    `.env` carries production Mailgun, Resend *and* Listmonk credentials for local
    backend runs, and `settings` reads them at import time — so any test that
    exercises an email code path without mocking it would send a real email, and
    any test that reaches the signup hook would subscribe a fake address to the
    live marketing list. Clearing every provider's fields makes
    `mailgun_is_configured()`, `resend_is_configured()` and
    `listmonk_is_configured()` short-circuit, so nothing leaves the process.
    Tests that want to inspect those flows monkeypatch the transport directly
    and are unaffected.
    """
    monkeypatch.setattr(settings, "mailgun_api_key", "")
    monkeypatch.setattr(settings, "mailgun_domain", "")
    monkeypatch.setattr(settings, "mailgun_from_email", "")
    monkeypatch.setattr(settings, "resend_api_key", "")
    monkeypatch.setattr(settings, "resend_from_email", "")
    monkeypatch.setattr(settings, "listmonk_url", "")
    monkeypatch.setattr(settings, "listmonk_api_user", "")
    monkeypatch.setattr(settings, "listmonk_api_token", "")
