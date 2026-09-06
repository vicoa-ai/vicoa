"""Map Pi-family subagent frames onto Vicoa's flat, tagged subagent rows.

Only omp has subagents; pi's spec sets ``supports_subagents=False`` and this
module is simply never wired up for it.

The one decision that matters here is the **subscription level**. omp offers
``off`` / ``progress`` / ``events``, and ``events`` is a firehose: the archived
trace captured 110 ``subagent_event`` frames for a single trivial subagent,
because that level nests the child's entire event stream inside the parent's.
So the wrapper subscribes at ``progress`` and builds cards from
``subagent_lifecycle`` + ``subagent_progress`` only.

Two shape facts from the trace, both easy to assume wrong:

* ``payload.id`` is a readable name (``"DelightedDinosaur"``), not a UUID.
* ``payload.parentToolCallId`` is what links a subagent to the ``task`` tool
  card that launched it — which is the group key Vicoa's subagent metadata
  already uses (``message_metadata.subagent.tool_use_id``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from integrations.headless import subagent as subagent_mod
from integrations.headless.pi_family.rpc_types import as_dict, as_str


logger = logging.getLogger(__name__)

#: Default subscription. See the module docstring — ``events`` is 30x the
#: traffic for information we do not render.
DEFAULT_SUBSCRIPTION_LEVEL = "progress"


@dataclass
class SubagentRun:
    """What we know about one running subagent."""

    subagent_id: str
    agent: str = "agent"
    parent_tool_call_id: str = ""
    assignment: str = ""
    status: str = ""
    announced: bool = False


@dataclass
class SubagentTracker:
    """Track live subagents and decide which frames deserve a chat row.

    Progress frames arrive continuously; writing a row per frame would bury
    the conversation. Only a *status transition* (and the first sighting)
    produces a row.
    """

    runs: Dict[str, SubagentRun] = field(default_factory=dict)

    def handle_lifecycle(self, payload: Any) -> Optional[tuple[str, dict]]:
        """``subagent_lifecycle`` -> ``(content, message_metadata)`` or None."""
        data = as_dict(payload)
        subagent_id = as_str(data.get("id"))
        if not subagent_id:
            return None
        run = self.runs.setdefault(subagent_id, SubagentRun(subagent_id=subagent_id))
        run.agent = as_str(data.get("agent")) or run.agent
        run.parent_tool_call_id = (
            as_str(data.get("parentToolCallId")) or run.parent_tool_call_id
        )
        status = as_str(data.get("status"))
        if status and status == run.status:
            return None
        run.status = status or run.status
        run.announced = True
        label = _status_label(run.status)
        content = f"🤖 Subagent `{run.agent}` ({subagent_id}) {label}"
        return content, _metadata(run, role="lifecycle")

    def handle_progress(self, payload: Any) -> Optional[tuple[str, dict]]:
        """``subagent_progress`` -> ``(content, message_metadata)`` or None.

        Emits only on a status change, and only once the run has an
        assignment worth showing.
        """
        data = as_dict(payload)
        progress = as_dict(data.get("progress"))
        subagent_id = as_str(progress.get("id")) or as_str(data.get("id"))
        if not subagent_id:
            return None
        run = self.runs.setdefault(subagent_id, SubagentRun(subagent_id=subagent_id))
        run.agent = (
            as_str(progress.get("agent")) or as_str(data.get("agent")) or run.agent
        )
        run.parent_tool_call_id = (
            as_str(data.get("parentToolCallId")) or run.parent_tool_call_id
        )
        run.assignment = as_str(data.get("assignment")) or run.assignment
        status = as_str(progress.get("status")) or as_str(data.get("status"))
        if not status or status == run.status:
            return None
        run.status = status
        run.announced = True
        label = _status_label(status)
        detail = f" — {run.assignment}" if run.assignment else ""
        content = f"🤖 Subagent `{run.agent}` ({subagent_id}) {label}{detail}"
        return content, _metadata(run, role="step")

    def forget(self, subagent_id: str) -> None:
        self.runs.pop(subagent_id, None)

    def reset(self) -> None:
        self.runs.clear()


def _status_label(status: str) -> str:
    return {
        "started": "started",
        "running": "is working",
        "completed": "finished",
        "done": "finished",
        "failed": "failed",
        "aborted": "was cancelled",
        "cancelled": "was cancelled",
    }.get(status, status or "updated")


def _metadata(run: SubagentRun, *, role: str) -> dict:
    """Reuse the existing subagent metadata contract.

    ``tool_use_id`` is the group key clients collapse on. Falling back to the
    subagent's own id when there is no ``parentToolCallId`` keeps a detached
    run from being grouped with unrelated ones.
    """
    return subagent_mod.build_metadata(
        tool_use_id=run.parent_tool_call_id or run.subagent_id,
        subagent_type=run.agent,
        description=run.assignment or run.subagent_id,
        role=role,
    )


__all__ = ["DEFAULT_SUBSCRIPTION_LEVEL", "SubagentRun", "SubagentTracker"]
