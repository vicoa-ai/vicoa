"""Integration tests for the server-projected ``rate_limited_until`` column.

The daemon PATCHes ``{"usage": {...}}`` onto ``instance_metadata`` each turn;
``update_agent_instance_endpoint`` projects the binding rate-limit reset instant
into ``agent_instances.rate_limited_until`` (set and cleared by the same
projection). ``get_all_agent_instances(rate_limited_only=True)`` then surfaces
just the currently-blocked rows for the auto-continue automation, bounded by a
max-age guard so a permanently-dead session isn't retried forever.

Plan: plans/todos/auto-continue-rate-limited-sessions.md (§2 projection, §4
filter + derived fields, §5 max-age guard).
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from backend.db.queries import _RATE_LIMIT_MAX_AGE, get_all_agent_instances
from servers.api.models import UpdateAgentInstanceRequest
from servers.api.routers import update_agent_instance_endpoint
from shared.database.automation_models import Automation, AutomationRun
from shared.database.enums import AgentStatus
from shared.database.models import AgentInstance, Machine, Message, User, UserAgent
from shared.database.session import SessionLocal

pytestmark = pytest.mark.integration


def _usage(used_pct: float, resets_at: str | None) -> dict:
    """A minimal usage blob with a single Session window at ``used_pct``."""
    return {
        "usage": {
            "limits": {
                "windows": [
                    {
                        "id": "five_hour",
                        "label": "Session",
                        "used_pct": used_pct,
                        "resets_at": resets_at,
                    }
                ]
            }
        }
    }


def _patch(instance_id: UUID, user_id: UUID, metadata: dict) -> None:
    request = UpdateAgentInstanceRequest.model_validate({"instance_metadata": metadata})
    with SessionLocal() as db:
        update_agent_instance_endpoint(
            instance_id=instance_id,
            update_data=request,
            user_id=str(user_id),
            db=db,
        )


def _row(instance_id: UUID) -> AgentInstance:
    with SessionLocal() as db:
        return db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()


@pytest.fixture
def user_and_instance() -> Iterator[tuple[UUID, UUID]]:
    user_id, agent_id, instance_id = uuid4(), uuid4(), uuid4()
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.flush()
        db.add(UserAgent(id=agent_id, user_id=user_id, name="claude"))
        db.add(
            AgentInstance(
                id=instance_id,
                user_agent_id=agent_id,
                user_id=user_id,
                status=AgentStatus.ACTIVE,
                name="orig",
            )
        )
        db.commit()
    try:
        yield user_id, instance_id
    finally:
        with SessionLocal() as db:
            db.query(Message).filter(Message.agent_instance_id == instance_id).delete()
            db.query(AgentInstance).filter(AgentInstance.user_id == user_id).delete()
            db.query(UserAgent).filter(UserAgent.user_id == user_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()


def test_maxed_window_usage_patch_sets_rate_limited_until(
    user_and_instance: tuple[UUID, UUID],
) -> None:
    user_id, instance_id = user_and_instance
    _patch(instance_id, user_id, _usage(100.0, "2026-08-20T18:00:00+00:00"))
    # reset + 45s buffer, stored UTC-naive (session tz is UTC).
    assert _row(instance_id).rate_limited_until == datetime(2026, 8, 20, 18, 0, 45)


def test_recovering_usage_patch_clears_rate_limited_until(
    user_and_instance: tuple[UUID, UUID],
) -> None:
    user_id, instance_id = user_and_instance
    _patch(instance_id, user_id, _usage(100.0, "2026-08-20T18:00:00+00:00"))
    assert _row(instance_id).rate_limited_until is not None
    # A later turn whose window dropped back under the limit clears the column.
    _patch(instance_id, user_id, _usage(42.0, "2026-08-20T23:00:00+00:00"))
    assert _row(instance_id).rate_limited_until is None


def test_non_usage_metadata_patch_preserves_rate_limited_until(
    user_and_instance: tuple[UUID, UUID],
) -> None:
    user_id, instance_id = user_and_instance
    _patch(instance_id, user_id, _usage(100.0, "2026-08-20T18:00:00+00:00"))
    before = _row(instance_id).rate_limited_until
    # An unrelated metadata write (no `usage` key) must not clobber the column.
    _patch(instance_id, user_id, {"source": "cli"})
    row = _row(instance_id)
    assert row.rate_limited_until == before
    assert row.instance_metadata.get("source") == "cli"


def test_credits_exhaustion_does_not_flag_rate_limited(
    user_and_instance: tuple[UUID, UUID],
) -> None:
    user_id, instance_id = user_and_instance
    _patch(
        instance_id,
        user_id,
        {
            "usage": {
                "limits": {
                    "windows": [],
                    "credits": {"unit": "usd", "remaining": 0.0},
                }
            }
        },
    )
    assert _row(instance_id).rate_limited_until is None


def test_rate_limited_only_filter_and_max_age_guard(
    user_and_instance: tuple[UUID, UUID],
) -> None:
    user_id, instance_id = user_and_instance
    # Currently blocked: reset in the near future.
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    _patch(instance_id, user_id, _usage(100.0, future))

    instances, total = get_all_agent_instances(
        SessionLocal(), user_id, rate_limited_only=True
    )
    assert total == 1
    resp = instances[0]
    assert resp.id == str(instance_id)
    assert resp.rate_limited is True
    assert resp.rate_limit_resets_at is not None

    # Age the row's reset well beyond the max-age guard: a permanently-dead
    # session must drop out of the sweep rather than be retried forever.
    stale = datetime.now(timezone.utc) - _RATE_LIMIT_MAX_AGE - timedelta(hours=1)
    with SessionLocal() as db:
        db.query(AgentInstance).filter(AgentInstance.id == instance_id).update(
            {"rate_limited_until": stale.replace(tzinfo=None)}
        )
        db.commit()
    _, total_after = get_all_agent_instances(
        SessionLocal(), user_id, rate_limited_only=True
    )
    assert total_after == 0


def _mk_automation(db, user_id: UUID, machine_id: UUID) -> UUID:
    aid = uuid4()
    db.add(
        Automation(
            id=aid,
            user_id=user_id,
            title="auto",
            prompt="…",
            machine_id=machine_id,
            directory="/x",
            session_config={"agent": "claude"},
            schedule_kind="recurring",
        )
    )
    db.flush()
    return aid


def _mk_session(db, user_id: UUID, agent_id: UUID) -> UUID:
    iid = uuid4()
    db.add(
        AgentInstance(
            id=iid,
            user_agent_id=agent_id,
            user_id=user_id,
            status=AgentStatus.ACTIVE,
        )
    )
    db.flush()
    return iid


def _link_run(db, automation_id: UUID, user_id: UUID, instance_id: UUID) -> None:
    db.add(
        AutomationRun(
            automation_id=automation_id,
            user_id=user_id,
            agent_instance_id=instance_id,
            status="fired",
        )
    )


def test_rate_limited_self_exclusion_is_scoped_to_the_calling_automation(
    user_and_instance: tuple[UUID, UUID],
) -> None:
    """A rate-limited session spawned by automation A is hidden only from A's
    OWN sweep (so A can't flag-and-continue its own runs), while a human caller
    and a *different* automation B still see it — B must be able to continue it.
    (Machine/Automation/Run rows cascade-clean when the fixture deletes the
    user.)"""
    user_id, target_id = user_and_instance  # the rate-limited session, owned by A
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    _patch(target_id, user_id, _usage(100.0, future))

    with SessionLocal() as db:
        agent_id = (
            db.query(AgentInstance.user_agent_id)
            .filter(AgentInstance.id == target_id)
            .scalar()
        )
        machine_id = uuid4()
        db.add(Machine(id=machine_id, user_id=user_id))
        db.flush()
        automation_a = _mk_automation(db, user_id, machine_id)
        automation_b = _mk_automation(db, user_id, machine_id)
        # target_id and caller_a are two runs of A; caller_b is a run of B.
        caller_a = _mk_session(db, user_id, agent_id)
        caller_b = _mk_session(db, user_id, agent_id)
        _link_run(db, automation_a, user_id, target_id)
        _link_run(db, automation_a, user_id, caller_a)
        _link_run(db, automation_b, user_id, caller_b)
        db.commit()

    # Human/manual caller (no id) sees the rate-limited session.
    _, human = get_all_agent_instances(SessionLocal(), user_id, rate_limited_only=True)
    assert human == 1

    # A's own sweep excludes A's session -> no self-continue loop.
    _, from_a = get_all_agent_instances(
        SessionLocal(), user_id, rate_limited_only=True, caller_instance_id=caller_a
    )
    assert from_a == 0

    # B's sweep still sees A's rate-limited session, so B can continue it.
    _, from_b = get_all_agent_instances(
        SessionLocal(), user_id, rate_limited_only=True, caller_instance_id=caller_b
    )
    assert from_b == 1

    # A non-UUID / unknown caller id is ignored (never 422s, no exclusion).
    _, junk = get_all_agent_instances(
        SessionLocal(), user_id, rate_limited_only=True, caller_instance_id="not-a-uuid"
    )
    assert junk == 1
