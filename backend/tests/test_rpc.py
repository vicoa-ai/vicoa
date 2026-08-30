"""Behavioral tests for RPC routing (websocket-migration plan §2.8).

A daemon registers handlers under `(user_id, machine_id, method)`. A client
`call` is routed to the matching daemon as an `rpc-request` carrying a
server-generated `corr_id`; the daemon's `rpc-response` (echoing that
`corr_id`) resolves the awaiting call. The client-chosen `request_id` never
enters a server-wide map — only the `corr_id` does.
"""

import asyncio

import pytest

from shared.websocket.connection_manager import Connection
from shared.websocket.rpc import RpcError, RpcRouter


def _daemon(connection_id: str, user_id: str, machine_id: str) -> Connection:
    return Connection(
        connection_id=connection_id,
        user_id=user_id,
        scope="machine-scoped",
        rooms=frozenset({f"user:{user_id}:machine:{machine_id}"}),
    )


async def test_call_routes_to_registered_daemon_and_returns_its_result() -> None:
    router = RpcRouter()
    daemon = _daemon("d1", "u1", "m1")
    router.register("u1", "m1", "spawn-session", daemon)

    call = asyncio.create_task(
        router.call("u1", "m1", "spawn-session", {"directory": "/code"})
    )
    await asyncio.sleep(0)  # let call() enqueue the rpc-request

    request = daemon.outbox.get_nowait()
    assert request["type"] == "rpc-request"
    assert request["method"] == "spawn-session"
    assert request["params"] == {"directory": "/code"}

    router.resolve(request["corr_id"], {"instance_id": "i9"})

    assert await call == {"instance_id": "i9"}


async def test_call_with_no_registered_daemon_raises_no_handler() -> None:
    router = RpcRouter()

    with pytest.raises(RpcError) as exc:
        await router.call("u1", "m1", "spawn-session", {}, grace=0.01)

    assert exc.value.code == "no_handler"


async def test_call_waits_for_a_daemon_registering_within_the_grace_window() -> None:
    """A daemon reconnecting just after the call starts still gets routed to —
    §2.8's grace window covers a daemon that is briefly offline."""
    router = RpcRouter()
    daemon = _daemon("d1", "u1", "m1")

    async def register_soon() -> None:
        await asyncio.sleep(0.05)
        router.register("u1", "m1", "spawn-session", daemon)

    asyncio.create_task(register_soon())
    call = asyncio.create_task(router.call("u1", "m1", "spawn-session", {}, grace=1.0))
    await asyncio.sleep(0.1)  # daemon has registered; request enqueued

    request = daemon.outbox.get_nowait()
    assert request["type"] == "rpc-request"
    router.resolve(request["corr_id"], {"ok": True})

    assert await call == {"ok": True}


async def test_call_times_out_as_a_typed_rpc_error() -> None:
    router = RpcRouter()
    router.register("u1", "m1", "spawn-session", _daemon("d1", "u1", "m1"))

    with pytest.raises(RpcError) as exc:
        await router.call("u1", "m1", "spawn-session", {}, timeout=0.01)

    assert exc.value.code == "timeout"


async def test_daemon_disconnect_fails_in_flight_calls() -> None:
    router = RpcRouter()
    daemon = _daemon("d1", "u1", "m1")
    router.register("u1", "m1", "spawn-session", daemon)

    call = asyncio.create_task(router.call("u1", "m1", "spawn-session", {}))
    await asyncio.sleep(0)  # let call() register its pending entry

    router.unregister(daemon)

    with pytest.raises(RpcError) as exc:
        await call
    assert exc.value.code == "target_disconnected"


async def test_call_after_daemon_disconnect_raises_no_handler() -> None:
    router = RpcRouter()
    daemon = _daemon("d1", "u1", "m1")
    router.register("u1", "m1", "spawn-session", daemon)
    router.unregister(daemon)

    with pytest.raises(RpcError) as exc:
        await router.call("u1", "m1", "spawn-session", {}, grace=0.01)
    assert exc.value.code == "no_handler"


async def test_routing_key_isolates_other_users_and_machines() -> None:
    """The (user_id, machine_id, method) key is the cross-user isolation; a
    caller targeting a daemon they do not own simply finds no handler."""
    router = RpcRouter()
    router.register("u1", "m1", "spawn-session", _daemon("d1", "u1", "m1"))

    for user_id, machine_id in (("u2", "m1"), ("u1", "m2")):
        with pytest.raises(RpcError) as exc:
            await router.call(user_id, machine_id, "spawn-session", {}, grace=0.01)
        assert exc.value.code == "no_handler"


async def test_resolve_with_unknown_corr_id_is_a_safe_no_op() -> None:
    """A late or duplicate rpc-response after the call already settled."""
    RpcRouter().resolve("never-issued", {"stale": True})


async def test_concurrent_calls_resolve_independently_by_corr_id() -> None:
    router = RpcRouter()
    daemon = _daemon("d1", "u1", "m1")
    router.register("u1", "m1", "spawn-session", daemon)

    first = asyncio.create_task(router.call("u1", "m1", "spawn-session", {"n": 1}))
    second = asyncio.create_task(router.call("u1", "m1", "spawn-session", {"n": 2}))
    await asyncio.sleep(0)

    req_a = daemon.outbox.get_nowait()
    req_b = daemon.outbox.get_nowait()
    assert req_a["corr_id"] != req_b["corr_id"]

    # resolve out of call order — correlation is by corr_id, not arrival
    router.resolve(req_b["corr_id"], {"for": req_b["params"]["n"]})
    router.resolve(req_a["corr_id"], {"for": req_a["params"]["n"]})

    assert await first == {"for": 1}
    assert await second == {"for": 2}
