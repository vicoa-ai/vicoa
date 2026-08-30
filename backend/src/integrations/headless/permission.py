"""Permission prompt helpers for the headless Claude runner.

Replaces the out-of-process ``servers/mcp/stdio_server.py:approve_tool`` flow
that the headless runner used to spawn over MCP. The runner now invokes the
``can_use_tool`` SDK callback directly; this module owns:

* The in-process "allow always" cache (``PermissionCache``).
* The Markdown rendering for the prompt the dashboard parses
  (``render_permission_prompt`` + ``format_dict_as_markdown``).
* The Future-based reply registry (``PermissionReplyRegistry``) that lets
  ``_handle_permission_prompt`` POST with ``poll_for_reply=False`` and
  resolve the user's response via the SSE listener — same shape as
  ``auq.AskUserQuestionRegistry``. See
  ``docs/design/mcp-headless-refactor.md`` §2c / §2g for why.

The prompt format is **load-bearing**: the dashboard's three-option picker
renders one button per line in the ``[OPTIONS]`` block. The constants below
are the user-facing display labels. Matching is done case-insensitively at
the comparison site (``raw_answer.lower() == ALLOW_ONCE.lower()``).
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Deque, Dict, List, Optional


# Button labels shown to the user. These are exactly what the dashboard
# renders in its picker and what the user clicks. The runner compares
# incoming replies case-insensitively, so dashboards are free to echo the
# label in any casing.
ALLOW_ONCE = "Allow once"
ALLOW_ALWAYS = "Always allow"
DENY = "Deny"


def format_dict_as_markdown(data: Dict[str, Any]) -> str:
    """Format a tool-input dict as readable Markdown for permission prompts.

    Mirrors ``servers/mcp/stdio_server.py:format_dict_as_markdown`` so the
    prompts produced by the in-process can_use_tool path match what the
    dashboard used to render when permissions came through MCP.
    """
    lines: List[str] = []
    for key, value in data.items():
        lines.append(f"**{key}:**")
        if isinstance(value, dict):
            nested = format_dict_as_markdown(value)
            indented = "\n".join(f"  {line}" for line in nested.split("\n"))
            lines.append(indented)
        elif isinstance(value, list):
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, str) and "\n" in value:
            lines.append("```")
            lines.append(value)
            lines.append("```")
        else:
            lines.append(f"  {value}")
        lines.append("")
    return "\n".join(lines).rstrip()


def bash_command_prefix(tool_input: Dict[str, Any]) -> Optional[str]:
    """Return the first word of a Bash ``command``, or ``None`` if absent.

    Used as the cache key for "allow always" on Bash so that approving
    ``git status`` doesn't accidentally also approve ``rm -rf``.
    """
    command = tool_input.get("command", "")
    if not isinstance(command, str):
        return None
    parts = command.split()
    return parts[0] if parts else None


class PermissionCache:
    """Session-scoped "allow always" cache.

    Structure mirrors the per-instance dict that used to live in
    ``servers/mcp/stdio_server.py``::

        {"Edit": True, "Bash": {"git": True, "ls": True}, ...}

    For Bash, the key is the command prefix; for any other tool, the key is
    the tool name itself.
    """

    def __init__(self, state: Optional[Dict[str, Any]] = None) -> None:
        # Tests inject pre-populated dicts via the runner's
        # ``_permission_state`` attribute, so we accept and own it directly
        # rather than constructing a fresh one.
        self._state: Dict[str, Any] = state if state is not None else {}

    @property
    def state(self) -> Dict[str, Any]:
        """The raw cache dict (read/write). Exposed for tests."""
        return self._state

    def is_cached(self, tool_name: str, tool_input: Dict[str, Any]) -> bool:
        if tool_name == "Bash":
            prefix = bash_command_prefix(tool_input)
            if not prefix:
                return False
            bash_perms = self._state.get("Bash", {})
            return bool(bash_perms.get(prefix))
        return bool(self._state.get(tool_name))

    def cache(self, tool_name: str, tool_input: Dict[str, Any]) -> None:
        if tool_name == "Bash":
            prefix = bash_command_prefix(tool_input)
            if not prefix:
                return
            bash_perms = self._state.setdefault("Bash", {})
            bash_perms[prefix] = True
            return
        self._state[tool_name] = True


def looks_like_permission_reply(content: str) -> bool:
    """True if ``content`` matches one of the known permission-reply labels.

    Used by ``_route`` to catch *orphan* permission replies — plain-text
    button clicks ("Allow once" / "Always allow" / "Deny") that arrive
    after their originating ``PermissionReplyRegistry`` future is already
    gone (answered, cancelled, or timed out). Without this check they fall
    through to ``_user_message_queue`` and surface as bogus user input on
    the next turn. Matching is case-insensitive, mirroring the comparison
    ``_handle_permission_prompt`` does against ``ALLOW_ONCE`` / etc.
    """
    return content.strip().lower() in {
        ALLOW_ONCE.lower(),
        ALLOW_ALWAYS.lower(),
        DENY.lower(),
    }


def render_permission_prompt(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Build the Markdown prompt sent to the dashboard."""
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        prefix = bash_command_prefix(tool_input) or "command"
        body = (
            f"Allow execution of Bash {prefix}?\n\n"
            f"**Full command:**\n```bash\n{command}\n```\n\n"
        )
    else:
        formatted_input = format_dict_as_markdown(tool_input)
        body = f"Allow execution of {tool_name}?\n\n**Input:**\n{formatted_input}\n\n"
    body += "[OPTIONS]\n"
    body += f"1. {ALLOW_ONCE}\n"
    body += f"2. {ALLOW_ALWAYS}\n"
    body += f"3. {DENY}\n"
    body += "[/OPTIONS]"
    return body


class PermissionReplyRegistry:
    """Tracks pending permission-prompt futures resolved by the SSE listener.

    Why a registry exists here (mirroring ``auq.AskUserQuestionRegistry``):

    ``_handle_permission_prompt`` used to call
    ``send_message(requires_user_input=True)`` which both committed the
    prompt and *polled* ``/api/v1/messages/pending`` until the user replied.
    That polling participates in the §2g cursor race (concurrent
    ``send_to_vicoa`` POSTs overwrite ``instance.last_read_message_id``;
    losing polls come back ``status: "stale"``) and in the §2c
    double-delivery (the same reply arrives via the poller AND the SSE
    stream — the SSE copy gets enqueued and surfaces as bogus user input on
    the next turn: the *exact* bug seen in session ``269d5bf3-…``).

    The fix is the same shape as AUQ:

    1. Runner POSTs with ``requires_user_input=True, poll_for_reply=False``
       (push/email/SMS still fire; SDK does not poll).
    2. Runner mints a ``request_id`` and registers an ``asyncio.Future``.
    3. The SSE listener decodes each inbound user message and tries the
       registry first via ``resolve_text``; only one permission prompt can
       be in flight per session (``can_use_tool`` is sequential), so a
       FIFO match is unambiguous in Phase 1 without any dashboard wire
       change.
    4. Once dashboards stamp a ``request_id`` into a structured control
       reply (Phase 2), ``resolve_for_request`` can be used directly.

    The future resolves to the **raw reply text** —
    ``_handle_permission_prompt`` then runs the same Allow/Deny parsing it
    used to apply to ``response.queued_user_messages[0]``.
    """

    def __init__(self) -> None:
        self._by_request_id: Dict[str, asyncio.Future[str]] = {}
        self._fifo: Deque[asyncio.Future[str]] = deque()

    def create(self, request_id: str) -> asyncio.Future[str]:
        """Register and return a new pending future for ``request_id``."""
        fut: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        self._by_request_id[request_id] = fut
        self._fifo.append(fut)
        return fut

    def has_pending(self) -> bool:
        """True iff any future is still awaiting a reply."""
        return bool(self._fifo)

    def resolve_text(self, text: str) -> bool:
        """Resolve the oldest pending future with the given raw reply text.

        Used by the SSE listener when no ``request_id`` is embedded in the
        reply (Phase 1: the dashboard sends free text like ``"Allow once"``).
        Returns True if a future was resolved.
        """
        if not self._fifo:
            return False
        fut = self._fifo[0]
        self._forget(fut)
        if not fut.done():
            fut.set_result(text)
        return True

    def resolve_for_request(self, request_id: str, text: str) -> bool:
        """Resolve a specific pending future by ``request_id`` (Phase 2).

        Used when the dashboard echoes back the runner's ``request_id`` in
        a structured control reply.
        """
        fut = self._by_request_id.get(request_id)
        if fut is None:
            return False
        self._forget(fut)
        if not fut.done():
            fut.set_result(text)
        return True

    def cancel(self, request_id: str) -> None:
        """Cancel and forget the future for ``request_id`` (timeout/shutdown)."""
        fut = self._by_request_id.get(request_id)
        if fut is None:
            return
        self._forget(fut)
        if not fut.done():
            fut.cancel()

    def cancel_all(self) -> None:
        for fut in list(self._fifo):
            if not fut.done():
                fut.cancel()
        self._by_request_id.clear()
        self._fifo.clear()

    def _forget(self, fut: asyncio.Future[str]) -> None:
        try:
            self._fifo.remove(fut)
        except ValueError:
            pass
        for key, value in list(self._by_request_id.items()):
            if value is fut:
                del self._by_request_id[key]


__all__ = [
    "ALLOW_ALWAYS",
    "ALLOW_ONCE",
    "DENY",
    "PermissionCache",
    "PermissionReplyRegistry",
    "bash_command_prefix",
    "format_dict_as_markdown",
    "looks_like_permission_reply",
    "render_permission_prompt",
]
