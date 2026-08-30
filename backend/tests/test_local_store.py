"""LocalStore CRUD + pending-delivery semantics (desktop local-only mode)."""

from pathlib import Path

import pytest

from vicoa.local_server.store import (
    InstanceConflictError,
    InstanceNotFoundError,
    LocalStore,
)


@pytest.fixture
def store(tmp_path: Path):
    s = LocalStore(tmp_path / "local_store.db")
    yield s
    s.close()


def _register(store: LocalStore, **kwargs) -> str:
    defaults = dict(agent_type="Claude Code", project="/tmp/proj")
    defaults.update(kwargs)
    return store.register_instance(**defaults).id


# ----------------------------------------------------------------------
# Instances
# ----------------------------------------------------------------------
def test_register_and_get_instance(store: LocalStore) -> None:
    inst = store.register_instance(
        agent_type="Claude Code",
        agent_instance_id="11111111-1111-1111-1111-111111111111",
        name="my session",
        project="/tmp/proj",
        transport="ws",
        source="app",
        session_config={"agent": "claude"},
    )
    assert inst.id == "11111111-1111-1111-1111-111111111111"
    assert inst.status == "ACTIVE"
    assert inst.machine_id is None
    assert inst.instance_metadata == {"transport": "ws", "source": "app"}
    fetched = store.get_instance(inst.id)
    assert fetched is not None
    assert fetched.session_config == {"agent": "claude"}
    assert fetched.started_at.endswith("Z")


def test_register_duplicate_id_conflicts(store: LocalStore) -> None:
    instance_id = _register(store)
    with pytest.raises(InstanceConflictError):
        store.register_instance(agent_type="Claude Code", agent_instance_id=instance_id)


def test_update_status_and_terminal_semantics(store: LocalStore) -> None:
    instance_id = _register(store)
    updated = store.update_instance_status(instance_id, "AWAITING_INPUT")
    assert updated.status == "AWAITING_INPUT"
    completed = store.update_instance_status(instance_id, "COMPLETED")
    assert completed.ended_at is not None
    with pytest.raises(ValueError, match="Invalid status"):
        store.update_instance_status(instance_id, "NOT_A_STATUS")
    with pytest.raises(InstanceNotFoundError):
        store.update_instance_status("missing-id", "ACTIVE")


def test_patch_instance_merges_session_config(store: LocalStore) -> None:
    instance_id = _register(store, session_config={"agent": "claude", "model": "a"})
    patched = store.patch_instance(
        instance_id, name="renamed", session_config_merge={"model": "b"}
    )
    assert patched.name == "renamed"
    assert patched.session_config == {"agent": "claude", "model": "b"}


# ----------------------------------------------------------------------
# Messages + pending delivery
# ----------------------------------------------------------------------
def test_agent_message_collects_queued_user_messages(store: LocalStore) -> None:
    instance_id = _register(store)
    # Renderer-style user message: mark_as_read=False keeps it pending.
    store.add_user_message(
        agent_instance_id=instance_id, content="first", mark_as_read=False
    )
    message, instance, queued = store.add_agent_message(
        agent_instance_id=instance_id, content="reply", requires_user_input=False
    )
    assert [m.content for m in queued] == ["first"]
    assert instance.status == "ACTIVE"
    # The new agent message becomes the read cursor.
    assert instance.last_read_message_id == message.id


def test_agent_message_creates_instance_when_missing(store: LocalStore) -> None:
    message, instance, queued = store.add_agent_message(
        agent_instance_id="22222222-2222-2222-2222-222222222222",
        content="hello",
        agent_type="Claude Code",
        requires_user_input=True,
    )
    assert instance.id == "22222222-2222-2222-2222-222222222222"
    assert instance.status == "AWAITING_INPUT"
    assert queued == []
    with pytest.raises(ValueError, match="agent_type is required"):
        store.add_agent_message(agent_instance_id="unknown", content="x")


def test_pending_messages_deliver_once(store: LocalStore) -> None:
    instance_id = _register(store)
    store.add_user_message(
        agent_instance_id=instance_id, content="ping", mark_as_read=False
    )
    messages, status = store.pending_messages(instance_id, None)
    assert status == "ok"
    assert [m.content for m in messages] == ["ping"]
    # Delivery advanced the cursor: nothing pending on the next poll.
    again, status = store.pending_messages(instance_id, messages[-1].id)
    assert status == "ok"
    assert again == []


def test_pending_messages_stale_cursor(store: LocalStore) -> None:
    instance_id = _register(store)
    store.add_user_message(
        agent_instance_id=instance_id, content="ping", mark_as_read=False
    )
    store.pending_messages(instance_id, None)
    _, status = store.pending_messages(instance_id, "not-the-cursor")
    assert status == "stale"


def test_mark_as_read_user_message_is_not_pending(store: LocalStore) -> None:
    instance_id = _register(store)
    store.add_user_message(
        agent_instance_id=instance_id, content="already-read", mark_as_read=True
    )
    messages, status = store.pending_messages(instance_id, None)
    assert status == "ok"
    assert messages == []


def test_mark_message_requires_input(store: LocalStore) -> None:
    instance_id = _register(store)
    agent_msg, _, _ = store.add_agent_message(
        agent_instance_id=instance_id, content="question?"
    )
    returned_id, queued, status = store.mark_message_requires_input(agent_msg.id)
    assert returned_id == instance_id
    assert queued == []
    assert status == "ok"
    inst = store.get_instance(instance_id)
    assert inst is not None and inst.status == "AWAITING_INPUT"
    with pytest.raises(ValueError, match="already requires"):
        store.mark_message_requires_input(agent_msg.id)


# ----------------------------------------------------------------------
# WS catch-up fetches
# ----------------------------------------------------------------------
def test_fetch_messages_scope_policies(store: LocalStore) -> None:
    instance_id = _register(store)
    store.add_user_message(
        agent_instance_id=instance_id, content="u1", mark_as_read=False
    )
    store.add_agent_message(agent_instance_id=instance_id, content="a1")

    # User-scoped (renderer): full conversation.
    rows, has_more, resync = store.fetch_messages(
        instance_id, None, include_agent_messages=True
    )
    assert resync is None and has_more is False
    assert [r["content"] for r in rows] == ["u1", "a1"]
    assert rows[0]["t"] == "new-message"
    assert rows[0]["instance_id"] == instance_id

    # Session-scoped (wrapper): USER-only, and the last_read cursor (advanced
    # by the agent reply) suppresses already-processed rows.
    rows, _, _ = store.fetch_messages(instance_id, None, include_agent_messages=False)
    assert rows == []


def test_fetch_messages_pagination_cursor(store: LocalStore) -> None:
    instance_id = _register(store)
    for index in range(5):
        store.add_user_message(
            agent_instance_id=instance_id, content=f"m{index}", mark_as_read=False
        )
    first, has_more, _ = store.fetch_messages(
        instance_id, None, include_agent_messages=True, page_limit=2
    )
    assert [r["content"] for r in first] == ["m0", "m1"]
    assert has_more is True
    second, _, _ = store.fetch_messages(
        instance_id,
        {"created_at": first[-1]["created_at"], "id": first[-1]["id"]},
        include_agent_messages=True,
        page_limit=10,
    )
    assert [r["content"] for r in second] == ["m2", "m3", "m4"]


def test_fetch_messages_missing_cursor_requests_resync(store: LocalStore) -> None:
    instance_id = _register(store)
    rows, has_more, resync = store.fetch_messages(
        instance_id,
        {"created_at": "2026-01-01T00:00:00.000000Z", "id": "gone"},
        include_agent_messages=True,
    )
    assert rows == [] and has_more is False
    assert resync == "missing_history"


def test_fetch_instances_watermark(store: LocalStore) -> None:
    instance_id = _register(store)
    rows = store.fetch_instances(None)
    assert [r["id"] for r in rows] == [instance_id]
    assert rows[0]["t"] == "instance-update"
    # A watermark far in the future (beyond the safety window) filters it out.
    rows = store.fetch_instances("2999-01-01T00:00:00.000000Z")
    assert rows == []


# ----------------------------------------------------------------------
# Event hook
# ----------------------------------------------------------------------
def test_listener_receives_envelope_payloads(store: LocalStore) -> None:
    events: list[dict] = []
    store.add_listener(events.append)
    instance_id = _register(store)
    store.add_user_message(
        agent_instance_id=instance_id, content="hi", mark_as_read=False
    )
    kinds = [e["body"]["t"] for e in events]
    assert kinds == ["instance-created", "new-message"]
    assert events[0]["entity"] == "agent_instances"
    assert events[1]["entity"] == "messages"
    assert events[1]["body"]["content"] == "hi"


def test_recent_directories_roundtrip(store: LocalStore) -> None:
    store.push_recent_directory("/tmp/a")
    store.push_recent_directory("/tmp/b")
    store.push_recent_directory("/tmp/a")
    assert store.recent_directories() == ["/tmp/a", "/tmp/b"]
