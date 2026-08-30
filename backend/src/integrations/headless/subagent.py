"""Capture Claude Code sub-agent (Task tool) activity as flat, metadata-tagged
messages. The SDK stamps child messages with ``parent_tool_use_id`` equal to
the launching Task block's id; that id is the group key threaded into
``message_metadata.subagent``."""

from __future__ import annotations

from typing import Dict, Tuple


class SubAgentTracker:
    def __init__(self) -> None:
        self._tasks: Dict[str, Tuple[str, str]] = {}

    def remember_task(
        self, tool_use_id: str, subagent_type: str, description: str
    ) -> None:
        self._tasks[tool_use_id] = (subagent_type or "agent", description or "")

    def label_for(self, tool_use_id: str) -> Tuple[str, str]:
        return self._tasks.get(tool_use_id, ("agent", ""))


def build_metadata(
    tool_use_id: str, subagent_type: str, description: str, role: str = "step"
) -> dict:
    return {
        "subagent": {
            "tool_use_id": tool_use_id,
            "subagent_type": subagent_type or "agent",
            "description": description or "",
            "role": role,
        }
    }


__all__ = ["SubAgentTracker", "build_metadata"]
