"""Integration tests for filing a session under a project from the CLI.

`vicoa session update --project` sends `project_id` on the agent-facing
PATCH /agent-instances/{id}. Unlike the dashboard's move (which may file into
a shared project the caller edits), this surface is owner-only: the target
must be one of the caller's own personal projects.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from servers.api.models import UpdateAgentInstanceRequest
from servers.api.routers import update_agent_instance_endpoint
from shared.database.enums import AgentStatus
from shared.database.models import AgentInstance, AgentType, User
from shared.database.session import SessionLocal
from shared.database.task_models import Project

pytestmark = pytest.mark.integration


@dataclass
class Fixture:
    user_id: UUID
    instance_id: UUID
    home_project_id: UUID
    other_project_id: UUID
    archived_project_id: UUID
    foreign_project_id: UUID


@pytest.fixture
def filed_session() -> Iterator[Fixture]:
    """A session filed under one of its owner's projects, two more projects of
    theirs (one archived), and a project that belongs to someone else."""
    user_id, stranger_id, agent_id, instance_id = uuid4(), uuid4(), uuid4(), uuid4()
    home, other, archived, foreign = uuid4(), uuid4(), uuid4(), uuid4()
    with SessionLocal() as db:
        for uid in (user_id, stranger_id):
            db.add(User(id=uid, email=f"{uid}@test.vicoa", display_name="t"))
        db.flush()
        db.add(Project(id=home, user_id=user_id, name="app"))
        db.add(Project(id=other, user_id=user_id, name="app-twin"))
        db.add(Project(id=archived, user_id=user_id, name="old", is_archived=True))
        db.add(Project(id=foreign, user_id=stranger_id, name="theirs"))
        db.add(AgentType(id=agent_id, user_id=user_id, name="claude"))
        db.add(
            AgentInstance(
                id=instance_id,
                agent_type_id=agent_id,
                user_id=user_id,
                status=AgentStatus.ACTIVE,
                project="~/src/app",
                project_id=home,
            )
        )
        db.commit()
    try:
        yield Fixture(user_id, instance_id, home, other, archived, foreign)
    finally:
        with SessionLocal() as db:
            db.query(AgentInstance).filter(AgentInstance.user_id == user_id).delete()
            db.query(AgentType).filter(AgentType.user_id == user_id).delete()
            db.query(Project).filter(
                Project.user_id.in_([user_id, stranger_id])
            ).delete()
            db.query(User).filter(User.id.in_([user_id, stranger_id])).delete()
            db.commit()


def _patch(user_id: UUID, instance_id: UUID, body: dict) -> str | None:
    request = UpdateAgentInstanceRequest.model_validate(body)
    with SessionLocal() as db:
        response = update_agent_instance_endpoint(
            instance_id=instance_id,
            update_data=request,
            user_id=str(user_id),
            db=db,
        )
    return response.project_id


def _row(instance_id: UUID) -> AgentInstance:
    with SessionLocal() as db:
        return db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()


def test_files_the_session_under_another_own_project(filed_session: Fixture) -> None:
    """Only the filing changes — the folder the session runs in stays put —
    and the response echoes the new project (the CLI's old-server check)."""
    f = filed_session
    echoed = _patch(f.user_id, f.instance_id, {"project_id": str(f.other_project_id)})
    row = _row(f.instance_id)
    assert row.project_id == f.other_project_id
    assert echoed == str(f.other_project_id)
    assert row.project == "~/src/app"


def test_null_files_the_session_under_no_project(filed_session: Fixture) -> None:
    f = filed_session
    assert _patch(f.user_id, f.instance_id, {"project_id": None}) is None
    assert _row(f.instance_id).project_id is None


def test_absent_project_id_leaves_the_filing_alone(filed_session: Fixture) -> None:
    f = filed_session
    _patch(f.user_id, f.instance_id, {"name": "renamed"})
    assert _row(f.instance_id).project_id == f.home_project_id


def test_filing_under_an_archived_project_unarchives_it(
    filed_session: Fixture,
) -> None:
    """A session is live work, the same self-heal the dashboard move and the
    register path apply."""
    f = filed_session
    _patch(f.user_id, f.instance_id, {"project_id": str(f.archived_project_id)})
    with SessionLocal() as db:
        project = db.get(Project, f.archived_project_id)
        assert project is not None
        assert project.is_archived is False
    assert _row(f.instance_id).project_id == f.archived_project_id


def test_someone_elses_project_is_not_found(filed_session: Fixture) -> None:
    f = filed_session
    with pytest.raises(HTTPException) as exc:
        _patch(f.user_id, f.instance_id, {"project_id": str(f.foreign_project_id)})
    assert exc.value.status_code == 404
    assert _row(f.instance_id).project_id == f.home_project_id


def test_malformed_project_id_is_rejected(filed_session: Fixture) -> None:
    f = filed_session
    with pytest.raises(HTTPException) as exc:
        _patch(f.user_id, f.instance_id, {"project_id": "not-a-uuid"})
    assert exc.value.status_code == 400
    assert _row(f.instance_id).project_id == f.home_project_id


def test_another_users_session_is_not_found(filed_session: Fixture) -> None:
    f = filed_session
    with pytest.raises(HTTPException) as exc:
        _patch(uuid4(), f.instance_id, {"project_id": str(f.other_project_id)})
    assert exc.value.status_code == 404
    assert _row(f.instance_id).project_id == f.home_project_id
