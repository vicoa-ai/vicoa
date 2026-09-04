"""The initial-prompt POST must not consume its own catch-up cursor.

Every wrapper POSTs its ``initial_prompt`` as a user message and then waits
for the row to come back over the session WebSocket — there is no direct
hand-off into the turn queue. Two legs deliver it: the live ``new-message``
broadcast, and the catch-up ``fetch_messages_request`` issued on connect (and
re-issued by the 10s reconcile backstop).

``send_user_message`` defaults to ``mark_as_read=True``, which points the
instance's ``last_read_message_id`` at the row it just created. The
session-scoped catch-up falls back to that cursor when the client has no
watermark and selects strictly ``created_at > cursor`` — so a prompt marked
read excludes *itself* from every later catch-up. If the live broadcast also
missed it (the ``wait_until_ready`` timeout branch, hit when the WS handshake
outruns 10s), neither leg can deliver it and the session hangs until a human
interrupts. Observed on session c0d25529-… : 6h+ idle, thousands of backstop
re-fetches all returning zero rows.

So ``mark_as_read=False`` on that POST is load-bearing, in all three wrappers.
It is one keyword argument that no runtime assertion in the happy path would
miss, so it is pinned structurally. The server-side half of the invariant —
that the cursor left alone actually recovers the prompt — is covered by
``backend/tests/test_fetch_messages.py``.
"""

from __future__ import annotations

import ast
import importlib
import inspect

import pytest

# (module, the attribute the POST's ``content=`` is read from). The content
# expression is what identifies the *initial-prompt* POST among a module's
# other ``send_user_message`` calls.
WRAPPERS = [
    ("integrations.headless.claude_code", "initial_prompt"),
    ("integrations.headless.codex_native", "initial_prompt"),
    ("integrations.headless.acp_base", "initial_prompt"),
]


def _initial_prompt_posts(module_name: str, content_name: str) -> list[ast.Call]:
    """Every ``send_user_message`` call in the module that sends the prompt."""
    tree = ast.parse(inspect.getsource(importlib.import_module(module_name)))
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "send_user_message"):
            continue
        content = next((k for k in node.keywords if k.arg == "content"), None)
        if content is None:
            continue
        # ``content=self.initial_prompt`` or ``content=initial_prompt``.
        value = content.value
        name = (
            value.attr
            if isinstance(value, ast.Attribute)
            else value.id
            if isinstance(value, ast.Name)
            else None
        )
        if name == content_name:
            calls.append(node)
    return calls


@pytest.mark.parametrize("module_name,content_name", WRAPPERS)
def test_initial_prompt_post_is_found(module_name: str, content_name: str) -> None:
    # Guards the parametrised test below against silently matching nothing
    # after a refactor renames the call or its content expression.
    assert len(_initial_prompt_posts(module_name, content_name)) == 1


@pytest.mark.parametrize("module_name,content_name", WRAPPERS)
def test_initial_prompt_post_does_not_mark_itself_read(
    module_name: str, content_name: str
) -> None:
    (call,) = _initial_prompt_posts(module_name, content_name)
    mark_as_read = next((k for k in call.keywords if k.arg == "mark_as_read"), None)

    assert mark_as_read is not None, (
        f"{module_name}: the initial-prompt POST must pass mark_as_read=False; "
        "the SDK default (True) makes the prompt invisible to its own catch-up "
        "recovery and hangs the session when the live broadcast is missed."
    )
    assert isinstance(mark_as_read.value, ast.Constant)
    assert mark_as_read.value.value is False
