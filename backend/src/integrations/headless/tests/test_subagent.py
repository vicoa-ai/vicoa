import asyncio

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TaskNotificationMessage,
    TaskStartedMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from integrations.headless.claude_code import InboundUserMessage
from integrations.headless.subagent import SubAgentTracker, build_metadata
from _fakes import FakeAsyncVicoaClient


def test_tracker_labels_known_task():
    t = SubAgentTracker()
    t.remember_task("tu-1", "Explore", "map the code")
    assert t.label_for("tu-1") == ("Explore", "map the code")


def test_tracker_falls_back_on_unknown_task():
    assert SubAgentTracker().label_for("nope") == ("agent", "")


def test_build_metadata_shape():
    md = build_metadata("tu-1", "Explore", "map the code")
    assert md == {
        "subagent": {
            "tool_use_id": "tu-1",
            "subagent_type": "Explore",
            "description": "map the code",
            "role": "step",
        }
    }


# ---------------------------------------------------------------------------
# Task C3: diverting sub-agent messages in the receive loop.
#
# The SDK streams a sub-agent's inner messages on the SAME receive_response()
# stream as the main conversation, each stamped with parent_tool_use_id equal
# to the launching Task/Agent block's id. These builders mirror what the SDK
# actually emits (verified against claude_agent_sdk's dataclass signatures).
# ---------------------------------------------------------------------------


def _assistant_with_task(
    tool_use_id: str, subagent_type: str, description: str
) -> AssistantMessage:
    """A main-stream AssistantMessage launching a sub-agent via the Task tool."""
    return AssistantMessage(
        content=[
            ToolUseBlock(
                id=tool_use_id,
                name="Task",
                input={"subagent_type": subagent_type, "description": description},
            )
        ],
        model="claude-test",
        parent_tool_use_id=None,
    )


def _child_assistant(parent_tool_use_id: str, text: str) -> AssistantMessage:
    """A sub-agent's own AssistantMessage, stamped with its launching Task id."""
    return AssistantMessage(
        content=[TextBlock(text=text)],
        model="claude-test",
        parent_tool_use_id=parent_tool_use_id,
    )


def _child_assistant_text_main(text: str) -> AssistantMessage:
    """A main-stream AssistantMessage carrying plain text (the agent talking)."""
    return AssistantMessage(
        content=[TextBlock(text=text)],
        model="claude-test",
        parent_tool_use_id=None,
    )


def _child_tool_result(
    parent_tool_use_id: str, tool_use_id: str, content: str
) -> UserMessage:
    """A sub-agent's tool-result UserMessage, stamped with its launching Task id."""
    return UserMessage(
        content=[ToolResultBlock(tool_use_id=tool_use_id, content=content)],
        parent_tool_use_id=parent_tool_use_id,
    )


@pytest.mark.asyncio
async def test_task_launch_is_remembered_and_children_are_tagged(make_runner):
    runner = make_runner()
    sends = []

    async def _capture(content, message_metadata=None):
        sends.append((content, message_metadata))

    runner.send_to_vicoa = _capture  # type: ignore

    # 1) main-stream AssistantMessage carrying a Task tool_use → remembered.
    runner._remember_tasks_in_message(_assistant_with_task("tu-1", "Explore", "map"))
    # 2) child AssistantMessage (parent_tool_use_id set) → tagged + diverted.
    handled = await runner._maybe_handle_subagent_message(
        _child_assistant("tu-1", "reading files")
    )
    assert handled is True
    assert sends[-1][0] == "reading files"
    assert sends[-1][1]["subagent"]["tool_use_id"] == "tu-1"
    assert sends[-1][1]["subagent"]["subagent_type"] == "Explore"
    assert sends[-1][1]["subagent"]["description"] == "map"


@pytest.mark.asyncio
async def test_parallel_subagents_keep_distinct_ids(make_runner):
    runner = make_runner()
    sends = []

    async def _capture(content, message_metadata=None):
        sends.append(message_metadata)

    runner.send_to_vicoa = _capture  # type: ignore

    runner._remember_tasks_in_message(_assistant_with_task("tu-a", "Explore", "A"))
    runner._remember_tasks_in_message(_assistant_with_task("tu-b", "Plan", "B"))
    await runner._maybe_handle_subagent_message(_child_assistant("tu-a", "x"))
    await runner._maybe_handle_subagent_message(_child_assistant("tu-b", "y"))
    ids = [m["subagent"]["tool_use_id"] for m in sends]
    assert ids == ["tu-a", "tu-b"]
    types = [m["subagent"]["subagent_type"] for m in sends]
    assert types == ["Explore", "Plan"]


@pytest.mark.asyncio
async def test_main_stream_message_is_not_diverted(make_runner):
    """parent_tool_use_id=None (main-stream) must fall through untouched —
    the "Using tool: Task" launch line still sends via the normal flat path,
    not through _maybe_handle_subagent_message."""
    runner = make_runner()
    sends = []

    async def _capture(content, message_metadata=None):
        sends.append((content, message_metadata))

    runner.send_to_vicoa = _capture  # type: ignore

    handled = await runner._maybe_handle_subagent_message(
        _assistant_with_task("tu-1", "Explore", "map")
    )
    assert handled is False
    assert sends == []


@pytest.mark.asyncio
async def test_child_user_message_tool_result_is_dropped_like_main_stream(make_runner):
    """Sub-agent tool-result UserMessages mirror the main stream, which drops
    every tool-result UserMessage via the blanket ``isinstance(message,
    UserMessage): continue`` skip. They are marked handled (so they never
    reach the flat-send path) but nothing is forwarded to Vicoa — the
    sub-agent's tool-use lines already convey what it did."""
    runner = make_runner()
    sends = []

    async def _capture(content, message_metadata=None):
        sends.append((content, message_metadata))

    runner.send_to_vicoa = _capture  # type: ignore

    runner._remember_tasks_in_message(_assistant_with_task("tu-1", "Explore", "map"))
    handled = await runner._maybe_handle_subagent_message(
        _child_tool_result("tu-1", "inner-tu-1", "file contents here")
    )
    assert handled is True
    assert sends == []


@pytest.mark.asyncio
async def test_unknown_task_id_falls_back_to_agent_label(make_runner):
    """A child message whose parent Task launch was never observed on this
    stream (e.g. resumed session) still gets diverted, labelled with the
    tracker's ("agent", "") default rather than crashing or falling flat."""
    runner = make_runner()
    sends = []

    async def _capture(content, message_metadata=None):
        sends.append((content, message_metadata))

    runner.send_to_vicoa = _capture  # type: ignore

    handled = await runner._maybe_handle_subagent_message(
        _child_assistant("tu-unknown", "hello")
    )
    assert handled is True
    assert sends[-1][1]["subagent"]["subagent_type"] == "agent"
    assert sends[-1][1]["subagent"]["tool_use_id"] == "tu-unknown"


# ---------------------------------------------------------------------------
# End-to-end: drive the ACTUAL receive_response() loop in
# run_conversation_turn, not just the helpers directly. This is the
# regression net for the wiring itself — a misplaced insertion (e.g. after
# the UserMessage-skip instead of before it) would pass every test above
# yet still drop or misroute real messages.
# ---------------------------------------------------------------------------


class _FakeClaudeClient:
    """Minimal stand-in for ``ClaudeSDKClient``: records ``query()`` calls
    and replays a fixed message sequence from ``receive_messages()``.

    ``receive_messages()`` is consumed by the runner's session-lifetime
    stream reader (``_run_stream_reader``). The generator parks forever once
    the script is exhausted, mirroring the real stream: it does not end at
    the last scripted message, so a reader that expects an end-of-stream
    hangs the test rather than passing by accident. Tests stop the reader
    with ``await runner._stop_stream_reader()`` when done.
    """

    def __init__(self, messages, park_when_exhausted: bool = True):
        self._messages = messages
        self._park_when_exhausted = park_when_exhausted
        self.queries = []

    async def query(self, query_input):
        self.queries.append(query_input)

    async def receive_messages(self):
        for message in self._messages:
            yield message
        if self._park_when_exhausted:
            await asyncio.Event().wait()


async def _wait_until(predicate, timeout: float = 5.0) -> None:
    """Poll until ``predicate()`` is truthy — for asserting on work the
    session-lifetime reader does *after* ``run_conversation_turn`` returned."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not met within timeout")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_receive_loop_diverts_children_and_keeps_main_stream_flat(make_runner):
    """Full ``run_conversation_turn`` pass: a Task launch on the main stream
    still sends flat (unwrapped metadata) and the sub-agent's own turn is
    diverted + tagged, while its tool-result ``UserMessage`` is dropped —
    mirroring the main stream, which drops every tool-result ``UserMessage``
    via the blanket ``isinstance(message, UserMessage): continue`` skip.
    """
    fake_vicoa = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake_vicoa)
    runner.conversation_started = False

    messages = [
        SystemMessage(subtype="init", data={"session_id": "sdk-sess-1"}),
        # Main-stream launch: parent_tool_use_id=None → flat send + remembered.
        _assistant_with_task("tu-1", "Explore", "map the code"),
        # Sub-agent's own turn: diverted + tagged.
        _child_assistant("tu-1", "reading files"),
        # Sub-agent's tool-result: dropped, mirroring the main stream's
        # blanket UserMessage skip. Its content must not be forwarded.
        _child_tool_result("tu-1", "inner-tu-1", "def foo(): ..."),
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="sdk-sess-1",
        ),
    ]
    runner.claude_client = _FakeClaudeClient(messages)

    sentinel = InboundUserMessage("next")

    async def _fake_wait_for_user_input():
        return sentinel

    runner._wait_for_user_input = _fake_wait_for_user_input  # type: ignore[assignment]

    result = await asyncio.wait_for(
        runner.run_conversation_turn(InboundUserMessage("go explore")), timeout=5
    )

    assert result is sentinel
    sent = fake_vicoa.sent_messages
    # Main-stream Task launch: flat, no subagent metadata.
    launch = next(
        c for c in sent if "Explore" in c["content"] or "Task" in c["content"]
    )
    assert launch["message_metadata"] is None

    # The sub-agent's own turn is diverted + tagged; its tool-result
    # UserMessage is dropped (mirrors the main-stream UserMessage skip).
    tagged = [
        c for c in sent if c["message_metadata"] and "subagent" in c["message_metadata"]
    ]
    assert len(tagged) == 1
    assert tagged[0]["message_metadata"]["subagent"]["tool_use_id"] == "tu-1"
    assert tagged[0]["message_metadata"]["subagent"]["subagent_type"] == "Explore"
    assert "reading files" in tagged[0]["content"]
    # The dropped tool-result's content is never forwarded to Vicoa.
    assert not any("def foo" in c["content"] for c in sent)
    await runner._stop_stream_reader()


# ---------------------------------------------------------------------------
# Background sub-agents (``run_in_background: true``).
#
# The Agent tool returns immediately, the agent ends its own turn, and the
# sub-agent keeps streaming afterwards. Verified against the real CLI: the
# main ``result`` lands ~1s after launch while the sub-agent's messages and
# its ``task_notification`` arrive seconds later, followed by a fresh ``init``
# turn in which the agent reports the outcome and a second ``result``.
#
# ``receive_response()`` would stop at the first ``result``, which (a) flipped
# the session to AWAITING_INPUT while the sub-agent was still running and (b)
# left everything after it buffered in the SDK until the next turn flushed it
# as one burst.
# ---------------------------------------------------------------------------


def _task_started(task_id: str, tool_use_id: str) -> TaskStartedMessage:
    return TaskStartedMessage(
        subtype="task_started",
        data={},
        task_id=task_id,
        description="do the thing",
        uuid="u-start",
        session_id="sdk-sess-1",
        tool_use_id=tool_use_id,
    )


def _task_notification(
    task_id: str, tool_use_id: str, summary: str, status: str = "completed"
) -> TaskNotificationMessage:
    return TaskNotificationMessage(
        subtype="task_notification",
        data={},
        task_id=task_id,
        status=status,
        output_file="/tmp/task.output",
        summary=summary,
        uuid="u-notify",
        session_id="sdk-sess-1",
        tool_use_id=tool_use_id,
    )


def _result() -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="sdk-sess-1",
    )


def _wire_runner(make_runner, messages):
    """A runner driving ``messages``, with a sentinel returned once the turn ends."""
    fake_vicoa = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake_vicoa)
    runner.conversation_started = False
    runner.claude_client = _FakeClaudeClient(messages)

    sentinel = InboundUserMessage("next")

    async def _fake_wait_for_user_input():
        return sentinel

    runner._wait_for_user_input = _fake_wait_for_user_input  # type: ignore[assignment]
    return runner, fake_vicoa, sentinel


@pytest.mark.asyncio
async def test_background_subagent_output_streams_after_turn_end(make_runner):
    """The turn ends at its own result even though a background sub-agent is
    still running — the run loop is free for the next user message — but the
    awaiting-input settle is deferred: the session stays working, the reader
    keeps forwarding the sub-agent's later output in real time, and the
    settle fires exactly once when the report turn completes."""
    messages = [
        SystemMessage(subtype="init", data={"session_id": "sdk-sess-1"}),
        _assistant_with_task("tu-1", "Explore", "map the code"),
        _task_started("task-1", "tu-1"),
        # Agent finishes its own turn without waiting on the sub-agent.
        _child_assistant_text_main("launched it, not waiting"),
        _result(),
        # --- everything below used to be stranded in the SDK buffer ---
        _child_assistant("tu-1", "reading files"),
        _task_notification("task-1", "tu-1", "Found 3 call sites."),
        _child_assistant_text_main("The background agent found 3 call sites."),
        _result(),
    ]
    runner, fake_vicoa, sentinel = _wire_runner(make_runner, messages)

    result = await asyncio.wait_for(
        runner.run_conversation_turn(InboundUserMessage("go")), timeout=5
    )
    assert result is sentinel

    # The reader forwards the post-result tail on its own; the settle fires
    # once, at the report turn's closing result.
    await _wait_until(lambda: len(fake_vicoa.mark_requires_input_calls) == 1)
    contents = [c["content"] for c in fake_vicoa.sent_messages]
    assert any("reading files" in c for c in contents)
    assert any("Found 3 call sites." in c for c in contents)
    assert any("The background agent found 3 call sites." in c for c in contents)
    assert len(fake_vicoa.mark_requires_input_calls) == 1
    assert runner._pending_background_tasks == set()
    await runner._stop_stream_reader()


@pytest.mark.asyncio
async def test_turn_ends_at_result_and_later_output_still_surfaces(make_runner):
    """A foreground sub-agent settles before the result, so the turn ends
    there — ordinary turns never wait. And output the CLI emits *after* the
    result is no longer stranded in the SDK buffer until the next user
    message: the reader forwards it as autonomous work."""
    messages = [
        SystemMessage(subtype="init", data={"session_id": "sdk-sess-1"}),
        _assistant_with_task("tu-1", "Explore", "map the code"),
        _task_started("task-1", "tu-1"),
        _child_assistant("tu-1", "reading files"),
        _task_notification("task-1", "tu-1", "All done."),
        _child_assistant_text_main("Here is what it found."),
        _result(),
        # Emitted after the turn closed; previously this sat unread until the
        # next user prompt flushed it (the "stuck UI" bug).
        _child_assistant_text_main("late output after the result"),
    ]
    runner, fake_vicoa, sentinel = _wire_runner(make_runner, messages)

    result = await asyncio.wait_for(
        runner.run_conversation_turn(InboundUserMessage("go")), timeout=5
    )

    assert result is sentinel
    contents = [c["content"] for c in fake_vicoa.sent_messages]
    assert any("All done." in c for c in contents)
    await _wait_until(
        lambda: any(
            "late output after the result" in c["content"]
            for c in fake_vicoa.sent_messages
        )
    )
    await runner._stop_stream_reader()


@pytest.mark.asyncio
async def test_subagent_result_is_forwarded_tagged(make_runner):
    """The sub-agent's actual conclusion reaches the session, grouped under
    the same tool_use_id as its steps and flagged ``role: result``."""
    runner = make_runner()
    sends = []

    async def _capture(content, message_metadata=None):
        sends.append((content, message_metadata))

    runner.send_to_vicoa = _capture  # type: ignore
    runner._remember_tasks_in_message(_assistant_with_task("tu-1", "Explore", "map"))

    await runner._send_subagent_result(
        _task_notification("task-1", "tu-1", "Found 3 call sites.")
    )

    content, metadata = sends[-1]
    assert content == "Found 3 call sites."
    assert metadata["subagent"] == {
        "tool_use_id": "tu-1",
        "subagent_type": "Explore",
        "description": "map",
        "role": "result",
    }


@pytest.mark.asyncio
async def test_failed_subagent_result_is_marked(make_runner):
    runner = make_runner()
    sends = []

    async def _capture(content, message_metadata=None):
        sends.append(content)

    runner.send_to_vicoa = _capture  # type: ignore

    await runner._send_subagent_result(
        _task_notification("task-1", "tu-1", "ran out of context", status="failed")
    )

    assert sends[-1] == "⚠️ Sub-agent failed\n\nran out of context"


@pytest.mark.asyncio
async def test_empty_subagent_summary_is_not_forwarded(make_runner):
    runner = make_runner()
    sends = []

    async def _capture(content, message_metadata=None):
        sends.append(content)

    runner.send_to_vicoa = _capture  # type: ignore

    await runner._send_subagent_result(_task_notification("task-1", "tu-1", "   "))
    await runner._send_subagent_result(_task_notification("task-1", "", "non-empty"))

    assert sends == []


@pytest.mark.asyncio
async def test_wedged_background_subagent_does_not_block_the_run_loop(make_runner):
    """A sub-agent that never reports back must not block anything: the turn
    ends at its own result and the run loop is immediately free for the next
    user message. The settle stays deferred (the sub-agent may still report);
    the status watchdog handles the truly-wedged case — see the next test."""
    messages = [
        SystemMessage(subtype="init", data={"session_id": "sdk-sess-1"}),
        _assistant_with_task("tu-1", "Explore", "map the code"),
        _task_started("task-1", "tu-1"),
        _result(),
        # No task_notification ever arrives; the fake then parks forever.
    ]
    runner, fake_vicoa, sentinel = _wire_runner(make_runner, messages)

    result = await asyncio.wait_for(
        runner.run_conversation_turn(InboundUserMessage("go")), timeout=5
    )

    assert result is sentinel
    assert runner._pending_background_tasks == {"task-1"}
    assert fake_vicoa.mark_requires_input_calls == []
    await runner._stop_stream_reader()


@pytest.mark.asyncio
async def test_watchdog_settles_wedged_background_work(make_runner, monkeypatch):
    """When background work goes permanently quiet, the status watchdog
    settles the row so the session isn't shown working forever. Status only:
    the stream reader is untouched, so a late report would still surface."""
    monkeypatch.setattr(
        "integrations.headless.claude_code._STATUS_WATCHDOG_INTERVAL", 0.02
    )
    monkeypatch.setattr(
        "integrations.headless.claude_code._STATUS_SETTLE_IDLE_SECONDS", 0.05
    )
    fake_vicoa = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake_vicoa)
    runner.last_message_id = "msg-1"
    runner._pending_background_tasks = {"task-1"}
    runner._last_stream_activity = asyncio.get_running_loop().time() - 1.0

    watchdog = asyncio.create_task(runner._run_status_watchdog())
    try:
        await _wait_until(lambda: fake_vicoa.mark_requires_input_calls == ["msg-1"])
    finally:
        watchdog.cancel()

    assert runner._pending_background_tasks == set()


@pytest.mark.asyncio
async def test_watchdog_defers_while_reply_pending(make_runner, monkeypatch):
    """Quiet-with-a-question-open is the human's time, not a wedge: the
    watchdog must never settle while an AskUserQuestion or permission reply
    is pending (the old give-up fired here and broke the AUQ flow)."""
    monkeypatch.setattr(
        "integrations.headless.claude_code._STATUS_WATCHDOG_INTERVAL", 0.02
    )
    monkeypatch.setattr(
        "integrations.headless.claude_code._STATUS_SETTLE_IDLE_SECONDS", 0.05
    )
    fake_vicoa = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake_vicoa)
    runner.last_message_id = "msg-1"
    runner._pending_background_tasks = {"task-1"}
    runner._last_stream_activity = asyncio.get_running_loop().time() - 1.0
    runner._auq_registry.create("req-1")

    watchdog = asyncio.create_task(runner._run_status_watchdog())
    try:
        await asyncio.sleep(0.2)
    finally:
        watchdog.cancel()
        runner._auq_registry.cancel("req-1")

    assert fake_vicoa.mark_requires_input_calls == []
    assert runner._pending_background_tasks == {"task-1"}
