"""Capture Claude Code sub-agent (Task tool) activity as flat, metadata-tagged
messages. The SDK stamps child messages with ``parent_tool_use_id`` equal to
the launching Task block's id; that id is the group key threaded into
``message_metadata.subagent``."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

# Task types the CLI announces through ``task_started`` that mean delegated
# *agent* work — a Task-tool sub-agent or a workflow.
#
# A backgrounded shell (``Bash(run_in_background=True)``, or one the CLI
# auto-backgrounds when it outruns the foreground timeout) rides the *exact
# same* task frames as ``local_bash``, and all three carry a ``tool_use_id``.
# So the presence of an id is not a discriminator: keying off it alone is what
# made every slow ``git push`` render as a "Sub-agent: agent" card holding one
# line of text. ``task_type`` is the CLI's own answer to the question.
#
# Mirrors the SDK's ``DEFERRING_TASK_TYPES`` and paseo's
# ``isProviderSubagentTask``.
AGENT_TASK_TYPES = frozenset({"local_agent", "local_workflow"})


class SubAgentTracker:
    """Which launched tasks are sub-agents, and what to call them.

    Two independent facts are remembered, from two different frames:

    * the ``Task``/``Agent`` **tool blocks** seen on the stream — the source of
      the label (``subagent_type`` / ``description``). Having seen one at all
      also proves that ``tool_use_id`` belongs to delegated agent work.
    * the ``task_started`` **announcements** — the source of ``task_type``,
      which is what separates a sub-agent from a backgrounded shell.
      ``task_notification`` (where a finished task reports back) carries no
      ``task_type`` of its own, so it has to be looked up by ``task_id``.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, Tuple[str, str]] = {}
        # task_id -> task_type / tool_use_id, both from ``task_started``.
        self._task_types: Dict[str, str] = {}
        self._tool_use_by_task: Dict[str, str] = {}

    def remember_task(
        self, tool_use_id: str, subagent_type: str, description: str
    ) -> None:
        self._tasks[tool_use_id] = (subagent_type or "agent", description or "")

    def label_for(self, tool_use_id: str) -> Tuple[str, str]:
        return self._tasks.get(tool_use_id, ("agent", ""))

    def knows(self, tool_use_id: Optional[str]) -> bool:
        """True when ``tool_use_id`` is a ``Task``/``Agent`` block we saw launch."""
        return bool(tool_use_id) and tool_use_id in self._tasks

    def observe_task_started(
        self,
        task_id: Optional[str],
        task_type: Optional[str],
        tool_use_id: Optional[str],
    ) -> None:
        """Record a ``task_started`` announcement so its later
        ``task_notification`` can be classified."""
        if not task_id:
            return
        if task_type:
            self._task_types[task_id] = task_type
        if tool_use_id:
            self._tool_use_by_task[task_id] = tool_use_id

    def is_agent_task(
        self, task_id: Optional[str], tool_use_id: Optional[str] = None
    ) -> bool:
        """Is this settled task a sub-agent, or a backgrounded shell?

        ``task_type`` from the matching ``task_started`` is authoritative when
        the CLI announced one. Releases predating ``task_type`` announce
        nothing to go on, so fall back to having actually seen the launching
        ``Task``/``Agent`` tool block — only delegated agent work produces one.
        """
        task_type = self._task_types.get(task_id or "")
        if task_type:
            return task_type in AGENT_TASK_TYPES
        return self.knows(tool_use_id or self._tool_use_by_task.get(task_id or ""))


def build_metadata(
    tool_use_id: str,
    subagent_type: str,
    description: str,
    role: str = "step",
    status: Optional[str] = None,
) -> dict:
    payload = {
        "tool_use_id": tool_use_id,
        "subagent_type": subagent_type or "agent",
        "description": description or "",
        "role": role,
    }
    # Only the settled report carries one; clients key the failure treatment
    # off its presence, so don't stamp a null onto every step.
    if status:
        payload["status"] = status
    return {"subagent": payload}


__all__ = ["AGENT_TASK_TYPES", "SubAgentTracker", "build_metadata"]
