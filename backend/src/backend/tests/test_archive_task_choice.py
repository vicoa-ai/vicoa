"""Archiving a session that works on a task.

Archive is the COMPLETED status, which the status sync maps to the task's
`done`. That is right when the session finished the work and wrong when the
user is only putting the session away, so the archive can say what should
happen to the task (`task_status`), and the sync itself holds back while
another session on the task is still part of the work.
"""

from uuid import uuid4

import pytest

from shared.database import AgentInstance, Task, User
from shared.database.enums import AgentStatus


@pytest.fixture
def task(test_db, test_user, test_agent_instance):
    """A task the (ACTIVE) test session works on, so the sync put it in progress."""
    task = Task(user_id=test_user.id, project_id=None, title="ship it")
    test_db.add(task)
    test_db.flush()
    test_agent_instance.task_id = task.id
    test_db.commit()
    assert task.status == "in_progress"
    return task


def _sibling(test_db, test_user, test_agent_type, task, status):
    instance = AgentInstance(
        id=uuid4(),
        agent_type_id=test_agent_type.id,
        user_id=test_user.id,
        status=status,
        task_id=task.id,
    )
    test_db.add(instance)
    test_db.commit()
    return instance


def _archive(client, instance, **body):
    return client.put(
        f"/api/v1/agent-instances/{instance.id}/status",
        json={"status": "COMPLETED", **body},
    )


class TestOpenSiblingSessions:
    """A task is not finished while another session on it is still working."""

    @pytest.mark.parametrize(
        "status",
        [
            AgentStatus.ACTIVE,
            AgentStatus.AWAITING_INPUT,
            AgentStatus.STARTING,
            AgentStatus.PAUSED,
        ],
    )
    def test_an_open_sibling_holds_the_task_open(
        self, test_db, test_user, test_agent_type, test_agent_instance, task, status
    ):
        _sibling(test_db, test_user, test_agent_type, task, status)

        test_agent_instance.status = AgentStatus.COMPLETED
        test_db.commit()
        test_db.refresh(task)
        assert task.status == "in_progress"

    @pytest.mark.parametrize(
        "status",
        [
            AgentStatus.COMPLETED,
            AgentStatus.REVIEWED,
            AgentStatus.FAILED,
            AgentStatus.KILLED,
            AgentStatus.DISCONNECTED,
        ],
    )
    def test_a_finished_sibling_does_not(
        self, test_db, test_user, test_agent_type, test_agent_instance, task, status
    ):
        _sibling(test_db, test_user, test_agent_type, task, status)

        test_agent_instance.status = AgentStatus.COMPLETED
        test_db.commit()
        test_db.refresh(task)
        assert task.status == "done"

    def test_the_last_session_to_finish_closes_the_task(
        self, test_db, test_user, test_agent_type, test_agent_instance, task
    ):
        other = _sibling(test_db, test_user, test_agent_type, task, AgentStatus.ACTIVE)

        test_agent_instance.status = AgentStatus.COMPLETED
        test_db.commit()
        test_db.refresh(task)
        assert task.status == "in_progress"

        other.status = AgentStatus.COMPLETED
        test_db.commit()
        test_db.refresh(task)
        assert task.status == "done"


class TestArchiveTaskStatusChoice:
    def test_no_choice_keeps_the_default_mapping(
        self, authenticated_client, test_db, test_agent_instance, task
    ):
        assert _archive(authenticated_client, test_agent_instance).status_code == 200
        test_db.refresh(task)
        assert task.status == "done"

    def test_no_change_leaves_the_task_alone(
        self, authenticated_client, test_db, test_agent_instance, task
    ):
        resp = _archive(
            authenticated_client, test_agent_instance, task_status="no_change"
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "COMPLETED"
        test_db.refresh(task)
        assert task.status == "in_progress"

    @pytest.mark.parametrize("chosen", ["todo", "in_progress", "in_review", "blocked"])
    def test_a_named_status_is_written_to_the_task(
        self, authenticated_client, test_db, test_agent_instance, task, chosen
    ):
        resp = _archive(authenticated_client, test_agent_instance, task_status=chosen)
        assert resp.status_code == 200
        test_db.refresh(task)
        assert task.status == chosen

    def test_done_goes_through_even_with_another_session_open(
        self,
        authenticated_client,
        test_db,
        test_user,
        test_agent_type,
        test_agent_instance,
        task,
    ):
        """The dialog shows "another session is still open" and defaults to
        no change; picking Done anyway is the user's call."""
        _sibling(test_db, test_user, test_agent_type, task, AgentStatus.ACTIVE)

        _archive(authenticated_client, test_agent_instance, task_status="done")
        test_db.refresh(task)
        assert task.status == "done"

    def test_done_overrides_a_status_someone_chose(
        self, authenticated_client, test_db, test_agent_instance, task
    ):
        task.status = "blocked"
        test_db.commit()

        _archive(authenticated_client, test_agent_instance, task_status="done")
        test_db.refresh(task)
        assert task.status == "done"

    def test_a_resumed_session_reopens_the_done_it_set(
        self, authenticated_client, test_db, test_agent_instance, task
    ):
        _archive(authenticated_client, test_agent_instance, task_status="done")
        test_agent_instance.status = AgentStatus.ACTIVE
        test_db.commit()
        test_db.refresh(task)
        assert task.status == "in_progress"

    def test_a_chosen_review_survives_a_resume(
        self, authenticated_client, test_db, test_agent_instance, task
    ):
        """In review was the user's pick, so waking the session does not undo it."""
        _archive(authenticated_client, test_agent_instance, task_status="in_review")
        test_agent_instance.status = AgentStatus.ACTIVE
        test_db.commit()
        test_db.refresh(task)
        assert task.status == "in_review"

    def test_a_chosen_todo_is_picked_up_again_by_a_resume(
        self, authenticated_client, test_db, test_agent_instance, task
    ):
        _archive(authenticated_client, test_agent_instance, task_status="todo")
        test_agent_instance.status = AgentStatus.ACTIVE
        test_db.commit()
        test_db.refresh(task)
        assert task.status == "in_progress"

    def test_a_session_with_no_task_archives_as_before(
        self, authenticated_client, test_agent_instance
    ):
        resp = _archive(authenticated_client, test_agent_instance, task_status="done")
        assert resp.status_code == 200

    @pytest.mark.usefixtures("task")
    def test_unknown_task_status_is_rejected(
        self, authenticated_client, test_agent_instance
    ):
        resp = _archive(
            authenticated_client, test_agent_instance, task_status="shipped"
        )
        assert resp.status_code == 400

    @pytest.mark.usefixtures("task")
    def test_task_status_only_applies_to_an_archive(
        self, authenticated_client, test_agent_instance
    ):
        resp = authenticated_client.put(
            f"/api/v1/agent-instances/{test_agent_instance.id}/status",
            json={"status": "AWAITING_INPUT", "task_status": "done"},
        )
        assert resp.status_code == 400


class TestArchivePreview:
    def _preview(self, client, instance):
        return client.get(f"/api/v1/agent-instances/{instance.id}/archive-preview")

    def test_a_session_with_no_task_has_nothing_to_ask(
        self, authenticated_client, test_agent_instance
    ):
        resp = self._preview(authenticated_client, test_agent_instance)
        assert resp.status_code == 200
        assert resp.json()["task"] is None
        assert resp.json()["ask"] is False

    def test_an_in_progress_task_asks_and_defaults_to_done(
        self, authenticated_client, test_agent_instance, task
    ):
        body = self._preview(authenticated_client, test_agent_instance).json()
        assert body["ask"] is True
        assert body["default"] == "done"
        assert body["other_open_sessions"] == 0
        assert body["task"]["id"] == str(task.id)
        assert body["task"]["title"] == "ship it"
        assert body["task"]["status"] == "in_progress"

    def test_an_open_sibling_still_asks_but_defaults_to_no_change(
        self,
        authenticated_client,
        test_db,
        test_user,
        test_agent_type,
        test_agent_instance,
        task,
    ):
        _sibling(test_db, test_user, test_agent_type, task, AgentStatus.AWAITING_INPUT)

        body = self._preview(authenticated_client, test_agent_instance).json()
        assert body["ask"] is True
        assert body["default"] == "no_change"
        assert body["other_open_sessions"] == 1

    @pytest.mark.parametrize("status", ["done", "cancelled", "blocked", "todo"])
    def test_a_task_the_archive_would_not_touch_has_nothing_to_ask(
        self, authenticated_client, test_db, test_agent_instance, task, status
    ):
        task.status = status
        test_db.commit()

        body = self._preview(authenticated_client, test_agent_instance).json()
        assert body["ask"] is False

    def test_a_task_the_sync_moved_to_review_still_asks(
        self, authenticated_client, test_db, test_agent_instance, task
    ):
        """done then reviewed is the sync's own in_review, which an archive
        would take back to done."""
        test_agent_instance.status = AgentStatus.COMPLETED
        test_db.commit()
        test_agent_instance.status = AgentStatus.REVIEWED
        test_db.commit()
        test_db.refresh(task)
        assert task.status == "in_review"

        body = self._preview(authenticated_client, test_agent_instance).json()
        assert body["ask"] is True

    def test_a_foreign_session_is_404(self, authenticated_client, test_db):
        from shared.database import AgentType

        stranger = User(id=uuid4(), email="stranger@example.com")
        test_db.add(stranger)
        test_db.flush()
        agent_type = AgentType(user_id=stranger.id, name="claude code", is_active=True)
        test_db.add(agent_type)
        test_db.flush()
        theirs = AgentInstance(
            id=uuid4(),
            agent_type_id=agent_type.id,
            user_id=stranger.id,
            status=AgentStatus.ACTIVE,
        )
        test_db.add(theirs)
        test_db.commit()

        resp = self._preview(authenticated_client, theirs)
        assert resp.status_code == 404
