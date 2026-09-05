"""Turn Pi-family runtime events into Vicoa ``messages`` rows.

Pure translation: the mapper owns no I/O and no lifecycle. It takes one frame
and returns the rows that frame implies, so it can be driven straight from the
archived wire traces in ``tests/fixtures/omp/*.jsonl``.

**Dispatch is on ``type`` with an explicit default that logs and drops.** Never
a closed union — see the note in ``rpc_types``; the measured wire already
carries several event types no published schema models, and a union would make
them disappear silently instead of showing up in a log.

Structural facts from the traces that this file depends on:

* Delta order inside ``message_update.assistantMessageEvent`` is
  ``thinking_start`` -> ``thinking_delta``* -> ``thinking_end`` ->
  ``text_start`` -> ``text_delta``* -> ``text_end``. The ``*_end`` events carry
  the block's complete ``content``, so rows are emitted there rather than
  reassembled from deltas — deltas are still accumulated as a fallback for a
  block that ends without one.
* ``contentIndex`` identifies the block within the message, and ``message_end``
  repeats every block. Emitting per block *and* per message would duplicate
  every row, so the mapper records which indices it has already written.
* A provider rejection is NOT a transport error: it arrives as an ordinary
  ``message_end`` with ``stopReason: "error"`` and the raw provider JSON in
  ``errorMessage``.
* A ``host_tool_call`` also emits the normal ``tool_execution_*`` triple, so
  host tools render as ordinary tool cards with no separate path here.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from integrations.headless.format_tools import format_tool_use
from integrations.headless.pi_family.rpc_types import (
    as_dict,
    as_list,
    as_str,
    assistant_event,
    message_error,
    message_role,
    message_stop_reason,
)
from integrations.headless.thinking import build_thinking_metadata


logger = logging.getLogger(__name__)


#: Cap on the tool-result tail folded into a chat row. Matches the 200-char
#: budget the Claude path uses for its ``Result:`` line — enough to see what
#: happened, short enough that a 10k-line file read doesn't bury the thread.
TOOL_RESULT_MAX_CHARS = 200

#: Lifecycle frames the session (not the mapper) acts on.
LIFECYCLE_TYPES = frozenset(
    {
        "agent_start",
        "agent_end",
        "agent_settled",
        "turn_start",
        "turn_end",
    }
)

#: Frames another module owns end-to-end. Listed so the default branch's
#: "unhandled" log stays a genuine signal rather than constant noise.
_HANDLED_ELSEWHERE = frozenset(
    {
        "available_commands_update",
        "extension_ui_request",
        "host_tool_call",
        "host_tool_cancel",
        "queue_update",
        "ready",
        "response",
        "rpc_chunk",
        "subagent_event",
        "subagent_lifecycle",
        "subagent_progress",
        "tool_stream_update",
        "bash_execution_update",
    }
)


@dataclass
class Emission:
    """One Vicoa ``messages`` row the caller should POST."""

    content: str
    metadata: Optional[dict] = None


@dataclass
class EventMapper:
    """Stateful translator for one session's event stream.

    ``agent_type`` is the display name stamped on rows (``"Pi"`` / ``"Oh My
    Pi"``); ``thinking_source`` is the catalog id recorded in the thinking
    card's metadata.
    """

    agent_type: str = "Pi"
    thinking_source: str = "pi"

    #: contentIndex values already written for the message being streamed.
    _emitted_indices: Set[int] = field(default_factory=set)
    #: Partial text/thinking per contentIndex, used only when a block ends
    #: without an ``*_end`` frame.
    _partials: Dict[int, str] = field(default_factory=dict)
    #: toolCallId -> the header we rendered at ``tool_execution_start``, so an
    #: ``_end`` row can name the tool without re-deriving it from args.
    _tool_headers: Dict[str, str] = field(default_factory=dict)
    #: Signature of the last todo list written. The same list reaches us twice
    #: — once as the ``todo`` tool's result, once as the ``todo_reminder`` the
    #: agent gets when it hasn't touched the list in a while — and a second
    #: identical card is pure noise.
    _last_todos: str = ""

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def handle(self, frame: Dict[str, Any]) -> List[Emission]:
        """Rows implied by ``frame``. Never raises on an unexpected shape."""
        frame_type = as_str(frame.get("type"))
        handler = _DISPATCH.get(frame_type)
        if handler is not None:
            try:
                return handler(self, frame)
            except Exception:
                logger.exception(
                    "pi_family mapper: handler for %s raised; dropping frame",
                    frame_type,
                )
                return []
        if frame_type in LIFECYCLE_TYPES or frame_type in _HANDLED_ELSEWHERE:
            return []
        logger.debug("pi_family mapper: unhandled event type=%s", frame_type)
        return []

    def reset_message(self) -> None:
        self._emitted_indices.clear()
        self._partials.clear()

    def reset(self) -> None:
        self.reset_message()
        self._tool_headers.clear()
        self._last_todos = ""

    # ------------------------------------------------------------------
    # Assistant streaming
    # ------------------------------------------------------------------

    def _on_message_start(self, frame: Dict[str, Any]) -> List[Emission]:
        if message_role(frame.get("message")) == "assistant":
            self.reset_message()
        return []

    def _on_message_update(self, frame: Dict[str, Any]) -> List[Emission]:
        event = assistant_event(frame)
        event_type = as_str(event.get("type"))
        index = event.get("contentIndex")
        if not isinstance(index, int):
            return []

        if event_type in {"text_delta", "thinking_delta"}:
            self._partials[index] = self._partials.get(index, "") + as_str(
                event.get("delta")
            )
            return []

        if event_type == "text_end":
            content = as_str(event.get("content")) or self._partials.pop(index, "")
            self._partials.pop(index, None)
            return self._emit_text(index, content)

        if event_type == "thinking_end":
            content = as_str(event.get("content")) or self._partials.pop(index, "")
            self._partials.pop(index, None)
            return self._emit_thinking(index, content)

        return []

    def _on_message_end(self, frame: Dict[str, Any]) -> List[Emission]:
        message = as_dict(frame.get("message"))
        role = message_role(message)
        if role != "assistant":
            # ``user`` echoes our own POST; ``toolResult`` duplicates what
            # ``tool_execution_end`` already rendered. Both would double up.
            self.reset_message()
            return []

        emissions: List[Emission] = []
        # Blocks that never produced an ``*_end`` (interrupted stream, or a
        # non-streaming provider) are written here from the final message.
        for index, block in enumerate(as_list(message.get("content"))):
            block_dict = as_dict(block)
            block_type = as_str(block_dict.get("type"))
            if block_type == "text":
                emissions.extend(self._emit_text(index, as_str(block_dict.get("text"))))
            elif block_type == "thinking":
                emissions.extend(
                    self._emit_thinking(index, as_str(block_dict.get("thinking")))
                )

        if message_stop_reason(message) == "error":
            emissions.append(
                Emission(content=_format_provider_error(message_error(message)))
            )
        self.reset_message()
        return emissions

    def _emit_text(self, index: int, content: str) -> List[Emission]:
        if index in self._emitted_indices:
            return []
        self._emitted_indices.add(index)
        content = content.strip()
        if not content:
            return []
        return [Emission(content=content)]

    def _emit_thinking(self, index: int, content: str) -> List[Emission]:
        if index in self._emitted_indices:
            return []
        self._emitted_indices.add(index)
        content = content.strip()
        if not content:
            # Thinking with `display: omitted` streams empty blocks; a row with
            # no body would render as a card the user can't open.
            return []
        return [
            Emission(
                content=content,
                metadata=build_thinking_metadata(self.thinking_source),
            )
        ]

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def _on_tool_start(self, frame: Dict[str, Any]) -> List[Emission]:
        tool_name = as_str(frame.get("toolName")) or "tool"
        args = as_dict(frame.get("args"))
        tool_call_id = as_str(frame.get("toolCallId"))
        header = _render_tool_header(tool_name, args, as_str(frame.get("intent")))
        if tool_call_id:
            self._tool_headers[tool_call_id] = header
        if tool_name == "todo":
            # The completed list rendered at ``_end`` says everything this
            # header would, and arrives within the same turn — so the header
            # alone would just be a duplicate card above the real one.
            return []
        return [Emission(content=header)]

    def _on_tool_end(self, frame: Dict[str, Any]) -> List[Emission]:
        tool_call_id = as_str(frame.get("toolCallId"))
        self._tool_headers.pop(tool_call_id, None)
        is_error = bool(frame.get("isError"))
        text = _tool_result_text(frame.get("result"))

        if as_str(frame.get("toolName")) == "todo" and not is_error:
            # The native todo tool's completed state is richer than the header
            # (which only names the operation), and Vicoa already renders a
            # TodoWrite card as "Todos". Prefer the card over a Result line.
            return self._emit_todos(_todos_from_result(frame.get("result")))

        if is_error:
            body = text or "the tool reported an error with no message"
            return [Emission(content=f"⚠️ Tool failed: {body}")]
        if not text:
            # A clean tool with no output needs no second row; the header
            # already told the user what ran.
            return []
        return [Emission(content=f"   Result: {_truncate(text)}")]

    def _on_todo_reminder(self, frame: Dict[str, Any]) -> List[Emission]:
        return self._emit_todos([as_dict(item) for item in as_list(frame.get("todos"))])

    def _emit_todos(self, todos: List[Dict[str, Any]]) -> List[Emission]:
        """Write a Todos card, skipping a list identical to the last one."""
        if not todos:
            return []
        signature = json.dumps(todos, sort_keys=True, default=str)
        if signature == self._last_todos:
            return []
        self._last_todos = signature
        return [Emission(content=format_tool_use("TodoWrite", {"todos": todos}))]

    # ------------------------------------------------------------------
    # Notices and lifecycle chatter
    # ------------------------------------------------------------------

    def _on_notice(self, frame: Dict[str, Any]) -> List[Emission]:
        """Surface a notice — but only when it is addressed to the user.

        ``info`` is dropped. Upstream's own contract for this event
        (``AgentSession.emitNotice``) is that it renders as
        ``showWarning`` / ``showError`` / **``showStatus``** — so the info tier
        is the TUI's transient status line, not conversation. Vicoa has no
        status line, and turning that chrome into permanent chat rows produced
        exactly the noise it looks like: every session opened with
        ``xd://: mounted vicoa_get_session, vicoa_read_session_transcript, …``
        from the ``xdev`` extension announcing that our own host tools had been
        mounted. Nothing there is actionable, and it pushed the user's first
        real message off screen.

        Warnings and errors still come through: those are the tiers upstream
        reserves for conditions the user should actually see.
        """
        level = as_str(frame.get("level"))
        if level not in {"warning", "error"}:
            logger.debug(
                "pi_family mapper: dropping %s notice from %s: %s",
                level or "info",
                as_str(frame.get("source")) or "session",
                as_str(frame.get("message"))[:120],
            )
            return []
        message = as_str(frame.get("message")).strip()
        if not message:
            return []
        icon = "⚠️" if level == "warning" else "❌"
        source = as_str(frame.get("source"))
        suffix = f" _({source})_" if source else ""
        return [Emission(content=f"{icon} {message}{suffix}")]

    def _on_goal_updated(self, frame: Dict[str, Any]) -> List[Emission]:
        goal = frame.get("goal")
        if goal is None:
            return [Emission(content="🎯 Goal cleared")]
        text = as_str(as_dict(goal).get("text")) or as_str(
            as_dict(goal).get("description")
        )
        if not text:
            return []
        return [Emission(content=f"🎯 Goal: {text}")]

    def _on_auto_retry_start(self, frame: Dict[str, Any]) -> List[Emission]:
        attempt = frame.get("attempt")
        max_attempts = frame.get("maxAttempts")
        error = as_str(frame.get("errorMessage")).strip()
        head = f"🔁 Retrying ({attempt}/{max_attempts})"
        return [Emission(content=f"{head}: {error}" if error else head)]

    def _on_auto_retry_end(self, frame: Dict[str, Any]) -> List[Emission]:
        if frame.get("success"):
            # A recovered blip is noise; the retry notice already went out.
            return []
        final = as_str(frame.get("finalError")).strip()
        return [Emission(content=f"⚠️ Retries exhausted{f': {final}' if final else ''}")]

    def _on_retry_fallback_applied(self, frame: Dict[str, Any]) -> List[Emission]:
        return [
            Emission(
                content=(
                    f"🔀 Falling back from `{as_str(frame.get('from'))}` to "
                    f"`{as_str(frame.get('to'))}`"
                )
            )
        ]

    def _on_retry_fallback_succeeded(self, frame: Dict[str, Any]) -> List[Emission]:
        return [Emission(content=f"✅ Recovered on `{as_str(frame.get('model'))}`")]

    def _on_compaction_start(self, _frame: Dict[str, Any]) -> List[Emission]:
        return [Emission(content="🗜️ Compacting the conversation…")]

    def _on_compaction_end(self, frame: Dict[str, Any]) -> List[Emission]:
        if frame.get("aborted"):
            return [Emission(content="🗜️ Compaction aborted")]
        if frame.get("skipped"):
            return []
        error = as_str(frame.get("errorMessage")).strip()
        if error:
            return [Emission(content=f"⚠️ Compaction failed: {error}")]
        return [Emission(content="🗜️ Conversation compacted")]

    def _on_auto_compaction_start(self, frame: Dict[str, Any]) -> List[Emission]:
        reason = as_str(frame.get("reason"))
        suffix = f" ({reason})" if reason else ""
        return [Emission(content=f"🗜️ Auto-compacting the conversation{suffix}…")]

    def _on_thinking_level_changed(self, frame: Dict[str, Any]) -> List[Emission]:
        level = as_str(frame.get("thinkingLevel")) or as_str(frame.get("resolved"))
        if not level:
            return []
        return [Emission(content=f"🧠 Thinking level: {level}")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render_tool_header(tool_name: str, args: Dict[str, Any], intent: str) -> str:
    """The ``🔧 Using tool: …`` line the dashboard's tool card parses.

    ``intent`` is a gift from the protocol: a human-readable label the agent
    already wrote for this exact call (``"Reading sample.txt"``). It is better
    than anything we would synthesize from ``args``, so it wins when present.
    """
    display = _display_tool_name(tool_name)
    if intent.strip():
        return f"🔧 Using tool: {display} - {intent.strip()}"
    summary = _summarize_args(args)
    return (
        f"🔧 Using tool: {display} - {summary}"
        if summary
        else (f"🔧 Using tool: {display}")
    )


#: Pi-family tool names -> the names Vicoa's clients already have affordances
#: for. Only where the semantics genuinely match; anything else keeps its own
#: name rather than being forced into a Claude-shaped card.
_TOOL_NAME_ALIASES = {
    "read": "Read",
    "write": "Write",
    "edit": "Edit",
    "bash": "Bash",
    "todo": "TodoWrite",
    "task": "Task",
    "glob": "Glob",
    "grep": "Grep",
    "list": "LS",
    "webfetch": "WebFetch",
    "websearch": "WebSearch",
}


def _display_tool_name(tool_name: str) -> str:
    return _TOOL_NAME_ALIASES.get(tool_name.lower(), tool_name)


def _summarize_args(args: Dict[str, Any]) -> str:
    """One-line argument summary for a tool with no ``intent``."""
    for key in ("path", "file_path", "filePath", "command", "pattern", "query", "url"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return f"`{value.strip()}`"
    if not args:
        return ""
    try:
        rendered = json.dumps(args, ensure_ascii=False)
    except (TypeError, ValueError):
        rendered = str(args)
    return f"`{_truncate(rendered, 120)}`"


def _tool_result_text(result: Any) -> str:
    """Flatten an ``AgentToolResult`` into plain text.

    Shape is ``{content: [{type: "text", text}], details: {...}}``; ``details``
    is structured data for the agent, not for a chat row.
    """
    parts: List[str] = []
    for block in as_list(as_dict(result).get("content")):
        block_dict = as_dict(block)
        if block_dict.get("type") == "text":
            text = as_str(block_dict.get("text"))
            if text:
                parts.append(text)
    if parts:
        return "\n".join(parts).strip()
    if isinstance(result, str):
        return result.strip()
    return ""


def _todos_from_result(result: Any) -> List[Dict[str, Any]]:
    """Flatten the todo tool's ``details.phases[].tasks[]`` into todo items."""
    details = as_dict(as_dict(result).get("details"))
    todos: List[Dict[str, Any]] = []
    for phase in as_list(details.get("phases")):
        for task in as_list(as_dict(phase).get("tasks")):
            task_dict = as_dict(task)
            content = as_str(task_dict.get("content"))
            if content:
                todos.append(
                    {"content": content, "status": as_str(task_dict.get("status"))}
                )
    return todos


def _truncate(text: str, limit: int = TOOL_RESULT_MAX_CHARS) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _format_provider_error(raw: str) -> str:
    """Render a provider failure, unwrapping the JSON body when there is one.

    The message is usually the provider's raw HTTP error body, e.g.
    ``{"type":"error","error":{"type":"authentication_error","message":"..."}}``.
    Showing the nested ``message`` is far more useful than the envelope.
    """
    message = raw.strip() or "the model provider returned an error"
    try:
        decoded = json.loads(message)
    except (ValueError, TypeError):
        decoded = None
    if isinstance(decoded, dict):
        inner = decoded.get("error")
        if isinstance(inner, dict) and isinstance(inner.get("message"), str):
            message = inner["message"]
        elif isinstance(decoded.get("message"), str):
            message = decoded["message"]
    return f"⚠️ **Model provider error**\n\n{message}"


_DISPATCH = {
    "message_start": EventMapper._on_message_start,
    "message_update": EventMapper._on_message_update,
    "message_end": EventMapper._on_message_end,
    "tool_execution_start": EventMapper._on_tool_start,
    "tool_execution_end": EventMapper._on_tool_end,
    "todo_reminder": EventMapper._on_todo_reminder,
    "notice": EventMapper._on_notice,
    "goal_updated": EventMapper._on_goal_updated,
    "auto_retry_start": EventMapper._on_auto_retry_start,
    "auto_retry_end": EventMapper._on_auto_retry_end,
    "retry_fallback_applied": EventMapper._on_retry_fallback_applied,
    "retry_fallback_succeeded": EventMapper._on_retry_fallback_succeeded,
    "compaction_start": EventMapper._on_compaction_start,
    "compaction_end": EventMapper._on_compaction_end,
    "auto_compaction_start": EventMapper._on_auto_compaction_start,
    "auto_compaction_end": EventMapper._on_compaction_end,
    "thinking_level_changed": EventMapper._on_thinking_level_changed,
}
# ``tool_execution_update`` deliberately has no entry: it fires many times per
# call (48 times for one subagent run in the archived trace) and carries only
# a partial of what ``_end`` delivers in full.


__all__ = ["Emission", "EventMapper", "TOOL_RESULT_MAX_CHARS"]
