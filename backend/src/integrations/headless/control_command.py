"""Control-command parsing for the dashboard → runner wire.

The dashboard sends JSON-encoded control directives embedded in user-message
bodies (e.g. permission-mode changes, interrupts, AskUserQuestion replies).
This module owns the regex + parsing; dispatch lives in ``claude_code.py``.
"""

from __future__ import annotations

import json
import re
from typing import Dict, Optional


# Same regex as ``auq.CONTROL_JSON_PATTERN``. Kept here too so callers that
# only need the generic parser don't have to import the AUQ module.
CONTROL_JSON_PATTERN = re.compile(r'\{[^}]*"type"\s*:\s*"control"[^}]*\}')


def is_control_envelope(content: str) -> bool:
    """True only when ``content`` *is* a control directive, not prose that
    merely quotes one.

    The dashboards always emit control messages as a short human-readable
    label followed by the control token — ``"<label> {json}"`` or
    ``"<summary>\\n{json}"`` — so the control JSON is always the **trailing**
    content. This checks exactly that: from the first control-JSON token to the
    end of the message there must be nothing but control-JSON tokens and
    whitespace.

    A normal user message that pastes, quotes, or discusses control JSON (e.g.
    describing the ``session get`` output) has free text *after* the token, so
    it fails this check and is treated as ordinary input instead of being
    silently swallowed. That swallow was the "idle-session message disappears"
    bug: ``_route`` matched the embedded token with ``.search()`` (anywhere in
    the body) and dropped the whole message; because it was deduped into the
    WS ``CatchUpBuffer._seen`` set on the way out, the reconcile backstop could
    never recover it.
    """
    if not content:
        return False
    first = CONTROL_JSON_PATTERN.search(content)
    if first is None:
        return False
    # Everything from the first token onward, with all control tokens removed,
    # must be whitespace only. Handles multi-token messages like
    # ``"Stop. {model} {interrupt}"`` where the tokens are contiguous at the end.
    residue = CONTROL_JSON_PATTERN.sub("", content[first.start() :])
    return residue.strip() == ""


def parse_control_command(content: str) -> Optional[Dict[str, str]]:
    """Parse a JSON control command that trails ``content``.

    Expected wire format::

        {"type": "control", "setting": "<name>", "value": "<value>"}

    Returns ``{"setting": ..., "value": ...}`` (or ``{"setting": ...}`` for
    interrupts which carry no value), or ``None`` if the content is not a
    control command. A message that merely *contains* a control token amid
    other prose is rejected here (see ``is_control_envelope``).
    """
    if not content:
        return None

    if not is_control_envelope(content):
        return None

    match = CONTROL_JSON_PATTERN.search(content)
    if not match:
        return None

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

    if data.get("type") != "control":
        return None

    setting = data.get("setting")
    value = data.get("value")

    # Interrupts are valueless; everything else needs both fields.
    if setting == "interrupt":
        return {"setting": setting}

    if not setting or value is None:
        return None

    return {"setting": setting, "value": value}


__all__ = ["CONTROL_JSON_PATTERN", "is_control_envelope", "parse_control_command"]
