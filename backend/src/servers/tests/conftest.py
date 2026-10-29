"""Pytest configuration and fixtures for servers tests."""

import os
import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from testcontainers.postgres import PostgresContainer

from shared.database.models import Base, User, AgentType, AgentInstance
from shared.database.enums import AgentStatus
from shared.database.utils import json_dumps_without_nul
from shared.database.testing import (
    COMMITTED_DB_MARKER,
    committed_session,
    session_factory_for,
    transactional_session,
)


@pytest.fixture(scope="session")
def postgres_container():
    """Create a PostgreSQL container for testing - shared across all tests."""
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def test_engine(postgres_container):
    """One engine, and one `create_all`, for the whole run."""
    engine = create_engine(
        postgres_container.get_connection_url(),
        # Same as the app engine (`shared/database/session.py`).
        json_serializer=json_dumps_without_nul,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def test_db(request, test_engine):
    """A database session, seeded with a user and an agent type, that leaves
    nothing behind.

    By default the test runs inside one transaction that is rolled back at the
    end (commits become savepoints; see `shared.database.testing`). A test that
    needs real commits — a second connection or a thread must see the rows —
    opts in with `@pytest.mark.committed_db` and gets its tables truncated
    afterwards instead.
    """
    if request.node.get_closest_marker(COMMITTED_DB_MARKER):
        isolate = committed_session(test_engine, Base.metadata)
    else:
        isolate = transactional_session(test_engine)

    with isolate as session:
        test_user = User(
            id=uuid4(),
            email="test@example.com",
            display_name="Test User",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_agent_type = AgentType(
            id=uuid4(),
            user_id=test_user.id,
            name="Claude Code",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(test_user)
        session.add(test_agent_type)
        session.commit()

        yield session


@pytest.fixture
def db_session_factory(test_db):
    """A `SessionLocal` stand-in for code that opens its own session.

    Monkeypatch the module under test's `SessionLocal` with this; sessions it
    hands out see the same data as `test_db`.
    """
    return session_factory_for(test_db)


@pytest.fixture
def mock_jwt_payload():
    """Mock JWT payload for authentication tests."""
    return {
        "sub": str(uuid4()),
        "email": "test@example.com",
        "iat": datetime.now(timezone.utc).timestamp(),
        "exp": (datetime.now(timezone.utc).timestamp() + 3600),
    }


@pytest.fixture
def mock_context(test_db, mock_jwt_payload):
    """Mock MCP context with authentication."""
    context = Mock()
    context.user_id = mock_jwt_payload["sub"]
    context.user_email = mock_jwt_payload["email"]
    context.db = test_db
    return context


@pytest_asyncio.fixture
async def async_mock_context(test_db, mock_jwt_payload):
    """Async mock MCP context for async tests."""
    context = AsyncMock()
    context.user_id = mock_jwt_payload["sub"]
    context.user_email = mock_jwt_payload["email"]
    context.db = test_db
    return context


@pytest.fixture
def test_agent_instance(test_db):
    """Create a test agent instance."""
    # Get test user and agent type
    user = test_db.query(User).first()
    agent_type = test_db.query(AgentType).first()

    instance = AgentInstance(
        id=uuid4(),
        agent_type_id=agent_type.id,
        user_id=user.id,
        status=AgentStatus.ACTIVE,
        started_at=datetime.now(timezone.utc),
    )

    test_db.add(instance)
    test_db.commit()

    return instance


@pytest.fixture(autouse=True)
def reset_env():
    """Reset environment variables for each test."""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)
