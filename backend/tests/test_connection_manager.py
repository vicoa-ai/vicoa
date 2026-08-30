"""Behavioral tests for the in-memory ConnectionManager (websocket-migration §2.10).

The manager keeps a process-local registry of WebSocket connections indexed by
user and by room. `broadcast_update` fans a frame out to every connection in the
target rooms; clean unregistration must leave no dangling references.

Connections are tested through their outbox queue — no real WebSocket is needed,
because routing is the behavior under test, not socket I/O.
"""

import asyncio

from shared.websocket.connection_manager import (
    Connection,
    ConnectionManager,
    connections_closed_slow_count,
)


def _conn(connection_id: str, user_id: str, scope: str, *rooms: str) -> Connection:
    return Connection(
        connection_id=connection_id,
        user_id=user_id,
        scope=scope,
        rooms=frozenset(rooms),
    )


def test_broadcast_update_reaches_connection_in_target_room() -> None:
    manager = ConnectionManager()
    conn = _conn("c1", "u1", "user-scoped", "user:u1:user-scoped")
    manager.register(conn)

    manager.broadcast_update(
        "u1", {"entity": "messages"}, rooms=["user:u1:user-scoped"]
    )

    assert conn.outbox.get_nowait() == {
        "type": "update",
        "payload": {"entity": "messages"},
    }


def test_broadcast_frame_delivers_the_frame_verbatim_to_the_room() -> None:
    """Raw push frames (e.g. pty-output) are NOT wrapped in an `update`
    envelope — the client dispatches them by top-level type."""
    manager = ConnectionManager()
    room = "user:u1:machine:m1:terminals"
    watcher = _conn("c1", "u1", "terminal-scoped", room)
    other = _conn("c2", "u1", "user-scoped", "user:u1:user-scoped")
    manager.register(watcher)
    manager.register(other)

    frame = {"type": "pty-output", "pty_id": "p1", "data": "aGk="}
    manager.broadcast_frame([room], frame)

    assert watcher.outbox.get_nowait() == frame
    # A connection in a different room does not receive it.
    assert other.outbox.empty()


def test_unregister_stops_a_connection_from_receiving_broadcasts() -> None:
    manager = ConnectionManager()
    conn = _conn("c1", "u1", "user-scoped", "user:u1:user-scoped")
    manager.register(conn)
    manager.unregister(conn)

    manager.broadcast_update("u1", {"entity": "messages"}, ["user:u1:user-scoped"])

    assert conn.outbox.empty()


def test_has_user_scoped_reflects_a_registered_user_scoped_connection() -> None:
    manager = ConnectionManager()
    assert manager.has_user_scoped("u1") is False

    manager.register(_conn("c1", "u1", "user-scoped", "user:u1:user-scoped"))

    assert manager.has_user_scoped("u1") is True


def test_has_user_scoped_ignores_non_user_scoped_connections() -> None:
    """FCM push gating must not be satisfied by a CLI session-scoped socket."""
    manager = ConnectionManager()
    manager.register(_conn("c1", "u1", "session-scoped", "user:u1:session:i1"))

    assert manager.has_user_scoped("u1") is False


# ---------------------------------------------------------------------------
# desktop foreground presence (gates FCM phone push)
# ---------------------------------------------------------------------------


def test_is_desktop_foreground_false_without_a_report() -> None:
    """A registered connection that never reported foreground doesn't suppress."""
    manager = ConnectionManager()
    manager.register(_conn("c1", "u1", "user-scoped", "user:u1:user-scoped"))

    assert manager.is_desktop_foreground("u1") is False


def test_record_presence_true_marks_the_user_foreground() -> None:
    manager = ConnectionManager()
    conn = _conn("c1", "u1", "user-scoped", "user:u1:user-scoped")
    manager.register(conn)

    manager.record_presence(conn, True)

    assert manager.is_desktop_foreground("u1") is True


def test_record_presence_false_clears_foreground() -> None:
    """A blur frame (foreground=False) lifts suppression immediately."""
    manager = ConnectionManager()
    conn = _conn("c1", "u1", "user-scoped", "user:u1:user-scoped")
    manager.register(conn)

    manager.record_presence(conn, True)
    manager.record_presence(conn, False)

    assert manager.is_desktop_foreground("u1") is False


def test_foreground_report_goes_stale_after_the_ttl(monkeypatch) -> None:
    """A wedged socket whose blur frame never arrives stops suppressing push
    once its last foreground report ages past the TTL."""
    import shared.websocket.connection_manager as cm

    now = [1000.0]
    monkeypatch.setattr(cm.time, "monotonic", lambda: now[0])

    manager = ConnectionManager()
    conn = _conn("c1", "u1", "user-scoped", "user:u1:user-scoped")
    manager.register(conn)
    manager.record_presence(conn, True)
    assert manager.is_desktop_foreground("u1") is True

    now[0] += cm._FOREGROUND_TTL_SECONDS + 1
    assert manager.is_desktop_foreground("u1") is False


def test_is_desktop_foreground_is_scoped_per_user() -> None:
    manager = ConnectionManager()
    c1 = _conn("c1", "u1", "user-scoped", "user:u1:user-scoped")
    c2 = _conn("c2", "u2", "user-scoped", "user:u2:user-scoped")
    manager.register(c1)
    manager.register(c2)

    manager.record_presence(c1, True)

    assert manager.is_desktop_foreground("u1") is True
    assert manager.is_desktop_foreground("u2") is False


def test_foreground_cleared_when_connection_unregisters() -> None:
    """Dropping the socket (app closed/crashed) removes its foreground vote."""
    manager = ConnectionManager()
    conn = _conn("c1", "u1", "user-scoped", "user:u1:user-scoped")
    manager.register(conn)
    manager.record_presence(conn, True)

    manager.unregister(conn)

    assert manager.is_desktop_foreground("u1") is False


def test_broadcast_ephemeral_reaches_all_connections_of_the_user_only() -> None:
    manager = ConnectionManager()
    web = _conn("c1", "u1", "user-scoped", "user:u1:user-scoped")
    cli = _conn("c2", "u1", "session-scoped", "user:u1:session:i1")
    stranger = _conn("c3", "u2", "user-scoped", "user:u2:user-scoped")
    for conn in (web, cli, stranger):
        manager.register(conn)

    manager.broadcast_ephemeral("u1", {"t": "machine-alive", "machine_id": "m1"})

    frame = {"type": "ephemeral", "body": {"t": "machine-alive", "machine_id": "m1"}}
    assert web.outbox.get_nowait() == frame
    assert cli.outbox.get_nowait() == frame
    assert stranger.outbox.empty()


def test_broadcast_update_delivers_once_to_a_connection_in_two_target_rooms() -> None:
    """A connection in both the session and user-scoped room (§2.3) is deduped."""
    manager = ConnectionManager()
    conn = _conn("c1", "u1", "user-scoped", "user:u1:user-scoped", "user:u1:session:i1")
    manager.register(conn)

    manager.broadcast_update(
        "u1", {"entity": "messages"}, ["user:u1:session:i1", "user:u1:user-scoped"]
    )

    assert conn.outbox.get_nowait() == {
        "type": "update",
        "payload": {"entity": "messages"},
    }
    assert conn.outbox.empty()


def test_broadcast_update_skips_connections_not_in_target_rooms() -> None:
    manager = ConnectionManager()
    target = _conn("c1", "u1", "session-scoped", "user:u1:session:i1")
    bystander = _conn("c2", "u1", "session-scoped", "user:u1:session:i2")
    manager.register(target)
    manager.register(bystander)

    manager.broadcast_update("u1", {"entity": "messages"}, ["user:u1:session:i1"])

    assert not target.outbox.empty()
    assert bystander.outbox.empty()


# --- backpressure / slow-consumer shed (§2.10) -----------------------------


def _bounded_conn(connection_id: str, on_overflow, *, maxsize: int = 2) -> Connection:
    """A Connection with a tight outbox so tests can trip overflow quickly."""
    return Connection(
        connection_id=connection_id,
        user_id="u1",
        scope="user-scoped",
        rooms=frozenset({"user:u1:user-scoped"}),
        on_overflow=on_overflow,
        outbox=asyncio.Queue(maxsize=maxsize),
    )


def test_outbox_overflow_sheds_connection_with_callback_and_metric() -> None:
    """A full outbox flips `overflowed`, increments the counter, fires the callback."""
    manager = ConnectionManager()
    calls = 0

    def on_overflow() -> None:
        nonlocal calls
        calls += 1

    conn = _bounded_conn("c1", on_overflow, maxsize=2)
    manager.register(conn)
    before = connections_closed_slow_count()

    manager.broadcast_update("u1", {"n": 1}, ["user:u1:user-scoped"])
    manager.broadcast_update("u1", {"n": 2}, ["user:u1:user-scoped"])
    assert conn.overflowed is False
    assert calls == 0

    # Third broadcast overflows the maxsize=2 outbox.
    manager.broadcast_update("u1", {"n": 3}, ["user:u1:user-scoped"])

    assert conn.overflowed is True
    assert calls == 1
    assert connections_closed_slow_count() - before == 1


def test_overflow_is_idempotent_on_repeated_broadcasts() -> None:
    """Subsequent broadcasts to a shed connection do not re-fire the callback."""
    manager = ConnectionManager()
    calls = 0

    def on_overflow() -> None:
        nonlocal calls
        calls += 1

    conn = _bounded_conn("c1", on_overflow, maxsize=1)
    manager.register(conn)
    before = connections_closed_slow_count()

    manager.broadcast_update("u1", {"n": 1}, ["user:u1:user-scoped"])
    manager.broadcast_update("u1", {"n": 2}, ["user:u1:user-scoped"])  # overflow
    manager.broadcast_update("u1", {"n": 3}, ["user:u1:user-scoped"])
    manager.broadcast_update("u1", {"n": 4}, ["user:u1:user-scoped"])

    assert calls == 1
    assert connections_closed_slow_count() - before == 1


def test_overflow_callback_exception_does_not_break_broadcaster() -> None:
    """A misbehaving on_overflow must not take the manager down."""
    manager = ConnectionManager()

    def boom() -> None:
        raise RuntimeError("handler bug")

    conn = _bounded_conn("c1", boom, maxsize=1)
    manager.register(conn)

    manager.broadcast_update("u1", {"n": 1}, ["user:u1:user-scoped"])
    # Overflow with a raising callback — must not propagate.
    manager.broadcast_update("u1", {"n": 2}, ["user:u1:user-scoped"])

    assert conn.overflowed is True


def test_connection_without_on_overflow_callback_still_records_metric() -> None:
    """No callback registered (e.g. test/standalone Connection) — counter still fires."""
    manager = ConnectionManager()
    conn = Connection(
        connection_id="c1",
        user_id="u1",
        scope="user-scoped",
        rooms=frozenset({"user:u1:user-scoped"}),
        outbox=asyncio.Queue(maxsize=1),
    )
    manager.register(conn)
    before = connections_closed_slow_count()

    manager.broadcast_update("u1", {"n": 1}, ["user:u1:user-scoped"])
    manager.broadcast_update("u1", {"n": 2}, ["user:u1:user-scoped"])

    assert conn.overflowed is True
    assert connections_closed_slow_count() - before == 1


def test_broadcast_ephemeral_also_sheds_on_overflow() -> None:
    """Ephemeral broadcasts share the same enqueue path and must respect the cap."""
    manager = ConnectionManager()
    conn = _bounded_conn("c1", on_overflow=lambda: None, maxsize=1)
    manager.register(conn)

    manager.broadcast_ephemeral("u1", {"t": "machine-alive"})
    manager.broadcast_ephemeral("u1", {"t": "machine-alive"})  # overflow

    assert conn.overflowed is True


# ---------------------------------------------------------------------------
# close_user (credential revocation, Phase 2b extension)
# ---------------------------------------------------------------------------


def test_close_user_fires_on_revoked_for_each_connection_of_user() -> None:
    """Every WS connection owned by the user gets its on_revoked invoked once.
    Connections belonging to other users are left alone."""
    manager = ConnectionManager()
    calls: list[str] = []

    def _make(connection_id: str, user_id: str) -> Connection:
        return Connection(
            connection_id=connection_id,
            user_id=user_id,
            scope="user-scoped",
            rooms=frozenset({f"user:{user_id}:user-scoped"}),
            on_revoked=lambda cid=connection_id: calls.append(cid),
        )

    c1 = _make("c1", "u1")
    c2 = _make("c2", "u1")
    other = _make("c3", "u2")
    for c in (c1, c2, other):
        manager.register(c)

    closed = manager.close_user("u1")

    assert closed == 2
    assert sorted(calls) == ["c1", "c2"]


def test_close_user_returns_zero_when_user_has_no_connections() -> None:
    """No live connections for the user → no-op, returns 0."""
    manager = ConnectionManager()

    assert manager.close_user("ghost-user") == 0


def test_close_user_handles_missing_callback_defensively() -> None:
    """A connection without `on_revoked` is still counted but does nothing.
    Lets us evolve the close mechanism without breaking older registrations."""
    manager = ConnectionManager()
    conn = Connection(
        connection_id="c1",
        user_id="u1",
        scope="user-scoped",
        rooms=frozenset({"user:u1:user-scoped"}),
        # on_revoked deliberately omitted
    )
    manager.register(conn)

    assert manager.close_user("u1") == 1  # counted, no raise


def test_close_user_swallows_exceptions_from_callback() -> None:
    """A bad on_revoked callback must not take the manager down — log + continue,
    same defensive pattern as on_overflow."""
    manager = ConnectionManager()

    def _bad():
        raise RuntimeError("boom")

    bad = Connection(
        connection_id="bad",
        user_id="u1",
        scope="user-scoped",
        rooms=frozenset({"user:u1:user-scoped"}),
        on_revoked=_bad,
    )
    good_calls: list[str] = []
    good = Connection(
        connection_id="good",
        user_id="u1",
        scope="user-scoped",
        rooms=frozenset({"user:u1:user-scoped"}),
        on_revoked=lambda: good_calls.append("good"),
    )
    manager.register(bad)
    manager.register(good)

    assert manager.close_user("u1") == 2  # both attempted
    assert good_calls == ["good"]  # second callback still ran
