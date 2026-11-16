"""The task dispatch sweep delivers each queued dispatch exactly once.

Into the (agent, task) session when there is one — a message or a resume —
else a new session on the resolved machine and folder. Its cap, its offline
retry and its fallback to a fresh session are what keep a person from waiting
on something that silently never happened.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest

from servers.scheduler import task_dispatcher
from servers.scheduler.dispatch import DispatchResult
from shared.database import Project, Task, TaskDispatch
from shared.database.agent_profile_models import AgentProfile
from shared.database.enums import AgentStatus
from shared.database.models import AgentInstance, AgentType, Machine, User
from shared.database.task_models import ProjectDirectory

pytestmark = pytest.mark.committed_db


class FakeSockets:
    def __init__(self) -> None:
        self.connected: set[str] = set()

    def is_session_connected(self, instance_id: str) -> bool:
        return instance_id in self.connected


class Recorder:
    """Stands in for `dispatch_automation` and `deliver_to_session`."""

    def __init__(self) -> None:
        self.spawns: list[dict[str, Any]] = []
        self.deliveries: list[dict[str, Any]] = []
        self.spawn_result = DispatchResult(status="fired", agent_instance_id=None)
        self.deliver_result = DispatchResult(status="fired", via="message")

    async def spawn(self, **kwargs: Any) -> DispatchResult:
        self.spawns.append(kwargs)
        return self.spawn_result

    async def deliver(self, **kwargs: Any) -> DispatchResult:
        self.deliveries.append(kwargs)
        return self.deliver_result


@pytest.fixture
def user(test_db) -> User:
    return test_db.query(User).first()


@pytest.fixture
def machine(test_db, user) -> Machine:
    row = Machine(
        id=uuid4(),
        user_id=user.id,
        display_name="laptop",
        last_heartbeat_at=datetime.now(timezone.utc),
    )
    test_db.add(row)
    test_db.commit()
    return row


@pytest.fixture
def profile(test_db, user, machine) -> AgentProfile:
    row = AgentProfile(
        user_id=user.id,
        name="Claude",
        agent="claude",
        config={"agent": "claude", "model": "opus"},
        default_machine_id=machine.id,
    )
    test_db.add(row)
    test_db.commit()
    return row


@pytest.fixture
def task(test_db, user, machine) -> Task:
    project = Project(user_id=user.id, name="Vicoa", key="VIC", task_counter=1)
    test_db.add(project)
    test_db.flush()
    test_db.add(
        ProjectDirectory(
            user_id=user.id,
            project_id=project.id,
            machine_id=machine.id,
            local_path="/src/vicoa",
        )
    )
    row = Task(
        user_id=user.id,
        project_id=project.id,
        number=7,
        title="Fix the flaky login test",
        status="todo",
    )
    test_db.add(row)
    test_db.commit()
    return row


def _queue(db, task, profile, *, mode="ownership", trigger="assigned") -> TaskDispatch:
    row = TaskDispatch(
        user_id=profile.user_id,
        task_id=task.id,
        agent_profile_id=profile.id,
        mode=mode,
        trigger=trigger,
        state="queued",
        worktree={"mode": "new"},
        next_attempt_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    db.add(row)
    db.commit()
    return row


def _session(
    db, user, machine, task, profile, status=AgentStatus.AWAITING_INPUT, worktree=None
):
    agent_type = db.query(AgentType).first()
    row = AgentInstance(
        id=uuid4(),
        agent_type_id=agent_type.id,
        user_id=user.id,
        status=status,
        started_at=datetime.now(timezone.utc),
        machine_id=machine.id,
        project=f"~/worktrees/{worktree}" if worktree else "/src/vicoa",
        home_dir="/Users/me",
        instance_metadata={"worktree_name": worktree} if worktree else {},
        task_id=task.id,
        agent_profile_id=profile.id,
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def harness(monkeypatch, db_session_factory):
    sockets = FakeSockets()
    recorder = Recorder()
    monkeypatch.setattr(task_dispatcher, "SessionLocal", db_session_factory)
    monkeypatch.setattr(task_dispatcher, "connection_manager", sockets)
    monkeypatch.setattr(task_dispatcher, "dispatch_automation", recorder.spawn)
    monkeypatch.setattr(task_dispatcher, "deliver_to_session", recorder.deliver)
    return sockets, recorder


def _reload(db, row: TaskDispatch) -> TaskDispatch:
    db.expire_all()
    return db.get(TaskDispatch, row.id)


async def test_no_session_starts_one_where_the_project_lives(
    test_db, harness, task, profile, machine
):
    _, recorder = harness
    row = _queue(test_db, task, profile)
    await task_dispatcher.TaskDispatcher().sweep_once()

    [spawn] = recorder.spawns
    assert spawn["machine_id"] == machine.id
    assert spawn["directory"] == "/src/vicoa"
    assert spawn["worktree"] == {
        "mode": "new",
        "name": "vic-7-fix-the-flaky-login-test",
    }
    assert spawn["session_config"]["model"] == "opus"
    assert spawn["prompt"].startswith(
        'Someone assigned VIC-7 "Fix the flaky login test" to you.'
    )
    # The standing rules ride in the system prompt, not in the message.
    assert "--assignee me" in spawn["system_prompt"]
    assert "--assignee me" not in spawn["prompt"]
    assert _reload(test_db, row).state == "started"


async def test_a_live_session_gets_a_message(
    test_db, harness, user, machine, task, profile
):
    sockets, recorder = harness
    session = _session(test_db, user, machine, task, profile)
    sockets.connected.add(str(session.id))
    row = _queue(test_db, task, profile, mode="reply", trigger="commented")
    await task_dispatcher.TaskDispatcher().sweep_once()

    [delivery] = recorder.deliveries
    assert delivery["instance_id"] == session.id
    assert delivery["marker"] == ("task_dispatch_id", str(row.id))
    assert "VIC-7" in delivery["prompt"]
    # Never given the brief: it comes in front of this first task message.
    assert delivery["message_prompt"].startswith("How to work on Vicoa tasks")
    assert delivery["message_prompt"].endswith(delivery["prompt"])
    assert recorder.spawns == []
    reloaded = _reload(test_db, row)
    assert (reloaded.state, reloaded.agent_instance_id) == ("delivered", session.id)
    # ...and from now on the session counts as having it, resume included.
    assert (
        test_db.get(AgentInstance, session.id).instance_metadata["task_brief"] is True
    )
    assert task_dispatcher.brief_for_resume_blocking(user.id, session.id) is not None


async def test_a_stopped_session_that_resumes(
    test_db, harness, user, machine, task, profile
):
    _, recorder = harness
    _session(test_db, user, machine, task, profile, status=AgentStatus.COMPLETED)
    recorder.deliver_result = DispatchResult(status="fired", via="resume")
    row = _queue(test_db, task, profile)
    await task_dispatcher.TaskDispatcher().sweep_once()
    assert _reload(test_db, row).state == "resumed"


async def test_an_unresumable_session_falls_back_to_a_fresh_one(
    test_db, harness, user, machine, task, profile
):
    _, recorder = harness
    _session(test_db, user, machine, task, profile, status=AgentStatus.COMPLETED)
    recorder.deliver_result = DispatchResult(status="failed", detail="no transcript")
    row = _queue(test_db, task, profile)
    await task_dispatcher.TaskDispatcher().sweep_once()

    [spawn] = recorder.spawns
    assert "could not be resumed" in spawn["prompt"]
    assert _reload(test_db, row).state == "started"


async def test_an_offline_computer_waits(
    test_db, harness, user, machine, task, profile
):
    _, recorder = harness
    _session(test_db, user, machine, task, profile, status=AgentStatus.COMPLETED)
    recorder.deliver_result = DispatchResult(status="missed_offline")
    row = _queue(test_db, task, profile)
    await task_dispatcher.TaskDispatcher().sweep_once()

    reloaded = _reload(test_db, row)
    assert reloaded.state == "queued"
    assert reloaded.detail == "waiting for the computer to come online"
    assert reloaded.next_attempt_at > datetime.now(timezone.utc)


async def test_the_cap_holds_the_rest_back(
    test_db, harness, user, machine, task, profile
):
    _, recorder = harness
    profile.max_concurrent_sessions = 1
    test_db.commit()
    other = Task(user_id=user.id, title="busy one", status="in_progress")
    test_db.add(other)
    test_db.commit()
    _session(test_db, user, machine, other, profile, status=AgentStatus.ACTIVE)
    row = _queue(test_db, task, profile)
    await task_dispatcher.TaskDispatcher().sweep_once()

    assert recorder.spawns == []
    reloaded = _reload(test_db, row)
    assert reloaded.state == "queued"
    assert reloaded.detail == "queued: 1 of 1 sessions busy"


async def test_a_message_into_a_running_turn_needs_no_slot(
    test_db, harness, user, machine, task, profile
):
    sockets, recorder = harness
    profile.max_concurrent_sessions = 1
    test_db.commit()
    session = _session(test_db, user, machine, task, profile, status=AgentStatus.ACTIVE)
    sockets.connected.add(str(session.id))
    row = _queue(test_db, task, profile, mode="reply", trigger="commented")
    await task_dispatcher.TaskDispatcher().sweep_once()
    assert len(recorder.deliveries) == 1
    assert _reload(test_db, row).state == "delivered"


async def test_nowhere_to_run_fails_visibly(test_db, harness, user, profile):
    _, recorder = harness
    profile.default_machine_id = None
    test_db.commit()
    loose = Task(user_id=user.id, title="unfiled", status="todo")
    test_db.add(loose)
    test_db.commit()
    row = _queue(test_db, loose, profile)
    await task_dispatcher.TaskDispatcher().sweep_once()

    assert recorder.spawns == []
    reloaded = _reload(test_db, row)
    assert reloaded.state == "failed"
    assert reloaded.detail and "no computer" in reloaded.detail


async def test_a_closed_task_is_cancelled(test_db, harness, task, profile):
    _, recorder = harness
    row = _queue(test_db, task, profile)
    task.status = "done"
    test_db.commit()
    await task_dispatcher.TaskDispatcher().sweep_once()
    assert recorder.spawns == [] and recorder.deliveries == []
    assert _reload(test_db, row).state == "cancelled"


async def test_the_spawned_session_is_linked_to_task_and_agent(
    test_db, harness, user, machine, task, profile, monkeypatch
):
    _, recorder = harness
    monkeypatch.setattr(task_dispatcher, "STAMP_DELAYS", (0.0,))
    new_id = uuid4()
    recorder.spawn_result = DispatchResult(
        status="fired", agent_instance_id=str(new_id)
    )
    row = _queue(test_db, task, profile)
    dispatcher = task_dispatcher.TaskDispatcher()
    await dispatcher.sweep_once()

    # The wrapper registers its row a moment after the spawn returns.
    agent_type = test_db.query(AgentType).first()
    test_db.add(
        AgentInstance(
            id=new_id,
            agent_type_id=agent_type.id,
            user_id=user.id,
            status=AgentStatus.ACTIVE,
            started_at=datetime.now(timezone.utc),
        )
    )
    test_db.commit()
    claim = task_dispatcher._Claim(
        id=row.id,
        user_id=user.id,
        task_id=task.id,
        profile_id=profile.id,
        session_id=None,
        prompt="",
        message_prompt="",
        session_config={},
        system_prompt="",
        spawns=[],
        placement_problem=None,
    )
    await dispatcher._stamp(claim, new_id)
    test_db.expire_all()
    instance = test_db.get(AgentInstance, new_id)
    assert (instance.task_id, instance.agent_profile_id) == (task.id, profile.id)
    assert test_db.get(TaskDispatch, row.id).agent_instance_id == new_id
    # Linking the running session moved the todo task to in_progress.
    assert test_db.get(Task, task.id).status == "in_progress"


def test_worktree_names_are_short_and_safe():
    name = task_dispatcher._worktree_name("VIC-7", "Fix: the *very* long title " * 5)
    assert name.startswith("vic-7-fix-the-very-long-title")
    assert len(name) <= 48


class FlakySpawn(Recorder):
    """The first spawn is refused (its folder is gone), the next one fires."""

    async def spawn(self, **kwargs: Any) -> DispatchResult:
        self.spawns.append(kwargs)
        if len(self.spawns) == 1:
            return DispatchResult(status="failed", detail="no such directory")
        return DispatchResult(status="fired", agent_instance_id=None)


async def test_handed_back_tells_the_agent_what_changed(
    test_db, harness, user, machine, task, profile
):
    from shared.database import TaskActivity

    sockets, recorder = harness
    session = _session(test_db, user, machine, task, profile)
    sockets.connected.add(str(session.id))
    handed_over = datetime.now(timezone.utc) - timedelta(minutes=10)
    # The agent handed the task to the person; the person commented and blocked it.
    test_db.add(
        TaskActivity(
            task_id=task.id,
            project_id=task.project_id,
            actor_type="agent",
            actor_id=profile.id,
            action="assigned",
            details={"from": str(profile.id), "to": str(user.id), "to_type": "user"},
            created_at=handed_over,
        )
    )
    test_db.add(
        TaskActivity(
            task_id=task.id,
            project_id=task.project_id,
            actor_type="user",
            actor_id=user.id,
            action="status_changed",
            details={"from": "in_progress", "to": "blocked"},
            created_at=handed_over + timedelta(minutes=2),
        )
    )
    from shared.database import TaskComment

    comment = TaskComment(
        task_id=task.id,
        project_id=task.project_id,
        author_type="user",
        author_id=user.id,
        body="Use the staging bucket, not prod.",
        created_at=handed_over + timedelta(minutes=3),
    )
    test_db.add(comment)
    test_db.commit()
    _queue(test_db, task, profile)
    await task_dispatcher.TaskDispatcher().sweep_once()

    [delivery] = recorder.deliveries
    prompt = delivery["prompt"]
    assert prompt.startswith(
        'Someone assigned VIC-7 "Fix the flaky login test" back to you.'
    )
    assert "Since you handed it over" in prompt
    assert f"in thread `{comment.id}`" in prompt
    assert "> Use the staging bucket, not prod." in prompt
    assert "the status was changed to blocked" in prompt
    assert "bring your branch up to date" in prompt


async def test_another_agent_continues_in_the_tasks_worktree(
    test_db, harness, user, machine, task, profile
):
    _, recorder = harness
    other = AgentProfile(
        user_id=user.id,
        name="Codex",
        agent="codex",
        config={"agent": "codex"},
        default_machine_id=machine.id,
    )
    test_db.add(other)
    test_db.commit()
    earlier = _session(
        test_db,
        user,
        machine,
        task,
        profile,
        status=AgentStatus.COMPLETED,
        worktree="vic-7-flaky",
    )
    _queue(test_db, task, other)
    await task_dispatcher.TaskDispatcher().sweep_once()

    [spawn] = recorder.spawns
    assert spawn["directory"] == "/Users/me/worktrees/vic-7-flaky"
    assert spawn["worktree"] is None
    assert str(earlier.id) in spawn["prompt"]
    assert "Claude worked on it before" in spawn["prompt"]
    assert "in this folder" in spawn["prompt"]


async def test_unresumable_session_restarts_in_its_worktree_then_a_new_one(
    test_db, monkeypatch, harness, user, machine, task, profile
):
    _, recorder = harness
    flaky = FlakySpawn()
    flaky.deliver_result = DispatchResult(status="failed", detail="no transcript")
    monkeypatch.setattr(task_dispatcher, "dispatch_automation", flaky.spawn)
    monkeypatch.setattr(task_dispatcher, "deliver_to_session", flaky.deliver)
    _session(
        test_db,
        user,
        machine,
        task,
        profile,
        status=AgentStatus.COMPLETED,
        worktree="vic-7-flaky",
    )
    row = _queue(test_db, task, profile)
    await task_dispatcher.TaskDispatcher().sweep_once()

    first, second = flaky.spawns
    assert first["directory"] == "/Users/me/worktrees/vic-7-flaky"
    assert first["worktree"] is None
    # The old worktree's name may still be taken: the new one gets its own.
    assert second["directory"] == "/src/vicoa"
    assert second["worktree"]["mode"] == "new"
    assert second["worktree"]["name"].startswith("vic-7-fix-the-flaky")
    assert second["worktree"]["name"] != "vic-7-fix-the-flaky-login-test"
    assert "could not be resumed" in second["prompt"]
    assert _reload(test_db, row).state == "started"


async def test_a_comment_is_quoted_with_its_author(
    test_db, harness, user, machine, task, profile
):
    from shared.database import TaskComment

    sockets, recorder = harness
    session = _session(test_db, user, machine, task, profile)
    session.instance_metadata = {"task_brief": True}
    test_db.commit()
    sockets.connected.add(str(session.id))
    comment = TaskComment(
        task_id=task.id,
        project_id=task.project_id,
        author_type="user",
        author_id=user.id,
        body="Can you also cover the retry path?",
    )
    test_db.add(comment)
    test_db.commit()
    row = _queue(test_db, task, profile, mode="reply", trigger="mentioned")
    row.trigger_comment_id = comment.id
    test_db.commit()
    await task_dispatcher.TaskDispatcher().sweep_once()

    [delivery] = recorder.deliveries
    name = user.display_name or "Someone"
    assert delivery["prompt"].startswith(
        f'{name} mentioned you on VIC-7 "Fix the flaky login test":'
    )
    assert "> Can you also cover the retry path?" in delivery["prompt"]
    assert f"--reply-to {comment.id}" in delivery["prompt"]
    # It already has the brief: the message goes in as it is.
    assert delivery["message_prompt"] == delivery["prompt"]
