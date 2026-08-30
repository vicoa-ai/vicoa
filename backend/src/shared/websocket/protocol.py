"""WebSocket hello/scope resolution (websocket-migration plan §2.3, §2.9).

A connection's first frame is a `hello` that declares its scope. `resolve_hello`
validates the frame and computes the single room (§2.3) the connection joins.

It performs the structural and token-type checks only — not the DB ownership
check (§2.9), which the endpoint runs separately — so this stays pure and
unit-testable.
"""

from dataclasses import dataclass

from ..auth.ws import TokenType


class WsProtocolError(Exception):
    """The hello frame is malformed or not allowed for its credentials."""


def terminal_room(user_id: str, machine_id: str) -> str:
    """Room carrying a machine's streamed terminal output to viewing clients.

    Distinct from the daemon's own `user:{uid}:machine:{mid}` room so a daemon
    never receives its own `pty-output` echoes; the client subscribes here
    (terminal-scoped) and the daemon's frames are fanned in by the ws handler.
    """
    return f"user:{user_id}:machine:{machine_id}:terminals"


@dataclass(slots=True)
class ResolvedHello:
    """The validated scope of a connection and the room it joins."""

    scope: str
    room: str
    instance_id: str | None
    machine_id: str | None


def resolve_hello(hello: dict, *, user_id: str, token_type: TokenType) -> ResolvedHello:
    """Validate a hello frame and resolve the connection's scope and room."""
    if hello.get("type") != "hello":
        raise WsProtocolError("the first frame must be a hello frame")

    scope = hello.get("scope")

    if scope == "machine-scoped":
        machine_id = hello.get("machine_id")
        if not machine_id:
            raise WsProtocolError("machine-scoped hello requires a machine_id")
        return ResolvedHello(
            scope=scope,
            room=f"user:{user_id}:machine:{machine_id}",
            instance_id=None,
            machine_id=machine_id,
        )

    if scope == "terminal-scoped":
        # A user-facing client (web/desktop) streaming a remote machine's
        # terminal output. Supabase-only: agents/daemons never subscribe to
        # terminals. Cross-user isolation comes from the `user:{uid}:…` room
        # prefix (the uid is from the caller's own token), so — like
        # user-scoped — no separate DB ownership check is needed: a machine_id
        # the caller doesn't own simply has no daemon fanning into its room.
        machine_id = hello.get("machine_id")
        if not machine_id:
            raise WsProtocolError("terminal-scoped hello requires a machine_id")
        if token_type != "vicoa-supabase":
            raise WsProtocolError(
                "terminal-scoped requires a Supabase token; an agent token "
                "cannot claim terminal-scoped"
            )
        return ResolvedHello(
            scope=scope,
            room=terminal_room(user_id, machine_id),
            instance_id=None,
            machine_id=machine_id,
        )

    if scope == "session-scoped":
        instance_id = hello.get("instance_id")
        if not instance_id:
            raise WsProtocolError("session-scoped hello requires an instance_id")
        return ResolvedHello(
            scope=scope,
            room=f"user:{user_id}:session:{instance_id}",
            instance_id=instance_id,
            machine_id=None,
        )

    if scope == "user-scoped":
        if token_type != "vicoa-supabase":
            raise WsProtocolError(
                "user-scoped requires a Supabase token; an agent token cannot "
                "claim user-scoped"
            )
        return ResolvedHello(
            scope=scope,
            room=f"user:{user_id}:user-scoped",
            instance_id=None,
            machine_id=None,
        )

    raise WsProtocolError(f"unknown hello scope: {scope!r}")
