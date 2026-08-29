"""WebSocket realtime infrastructure (websocket-migration plan §2).

Public re-exports for the realtime transport.
"""

from .connection_manager import Connection, ConnectionManager
from .envelope import (
    build_ephemeral,
    build_instance_created_update,
    build_instance_update,
    build_machine_update,
    build_message_update,
    build_new_message_update,
    build_spawn_request_update,
)
from .in_tx import after_commit
from .protocol import ResolvedHello, WsProtocolError, resolve_hello
from .rpc import RpcError, RpcRouter

__all__ = [
    "Connection",
    "ConnectionManager",
    "ResolvedHello",
    "RpcError",
    "RpcRouter",
    "WsProtocolError",
    "after_commit",
    "build_ephemeral",
    "build_instance_created_update",
    "build_instance_update",
    "build_machine_update",
    "build_message_update",
    "build_new_message_update",
    "build_spawn_request_update",
    "resolve_hello",
]
