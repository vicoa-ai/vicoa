"""Slash-command index built from an ACP-shaped ``availableCommands`` list.

Feeds Vicoa's command index via ``POST /api/v1/commands/sync`` — the same
endpoint ``vicoa headless`` uses for Claude and Codex — so the composer's ``/``
menu works with no client change.

The shape is ACP's ``AvailableCommand``::

    {"name": "review", "description": "...", "input": {"hint": "<pr-number>"}}

The Pi family speaks the same frame with one extension, measured and not
modelled by the ACP schema — nested subcommands, which are flattened into
``parent:child`` entries so a flat picker can still reach them::

    {"name": "security", "description": "...", "source": "builtin",
     "input": {"hint": "<plan|scan|status>"},
     "subcommands": [{"name": "plan", "description": "Create a scan plan"}]}

Lives here rather than under ``pi_family/`` because the frame originates in the
ACP spec: the generic ACP wrapper and both Pi-family agents share this builder.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Dict, List


#: Guard against a pathological command list ballooning the sync payload. The
#: real lists run to a few dozen; an operator with many skills was measured at
#: 76. This is a sanity ceiling, not a product limit.
MAX_COMMANDS = 500


def _as_dict(value: Any) -> Dict[str, Any]:
    """``value`` when it is a mapping, else ``{}``."""
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> List[Any]:
    """``value`` when it is a non-string sequence, else ``[]``."""
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def build_command_index(commands: Any) -> Dict[str, Dict[str, str]]:
    """``{name: {"description": str}}`` for ``client.sync_commands``.

    Names are stored without a leading ``/`` to match what
    ``scan_agent_commands`` produces for the other agents.
    """
    index: Dict[str, Dict[str, str]] = {}
    for entry in _as_list(commands):
        command = _as_dict(entry)
        name = _as_str(command.get("name")).lstrip("/")
        if not name:
            continue
        description = _as_str(command.get("description"))
        hint = _as_str(_as_dict(command.get("input")).get("hint"))
        if hint:
            description = f"{description} {hint}".strip()
        index[name] = {"description": description}
        for sub in _as_list(command.get("subcommands")):
            sub_command = _as_dict(sub)
            sub_name = _as_str(sub_command.get("name")).lstrip("/")
            if not sub_name:
                continue
            index[f"{name}:{sub_name}"] = {
                "description": _as_str(sub_command.get("description"))
            }
        if len(index) >= MAX_COMMANDS:
            break
    return index


__all__ = ["MAX_COMMANDS", "build_command_index"]
