"""Watcher rooms in the ConnectionManager (collaboration §9).

A watcher room, `instance:{id}:watchers`, is joined at runtime by someone a
session is shared with. What reaches it is the grantee view of the owner's
payload — narrowed once, on the way out — and nothing the view does not know.
Routing is the behavior under test, so connections are read through their
outbox; no socket and no database.
"""

from datetime import datetime, timedelta, timezone

from shared.websocket.connection_manager import (
    MAX_WATCHES_PER_CONNECTION,
    Connection,
    ConnectionManager,
)
from shared.websocket.envelope import build_access_changed_update
from shared.websocket.protocol import is_watcher_room, watcher_room
from shared.websocket.watchers import watcher_view

OWNER_ROOM = "user:owner:user-scoped"


def _conn(connection_id: str, user_id: str, *rooms: str) -> Connection:
    return Connection(
        connection_id=connection_id,
        user_id=user_id,
        scope="user-scoped",
        rooms=frozenset(rooms),
    )


def _instance_payload(**overrides: object) -> dict:
    body = {
        "t": "instance-update",
        "id": "i1",
        "user_agent_id": "a1",
        "status": "ACTIVE",
        "name": "Fix the thing",
        "project": "/Users/owner/src/secret-repo",
        "home_dir": "/Users/owner",
        "started_at": "2026-09-29T10:00:00Z",
        "ended_at": None,
        "last_heartbeat_at": None,
        "machine_id": "m1",
        "instance_metadata": {"worktree_name": "wt", "repo_root": "/Users/owner/src"},
        "session_config": {"model": "opus", "cwd": "/Users/owner/src", "env": {}},
        "has_git_changes": True,
        "updated_at": "2026-09-29T10:00:01Z",
        "pinned_at": None,
    }
    body.update(overrides)
    return {
        "entity": "agent_instances",
        "entity_id": "i1",
        "event_id": "i1:update",
        "body": body,
    }


def _drain(conn: Connection) -> list[dict]:
    frames = []
    while not conn.outbox.empty():
        frames.append(conn.outbox.get_nowait())
    return frames


def test_watcher_room_is_not_user_prefixed() -> None:
    room = watcher_room("i1")
    assert room == "instance:i1:watchers"
    assert is_watcher_room(room)
    assert not is_watcher_room(OWNER_ROOM)


def test_a_watcher_gets_the_narrowed_row_and_the_owner_the_full_one() -> None:
    manager = ConnectionManager()
    owner = _conn("c-owner", "owner", OWNER_ROOM)
    grantee = _conn("c-grantee", "grantee", "user:grantee:user-scoped")
    manager.register(owner)
    manager.register(grantee)
    assert manager.watch(grantee, "i1")

    payload = _instance_payload()
    manager.broadcast_update("owner", payload, [OWNER_ROOM, watcher_room("i1")])

    assert _drain(owner) == [{"type": "update", "payload": payload}]
    [frame] = _drain(grantee)
    body = frame["payload"]["body"]
    assert body["home_dir"] is None
    assert body["machine_id"] is None
    assert body["project"] == "secret-repo"
    assert body["instance_metadata"] == {"worktree_name": "wt"}
    assert body["session_config"] == {"model": "opus"}
    assert body["has_git_changes"] is False
    assert body["grantee_view"] is True
    # The owner's copy was not mutated by the narrowing.
    assert payload["body"]["home_dir"] == "/Users/owner"


def test_the_watcher_copy_always_carries_a_live_state() -> None:
    """With `machine_id` stripped a client cannot derive liveness from the
    machine heartbeat, so the relay stamps its own verdict."""
    manager = ConnectionManager()
    grantee = _conn("c", "grantee")
    manager.register(grantee)
    manager.watch(grantee, "i1")
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    manager.broadcast_update(
        "owner",
        _instance_payload(last_heartbeat_at=stale, started_at=stale),
        [watcher_room("i1")],
    )

    [frame] = _drain(grantee)
    # The daemon holds no socket here, so the host reads as offline.
    assert frame["payload"]["body"]["live_state"] == "machine_offline"


def test_a_site_supplied_live_state_is_kept() -> None:
    narrowed = watcher_view(
        _instance_payload(live_state="live"),
        session_connected=lambda _: False,
        machine_connected=lambda _: False,
    )
    assert narrowed is not None
    assert narrowed["body"]["live_state"] == "live"


def test_a_connected_session_socket_reads_as_live() -> None:
    narrowed = watcher_view(
        _instance_payload(started_at="2020-01-01T00:00:00Z"),
        session_connected=lambda iid: iid == "i1",
        machine_connected=lambda _: False,
    )
    assert narrowed is not None
    assert narrowed["body"]["live_state"] == "live"


def test_messages_pass_through_unchanged() -> None:
    payload = {
        "entity": "messages",
        "entity_id": "m1",
        "event_id": "m1:insert",
        "body": {"t": "new-message", "id": "m1", "instance_id": "i1", "content": "hi"},
    }
    manager = ConnectionManager()
    grantee = _conn("c", "grantee")
    manager.register(grantee)
    manager.watch(grantee, "i1")

    manager.broadcast_update("owner", payload, [OWNER_ROOM, watcher_room("i1")])

    assert _drain(grantee) == [{"type": "update", "payload": payload}]


def test_payloads_the_view_does_not_know_are_withheld() -> None:
    """Machines, spawn requests, anything new: the owner's alone. A watcher
    room is never a pass-through for a kind nobody decided about."""
    manager = ConnectionManager()
    grantee = _conn("c", "grantee")
    manager.register(grantee)
    manager.watch(grantee, "i1")

    manager.broadcast_update(
        "owner",
        {"entity": "machines", "body": {"t": "machine-update", "id": "m1"}},
        [watcher_room("i1")],
    )
    manager.broadcast_update(
        "owner", {"entity": "x", "body": {"t": "something-new"}}, [watcher_room("i1")]
    )

    assert _drain(grantee) == []


def test_verbatim_frames_never_reach_a_watcher_room() -> None:
    manager = ConnectionManager()
    grantee = _conn("c", "grantee")
    manager.register(grantee)
    manager.watch(grantee, "i1")

    manager.broadcast_frame([watcher_room("i1")], {"type": "pty-output", "data": "x"})

    assert _drain(grantee) == []


def test_a_connection_in_both_kinds_of_room_gets_only_the_owner_copy() -> None:
    manager = ConnectionManager()
    both = _conn("c", "owner", OWNER_ROOM)
    manager.register(both)
    manager.watch(both, "i1")

    payload = _instance_payload()
    manager.broadcast_update("owner", payload, [OWNER_ROOM, watcher_room("i1")])

    assert _drain(both) == [{"type": "update", "payload": payload}]


def test_an_empty_watcher_room_builds_nothing(monkeypatch) -> None:
    calls = []

    def spy(payload, **_):
        calls.append(payload)
        return payload

    monkeypatch.setattr("shared.websocket.connection_manager.watcher_view", spy)
    manager = ConnectionManager()
    owner = _conn("c", "owner", OWNER_ROOM)
    manager.register(owner)

    manager.broadcast_update(
        "owner", _instance_payload(), [OWNER_ROOM, watcher_room("i1")]
    )

    assert calls == []


def test_unwatch_and_unregister_leave_no_room_behind() -> None:
    manager = ConnectionManager()
    grantee = _conn("c", "grantee", "user:grantee:user-scoped")
    manager.register(grantee)
    manager.watch(grantee, "i1")
    manager.watch(grantee, "i2")
    assert manager.has_watchers("i1")
    assert set(manager.watchers()) == {"i1", "i2"}

    assert manager.unwatch(grantee, "i1")
    assert not manager.has_watchers("i1")
    assert not manager.unwatch(grantee, "i1")

    manager.unregister(grantee)
    assert not manager.has_watchers("i2")
    assert manager.watchers() == {}
    assert grantee.watching == set()


def test_revoke_watch_evicts_and_tells_the_client() -> None:
    manager = ConnectionManager()
    grantee = _conn("c", "grantee")
    manager.register(grantee)
    manager.watch(grantee, "i1")
    grantee.access_cache["i1"] = (0.0, "viewer")

    manager.revoke_watch(grantee, "i1")

    assert _drain(grantee) == [
        {"type": "watch_revoked", "instance_id": "i1", "reason": "access_revoked"}
    ]
    assert "i1" not in grantee.access_cache
    manager.broadcast_update("owner", _instance_payload(), [watcher_room("i1")])
    assert _drain(grantee) == []


def test_watches_per_connection_are_capped() -> None:
    manager = ConnectionManager()
    grantee = _conn("c", "grantee")
    manager.register(grantee)
    for n in range(MAX_WATCHES_PER_CONNECTION):
        assert manager.watch(grantee, f"i{n}")
    assert not manager.watch(grantee, "one-too-many")
    # Re-watching one already held is not a new slot.
    assert manager.watch(grantee, "i0")


def test_access_changed_payload_names_what_changed() -> None:
    payload = build_access_changed_update(project_id="p1")
    assert payload["entity"] == "access"
    assert payload["entity_id"] == "p1"
    assert payload["body"] == {
        "t": "access-changed",
        "project_id": "p1",
        "instance_id": None,
    }
    # Unique per event, so a client's dedupe never swallows the second change.
    assert (
        build_access_changed_update(project_id="p1")["event_id"] != payload["event_id"]
    )
