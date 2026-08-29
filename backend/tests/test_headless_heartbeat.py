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
