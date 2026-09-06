"""Translate ``extension_ui_request`` frames into Vicoa's human-in-the-loop UI.

This one frame type carries everything the agent wants from a human, and the
methods split cleanly across surfaces Vicoa already has:

======================  ==========================================
frame                   Vicoa surface
======================  ==========================================
``select`` (approve/deny)  permission prompt + ``PermissionReplyRegistry``
``select`` (other)         AskUserQuestion picker (single-select)
``input`` / ``editor``     AskUserQuestion picker (text answer)
``confirm``                AskUserQuestion picker (Yes / No)
``notify``                 a system feedback row
``open_url``               a system row carrying the link
``cancel``                 resolve the targeted pending request as cancelled
everything else            ignored
======================  ==========================================

Two things measured from the traces shape this module:

* **Approval prompts are just ``select``.** With ``--approval-mode always-ask``
  the whole prompt arrives as a multi-line free-text ``title`` with
  ``options: ["Approve", "Deny"]`` — a direct fit for the existing permission
  prompt, whose protocol is purely textual (``[OPTIONS]`` block, reply is the
  clicked label).
* **``extension_ui_request`` fires in plain ``--mode rpc``**, not just
  ``rpc-ui``, and with non-dialog methods (``setWidget`` at session start and
  end). So unknown methods MUST be ignored silently rather than treated as a
  dialog — replying to ``setWidget`` would be a protocol error, and blocking
  on it would hang the turn.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from integrations.headless.pi_family.rpc_types import as_dict, as_list, as_str


logger = logging.getLogger(__name__)


#: Methods that are pure presentation. They carry an ``id`` like a dialog but
#: expect no response; answering (or worse, awaiting a human) would be wrong.
PRESENTATION_METHODS = frozenset(
    {"setWidget", "setStatus", "setTitle", "set_editor_text"}
)

#: Methods that ask a human something and block the agent until answered.
DIALOG_METHODS = frozenset({"select", "confirm", "input", "editor"})

#: Option labels that make a ``select`` an approval prompt rather than a
#: question. Compared case-insensitively against the whole option set.
_APPROVAL_OPTION_SETS = (
    frozenset({"approve", "deny"}),
    frozenset({"allow", "deny"}),
    frozenset({"yes", "no"}),
)


def classify(frame: Dict[str, Any]) -> str:
    """One of ``permission`` / ``question`` / ``notice`` / ``cancel`` / ``ignore``."""
    method = as_str(frame.get("method"))
    if method in PRESENTATION_METHODS:
        return "ignore"
    if method == "cancel":
        return "cancel"
    if method in {"notify", "open_url"}:
        return "notice"
    if method == "select" and _is_approval(as_list(frame.get("options"))):
        return "permission"
    if method in DIALOG_METHODS:
        return "question"
    return "ignore"


def _is_approval(options: List[Any]) -> bool:
    labels = frozenset(
        as_str(option).strip().lower() for option in options if as_str(option).strip()
    )
    if not labels:
        return False
    return any(labels == candidate for candidate in _APPROVAL_OPTION_SETS)


def render_permission_prompt(frame: Dict[str, Any]) -> str:
    """Build the Markdown body the dashboard's option picker parses.

    The ``[OPTIONS]`` block is load-bearing: the dashboard renders one button
    per line and sends back the clicked label verbatim. The agent's own
    ``title`` already reads as a complete prompt ("Allow tool: write\\nPath:
    …"), so it is passed through rather than re-templated.
    """
    title = as_str(frame.get("title")).strip() or "The agent is requesting approval."
    options = [
        as_str(option) for option in as_list(frame.get("options")) if as_str(option)
    ]
    lines = [title, "", "[OPTIONS]"]
    for index, option in enumerate(options, start=1):
        lines.append(f"{index}. {option}")
    lines.append("[/OPTIONS]")
    return "\n".join(lines)


def match_option(reply: str, options: List[Any]) -> Optional[str]:
    """Resolve a free-text reply back to one of ``options``.

    Accepts the exact label (any casing) or its 1-based index, because the
    dashboard sends the label but a user typing into the chat may well answer
    "1". Returns ``None`` when nothing matches, which the caller treats as a
    cancel rather than guessing.
    """
    labels = [as_str(option) for option in options if as_str(option)]
    if not labels:
        return None
    needle = (reply or "").strip()
    if not needle:
        return None
    for label in labels:
        if label.lower() == needle.lower():
            return label
    if needle.isdigit():
        index = int(needle) - 1
        if 0 <= index < len(labels):
            return labels[index]
    # A prefix match covers "Approve." / "approve this" style replies without
    # accepting anything unrelated.
    for label in labels:
        if needle.lower().startswith(label.lower()):
            return label
    return None


def build_question(frame: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], bool]:
    """Build the AUQ question list for a dialog frame.

    Returns ``(questions, is_text_mode)``. Text mode means the answer is free
    text (``input`` / ``editor``) rather than an option index, which changes
    how the reply is turned back into an ``extension_ui_response``.
    """
    method = as_str(frame.get("method"))
    title = as_str(frame.get("title")).strip()

    if method == "confirm":
        message = as_str(frame.get("message")).strip()
        question_text = "\n\n".join(part for part in (title, message) if part) or (
            "Confirm?"
        )
        return (
            [
                {
                    "question": question_text,
                    "header": "Confirm",
                    "options": [{"label": "Yes"}, {"label": "No"}],
                    "multi_select": False,
                }
            ],
            False,
        )

    if method in {"input", "editor"}:
        placeholder = as_str(frame.get("placeholder")) or as_str(frame.get("prefill"))
        question_text = title or "The agent is asking for input."
        if placeholder:
            question_text = f"{question_text}\n\n_{placeholder}_"
        # No options -> the picker renders a free-text field.
        return (
            [
                {
                    "question": question_text,
                    "header": "Input",
                    "options": [],
                    "multi_select": False,
                }
            ],
            True,
        )

    # select
    details = as_list(frame.get("optionDetails"))
    options: List[Dict[str, str]] = []
    for index, option in enumerate(as_list(frame.get("options"))):
        label = as_str(option)
        if not label:
            continue
        description = as_str(
            as_dict(details[index] if index < len(details) else {}).get("description")
        )
        options.append({"label": label, "description": description})
    return (
        [
            {
                "question": title or "Choose an option.",
                "header": "Choose",
                "options": options,
                "multi_select": False,
            }
        ],
        False,
    )


def answer_to_response(
    frame: Dict[str, Any],
    decoded: Dict[str, Any],
    *,
    is_text_mode: bool,
) -> Dict[str, Any]:
    """Turn a decoded AUQ reply into the ``extension_ui_response`` payload.

    The response shape is method-dependent: ``confirm`` wants ``confirmed``,
    everything else wants ``value``, and a cancel/no-answer wants
    ``cancelled``. Sending the wrong key leaves the agent waiting.
    """
    request_id = as_str(frame.get("id"))
    method = as_str(frame.get("method"))
    if decoded.get("cancelled"):
        return {"id": request_id, "cancelled": True}

    answers = as_list(decoded.get("answers"))
    answer = as_dict(answers[0]) if answers else {}

    if is_text_mode:
        text = as_str(answer.get("text")).strip()
        if not text:
            return {"id": request_id, "cancelled": True}
        return {"id": request_id, "value": text}

    options = [
        as_str(option) for option in as_list(frame.get("options")) if as_str(option)
    ]
    if method == "confirm":
        options = ["Yes", "No"]
    label: Optional[str] = None
    if answer.get("mode") == "text":
        label = match_option(as_str(answer.get("text")), options)
    else:
        index = answer.get("option_index")
        if index is None:
            indexes = as_list(answer.get("option_indexes"))
            index = indexes[0] if indexes else None
        if isinstance(index, int) and 0 <= index < len(options):
            label = options[index]

    if label is None:
        return {"id": request_id, "cancelled": True}
    if method == "confirm":
        return {"id": request_id, "confirmed": label.lower() == "yes"}
    return {"id": request_id, "value": label}


def render_notice(frame: Dict[str, Any]) -> Optional[str]:
    """Chat text for a ``notify`` / ``open_url`` frame, or ``None`` to drop."""
    method = as_str(frame.get("method"))
    if method == "notify":
        message = as_str(frame.get("message")).strip()
        if not message:
            return None
        icon = {"warning": "⚠️", "error": "❌"}.get(as_str(frame.get("notifyType")), "ℹ️")
        return f"{icon} {message}"
    if method == "open_url":
        # Prefer ``launchUrl`` when present: it is a short loopback that
        # 302-redirects to the real one, specifically so terminal wrapping
        # can't corrupt OAuth query parameters. A chat surface doesn't wrap,
        # but the short form is still the better copy target.
        url = as_str(frame.get("launchUrl")) or as_str(frame.get("url"))
        if not url:
            return None
        instructions = as_str(frame.get("instructions")).strip()
        body = f"🔗 Open this link to continue:\n\n{url}"
        return f"{body}\n\n{instructions}" if instructions else body
    return None


__all__ = [
    "DIALOG_METHODS",
    "PRESENTATION_METHODS",
    "answer_to_response",
    "build_question",
    "classify",
    "match_option",
    "render_notice",
    "render_permission_prompt",
]
