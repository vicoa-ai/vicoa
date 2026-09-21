"""Integration tests for the PATCH /agent-instances/{id} folder move.

`vicoa session update --worktree` re-files a session under another checkout
of its repo by sending `project` + `worktree_name` + `repo_root` — the same
three fields registration stamps. The sidebar groups worktree sessions by
`project`, so this is what moves a session whose agent wandered into a
worktree on its own out from under the main checkout.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from servers.api.models import UpdateAgentInstanceRequest
from servers.api.routers import update_agent_instance_endpoint
from shared.database.enums import AgentStatus
from shared.database.models import AgentInstance, AgentType, Message, User
from shared.database.session import SessionLocal

pytestmark = pytest.mark.integration


@pytest.fixture
def main_checkout_session() -> Iterator[tuple[UUID, UUID, UUID]]:
    """A session registered from a repo's main checkout, filed under a
    project, with the usage blob the headless runners keep on metadata."""
    user_id, agent_id, instance_id, project_id = uuid4(), uuid4(), uuid4(), uuid4()
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.flush()
        db.add(AgentType(id=agent_id, user_id=user_id, name="claude"))
        db.add(
            AgentInstance(
                id=instance_id,
                agent_type_id=agent_id,
                user_id=user_id,
                status=AgentStatus.ACTIVE,
                project="~/src/app",
                home_dir="/Users/t",
                instance_metadata={
                    "source": "app",
                    "repo_root": "~/src/app",
                    "usage": {"context": {"percent": 40}},
                },
            )
        )
        db.commit()
    try:
        yield user_id, instance_id, project_id
    finally:
        with SessionLocal() as db:
            db.query(Message).filter(Message.agent_instance_id == instance_id).delete()
            db.query(AgentInstance).filter(AgentInstance.user_id == user_id).delete()
            db.query(AgentType).filter(AgentType.user_id == user_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()


def _patch(user_id: UUID, instance_id: UUID, body: dict) -> None:
    request = UpdateAgentInstanceRequest.model_validate(body)
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


def test_move_into_a_worktree_stamps_path_name_and_root(
    main_checkout_session: tuple[UUID, UUID, UUID],
) -> None:
    """The three registration fields move together; unrelated metadata
    (source, the live usage blob) survives the write."""
    user_id, instance_id, _ = main_checkout_session
    _patch(
        user_id,
        instance_id,
        {
            "project": "~/vicoa/workspaces/app-worktrees/feat-x/app",
            "worktree_name": "feat-x",
            "repo_root": "~/src/app",
        },
    )
    row = _row(instance_id)
    assert row.project == "~/vicoa/workspaces/app-worktrees/feat-x/app"
    assert row.instance_metadata["worktree_name"] == "feat-x"
    assert row.instance_metadata["repo_root"] == "~/src/app"
    assert row.instance_metadata["source"] == "app"
    assert row.instance_metadata["usage"] == {"context": {"percent": 40}}
    assert row.home_dir == "/Users/t"


def test_move_back_to_main_drops_the_worktree_key(
    main_checkout_session: tuple[UUID, UUID, UUID],
) -> None:
    """An explicit null `worktree_name` removes the key — the shape
    registration leaves for a main-checkout session — rather than storing
    None for readers to trip over."""
    user_id, instance_id, _ = main_checkout_session
    _patch(
        user_id,
        instance_id,
        {
            "project": "~/vicoa/workspaces/app-worktrees/feat-x/app",
            "worktree_name": "feat-x",
            "repo_root": "~/src/app",
        },
    )
    _patch(
        user_id,
        instance_id,
        {"project": "~/src/app", "worktree_name": None, "repo_root": "~/src/app"},
    )
    row = _row(instance_id)
    assert row.project == "~/src/app"
    assert "worktree_name" not in row.instance_metadata
    assert row.instance_metadata["repo_root"] == "~/src/app"


def test_project_id_is_left_alone_by_a_folder_move(
    main_checkout_session: tuple[UUID, UUID, UUID],
) -> None:
    """Every checkout of a repo belongs to the same project, and a user may
    have re-filed the session by hand — a folder move must not re-resolve
    it. (No project row is needed: the column is simply not touched.)"""
    user_id, instance_id, _ = main_checkout_session
    before = _row(instance_id).project_id
    _patch(
        user_id,
        instance_id,
        {
            "project": "~/vicoa/workspaces/app-worktrees/feat-x/app",
            "worktree_name": "feat-x",
            "repo_root": "~/src/app",
        },
    )
    assert _row(instance_id).project_id == before


def test_absent_project_leaves_the_folder_untouched(
    main_checkout_session: tuple[UUID, UUID, UUID],
) -> None:
    """A rename-only PATCH (the existing callers) must not clear the folder
    just because the new fields default to None."""
    user_id, instance_id, _ = main_checkout_session
    _patch(user_id, instance_id, {"name": "renamed"})
    row = _row(instance_id)
    assert row.name == "renamed"
    assert row.project == "~/src/app"
    assert row.instance_metadata["repo_root"] == "~/src/app"


@pytest.mark.parametrize("project", [None, "", "   "])
def test_empty_project_is_rejected(
    main_checkout_session: tuple[UUID, UUID, UUID], project: str | None
) -> None:
    user_id, instance_id, _ = main_checkout_session
    with pytest.raises(HTTPException) as exc:
        _patch(user_id, instance_id, {"project": project})
    assert exc.value.status_code == 400
    assert _row(instance_id).project == "~/src/app"


def test_worktree_fields_without_project_are_rejected(
    main_checkout_session: tuple[UUID, UUID, UUID],
) -> None:
    """The label and root describe `project`; on their own they would leave
    the folder and its label disagreeing."""
    user_id, instance_id, _ = main_checkout_session
    with pytest.raises(HTTPException) as exc:
        _patch(user_id, instance_id, {"worktree_name": "feat-x"})
    assert exc.value.status_code == 400
    assert "worktree_name" not in _row(instance_id).instance_metadata


def test_another_users_session_is_not_found(
    main_checkout_session: tuple[UUID, UUID, UUID],
) -> None:
    _, instance_id, _ = main_checkout_session
    with pytest.raises(HTTPException) as exc:
        _patch(uuid4(), instance_id, {"project": "~/elsewhere"})
    assert exc.value.status_code == 404
    assert _row(instance_id).project == "~/src/app"
