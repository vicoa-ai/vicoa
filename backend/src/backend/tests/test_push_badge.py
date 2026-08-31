"""Tests for the app-icon badge count endpoint (GET /api/v1/push/badge-count).

The badge shows how many of the user's sessions are awaiting their input, i.e.
agent instances with status AWAITING_INPUT, scoped to the requesting user.
"""

from datetime import datetime, timezone
from uuid import uuid4

from shared.database.models import AgentInstance, User, UserAgent
from shared.database.enums import AgentStatus


def _make_instance(test_db, user_agent, user, status):
    instance = AgentInstance(
        id=uuid4(),
        user_agent_id=user_agent.id,
        user_id=user.id,
        status=status,
        started_at=datetime.now(timezone.utc),
    )
    test_db.add(instance)
    test_db.commit()
    return instance


class TestBadgeCount:
    def test_zero_when_nothing_awaiting(
        self, authenticated_client, test_db, test_user, test_user_agent
    ):
        _make_instance(test_db, test_user_agent, test_user, AgentStatus.ACTIVE)
        _make_instance(test_db, test_user_agent, test_user, AgentStatus.COMPLETED)

        response = authenticated_client.get("/api/v1/push/badge-count")

        assert response.status_code == 200
        assert response.json() == {"count": 0}

    def test_counts_only_awaiting_input(
        self, authenticated_client, test_db, test_user, test_user_agent
    ):
        _make_instance(test_db, test_user_agent, test_user, AgentStatus.AWAITING_INPUT)
        _make_instance(test_db, test_user_agent, test_user, AgentStatus.AWAITING_INPUT)
        _make_instance(test_db, test_user_agent, test_user, AgentStatus.ACTIVE)
        _make_instance(test_db, test_user_agent, test_user, AgentStatus.COMPLETED)

        response = authenticated_client.get("/api/v1/push/badge-count")

        assert response.status_code == 200
        assert response.json() == {"count": 2}

    def test_is_user_scoped(
        self, authenticated_client, test_db, test_user, test_user_agent
    ):
        # This user has one session awaiting input.
        _make_instance(test_db, test_user_agent, test_user, AgentStatus.AWAITING_INPUT)

        # Another user's awaiting-input session must not leak into the count.
        other_user = User(
            id=uuid4(),
            email="other@example.com",
            display_name="Other User",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(other_user)
        test_db.commit()
        other_agent = UserAgent(
            id=uuid4(),
            user_id=other_user.id,
            name="claude code",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(other_agent)
        test_db.commit()
        _make_instance(test_db, other_agent, other_user, AgentStatus.AWAITING_INPUT)
        _make_instance(test_db, other_agent, other_user, AgentStatus.AWAITING_INPUT)

        response = authenticated_client.get("/api/v1/push/badge-count")

        assert response.status_code == 200
        assert response.json() == {"count": 1}
