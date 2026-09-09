"""Task timeline API layer — comments, reactions, assignee, serialization.

Companion to `test_task_identity.py`, which covers the DB-level identifier and
activity rules. This file covers what the task-detail route actually calls.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from shared.database import User
from shared.database.agent_profile_models import AgentProfile

from backend.db import task_queries, task_timeline_queries
from backend.db.task_serializers import serialize_task, serialize_tasks

pytestmark = pytest.mark.integration


@pytest.fixture
def agent_profile(test_db, test_user):
    profile = AgentProfile(
        user_id=test_user.id, name="Claude", agent="claude", emoji="🤖"
    )
    test_db.add(profile)
    test_db.commit()
    return profile


@pytest.fixture
def stranger(test_db):
    user = User(
        id=uuid4(),
        email="stranger@example.com",
        display_name="Stranger",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def task(test_db, test_user):
    project = task_queries.create_project(test_db, test_user.id, name="Vicoa")
    return task_queries.create_task(
        test_db, test_user.id, "a task", project_id=project.id
    )


class TestComments:
    def test_create_and_read_back(self, test_db, test_user, task):
        task_timeline_queries.create_comment(test_db, task, test_user.id, "hello")
        timeline = task_timeline_queries.build_timeline(test_db, task, test_user.id)
        assert [c.body for c in timeline.comments] == ["hello"]
        assert timeline.comments[0].author.name == test_user.display_name

    def test_commenting_subscribes_the_author(self, test_db, test_user, task):
        from shared.database import TaskSubscriber

        task_timeline_queries.create_comment(test_db, task, test_user.id, "hello")
        row = (
            test_db.query(TaskSubscriber)
            .filter(TaskSubscriber.task_id == task.id)
            .one()
        )
        assert row.reason == "commenter"

    def test_edit_stamps_edited_at(self, test_db, test_user, task):
        comment = task_timeline_queries.create_comment(
            test_db, task, test_user.id, "typo"
        )
        task_timeline_queries.update_comment(
            test_db, task, comment.id, test_user.id, "fixed"
        )
        timeline = task_timeline_queries.build_timeline(test_db, task, test_user.id)
        assert timeline.comments[0].body == "fixed"
        assert timeline.comments[0].edited_at is not None

    def test_delete_is_soft_and_withholds_the_body(self, test_db, test_user, task):
        """The row survives so the thread keeps its shape and reactions don't
        dangle — but the text stops being served."""
        comment = task_timeline_queries.create_comment(
            test_db, task, test_user.id, "oops"
        )
        task_timeline_queries.delete_comment(test_db, task, comment.id, test_user.id)
        timeline = task_timeline_queries.build_timeline(test_db, task, test_user.id)
        assert len(timeline.comments) == 1
        assert timeline.comments[0].body is None
        assert timeline.comments[0].deleted_at is not None

    def test_only_the_author_can_edit(self, test_db, test_user, stranger, task):
        """Owning the task does not confer the right to rewrite someone else's
        words — the same reason GitHub separates the two."""
        comment = task_timeline_queries.create_comment(
            test_db, task, stranger.id, "not yours"
        )
        with pytest.raises(task_timeline_queries.CommentNotFoundError):
            task_timeline_queries.update_comment(
                test_db, task, comment.id, test_user.id, "rewritten"
            )

    def test_deleted_comment_cannot_be_edited(self, test_db, test_user, task):
        comment = task_timeline_queries.create_comment(
            test_db, task, test_user.id, "gone"
        )
        task_timeline_queries.delete_comment(test_db, task, comment.id, test_user.id)
        with pytest.raises(task_timeline_queries.CommentNotFoundError):
            task_timeline_queries.update_comment(
                test_db, task, comment.id, test_user.id, "back"
            )


class TestReactions:
    def test_toggle_on_then_off(self, test_db, test_user, task):
        comment = task_timeline_queries.create_comment(
            test_db, task, test_user.id, "nice"
        )
        assert (
            task_timeline_queries.toggle_reaction(
                test_db, test_user.id, "comment", comment.id, "👍"
            )
            is True
        )
        timeline = task_timeline_queries.build_timeline(test_db, task, test_user.id)
        assert timeline.comments[0].reactions[0].count == 1
        assert timeline.comments[0].reactions[0].reacted is True

        assert (
            task_timeline_queries.toggle_reaction(
                test_db, test_user.id, "comment", comment.id, "👍"
            )
            is False
        )
        timeline = task_timeline_queries.build_timeline(test_db, task, test_user.id)
        assert timeline.comments[0].reactions == []

    def test_reacted_is_per_viewer(self, test_db, test_user, stranger, task):
        comment = task_timeline_queries.create_comment(
            test_db, task, test_user.id, "nice"
        )
        task_timeline_queries.toggle_reaction(
            test_db, stranger.id, "comment", comment.id, "🎉"
        )
        mine = task_timeline_queries.build_timeline(test_db, task, test_user.id)
        assert mine.comments[0].reactions[0].count == 1
        assert mine.comments[0].reactions[0].reacted is False

    def test_the_task_itself_is_reactable(self, test_db, test_user, task):
        """The task body is a target like any comment — the same way a GitHub
        issue's opening post is."""
        task_timeline_queries.toggle_reaction(
            test_db, test_user.id, "task", task.id, "🚀"
        )
        timeline = task_timeline_queries.build_timeline(test_db, task, test_user.id)
        assert [(r.emoji, r.count) for r in timeline.reactions] == [("🚀", 1)]
        assert timeline.comments == []

    @pytest.mark.parametrize("emoji", ["💩", "👩\u200d💻", "👍🏽", "❤️"])
    def test_any_real_emoji_is_accepted(self, test_db, test_user, task, emoji):
        """Reactions are open — the client offers the full Unicode picker, so a
        server-side allowlist would only be a second, staler list."""
        assert (
            task_timeline_queries.toggle_reaction(
                test_db, test_user.id, "task", task.id, emoji
            )
            is True
        )

    @pytest.mark.parametrize("value", ["hello", "ok", "", "a👍", "   ", "<script>"])
    def test_non_emoji_is_rejected(self, test_db, test_user, task, value):
        """Free varchar + no allowlist still must not become a text-injection
        surface: a reaction pill renders whatever it is handed."""
        with pytest.raises(task_timeline_queries.UnknownReactionError):
            task_timeline_queries.toggle_reaction(
                test_db, test_user.id, "task", task.id, value
            )

    def test_summaries_are_ordered_by_count(self, test_db, test_user, stranger, task):
        comment = task_timeline_queries.create_comment(
            test_db, task, test_user.id, "nice"
        )
        for user_id in (test_user.id, stranger.id):
            task_timeline_queries.toggle_reaction(
                test_db, user_id, "comment", comment.id, "🎉"
            )
        task_timeline_queries.toggle_reaction(
            test_db, test_user.id, "comment", comment.id, "👍"
        )
        timeline = task_timeline_queries.build_timeline(test_db, task, test_user.id)
        assert [r.emoji for r in timeline.comments[0].reactions] == ["🎉", "👍"]


class TestAssignee:
    def test_assign_to_own_agent_profile(self, test_db, test_user, task, agent_profile):
        task_queries.update_task(
            test_db,
            test_user.id,
            task.id,
            {"assignee_type": "agent", "assignee_id": agent_profile.id},
        )
        response = serialize_task(test_db, task)
        assert response.assignee is not None
        assert response.assignee.type == "agent"
        assert response.assignee.name == "Claude"
        assert response.assignee.emoji == "🤖"

    def test_cannot_assign_to_a_foreign_agent_profile(
        self, test_db, test_user, stranger, task
    ):
        theirs = AgentProfile(user_id=stranger.id, name="Theirs", agent="claude")
        test_db.add(theirs)
        test_db.commit()
        with pytest.raises(task_queries.AssigneeNotFoundError):
            task_queries.update_task(
                test_db,
                test_user.id,
                task.id,
                {"assignee_type": "agent", "assignee_id": theirs.id},
            )

    def test_cannot_assign_to_another_user(self, test_db, test_user, stranger, task):
        with pytest.raises(task_queries.AssigneeNotFoundError):
            task_queries.update_task(
                test_db,
                test_user.id,
                task.id,
                {"assignee_type": "user", "assignee_id": stranger.id},
            )

    def test_clearing_the_assignee(self, test_db, test_user, task, agent_profile):
        task_queries.update_task(
            test_db,
            test_user.id,
            task.id,
            {"assignee_type": "agent", "assignee_id": agent_profile.id},
        )
        task_queries.update_task(
            test_db,
            test_user.id,
            task.id,
            {"assignee_type": None, "assignee_id": None},
        )
        assert serialize_task(test_db, task).assignee is None


class TestSerialization:
    def test_identifier_and_parent_title(self, test_db, test_user, task):
        child = task_queries.create_task(
            test_db,
            test_user.id,
            "child",
            project_id=task.project_id,
            parent_task_id=task.id,
        )
        [parent_response, child_response] = serialize_tasks(test_db, [task, child])
        assert parent_response.identifier == "VIC-1"
        assert child_response.identifier == "VIC-2"
        assert child_response.parent_title == "a task"
        assert parent_response.parent_title is None

    def test_identifier_is_none_without_a_key(self, test_db, test_user):
        """A task whose project never got a key renders without an identifier
        rather than with a half-formed one."""
        from shared.database import Project, Task

        project = Project(user_id=test_user.id, name="Keyless")
        test_db.add(project)
        test_db.commit()
        orphan = Task(
            user_id=test_user.id, project_id=project.id, title="no key", number=4
        )
        test_db.add(orphan)
        test_db.commit()
        assert serialize_task(test_db, orphan).identifier is None

    def test_deleted_author_still_renders(self, test_db, test_user, task):
        """A comment outlives its author; a blank name would make the thread
        unreadable."""
        ghost = uuid4()
        from shared.database import TaskComment

        test_db.add(
            TaskComment(
                task_id=task.id,
                project_id=task.project_id,
                author_type="user",
                author_id=ghost,
                body="from beyond",
            )
        )
        test_db.commit()
        timeline = task_timeline_queries.build_timeline(test_db, task, test_user.id)
        assert timeline.comments[0].author.name == "Deleted user"
        assert timeline.comments[0].author.id is None
