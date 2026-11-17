"""Account deletion and its statement timeout.

The last statement of `delete_user_account`, `DELETE FROM users`, runs every
ON DELETE action that points at the user. `messages.sender_user_id` (SET NULL)
has no index, so that statement scans the whole messages table however little
the user wrote, and on a large table it can outlast the connection's 30 s
`statement_timeout`: the delete fails and the user keeps an account they asked
to delete. `delete_user_account` raises the limit for its own transaction only.

Pinned here: the raised limit is what the users delete runs under, the
connection gets its default back when the transaction ends (commit or
rollback), the delete still removes or detaches every row it did, and the
route does not run that blocking work on the event loop.
"""

import inspect
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from backend.auth import routes as auth_routes
from backend.db.queries import ACCOUNT_DELETE_STATEMENT_TIMEOUT_MS, delete_user_account
from shared.database.enums import AgentStatus, SenderType
from shared.database.models import (
    AgentInstance,
    AgentType,
    APIKey,
    Message,
    PushToken,
    User,
)

# The app engine's per-connection default (`shared/database/session.py`).
APP_DEFAULT_TIMEOUT_MS = 30_000

_USERS_DELETE = re.compile(r"\s*DELETE FROM users\s", re.IGNORECASE)


def _timeout_ms(conn: Connection) -> int:
    # pg_settings reports the value in its base unit (ms), unlike SHOW ("5min").
    return int(
        conn.execute(
            text("SELECT setting FROM pg_settings WHERE name = 'statement_timeout'")
        ).scalar_one()
    )


@contextmanager
def _timeout_at_users_delete(
    bind: Engine | Connection, *, fail: bool = False
) -> Iterator[list[int]]:
    """Record the statement timeout in force when `DELETE FROM users` is sent
    (read on the same connection, so inside the same transaction). With
    `fail=True` the delete is then made to fail, as a timeout would."""
    seen: list[int] = []

    def probe(conn, cursor, statement, parameters, context, executemany):
        if not _USERS_DELETE.match(statement):
            return
        with cursor.connection.cursor() as other:
            other.execute(
                "SELECT setting FROM pg_settings WHERE name = 'statement_timeout'"
            )
            seen.append(int(other.fetchone()[0]))
        if fail:
            raise RuntimeError("users delete failed")

    event.listen(bind, "before_cursor_execute", probe)
    try:
        yield seen
    finally:
        event.remove(bind, "before_cursor_execute", probe)


def _user(db: Session, email: str) -> User:
    user = User(
        id=uuid4(),
        email=email,
        display_name=email.split("@")[0],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    return user


def _instance(db: Session, user_id: UUID) -> AgentInstance:
    agent_type = AgentType(id=uuid4(), user_id=user_id, name=f"agent-{uuid4().hex}")
    db.add(agent_type)
    db.flush()
    instance = AgentInstance(
        id=uuid4(),
        agent_type_id=agent_type.id,
        user_id=user_id,
        status=AgentStatus.ACTIVE,
        started_at=datetime.now(timezone.utc),
    )
    db.add(instance)
    db.commit()
    return instance


def _message(
    db: Session, instance_id: UUID, sender_user_id: UUID | None = None
) -> Message:
    message = Message(
        id=uuid4(),
        agent_instance_id=instance_id,
        sender_type=SenderType.USER if sender_user_id else SenderType.AGENT,
        sender_user_id=sender_user_id,
        content="hello",
    )
    db.add(message)
    db.commit()
    return message


@pytest.fixture
def no_close_user_bridge() -> Iterator[None]:
    # The post-commit WS teardown is an HTTP call to the server process.
    with patch("backend.broadcast_bridge.post_close_user"):
        yield


@pytest.fixture
def own_connection(test_engine: Engine) -> Iterator[Connection]:
    """One connection with the app's default timeout set at session level, so
    a test can read what the connection is left with after a real COMMIT or
    ROLLBACK."""
    with test_engine.connect() as conn:
        conn.execute(text(f"SET statement_timeout = {APP_DEFAULT_TIMEOUT_MS}"))
        conn.commit()
        yield conn


@pytest.mark.usefixtures("no_close_user_bridge")
class TestAccountDeleteTimeout:
    @pytest.mark.committed_db  # SET LOCAL only ends at a real COMMIT / ROLLBACK
    def test_users_delete_runs_under_the_raised_timeout_and_commit_restores_it(
        self, test_db, own_connection
    ):
        db = Session(bind=own_connection)
        user = _user(db, "ada@example.com")
        user_id = user.id

        with _timeout_at_users_delete(own_connection) as seen:
            delete_user_account(db, user_id)

        assert seen == [ACCOUNT_DELETE_STATEMENT_TIMEOUT_MS]
        assert ACCOUNT_DELETE_STATEMENT_TIMEOUT_MS > APP_DEFAULT_TIMEOUT_MS
        assert _timeout_ms(own_connection) == APP_DEFAULT_TIMEOUT_MS
        assert db.query(User).filter(User.id == user_id).count() == 0
        db.close()

    @pytest.mark.committed_db
    def test_a_failed_delete_rolls_back_and_restores_the_timeout(
        self, test_db, own_connection
    ):
        db = Session(bind=own_connection)
        user = _user(db, "ada@example.com")
        user_id = user.id
        instance_id = _instance(db, user_id).id

        with _timeout_at_users_delete(own_connection, fail=True) as seen:
            with pytest.raises(RuntimeError, match="users delete failed"):
                delete_user_account(db, user_id)

        assert seen == [ACCOUNT_DELETE_STATEMENT_TIMEOUT_MS]
        assert _timeout_ms(own_connection) == APP_DEFAULT_TIMEOUT_MS
        # Nothing was half-deleted: the earlier deletes rolled back with it.
        assert db.query(User).filter(User.id == user_id).count() == 1
        assert (
            db.query(AgentInstance).filter(AgentInstance.id == instance_id).count() == 1
        )
        db.close()

    @pytest.mark.committed_db
    def test_set_after_the_user_delete_hooks_so_a_hook_commit_cannot_end_it(
        self, test_db, own_connection
    ):
        """A hook runs first and may read, then commit (get-or-create style);
        the limit must still hold for the statements after it."""
        db = Session(bind=own_connection)
        user = _user(db, "ada@example.com")

        def committing_hook(hook_db: Session, hook_user_id: UUID) -> None:
            hook_db.execute(text("SELECT 1"))
            hook_db.commit()

        with (
            patch("shared.hooks._user_delete_hooks", [committing_hook]),
            _timeout_at_users_delete(own_connection) as seen,
        ):
            delete_user_account(db, user.id)

        assert seen == [ACCOUNT_DELETE_STATEMENT_TIMEOUT_MS]
        assert _timeout_ms(own_connection) == APP_DEFAULT_TIMEOUT_MS
        db.close()


@pytest.mark.usefixtures("no_close_user_bridge")
def test_delete_removes_the_users_rows_and_detaches_their_messages_elsewhere(
    test_db,
):
    """The same end state as before the timeout change: the user's own rows are
    gone, and a message they sent in someone else's session stays, with its
    sender cleared by the SET NULL action (the statement the timeout is for)."""
    leaver = _user(test_db, "leaver@example.com")
    other = _user(test_db, "other@example.com")
    leaver_id, other_id = leaver.id, other.id

    own = _instance(test_db, leaver_id)
    own_id, own_type_id = own.id, own.agent_type_id
    _message(test_db, own_id, sender_user_id=leaver_id)
    _message(test_db, own_id)
    test_db.add(
        APIKey(
            id=uuid4(),
            user_id=leaver_id,
            name="cli",
            api_key_hash=uuid4().hex,
            api_key=uuid4().hex,
        )
    )
    test_db.add(
        PushToken(id=uuid4(), user_id=leaver_id, token=uuid4().hex, platform="ios")
    )
    test_db.commit()

    elsewhere = _instance(test_db, other_id)
    sent_elsewhere_id = _message(test_db, elsewhere.id, sender_user_id=leaver_id).id
    elsewhere_id = elsewhere.id

    delete_user_account(test_db, leaver_id)
    test_db.expire_all()

    assert test_db.query(User).filter(User.id == leaver_id).count() == 0
    assert test_db.query(AgentInstance).filter(AgentInstance.id == own_id).count() == 0
    assert test_db.query(AgentType).filter(AgentType.id == own_type_id).count() == 0
    assert (
        test_db.query(Message).filter(Message.agent_instance_id == own_id).count() == 0
    )
    assert test_db.query(APIKey).filter(APIKey.user_id == leaver_id).count() == 0
    assert test_db.query(PushToken).filter(PushToken.user_id == leaver_id).count() == 0

    sent_elsewhere = test_db.get(Message, sent_elsewhere_id)
    assert sent_elsewhere is not None
    assert sent_elsewhere.sender_user_id is None
    assert test_db.get(AgentInstance, elsewhere_id) is not None
    assert test_db.get(User, other_id) is not None


def test_delete_route_runs_in_the_threadpool():
    """The handler's work is all blocking (a transaction that may run for
    minutes, the identity provider's HTTP call). As an `async def` it would
    run on the event loop and stall every other request on the worker."""
    assert not inspect.iscoroutinefunction(auth_routes.delete_user_account)


@pytest.mark.usefixtures("no_close_user_bridge")
def test_delete_me_endpoint_deletes_the_account(
    authenticated_client, test_db, test_user
):
    user_id = test_user.id
    with patch.object(auth_routes, "get_auth_provider") as provider:
        response = authenticated_client.delete("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json() == {"message": "User account successfully deleted"}
    provider.return_value.delete_user.assert_called_once_with(user_id)
    test_db.expire_all()
    assert test_db.query(User).filter(User.id == user_id).count() == 0
