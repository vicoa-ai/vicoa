"""Regression tests for the Stop / interrupt path.

Two user-reported bugs, both in ``HeadlessClaudeRunner``:

1. **Status stuck on ACTIVE.** ``_handle_interrupt`` wrote
   ``status=AWAITING_INPUT`` and *then* POSTed its "Interrupted" notice.
   Every agent-message POST goes through ``create_agent_message``, which sets
   ``instance.status = ACTIVE`` whenever ``requires_user_input`` is False - so
   the notice immediately undid the status write and the dashboard sat on
   "active" with nothing running.

2. **The next message got the previous turn's answer.** The old per-turn
   stream loop stopped reading on interrupt without consuming the aborted
   turn's closing ``ResultMessage``, and the *next* turn read it first: the
   user's message ended instantly with no agent content (falling through to
   the "What would you like me to do next?" fallback) and its real answer
   only surfaced one turn later, attached to the wrong prompt. The
   session-lifetime reader now keeps consuming through the interrupt
   (suppressing forwarding until the closing result), and a result with no
   open turn is dropped as stale — so the misalignment cannot re-occur.

``_StatefulFakeClaudeClient`` below is what makes (2) testable - it models the
SDK's shared cursor, so a regression in the stale-result handling reproduces
the original misalignment rather than silently passing.
"""

from __future__ import annotations

import asyncio
from typing import Any, List

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from integrations.headless.claude_code import InboundUserMessage

from _fakes import FakeAsyncVicoaClient


def _result(session_id: str = "sdk-sess-1") -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id=session_id,
    )


def _assistant(text: str) -> AssistantMessage:
    return AssistantMessage(content=[TextBlock(text=text)], model="claude-test")


class _StatefulFakeClaudeClient:
    """``ClaudeSDKClient`` double with the real SDK's *shared* buffer semantics.

    The production client reads the CLI into one anyio stream; every
    ``receive_messages()`` call is a fresh view over that same stream, not a
    fresh copy of the messages. The naive fake (a generator restarted from a
    list on each call) hides exactly the bug this module tests, so here the
    cursor lives on the instance and is shared across views.

    ``park_when_exhausted`` mirrors the real stream never ending on its own:
    a turn that fails to stop for the right reason hangs the test instead of
    passing by accident.
    """

    def __init__(self, messages: List[Any], park_when_exhausted: bool = True) -> None:
        self._messages = list(messages)
        self._cursor = 0
        self._park_when_exhausted = park_when_exhausted
        self.queries: List[Any] = []
        self.interrupts = 0
        # Optional hook fired on every ``query()`` — lets a test model the
        # CLI *responding* to a prompt (extend the script causally, the way
        # the real CLI only answers after being asked).
        self.on_query = None

    def extend(self, messages: List[Any]) -> None:
        """Append what the CLI emits later (e.g. the next turn's reply)."""
        self._messages.extend(messages)

    async def query(self, query_input: Any) -> None:
        self.queries.append(query_input)
        if self.on_query is not None:
            self.on_query(query_input)

    async def interrupt(self) -> None:
        self.interrupts += 1

    async def receive_messages(self):
        while True:
            if self._cursor < len(self._messages):
                message = self._messages[self._cursor]
                self._cursor += 1
                yield message
                continue
            if not self._park_when_exhausted:
                return
            # Poll rather than park on a dead event: ``extend()`` may add
            # the next turn's messages later, exactly like the real CLI
            # writing more output to the shared stream.
            await asyncio.sleep(0.01)

    @property
    def remaining(self) -> List[Any]:
        """Messages still parked in the shared buffer."""
        return self._messages[self._cursor :]


def _prime_for_turn(runner) -> None:
    """Attributes ``run_conversation_turn`` touches that conftest omits."""
    runner.conversation_started = True
    runner.last_message_id = None
    runner._last_sdk_session_id = None


# ---------------------------------------------------------------------------
# Bug 1 - ordering: the notice must be POSTed before the status write.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_interrupt_posts_notice_before_awaiting_input_write(make_runner):
    """The AWAITING_INPUT write must be the *last* thing the interrupt does.

    Reversed (the original order), the notice POST re-opens the row as ACTIVE
    and the session shows "active" forever after a Stop.
    """
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    runner.claude_client = _StatefulFakeClaudeClient([])

    await runner._handle_interrupt()

    assert runner.interrupt_requested is True
    assert fake.call_log == ["send_message", "status:AWAITING_INPUT"]
    assert "Interrupted" in fake.sent_messages[0]["content"]
    # Never via requires_user_input=True - that path fires push/email/SMS, and
    # the user pressing Stop is already looking at the app.
    assert fake.sent_messages[0]["requires_user_input"] is False


@pytest.mark.asyncio
async def test_interrupt_is_idempotent(make_runner):
    """A double-tapped Stop must not post the notice twice."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    runner.claude_client = _StatefulFakeClaudeClient([])

    await runner._handle_interrupt()
    await runner._handle_interrupt()

    assert len(fake.sent_messages) == 1
    assert runner.claude_client.interrupts == 1


@pytest.mark.asyncio
async def test_turn_resettles_awaiting_input_after_racing_post(make_runner):
    """A message POSTed between the Stop and the loop break re-opens the row as
    ACTIVE, so the turn re-asserts AWAITING_INPUT once it has unwound."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    _prime_for_turn(runner)

    client = _StatefulFakeClaudeClient([_assistant("partial work"), _result()])
    runner.claude_client = client

    async def _interrupt_after_first_message(content, message_metadata=None):
        # Stands in for the WS control message landing mid-stream.
        await runner._handle_interrupt()

    runner.send_to_vicoa = _interrupt_after_first_message  # type: ignore[assignment]

    result = await asyncio.wait_for(
        runner.run_conversation_turn(InboundUserMessage("do a thing")), timeout=5
    )

    assert result is None
    # Turn start now marks the row ACTIVE (mirrors the ACP dequeue), then the
    # interrupt's own write, then the post-unwind re-assert. What matters for
    # this regression is that the *last* write is AWAITING_INPUT — a Stop must
    # never leave the row stuck on ACTIVE.
    assert [c["status"] for c in fake.status_calls] == [
        "ACTIVE",
        "AWAITING_INPUT",
        "AWAITING_INPUT",
    ]
    assert fake.call_log[-1] == "status:AWAITING_INPUT"
    await runner._stop_stream_reader()


# ---------------------------------------------------------------------------
# Bug 2 - the aborted turn's leftovers must not reach the next turn.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_result_with_no_open_turn_is_dropped(make_runner):
    """A ResultMessage arriving with no open turn (interrupt force-close beat
    it, or a reconnect cleared state) must be dropped — letting it close a
    *later* turn is exactly the lag-by-one bug."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    _prime_for_turn(runner)

    assert not runner._open_turns
    await runner._process_sdk_message(_result())

    # Dropped: no settle, no status write, no forward.
    assert fake.sent_messages == []
    assert fake.mark_requires_input_calls == []
    assert not runner._open_turns


@pytest.mark.asyncio
async def test_interrupted_turn_forces_closed_when_no_result_comes(
    make_runner, monkeypatch
):
    """A CLI that never closes an interrupted turn must not wedge the run
    loop: ``_await_foreground_turn_close`` forces the close after the
    interrupt timeout (the reader stays on the stream either way)."""
    monkeypatch.setattr(
        "integrations.headless.claude_code._INTERRUPT_RESULT_TIMEOUT", 0.05
    )
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    _prime_for_turn(runner)
    # No ResultMessage will ever arrive; the stream just parks.
    client = _StatefulFakeClaudeClient([_assistant("...")])
    runner.claude_client = client

    async def _interrupt_on_first_forward(content, message_metadata=None):
        await runner._handle_interrupt()

    runner.send_to_vicoa = _interrupt_on_first_forward  # type: ignore[assignment]

    result = await asyncio.wait_for(
        runner.run_conversation_turn(InboundUserMessage("do a thing")), timeout=5
    )

    assert result is None
    assert not runner._open_turns
    await runner._stop_stream_reader()


@pytest.mark.asyncio
async def test_message_after_interrupt_gets_its_own_reply(make_runner):
    """The end-to-end regression for the reported mismatch.

    Turn 1 is interrupted mid-stream. Turn 2 must render turn 2's reply - not
    the aborted turn's stale ResultMessage, which previously ended turn 2
    instantly with no content and emitted the "What would you like me to do
    next?" fallback while turn 2's real answer waited for turn 3.
    """
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    _prime_for_turn(runner)

    # Turn 1: one assistant message, then the Stop lands, then the CLI closes
    # the aborted turn out with its own trailing content + result.
    client = _StatefulFakeClaudeClient(
        [_assistant("working on turn one"), _assistant("cut off"), _result()]
    )
    runner.claude_client = client

    forwarded: List[str] = []
    interrupted_once = False

    async def _capture(content, message_metadata=None):
        nonlocal interrupted_once
        forwarded.append(content)
        runner.last_message_id = f"msg-{len(forwarded)}"
        if not interrupted_once:
            interrupted_once = True
            await runner._handle_interrupt()

    runner.send_to_vicoa = _capture  # type: ignore[assignment]

    turn_one = await asyncio.wait_for(
        runner.run_conversation_turn(InboundUserMessage("turn one")), timeout=5
    )
    assert turn_one is None
    assert forwarded == ["working on turn one"]

    # Turn 2: the CLI answers the new message. Extended from the query hook
    # so the reply appears only after the prompt is sent — extending earlier
    # would model a CLI that answers before being asked, and the reader
    # (correctly) treats unsolicited output as autonomous work.
    client.on_query = lambda _q: client.extend(
        [_assistant("answer to turn two"), _result()]
    )

    sentinel = InboundUserMessage("later")

    async def _fake_wait_for_user_input():
        return sentinel

    runner._wait_for_user_input = _fake_wait_for_user_input  # type: ignore[assignment]

    turn_two = await asyncio.wait_for(
        runner.run_conversation_turn(InboundUserMessage("turn two")), timeout=5
    )

    assert turn_two is sentinel
    assert forwarded[1:] == ["answer to turn two"]
    assert "What would you like me to do next?" not in forwarded
    await runner._stop_stream_reader()
