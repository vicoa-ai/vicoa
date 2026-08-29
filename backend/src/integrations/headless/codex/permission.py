"""Codex permission flow primitives.

The 6-value ``CommandExecutionApprovalDecision`` enum (Codex 0.144.5,
unchanged since 0.131.0) is surfaced as 4 options in v1 (plan §6):

* ``accept`` -- one-shot allow
* ``acceptForSession`` -- thread-scoped "Always allow"
* ``decline`` -- reject this command
* ``cancel`` -- abort the whole turn

``acceptWithExecpolicyAmendment`` and ``applyNetworkPolicyAmendment`` are
out of scope for v1 (power-user execpolicy/network rule persistence).
"""

from __future__ import annotations

from typing import Any, Dict


DECISION_ACCEPT = "accept"
DECISION_ACCEPT_FOR_SESSION = "acceptForSession"
DECISION_DECLINE = "decline"
DECISION_CANCEL = "cancel"


# Labels the user sees in the dashboard. Kept in sync with the parse table
# below so renderer + parser can't drift.
LABEL_ACCEPT = "Accept"
LABEL_ACCEPT_FOR_SESSION = "Accept (session)"
LABEL_DECLINE = "Decline"
LABEL_CANCEL = "Cancel"


# Case-insensitive text -> decision. Order matters only for the renderer;
# duplicates are intentional (synonyms map to the same decision).
_REPLY_TO_DECISION = {
    "accept": DECISION_ACCEPT,
    "approve": DECISION_ACCEPT,
    "accept (session)": DECISION_ACCEPT_FOR_SESSION,
    "always allow": DECISION_ACCEPT_FOR_SESSION,
    "decline": DECISION_DECLINE,
    "deny": DECISION_DECLINE,
    "cancel": DECISION_CANCEL,
    "stop": DECISION_CANCEL,
}


def parse_decision(reply_text: str) -> str:
    """Map raw reply text from the dashboard to a Codex decision string.

    Unknown text defaults to ``decline``: declining a single tool call is
    safer than approving (privilege escalation) or cancelling the whole turn
    (work loss). The agent will then decide what to try next.
    """
    return _REPLY_TO_DECISION.get(
        (reply_text or "").strip().casefold(), DECISION_DECLINE
    )


def render_command_permission_prompt(params: Dict[str, Any]) -> str:
    """Build the dashboard markdown for ``item/commandExecution/requestApproval``.

    Params shape (from the Codex 0.144.5 schema):
    ``{command, cwd, reason?, ...}``. The plan keeps the response opt-set
    aligned with the 4 most useful decisions.
    """
    command = params.get("command") or ""
    cwd = params.get("cwd") or ""
    reason = params.get("reason") or ""

    body_lines = ["Allow execution of this command?", ""]
    body_lines.append("**Command:**")
    body_lines.append(f"```bash\n{command}\n```")
    if cwd:
        body_lines.append(f"**Working directory:** `{cwd}`")
    if reason:
        body_lines.append(f"**Reason:** {reason}")
    body_lines.append("")
    body_lines.append(_render_options_block())
    return "\n".join(body_lines)


def render_file_change_permission_prompt(params: Dict[str, Any]) -> str:
    """Build the dashboard markdown for ``item/fileChange/requestApproval``.

    Params shape: ``{files: [{path, diff?, ...}], reason?}``. Same 4-option
    decision enum as command approval — vicoa's renderer differs only in
    the body (file list + diff preview).
    """
    files = params.get("files") or []
    reason = params.get("reason") or ""

    body_lines = ["Allow these file changes?", ""]
    for f in files:
        path = f.get("path") or "?"
        body_lines.append(f"**{path}**")
        diff = f.get("diff") or ""
        if diff:
            body_lines.append(f"```diff\n{diff}```")
        body_lines.append("")
    if reason:
        body_lines.append(f"**Reason:** {reason}")
        body_lines.append("")
    body_lines.append(_render_options_block())
    return "\n".join(body_lines)


def _render_options_block() -> str:
    return (
        "[OPTIONS]\n"
        f"1. {LABEL_ACCEPT}\n"
        f"2. {LABEL_ACCEPT_FOR_SESSION}\n"
        f"3. {LABEL_DECLINE}\n"
        f"4. {LABEL_CANCEL}\n"
        "[/OPTIONS]"
    )


__all__ = [
    "DECISION_ACCEPT",
    "DECISION_ACCEPT_FOR_SESSION",
    "DECISION_CANCEL",
    "DECISION_DECLINE",
    "LABEL_ACCEPT",
    "LABEL_ACCEPT_FOR_SESSION",
    "LABEL_CANCEL",
    "LABEL_DECLINE",
    "parse_decision",
    "render_command_permission_prompt",
    "render_file_change_permission_prompt",
]
