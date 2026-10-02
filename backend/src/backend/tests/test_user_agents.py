"""Tests for user agent endpoints."""

from datetime import datetime, timezone
from uuid import uuid4

from shared.database.models import AgentType, AgentInstance, User
from shared.database.enums import AgentStatus


class TestUserAgentEndpoints:
    """Test user agent management endpoints."""

    def test_list_user_agents(
        self, authenticated_client, test_db, test_user, test_agent_type
    ):
        """Test listing user agents."""
        # Create additional user agent
        another_agent = AgentType(
            id=uuid4(),
            user_id=test_user.id,
            name="cursor",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(another_agent)
        test_db.commit()

        response = authenticated_client.get("/api/v1/user-agents")
        assert response.status_code == 200
        data = response.json()

        assert len(data) == 2
        names = [agent["name"] for agent in data]
        assert "claude code" in names
        assert "cursor" in names

    def test_list_user_agents_different_users(
        self, authenticated_client, test_db, test_agent_type
    ):
        """Test that users only see their own user agents."""
        # Create another user with agent
        other_user = User(
            id=uuid4(),
            email="other@example.com",
            display_name="Other User",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(other_user)

        other_agent = AgentType(
            id=uuid4(),
            user_id=other_user.id,
            name="other agent",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(other_agent)
        test_db.commit()

        response = authenticated_client.get("/api/v1/user-agents")
        assert response.status_code == 200
        data = response.json()

        # Should only see own agent
        assert len(data) == 1
        assert data[0]["name"] == "claude code"

    def test_create_user_agent(self, authenticated_client, test_db, test_user):
        """Test creating a new user agent."""
        agent_data = {"name": "New Agent", "is_active": True}

        response = authenticated_client.post("/api/v1/user-agents", json=agent_data)
        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "New Agent"
        assert data["is_active"] is True
        assert "id" in data

        # Verify in database
        agent = test_db.query(AgentType).filter_by(name="New Agent").first()
        assert agent is not None
        assert agent.user_id == test_user.id

    def test_update_user_agent(self, authenticated_client, test_db, test_agent_type):
        """Test updating a user agent."""
        update_data = {"name": "Updated Claude", "is_active": False}

        response = authenticated_client.patch(
            f"/api/v1/user-agents/{test_agent_type.id}", json=update_data
        )
        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "Updated Claude"
        assert data["is_active"] is False

        # Verify in database
        test_db.refresh(test_agent_type)
        assert test_agent_type.name == "Updated Claude"
        assert test_agent_type.is_active is False

    def test_update_user_agent_not_found(self, authenticated_client):
        """Test updating a non-existent user agent."""
        fake_id = uuid4()
        response = authenticated_client.patch(
            f"/api/v1/user-agents/{fake_id}", json={"name": "Updated"}
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "User agent not found"

    def test_update_user_agent_wrong_user(self, authenticated_client, test_db):
        """Test updating another user's agent."""
        # Create another user with agent
        other_user = User(
            id=uuid4(),
            email="other@example.com",
            display_name="Other User",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(other_user)

        other_agent = AgentType(
            id=uuid4(),
            user_id=other_user.id,
            name="other agent",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(other_agent)
        test_db.commit()

        response = authenticated_client.patch(
            f"/api/v1/user-agents/{other_agent.id}", json={"name": "Hacked"}
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "User agent not found"

    def test_get_user_agent_instances(
        self, authenticated_client, test_db, test_user, test_agent_type
    ):
        """Test getting instances for a user agent."""
        # Create instances
        instance1 = AgentInstance(
            id=uuid4(),
            agent_type_id=test_agent_type.id,
            user_id=test_user.id,
            status=AgentStatus.ACTIVE,
            started_at=datetime.now(timezone.utc),
        )
        instance2 = AgentInstance(
            id=uuid4(),
            agent_type_id=test_agent_type.id,
            user_id=test_user.id,
            status=AgentStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
        )
        test_db.add_all([instance1, instance2])
        test_db.commit()

        response = authenticated_client.get(
            f"/api/v1/user-agents/{test_agent_type.id}/instances"
        )
        assert response.status_code == 200
        data = response.json()

        assert len(data) == 2
        statuses = [inst["status"] for inst in data]
        assert "ACTIVE" in statuses
        assert "COMPLETED" in statuses

    def test_get_user_agent_instances_not_found(self, authenticated_client):
        """Test getting instances for non-existent user agent."""
        fake_id = uuid4()
        response = authenticated_client.get(f"/api/v1/user-agents/{fake_id}/instances")
        assert response.status_code == 404
        assert response.json()["detail"] == "User agent not found"

    def test_webhook_fields_are_ignored(self, authenticated_client):
        """Webhook agents are gone; old clients sending their fields still work."""
        response = authenticated_client.post(
            "/api/v1/user-agents",
            json={
                "name": "Old Client Agent",
                "webhook_type": "DEFAULT",
                "webhook_config": {"url": "http://127.0.0.1:45678/internal-webhook"},
            },
        )
        assert response.status_code == 200
        assert "webhook_type" not in response.json()
        assert "webhook_config" not in response.json()

    def test_starting_an_instance_by_webhook_is_gone(
        self, authenticated_client, test_db, test_agent_type
    ):
        """The backend no longer POSTs to a user-supplied URL to start an agent."""
        response = authenticated_client.post(
            f"/api/v1/user-agents/{test_agent_type.id}/instances",
            json={"prompt": "Test prompt"},
        )

        assert response.status_code == 405
        assert (
            test_db.query(AgentInstance)
            .filter_by(agent_type_id=test_agent_type.id)
            .first()
            is None
        )
        # Only PATCH/DELETE remain on /user-agents/{id}.
        response = authenticated_client.get("/api/v1/user-agents/webhook-types")
        assert response.status_code == 405
