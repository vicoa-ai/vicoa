"""An agent asks one person on a task; the task waits on them until it closes.

plans/todos/task-questions-waiting-on.md. A question is a comment plus a `reply`
wakeup (`task_wakeups`). Covers who it asks (the agent API's `ask`), each way
the wakeup fires or ends, the answer waking the agent that asked, the pushes,
and what a task and a timeline show.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared import task_dispatch
from shared.database import TaskDispatch, User
from shared.database.actor import Actor, set_session_actor
from shared.database.agent_profile_models import AgentProfile
from shared.database.collab_models import ProjectGrant
from shared.database.models import AgentInstance
from shared.database.session import get_db
from shared.database.task_models import TaskComment
from shared.database.task_wakeup_models import TaskWakeup
from shared import task_wakeups
from backend.db import share_queries, task_queries, task_timeline_queries
from backend.db.task_serializers import serialize_task
from servers.api.auth import get_current_user_id
from servers.api.tasks import task_router

pytestmark = pytest.mark.integration


def _user(db, email: str, name: str) -> User:
    user = User(
        id=uuid4(),
        email=email,
        display_name=name,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    return user


def _as_person(db, user) -> None:
    set_session_actor(db, Actor(type="user", id=user.id))


@pytest.fixture
def profile(test_db, test_user):
    row = AgentProfile(user_id=test_user.id, name="Claude", agent="claude")
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


@pytest.fixture
def ada(test_db, project):
    """A teammate who can see the board."""
    user = _user(test_db, "ada@example.com", "Ada")
    test_db.add(
        ProjectGrant(
            project_id=project.id,
            principal_type="user",
            principal_id=user.id,
            role="editor",
            scopes=["tasks", "sessions"],
        )
    )
    test_db.commit()
    return user


@pytest.fixture
def stranger(test_db):
    return _user(test_db, "stranger@example.com", "Stranger")


@pytest.fixture
def session(test_db, test_user, test_agent_type, profile, task):
    """The agent's task session, as `vicoa task comment` names it."""
    instance = AgentInstance(
        user_id=test_user.id,
        agent_type_id=test_agent_type.id,
        agent_profile_id=profile.id,
        task_id=task.id,
    )
    test_db.add(instance)
    test_db.commit()
    return instance


@pytest.fixture
def client(test_db, test_user):
    app = FastAPI()
    app.include_router(task_router, prefix="/api/v1")

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = lambda: str(test_user.id)
    return TestClient(app)


@pytest.fixture
def pushes(monkeypatch):
    sent: list[tuple[str, UUID]] = []
    from servers.shared import task_notifications

    monkeypatch.setattr(
        task_notifications,
        "notify_task_question_after_commit",
        lambda db, task, *, addressee_id, **_: sent.append(("question", addressee_id)),
    )
    monkeypatch.setattr(
        task_notifications,
        "notify_task_mentioned_after_commit",
        lambda db, task, *, user_ids, **_: sent.extend(
            ("mention", uid) for uid in user_ids
        ),
    )
    return sent


def _ask(client, task, session, body="A or B?", **ask):
    return client.post(
        f"/api/v1/tasks/{task.id}/comments",
        json={"body": body, "agent_instance_id": str(session.id), "ask": ask},
    )


def _question(db, task) -> TaskWakeup | None:
    """The task's newest reply wakeup: the latest question asked on it."""
    return (
        db.query(TaskWakeup)
        .filter(TaskWakeup.task_id == task.id, TaskWakeup.kind == "reply")
        .order_by(TaskWakeup.created_at.desc())
        .first()
    )


def _asked(db, task) -> UUID | None:
    """Whom the task's latest question asks."""
    wakeup = _question(db, task)
    assert wakeup is not None
    return wakeup.wait_for_user_id


def _ask_directly(db, user, task, profile, person) -> TaskWakeup:
    """A question as the agent API would store it; returns its wakeup."""
    set_session_actor(db, Actor(type="agent", id=profile.id))
    comment = task_timeline_queries.create_comment(
        db,
        task,
        user.id,
        "Which way?",
        author=("agent", profile.id),
        ask_user_id=person.id,
    )
    return db.query(TaskWakeup).filter(TaskWakeup.source_comment_id == comment.id).one()


def _queued(db, task):
    return (
        db.query(TaskDispatch)
        .filter(TaskDispatch.task_id == task.id, TaskDispatch.state == "queued")
        .all()
    )


class TestWhoIsAsked:
    def test_by_default_the_person_who_started_the_run(
        self, test_db, test_user, task, profile, session, ada, client, pushes
    ):
        test_db.add(
            TaskDispatch(
                user_id=test_user.id,
                task_id=task.id,
                agent_profile_id=profile.id,
                mode="reply",
                trigger="mentioned",
                requested_by_user_id=ada.id,
                agent_instance_id=session.id,
                state="delivered",
                next_attempt_at=datetime.now(timezone.utc),
            )
        )
        test_db.commit()
        resp = _ask(client, task, session)
        assert resp.status_code == 201, resp.text
        assert _asked(test_db, task) == ada.id
        assert pushes == [("question", ada.id)]

    def test_else_the_sessions_owner(
        self, test_db, test_user, task, session, client, pushes
    ):
        assert _ask(client, task, session).status_code == 201
        assert _asked(test_db, task) == test_user.id
        assert pushes == [("question", test_user.id)]

    @pytest.mark.parametrize("to", ["ada@example.com", "ADA", "id"])
    def test_to_by_email_name_or_id(self, test_db, task, session, ada, client, to):
        resp = _ask(client, task, session, to=str(ada.id) if to == "id" else to)
        assert resp.status_code == 201, resp.text
        assert _asked(test_db, task) == ada.id

    def test_to_me_is_the_keys_user(self, test_db, test_user, task, session, client):
        assert _ask(client, task, session, to="me").status_code == 201
        assert _asked(test_db, task) == test_user.id

    def test_someone_who_cant_see_the_task_is_refused(
        self, test_db, task, session, ada, stranger, client
    ):
        resp = _ask(client, task, session, to=stranger.email)
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "Ada" in detail and str(ada.id) in detail
        # Who can be asked, by name and id; never by address.
        assert "@" not in detail.split("one of:")[1]
        assert _question(test_db, task) is None

    def test_only_an_agent_asks(self, test_db, task, client):
        resp = client.post(
            f"/api/v1/tasks/{task.id}/comments", json={"body": "?", "ask": {}}
        )
        assert resp.status_code == 400
        assert _question(test_db, task) is None

    def test_a_question_shows_on_the_task_and_its_comment(
        self, test_db, task, session, ada, client
    ):
        timeline = _ask(client, task, session, to="Ada").json()
        [comment] = timeline["comments"]
        assert comment["question"]["addressee"]["name"] == "Ada"
        assert comment["question"]["closed_at"] is None
        assert {p["name"] for p in timeline["people"]} == {"Test User", "Ada"}

        shown = client.get(f"/api/v1/tasks/{task.id}").json()
        [question] = shown["open_questions"]
        assert question["addressee"]["id"] == str(ada.id)
        assert question["asked_by"]["name"] == "Claude"
        assert question["comment_id"] == comment["id"]

    def test_task_ls_waiting_on(self, test_db, test_user, task, session, ada, client):
        other = task_queries.create_task(test_db, test_user.id, "Other")
        _ask(client, task, session, to="Ada")
        for value in ("ada@example.com", "Ada", str(ada.id)):
            listed = client.get("/api/v1/tasks", params={"waiting_on": value}).json()
            assert [t["id"] for t in listed] == [str(task.id)], value
        assert client.get("/api/v1/tasks", params={"waiting_on": "me"}).json() == []
        assert (
            client.get("/api/v1/tasks", params={"waiting_on": "nobody@x.io"}).json()
            == []
        )
        assert other.id  # present, just not waiting on anyone


class TestClosing:
    def _open(self, db, task):
        return (
            db.query(TaskWakeup)
            .filter(TaskWakeup.task_id == task.id, TaskWakeup.state == "waiting")
            .all()
        )

    def test_the_addressees_top_level_comment_answers_it(
        self, test_db, test_user, task, profile, ada
    ):
        wakeup = _ask_directly(test_db, test_user, task, profile, ada)
        _as_person(test_db, ada)
        answer = task_timeline_queries.create_comment(
            test_db, task, ada.id, "B, top level"
        )
        test_db.refresh(wakeup)
        assert (wakeup.state, wakeup.ended_reason) == ("fired", None)
        assert wakeup.fired_by_comment_id == answer.id
        # It records the run it started.
        [dispatch] = _queued(test_db, task)
        assert wakeup.dispatch_id == dispatch.id
        assert wakeup.ended_at is not None

    def test_a_reply_in_its_thread_answers_it(self, test_db, test_user, task, profile):
        wakeup = _ask_directly(test_db, test_user, task, profile, test_user)
        _as_person(test_db, test_user)
        task_timeline_queries.create_comment(
            test_db,
            task,
            test_user.id,
            "B",
            parent_comment_id=wakeup.source_comment_id,
        )
        test_db.refresh(wakeup)
        assert wakeup.state == "fired"
        [row] = _queued(test_db, task)
        assert (row.agent_profile_id, row.trigger) == (profile.id, "answered")

    def test_mentioning_the_asker_answers_it(self, test_db, test_user, task, profile):
        wakeup = _ask_directly(test_db, test_user, task, profile, test_user)
        _as_person(test_db, test_user)
        task_timeline_queries.create_comment(
            test_db, task, test_user.id, f"[@Claude](vicoa://agent/{profile.id}) B"
        )
        test_db.refresh(wakeup)
        assert wakeup.state == "fired"
        [row] = _queued(test_db, task)
        assert row.trigger == "answered"

    def test_a_reply_in_another_agents_thread_does_not(
        self, test_db, test_user, task, profile
    ):
        other = AgentProfile(user_id=test_user.id, name="Codex", agent="codex")
        test_db.add(other)
        test_db.commit()
        set_session_actor(test_db, Actor(type="agent", id=other.id))
        theirs = task_timeline_queries.create_comment(
            test_db, task, test_user.id, "Done?", author=("agent", other.id)
        )
        _ask_directly(test_db, test_user, task, profile, test_user)
        _as_person(test_db, test_user)
        task_timeline_queries.create_comment(
            test_db, task, test_user.id, "Yes", parent_comment_id=theirs.id
        )
        # It went to that thread's agent; the one that asked hasn't heard yet.
        [row] = _queued(test_db, task)
        assert (row.agent_profile_id, row.trigger) == (other.id, "replied")
        assert len(self._open(test_db, task)) == 1

    def test_someone_elses_comment_does_not(
        self, test_db, test_user, task, profile, ada
    ):
        _ask_directly(test_db, test_user, task, profile, ada)
        _as_person(test_db, test_user)
        task_timeline_queries.create_comment(test_db, task, test_user.id, "hm")
        assert len(self._open(test_db, task)) == 1

    def test_a_note_does_not(self, test_db, test_user, task, profile, ada):
        _ask_directly(test_db, test_user, task, profile, ada)
        _as_person(test_db, ada)
        task_timeline_queries.create_comment(test_db, task, ada.id, "/note later")
        assert len(self._open(test_db, task)) == 1

    @pytest.mark.parametrize(
        ("before", "after", "reason"),
        [
            ("blocked", "in_progress", "unblocked"),
            ("in_progress", "in_review", "delivered"),
            ("blocked", "in_review", "delivered"),
            ("blocked", "done", "task_closed"),
            ("in_progress", "cancelled", "task_closed"),
        ],
    )
    def test_status(
        self, test_db, test_user, task, profile, ada, before, after, reason
    ):
        task_queries.update_task(test_db, test_user.id, task.id, {"status": before})
        wakeup = _ask_directly(test_db, test_user, task, profile, ada)
        _as_person(test_db, test_user)
        task_queries.update_task(test_db, test_user.id, task.id, {"status": after})
        test_db.refresh(wakeup)
        assert (wakeup.state, wakeup.ended_reason) == ("ended", reason)

    def test_becoming_blocked_keeps_it_open(
        self, test_db, test_user, task, profile, ada
    ):
        task_queries.update_task(
            test_db, test_user.id, task.id, {"status": "in_progress"}
        )
        _ask_directly(test_db, test_user, task, profile, ada)
        task_queries.update_task(test_db, test_user.id, task.id, {"status": "blocked"})
        assert len(self._open(test_db, task)) == 1

    def test_deleting_the_question(self, test_db, test_user, task, profile, ada):
        # No API deletes an agent's comment yet; the hook is what a future one
        # (or the comment's soft delete anywhere) calls.
        wakeup = _ask_directly(test_db, test_user, task, profile, ada)
        comment = test_db.get(TaskComment, wakeup.source_comment_id)
        task_wakeups.on_comment_deleted(test_db, comment)
        test_db.commit()
        test_db.refresh(wakeup)
        assert (wakeup.state, wakeup.ended_reason) == ("ended", "deleted")
        assert serialize_task(test_db, task).open_questions == []

    def test_only_an_agent_asks(self, test_db, test_user, task, ada):
        with pytest.raises(ValueError):
            task_timeline_queries.create_comment(
                test_db, task, test_user.id, "q", ask_user_id=ada.id
            )

    def test_the_thread_shows_an_answered_question(
        self, test_db, test_user, task, profile, ada
    ):
        wakeup = _ask_directly(test_db, test_user, task, profile, ada)
        _as_person(test_db, ada)
        task_timeline_queries.create_comment(test_db, task, ada.id, "B")
        timeline = task_timeline_queries.build_timeline(test_db, task, test_user.id)
        [asked] = [c for c in timeline.comments if c.id == wakeup.source_comment_id]
        assert asked.question is not None
        assert asked.question.closed_reason == "answered"
        assert asked.question.addressee.name == "Ada"


class TestTheAnswerWakesTheAsker:
    def test_on_a_task_assigned_to_a_person(
        self, test_db, test_user, task, profile, ada
    ):
        task_queries.update_task(
            test_db,
            test_user.id,
            task.id,
            {"assignee_type": "user", "assignee_id": ada.id},
            sharing=True,
        )
        _ask_directly(test_db, test_user, task, profile, ada)
        _as_person(test_db, ada)
        # A teammate may wake the owner's agent only because it asked her.
        answer = task_timeline_queries.create_comment(test_db, task, ada.id, "B")
        [row] = _queued(test_db, task)
        assert (row.mode, row.trigger) == ("reply", "answered")
        assert row.agent_profile_id == profile.id
        assert row.requested_by_user_id == ada.id
        assert row.trigger_comment_id == answer.id

    def test_a_mention_is_for_the_mentioned_alone(
        self, test_db, test_user, task, profile
    ):
        other = AgentProfile(user_id=test_user.id, name="Codex", agent="codex")
        test_db.add(other)
        test_db.commit()
        wakeup = _ask_directly(test_db, test_user, task, profile, test_user)
        _as_person(test_db, test_user)
        task_timeline_queries.create_comment(
            test_db, task, test_user.id, f"[@Codex](vicoa://agent/{other.id}) help"
        )
        [row] = _queued(test_db, task)
        assert (row.agent_profile_id, row.trigger) == (other.id, "mentioned")
        test_db.refresh(wakeup)
        assert wakeup.state == "waiting"
        # Both named: each hears it, and the question is answered.
        task_timeline_queries.create_comment(
            test_db,
            task,
            test_user.id,
            f"[@Codex](vicoa://agent/{other.id}) [@Claude](vicoa://agent/{profile.id}) B",
        )
        triggers = {(r.agent_profile_id, r.trigger) for r in _queued(test_db, task)}
        assert triggers == {(other.id, "mentioned"), (profile.id, "answered")}
        test_db.refresh(wakeup)
        assert wakeup.state == "fired"

    def test_a_top_level_answer_does_not_also_wake_the_assignee(
        self, test_db, test_user, task, profile
    ):
        owner = AgentProfile(user_id=test_user.id, name="Ops", agent="claude")
        test_db.add(owner)
        test_db.commit()
        task.assignee_type, task.assignee_id = "agent", owner.id
        test_db.commit()
        _ask_directly(test_db, test_user, task, profile, test_user)
        _as_person(test_db, test_user)
        task_timeline_queries.create_comment(test_db, task, test_user.id, "B")
        [row] = _queued(test_db, task)
        assert (row.agent_profile_id, row.trigger) == (profile.id, "answered")
        # Answered, so nobody waits on him: his next top-level comment is the owner's.
        task_timeline_queries.create_comment(test_db, task, test_user.id, "And C")
        triggers = {(r.agent_profile_id, r.trigger) for r in _queued(test_db, task)}
        assert triggers == {(profile.id, "answered"), (owner.id, "commented")}

    def test_a_teammates_mention_still_cant_start_the_agent(
        self, test_db, test_user, task, profile, ada
    ):
        _as_person(test_db, ada)
        task_timeline_queries.create_comment(
            test_db, task, ada.id, f"[@Claude](vicoa://agent/{profile.id}) go"
        )
        assert _queued(test_db, task) == []

    def test_route_reads_open_questions(self, test_db, test_user, task, profile):
        _ask_directly(test_db, test_user, task, profile, test_user)
        comment = TaskComment(
            task_id=task.id, author_type="user", author_id=test_user.id, body="B"
        )
        assert task_dispatch.route_comment(test_db, task, comment) == [
            (profile.id, "answered")
        ]


class TestPeopleMentions:
    def test_a_mention_pushes_and_wakes_nobody(
        self, test_db, test_user, task, profile, ada, stranger, pushes
    ):
        _as_person(test_db, test_user)
        task_timeline_queries.create_comment(
            test_db,
            task,
            test_user.id,
            f"[@Ada](vicoa://user/{ada.id}) [@S](vicoa://user/{stranger.id}) "
            f"[@me](vicoa://user/{test_user.id}) look",
        )
        # Not the stranger (can't see the task), not the author.
        assert pushes == [("mention", ada.id)]
        assert _queued(test_db, task) == []
        assert serialize_task(test_db, task).open_questions == []

    def test_the_person_asked_gets_one_push(
        self, test_db, test_user, task, profile, ada, pushes
    ):
        set_session_actor(test_db, Actor(type="agent", id=profile.id))
        task_timeline_queries.create_comment(
            test_db,
            task,
            test_user.id,
            f"[@Ada](vicoa://user/{ada.id}) which?",
            author=("agent", profile.id),
            ask_user_id=ada.id,
        )
        assert pushes == [("question", ada.id)]

    def test_an_agent_mentioning_its_owner_pushes(
        self, test_db, test_user, task, profile, pushes
    ):
        set_session_actor(test_db, Actor(type="agent", id=profile.id))
        task_timeline_queries.create_comment(
            test_db,
            task,
            test_user.id,
            f"[@Nick](vicoa://user/{test_user.id}) done",
            author=("agent", profile.id),
        )
        assert pushes == [("mention", test_user.id)]


class _Link:
    created_by_user_id = None
    show_owner = True


class _Grant:
    link = _Link()


class TestPublicShare:
    def test_a_link_shows_no_questions_or_people(
        self, test_db, test_user, task, profile, ada
    ):
        _ask_directly(test_db, test_user, task, profile, ada)
        grant = _Grant()
        [row] = share_queries.public_tasks(test_db, grant, [task])  # type: ignore[arg-type]
        assert row.open_questions == []
        timeline = share_queries.public_timeline(
            task_timeline_queries.build_timeline(test_db, task, test_user.id),
            grant,  # type: ignore[arg-type]
        )
        assert timeline.people == []
        assert all(c.question is None for c in timeline.comments)
