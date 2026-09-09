"""Task identifiers and generated activity (collaboration plan §3.5, P2).

Covers the two halves of KEY-42 — `projects.key` and `tasks.number` — and the
`after_flush` listener that turns task mutations into `task_activity` rows.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from shared.database import (
    AgentInstance,
    Project,
    Task,
    TaskActivity,
    TaskComment,
    User,
    get_or_create_inbox,
)
from shared.database.actor import Actor, set_session_actor
from shared.database.enums import AgentStatus
from shared.database.task_identity import (
    derive_key_base,
    format_task_identifier,
    parse_task_identifier,
)

from backend.db import task_queries

pytestmark = pytest.mark.integration


@pytest.fixture
def second_user(test_db):
    user = User(
        id=uuid4(),
        email="second@example.com",
        display_name="Second",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    test_db.add(user)
    test_db.commit()
    return user


def _project(db, user_id, name):
    return task_queries.create_project(db, user_id, name=name)


def _actions(db, task_id):
    rows = (
        db.query(TaskActivity)
        .filter(TaskActivity.task_id == task_id)
        .order_by(TaskActivity.created_at)
        .all()
    )
    return [r.action for r in rows]


class TestKeyDerivation:
    """Pure string rules — no database."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("vicoa", "VIC"),
            ("vicoa-ai", "VIC"),
            ("Inbox", "INB"),
            ("My Cool Project", "MYC"),
            ("go", "GO"),
        ],
    )
    def test_derives_from_ascii(self, name, expected):
        assert derive_key_base(name) == expected

    @pytest.mark.parametrize("name", ["工作台", "🚀", "", "a", "42"])
    def test_falls_back_when_nothing_usable(self, name):
        """A name with fewer than two ASCII alnum characters gets the neutral
        key rather than a mangled one — CJK names are the real case here."""
        assert derive_key_base(name) == "PRJ"

    def test_drops_leading_digits(self):
        """A key starting with a digit would read as part of the number."""
        assert derive_key_base("2024-planning") == "PLA"


class TestIdentifierFormat:
    def test_round_trip(self):
        assert format_task_identifier("VIC", 42) == "VIC-42"
        assert parse_task_identifier("VIC-42") == ("VIC", 42)

    def test_parse_is_case_insensitive(self):
        assert parse_task_identifier("  vic-42 ") == ("VIC", 42)

    def test_none_without_both_halves(self):
        assert format_task_identifier(None, 42) is None
        assert format_task_identifier("VIC", None) is None

    @pytest.mark.parametrize(
        "value",
        [
            "not-an-id",
            str(uuid4()),  # a UUID must never be mistaken for KEY-42
            "VIC-",
            "-42",
            "V-42",  # a one-character key is below the minimum
        ],
    )
    def test_rejects_non_identifiers(self, value):
        assert parse_task_identifier(value) is None


class TestNumberAllocation:
    def test_numbers_start_at_one_per_project(self, test_db, test_user):
        a = _project(test_db, test_user.id, "Alpha")
        b = _project(test_db, test_user.id, "Bravo")

        a1 = task_queries.create_task(test_db, test_user.id, "one", project_id=a.id)
        a2 = task_queries.create_task(test_db, test_user.id, "two", project_id=a.id)
        b1 = task_queries.create_task(test_db, test_user.id, "one", project_id=b.id)

        assert (a1.number, a2.number, b1.number) == (1, 2, 1)

    def test_counter_never_reuses_a_deleted_number(self, test_db, test_user):
        project = _project(test_db, test_user.id, "Alpha")
        first = task_queries.create_task(
            test_db, test_user.id, "one", project_id=project.id
        )
        task_queries.delete_task(test_db, test_user.id, first.id)

        second = task_queries.create_task(
            test_db, test_user.id, "two", project_id=project.id
        )
        assert second.number == 2

    def test_inbox_tasks_get_numbers_too(self, test_db, test_user):
        task = task_queries.create_task(test_db, test_user.id, "unfiled")
        inbox = get_or_create_inbox(test_db, test_user.id)
        assert task.number == 1
        assert inbox.key == "INB"

    def test_rejected_create_does_not_burn_a_number(self, test_db, test_user):
        """Validation runs before allocation, so a 404 leaves no gap."""
        project = _project(test_db, test_user.id, "Alpha")
        with pytest.raises(task_queries.LabelNotFoundError):
            task_queries.create_task(
                test_db,
                test_user.id,
                "bad",
                project_id=project.id,
                label_ids=[uuid4()],
            )
        test_db.rollback()
        ok = task_queries.create_task(
            test_db, test_user.id, "good", project_id=project.id
        )
        assert ok.number == 1


class TestKeyAllocation:
    def test_key_allocated_on_first_task_not_on_create(self, test_db, test_user):
        project = _project(test_db, test_user.id, "Vicoa")
        assert project.key is None

        task_queries.create_task(test_db, test_user.id, "one", project_id=project.id)
        test_db.refresh(project)
        assert project.key == "VIC"

    def test_colliding_names_get_a_suffix(self, test_db, test_user):
        first = _project(test_db, test_user.id, "Vicoa")
        second = _project(test_db, test_user.id, "Vicious")
        task_queries.create_task(test_db, test_user.id, "a", project_id=first.id)
        task_queries.create_task(test_db, test_user.id, "b", project_id=second.id)

        test_db.refresh(first)
        test_db.refresh(second)
        assert first.key == "VIC"
        assert second.key == "VIC2"

    def test_key_namespace_is_per_owner_not_global(
        self, test_db, test_user, second_user
    ):
        mine = _project(test_db, test_user.id, "Vicoa")
        theirs = _project(test_db, second_user.id, "Vicoa")
        task_queries.create_task(test_db, test_user.id, "a", project_id=mine.id)
        task_queries.create_task(test_db, second_user.id, "b", project_id=theirs.id)

        test_db.refresh(mine)
        test_db.refresh(theirs)
        assert mine.key == theirs.key == "VIC"

    def test_rename_does_not_re_derive_the_key(self, test_db, test_user):
        """ "VIC-42" in an old commit message has to keep resolving."""
        project = _project(test_db, test_user.id, "Vicoa")
        task_queries.create_task(test_db, test_user.id, "a", project_id=project.id)
        task_queries.update_project(
            test_db, test_user.id, project.id, {"name": "Renamed"}
        )
        test_db.refresh(project)
        assert project.key == "VIC"


class TestProjectMove:
    def test_move_reassigns_number_and_moves_child_rows(self, test_db, test_user):
        source = _project(test_db, test_user.id, "Alpha")
        target = _project(test_db, test_user.id, "Bravo")
        task_queries.create_task(test_db, test_user.id, "filler", project_id=target.id)
        task = task_queries.create_task(
            test_db, test_user.id, "movable", project_id=source.id
        )
        comment = TaskComment(
            task_id=task.id,
            project_id=source.id,
            author_type="user",
            author_id=test_user.id,
            body="stays with the task",
        )
        test_db.add(comment)
        test_db.commit()

        task_queries.update_task(
            test_db, test_user.id, task.id, {"project_id": target.id}
        )

        test_db.refresh(task)
        test_db.refresh(comment)
        assert task.project_id == target.id
        # Target already held one task, so the mover becomes its #2.
        assert task.number == 2
        # The denormalized project_id follows, or the comment would stay
        # reachable through a grant on a project it no longer belongs to.
        assert comment.project_id == target.id
        assert (
            test_db.query(TaskActivity)
            .filter(TaskActivity.task_id == task.id)
            .first()
            .project_id
            == target.id
        )

    def test_same_project_patch_keeps_the_number(self, test_db, test_user):
        project = _project(test_db, test_user.id, "Alpha")
        task = task_queries.create_task(
            test_db, test_user.id, "stay", project_id=project.id
        )
        task_queries.update_task(
            test_db, test_user.id, task.id, {"project_id": project.id}
        )
        test_db.refresh(task)
        assert task.number == 1


class TestGeneratedActivity:
    def test_create_emits_one_created_row(self, test_db, test_user):
        task = task_queries.create_task(test_db, test_user.id, "new")
        assert _actions(test_db, task.id) == ["created"]

    def test_field_changes_emit_one_row_each(self, test_db, test_user):
        task = task_queries.create_task(test_db, test_user.id, "new")
        task_queries.update_task(
            test_db,
            test_user.id,
            task.id,
            {"status": "in_progress", "priority": "high"},
        )
        assert set(_actions(test_db, task.id)) == {
            "created",
            "status_changed",
            "priority_changed",
        }

    def test_no_row_when_nothing_actually_changed(self, test_db, test_user):
        task = task_queries.create_task(test_db, test_user.id, "new")
        task_queries.update_task(test_db, test_user.id, task.id, {"status": "backlog"})
        assert _actions(test_db, task.id) == ["created"]

    def test_status_change_records_from_and_to(self, test_db, test_user):
        task = task_queries.create_task(test_db, test_user.id, "new")
        task_queries.update_task(
            test_db, test_user.id, task.id, {"status": "in_progress"}
        )
        row = (
            test_db.query(TaskActivity)
            .filter(
                TaskActivity.task_id == task.id,
                TaskActivity.action == "status_changed",
            )
            .one()
        )
        assert row.details == {"from": "backlog", "to": "in_progress"}

    def test_long_text_is_recorded_without_a_diff(self, test_db, test_user):
        """A before/after pair of two long descriptions is unrenderable and
        would dwarf the table — record that it changed, not what to."""
        task = task_queries.create_task(test_db, test_user.id, "new")
        task_queries.update_task(
            test_db, test_user.id, task.id, {"description": "x" * 4000}
        )
        row = (
            test_db.query(TaskActivity)
            .filter(TaskActivity.action == "description_changed")
            .one()
        )
        assert row.details == {}

    def test_labels_emit_added_and_removed(self, test_db, test_user):
        label = task_queries.create_label(test_db, test_user.id, "backend", "#ff0000")
        task = task_queries.create_task(test_db, test_user.id, "new")
        task_queries.update_task(
            test_db, test_user.id, task.id, {"label_ids": [label.id]}
        )
        task_queries.update_task(test_db, test_user.id, task.id, {"label_ids": []})
        actions = _actions(test_db, task.id)
        assert "label_added" in actions and "label_removed" in actions

    def test_actor_comes_from_the_session(self, test_db, test_user):
        set_session_actor(test_db, Actor(type="user", id=test_user.id))
        try:
            task = task_queries.create_task(test_db, test_user.id, "new")
        finally:
            set_session_actor(test_db, None)
        row = test_db.query(TaskActivity).filter(TaskActivity.task_id == task.id).one()
        assert (row.actor_type, row.actor_id) == ("user", test_user.id)

    def test_unattributed_when_no_actor_is_set(self, test_db, test_user):
        """A background sweep has no request context. An unattributed row is
        honest; a guessed one is not."""
        task = task_queries.create_task(test_db, test_user.id, "new")
        row = test_db.query(TaskActivity).filter(TaskActivity.task_id == task.id).one()
        assert row.actor_type is None and row.actor_id is None


class TestStatusSyncAttribution:
    def test_session_driven_status_is_attributed_to_the_session(
        self, test_db, test_user, test_agent_type
    ):
        """The daemon posts the status update authenticated as the user, but the
        thing that moved the task is the agent's session — and the timeline
        needs the instance id to fold these hops into that session's card."""
        set_session_actor(test_db, Actor(type="user", id=test_user.id))
        try:
            task = task_queries.create_task(test_db, test_user.id, "linked")
            instance = AgentInstance(
                id=uuid4(),
                agent_type_id=test_agent_type.id,
                user_id=test_user.id,
                status=AgentStatus.ACTIVE,
                task_id=task.id,
            )
            test_db.add(instance)
            test_db.commit()
        finally:
            set_session_actor(test_db, None)

        row = (
            test_db.query(TaskActivity)
            .filter(TaskActivity.action == "status_changed")
            .one()
        )
        # No agent_profile_id on this instance, so it degrades to 'system'
        # rather than inheriting the request's user.
        assert row.actor_type == "system"
        assert row.details["agent_instance_id"] == str(instance.id)

    def test_override_does_not_leak_to_a_later_change(
        self, test_db, test_user, test_agent_type
    ):
        set_session_actor(test_db, Actor(type="user", id=test_user.id))
        try:
            task = task_queries.create_task(test_db, test_user.id, "linked")
            instance = AgentInstance(
                id=uuid4(),
                agent_type_id=test_agent_type.id,
                user_id=test_user.id,
                status=AgentStatus.ACTIVE,
                task_id=task.id,
            )
            test_db.add(instance)
            test_db.commit()

            task_queries.update_task(
                test_db, test_user.id, task.id, {"priority": "urgent"}
            )
        finally:
            set_session_actor(test_db, None)

        row = (
            test_db.query(TaskActivity)
            .filter(TaskActivity.action == "priority_changed")
            .one()
        )
        assert row.actor_type == "user"
        assert "agent_instance_id" not in row.details


class TestProjectKeyUniquenessIndex:
    def test_two_projects_cannot_hold_the_same_key(self, test_db, test_user):
        from sqlalchemy.exc import IntegrityError

        a = Project(user_id=test_user.id, name="Alpha", key="DUP")
        b = Project(user_id=test_user.id, name="Bravo", key="dup")
        test_db.add_all([a, b])
        with pytest.raises(IntegrityError):
            test_db.commit()
        test_db.rollback()

    def test_two_tasks_cannot_hold_the_same_number(self, test_db, test_user):
        from sqlalchemy.exc import IntegrityError

        project = _project(test_db, test_user.id, "Alpha")
        test_db.add_all(
            [
                Task(user_id=test_user.id, project_id=project.id, title="a", number=7),
                Task(user_id=test_user.id, project_id=project.id, title="b", number=7),
            ]
        )
        with pytest.raises(IntegrityError):
            test_db.commit()
        test_db.rollback()
