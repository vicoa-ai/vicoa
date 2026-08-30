"""Unit tests for ``integrations.headless.codex.permission``.

Pure-function tests for the decision-text parser and the markdown renderer.
End-to-end wiring (transport request handler -> session -> vicoa POST ->
user reply -> JSON-RPC response) lives in test_codex_app_server.py.
"""

from __future__ import annotations

import pytest

from integrations.headless.codex.permission import (
    DECISION_ACCEPT,
    DECISION_ACCEPT_FOR_SESSION,
    DECISION_CANCEL,
    DECISION_DECLINE,
    parse_decision,
    render_command_permission_prompt,
    render_file_change_permission_prompt,
)


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("Accept", DECISION_ACCEPT),
        ("accept", DECISION_ACCEPT),
        ("Approve", DECISION_ACCEPT),
        ("Accept (session)", DECISION_ACCEPT_FOR_SESSION),
        ("Always allow", DECISION_ACCEPT_FOR_SESSION),
        ("ALWAYS ALLOW", DECISION_ACCEPT_FOR_SESSION),
        ("Decline", DECISION_DECLINE),
        ("Deny", DECISION_DECLINE),
        ("Cancel", DECISION_CANCEL),
        ("Stop", DECISION_CANCEL),
    ],
)
def test_parse_decision_known_replies(reply: str, expected: str):
    assert parse_decision(reply) == expected


def test_parse_decision_unknown_reply_defaults_to_decline():
    # Safer default than ``accept`` (privilege escalation) or ``cancel``
    # (kills the whole turn). If the user typed unexpected text, treat the
    # specific tool call as declined and let the agent decide what's next.
    assert parse_decision("maybe later") == DECISION_DECLINE
    assert parse_decision("") == DECISION_DECLINE


def test_render_command_permission_prompt_includes_command_and_four_options():
    out = render_command_permission_prompt(
        {
            "command": "rm -rf /tmp/foo",
            "cwd": "/Users/dev/projects/x",
            "reason": "cleanup before build",
        }
    )
    # Command and working directory surface so the user can evaluate the ask.
    assert "rm -rf /tmp/foo" in out
    assert "/Users/dev/projects/x" in out
    assert "cleanup before build" in out
    # The four options the parser knows about must all appear, fenced by
    # the [OPTIONS]/[/OPTIONS] markers the dashboard parses.
    assert "[OPTIONS]" in out
    assert "[/OPTIONS]" in out
    assert "Accept" in out
    assert "Accept (session)" in out
    assert "Decline" in out
    assert "Cancel" in out


def test_render_file_change_permission_prompt_lists_files_and_diff():
    out = render_file_change_permission_prompt(
        {
            "files": [
                {"path": "src/app.py", "diff": "@@ -1 +1 @@\n-x\n+y\n"},
                {"path": "src/lib.py", "diff": "@@ -2 +2 @@\n-a\n+b\n"},
            ],
            "reason": "rename a -> b",
        }
    )
    assert "src/app.py" in out
    assert "src/lib.py" in out
    # Diff bodies surface so the user can see what changes.
    assert "+y" in out
    assert "+b" in out
    assert "rename a -> b" in out
    # Four-option block — uses the same decision enum as command approval.
    assert "[OPTIONS]" in out
    assert "Accept (session)" in out
