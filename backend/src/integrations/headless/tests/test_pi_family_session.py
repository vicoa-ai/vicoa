"""Turn lifecycle and status handling for :class:`PiRuntimeSession`.

Built against a fake transport so the tests describe the *protocol* semantics —
in particular the three ways a turn can end — without a subprocess.
"""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from integrations.headless.pi_family.protocol import ReadyGate
from integrations.headless.pi_family.session import PiRuntimeSession
from integrations.headless.pi_family.spec import PI_FAMILY_AGENTS


class FakeTransport:
    """Answers requests from a canned map and lets a test push events in."""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.requests: list[tuple[str, dict]] = []
        self.sends: list[tuple[str, dict]] = []
        self.on_event = None
        self.on_close = None
        self.is_closed = False
        self.last_activity = 0.0
        self.started = False

    async def start(self):
        self.started = True

    async def aclose(self):
        self.is_closed = True

    async def request(self, command, params=None, *, timeout=None):
        self.requests.append((command, params or {}))
        return self.responses.get(command, {})

    def send(self, command, params=None):
        self.sends.append((command, params or {}))

    async def emit(self, frame):
        assert self.on_event is not None
        await self.on_event(frame)


class FakeClient:
    def __init__(self):
        self.rows: list[tuple[str, dict]] = []
        self.statuses: list[str] = []
        self.patches: list[dict] = []
        self.commands: list[dict] = []

    async def send_message(self, **kwargs):
        self.rows.append(
            (kwargs.get("content", ""), kwargs.get("message_metadata") or {})
        )
        return type("R", (), {"message_id": "m1"})()

    async def update_agent_instance_status(self, _instance_id, status):
        self.statuses.append(status)

    async def patch_agent_instance(self, _instance_id, **kwargs):
        self.patches.append(kwargs)

    async def sync_commands(self, **kwargs):
        self.commands.append(kwargs)


#: Sessions created by ``make_session``, closed after each test. ``start``
#: launches a status watchdog that would otherwise outlive its event loop and
#: print "Task was destroyed but it is pending".
_OPEN_SESSIONS: list[PiRuntimeSession] = []


@pytest.fixture(autouse=True)
async def _close_sessions():
    yield
    for session in _OPEN_SESSIONS:
        await session.aclose()
    _OPEN_SESSIONS.clear()


def make_session(agent="omp", responses=None, **kwargs):
    transport = FakeTransport(responses)
    client = FakeClient()
    ready_gate = ReadyGate()
    # omp announces itself with an unsolicited ``ready`` frame before anything
    # else, and bring-up waits for it. Latch it up front so these tests
    # exercise the handshake's *outcome* rather than its 60s timeout.
    ready_gate.offer(
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
        transport=transport,
        spec=PI_FAMILY_AGENTS[agent],
        ready_gate=ready_gate,
        agent_type=PI_FAMILY_AGENTS[agent].display_name,
        **kwargs,
    )
    _OPEN_SESSIONS.append(session)
    return session, transport, client


async def drive_prompt(session, transport, frames, timeout=2.0):
    """Send a prompt, replay ``frames``, and wait for the turn to settle."""
    task = asyncio.create_task(session.prompt("go"))
    await asyncio.sleep(0)
    for frame in frames:
        await transport.emit(frame)
    await asyncio.wait_for(task, timeout=timeout)


async def test_omp_settles_on_a_terminal_agent_end():
    session, transport, client = make_session("omp")
    await drive_prompt(
        session,
        transport,
        [
            {"type": "agent_start"},
            {"type": "turn_start"},
            {"type": "turn_end"},
            {"type": "agent_end", "isTerminal": True, "messages": []},
        ],
    )
    assert client.statuses == ["ACTIVE", "AWAITING_INPUT"]


async def test_pi_settles_on_agent_settled_not_on_agent_end():
    """``agent_end`` is one low-level run; a retry or a queued continuation may
    still follow. Settling there would end the turn early."""
    session, transport, client = make_session("pi")
    task = asyncio.create_task(session.prompt("go"))
    await asyncio.sleep(0)
    await transport.emit({"type": "agent_start"})
    await transport.emit({"type": "agent_end", "messages": []})
    await asyncio.sleep(0.05)
    assert not task.done()
    await transport.emit({"type": "agent_settled"})
    await asyncio.wait_for(task, timeout=2)
    assert client.statuses[-1] == "AWAITING_INPUT"


async def test_a_non_terminal_agent_end_does_not_settle_the_turn():
    """omp emits a second ``agent_start`` for a continuation; settling on the
    first ``agent_end`` would cut the work short."""
    session, transport, _client = make_session("omp")
    task = asyncio.create_task(session.prompt("go"))
    await asyncio.sleep(0)
    await transport.emit({"type": "agent_end", "isTerminal": False, "messages": []})
    await asyncio.sleep(0.05)
    assert not task.done()
    await transport.emit({"type": "agent_end", "isTerminal": True, "messages": []})
    await asyncio.wait_for(task, timeout=2)


async def test_a_retrying_agent_end_does_not_settle_the_turn():
    session, transport, _client = make_session("pi")
    task = asyncio.create_task(session.prompt("go"))
    await asyncio.sleep(0)
    await transport.emit({"type": "agent_end", "willRetry": True, "messages": []})
    await asyncio.sleep(0.05)
    assert not task.done()
    await transport.emit({"type": "agent_settled"})
    await asyncio.wait_for(task, timeout=2)


async def test_a_settle_grace_covers_a_build_that_never_emits_its_settle_event():
    """Belt and braces for version drift: the grace fires only when the
    promised event does not arrive."""
    spec = dataclasses.replace(PI_FAMILY_AGENTS["pi"], settle_event="agent_settled")
    session, transport, _client = make_session("pi")
    session.spec = spec
    import integrations.headless.pi_family.session as session_module

    original = session_module._SETTLE_GRACE_SECONDS
    session_module._SETTLE_GRACE_SECONDS = 0.05
    try:
        await drive_prompt(
            session, transport, [{"type": "agent_end", "messages": []}], timeout=2
        )
    finally:
        session_module._SETTLE_GRACE_SECONDS = original


async def test_new_work_cancels_an_armed_settle():
    session, transport, _client = make_session("pi")
    import integrations.headless.pi_family.session as session_module

    original = session_module._SETTLE_GRACE_SECONDS
    session_module._SETTLE_GRACE_SECONDS = 0.3
    try:
        task = asyncio.create_task(session.prompt("go"))
        await asyncio.sleep(0)
        await transport.emit({"type": "agent_end", "messages": []})
        await asyncio.sleep(0.05)
        await transport.emit({"type": "agent_start"})  # continuation
        await asyncio.sleep(0.4)
        assert not task.done()
        await transport.emit({"type": "agent_settled"})
        await asyncio.wait_for(task, timeout=2)
    finally:
        session_module._SETTLE_GRACE_SECONDS = original


async def test_a_dead_transport_unparks_the_turn_and_says_why():
    """The parked completion future is not a transport request, so failing
    pending requests cannot reach it."""
    session, transport, client = make_session("omp")
    task = asyncio.create_task(session.prompt("go"))
    await asyncio.sleep(0)
    session._on_transport_closed("omp exited\n--- omp stderr ---\nNo models available")
    await asyncio.wait_for(task, timeout=2)
    await asyncio.sleep(0.05)
    assert any("exited unexpectedly" in row for row, _ in client.rows)
    assert client.statuses[-1] == "AWAITING_INPUT"


async def test_events_become_chat_rows():
    session, transport, client = make_session("omp")
    await drive_prompt(
        session,
        transport,
        [
            {
                "type": "message_update",
                "assistantMessageEvent": {
                    "type": "text_end",
                    "contentIndex": 0,
                    "content": "done",
                },
            },
            {"type": "agent_end", "isTerminal": True, "messages": []},
        ],
    )
    assert ("done", {}) in client.rows


async def test_steer_only_applies_while_a_turn_is_running():
    session, transport, _client = make_session("omp")
    assert session.steer("hurry") is False
    task = asyncio.create_task(session.prompt("go"))
    await asyncio.sleep(0)
    assert session.steer("hurry") is True
    assert transport.sends[-1] == ("steer", {"message": "hurry"})
    await transport.emit({"type": "agent_end", "isTerminal": True, "messages": []})
    await asyncio.wait_for(task, timeout=2)


async def test_interrupt_with_no_turn_still_settles_a_stale_active_row():
    session, transport, client = make_session("omp")
    await session.interrupt()
    assert client.statuses == ["AWAITING_INPUT"]
    assert ("abort", {}) not in transport.requests


async def test_interrupt_aborts_a_running_turn():
    session, transport, _client = make_session("omp")
    task = asyncio.create_task(session.prompt("go"))
    await asyncio.sleep(0)
    await session.interrupt()
    assert ("abort", {}) in transport.requests
    await transport.emit({"type": "agent_end", "isTerminal": True, "messages": []})
    await asyncio.wait_for(task, timeout=2)


async def test_presentation_ui_requests_are_never_answered():
    """``setWidget`` fires in plain rpc mode and expects no response."""
    session, transport, _client = make_session("omp")
    session._spawn_dialog(
        {
            "type": "extension_ui_request",
            "id": "w1",
            "method": "setWidget",
            "widgetKey": "x",
        }
    )
    await asyncio.sleep(0.05)
    assert transport.sends == []


async def test_bring_up_captures_the_session_id_and_reports_live_models():
    session, transport, client = make_session(
        "omp",
        responses={
            "get_state": {"sessionId": "01a0-xyz"},
            "get_available_models": {
                "models": [
                    {"id": "claude-haiku-4-5", "provider": "anthropic", "name": "Haiku"}
                ]
            },
            "get_available_commands": {
                "commands": [{"name": "compact", "description": "Compact"}]
            },
        },
    )
    await session.start()
    assert session.agent_session_id == "01a0-xyz"
    # The label is the display name alone — the clients render the qualified id
    # underneath it, so "(anthropic)" in the label would just say it twice.
    assert session.available_models == [
        {"id": "anthropic/claude-haiku-4-5", "label": "Haiku"}
    ]
    assert {"pi_session_id": "01a0-xyz"} in [
        p.get("instance_metadata") for p in client.patches
    ]
    assert client.commands[0]["agent_type"] == "omp"
    assert client.statuses[-1] == "AWAITING_INPUT"


async def test_the_reported_current_model_is_what_the_agent_is_running():
    """Not the spawn-time preference, which is empty on the common "Default"
    path — leaving the gear to name whichever model sorted first."""
    session, _transport, client = make_session(
        "omp",
        responses={
            "get_state": {
                "sessionId": "s",
                "model": {"id": "claude-haiku-4-5", "provider": "anthropic"},
            },
            "get_available_models": {
                "models": [
                    {
                        "id": "claude-3-5-sonnet",
                        "provider": "anthropic",
                        "name": "Sonnet",
                    },
                    {
                        "id": "claude-haiku-4-5",
                        "provider": "anthropic",
                        "name": "Haiku",
                    },
                ]
            },
        },
    )
    await session.start()
    assert session.current_model == "anthropic/claude-haiku-4-5"
    config = next(
        p["session_config"]
        for p in client.patches
        if "available_models" in p.get("session_config", {})
    )
    assert config["current_model"] == "anthropic/claude-haiku-4-5"


async def test_the_current_model_key_matches_an_entry_in_the_advertised_list():
    """A mismatch renders the gear as if nothing were selected."""
    session, _transport, _client = make_session(
        "omp",
        responses={
            "get_state": {
                "sessionId": "s",
                "model": {"id": "claude-haiku-4-5", "provider": "anthropic"},
            },
            "get_available_models": {
                "models": [
                    {"id": "claude-haiku-4-5", "provider": "anthropic", "name": "Haiku"}
                ]
            },
        },
    )
    await session.start()
    assert session.current_model in {m["id"] for m in session.available_models}


async def test_a_model_changed_event_republishes_the_new_model():
    session, transport, client = make_session(
        "omp",
        responses={
            "get_state": {
                "sessionId": "s",
                "model": {"id": "claude-haiku-4-5", "provider": "anthropic"},
            }
        },
    )
    await session.start()
    transport.responses["get_state"] = {
        "sessionId": "s",
        "model": {"id": "gpt-5.2", "provider": "openai"},
    }
    await transport.emit({"type": "model_changed"})
    assert session.current_model == "openai/gpt-5.2"
    assert client.patches[-1]["session_config"]["current_model"] == "openai/gpt-5.2"


async def test_pi_bring_up_skips_the_subagent_subscription_it_cannot_serve():
    session, transport, _client = make_session("pi", responses={"get_state": {}})
    await session.start()
    assert "set_subagent_subscription" not in [c for c, _ in transport.requests]
    assert "get_commands" in [c for c, _ in transport.requests]


async def test_omp_bring_up_defaults_the_subagent_subscription_to_progress():
    """``events`` nests the child's whole stream — 110 frames for one trivial
    subagent."""
    session, transport, _client = make_session("omp", responses={"get_state": {}})
    await session.start()
    assert ("set_subagent_subscription", {"level": "progress"}) in transport.requests


async def test_an_unknown_model_switch_is_reported_not_silently_recorded():
    session, transport, _client = make_session("omp")

    async def failing(command, params=None, *, timeout=None):
        raise RuntimeError("Model not found: anthropic/nope")

    transport.request = failing
    assert await session.set_model("anthropic/nope") is False
    assert session.model is None


async def test_an_unsupported_thinking_level_is_dropped_at_the_boundary():
    """omp accepts ``auto``; pi does not. Passing it through would fail at the
    CLI instead of here."""
    session, _transport, _client = make_session("pi")
    assert await session.set_thinking_level("auto") is False


async def test_subagent_progress_writes_one_row_per_status_change():
    session, transport, client = make_session("omp")
    payload = {
        "id": "DelightedDinosaur",
        "agent": "task",
        "parentToolCallId": "toolu_1",
        "assignment": "Count the lines",
        "progress": {"id": "DelightedDinosaur", "status": "running", "agent": "task"},
    }
    await transport.emit({"type": "subagent_progress", "payload": payload})
    await transport.emit({"type": "subagent_progress", "payload": payload})
    completed = {**payload, "progress": {**payload["progress"], "status": "completed"}}
    await transport.emit({"type": "subagent_progress", "payload": completed})
    subagent_rows = [row for row, md in client.rows if md.get("subagent")]
    assert len(subagent_rows) == 2
    assert "is working" in subagent_rows[0] and "finished" in subagent_rows[1]


async def test_subagent_rows_group_under_the_launching_tool_call():
    session, transport, client = make_session("omp")
    await transport.emit(
        {
            "type": "subagent_lifecycle",
            "payload": {
                "id": "Dino",
                "agent": "task",
                "parentToolCallId": "toolu_1",
                "status": "started",
            },
        }
    )
    metadata = next(md for _row, md in client.rows if md.get("subagent"))
    assert metadata["subagent"]["tool_use_id"] == "toolu_1"


async def test_the_subagent_event_firehose_is_dropped():
    session, transport, client = make_session("omp")
    await transport.emit(
        {"type": "subagent_event", "payload": {"id": "d", "event": {"type": "x"}}}
    )
    assert client.rows == []
