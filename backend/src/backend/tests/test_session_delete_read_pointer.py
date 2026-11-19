"""Deleting messages and the `last_read_message_id` foreign key.

`agent_instances.last_read_message_id` references `messages.id` with
`ON DELETE SET NULL`. Postgres carries that out with one
`UPDATE ONLY agent_instances SET last_read_message_id = NULL
WHERE $1 = last_read_message_id` per deleted message, whether or not any row
points at it. Without an index on the column each of those scans the whole
table, so deleting a long session (`delete_agent_instance` removes all of its
messages in one statement) or an account could outlast the statement timeout.

Pinned here: that per-message lookup uses `ix_agent_instances_last_read_message`
(read from the plan Postgres actually runs, custom and generic), and a session
with a few thousand messages still deletes with every pointer at its messages
set to NULL and other pointers left alone.
"""

import logging
import re
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, func, insert, select, text, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from backend.db.queries import delete_agent_instance
from shared.database.enums import AgentStatus, SenderType
from shared.database.models import AgentInstance, AgentType, Message, User

INDEX_NAME = "ix_agent_instances_last_read_message"

# The statement Postgres runs for the SET NULL action, as auto_explain logs it.
_FK_ACTION = re.compile(
    r'UPDATE ONLY "public"\."agent_instances" SET "last_read_message_id" = NULL'
)
_USES_INDEX = re.compile(rf"(Index Scan using|Bitmap Index Scan on) {INDEX_NAME}\b")
# Where SQLAlchemy's psycopg2 dialect logs each server NOTICE.
_NOTICE_LOGGER = "sqlalchemy.dialects.postgresql"


def _add_instance(db: Session, user_id: UUID, agent_type_id: UUID) -> AgentInstance:
    instance = AgentInstance(
        id=uuid4(),
        agent_type_id=agent_type_id,
        user_id=user_id,
        status=AgentStatus.ACTIVE,
        started_at=datetime.now(timezone.utc),
    )
    db.add(instance)
    db.flush()
    return instance


def _add_messages(db: Session, instance_id: UUID, count: int) -> list[UUID]:
    """Insert `count` agent messages in one round trip, oldest first."""
    start = datetime.now(timezone.utc)
    ids = [uuid4() for _ in range(count)]
    db.execute(
        insert(Message),
        [
            {
                "id": message_id,
                "agent_instance_id": instance_id,
                "sender_type": SenderType.AGENT,
                "content": f"message {n}",
                "created_at": start + timedelta(milliseconds=n),
            }
            for n, message_id in enumerate(ids)
        ],
    )
    return ids


def _point_at(db: Session, instance_id: UUID, message_id: UUID) -> None:
    db.execute(
        update(AgentInstance)
        .where(AgentInstance.id == instance_id)
        .values(last_read_message_id=message_id)
    )


@pytest.fixture
def fresh_session(
    test_engine: Engine, postgres_container: PostgresContainer
) -> Iterator[Session]:
    """A session on a brand-new server connection, rolled back at the end.

    Postgres caches the plan of a foreign-key action per connection, so a
    pooled connection that already deleted messages in an earlier test could
    hand back a plan made under other settings. `test_engine` is requested only
    so the schema exists.
    """
    engine = create_engine(postgres_container.get_connection_url(), poolclass=NullPool)
    try:
        with engine.connect() as conn:
            outer = conn.begin()
            session = Session(bind=conn, join_transaction_mode="create_savepoint")
            try:
                yield session
            finally:
                session.close()
                outer.rollback()
    finally:
        engine.dispose()


@pytest.mark.parametrize("plan_cache_mode", ["force_custom_plan", "force_generic_plan"])
def test_fk_action_on_message_delete_uses_the_index(
    fresh_session: Session, plan_cache_mode: str, caplog: pytest.LogCaptureFixture
) -> None:
    db = fresh_session
    user = User(id=uuid4(), email="alpha@example.com", display_name="Alpha")
    db.add(user)
    db.flush()
    agent_type = AgentType(id=uuid4(), user_id=user.id, name="claude code")
    db.add(agent_type)
    db.flush()
    instance = _add_instance(db, user.id, agent_type.id)
    message_ids = _add_messages(db, instance.id, 3)
    _point_at(db, instance.id, message_ids[-1])
    db.flush()

    # auto_explain logs the plan of every statement, nested ones included (the
    # foreign-key actions run as nested statements), as a NOTICE, and
    # SQLAlchemy's psycopg2 dialect logs each NOTICE at INFO. Sequential scans
    # are switched off so the assertion is "the planner can use the index",
    # not "a seq scan looked cheaper on a tiny test table".
    for statement in (
        "LOAD 'auto_explain'",
        "SET LOCAL auto_explain.log_min_duration = 0",
        "SET LOCAL auto_explain.log_nested_statements = on",
        "SET LOCAL auto_explain.log_level = notice",
        "SET LOCAL enable_seqscan = off",
        f"SET LOCAL plan_cache_mode = {plan_cache_mode}",
    ):
        db.execute(text(statement))

    caplog.set_level(logging.INFO, logger=_NOTICE_LOGGER)
    caplog.clear()
    db.execute(
        text("DELETE FROM messages WHERE agent_instance_id = :id"),
        {"id": instance.id},
    )

    notices = [r.getMessage() for r in caplog.records if r.name == _NOTICE_LOGGER]
    fk_plans = [notice for notice in notices if _FK_ACTION.search(notice)]
    # One per deleted message, so the check below can't pass on zero plans.
    assert len(fk_plans) == len(message_ids), notices
    for plan in fk_plans:
        assert _USES_INDEX.search(plan), plan


def test_deleting_a_long_session_clears_every_pointer_at_its_messages(
    test_db: Session, test_user: User, test_agent_type: AgentType
) -> None:
    doomed = _add_instance(test_db, test_user.id, test_agent_type.id)
    neighbour = _add_instance(test_db, test_user.id, test_agent_type.id)
    bystander = _add_instance(test_db, test_user.id, test_agent_type.id)

    doomed_messages = _add_messages(test_db, doomed.id, 3000)
    bystander_messages = _add_messages(test_db, bystander.id, 5)

    _point_at(test_db, doomed.id, doomed_messages[-1])
    # Not something the app writes today, but the foreign key allows it, and
    # the SET NULL action has to reach it all the same.
    _point_at(test_db, neighbour.id, doomed_messages[10])
    _point_at(test_db, bystander.id, bystander_messages[-1])
    test_db.commit()

    assert delete_agent_instance(test_db, doomed.id, test_user.id) is True
    test_db.expire_all()

    remaining = test_db.execute(
        select(func.count())
        .select_from(Message)
        .where(Message.agent_instance_id == doomed.id)
    ).scalar_one()
    assert remaining == 0

    rows = {
        row.id: row
        for row in test_db.execute(
            select(
                AgentInstance.id,
                AgentInstance.status,
                AgentInstance.last_read_message_id,
            ).where(AgentInstance.id.in_([doomed.id, neighbour.id, bystander.id]))
        )
    }
    assert rows[doomed.id].status == AgentStatus.DELETED
    assert rows[doomed.id].last_read_message_id is None
    assert rows[neighbour.id].last_read_message_id is None
    assert rows[bystander.id].last_read_message_id == bystander_messages[-1]

    bystander_left = test_db.execute(
        select(func.count())
        .select_from(Message)
        .where(Message.agent_instance_id == bystander.id)
    ).scalar_one()
    assert bystander_left == len(bystander_messages)
