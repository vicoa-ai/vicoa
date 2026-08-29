"""Behavioral tests for hello/scope resolution (websocket-migration §2.3, §2.9).

A connection's first frame is a `hello` declaring its scope. `resolve_hello`
validates the frame's structure and the scope/token-type rule, and computes the
single room the connection joins. It does NOT do the DB ownership check — that
is the endpoint's job — so this logic stays pure and unit-testable.
"""

import pytest

from shared.websocket.protocol import WsProtocolError, resolve_hello, terminal_room


def test_machine_scoped_hello_resolves_to_the_machine_room() -> None:
    resolved = resolve_hello(
        {"type": "hello", "scope": "machine-scoped", "machine_id": "m1"},
        user_id="u1",
        token_type="vicoa-key",
    )

    assert resolved.scope == "machine-scoped"
    assert resolved.room == "user:u1:machine:m1"
    assert resolved.machine_id == "m1"
    assert resolved.instance_id is None


def test_session_scoped_hello_resolves_to_the_session_room() -> None:
    resolved = resolve_hello(
        {"type": "hello", "scope": "session-scoped", "instance_id": "i1"},
        user_id="u1",
        token_type="vicoa-key",
    )

    assert resolved.scope == "session-scoped"
    assert resolved.room == "user:u1:session:i1"
    assert resolved.instance_id == "i1"
    assert resolved.machine_id is None


def test_user_scoped_hello_resolves_to_the_user_room() -> None:
    resolved = resolve_hello(
        {"type": "hello", "scope": "user-scoped"},
        user_id="u1",
        token_type="vicoa-supabase",
    )

    assert resolved.scope == "user-scoped"
    assert resolved.room == "user:u1:user-scoped"
    assert resolved.instance_id is None
    assert resolved.machine_id is None


def test_user_scoped_hello_rejects_an_agent_token() -> None:
    """An agent (vicoa-key) token must not be able to claim user-scoped (§2.9)."""
    with pytest.raises(WsProtocolError, match="agent"):
        resolve_hello(
            {"type": "hello", "scope": "user-scoped"},
            user_id="u1",
            token_type="vicoa-key",
        )


def test_terminal_scoped_hello_resolves_to_the_terminal_room() -> None:
    resolved = resolve_hello(
        {"type": "hello", "scope": "terminal-scoped", "machine_id": "m1"},
        user_id="u1",
        token_type="vicoa-supabase",
    )

    assert resolved.scope == "terminal-scoped"
    assert resolved.room == terminal_room("u1", "m1")
    assert resolved.room == "user:u1:machine:m1:terminals"
    assert resolved.machine_id == "m1"
    assert resolved.instance_id is None


def test_terminal_scoped_hello_without_machine_id_is_rejected() -> None:
    with pytest.raises(WsProtocolError, match="machine_id"):
        resolve_hello(
            {"type": "hello", "scope": "terminal-scoped"},
            user_id="u1",
            token_type="vicoa-supabase",
        )


def test_terminal_scoped_hello_rejects_an_agent_token() -> None:
    """Only user-facing clients stream terminals; an agent token cannot."""
    with pytest.raises(WsProtocolError, match="terminal-scoped"):
        resolve_hello(
            {"type": "hello", "scope": "terminal-scoped", "machine_id": "m1"},
            user_id="u1",
            token_type="vicoa-key",
        )


def test_terminal_room_differs_from_the_daemon_machine_room() -> None:
    """The client's terminal room must not collide with the daemon's own
    machine room, or the daemon would receive its own pty-output echoes."""
    daemon_room = resolve_hello(
        {"type": "hello", "scope": "machine-scoped", "machine_id": "m1"},
        user_id="u1",
        token_type="vicoa-key",
    ).room
    assert terminal_room("u1", "m1") != daemon_room


def test_session_scoped_hello_without_instance_id_is_rejected() -> None:
    with pytest.raises(WsProtocolError, match="instance_id"):
        resolve_hello(
            {"type": "hello", "scope": "session-scoped"},
            user_id="u1",
            token_type="vicoa-key",
        )


def test_machine_scoped_hello_without_machine_id_is_rejected() -> None:
    with pytest.raises(WsProtocolError, match="machine_id"):
        resolve_hello(
            {"type": "hello", "scope": "machine-scoped"},
            user_id="u1",
            token_type="vicoa-key",
        )


def test_unknown_scope_is_rejected() -> None:
    with pytest.raises(WsProtocolError, match="scope"):
        resolve_hello(
            {"type": "hello", "scope": "global"},
            user_id="u1",
            token_type="vicoa-key",
        )


def test_first_frame_must_be_a_hello() -> None:
    with pytest.raises(WsProtocolError, match="hello"):
        resolve_hello(
            {"type": "fetch_messages_request", "scope": "user-scoped"},
            user_id="u1",
            token_type="vicoa-supabase",
        )
