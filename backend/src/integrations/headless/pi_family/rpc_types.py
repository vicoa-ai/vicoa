"""Permissive readers for Pi-family RPC payloads.

**Every shape here is extra-allow, and there is no closed union anywhere.**
That is a deliberate response to measurement, not caution for its own sake:
the archived traces (``tests/fixtures/omp/``) disagree with paseo's pinned
schemas in seven places within one minor-version band — ``turn_end`` is a real
event absent from their union, ``tool_execution_start`` carries a ready-made
``intent``, ``todo_reminder`` gained ``attempt``/``maxAttempts``,
``available_commands_update`` commands gained ``subcommands``, ``subagent_event``
carries event types they never modelled, and both ``get_session_stats`` and
``get_state.model`` return substantially more fields. Because paseo parses with
a discriminated union, each of those unmodelled types silently vanishes.

So: dispatch on ``type`` with an explicit default branch that logs and drops
(see ``event_mapper.py``), and read individual fields defensively here. These
are plain accessor functions rather than dataclasses precisely so an unknown
sibling key can never cause a drop.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence


def as_dict(value: Any) -> Dict[str, Any]:
    """``value`` when it is a mapping, else ``{}``."""
    return dict(value) if isinstance(value, Mapping) else {}


def as_list(value: Any) -> List[Any]:
    """``value`` when it is a non-string sequence, else ``[]``."""
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def as_str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def as_int(value: Any) -> Optional[int]:
    # bool is an int subclass; a flag is never a count.
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def as_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


def message_role(message: Any) -> str:
    """Role of an ``AgentMessage``: user / assistant / toolResult / custom / …"""
    return as_str(as_dict(message).get("role"))


def message_text(message: Any) -> str:
    """Concatenate the ``text`` blocks of a message's content.

    Assistant content is a list of ``{type: text|thinking|toolCall}`` blocks;
    only ``text`` is user-facing prose. Thinking is surfaced separately as a
    collapsed card, and tool calls as tool cards.
    """
    parts: List[str] = []
    for block in as_list(as_dict(message).get("content")):
        block_dict = as_dict(block)
        if block_dict.get("type") == "text":
            text = as_str(block_dict.get("text"))
            if text:
                parts.append(text)
    return "\n".join(parts)


def message_thinking(message: Any) -> str:
    """Concatenate the ``thinking`` blocks of a message's content."""
    parts: List[str] = []
    for block in as_list(as_dict(message).get("content")):
        block_dict = as_dict(block)
        if block_dict.get("type") == "thinking":
            text = as_str(block_dict.get("thinking"))
            if text:
                parts.append(text)
    return "\n".join(parts)


def message_stop_reason(message: Any) -> str:
    return as_str(as_dict(message).get("stopReason"))


def message_error(message: Any) -> str:
    """Provider failure text from a message.

    A provider rejection does NOT arrive as a transport error: the turn ends
    with a normal ``message_end`` whose ``stopReason`` is ``error`` and whose
    ``errorMessage`` holds the raw provider JSON. Without reading it the user
    sees a turn that simply produced nothing.
    """
    return as_str(as_dict(message).get("errorMessage"))


# ---------------------------------------------------------------------------
# Streaming deltas
# ---------------------------------------------------------------------------


def assistant_event(frame: Any) -> Dict[str, Any]:
    """The ``assistantMessageEvent`` carried by a ``message_update`` frame."""
    return as_dict(as_dict(frame).get("assistantMessageEvent"))


# ---------------------------------------------------------------------------
# Usage / stats
# ---------------------------------------------------------------------------


def context_from_session_stats(stats: Any) -> Optional[dict]:
    """Vicoa ``usage.context`` blob from a ``get_session_stats`` payload.

    Measured shape (omp 18.1.10)::

        {sessionId, userMessages, assistantMessages, toolCalls, toolResults,
         totalMessages, tokens: {input, output, reasoning, cacheRead,
         cacheWrite, total}, cost, premiumRequests,
         contextUsage: {tokens, contextWindow, percent}}

    ``contextUsage`` is a point-in-time reading of the window (not a running
    sum), which is exactly what the meter wants — see the long note in
    ``usage.claude_context_used_tokens`` on why accumulating is wrong.
    """
    stats_dict = as_dict(stats)
    usage = as_dict(stats_dict.get("contextUsage"))
    used = as_int(usage.get("tokens"))
    window = as_int(usage.get("contextWindow"))
    cost = as_float(stats_dict.get("cost"))
    if used is None and window is None and cost is None:
        return None
    return {
        "used_tokens": int(used or 0),
        "max_tokens": window,
        "cost_usd": cost,
    }


def context_from_state(state: Any) -> Optional[dict]:
    """Same blob, sourced from ``get_state`` (which also carries contextUsage)."""
    state_dict = as_dict(state)
    usage = as_dict(state_dict.get("contextUsage"))
    used = as_int(usage.get("tokens"))
    window = as_int(usage.get("contextWindow")) or as_int(
        as_dict(state_dict.get("model")).get("contextWindow")
    )
    if used is None and window is None:
        return None
    return {"used_tokens": int(used or 0), "max_tokens": window, "cost_usd": None}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def qualified_model_id(model: Any) -> str:
    """The ``provider/id`` selection key for one ``Model``.

    ``set_model`` takes provider and id separately, and two providers can serve
    the same model id, so the qualified form is what the picker must key on.
    Built in exactly one place so the live model list and the "which model am I
    on" reading can never disagree — a mismatch there renders the gear as if
    nothing were selected.
    """
    model_dict = as_dict(model)
    model_id = as_str(model_dict.get("id"))
    if not model_id:
        return ""
    provider = as_str(model_dict.get("provider"))
    return f"{provider}/{model_id}" if provider else model_id


def model_entries(models: Any) -> List[Dict[str, str]]:
    """``[{id, label}]`` for the mid-session gear, from a ``Model[]``.

    Both agents proxy many providers whose real list is per-machine config, so
    this live list — not the static catalog — is the authoritative one, exactly
    as it is for OpenCode.

    ``label`` is the model's display name alone. The provider is deliberately
    NOT appended: the clients render the qualified id right after the label in
    a muted tone, so a ``"Claude Haiku 4.5 (anthropic)"`` label would read
    ``Claude Haiku 4.5 (anthropic) anthropic/claude-haiku-4-5-20251001`` — the
    provider twice, and still nothing to tell two Haiku builds apart, which is
    the one thing a user picking between them needs.
    """
    entries: List[Dict[str, str]] = []
    seen: set[str] = set()
    for model in as_list(models):
        model_dict = as_dict(model)
        entry_id = qualified_model_id(model_dict)
        if not entry_id or entry_id in seen:
            continue
        seen.add(entry_id)
        name = as_str(model_dict.get("name")) or as_str(model_dict.get("id"))
        entries.append({"id": entry_id, "label": name})
    return entries


def split_model_id(model_id: str) -> tuple[Optional[str], str]:
    """Split a ``provider/id`` selection into ``(provider, id)``.

    ``set_model`` takes the two separately. A bare id (no slash) leaves the
    provider unset so the caller can resolve it from the live model list.
    """
    if "/" in model_id:
        provider, _, rest = model_id.partition("/")
        if provider and rest:
            return provider, rest
    return None, model_id


__all__ = [
    "as_dict",
    "as_float",
    "as_int",
    "as_list",
    "as_str",
    "assistant_event",
    "context_from_session_stats",
    "context_from_state",
    "message_error",
    "message_role",
    "message_stop_reason",
    "message_text",
    "message_thinking",
    "model_entries",
    "qualified_model_id",
    "split_model_id",
]
