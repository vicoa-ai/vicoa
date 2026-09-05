"""Slash-command index from the Pi-family ``available_commands_update`` frame.

Both agents push their full slash-command + skill list unprompted at startup
(and again whenever it changes), and both answer a pull — pi with
``get_commands``, omp with ``get_available_commands`` (one spec field). The
result feeds Vicoa's existing command index via ``POST /api/v1/commands/sync``,
which is the same endpoint ``vicoa headless`` already uses for Claude and
Codex, so the composer's ``/`` menu works with no client change.

Measured shape, which paseo's schema does not model::

    {"name": "security", "description": "...", "source": "builtin",
     "input": {"hint": "<plan|scan|status>"},
     "subcommands": [{"name": "plan", "description": "Create a scan plan"}]}

Subcommands are flattened into ``parent:child`` entries so they are reachable
from a flat picker rather than dropped.
"""

from __future__ import annotations

from typing import Any, Dict

from integrations.headless.pi_family.rpc_types import as_dict, as_list, as_str


#: Guard against a pathological command list ballooning the sync payload. The
#: real lists run to a few dozen; an operator with many skills was measured at
#: 76. This is a sanity ceiling, not a product limit.
MAX_COMMANDS = 500


def build_command_index(commands: Any) -> Dict[str, Dict[str, str]]:
    """``{name: {"description": str}}`` for ``client.sync_commands``.

    Names are stored without a leading ``/`` to match what
    ``scan_agent_commands`` produces for the other agents.
    """
    index: Dict[str, Dict[str, str]] = {}
    for entry in as_list(commands):
        command = as_dict(entry)
        name = as_str(command.get("name")).lstrip("/")
        if not name:
            continue
        description = as_str(command.get("description"))
        hint = as_str(as_dict(command.get("input")).get("hint"))
        if hint:
            description = f"{description} {hint}".strip()
        index[name] = {"description": description}
        for sub in as_list(command.get("subcommands")):
            sub_command = as_dict(sub)
            sub_name = as_str(sub_command.get("name")).lstrip("/")
            if not sub_name:
                continue
            index[f"{name}:{sub_name}"] = {
                "description": as_str(sub_command.get("description"))
            }
        if len(index) >= MAX_COMMANDS:
            break
    return index


__all__ = ["MAX_COMMANDS", "build_command_index"]
