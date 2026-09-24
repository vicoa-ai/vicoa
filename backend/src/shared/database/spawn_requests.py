"""Shared helper for queuing a spawn request onto a machine's daemon.

Two routers expose the same "start a session on this machine" operation:

* ``backend.api.machines`` — human-facing (dashboard, mobile), user token.
* ``servers.api.routers`` — agent-facing (``vicoa session start``,
  ``vicoa_start_session``), Vicoa API key.

They were copies of each other, and the copies drifted: the agent-facing one
never stamped ``machine_id`` on the ``AgentInstance`` it pre-stages. Nothing
downstream fills that in — registration's idempotent "row exists" branch and
the PATCH endpoint both leave it alone, and a resume skips registration
entirely — so every session started from the CLI or by another agent stayed
machine-less for life. In the app that reads as a dead session view: no
terminal, no Changes/files panel, no git branch badge, no file search (each
of those is routed by ``instance.machine_id``), plus a degraded project match.

Both rows are created here now, once, so the two routes cannot drift again.
Each router still owns the ``request_metadata`` it hands the daemon (prompt
and agent-profile policy differ), its own broadcast, and its commit.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session, attributes

from .agent_instances import create_agent_instance
from .enums import AgentStatus
from .models import AgentInstance, Machine, MachineSpawnRequest

#: How many directories a machine remembers for the new-session picker.
RECENT_DIRECTORY_LIMIT = 10


def queue_spawn_request(
    db: Session,
    *,
    user_id: UUID,
    machine: Machine,
    agent: str,
    directory: str,
    request_metadata: dict,
    name: str | None = None,
    agent_profile_id: UUID | None = None,
) -> tuple[AgentInstance, MachineSpawnRequest]:
    """Pre-stage the session row and queue the request for ``machine``.

    Flushes but does not commit — the caller owns the transaction, so it can
    broadcast from the same one. Returns ``(instance, spawn_request)``.
    """

    instance = create_agent_instance(
        db,
        user_id,
        agent_name=agent,
        instance_id=uuid4(),
        name=name,
        instance_metadata={"spawn_starting": True},
        # Load-bearing: this is the link every machine-scoped feature reads
        # back (terminal, files/git panel, git badges, file search) and the
        # first tier of the project matcher. Anything that creates a session
        # for a known machine must stamp it here — see the module docstring.
        machine_id=machine.id,
        status=AgentStatus.STARTING,
        agent_profile_id=agent_profile_id,
    )

    spawn_request = MachineSpawnRequest(
        id=uuid4(),
        machine_id=machine.id,
        requested_by_user_id=user_id,
        directory=directory,
        agent=agent,
        agent_instance_id=instance.id,
        request_metadata=request_metadata,
    )
    db.add(spawn_request)

    _remember_recent_directory(machine, directory)

    db.flush()
    _notify_daemon(db, spawn_request)
    return instance, spawn_request


def _remember_recent_directory(machine: Machine, directory: str) -> None:
    """Move ``directory`` to the front of the machine's recent-dirs list."""

    metadata: dict = (
        machine.machine_metadata if isinstance(machine.machine_metadata, dict) else {}
    )
    recent_dirs: list[str] = []
    if isinstance(metadata.get("recent_directories"), list):
        recent_dirs = [str(item) for item in metadata["recent_directories"]]

    recent_dirs = [directory] + [path for path in recent_dirs if path != directory]
    metadata["recent_directories"] = recent_dirs[:RECENT_DIRECTORY_LIMIT]

    machine.machine_metadata = metadata
    attributes.flag_modified(machine, "machine_metadata")


def _notify_daemon(db: Session, spawn_request: MachineSpawnRequest) -> None:
    """Legacy NOTIFY: safety net for the spawn-requests SSE stream and old
    daemons that predate the WebSocket path (websocket-migration §4 Phase 2).

    The channel is keyed off the machine row's own id, which is what the
    daemon's ``/spawn-requests/stream`` LISTENs on — a client that spelled the
    id differently in the URL used to NOTIFY a channel nobody was listening to.
    """

    payload = json.dumps(
        {
            "request_id": str(spawn_request.id),
            "directory": spawn_request.directory,
            "agent": spawn_request.agent,
            "agent_instance_id": str(spawn_request.agent_instance_id),
            "metadata": spawn_request.request_metadata,
            "requested_at": spawn_request.created_at.isoformat() + "Z",
        }
    )
    channel = f"machine_spawn_{spawn_request.machine_id}"
    db.execute(text(f'NOTIFY "{channel}", :payload'), {"payload": payload})
