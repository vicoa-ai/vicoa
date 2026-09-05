"""Event-mapper tests, driven from the archived omp wire traces.

The fixtures under ``fixtures/omp/`` are verbatim frames from a real
``omp --mode rpc`` run, so these tests check the mapper against the protocol as
it actually behaves rather than against a hand-written idea of it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrations.headless.pi_family.event_mapper import Emission, EventMapper


FIXTURES = Path(__file__).parent / "fixtures" / "omp"


def replay(name: str) -> list[Emission]:
    mapper = EventMapper(agent_type="Oh My Pi", thinking_source="omp")
    emissions: list[Emission] = []
    with (FIXTURES / name).open() as handle:
        for line in handle:
            if line.strip():
                emissions.extend(mapper.handle(json.loads(line)))
    return emissions


def is_thinking(emission: Emission) -> bool:
    return bool((emission.metadata or {}).get("thinking"))


def test_plain_text_turn_yields_one_thinking_card_and_one_answer():
    emissions = replay("01-text.jsonl")
    assert len(emissions) == 2
    assert is_thinking(emissions[0])
    assert emissions[1].content == "hello"
    assert emissions[1].metadata is None


def test_thinking_metadata_names_the_producing_agent():
    thinking = next(e for e in replay("01-text.jsonl") if is_thinking(e))
    assert thinking.metadata == {"thinking": {"source": "omp"}}


def test_tool_call_uses_the_protocol_supplied_intent_as_the_card_header():
    """``intent`` is a label the agent already wrote for this exact call —
    strictly better than anything synthesized from ``args``."""
    contents = [e.content for e in replay("02-tools.jsonl")]
    assert "🔧 Using tool: Read - Reading sample.txt" in contents


def test_tool_result_is_written_as_its_own_result_row():
    contents = [e.content for e in replay("02-tools.jsonl")]
    result = next(c for c in contents if c.startswith("   Result:"))
    assert "the quick brown fox" in result


def test_no_row_is_emitted_twice_for_a_streamed_block():
    """``message_end`` repeats every block that already streamed an ``*_end``.

    Emitting per block *and* per message would double every row.
    """
    emissions = replay("01-text.jsonl")
    assert [e.content for e in emissions].count("hello") == 1


def test_host_tool_calls_render_as_ordinary_tool_cards():
    """A ``host_tool_call`` also emits the normal ``tool_execution_*`` triple,
    so no separate rendering path is needed."""
    contents = [e.content for e in replay("03-hosttool.jsonl")]
    assert any(c.startswith("🔧 Using tool: vicoa_list_sessions") for c in contents)
    assert any("2 sessions: alpha (running)" in c for c in contents)


def test_todo_list_is_written_once_not_once_per_source():
    """The same list arrives twice — as the todo tool's result and again as the
    ``todo_reminder`` nudge. The second is noise."""
    cards = [
        e.content
        for e in replay("05-todo.jsonl")
        if "Using tool: TodoWrite" in e.content
    ]
    assert len(cards) == 1
    assert "Add GET /health endpoint handler" in cards[0]


def test_subagent_task_card_is_rendered_from_the_parent_tool_call():
    contents = [e.content for e in replay("06-subagent.jsonl")]
    assert any(c.startswith("🔧 Using tool: Task -") for c in contents)


def test_approval_run_still_renders_the_write_and_its_result():
    contents = [e.content for e in replay("04-approval.jsonl")]
    assert any(c.startswith("🔧 Using tool: Write") for c in contents)
    assert any("Successfully wrote 2 bytes" in c for c in contents)


@pytest.mark.parametrize(
    "name",
    ["01-text.jsonl", "02-tools.jsonl", "03-hosttool.jsonl", "06-subagent.jsonl"],
)
def test_every_fixture_replays_without_an_empty_row(name):
    """An empty row would render as a blank chat bubble."""
    assert all(e.content.strip() for e in replay(name))


def test_provider_error_is_surfaced_from_the_message_not_the_transport():
    """A provider rejection is an ordinary ``message_end`` with
    ``stopReason: error`` — not a transport failure. Missing it means the turn
    silently produces nothing."""
    mapper = EventMapper()
    emissions = mapper.handle(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [],
                "stopReason": "error",
                "errorMessage": json.dumps(
                    {"type": "error", "error": {"message": "invalid x-api-key"}}
                ),
            },
        }
    )
    assert len(emissions) == 1
    assert "Model provider error" in emissions[0].content
    assert "invalid x-api-key" in emissions[0].content


def test_provider_error_falls_back_to_the_raw_text_when_it_is_not_json():
    mapper = EventMapper()
    emissions = mapper.handle(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [],
                "stopReason": "error",
                "errorMessage": "upstream timed out",
            },
        }
    )
    assert "upstream timed out" in emissions[0].content


def test_tool_error_is_flagged_rather_than_reported_as_a_result():
    mapper = EventMapper()
    emissions = mapper.handle(
        {
            "type": "tool_execution_end",
            "toolCallId": "t1",
            "toolName": "bash",
            "isError": True,
            "result": {"content": [{"type": "text", "text": "command not found"}]},
        }
    )
    assert emissions[0].content.startswith("⚠️ Tool failed:")


def test_a_clean_tool_with_no_output_writes_no_second_row():
    mapper = EventMapper()
    assert (
        mapper.handle(
            {
                "type": "tool_execution_end",
                "toolCallId": "t1",
                "toolName": "write",
                "result": {"content": []},
            }
        )
        == []
    )


def test_user_and_tool_result_message_ends_are_dropped():
    """They echo rows the wrapper and the tool card already wrote."""
    mapper = EventMapper()
    assert (
        mapper.handle(
            {
                "type": "message_end",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "hi"}],
                },
            }
        )
        == []
    )
    assert (
        mapper.handle(
            {
                "type": "message_end",
                "message": {
                    "role": "toolResult",
                    "content": [{"type": "text", "text": "out"}],
                },
            }
        )
        == []
    )


def test_unknown_event_types_are_dropped_not_raised():
    """The measured wire carries types no schema models; a closed union would
    make them vanish silently instead of being logged."""
    mapper = EventMapper()
    assert mapper.handle({"type": "some_future_event", "payload": {"a": 1}}) == []


def test_a_malformed_frame_cannot_take_down_the_stream():
    mapper = EventMapper()
    assert mapper.handle({"type": "tool_execution_start", "args": "not-a-dict"}) != []


def test_warning_and_error_notices_surface_with_distinct_icons():
    mapper = EventMapper()
    warning = mapper.handle({"type": "notice", "level": "warning", "message": "slow"})
    error = mapper.handle({"type": "notice", "level": "error", "message": "broke"})
    assert warning[0].content.startswith("⚠️")
    assert error[0].content.startswith("❌")


def test_info_notices_are_dropped_because_they_are_the_agents_status_line():
    """Upstream renders this tier as `showStatus`, not as conversation.

    Every omp session opened with the `xdev` extension announcing that our own
    host tools had been mounted — a wall of tool names, before the user's first
    real message.
    """
    mapper = EventMapper()
    assert (
        mapper.handle(
            {
                "type": "notice",
                "level": "info",
                "source": "xdev",
                "message": (
                    "xd://: mounted vicoa_get_session, "
                    "vicoa_read_session_transcript, vicoa_list_machines"
                ),
            }
        )
        == []
    )


def test_a_notice_with_no_level_is_dropped_rather_than_guessed_as_important():
    mapper = EventMapper()
    assert mapper.handle({"type": "notice", "message": "something"}) == []


def test_a_successful_retry_is_not_announced_twice():
    mapper = EventMapper()
    assert mapper.handle(
        {
            "type": "auto_retry_start",
            "attempt": 1,
            "maxAttempts": 3,
            "errorMessage": "429",
        }
    )
    assert mapper.handle({"type": "auto_retry_end", "success": True}) == []
