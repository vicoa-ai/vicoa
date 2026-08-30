"""Constructed-fixture suite for the workspace search queries (cmd+K palette).

Exercises backend.db.search_queries against a real database: tier ranking
(exact > prefix > contains > project > message), match_source/snippet
computation, DELETED exclusion, closed-task deprioritization, LIKE-metachar
escaping, and — because every query is a cross-user ILIKE sweep — user scoping.

These tests hit a real database, so they are marked `integration`.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.api.search import is_statement_timeout
from backend.db import search_queries
from shared.database import (
    AgentInstance,
    Automation,
    Machine,
    Message,
    Project,
    Task,
    User,
    UserAgent,
)
from shared.database.enums import AgentStatus, SenderType
from shared.database.session import SessionLocal

pytestmark = pytest.mark.integration

BASE = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def workspace() -> Iterator[dict]:
    """Two users' worth of sessions/tasks/automations built around the term
    "stripe"; yields ids keyed by role. The second user's rows exist purely to
    prove scoping."""
    user_id, other_user_id = uuid4(), uuid4()
    agent_id, other_agent_id = uuid4(), uuid4()
    machine_id = uuid4()
    project_id, other_project_id = uuid4(), uuid4()

    ids = {
        "user_id": user_id,
        # Sessions, one per rank tier.
        "session_exact": uuid4(),  # name == "stripe"
        "session_prefix": uuid4(),  # name "stripe experiments"
        "session_contains": uuid4(),  # name "My stripe fixes"
        "session_project": uuid4(),  # project path contains "stripe"
        "session_message": uuid4(),  # only messages contain "stripe"
        "session_deleted": uuid4(),  # matching name but DELETED
        "session_other_user": uuid4(),  # matching name, wrong user
        # Tasks.
        "task_title": uuid4(),
        "task_description": uuid4(),
        "task_done": uuid4(),
        "task_percent": uuid4(),  # title "100% coverage" (escape check)
        "task_percent_decoy": uuid4(),  # title "1000 coverage"
        "task_other_user": uuid4(),
        # Automations.
        "automation_title": uuid4(),
        "automation_prompt": uuid4(),
    }

    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.add(
            User(
                id=other_user_id, email=f"{other_user_id}@test.vicoa", display_name="o"
            )
        )
        # Flush parents before children — the messages↔agent_instances FK cycle
        # keeps SQLAlchemy from topologically sorting one big flush.
        db.flush()
        db.add(UserAgent(id=agent_id, user_id=user_id, name=f"agent-{agent_id}"))
        db.add(
            UserAgent(
                id=other_agent_id, user_id=other_user_id, name=f"agent-{other_agent_id}"
            )
        )
        db.add(Machine(id=machine_id, user_id=user_id, display_name="test-box"))
        db.add(Project(id=project_id, user_id=user_id, name="Search fixtures"))
        db.add(Project(id=other_project_id, user_id=other_user_id, name="Other"))
        db.flush()

        def instance(
            key: str,
            *,
            name=None,
            project=None,
            status=AgentStatus.ACTIVE,
            user=user_id,
            agent=agent_id,
            age_minutes=0,
        ):
            db.add(
                AgentInstance(
                    id=ids[key],
                    user_agent_id=agent,
                    user_id=user,
                    name=name,
                    project=project,
                    status=status,
                    updated_at=BASE - timedelta(minutes=age_minutes),
                )
            )

        instance("session_exact", name="stripe")
        instance("session_prefix", name="stripe experiments")
        instance("session_contains", name="My stripe fixes")
        instance("session_project", name="unrelated", project="/home/nick/stripe-tools")
        instance("session_message", name=None)
        instance("session_deleted", name="stripe deleted", status=AgentStatus.DELETED)
        instance(
            "session_other_user",
            name="stripe leak",
            user=other_user_id,
            agent=other_agent_id,
        )
        db.flush()

        db.add(
            Message(
                agent_instance_id=ids["session_message"],
                sender_type=SenderType.AGENT,
                content="Investigating stripe alpha issue",
                created_at=BASE - timedelta(minutes=10),
            )
        )
        db.add(
            Message(
                agent_instance_id=ids["session_message"],
                sender_type=SenderType.AGENT,
                content="Root cause: stripe beta webhook signature drift",
                created_at=BASE - timedelta(minutes=1),
            )
        )
        # CJK content for the short-pattern (recency-bounded) message tier.
        db.add(
            Message(
                agent_instance_id=ids["session_message"],
                sender_type=SenderType.AGENT,
                content="部署任务已经完成",
                created_at=BASE - timedelta(minutes=5),
            )
        )

        def task(
            key: str,
            *,
            title,
            description=None,
            status="todo",
            user=user_id,
            project=project_id,
        ):
            db.add(
                Task(
                    id=ids[key],
                    user_id=user,
                    project_id=project,
                    title=title,
                    description=description,
                    status=status,
                )
            )

        task("task_title", title="Fix stripe webhook")
        task(
            "task_description",
            title="Improve onboarding",
            description="Blocked until the stripe checkout flow settles down",
        )
        task("task_done", title="stripe cleanup", status="done")
        task("task_percent", title="100% coverage")
        task("task_percent_decoy", title="1000 coverage")
        task(
            "task_other_user",
            title="stripe leak",
            user=other_user_id,
            project=other_project_id,
        )

        db.add(
            Automation(
                id=ids["automation_title"],
                user_id=user_id,
                title="Nightly stripe reconciliation",
                prompt="Reconcile the ledgers",
                machine_id=machine_id,
                directory="/tmp",
                session_config={"agent": "claude"},
                schedule_kind="recurring",
            )
        )
        db.add(
            Automation(
                id=ids["automation_prompt"],
                user_id=user_id,
                title="Ledger sweep",
                prompt="Check the stripe dashboard for failed payouts",
                machine_id=machine_id,
                directory="/tmp",
                session_config={"agent": "claude"},
                schedule_kind="once",
            )
        )
        db.commit()

    try:
        yield ids
    finally:
        with SessionLocal() as db:
            for user in (user_id, other_user_id):
                db.query(Message).filter(
                    Message.agent_instance_id.in_(
                        db.query(AgentInstance.id).filter(AgentInstance.user_id == user)
                    )
                ).delete(synchronize_session=False)
                db.query(AgentInstance).filter(AgentInstance.user_id == user).delete(
                    synchronize_session=False
                )
                db.query(Automation).filter(Automation.user_id == user).delete()
                db.query(Task).filter(Task.user_id == user).delete()
                db.query(Project).filter(Project.user_id == user).delete()
                db.query(Machine).filter(Machine.user_id == user).delete()
                db.query(UserAgent).filter(UserAgent.user_id == user).delete()
                db.query(User).filter(User.id == user).delete()
            db.commit()


def _result_ids(rows: list[dict]) -> list[UUID | str]:
    return [row["id"] for row in rows]


def test_search_sessions_rank_scope_and_snippet(workspace):
    with SessionLocal() as db:
        rows = search_queries.search_sessions(db, workspace["user_id"], "stripe", 20)

    assert _result_ids(rows) == [
        str(workspace["session_exact"]),
        str(workspace["session_prefix"]),
        str(workspace["session_contains"]),
        str(workspace["session_project"]),
        str(workspace["session_message"]),
    ]

    by_id = {row["id"]: row for row in rows}
    assert by_id[str(workspace["session_exact"])]["match_source"] == "name"
    assert by_id[str(workspace["session_project"])]["match_source"] == "project"

    message_row = by_id[str(workspace["session_message"])]
    assert message_row["match_source"] == "message"
    # Snippet comes from the NEWEST matching message.
    assert "stripe beta" in message_row["snippet"]
    # Title fallback data is populated for unnamed sessions.
    assert message_row["latest_message"] is not None


def test_search_sessions_short_pattern_uses_bounded_message_tier(workspace):
    """A short term (e.g. a bare 2-char CJK word) still finds message matches
    through the recency-bounded message tier."""
    with SessionLocal() as db:
        rows = search_queries.search_sessions(db, workspace["user_id"], "任务", 20)

    assert _result_ids(rows) == [str(workspace["session_message"])]
    assert rows[0]["match_source"] == "message"
    assert "任务" in rows[0]["snippet"]


def test_search_sessions_message_tier_skipped_when_named_fill_limit(workspace):
    """With limit=2 the name tiers fill every slot; the message-matched
    session must not appear (and must not displace better-ranked rows)."""
    with SessionLocal() as db:
        rows = search_queries.search_sessions(db, workspace["user_id"], "stripe", 2)

    assert _result_ids(rows) == [
        str(workspace["session_exact"]),
        str(workspace["session_prefix"]),
    ]


def test_search_tasks_rank_scope_and_escape(workspace):
    with SessionLocal() as db:
        rows = search_queries.search_tasks(db, workspace["user_id"], "stripe", 20)

    # Match-quality tier wins first — "stripe cleanup" is a prefix match and
    # outranks the contains match even though it's done (closed_rank only
    # breaks ties within a tier) — then description matches last; the other
    # user's task never appears.
    result_ids = _result_ids(rows)
    assert result_ids == [
        workspace["task_done"],
        workspace["task_title"],
        workspace["task_description"],
    ]

    by_id = {row["id"]: row for row in rows}
    assert by_id[workspace["task_title"]]["match_source"] == "title"
    assert by_id[workspace["task_title"]]["snippet"] is None
    description_row = by_id[workspace["task_description"]]
    assert description_row["match_source"] == "description"
    assert "stripe checkout" in description_row["snippet"]

    # LIKE metacharacters are literals: "100%" must not match "1000 coverage".
    with SessionLocal() as db:
        rows = search_queries.search_tasks(db, workspace["user_id"], "100%", 20)
    assert _result_ids(rows) == [workspace["task_percent"]]


def test_search_automations_title_and_prompt(workspace):
    with SessionLocal() as db:
        rows = search_queries.search_automations(db, workspace["user_id"], "stripe", 10)

    assert _result_ids(rows) == [
        workspace["automation_title"],
        workspace["automation_prompt"],
    ]
    by_id = {row["id"]: row for row in rows}
    assert by_id[workspace["automation_title"]]["match_source"] == "title"
    prompt_row = by_id[workspace["automation_prompt"]]
    assert prompt_row["match_source"] == "prompt"
    assert "stripe dashboard" in prompt_row["snippet"]


def test_statement_timeout_is_detected_from_real_driver():
    """SET LOCAL statement_timeout + a slow statement must surface as an
    OperationalError that is_statement_timeout() recognizes (SQLSTATE 57014) —
    the mapping the /search endpoint turns into a retryable 503."""
    with SessionLocal() as db:
        db.execute(text("SET LOCAL statement_timeout = 50"))
        with pytest.raises(OperationalError) as excinfo:
            db.execute(text("SELECT pg_sleep(1)"))
        assert is_statement_timeout(excinfo.value)
