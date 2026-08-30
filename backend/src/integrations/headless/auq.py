"""AskUserQuestion helpers for the headless Claude runner.

This module owns the wire format Vicoa speaks with the dashboard pickers and a
Future-based registry the runner uses to resolve replies without polling.

Why a registry?
---------------
Claude's Agent SDK invokes the ``can_use_tool`` callback as a *detached* task
(``claude_agent_sdk/_internal/query.py:_spawn_control_request_handler``) while
the main message loop is still yielding ``AssistantMessage``s. The previous
implementation called ``send_message(requires_user_input=True)`` from inside
the callback, which POSTs an agent message *and then polls*
``/api/v1/messages/pending`` using the new message's id as the cursor. If
``send_to_vicoa`` (used to relay assistant text) POSTed concurrently for an
earlier ``AssistantMessage`` of the same turn, both POSTs would overwrite
``instance.last_read_message_id`` on the backend in last-writer-wins order.
Whichever lost the race left its poller passing a stale cursor → backend
returned ``status: "stale"`` → SDK raised ``TimeoutError("Another process has
read the messages")`` → callback returned silent Deny → Claude said
"Looks like the question timed out — let me try again" before the user even
had a chance to click an option. Repro: session
``ef853f34-c3f9-48f4-a32d-53e6716f51bf`` (22:18:52 deny vs. 22:19:42 user
submit, 50 s apart).

The Future-based registry collapses that flow. The runner:

1. POSTs the AskUserQuestion message with ``requires_user_input=False`` (no
   polling, no cursor race).
2. Awaits a per-request ``asyncio.Future`` keyed by a freshly minted
   ``request_id``.
3. Routes the dashboard's control-message reply (arriving via the SSE user
   stream) directly into ``resolve()`` to settle the future.

This is the same shape Paseo uses in
``packages/server/src/server/agent/providers/claude/agent.ts:3335`` (its
``handlePermissionRequest``), adapted for Python / Vicoa.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from integrations.headless.control_command import is_control_envelope


# Control command pattern (JSON format). Mirrors the regex in
# ``claude_code.py`` because both modules need to scrape a control JSON object
# out of free-form text the dashboard sends.
CONTROL_JSON_PATTERN = re.compile(r'\{[^}]*"type"\s*:\s*"control"[^}]*\}')


# Minimal content body for an AskUserQuestion prompt. The dashboard reads the
# questions/options from ``message_metadata.ask_user_question`` and renders an
# interactive picker; a non-empty body would render as duplicate text above the
# picker (repro: session ``9aa429b5-…`` at 17:53/17:55).
ASK_USER_QUESTION_PROMPT_LABEL = "🔧 Using tool: AskUserQuestion"


# ---------------------------------------------------------------------------
# Decoded payload shape
# ---------------------------------------------------------------------------
#
# A decoded reply is a plain dict. Callers should treat it as opaque; only
# ``cancelled`` is guaranteed to be present:
#
#   {
#     "cancelled": bool,
#     "answers": list[dict],            # present when not cancelled
#     "display_answers": list[dict],    # present when not cancelled
#     "request_id": str | None,         # echoed back from the prompt metadata
#     "message_id": str | None,         # the dashboard echoes the prompt's id
#   }
# ---------------------------------------------------------------------------


def decode_reply(reply: str) -> Optional[Dict[str, Any]]:
    """Parse the dashboard's control-message reply for AskUserQuestion.

    Returns ``None`` if the reply is not an AskUserQuestion control message
    (callers fall back to free-text handling). Otherwise returns the decoded
    payload described above.
    """
    if not reply:
        return None
    # Only a message that *is* a control directive (token trails the body), not
    # one that merely quotes control JSON amid prose — see ``is_control_envelope``.
    if not is_control_envelope(reply):
        return None
    match = CONTROL_JSON_PATTERN.search(reply)
    if not match:
        return None
    try:
        control = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if (
        not isinstance(control, dict)
        or control.get("type") != "control"
        or control.get("setting") != "ask_user_question"
    ):
        return None
    value = control.get("value")
    if value == "cancel":
        return {
            "cancelled": True,
            "answers": [],
            "display_answers": [],
            "request_id": None,
            "message_id": None,
        }
    if not isinstance(value, str) or not value.startswith("submit:"):
        return None
    encoded = value[len("submit:") :]
    # Re-pad — the web encoder strips trailing '=' before sending.
    padding = (-len(encoded)) % 4
    try:
        decoded_bytes = base64.urlsafe_b64decode(encoded + ("=" * padding))
    except (binascii.Error, ValueError):
        return None
    try:
        payload = json.loads(decoded_bytes)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return {
        "cancelled": False,
        "answers": payload.get("answers") or [],
        "display_answers": payload.get("display_answers") or [],
        "request_id": payload.get("request_id")
        if isinstance(payload.get("request_id"), str)
        else None,
        "message_id": payload.get("message_id")
        if isinstance(payload.get("message_id"), str)
        else None,
    }


def is_persist_only_message(content: str) -> bool:
    """Return True for control messages tagged ``action: persist_only``.

    The dashboard uses this tag for display/persistence-only artifacts (e.g.
    the AskUserQuestion "Q:/A:" answer summary). Such messages must not flow
    into the conversation as user input, otherwise the next turn would receive
    the summary text as a fresh prompt — exactly the bug observed in the
    17:55:05 conversation turn of session ``9aa429b5-…``.
    """
    if not content:
        return False
    # Reject prose that merely embeds a persist_only token mid-body; a real
    # persist_only artifact is ``"<summary>\n{json}"`` with the token trailing.
    if not is_control_envelope(content):
        return False
    match = CONTROL_JSON_PATTERN.search(content)
    if not match:
        return False
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return False
    return (
        isinstance(data, dict)
        and data.get("type") == "control"
        and data.get("action") == "persist_only"
    )


def build_metadata(
    *,
    questions: List[Any],
    prompt: str,
    tool_use_id: Optional[str],
    request_id: str,
) -> Dict[str, Any]:
    """Shape the metadata block the web/mobile pickers parse.

    Mirrors ``parseAskUserQuestionPayload`` in the web/Flutter UIs: keys are
    snake_case, options are ``{"label", "description"}`` only.
    """
    normalized_questions: List[Dict[str, Any]] = []
    for index, question in enumerate(questions):
        if not isinstance(question, dict):
            continue
        question_text = question.get("question")
        if not isinstance(question_text, str) or not question_text.strip():
            continue
        header = question.get("header")
        options_raw = question.get("options") or []
        options: List[Dict[str, str]] = []
        for option in options_raw:
            if not isinstance(option, dict):
                continue
            label = option.get("label")
            if not isinstance(label, str) or not label.strip():
                continue
            description = option.get("description")
            options.append(
                {
                    "label": label,
                    "description": description if isinstance(description, str) else "",
                }
            )
        # Claude's schema uses camelCase ``multiSelect``; the dashboard expects
        # ``multi_select``. Accept either on input.
        multi_select = bool(question.get("multi_select") or question.get("multiSelect"))
        normalized_questions.append(
            {
                "question": question_text,
                "header": header
                if isinstance(header, str) and header.strip()
                else f"Question {index + 1}",
                "options": options,
                "multi_select": multi_select,
            }
        )

    payload: Dict[str, Any] = {
        "questions": normalized_questions,
        "prompt": prompt,
        "request_id": request_id,
    }
    if tool_use_id:
        payload["tool_use_id"] = tool_use_id
    return {"ask_user_question": payload}


def reshape_answers(
    questions: List[Any],
    answers: List[Any],
    display_answers: List[Any],
) -> Dict[str, str]:
    """Map dashboard answers onto Claude's ``{question_text: answer}`` shape.

    Strategy per question:

    * ``mode="text"`` — use ``answer.text``.
    * ``mode="option"`` single-select — look up the option label via
      ``option_index``; fall back to the matching ``display_answers`` entry's
      ``label`` if the index is invalid.
    * ``mode="option"`` multi-select — comma-join the labels matched by
      ``option_indexes`` (same fallback).
    """
    result: Dict[str, str] = {}
    for i, question in enumerate(questions):
        if not isinstance(question, dict):
            continue
        question_text = question.get("question")
        if not isinstance(question_text, str) or not question_text:
            continue

        answer = (
            answers[i] if i < len(answers) and isinstance(answers[i], dict) else None
        )
        display = (
            display_answers[i]
            if i < len(display_answers) and isinstance(display_answers[i], dict)
            else None
        )

        value = ""
        if answer is not None:
            mode = answer.get("mode")
            if mode == "text":
                text = answer.get("text")
                if isinstance(text, str):
                    value = text.strip()
            elif mode == "option":
                options = question.get("options") or []
                if answer.get("question_multi_select") or "option_indexes" in answer:
                    indexes = answer.get("option_indexes") or []
                    labels: List[str] = []
                    for idx in indexes:
                        if (
                            isinstance(idx, int)
                            and 0 <= idx < len(options)
                            and isinstance(options[idx], dict)
                        ):
                            label = options[idx].get("label")
                            if isinstance(label, str) and label.strip():
                                labels.append(label)
                    value = ", ".join(labels)
                else:
                    idx = answer.get("option_index")
                    if (
                        isinstance(idx, int)
                        and 0 <= idx < len(options)
                        and isinstance(options[idx], dict)
                    ):
                        label = options[idx].get("label")
                        if isinstance(label, str):
                            value = label

        if not value and display is not None:
            # display_answers has the human-readable label even when the
            # answer structure is incomplete — last-ditch fallback.
            display_label = display.get("label")
            if isinstance(display_label, str):
                value = display_label.strip()

        result[question_text] = value
    return result


class AskUserQuestionRegistry:
    """Tracks pending AskUserQuestion futures so the SSE listener can resolve
    them without going through ``send_message``'s polling path.

    Design notes:

    * Keyed primarily by ``request_id`` (the runner mints it before the POST
      and stamps it into ``message_metadata``).
    * Also indexed by ``message_id`` once the POST returns, so dashboards
      that echo the prompt's message id (the legacy field) can still resolve.
    * FIFO fallback covers callers that echo neither id — single-AUQ-at-a-time
      is the common case and the oldest pending future is the right one then.
    * ``cancel_all`` is for shutdown; in-flight callbacks are cancelled rather
      than left hanging.
    """

    def __init__(self) -> None:
        self._by_request_id: Dict[str, asyncio.Future[Dict[str, Any]]] = {}
        self._by_message_id: Dict[str, asyncio.Future[Dict[str, Any]]] = {}
        self._fifo: Deque[asyncio.Future[Dict[str, Any]]] = deque()

    def create(self, request_id: str) -> asyncio.Future[Dict[str, Any]]:
        """Register and return a new pending future for ``request_id``."""
        fut: asyncio.Future[Dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._by_request_id[request_id] = fut
        self._fifo.append(fut)
        return fut

    def bind_message_id(self, request_id: str, message_id: Optional[str]) -> None:
        """Index the future under ``message_id`` too, once it's known."""
        if not message_id:
            return
        fut = self._by_request_id.get(request_id)
        if fut is not None:
            self._by_message_id[message_id] = fut

    def has_pending(self) -> bool:
        """True while at least one AskUserQuestion future is awaiting a reply.

        Lets the runner treat a plain-text chat message as the answer to an open
        question instead of stranding the turn — but only when a question is
        actually in flight. See ``_maybe_route_free_text_auq_answer``.
        """
        return any(not fut.done() for fut in self._fifo)

    def resolve(self, payload: Dict[str, Any]) -> bool:
        """Try to resolve a pending future from the decoded control payload.

        Lookup order:

        1. ``payload["request_id"]`` (most reliable; the dashboard echoes our
           own metadata back).
        2. ``payload["message_id"]`` (legacy; the prompt message's id).
        3. FIFO head (last-ditch fallback for clients that echo neither).

        Returns True if a future was found and resolved (or was already done,
        in which case the payload is discarded since the caller already
        unblocked some other way).
        """
        fut = self._lookup(payload)
        if fut is None:
            return False
        self._forget(fut)
        if fut.done():
            return True
        fut.set_result(payload)
        return True

    def cancel(self, request_id: str) -> None:
        """Cancel and forget the future for ``request_id`` (timeout / shutdown)."""
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
        self._by_message_id.clear()
        self._fifo.clear()

    # -- internals ----------------------------------------------------------

    def _lookup(
        self, payload: Dict[str, Any]
    ) -> Optional[asyncio.Future[Dict[str, Any]]]:
        rid = payload.get("request_id")
        if isinstance(rid, str):
            fut = self._by_request_id.get(rid)
            if fut is not None:
                return fut
        mid = payload.get("message_id")
        if isinstance(mid, str):
            fut = self._by_message_id.get(mid)
            if fut is not None:
                return fut
        # FIFO fallback: oldest pending future wins. Common case is one AUQ
        # at a time, so this is unambiguous.
        if self._fifo:
            return self._fifo[0]
        return None

    def _forget(self, fut: asyncio.Future[Dict[str, Any]]) -> None:
        try:
            self._fifo.remove(fut)
        except ValueError:
            pass
        for key, value in list(self._by_request_id.items()):
            if value is fut:
                del self._by_request_id[key]
        for key, value in list(self._by_message_id.items()):
            if value is fut:
                del self._by_message_id[key]


__all__ = [
    "ASK_USER_QUESTION_PROMPT_LABEL",
    "CONTROL_JSON_PATTERN",
    "AskUserQuestionRegistry",
    "build_metadata",
    "decode_reply",
    "is_persist_only_message",
    "reshape_answers",
]
