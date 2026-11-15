"""`_get_instance_message_stats`: the per-session stats every session list reads.

The query used to window every message row of every listed session (row
number plus two partition counts, each row carrying its content) and keep the
first row, which timed out on long sessions. It is now a grouped count plus a
one-row LATERAL lookup of the latest message. These tests pin the dict it
returns, including the edges the rewrite could have moved: a session with no
messages, `created_at` ties, and messages from someone other than the owner.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import event
from sqlalchemy.orm import Session

from backend.db.queries import _get_instance_message_stats
from shared.database.enums import AgentStatus, SenderType
from shared.database.models import AgentInstance, AgentType, Message, User

# `messages.created_at` is a naive `timestamp` column, so a naive instant
# reads back unchanged whatever the session's time zone is.
T0 = datetime(2026, 1, 1, 12, 0)


def _instance(db: Session, user: User, agent_type: AgentType) -> AgentInstance:
    instance = AgentInstance(
        id=uuid4(),
        agent_type_id=agent_type.id,
        user_id=user.id,
        status=AgentStatus.ACTIVE,
        started_at=T0,
    )
    db.add(instance)
    db.flush()
    return instance


def _message(
    db: Session,
    instance: AgentInstance,
    content: str,
    at: datetime,
    *,
    sender: User | None = None,
    message_id: UUID | None = None,
) -> Message:
    message = Message(
        id=message_id or uuid4(),
        agent_instance_id=instance.id,
        sender_type=SenderType.USER if sender else SenderType.AGENT,
        sender_user_id=sender.id if sender else None,
        content=content,
        created_at=at,
        requires_user_input=False,
    )
    db.add(message)
    db.flush()
    return message


def _other_user(db: Session) -> User:
    user = User(
        id=uuid4(),
        email=f"other-{uuid4().hex[:8]}@example.com",
        display_name="Other",
        created_at=T0,
        updated_at=T0,
    )
    db.add(user)
    db.flush()
    return user


@contextmanager
def _capture_sql(db: Session) -> Iterator[list[str]]:
    statements: list[str] = []
    engine = db.get_bind()

    def _record(
        _conn: Any, _cursor: Any, statement: str, *_args: Any, **_kwargs: Any
    ) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _record)


def test_no_ids_returns_empty_without_a_query(test_db: Session) -> None:
    with _capture_sql(test_db) as statements:
        assert _get_instance_message_stats(test_db, []) == {}
    assert statements == []


def test_counts_and_latest_per_session(
    test_db: Session, test_user: User, test_agent_type: AgentType
) -> None:
    long_session = _instance(test_db, test_user, test_agent_type)
    short_session = _instance(test_db, test_user, test_agent_type)
    # Inserted out of time order: the latest is picked by `created_at`, not by
    # insertion order.
    _message(test_db, long_session, "second", T0 + timedelta(minutes=2))
    _message(test_db, long_session, "third", T0 + timedelta(minutes=3))
    _message(test_db, long_session, "first", T0 + timedelta(minutes=1))
    _message(test_db, short_session, "only", T0 + timedelta(minutes=5))

    stats = _get_instance_message_stats(test_db, [long_session.id, short_session.id])

    assert stats == {
        long_session.id: {
            "latest_message": "third",
            "latest_message_at": (T0 + timedelta(minutes=3)),
            "message_count": 3,
            "foreign_message_count": 0,
        },
        short_session.id: {
            "latest_message": "only",
            "latest_message_at": (T0 + timedelta(minutes=5)),
            "message_count": 1,
            "foreign_message_count": 0,
        },
    }


def test_session_without_messages_is_left_out(
    test_db: Session, test_user: User, test_agent_type: AgentType
) -> None:
    """Callers default a missing entry (`chat_length` 0, no latest message)."""
    empty = _instance(test_db, test_user, test_agent_type)
    busy = _instance(test_db, test_user, test_agent_type)
    _message(test_db, busy, "hello", T0)

    stats = _get_instance_message_stats(test_db, [empty.id, busy.id, uuid4()])

    assert set(stats) == {busy.id}


def test_only_listed_sessions_are_read(
    test_db: Session, test_user: User, test_agent_type: AgentType
) -> None:
    listed = _instance(test_db, test_user, test_agent_type)
    unlisted = _instance(test_db, test_user, test_agent_type)
    _message(test_db, listed, "mine", T0)
    _message(test_db, unlisted, "not asked for", T0 + timedelta(hours=1))

    stats = _get_instance_message_stats(test_db, [listed.id])

    assert set(stats) == {listed.id}
    assert stats[listed.id]["message_count"] == 1
    assert stats[listed.id]["latest_message"] == "mine"


def test_created_at_tie_picks_the_same_row_every_time(
    test_db: Session, test_user: User, test_agent_type: AgentType
) -> None:
    """Two messages at the same instant: the higher id wins, on every call.

    The window query picked either one (its `row_number()` had no tiebreak),
    so a list could flip between them from one load to the next.
    """
    instance = _instance(test_db, test_user, test_agent_type)
    _message(test_db, instance, "older", T0)
    low = UUID("00000000-0000-4000-8000-000000000001")
    high = UUID("ffffffff-ffff-4fff-bfff-ffffffffffff")
    # The lower id is inserted last so neither insertion order nor physical
    # order can be what decides.
    _message(
        test_db, instance, "tie, high id", T0 + timedelta(minutes=1), message_id=high
    )
    _message(
        test_db, instance, "tie, low id", T0 + timedelta(minutes=1), message_id=low
    )

    for _ in range(3):
        stats = _get_instance_message_stats(test_db, [instance.id])
        assert stats[instance.id]["latest_message"] == "tie, high id"
        assert stats[instance.id]["message_count"] == 3


def test_foreign_count_is_messages_from_users_other_than_the_owner(
    test_db: Session, test_user: User, test_agent_type: AgentType
) -> None:
    """Agent rows (no sender) and the owner's own rows are not foreign."""
    instance = _instance(test_db, test_user, test_agent_type)
    collaborator = _other_user(test_db)
    _message(test_db, instance, "agent says", T0)
    _message(
        test_db, instance, "owner says", T0 + timedelta(seconds=1), sender=test_user
    )
    _message(
        test_db, instance, "guest 1", T0 + timedelta(seconds=2), sender=collaborator
    )
    _message(
        test_db, instance, "guest 2", T0 + timedelta(seconds=3), sender=collaborator
    )

    solo = _instance(test_db, test_user, test_agent_type)
    _message(test_db, solo, "owner only", T0, sender=test_user)

    stats = _get_instance_message_stats(test_db, [instance.id, solo.id])

    assert stats[instance.id]["message_count"] == 4
    assert stats[instance.id]["foreign_message_count"] == 2
    assert stats[instance.id]["latest_message"] == "guest 2"
    assert stats[solo.id]["message_count"] == 1
    assert stats[solo.id]["foreign_message_count"] == 0


def test_one_statement_without_a_window_over_every_row(
    test_db: Session, test_user: User, test_agent_type: AgentType
) -> None:
    """The shape that keeps a long session's list fast: no `OVER (...)`
    window (it buffered every row, content included), the latest row by a
    LATERAL lookup, one round trip."""
    instance = _instance(test_db, test_user, test_agent_type)
    _message(test_db, instance, "hello", T0)

    with _capture_sql(test_db) as statements:
        _get_instance_message_stats(test_db, [instance.id])

    assert len(statements) == 1
    sql = statements[0].upper()
    assert " OVER " not in sql and "OVER(" not in sql
    assert "LATERAL" in sql
