"""The omp host-tool frame adapter: registration, round trip, cancellation."""

from __future__ import annotations

import asyncio

from integrations.agent_tools import AgentToolContext
from integrations.agent_tools.registry import AgentTool, ToolResult, object_schema
from integrations.headless.pi_family.host_tools import HostToolRouter
from integrations.headless.pi_family.transport import PiRpcError


class Recorder:
    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    def __call__(self, command, params):
        self.sent.append((command, params))

    def of(self, command):
        return [params for name, params in self.sent if name == command]


def make_router(tools=None, **kwargs):
    recorder = Recorder()
    registry = (
        {tool.name: tool for tool in (tools or [])} if tools is not None else None
    )
    router = HostToolRouter(
        context=AgentToolContext(client=None, agent_instance_id="s1", **kwargs),
        send=recorder,
        registry=registry,
    )
    return router, recorder


def echo_tool(name="echo", handler=None):
    async def default(_context, arguments):
        return ToolResult(text=f"echoed {arguments.get('value')}")

    return AgentTool(
        name=name,
        label=name,
        description="echo",
        parameters=object_schema({"value": {"type": "string"}}),
        handler=handler or default,
    )


async def test_registration_returns_the_accepted_tool_names():
    router, _recorder = make_router([echo_tool()])

    async def request(command, params):
        assert command == "set_host_tools"
        assert params["tools"][0]["name"] == "echo"
        return {"toolNames": ["echo"]}

    assert await router.register(request) == ["echo"]


async def test_registration_degrades_quietly_on_a_build_without_host_tools():
    """pi answers ``Unknown command: set_host_tools``. That must cost the
    channel, not the session."""
    router, _recorder = make_router([echo_tool()])

    async def request(_command, _params):
        raise PiRpcError("set_host_tools", "Unknown command: set_host_tools")

    assert await router.register(request) == []


async def test_a_call_replies_with_a_result_echoing_the_correlation_id():
    """``id`` is the correlation id; ``toolCallId`` is the model's ``toolu_…``
    id that the ``tool_execution_*`` events key on. Echoing the wrong one
    strands the call."""
    router, recorder = make_router([echo_tool()])
    router.handle_call(
        {
            "type": "host_tool_call",
            "id": "corr-1",
            "toolCallId": "toolu_abc",
            "toolName": "echo",
            "arguments": {"value": "hi"},
        }
    )
    await asyncio.sleep(0.05)
    results = recorder.of("host_tool_result")
    assert len(results) == 1
    assert results[0]["id"] == "corr-1"
    assert results[0]["result"]["content"][0]["text"] == "echoed hi"
    assert "isError" not in results[0]


async def test_a_failing_tool_replies_with_is_error_rather_than_going_silent():
    async def boom(_context, _arguments):
        raise RuntimeError("nope")

    router, recorder = make_router([echo_tool(handler=boom)])
    router.handle_call({"id": "corr-2", "toolName": "echo", "arguments": {}})
    await asyncio.sleep(0.05)
    result = recorder.of("host_tool_result")[0]
    assert result["isError"] is True
    assert "nope" in result["result"]["content"][0]["text"]


async def test_an_unknown_tool_name_still_gets_an_answer():
    router, recorder = make_router([echo_tool()])
    router.handle_call({"id": "corr-3", "toolName": "not_a_tool", "arguments": {}})
    await asyncio.sleep(0.05)
    assert recorder.of("host_tool_result")[0]["isError"] is True


async def test_cancellation_suppresses_the_result_not_just_the_work():
    """A late result for a cancelled call corrupts omp's state, so the send
    must be suppressed — stopping the work is not enough."""
    started = asyncio.Event()

    async def slow(_context, _arguments):
        started.set()
        await asyncio.sleep(5)
        return ToolResult(text="too late")

    router, recorder = make_router([echo_tool(handler=slow)])
    router.handle_call({"id": "corr-4", "toolName": "echo", "arguments": {}})
    await asyncio.wait_for(started.wait(), timeout=1)
    router.handle_cancel({"type": "host_tool_cancel", "id": "x", "targetId": "corr-4"})
    await asyncio.sleep(0.05)
    assert recorder.of("host_tool_result") == []


async def test_an_update_for_a_cancelled_call_is_suppressed_too():
    router, recorder = make_router([echo_tool()])
    router.handle_cancel({"targetId": "corr-5"})
    router.send_update("corr-5", "working…")
    assert recorder.of("host_tool_update") == []


async def test_a_partial_update_is_sent_in_the_shape_omp_reflects_back():
    """``host_tool_update.partialResult`` comes back as
    ``tool_execution_update.partialResult``, so streaming progress is free."""
    router, recorder = make_router([echo_tool()])
    router.send_update("corr-6", "working…")
    update = recorder.of("host_tool_update")[0]
    assert update["id"] == "corr-6"
    assert update["partialResult"]["content"][0]["text"] == "working…"


async def test_concurrent_calls_do_not_serialize_behind_each_other():
    """omp can have several calls in flight; a blocking handler would stall the
    whole event stream."""
    release = asyncio.Event()

    async def gated(_context, arguments):
        if arguments.get("wait"):
            await release.wait()
        return ToolResult(text=str(arguments.get("value")))

    router, recorder = make_router([echo_tool(handler=gated)])
    router.handle_call(
        {"id": "slow", "toolName": "echo", "arguments": {"wait": True, "value": 1}}
    )
    router.handle_call({"id": "fast", "toolName": "echo", "arguments": {"value": 2}})
    await asyncio.sleep(0.05)
    assert [r["id"] for r in recorder.of("host_tool_result")] == ["fast"]
    release.set()
    await asyncio.sleep(0.05)
    assert [r["id"] for r in recorder.of("host_tool_result")] == ["fast", "slow"]


async def test_aclose_cancels_in_flight_calls_without_replying():
    async def forever(_context, _arguments):
        await asyncio.sleep(30)
        return ToolResult(text="never")

    router, recorder = make_router([echo_tool(handler=forever)])
    router.handle_call({"id": "corr-7", "toolName": "echo", "arguments": {}})
    await asyncio.sleep(0.02)
    await router.aclose()
    assert recorder.of("host_tool_result") == []


async def test_a_malformed_call_frame_is_ignored():
    router, recorder = make_router([echo_tool()])
    router.handle_call({"toolName": "echo"})  # no id
    await asyncio.sleep(0.02)
    assert recorder.sent == []


def test_definitions_expose_the_real_registry_by_default():
    router, _recorder = make_router(tools=None)
    names = {definition["name"] for definition in router.definitions}
    assert "vicoa_list_sessions" in names
