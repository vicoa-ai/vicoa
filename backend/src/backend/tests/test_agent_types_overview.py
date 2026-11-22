"""`get_all_agent_types_with_instances`: the stats behind `GET /agent-types`.

The overview used to build its own window query over every message row of all
of a user's sessions at once (row number plus a partition count, each row
carrying its content), the shape the session list dropped because it timed out
on long sessions. It now reads `_get_instance_message_stats`. These tests pin
what each listed session reports: message count, latest message and its time,
the order that time decides, and the edges a rewrite could move (a session
with no messages, a deleted session, a `created_at` tie).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import event
from sqlalchemy.orm import Session

from backend.db.queries import (
    _get_instance_message_stats,
    get_all_agent_types_with_instances,
)
from backend.models import AgentInstanceResponse, AgentTypeOverview
from shared.database.enums import AgentStatus, SenderType
from shared.database.models import AgentInstance, AgentType, Message, User

# `messages.created_at` is a naive `timestamp` column, so a naive instant
# reads back unchanged whatever the session's time zone is.
T0 = datetime(2026, 1, 1, 12, 0)


def _instance(
    db: Session,
    user: User,
    agent_type: AgentType,
    status: AgentStatus = AgentStatus.ACTIVE,
) -> AgentInstance:
    instance = AgentInstance(
        id=uuid4(),
        agent_type_id=agent_type.id,
        user_id=user.id,
        status=status,
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
    message_id: UUID | None = None,
) -> Message:
    message = Message(
        id=message_id or uuid4(),
        agent_instance_id=instance.id,
        sender_type=SenderType.AGENT,
        content=content,
        created_at=at,
        requires_user_input=False,
    )
    db.add(message)
    db.flush()
    return message


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


def _own_type(
    overview: list[AgentTypeOverview], agent_type: AgentType
) -> AgentTypeOverview:
    matches = [entry for entry in overview if entry.id == str(agent_type.id)]
    assert len(matches) == 1
    return matches[0]


def _by_id(entry: AgentTypeOverview) -> dict[str, AgentInstanceResponse]:
    return {instance.id: instance for instance in entry.recent_instances}


def test_each_session_reports_its_count_and_latest_message(
    test_db: Session, test_user: User, test_agent_type: AgentType
) -> None:
    long_session = _instance(test_db, test_user, test_agent_type)
    short_session = _instance(test_db, test_user, test_agent_type)
    empty_session = _instance(test_db, test_user, test_agent_type)
    # Inserted out of time order: the latest is picked by `created_at`, not by
    # insertion order.
    _message(test_db, long_session, "second", T0 + timedelta(minutes=2))
    _message(test_db, long_session, "third", T0 + timedelta(minutes=3))
    _message(test_db, long_session, "first", T0 + timedelta(minutes=1))
    _message(test_db, short_session, "only", T0 + timedelta(minutes=5))

    entry = _own_type(
        get_all_agent_types_with_instances(test_db, test_user.id), test_agent_type
    )
    sessions = _by_id(entry)

    reported = {
        session_id: (
            session.chat_length,
            session.latest_message,
            session.latest_message_at,
        )
        for session_id, session in sessions.items()
    }
    assert reported == {
        str(long_session.id): (3, "third", T0 + timedelta(minutes=3)),
        str(short_session.id): (1, "only", T0 + timedelta(minutes=5)),
        # A session with no messages has no stats row; it is listed with
        # defaults, as before.
        str(empty_session.id): (0, None, None),
    }
    assert entry.total_instances == 3
    assert entry.active_instances == 3


def test_matches_the_session_list_stats(
    test_db: Session, test_user: User, test_agent_type: AgentType
) -> None:
    """The overview and the session list read the same numbers."""
    sessions = [_instance(test_db, test_user, test_agent_type) for _ in range(3)]
    for index, session in enumerate(sessions):
        for step in range(index + 1):
            _message(
                test_db,
                session,
                f"session {index} step {step}",
                T0 + timedelta(minutes=10 * index + step),
            )

    list_stats = _get_instance_message_stats(test_db, [s.id for s in sessions])
    entry = _own_type(
        get_all_agent_types_with_instances(test_db, test_user.id), test_agent_type
    )

    for session_id, session in _by_id(entry).items():
        stats = list_stats[UUID(session_id)]
        assert session.chat_length == stats["message_count"]
        assert session.latest_message == stats["latest_message"]
        assert session.latest_message_at == stats["latest_message_at"]


def test_latest_activity_orders_the_sessions(
    test_db: Session, test_user: User, test_agent_type: AgentType
) -> None:
    """Awaiting input first, then the most recent message first."""
    quiet = _instance(test_db, test_user, test_agent_type)
    recent = _instance(test_db, test_user, test_agent_type)
    waiting = _instance(
        test_db, test_user, test_agent_type, status=AgentStatus.AWAITING_INPUT
    )
    _message(test_db, quiet, "a while ago", T0 + timedelta(minutes=1))
    _message(test_db, recent, "just now", T0 + timedelta(hours=2))
    _message(test_db, waiting, "a question?", T0 + timedelta(minutes=30))

    entry = _own_type(
        get_all_agent_types_with_instances(test_db, test_user.id), test_agent_type
    )

    assert [session.id for session in entry.recent_instances] == [
        str(waiting.id),
        str(recent.id),
        str(quiet.id),
    ]


def test_deleted_session_is_left_out_and_its_messages_are_not_read(
    test_db: Session, test_user: User, test_agent_type: AgentType
) -> None:
    kept = _instance(test_db, test_user, test_agent_type)
    deleted = _instance(test_db, test_user, test_agent_type, status=AgentStatus.DELETED)
    _message(test_db, kept, "kept", T0)
    _message(test_db, deleted, "gone", T0 + timedelta(hours=1))

    entry = _own_type(
        get_all_agent_types_with_instances(test_db, test_user.id), test_agent_type
    )

    assert set(_by_id(entry)) == {str(kept.id)}
    assert entry.total_instances == 1


def test_created_at_tie_picks_the_same_message_every_time(
    test_db: Session, test_user: User, test_agent_type: AgentType
) -> None:
    """Two messages at the same instant: the higher id wins, on every call.

    The old window query's `row_number()` had no tiebreak, so the overview
    could show either one from one load to the next.
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
        entry = _own_type(
            get_all_agent_types_with_instances(test_db, test_user.id),
            test_agent_type,
        )
        session = _by_id(entry)[str(instance.id)]
        assert session.latest_message == "tie, high id"
        assert session.chat_length == 3


def test_no_window_over_every_message(
    test_db: Session, test_user: User, test_agent_type: AgentType
) -> None:
    """The shape that keeps a user with long sessions fast: no statement in
    the call has an `OVER (...)` window (it buffered every row, content
    included); the latest message comes from a LATERAL lookup."""
    instance = _instance(test_db, test_user, test_agent_type)
    _message(test_db, instance, "hello", T0)

    with _capture_sql(test_db) as statements:
        get_all_agent_types_with_instances(test_db, test_user.id)

    upper = [statement.upper() for statement in statements]
    assert not [sql for sql in upper if " OVER " in sql or "OVER(" in sql]
    assert any("LATERAL" in sql for sql in upper)
