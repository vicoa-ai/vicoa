"""Prewarm (standby) for the Pi-family runner: see vicoa.standby.

A standby brings the agent up before the session exists, so until the go line
arrives it must not write anything to the server. These tests drive the runner
and the session against fakes: a fake transport for the agent, a fake client
for vicoa-server, and a patched ``read_go_async`` for the daemon's go line.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import pytest

from integrations.headless import pi_native
from integrations.headless.pi_family import runner as runner_mod
from integrations.headless.pi_family.protocol import ReadyGate
from integrations.headless.pi_family.runner import PiFamilyRunner
from integrations.headless.pi_family.session import PiRuntimeSession
from integrations.headless.pi_family.spec import PI_FAMILY_AGENTS


class FakeTransport:
    """Answers agent requests from a canned map; a test can push events in."""

    def __init__(self, responses: Optional[dict] = None) -> None:
        self.responses = responses or {}
        self.requests: list[tuple[str, dict]] = []
        self.sends: list[tuple[str, dict]] = []
        self.on_event: Any = None
        self.on_close: Any = None
        self.is_closed = False
        self.last_activity = 0.0
        self.closed_by_us = False

    async def start(self) -> None:
        pass

    async def aclose(self) -> None:
        self.is_closed = True
        self.closed_by_us = True

    async def request(self, command, params=None, *, timeout=None):
        self.requests.append((command, params or {}))
        return self.responses.get(command, {})

    def send(self, command, params=None) -> None:
        self.sends.append((command, params or {}))

    async def emit(self, frame: dict) -> None:
        assert self.on_event is not None
        await self.on_event(frame)


class FakeSubprocess:
    def __init__(self, transport: FakeTransport) -> None:
        self.transport = transport
        self.closed = False

    def stderr_tail(self) -> str:
        return ""

    async def aclose(self) -> None:
        self.closed = True


class FakeClient:
    """Records every server call, in order, as ``(name, payload)``."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.post_gate: Optional[asyncio.Event] = None
        self._next_id = 0

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    async def register_agent_instance(self, **kwargs):
        self.calls.append(("register", kwargs))
        return {"agent_instance_id": kwargs["agent_instance_id"]}

    async def update_agent_instance_status(self, _instance_id, status):
        self.calls.append(("status", status))

    async def patch_agent_instance(self, _instance_id, **kwargs):
        self.calls.append(("patch", kwargs))

    async def sync_commands(self, **kwargs):
        self.calls.append(("sync_commands", kwargs))

    async def send_message(self, **kwargs):
        self.calls.append(("agent_message", kwargs.get("content")))
        return type("R", (), {"message_id": "a1"})()

    async def send_user_message(self, **kwargs):
        if self.post_gate is not None:
            await self.post_gate.wait()
        self._next_id += 1
        message_id = f"u{self._next_id}"
        self.calls.append(("user_message", (kwargs.get("content"), message_id)))
        return {"message_id": message_id}

    async def mark_message_consumed(self, message_id, steered=False):
        self.calls.append(("consumed", message_id))

    async def end_session(self, session_id):
        self.calls.append(("end_session", session_id))

    async def close(self):
        pass


class FakeHeartbeat:
    def __init__(self, **_kwargs) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        pass


GET_STATE = {"sessionId": "pi-sess-1", "model": {"provider": "anthropic", "id": "m"}}
MODELS = {"models": [{"provider": "anthropic", "id": "m", "name": "M"}]}


def make_runner(prompt: Optional[str] = None, **kwargs) -> PiFamilyRunner:
    spec = PI_FAMILY_AGENTS["pi"]
    return PiFamilyRunner(
        spec=spec,
        vicoa_api_key="key",
        vicoa_base_url="https://agents.example",
        session_id="sess-1",
        cwd="/work/repo",
        agent_name=spec.display_name,
        agent_command="/usr/local/bin/pi",
        initial_prompt=prompt,
        **kwargs,
    )


class Harness:
    """A runner wired to fakes, with the go line under the test's control."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, standby: bool = True):
        self.client = FakeClient()
        self.transports: list[FakeTransport] = []
        self.subprocesses: list[FakeSubprocess] = []
        self.go: "asyncio.Future[Optional[dict]]" = (
            asyncio.get_running_loop().create_future()
        )
        self.go_requested = asyncio.Event()
        self.registered_marks: list[str] = []
        self.prompts: list[str] = []
        self.ws_started = False

        async def fake_spawn(**_kwargs):
            transport = FakeTransport(
                {"get_state": GET_STATE, "get_available_models": MODELS}
            )
            original_request = transport.request

            async def request(command, params=None, *, timeout=None):
                if command == "prompt":
                    self.prompts.append((params or {}).get("message", ""))
                return await original_request(command, params, timeout=timeout)

            transport.request = request  # type: ignore[method-assign]
            subprocess = FakeSubprocess(transport)
            self.transports.append(transport)
            self.subprocesses.append(subprocess)
            return subprocess

        async def fake_read_go(timeout=None):
            self.go_requested.set()
            return await self.go

        async def fake_handshake(*_args, **_kwargs):
            return None

        monkeypatch.setattr(runner_mod, "spawn_pi_agent", fake_spawn)
        monkeypatch.setattr(runner_mod, "read_go_async", fake_read_go)
        monkeypatch.setattr(runner_mod, "standby_requested", lambda: standby)
        monkeypatch.setattr(runner_mod, "AsyncVicoaClient", lambda **_: self.client)
        monkeypatch.setattr(runner_mod, "AsyncSessionHeartbeat", FakeHeartbeat)
        monkeypatch.setattr(
            runner_mod, "mark_session_registered", self.registered_marks.append
        )
        monkeypatch.setattr(runner_mod, "clear_session_registered", lambda _id: None)
        monkeypatch.setattr(
            "integrations.headless.pi_family.session.perform_handshake",
            fake_handshake,
        )
        monkeypatch.setattr(
            PiFamilyRunner,
            "_start_ws_client",
            lambda runner: setattr(self, "ws_started", True),
        )

    async def start(self, runner: PiFamilyRunner) -> "asyncio.Task[int]":
        self.runner = runner
        task = asyncio.create_task(runner.run())
        await asyncio.wait_for(self.go_requested.wait(), timeout=2.0)
        return task

    async def wait_for(self, predicate, timeout: float = 2.0) -> None:
        async def poll():
            while not predicate():
                await asyncio.sleep(0.01)

        await asyncio.wait_for(poll(), timeout=timeout)

    async def stop(self, task: "asyncio.Task[int]") -> int:
        """Stop the runner the way its SIGTERM handler does."""
        self.runner.running = False
        task.cancel()
        return await asyncio.wait_for(task, timeout=5.0)


async def settle_turn(transport: FakeTransport) -> None:
    await transport.emit({"type": "agent_start"})
    await transport.emit({"type": "agent_settled"})


def test_the_entry_module_opts_into_standby():
    """cli.py checks the attribute on the module it imports."""
    assert pi_native.SUPPORTS_ENGINE_STANDBY is True


async def test_nothing_reaches_the_server_before_the_go(monkeypatch):
    harness = Harness(monkeypatch)
    task = await harness.start(make_runner())
    transport = harness.transports[0]

    # The agent is up: handshake done and get_state read.
    assert ("get_state", {}) in transport.requests
    # Agent events arriving while prewarmed are held, not posted.
    await transport.emit({"type": "available_commands_update", "commands": []})
    await transport.emit({"type": "model_changed"})
    await asyncio.sleep(0.05)

    assert harness.client.calls == []
    assert harness.registered_marks == []
    assert harness.ws_started is False

    harness.go.set_result(None)
    assert await asyncio.wait_for(task, timeout=5.0) == 0


async def test_a_discarded_standby_exits_without_registering(monkeypatch):
    harness = Harness(monkeypatch)
    task = await harness.start(make_runner())
    harness.go.set_result(None)

    assert await asyncio.wait_for(task, timeout=5.0) == 0
    assert harness.client.calls == []
    assert harness.registered_marks == []
    assert harness.subprocesses[0].closed is True
    assert harness.transports[0].closed_by_us is True


async def test_an_adopted_standby_registers_then_runs_the_prompt_as_turn_one(
    monkeypatch,
):
    harness = Harness(monkeypatch)
    task = await harness.start(make_runner())
    harness.go.set_result({"prompt": "fix the bug"})

    await harness.wait_for(lambda: harness.prompts == ["fix the bug"])
    names = harness.client.names()
    assert names[0] == "register"
    assert harness.registered_marks == ["sess-1"]
    assert harness.ws_started is True
    # Only one turn, run locally; the prompt is shown in chat by the POST.
    await harness.wait_for(lambda: "user_message" in harness.client.names())
    assert len(harness.transports) == 1

    await settle_turn(harness.transports[0])
    assert await harness.stop(task) == 0
    assert "end_session" in harness.client.names()


async def test_the_turn_sets_its_own_status_after_a_prompt_bearing_go(monkeypatch):
    """No AWAITING_INPUT from bring-up: landing after the turn's ACTIVE it
    would show the session idle while the agent works."""
    harness = Harness(monkeypatch)
    task = await harness.start(make_runner())
    harness.go.set_result({"prompt": "hello"})
    await harness.wait_for(lambda: harness.prompts == ["hello"])

    statuses = [p for n, p in harness.client.calls if n == "status"]
    assert statuses == ["ACTIVE"]
    await settle_turn(harness.transports[0])
    await harness.stop(task)


async def test_a_prompt_less_go_reports_awaiting_input(monkeypatch):
    harness = Harness(monkeypatch)
    task = await harness.start(make_runner())
    harness.go.set_result({"prompt": None})
    await harness.wait_for(lambda: ("status", "AWAITING_INPUT") in harness.client.calls)

    assert harness.prompts == []
    assert "user_message" not in harness.client.names()
    await harness.stop(task)


async def test_deferred_start_up_writes_go_out_after_registration(monkeypatch):
    harness = Harness(monkeypatch)
    task = await harness.start(make_runner())
    harness.go.set_result({"prompt": None})

    def patched(key: str) -> bool:
        return any(n == "patch" and key in str(p) for n, p in harness.client.calls)

    await harness.wait_for(lambda: patched("pi_session_id") and patched("available"))
    names = harness.client.names()
    register_at = names.index("register")
    patch_calls = [
        (i, p) for i, (n, p) in enumerate(harness.client.calls) if n == "patch"
    ]
    assert all(i > register_at for i, _ in patch_calls)
    assert {"instance_metadata": {"pi_session_id": "pi-sess-1"}} in [
        p for _, p in patch_calls
    ]
    await harness.stop(task)


async def test_events_held_while_prewarmed_are_replayed_after_adoption(monkeypatch):
    harness = Harness(monkeypatch)
    task = await harness.start(make_runner())
    commands = [{"name": "review", "description": "Review"}]
    await harness.transports[0].emit(
        {"type": "available_commands_update", "commands": commands}
    )
    assert harness.client.calls == []

    harness.go.set_result({"prompt": None})
    await harness.wait_for(lambda: "sync_commands" in harness.client.names())
    assert harness.client.names().index("sync_commands") > harness.client.names().index(
        "register"
    )
    await harness.stop(task)


async def test_the_echo_of_the_adopted_prompt_is_dropped_by_id(monkeypatch):
    harness = Harness(monkeypatch)
    runner = make_runner()
    task = await harness.start(runner)
    harness.go.set_result({"prompt": "same words"})
    await harness.wait_for(lambda: runner._adopted_prompt_message_id is not None)
    echo_id = runner._adopted_prompt_message_id
    await settle_turn(harness.transports[0])
    await harness.wait_for(
        lambda: runner.session is not None and not runner.session.turn_active
    )

    # The live broadcast, then a catch-up replay of the same row: both dropped.
    await runner._route("same words", (), echo_id)
    await runner._route("same words", (), echo_id)
    await asyncio.sleep(0.05)
    assert harness.prompts == ["same words"]

    # The user sending the same text again is a new row and runs.
    await runner._route("same words", (), "u-later")
    await harness.wait_for(lambda: harness.prompts == ["same words", "same words"])
    await settle_turn(harness.transports[0])
    await harness.stop(task)


async def test_an_echo_racing_the_post_waits_for_its_id(monkeypatch):
    """The broadcast can beat the POST's own response; it is still dropped."""
    harness = Harness(monkeypatch)
    harness.client.post_gate = asyncio.Event()
    runner = make_runner()
    task = await harness.start(runner)
    harness.go.set_result({"prompt": "racy"})
    await harness.wait_for(lambda: harness.prompts == ["racy"])

    route = asyncio.create_task(runner._route("racy", (), "u1"))
    await asyncio.sleep(0.05)
    assert not route.done()  # waiting for the in-flight POST's id
    harness.client.post_gate.set()
    await asyncio.wait_for(route, timeout=2.0)
    await asyncio.sleep(0.05)
    assert harness.prompts == ["racy"]

    await settle_turn(harness.transports[0])
    await harness.stop(task)


async def test_agent_messages_wait_for_the_prompt_post(monkeypatch):
    harness = Harness(monkeypatch)
    harness.client.post_gate = asyncio.Event()
    task = await harness.start(make_runner())
    harness.go.set_result({"prompt": "go"})
    await harness.wait_for(lambda: harness.prompts == ["go"])

    session = harness.runner.session
    assert session is not None
    post = asyncio.create_task(session._post("the reply"))
    await asyncio.sleep(0.05)
    assert "agent_message" not in harness.client.names()

    harness.client.post_gate.set()
    await asyncio.wait_for(post, timeout=2.0)
    names = harness.client.names()
    assert names.index("user_message") < names.index("agent_message")

    await settle_turn(harness.transports[0])
    await harness.stop(task)


async def test_an_agent_that_died_while_prewarmed_is_started_again(monkeypatch):
    harness = Harness(monkeypatch)
    task = await harness.start(make_runner())
    first = harness.transports[0]
    assert first.on_close is not None
    first.is_closed = True
    first.on_close("pi exited")
    await asyncio.sleep(0.05)
    # The reason is kept, not posted: there is no row yet.
    assert harness.client.calls == []

    harness.go.set_result({"prompt": "still works"})
    await harness.wait_for(lambda: harness.prompts == ["still works"])
    assert len(harness.transports) == 2
    assert harness.subprocesses[0].closed is True

    await settle_turn(harness.transports[1])
    await harness.stop(task)


async def test_a_resume_never_waits_for_a_go(monkeypatch):
    harness = Harness(monkeypatch)
    runner = make_runner(is_resuming=True)
    harness.runner = runner
    task = asyncio.create_task(runner.run())
    await harness.wait_for(lambda: harness.ws_started)

    assert not harness.go_requested.is_set()
    assert "register" not in harness.client.names()
    assert harness.client.calls[0] == ("status", "AWAITING_INPUT")
    await harness.stop(task)


async def test_a_cold_start_is_unchanged(monkeypatch):
    harness = Harness(monkeypatch, standby=False)
    runner = make_runner(prompt="cold prompt")
    harness.runner = runner
    task = asyncio.create_task(runner.run())
    await harness.wait_for(lambda: "user_message" in harness.client.names())

    assert not harness.go_requested.is_set()
    names = harness.client.names()
    assert names[0] == "register"
    # Session id persisted inline before the session reports itself idle.
    assert names[1:3] == ["patch", "status"]
    # Cold: the prompt runs only via the server echo, not locally.
    assert harness.prompts == []
    await harness.stop(task)


# ---------------------------------------------------------------------------
# Session-level: start(report=False) and report_started
# ---------------------------------------------------------------------------


def make_session() -> tuple[PiRuntimeSession, FakeTransport, FakeClient]:
    transport = FakeTransport({"get_state": GET_STATE, "get_available_models": MODELS})
    client = FakeClient()
    gate = ReadyGate()
    gate.offer(
        {
            "type": "ready",
            "protocolVersion": 1,
            "supportedProtocolVersions": [1, 2],
            "maxFrameBytes": 1048576,
            "maxReassembledFrameBytes": 67108864,
        }
    )
    session = PiRuntimeSession(
        vicoa_client=client,
        instance_id="s1",
        cwd="/tmp",
        transport=transport,  # type: ignore[arg-type]
        spec=PI_FAMILY_AGENTS["omp"],
        ready_gate=gate,
        agent_type="Oh My Pi",
    )
    return session, transport, client


async def test_a_held_start_keeps_the_session_id_for_later():
    session, transport, client = make_session()
    try:
        await session.start(report=False)
        assert session.agent_session_id == "pi-sess-1"
        assert client.calls == []

        await session.report_started(set_status=False)
        await session._after_startup_reports()
        assert client.calls[0] == (
            "patch",
            {"instance_metadata": {"pi_session_id": "pi-sess-1"}},
        )
        assert "status" not in client.names()
    finally:
        await session.aclose()


async def test_a_host_tool_call_is_answered_while_prewarmed():
    """Host-tool frames talk only to the agent, so they never wait."""
    session, transport, client = make_session()

    class Router:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def register(self, _request) -> None:
            pass

        def handle_call(self, frame) -> None:
            self.calls.append(frame)

        def handle_cancel(self, frame) -> None:
            pass

        async def aclose(self) -> None:
            pass

    router = Router()
    try:
        await session.start(host_tools=router, report=False)  # type: ignore[arg-type]
        await transport.emit({"type": "host_tool_call", "id": "t1"})
        assert router.calls == [{"type": "host_tool_call", "id": "t1"}]
        assert client.calls == []
    finally:
        await session.aclose()
