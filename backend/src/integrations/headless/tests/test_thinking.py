"""Tests for surfacing model reasoning as a collapsed "thinking" card.

Covers the Claude headless path: ``_thinking_text`` extraction plus the
main-stream and sub-agent emit paths that POST the reasoning as a
metadata-tagged row (``message_metadata.thinking``) ahead of the turn's
text/tool-use. The Codex reasoning path is covered in
``test_codex_app_server.py``.
"""

from __future__ import annotations

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    TextBlock,
    ThinkingBlock,
)

from integrations.headless.claude_code import HeadlessClaudeRunner
from integrations.headless.thinking import build_thinking_metadata


def _thinking(text: str) -> ThinkingBlock:
    return ThinkingBlock(thinking=text, signature="sig")


def _assistant(content, parent_tool_use_id=None) -> AssistantMessage:
    return AssistantMessage(
        content=content, model="claude-test", parent_tool_use_id=parent_tool_use_id
    )


# --- metadata contract -----------------------------------------------------


def test_build_thinking_metadata_shape():
    assert build_thinking_metadata("claude") == {"thinking": {"source": "claude"}}
    assert build_thinking_metadata("codex") == {"thinking": {"source": "codex"}}


# --- _thinking_text extraction ---------------------------------------------


def test_thinking_text_extracts_thinking_before_text():
    msg = _assistant([_thinking("weighing options"), TextBlock(text="the answer")])
    assert HeadlessClaudeRunner._thinking_text(msg) == "weighing options"


def test_thinking_text_joins_multiple_blocks():
    msg = _assistant([_thinking("first"), _thinking("second")])
    assert HeadlessClaudeRunner._thinking_text(msg) == "first\n\nsecond"


def test_thinking_text_empty_without_thinking():
    assert HeadlessClaudeRunner._thinking_text(_assistant([TextBlock(text="hi")])) == ""


def test_thinking_text_empty_when_display_omitted():
    # display="omitted" models (Opus 4.7+ / Fable 5) emit a signature-only
    # block with empty ``thinking`` — nothing to show.
    msg = _assistant([ThinkingBlock(thinking="", signature="sig")])
    assert HeadlessClaudeRunner._thinking_text(msg) == ""


# --- main-stream emit ------------------------------------------------------


@pytest.mark.asyncio
async def test_main_stream_thinking_card_precedes_text(make_runner):
    runner = make_runner()
    sends = []

    async def _capture(content, message_metadata=None):
        sends.append((content, message_metadata))

    runner.send_to_vicoa = _capture  # type: ignore[assignment]

    await runner._process_sdk_message(
        _assistant([_thinking("let me think"), TextBlock(text="done")])
    )

    # Thinking card first (tagged), then the plain text.
    assert sends[0] == ("let me think", {"thinking": {"source": "claude"}})
    assert sends[1] == ("done", None)


@pytest.mark.asyncio
async def test_main_stream_no_card_without_thinking(make_runner):
    runner = make_runner()
    sends = []

    async def _capture(content, message_metadata=None):
        sends.append((content, message_metadata))

    runner.send_to_vicoa = _capture  # type: ignore[assignment]

    await runner._process_sdk_message(_assistant([TextBlock(text="just text")]))

    assert sends == [("just text", None)]


# --- sub-agent emit --------------------------------------------------------


@pytest.mark.asyncio
async def test_subagent_thinking_card_is_tagged_with_both_keys(make_runner):
    runner = make_runner()
    sends = []

    async def _capture(content, message_metadata=None):
        sends.append((content, message_metadata))

    runner.send_to_vicoa = _capture  # type: ignore[assignment]
    runner._subagent_tracker.remember_task("tu-1", "Explore", "map")

    handled = await runner._maybe_handle_subagent_message(
        _assistant(
            [_thinking("sub reasoning"), TextBlock(text="found it")],
            parent_tool_use_id="tu-1",
        )
    )

    assert handled is True
    # Thinking card carries BOTH subagent grouping and the thinking marker.
    thinking_content, thinking_md = sends[0]
    assert thinking_content == "sub reasoning"
    assert thinking_md["thinking"] == {"source": "claude"}
    assert thinking_md["subagent"]["tool_use_id"] == "tu-1"
    assert thinking_md["subagent"]["subagent_type"] == "Explore"
    # Then the sub-agent's own text, tagged with subagent only (no thinking).
    text_content, text_md = sends[1]
    assert text_content == "found it"
    assert "thinking" not in text_md
    assert text_md["subagent"]["tool_use_id"] == "tu-1"


@pytest.mark.asyncio
async def test_subagent_thinking_only_turn_still_surfaces(make_runner):
    """A sub-agent turn that is thinking-only (no text/tool) still POSTs the
    thinking card rather than being dropped as an empty child turn."""
    runner = make_runner()
    sends = []

    async def _capture(content, message_metadata=None):
        sends.append((content, message_metadata))

    runner.send_to_vicoa = _capture  # type: ignore[assignment]
    runner._subagent_tracker.remember_task("tu-1", "Explore", "map")

    handled = await runner._maybe_handle_subagent_message(
        _assistant([_thinking("quietly reasoning")], parent_tool_use_id="tu-1")
    )

    assert handled is True
    assert len(sends) == 1
    assert sends[0][0] == "quietly reasoning"
    assert sends[0][1]["thinking"] == {"source": "claude"}
