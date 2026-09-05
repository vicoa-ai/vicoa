"""Provider-agnostic Vicoa tools: registry, dispatch, guards, handlers."""

from __future__ import annotations

import pytest

from integrations.agent_tools import AgentToolContext, AgentToolError, SpendGuard
from integrations.agent_tools.context import DEPTH_ENV_VAR, MAX_SPAWN_DEPTH, child_env
from integrations.agent_tools.registry import (
    build_registry,
    dispatch,
    to_host_tool_definitions,
)


class FakeClient:
    """Records calls and replays canned responses keyed by ``METHOD path``."""

    def __init__(self, responses=None, error=None):
        self.responses = responses or {}
        self.error = error
        self.calls: list[tuple[str, str, dict]] = []

    async def request(self, method, endpoint, *, json=None, params=None, timeout=None):
        self.calls.append((method, endpoint, json or params or {}))
        if self.error is not None:
            raise self.error
        return self.responses.get(f"{method} {endpoint}", {})


def make_context(client=None, **kwargs):
    return AgentToolContext(
        client=client or FakeClient(),
        agent_instance_id=kwargs.pop("agent_instance_id", "self-1"),
        project_path=kwargs.pop("project_path", "/work/repo"),
        machine_id=kwargs.pop("machine_id", "machine-1"),
        **kwargs,
    )


@pytest.fixture
def registry():
    return build_registry()


def test_the_registry_covers_sessions_tasks_and_automations(registry):
    names = set(registry)
    assert {"vicoa_list_sessions", "vicoa_start_session"} <= names
    assert {"vicoa_list_tasks", "vicoa_create_task"} <= names
    assert {"vicoa_list_automations", "vicoa_create_automation"} <= names


def test_every_tool_has_a_closed_object_schema(registry):
    """An open schema invites the model to invent parameters that are then
    silently dropped — which reads to the user as the tool ignoring them."""
    for tool in registry.values():
        assert tool.parameters["type"] == "object"
        assert tool.parameters["additionalProperties"] is False
        for name in tool.parameters["required"]:
            assert name in tool.parameters["properties"], tool.name


def test_only_state_changing_tools_are_metered(registry):
    """Reads must stay free so an agent can inspect without burning budget."""
    assert not registry["vicoa_list_sessions"].mutating
    assert not registry["vicoa_get_task"].mutating
    assert registry["vicoa_start_session"].mutating
    assert registry["vicoa_create_task"].mutating


def test_host_tool_definitions_are_the_shape_set_host_tools_takes(registry):
    definitions = to_host_tool_definitions(registry)
    assert len(definitions) == len(registry)
    assert set(definitions[0]) == {
        "name",
        "label",
        "description",
        "parameters",
        "loadMode",
    }
    assert {d["loadMode"] for d in definitions} <= {"essential", "discoverable"}


async def test_an_unknown_tool_comes_back_as_a_readable_error(registry):
    result = await dispatch(registry, make_context(), "vicoa_nope", {})
    assert result.is_error
    assert "Unknown tool" in result.text


async def test_a_handler_exception_becomes_an_error_result_not_a_crash(registry):
    """An exception escaping into the frame loop would strand the call and
    leave the agent waiting for a result that never arrives."""
    context = make_context(FakeClient(error=RuntimeError("boom")))
    result = await dispatch(registry, context, "vicoa_list_tasks", {})
    assert result.is_error and "boom" in result.text


async def test_list_sessions_summarises_rows(registry):
    client = FakeClient(
        {
            "GET /api/v1/agent-instances": [
                {
                    "id": "a",
                    "name": "alpha",
                    "status": "ACTIVE",
                    "agent_type_name": "Claude Code",
                },
                {
                    "id": "b",
                    "name": "beta",
                    "status": "COMPLETED",
                    "agent_type_name": "Codex",
                },
            ]
        }
    )
    result = await dispatch(registry, make_context(client), "vicoa_list_sessions", {})
    assert not result.is_error
    assert "2 session(s)" in result.text and "alpha" in result.text
    assert client.calls[0][2]["scope"] == "me"


async def test_limits_are_clamped_rather_than_trusted(registry):
    client = FakeClient({"GET /api/v1/agent-instances": []})
    await dispatch(
        registry, make_context(client), "vicoa_list_sessions", {"limit": 5000}
    )
    assert client.calls[0][2]["limit"] == 50


async def test_a_string_limit_is_accepted_because_models_send_them(registry):
    client = FakeClient({"GET /api/v1/agent-instances": []})
    await dispatch(
        registry, make_context(client), "vicoa_list_sessions", {"limit": "5"}
    )
    assert client.calls[0][2]["limit"] == 5


async def test_start_session_defaults_to_this_sessions_machine_and_directory(registry):
    client = FakeClient(
        {
            "POST /api/v1/machines/machine-1/spawn-requests": {
                "agent_instance_id": "new-1"
            }
        }
    )
    result = await dispatch(
        registry,
        make_context(client),
        "vicoa_start_session",
        {"prompt": "fix the tests"},
    )
    method, endpoint, body = client.calls[0]
    assert (method, endpoint) == ("POST", "/api/v1/machines/machine-1/spawn-requests")
    assert body["directory"] == "/work/repo"
    assert body["prompt"] == "fix the tests"
    assert "new-1" in result.text


async def test_a_spawned_session_records_its_parent_and_its_new_depth(registry):
    client = FakeClient({"POST /api/v1/machines/machine-1/spawn-requests": {}})
    await dispatch(
        registry, make_context(client), "vicoa_start_session", {"prompt": "go"}
    )
    metadata = client.calls[0][2]["metadata"]
    assert metadata["spawned_by_agent_instance_id"] == "self-1"
    assert metadata["agent_tool_depth"] == 1


async def test_spawning_is_refused_at_the_depth_cap(registry):
    """`create_agent` + `send_prompt` otherwise lets agents spawn agents that
    spawn agents, unattended, burning the user's quota."""
    context = make_context(depth=MAX_SPAWN_DEPTH)
    result = await dispatch(registry, context, "vicoa_start_session", {"prompt": "go"})
    assert result.is_error and "level(s) deep" in result.text


async def test_messaging_yourself_is_refused(registry):
    """The message comes straight back to this wrapper as new user input —
    an infinite loop with extra steps."""
    result = await dispatch(
        registry,
        make_context(),
        "vicoa_send_session_message",
        {"session_id": "self-1", "content": "hi"},
    )
    assert result.is_error and "loop" in result.text


async def test_ending_your_own_session_from_inside_it_is_refused(registry):
    result = await dispatch(
        registry, make_context(), "vicoa_end_session", {"session_id": "self-1"}
    )
    assert result.is_error


async def test_interrupt_sends_the_same_control_envelope_the_stop_button_does(registry):
    client = FakeClient()
    await dispatch(
        registry,
        make_context(client),
        "vicoa_interrupt_session",
        {"session_id": "other"},
    )
    from integrations.headless.control_command import parse_control_command

    body = client.calls[0][2]
    assert body["agent_instance_id"] == "other"
    assert parse_control_command(body["content"]) == {"setting": "interrupt"}


async def test_the_rate_limit_bounds_fan_out_that_depth_alone_does_not(registry):
    """One agent looping ``start_session`` a thousand times never exceeds
    depth 1, so the depth cap cannot catch it."""
    client = FakeClient({"POST /api/v1/machines/machine-1/spawn-requests": {}})
    context = make_context(client, guard=SpendGuard(max_calls=2, window_seconds=999))
    for _ in range(2):
        assert not (
            await dispatch(registry, context, "vicoa_start_session", {"prompt": "go"})
        ).is_error
    refused = await dispatch(registry, context, "vicoa_start_session", {"prompt": "go"})
    assert refused.is_error and "Rate limit" in refused.text


async def test_reads_are_not_counted_against_the_rate_limit(registry):
    client = FakeClient({"GET /api/v1/tasks": []})
    context = make_context(client, guard=SpendGuard(max_calls=1, window_seconds=999))
    for _ in range(5):
        assert not (await dispatch(registry, context, "vicoa_list_tasks", {})).is_error


def test_the_rate_window_rolls():
    clock = {"now": 0.0}
    guard = SpendGuard(max_calls=1, window_seconds=10.0, now=lambda: clock["now"])
    guard.check_and_record("t")
    with pytest.raises(AgentToolError):
        guard.check_and_record("t")
    clock["now"] = 11.0
    guard.check_and_record("t")  # window has rolled


async def test_task_status_is_validated_against_the_backends_enum(registry):
    result = await dispatch(
        registry, make_context(), "vicoa_create_task", {"title": "x", "status": "nope"}
    )
    assert result.is_error and "backlog" in result.text


async def test_create_task_sends_only_the_fields_that_were_given(registry):
    client = FakeClient({"POST /api/v1/tasks": {"id": "t9"}})
    result = await dispatch(
        registry,
        make_context(client),
        "vicoa_create_task",
        {"title": "Ship it", "priority": "high"},
    )
    assert client.calls[0][2] == {"title": "Ship it", "priority": "high"}
    assert "t9" in result.text


async def test_update_task_refuses_a_no_op(registry):
    result = await dispatch(
        registry, make_context(), "vicoa_update_task", {"task_id": "t1"}
    )
    assert result.is_error and "Nothing to update" in result.text


async def test_a_recurring_automation_requires_a_frequency(registry):
    result = await dispatch(
        registry,
        make_context(),
        "vicoa_create_automation",
        {"title": "Nightly", "prompt": "run tests", "schedule_kind": "recurring"},
    )
    assert result.is_error and "frequency" in result.text


async def test_a_one_time_automation_requires_run_at(registry):
    result = await dispatch(
        registry,
        make_context(),
        "vicoa_create_automation",
        {"title": "Once", "prompt": "run tests", "schedule_kind": "once"},
    )
    assert result.is_error and "run_at" in result.text


async def test_create_automation_builds_the_session_config_the_api_validates(registry):
    """``session_config.agent`` is the one field the API requires — the
    scheduler dispatches on it."""
    client = FakeClient(
        {"POST /api/v1/automations": {"id": "a1", "next_run_at": "soon"}}
    )
    result = await dispatch(
        registry,
        make_context(client),
        "vicoa_create_automation",
        {
            "title": "Weekday tests",
            "prompt": "run the tests",
            "schedule_kind": "recurring",
            "frequency": {"kind": "weekdays", "time": "09:00"},
            "agent": "codex",
            "timezone": "Asia/Singapore",
        },
    )
    body = client.calls[0][2]
    assert body["session_config"] == {"agent": "codex"}
    assert body["machine_id"] == "machine-1"
    assert body["directory"] == "/work/repo"
    assert body["timezone"] == "Asia/Singapore"
    assert "a1" in result.text


def test_child_env_carries_the_depth_forward():
    env = child_env({"PATH": "/bin"}, depth=1)
    assert env[DEPTH_ENV_VAR] == "1"
    assert env["PATH"] == "/bin"
