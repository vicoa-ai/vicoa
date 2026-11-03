"""Native wrappers must register without a session ``name``.

Their ``agent_name`` is the agent's display name ("Codex", "Pi",
"Antigravity"), not a session title. The server only generates a title for a
session whose ``name`` is still unset, and a registration that carries a name
overwrites whatever the row already holds. So sending the display name pinned
every Codex, Pi and Antigravity session to the agent's own name, and replaced a
name the user picked at spawn.

Left out, the name is filled by the first user message's generated title, or by
the title the daemon hands over with ``VICOA_SESSION_TITLE`` (applied by the SDK
client whenever ``name`` is None) — the same path Claude Code sessions take.

Like the initial-prompt POST (``test_initial_prompt_catch_up``), this is one
keyword argument that no happy-path runtime assertion would miss, and
``codex_native`` registers inline in ``run()``, so it is pinned structurally.
"""

from __future__ import annotations

import ast
import importlib
import inspect

import pytest

WRAPPERS = [
    "integrations.headless.codex_native",
    "integrations.headless.pi_family.runner",
    "integrations.headless.antigravity.runner",
]


def _registrations(module_name: str) -> list[ast.Call]:
    """Every ``register_agent_instance(...)`` call in the module."""
    tree = ast.parse(inspect.getsource(importlib.import_module(module_name)))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "register_agent_instance"
    ]


@pytest.mark.parametrize("module_name", WRAPPERS)
def test_registration_is_found(module_name: str) -> None:
    # Guards the test below against silently matching nothing after a refactor
    # renames the call.
    assert len(_registrations(module_name)) == 1


@pytest.mark.parametrize("module_name", WRAPPERS)
def test_registration_sends_no_session_name(module_name: str) -> None:
    for call in _registrations(module_name):
        assert "name" not in {kw.arg for kw in call.keywords}, (
            f"{module_name} sends a session name on registration; the agent's "
            "display name is not a session title"
        )
