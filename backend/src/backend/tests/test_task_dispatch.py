"""Assigning a task, and commenting on it, queues work for agents.

plans/todos/task-assignment-agents.md. These cover the rules that decide
*whether* an agent is asked to act and in which mode — the task query layer
every surface goes through — and what a task then shows. Delivery is the
dispatcher's (servers/tests/test_task_dispatcher.py).
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from shared.database import TaskDispatch, User
from shared.database.actor import Actor, set_session_actor
from shared.database.agent_profile_models import AgentProfile
from shared.database.collab_models import Team
from shared.database.models import Machine
from shared.database.task_models import ProjectDirectory
from shared import task_dispatch
from backend.db import share_queries, task_queries, task_timeline_queries
from backend.db.task_serializers import serialize_task

pytestmark = pytest.mark.integration


def _as_person(db, user) -> None:
    set_session_actor(db, Actor(type="user", id=user.id))


def _as_agent(db, profile) -> None:
    set_session_actor(db, Actor(type="agent", id=profile.id, agent_instance_id=uuid4()))


@pytest.fixture
def profile(test_db, test_user):
    row = AgentProfile(user_id=test_user.id, name="Claude", agent="claude")
    test_db.add(row)
    test_db.commit()
    return row


@pytest.fixture
def other_profile(test_db, test_user):
    row = AgentProfile(user_id=test_user.id, name="Codex", agent="codex")
    test_db.add(row)
    test_db.commit()
    return row


@pytest.fixture
def project(test_db, test_user):
    return task_queries.create_project(test_db, test_user.id, name="Vicoa")


@pytest.fixture
def task(test_db, test_user, project):
    return task_queries.create_task(
        test_db, test_user.id, "Fix the queue", project_id=project.id, status="todo"
    )


def _assign(db, user, task, profile, **options):
    run = task_dispatch.RunOptions(**options) if options else None
    return task_queries.update_task(
        db,
        user.id,
        task.id,
        {"assignee_type": "agent", "assignee_id": profile.id},
        run_options=run,
    )


def _dispatches(db, task):
    return (
        db.query(TaskDispatch)
        .filter(TaskDispatch.task_id == task.id)
        .order_by(TaskDispatch.created_at)
        .all()
    )


def _queued(db, task):
    return [d for d in _dispatches(db, task) if d.state == "queued"]


class TestAssignment:
    def test_a_person_assigning_an_agent_queues_ownership(
        self, test_db, test_user, task, profile
    ):
        _as_person(test_db, test_user)
        _assign(test_db, test_user, task, profile)
        [row] = _queued(test_db, task)
        assert (row.mode, row.trigger) == ("ownership", "assigned")
        assert row.agent_profile_id == profile.id
        assert row.user_id == test_user.id
        assert row.requested_by_user_id == test_user.id
        assert row.worktree == {"mode": "new"}

    def test_assign_only_starts_nothing(self, test_db, test_user, task, profile):
        _as_person(test_db, test_user)
        _assign(test_db, test_user, task, profile, start=False)
        assert _dispatches(test_db, task) == []
        assert task.assignee_id == profile.id

    def test_the_dialog_choices_ride_along(self, test_db, test_user, task, profile):
        _as_person(test_db, test_user)
        machine = Machine(id=uuid4(), user_id=test_user.id, display_name="laptop")
        test_db.add(machine)
        test_db.commit()
        _assign(
            test_db,
            test_user,
            task,
            profile,
            machine_id=machine.id,
            directory="/src/vicoa",
            worktree="none",
        )
        [row] = _queued(test_db, task)
        assert row.machine_id == machine.id
        assert row.directory == "/src/vicoa"
        assert row.worktree == {"mode": "none"}

    def test_an_agent_assigning_an_agent_starts_nothing(
        self, test_db, test_user, task, profile, other_profile
    ):
        # The loop guard: everything a dispatched session does is signed as
        # its profile, and a profile's action never dispatches.
        _as_agent(test_db, other_profile)
        _assign(test_db, test_user, task, profile)
        assert _dispatches(test_db, task) == []

    def test_backlog_waits_until_it_moves(self, test_db, test_user, project, profile):
        _as_person(test_db, test_user)
        task = task_queries.create_task(
            test_db, test_user.id, "later", project_id=project.id
        )
        _assign(test_db, test_user, task, profile)
        assert _dispatches(test_db, task) == []
        task_queries.update_task(test_db, test_user.id, task.id, {"status": "todo"})
        [row] = _queued(test_db, task)
        assert (row.mode, row.trigger) == ("ownership", "unblocked")

    def test_create_with_an_agent_assignee_queues(
        self, test_db, test_user, project, profile
    ):
        _as_person(test_db, test_user)
        task = task_queries.create_task(
            test_db,
            test_user.id,
            "new",
            project_id=project.id,
            status="todo",
            assignee_type="agent",
            assignee_id=profile.id,
        )
        [row] = _queued(test_db, task)
        assert row.trigger == "assigned"

    def test_a_team_agent_says_why_it_cannot_start(self, test_db, test_user, task):
        team = Team(id=uuid4(), name="Crew", slug=f"crew-{uuid4().hex[:8]}")
        test_db.add(team)
        test_db.flush()
        team_profile = AgentProfile(
            user_id=test_user.id, team_id=team.id, name="Shared", agent="claude"
        )
        test_db.add(team_profile)
        test_db.commit()
        _as_person(test_db, test_user)
        task.assignee_type, task.assignee_id = "agent", team_profile.id
        task_dispatch.on_assignee_changed(test_db, task, old_type=None, old_id=None)
        test_db.commit()
        [row] = _dispatches(test_db, task)
        assert row.state == "failed"
        assert row.detail == "team agents can't start runs yet"

    def test_an_archived_agent_says_why(self, test_db, test_user, task, profile):
        profile.is_archived = True
        test_db.commit()
        _as_person(test_db, test_user)
        task.assignee_type, task.assignee_id = "agent", profile.id
        task_dispatch.on_assignee_changed(test_db, task, old_type=None, old_id=None)
        test_db.commit()
        [row] = _dispatches(test_db, task)
        assert (row.state, row.detail) == ("failed", "this agent is archived")

    def test_unassigning_cancels_what_was_waiting(
        self, test_db, test_user, task, profile
    ):
        _as_person(test_db, test_user)
        _assign(test_db, test_user, task, profile)
        task_queries.update_task(
            test_db,
            test_user.id,
            task.id,
            {"assignee_type": "user", "assignee_id": test_user.id},
        )
        [row] = _dispatches(test_db, task)
        assert (row.state, row.detail) == ("cancelled", "unassigned")

    def test_unassigning_keeps_a_comment_waiting_for_its_answer(
        self, test_db, test_user, task, profile
    ):
        _as_person(test_db, test_user)
        _assign(test_db, test_user, task, profile)
        task_timeline_queries.create_comment(test_db, task, test_user.id, "and X?")
        # The agent hands the task to the person before it got to the comment.
        _as_agent(test_db, profile)
        task_queries.update_task(
            test_db,
            test_user.id,
            task.id,
            {"assignee_type": "user", "assignee_id": test_user.id},
        )
        [row] = _queued(test_db, task)
        assert (row.mode, row.trigger) == ("reply", "commented")

    def test_closing_the_task_cancels_what_was_waiting(
        self, test_db, test_user, task, profile
    ):
        _as_person(test_db, test_user)
        _assign(test_db, test_user, task, profile)
        task_queries.update_task(test_db, test_user.id, task.id, {"status": "done"})
        [row] = _dispatches(test_db, task)
        assert (row.state, row.detail) == ("cancelled", "task done")


class TestComments:
    def _comment(self, db, user, task, body, parent=None):
        return task_timeline_queries.create_comment(
            db, task, user.id, body, parent_comment_id=parent
        )

    def _agent_comment(self, db, user, task, profile, body, parent=None):
        return task_timeline_queries.create_comment(
            db,
            task,
            user.id,
            body,
            parent_comment_id=parent,
            author=("agent", profile.id),
            agent_instance_id=None,
        )

    def test_top_level_on_an_agent_task_goes_to_the_assignee(
        self, test_db, test_user, task, profile
    ):
        _as_person(test_db, test_user)
        _assign(test_db, test_user, task, profile, start=False)
        comment = self._comment(test_db, test_user, task, "also check mobile")
        [row] = _queued(test_db, task)
        assert (row.mode, row.trigger) == ("reply", "commented")
        assert row.trigger_comment_id == comment.id

    def test_a_reply_goes_to_the_agent_in_that_thread(
        self, test_db, test_user, task, profile
    ):
        # The task is the person's: the agent asked and handed it over.
        question = self._agent_comment(
            test_db, test_user, task, profile, "A or B? I recommend A."
        )
        task_queries.update_task(
            test_db,
            test_user.id,
            task.id,
            {"assignee_type": "user", "assignee_id": test_user.id},
        )
        _as_person(test_db, test_user)
        self._comment(test_db, test_user, task, "A", parent=question.id)
        [row] = _queued(test_db, task)
        assert (row.agent_profile_id, row.trigger) == (profile.id, "replied")

    def test_a_reply_between_people_wakes_nobody(
        self, test_db, test_user, task, profile
    ):
        _as_person(test_db, test_user)
        _assign(test_db, test_user, task, profile, start=False)
        root = self._comment(test_db, test_user, task, "note to self")
        test_db.query(TaskDispatch).delete()
        test_db.commit()
        self._comment(test_db, test_user, task, "and another", parent=root.id)
        assert _dispatches(test_db, task) == []

    def test_a_mention_goes_to_that_agent_only(
        self, test_db, test_user, task, profile, other_profile
    ):
        _as_person(test_db, test_user)
        _assign(test_db, test_user, task, profile, start=False)
        self._comment(
            test_db,
            test_user,
            task,
            f"[@Codex](vicoa://agent/{other_profile.id}) can you review?",
        )
        [row] = _queued(test_db, task)
        assert (row.agent_profile_id, row.trigger) == (other_profile.id, "mentioned")

    def test_a_note_wakes_nobody(self, test_db, test_user, task, profile):
        _as_person(test_db, test_user)
        _assign(test_db, test_user, task, profile, start=False)
        self._comment(test_db, test_user, task, "/note just thinking out loud")
        assert _dispatches(test_db, task) == []

    def test_an_agent_comment_wakes_nobody(self, test_db, test_user, task, profile):
        _as_person(test_db, test_user)
        _assign(test_db, test_user, task, profile, start=False)
        self._agent_comment(test_db, test_user, task, profile, "done, see PR")
        assert _dispatches(test_db, task) == []

    def test_a_comment_merges_into_a_waiting_assignment(
        self, test_db, test_user, task, profile
    ):
        _as_person(test_db, test_user)
        _assign(test_db, test_user, task, profile)
        comment = self._comment(test_db, test_user, task, "one more thing")
        [row] = _queued(test_db, task)
        # Ownership is the bigger ask and wins; the comment is still noted.
        assert row.mode == "ownership"
        assert row.trigger_comment_id == comment.id

    def test_someone_elses_agent_is_not_started(self, test_db, test_user, task):
        stranger = User(
            id=uuid4(),
            email="s@example.com",
            display_name="S",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(stranger)
        test_db.flush()
        theirs = AgentProfile(user_id=stranger.id, name="Theirs", agent="claude")
        test_db.add(theirs)
        test_db.commit()
        _as_person(test_db, test_user)
        self._comment(
            test_db, test_user, task, f"[@Theirs](vicoa://agent/{theirs.id}) hi"
        )
        assert _dispatches(test_db, task) == []


class TestWhatTheTaskShows:
    def test_assigned_by_and_when(self, test_db, test_user, task, profile):
        _as_agent(test_db, profile)
        task_queries.update_task(
            test_db,
            test_user.id,
            task.id,
            {"assignee_type": "user", "assignee_id": test_user.id},
        )
        response = serialize_task(test_db, task)
        assert response.assigned_at is not None
        assert response.assigned_by is not None
        assert (response.assigned_by.type, response.assigned_by.id) == (
            "agent",
            profile.id,
        )

    def test_the_assigners_question(self, test_db, test_user, task, profile):
        question = task_timeline_queries.create_comment(
            test_db,
            task,
            test_user.id,
            "Option **A** or `B`? I recommend [A](https://example.com/a).",
            author=("agent", profile.id),
        )
        _as_agent(test_db, profile)
        task_queries.update_task(
            test_db,
            test_user.id,
            task.id,
            {"assignee_type": "user", "assignee_id": test_user.id},
        )
        response = serialize_task(test_db, task)
        # Plain text for a list row: no markdown markers, links keep their text.
        assert response.assigner_comment == "Option A or B? I recommend A."
        assert response.assigner_comment_id == question.id

    def test_the_latest_dispatch(self, test_db, test_user, task, profile):
        _as_person(test_db, test_user)
        _assign(test_db, test_user, task, profile)
        response = serialize_task(test_db, task)
        assert response.dispatch is not None
        assert (response.dispatch.state, response.dispatch.mode) == (
            "queued",
            "ownership",
        )

    def test_a_shared_board_shows_neither(self, test_db, test_user, task, profile):
        _as_person(test_db, test_user)
        _assign(test_db, test_user, task, profile)

        class _Grant:
            link = None

        rows = share_queries.public_tasks(test_db, _Grant(), [task])  # type: ignore[arg-type]
        assert rows[0].dispatch is None
        assert rows[0].assigned_by is None

    def test_list_by_assignee(self, test_db, test_user, project, profile):
        mine = task_queries.create_task(
            test_db,
            test_user.id,
            "mine",
            project_id=project.id,
            assignee_type="user",
            assignee_id=test_user.id,
        )
        task_queries.create_task(
            test_db,
            test_user.id,
            "agent's",
            project_id=project.id,
            assignee_type="agent",
            assignee_id=profile.id,
        )
        nobody = task_queries.create_task(
            test_db, test_user.id, "nobody's", project_id=project.id
        )
        assert [
            t.id
            for t in task_queries.list_tasks(
                test_db, test_user.id, assignee_id=test_user.id
            )
        ] == [mine.id]
        assert [
            t.id
            for t in task_queries.list_tasks(test_db, test_user.id, unassigned=True)
        ] == [nobody.id]


class TestPush:
    @pytest.fixture
    def pushes(self, monkeypatch):
        sent: list[dict] = []
        from servers.shared import task_notifications

        monkeypatch.setattr(
            task_notifications,
            "notify_task_assigned_after_commit",
            lambda db, task, assignee_user_id: sent.append(
                {"task": task.id, "to": assignee_user_id}
            ),
        )
        return sent

    def test_an_agent_handing_you_a_task_pushes(
        self, test_db, test_user, task, profile, pushes
    ):
        _as_agent(test_db, profile)
        task_queries.update_task(
            test_db,
            test_user.id,
            task.id,
            {"assignee_type": "user", "assignee_id": test_user.id},
        )
        assert pushes == [{"task": task.id, "to": test_user.id}]

    def test_assigning_yourself_does_not(self, test_db, test_user, task, pushes):
        _as_person(test_db, test_user)
        task_queries.update_task(
            test_db,
            test_user.id,
            task.id,
            {"assignee_type": "user", "assignee_id": test_user.id},
        )
        assert pushes == []


class TestPlacement:
    def test_project_folder_on_the_default_machine(
        self, test_db, test_user, task, profile, project
    ):
        machine = Machine(id=uuid4(), user_id=test_user.id, display_name="laptop")
        test_db.add(machine)
        test_db.flush()
        test_db.add(
            ProjectDirectory(
                user_id=test_user.id,
                project_id=project.id,
                machine_id=machine.id,
                local_path="/src/vicoa",
            )
        )
        profile.default_machine_id = machine.id
        test_db.commit()
        placement = task_dispatch.resolve_placement(test_db, profile, task)
        assert (placement.machine_id, placement.directory) == (machine.id, "/src/vicoa")
        assert placement.reason is None

    def test_found_through_the_project_folder(
        self, test_db, test_user, task, profile, project
    ):
        machine = Machine(id=uuid4(), user_id=test_user.id, display_name="desk")
        test_db.add(machine)
        test_db.flush()
        test_db.add(
            ProjectDirectory(
                user_id=test_user.id,
                project_id=project.id,
                machine_id=machine.id,
                local_path="/work/vicoa",
            )
        )
        test_db.commit()
        placement = task_dispatch.resolve_placement(test_db, profile, task)
        assert placement.directory == "/work/vicoa"

    def test_nowhere_to_run_says_so(self, test_db, test_user, task, profile):
        placement = task_dispatch.resolve_placement(test_db, profile, task)
        assert placement.machine_id is None
        assert placement.reason is not None


class TestMentions:
    def test_only_picker_links_count(self):
        a, b = uuid4(), uuid4()
        body = f"[@A](vicoa://agent/{a}) and @B and [@A](vicoa://agent/{a}) [@B](vicoa://agent/{b})"
        assert task_dispatch.mentioned_profile_ids(body) == [a, b]

    def test_note_prefix(self):
        assert task_dispatch.is_note("  /note hi")
        assert task_dispatch.is_note("/NOTE")
        assert not task_dispatch.is_note("a /note later")
        assert task_dispatch.is_note("/note: for later")
        assert not task_dispatch.is_note("/notebook is open")
