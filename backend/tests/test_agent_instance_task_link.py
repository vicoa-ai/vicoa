"""Integration tests: agent_instances.task_id links a session to a task via CLI.

Covers the "Start Session via Task via CLI" feature — the agent-facing server
(the surface the CLI authenticates against) can now link a task at registration
(`vicoa <agent> --task`) and via the instance PATCH (`vicoa session update
--task/--unlink-task`). Linking reuses the existing `task_id` column, the
ownership-scoped `get_task`, and the `before_flush` status sync, so a linked
task's status follows the run. Hits a real Postgres, so marked `integration`.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from backend.db.task_queries import create_task, get_task
from servers.api.models import (
    RegisterAgentInstanceRequest,
    UpdateAgentInstanceRequest,
)
from servers.api.routers import (
    register_agent_instance_endpoint,
    update_agent_instance_endpoint,
)
from shared.database.agent_instances import create_agent_instance
from shared.database.models import AgentInstance, User, UserAgent
from shared.database.session import SessionLocal
from shared.database.task_models import Project, Task

pytestmark = pytest.mark.integration


@pytest.fixture
def user_id() -> Iterator[UUID]:
    """A bare user; cleans up every row the tests hang off it."""
    uid = uuid4()
    with SessionLocal() as db:
        db.add(User(id=uid, email=f"{uid}@test.vicoa", display_name="t"))
        db.commit()
    try:
        yield uid
    finally:
        with SessionLocal() as db:
            db.query(AgentInstance).filter(AgentInstance.user_id == uid).delete()
            db.query(Task).filter(Task.user_id == uid).delete()
            db.query(Project).filter(Project.user_id == uid).delete()
            db.query(UserAgent).filter(UserAgent.user_id == uid).delete()
            db.query(User).filter(User.id == uid).delete()
            db.commit()


def _make_task(uid: UUID, status: str = "todo") -> UUID:
    with SessionLocal() as db:
        task = create_task(db, uid, "Fix the flaky test", status=status)
        return task.id


# --- registration (`vicoa <agent> --task`) ---------------------------------


def test_registration_links_owned_task_and_drives_status(user_id: UUID) -> None:
    """Spawning with a task_id stamps the link, and because the new instance is
    ACTIVE the before_flush sync flips the task todo → in_progress."""
    task_id = _make_task(user_id, status="todo")
    instance_id = uuid4()

    with SessionLocal() as db:
        register_agent_instance_endpoint(
            request=RegisterAgentInstanceRequest(
                agent_type="claude",
                agent_instance_id=str(instance_id),
                task_id=str(task_id),
            ),
            user_id=str(user_id),
            db=db,
        )

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        assert row.task_id == task_id
        assert get_task(db, user_id, task_id).status == "in_progress"


def test_registration_without_task_leaves_link_null(user_id: UUID) -> None:
    """No --task means no link — the common case must not regress."""
    instance_id = uuid4()

    with SessionLocal() as db:
        register_agent_instance_endpoint(
            request=RegisterAgentInstanceRequest(
                agent_type="claude",
                agent_instance_id=str(instance_id),
            ),
            user_id=str(user_id),
            db=db,
        )

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        assert row.task_id is None


def test_registration_rejects_foreign_task(user_id: UUID) -> None:
    """A task owned by another user is a 404 — never links across tenants, and
    the instance is not created behind the failed link."""
    other_uid = uuid4()
    with SessionLocal() as db:
        db.add(User(id=other_uid, email=f"{other_uid}@test.vicoa", display_name="o"))
        db.commit()
    other_task_id = _make_task(other_uid)

    instance_id = uuid4()
    try:
        with SessionLocal() as db:
            with pytest.raises(HTTPException) as exc:
                register_agent_instance_endpoint(
                    request=RegisterAgentInstanceRequest(
                        agent_type="claude",
                        agent_instance_id=str(instance_id),
                        task_id=str(other_task_id),
                    ),
                    user_id=str(user_id),
                    db=db,
                )
            assert exc.value.status_code == 404
        with SessionLocal() as db:
            assert (
                db.query(AgentInstance).filter(AgentInstance.id == instance_id).first()
                is None
            )
    finally:
        with SessionLocal() as db:
            db.query(Task).filter(Task.user_id == other_uid).delete()
            db.query(Project).filter(Project.user_id == other_uid).delete()
            db.query(User).filter(User.id == other_uid).delete()
            db.commit()


def test_registration_rejects_malformed_task_id(user_id: UUID) -> None:
    """A non-UUID task_id is a clean 400, not a 500."""
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            register_agent_instance_endpoint(
                request=RegisterAgentInstanceRequest(
                    agent_type="claude",
                    agent_instance_id=str(uuid4()),
                    task_id="not-a-uuid",
                ),
                user_id=str(user_id),
                db=db,
            )
        assert exc.value.status_code == 400


# --- PATCH (`vicoa session update --task / --unlink-task`) ------------------


def test_patch_links_task_onto_running_session(user_id: UUID) -> None:
    """The §8b late link: assigning a task to an already-ACTIVE session stamps
    task_id and flips the task to in_progress on the same commit."""
    task_id = _make_task(user_id, status="todo")
    instance_id = uuid4()
    with SessionLocal() as db:
        create_agent_instance(db, user_id, agent_name="claude", instance_id=instance_id)
        db.commit()

    with SessionLocal() as db:
        update_agent_instance_endpoint(
            instance_id=instance_id,
            update_data=UpdateAgentInstanceRequest(task_id=str(task_id)),
            user_id=str(user_id),
            db=db,
        )

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        assert row.task_id == task_id
        assert get_task(db, user_id, task_id).status == "in_progress"


def test_patch_unlinks_task(user_id: UUID) -> None:
    """An explicit null clears the link (--unlink-task)."""
    task_id = _make_task(user_id, status="todo")
    instance_id = uuid4()
    with SessionLocal() as db:
        inst = create_agent_instance(
            db, user_id, agent_name="claude", instance_id=instance_id
        )
        inst.task_id = task_id
        db.commit()

    with SessionLocal() as db:
        update_agent_instance_endpoint(
            instance_id=instance_id,
            update_data=UpdateAgentInstanceRequest(task_id=None),
            user_id=str(user_id),
            db=db,
        )

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        assert row.task_id is None


def test_patch_preserves_link_when_task_absent(user_id: UUID) -> None:
    """A PATCH that omits task_id (e.g. a rename) leaves the link untouched —
    field-present semantics, not a default-None clobber."""
    task_id = _make_task(user_id, status="todo")
    instance_id = uuid4()
    with SessionLocal() as db:
        inst = create_agent_instance(
            db, user_id, agent_name="claude", instance_id=instance_id
        )
        inst.task_id = task_id
        db.commit()

    with SessionLocal() as db:
        update_agent_instance_endpoint(
            instance_id=instance_id,
            update_data=UpdateAgentInstanceRequest(name="Renamed"),
            user_id=str(user_id),
            db=db,
        )

    with SessionLocal() as db:
        row = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        assert row.name == "Renamed"
        assert row.task_id == task_id


def test_patch_rejects_foreign_task(user_id: UUID) -> None:
    """Linking someone else's task via PATCH is a 404, same scoping as spawn."""
    other_uid = uuid4()
    with SessionLocal() as db:
        db.add(User(id=other_uid, email=f"{other_uid}@test.vicoa", display_name="o"))
        db.commit()
    other_task_id = _make_task(other_uid)

    instance_id = uuid4()
    with SessionLocal() as db:
        create_agent_instance(db, user_id, agent_name="claude", instance_id=instance_id)
        db.commit()

    try:
        with SessionLocal() as db:
            with pytest.raises(HTTPException) as exc:
                update_agent_instance_endpoint(
                    instance_id=instance_id,
                    update_data=UpdateAgentInstanceRequest(task_id=str(other_task_id)),
                    user_id=str(user_id),
                    db=db,
                )
            assert exc.value.status_code == 404
    finally:
        with SessionLocal() as db:
            db.query(Task).filter(Task.user_id == other_uid).delete()
            db.query(Project).filter(Project.user_id == other_uid).delete()
            db.query(User).filter(User.id == other_uid).delete()
            db.commit()
