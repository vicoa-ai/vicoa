"""Metadata contract for agent "thinking" / reasoning cards.

Both Claude (the SDK's ``ThinkingBlock``) and Codex (a ``reasoning`` ThreadItem)
surface the model's internal reasoning. Historically the two paths disagreed:
the Claude headless path dropped thinking entirely (``format_message_content``
has no ``ThinkingBlock`` branch), while Codex dumped it inline as a
``🧠 Reasoning:`` agent bubble. Both now POST the reasoning as a normal
``messages`` row whose ``message_metadata.thinking`` marks it so clients render
a *collapsed* "Thinking" card instead of a plain agent message.

Wire contract (mirrors ``subagent.build_metadata`` — structure in the metadata,
text in the row ``content``):

    message_metadata = {"thinking": {"source": "claude" | "codex"}}

The reasoning text rides in the row ``content`` so clients that predate the
card degrade gracefully to inline text (exactly the old Codex behaviour). The
metadata is a structural *marker*, not a copy of the text — clients check for
the key's presence and wrap ``content`` in a collapsed disclosure.
"""

from __future__ import annotations


def build_thinking_metadata(source: str) -> dict:
    """``message_metadata`` marking a row as an agent "thinking" card.

    ``source`` is the producing agent (``"claude"`` / ``"codex"``) — purely
    informational today; clients only test for the ``thinking`` key's presence.
    """
    return {"thinking": {"source": source}}


__all__ = ["build_thinking_metadata"]
