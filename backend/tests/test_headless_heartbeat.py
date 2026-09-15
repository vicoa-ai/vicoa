"""Headless wrappers must heartbeat.

Headless wrappers (ACP, claude_code, codex_native) historically ran no
heartbeat at all — ``agent_instances.last_heartbeat_at`` only moved when the
agent posted a message. That made an idle session awaiting user input look
identical to a dead one, which is fatal for a liveness indicator.

These tests pin the behaviour so it can't silently regress: the runners must
start a heartbeat, and must stop it before the session is finalized.

See integrations/utils/heartbeat.py and
plans/todos/session-liveness-and-resume.md.
"""

from __future__ import annotations

import asyncio

import pytest

from integrations.utils.heartbeat import AsyncSessionHeartbeat, SessionHeartbeat


class _FakeResp:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.text = ""


class _FakeHttpSession:
    def __init__(self, status_code: int = 200) -> None:
        self.calls: list[str] = []
        self._status_code = status_code

    def post(self, url: str, timeout: float | None = None) -> _FakeResp:
        self.calls.append(url)
        return _FakeResp(self._status_code)


class _FakeAsyncClient:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[str] = []
        self._fail = fail

    async def heartbeat_instance(self, agent_instance_id: str) -> dict:
        self.calls.append(agent_instance_id)
        if self._fail:
            raise RuntimeError("network down")
        return {}


# --------------------------------------------------------------------------
# Sync variant (ACP wrappers)
# --------------------------------------------------------------------------


def test_sync_heartbeat_posts_to_the_instance_endpoint():
    http = _FakeHttpSession()
    hb = SessionHeartbeat(
        agent_instance_id="inst-1",
        base_url="https://agents.example/",
        http_session=http,
        interval=5.0,
    )
    assert hb.url == "https://agents.example/api/v1/agents/instances/inst-1/heartbeat"

    hb.start()
    try:
        deadline = 3.0
        waited = 0.0
        while not http.calls and waited < deadline:
            import time

            time.sleep(0.05)
            waited += 0.05
    finally:
        hb.stop()

    assert http.calls, "heartbeat thread never POSTed"
    assert http.calls[0].endswith("/api/v1/agents/instances/inst-1/heartbeat")


def test_sync_heartbeat_stop_is_idempotent_and_start_is_not_reentrant():
    http = _FakeHttpSession()
    hb = SessionHeartbeat("inst-1", "https://x", http, interval=5.0)
    hb.start()
    first = hb._thread
    hb.start()  # must not spawn a second thread
    assert hb._thread is first
    hb.stop()
    hb.stop()  # must not raise


def test_sync_heartbeat_interval_has_a_floor():
    """A pathological interval must not turn into a request storm."""
    hb = SessionHeartbeat("i", "https://x", _FakeHttpSession(), interval=0.001)
    assert hb.interval >= 5.0


# --------------------------------------------------------------------------
# Async variant (claude_code, codex_native)
# --------------------------------------------------------------------------


async def test_async_heartbeat_calls_the_sdk_repeatedly():
    client = _FakeAsyncClient()
    hb = AsyncSessionHeartbeat("inst-2", client, interval=5.0)
    hb.start()
    try:
        for _ in range(60):
            if client.calls:
                break
            await asyncio.sleep(0.05)
    finally:
        await hb.stop()

    assert client.calls == ["inst-2"] or client.calls[0] == "inst-2"


async def test_async_heartbeat_survives_transport_errors():
    """A heartbeat failure must never take down the session it describes."""
    client = _FakeAsyncClient(fail=True)
    hb = AsyncSessionHeartbeat("inst-3", client, interval=5.0)
    hb.start()
    try:
        for _ in range(60):
            if client.calls:
                break
            await asyncio.sleep(0.05)
        # Task is still alive despite the raised error.
        assert hb._task is not None and not hb._task.done()
    finally:
        await hb.stop()


async def test_async_heartbeat_stop_cancels_the_task():
    client = _FakeAsyncClient()
    hb = AsyncSessionHeartbeat("inst-4", client, interval=5.0)
    hb.start()
    task = hb._task
    await hb.stop()
    assert task is not None and task.done()
    assert hb._task is None
    await hb.stop()  # must not raise


async def test_async_heartbeat_start_is_not_reentrant():
    client = _FakeAsyncClient()
    hb = AsyncSessionHeartbeat("inst-5", client, interval=5.0)
    hb.start()
    first = hb._task
    hb.start()
    try:
        assert hb._task is first
    finally:
        await hb.stop()


# --------------------------------------------------------------------------
# Wiring: the runners must actually own a heartbeat
# --------------------------------------------------------------------------


def test_acp_base_starts_and_stops_a_heartbeat():
    """Guards the wiring, not just the helper — an unwired heartbeat is the
    same bug as no heartbeat."""
    import inspect

    from integrations.headless import acp_base

    setup_src = inspect.getsource(acp_base.ACPWrapperBase._setup)
    cleanup_src = inspect.getsource(acp_base.ACPWrapperBase._cleanup)

    assert "_start_heartbeat()" in setup_src
    assert "_heartbeat" in cleanup_src and "stop()" in cleanup_src


@pytest.mark.parametrize(
    "module_name",
    ["integrations.headless.claude_code", "integrations.headless.codex_native"],
)
def test_async_runners_wire_a_heartbeat(module_name: str):
    import importlib
    import inspect

    module = importlib.import_module(module_name)
    src = inspect.getsource(module)
    assert "AsyncSessionHeartbeat(" in src, f"{module_name} never starts a heartbeat"
    assert "_heartbeat.stop()" in src, f"{module_name} never stops its heartbeat"


# --------------------------------------------------------------------------
# Server-driven cadence (servers/presence.py answers `next_interval_seconds`)
# --------------------------------------------------------------------------


def test_next_interval_from_response_reads_and_clamps():
    from integrations.utils.heartbeat import (
        MAX_HEARTBEAT_INTERVAL_SECONDS,
        MIN_HEARTBEAT_INTERVAL_SECONDS,
        next_interval_from_response,
    )

    assert next_interval_from_response({"next_interval_seconds": 120}, 30.0) == 120.0
    # Absent (older server), wrong shape, or non-numeric: the fallback stands.
    assert next_interval_from_response({}, 30.0) == 30.0
    assert next_interval_from_response(None, 30.0) == 30.0
    assert next_interval_from_response({"next_interval_seconds": "x"}, 30.0) == 30.0
    assert next_interval_from_response({"next_interval_seconds": True}, 30.0) == 30.0
    # Clamped both ways so a bad value can neither hammer nor silence.
    assert (
        next_interval_from_response({"next_interval_seconds": 1}, 30.0)
        == MIN_HEARTBEAT_INTERVAL_SECONDS
    )
    assert (
        next_interval_from_response({"next_interval_seconds": 99999}, 30.0)
        == MAX_HEARTBEAT_INTERVAL_SECONDS
    )


async def test_async_heartbeat_honours_the_server_cadence(monkeypatch):
    """The sleep after a tick is what the server asked for, not the default."""
    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def _capture(delay: float) -> None:
        sleeps.append(delay)
        # Let the loop run one full iteration, then park it.
        if len(sleeps) >= 2:
            await real_sleep(3600)
        await real_sleep(0)

    monkeypatch.setattr("integrations.utils.heartbeat.asyncio.sleep", _capture)
    monkeypatch.setattr("integrations.utils.heartbeat.random.uniform", lambda a, b: 0.0)

    class _Client:
        async def heartbeat_instance(self, agent_instance_id: str) -> dict:
            return {"next_interval_seconds": 120}

    hb = AsyncSessionHeartbeat(agent_instance_id="inst-1", vicoa_client=_Client())
    hb.start()
    try:
        for _ in range(50):
            if len(sleeps) >= 2:
                break
            await real_sleep(0.01)
    finally:
        await hb.stop()
    # sleeps[0] is the startup stagger; sleeps[1] follows the first tick.
    assert len(sleeps) >= 2
    assert sleeps[1] == 120.0


def test_sync_heartbeat_honours_the_server_cadence():
    """Same contract for the thread-based loop the ACP runners use."""
    import time

    class _Resp:
        status_code = 200
        text = ""

        def json(self) -> dict:
            return {"next_interval_seconds": 120}

    class _Http:
        def __init__(self) -> None:
            self.calls = 0

        def post(self, url: str, timeout: float | None = None) -> _Resp:
            self.calls += 1
            return _Resp()

    waits: list[float] = []
    hb = SessionHeartbeat(
        agent_instance_id="inst-1",
        base_url="https://agents.example/",
        http_session=_Http(),
        interval=5.0,
    )
    real_wait = hb._stop_event.wait

    def _wait(timeout: float | None = None) -> bool:
        if timeout is not None and timeout > 2.0:
            waits.append(timeout)
            hb._stop_event.set()  # one iteration is enough
        return real_wait(timeout if timeout is not None and timeout <= 2.0 else 0)

    hb._stop_event.wait = _wait  # type: ignore[method-assign]
    hb.start()
    deadline = time.time() + 3.0
    while not waits and time.time() < deadline:
        time.sleep(0.02)
    hb.stop()
    assert waits and 118.0 <= waits[0] <= 122.0
