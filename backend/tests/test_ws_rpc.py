"""Behavioral tests for the `/ws` RPC frame dispatch (websocket-migration §2.8).

The `RpcRouter` core is covered by `test_rpc.py`; these cover the endpoint
glue — `handle_rpc_call` turning a client `rpc-call` into a routed request and
an `rpc-result` / `rpc-error` frame on the caller's outbox.
"""

import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from shared.websocket.connection_manager import Connection
from shared.websocket.rpc import rpc_router
from servers.api.models import MachineRpcRequest
from servers.api.routers import machine_rpc_endpoint
from servers.api.ws_handler import handle_rpc_call


def _conn(scope: str, user_id: str, machine_id: str | None = None) -> Connection:
    return Connection(
        connection_id=uuid4().hex,
        user_id=user_id,
        scope=scope,
        rooms=frozenset(),
        machine_id=machine_id,
    )


async def test_rpc_call_routes_to_daemon_and_returns_rpc_result() -> None:
    caller = _conn("user-scoped", "u1")
    daemon = _conn("machine-scoped", "u1", "m1")
    rpc_router.register("u1", "m1", "spawn-session", daemon)
    try:
        task = asyncio.create_task(
            handle_rpc_call(
                caller,
                {
                    "type": "rpc-call",
                    "request_id": "r1",
                    "machine_id": "m1",
                    "method": "spawn-session",
                    "params": {"directory": "/code"},
                },
            )
        )
        await asyncio.sleep(0)  # let handle_rpc_call enqueue the rpc-request

        request = daemon.outbox.get_nowait()
        assert request["type"] == "rpc-request"
        assert request["params"] == {"directory": "/code"}
        rpc_router.resolve(request["corr_id"], {"agent_instance_id": "i1"})
        await task

        assert caller.outbox.get_nowait() == {
            "type": "rpc-result",
            "request_id": "r1",
            "result": {"agent_instance_id": "i1"},
        }
    finally:
        rpc_router.unregister(daemon)


async def test_rpc_call_returns_rpc_error_when_the_daemon_disconnects() -> None:
    caller = _conn("user-scoped", "u1")
    daemon = _conn("machine-scoped", "u1", "m1")
    rpc_router.register("u1", "m1", "spawn-session", daemon)

    task = asyncio.create_task(
        handle_rpc_call(
            caller,
            {
                "type": "rpc-call",
                "request_id": "r2",
                "machine_id": "m1",
                "method": "spawn-session",
                "params": {},
            },
        )
    )
    await asyncio.sleep(0)  # in-flight call registered
    rpc_router.unregister(daemon)  # daemon drops mid-call
    await task

    assert caller.outbox.get_nowait() == {
        "type": "rpc-error",
        "request_id": "r2",
        "code": "target_disconnected",
    }


async def test_rest_rpc_fallback_returns_the_daemon_result() -> None:
    daemon = _conn("machine-scoped", "u1", "m1")
    rpc_router.register("u1", "m1", "spawn-session", daemon)
    try:
        call = asyncio.create_task(
            machine_rpc_endpoint(
                "m1", MachineRpcRequest(method="spawn-session", params={}), "u1"
            )
        )
        await asyncio.sleep(0)
        request = daemon.outbox.get_nowait()
        rpc_router.resolve(request["corr_id"], {"agent_instance_id": "i7"})

        assert await call == {"result": {"agent_instance_id": "i7"}}
    finally:
        rpc_router.unregister(daemon)


async def test_rest_rpc_fallback_maps_rpc_error_to_an_http_status() -> None:
    daemon = _conn("machine-scoped", "u1", "m1")
    rpc_router.register("u1", "m1", "spawn-session", daemon)

    call = asyncio.create_task(
        machine_rpc_endpoint(
            "m1", MachineRpcRequest(method="spawn-session", params={}), "u1"
        )
    )
    await asyncio.sleep(0)
    rpc_router.unregister(daemon)  # daemon drops mid-call

    with pytest.raises(HTTPException) as exc:
        await call
    assert exc.value.status_code == 503
    assert exc.value.detail == "target_disconnected"
