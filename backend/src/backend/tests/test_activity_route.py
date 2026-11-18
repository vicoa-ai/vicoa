"""`GET /activity` reads the signed-in user's row, not the token's raw id.

The two differ when the identity provider's account was re-created with the
same email: the dashboard API serves the older row (`find_local_user`), and
the user's sessions and messages carry that row's id.
"""

from uuid import uuid4

from backend.auth.dependencies import get_current_claims
from backend.main import app
from shared.auth.tokens import TokenClaims
from shared.database.enums import SenderType
from shared.database.models import Message


def test_activity_counts_the_rows_messages_for_a_recreated_login(
    authenticated_client, test_db, test_user, test_agent_instance
):
    test_db.add(
        Message(
            id=uuid4(),
            agent_instance_id=test_agent_instance.id,
            sender_type=SenderType.USER,
            sender_user_id=test_user.id,
            content="hello",
        )
    )
    test_db.commit()
    app.dependency_overrides[get_current_claims] = lambda: TokenClaims(
        user_id=uuid4(), email=test_user.email
    )

    response = authenticated_client.get("/api/v1/activity")

    assert response.status_code == 200
    assert response.json()["total_user_messages"] == 1
    assert response.json()["total_sessions"] == 1
