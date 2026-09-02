"""Render Codex ``ThreadItem`` payloads to vicoa message text.

Returns ``None`` for items that should not surface as a vicoa ``messages``
row (e.g. ``userMessage`` echoes the wrapper already wrote, intercepted
plan_mode plans).

Scope of this slice: ``agentMessage``. Other variants (reasoning,
commandExecution, fileChange, mcpToolCall, webSearch, collabAgentToolCall,
image, plan, dynamicToolCall, contextCompaction) land in subsequent slices.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from integrations.headless.format_tools import format_tool_use


_COMMAND_OUTPUT_CAP = 200


def render_item(item: Dict[str, Any]) -> Optional[str]:
    item_type = item.get("type")
    if item_type == "agentMessage":
        return item.get("text") or ""
    if item_type == "reasoning":
        return _render_reasoning(item)
    if item_type == "commandExecution":
        return _render_command_execution(item)
    if item_type == "fileChange":
        return _render_file_change(item)
    # Variants not yet handled fall through to None so the session drops the
    # item rather than emitting an empty/garbled row. Subsequent slices will
    # add cases here one at a time.
    return None


def _render_reasoning(item: Dict[str, Any]) -> Optional[str]:
    """Reasoning items carry ``content`` and ``summary`` as string arrays per
    the 0.144.5 schema (NOT a single ``text`` field; the plan was wrong).

    Prefer ``summary`` for the dashboard surface — it's the model's
    short-form rationale. Fall back to ``content`` if no summary is present.
    Return ``None`` (skip) when both are empty so we don't write empty
    "Reasoning:\\n" rows.

    The row is tagged ``message_metadata.thinking`` upstream (see
    ``codex_app_server._handle_item``) so clients render it as a collapsed
    "Thinking" card with a lightbulb icon. The plain-text ``Reasoning:`` label
    (no emoji) is only the pre-card fallback for older clients.
    """
    summary_parts = item.get("summary") or []
    content_parts = item.get("content") or []
    parts = summary_parts or content_parts
    if not parts:
        return None
    body = "\n".join(p for p in parts if p)
    if not body:
        return None
    return "Reasoning:\n" + body


def _render_command_execution(item: Dict[str, Any]) -> str:
    """Render a ``commandExecution`` ThreadItem.

    Suppresses the noisy ``Result: (exit None)`` / ``Result: (exit 0)`` tail
    when there's nothing useful to say:

    * ``status == "canceled"`` -> the command was rejected at the permission
      card; never executed. Show ``(cancelled)`` instead of a fake exit
      code / empty output (which used to read as if the command had run
      and produced nothing).
    * Empty output AND exit 0 -> clean success with no stdout; head row is
      enough.
    * Exit code ``None`` AND empty output -> in-progress or status we
      don't have an exit for; skip the Result line.
    """
    head = format_tool_use("Bash", {"command": item.get("command", "")})
    status = item.get("status")
    if status == "canceled":
        return f"{head}\n   _(cancelled by user)_"
    output = (item.get("aggregatedOutput") or "")[:_COMMAND_OUTPUT_CAP]
    exit_code = item.get("exitCode")
    has_output = bool(output.strip())
    if not has_output and (exit_code is None or exit_code == 0):
        # Nothing meaningful to surface — head row already conveys "Bash ran".
        return head
    if not has_output:
        # Exit code is non-zero and there's no captured output. Still useful
        # to show — surface only the exit so the user can see the failure.
        return f"{head}\n   Result: (exit {exit_code})"
    return f"{head}\n   Result: {output} (exit {exit_code})"


def _render_file_change(item: Dict[str, Any]) -> str:
    """Render a ``fileChange`` ThreadItem.

    Real schema (0.144.5): ``{changes: [{path, kind: {type}, diff}], status}``
    where ``kind.type`` is one of ``add`` / ``update`` / ``delete``. The plan
    originally said ``files`` — wrong; live wire trace caught this.

    Tool-name mapping mirrors claude_code's cards so the dashboard renders
    file ops identically regardless of which agent produced them:
    ``add`` -> Write, ``update`` -> Edit, ``delete`` -> Delete. Multi-file
    fileChange items (rare in practice — codex emits one change per item)
    fall back to ``ApplyPatch`` with per-file kind glyphs.
    """
    # Tolerate the older ``files`` shape too in case codex emits it on some
    # paths or the schema evolves; ``changes`` is authoritative.
    changes = item.get("changes") or item.get("files") or []
    if not changes:
        return "🔧 Using tool: ApplyPatch"

    if len(changes) == 1:
        return _render_single_file_change(changes[0])

    # Mixed-file fallback: head lists all touched paths with kind glyphs;
    # diff blocks below are labelled with the path so the user can tell
    # which diff belongs to which file.
    head_parts: list[str] = []
    diff_blocks: list[str] = []
    for ch in changes:
        path = ch.get("path") or "?"
        glyph = _KIND_GLYPHS.get(_kind_type(ch.get("kind")), "✏️")
        head_parts.append(f"{glyph} `{path}`")
        diff = ch.get("diff") or ""
        if diff:
            diff_blocks.append(f"\n\n**{path}**\n```diff\n{diff}```")
    head = "🔧 Using tool: ApplyPatch - " + ", ".join(head_parts)
    return head + "".join(diff_blocks)


_KIND_TO_TOOL = {
    "add": "Write",
    "update": "Edit",
    "delete": "Delete",
}

_KIND_GLYPHS = {"add": "➕", "delete": "❌", "update": "✏️"}


def _kind_type(kind: Any) -> str:
    if isinstance(kind, dict):
        return kind.get("type") or "update"
    if isinstance(kind, str):
        return kind
    return "update"


def _render_single_file_change(change: Dict[str, Any]) -> str:
    path = change.get("path") or "?"
    kind_type = _kind_type(change.get("kind"))
    tool = _KIND_TO_TOOL.get(kind_type, "ApplyPatch")
    head = f"🔧 Using tool: {tool} - `{path}`"
    diff = change.get("diff") or ""
    if not diff:
        return head
    # Path is already in the head; the diff block below doesn't need to
    # repeat it (per UX feedback — duplicate path lines are noise).
    return f"{head}\n\n```diff\n{diff}```"
