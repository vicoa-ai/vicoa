"""Builders for WebSocket `update` payloads (websocket-migration plan §2.4-2.7).

Each builder snapshots one canonical table row into a plain dict of JSON
primitives — the `payload` of an `update` frame:

    {"entity", "entity_id", "event_id", "body": {"t", ...}}

Builders run inside the transaction (§2.7) and must return only JSON-
serializable primitives: no lazy ORM attributes, UUIDs, datetimes, or enums.
Mutable-entity bodies carry the complete table row so the §2.6 replace-merge
is safe; joined/derived fields are never included (builders stay pure).
"""

from datetime import datetime

from ..database.models import (
    AgentInstance,
    Machine,
    MachineSpawnRequest,
    Message,
)


def _iso(value: datetime | None) -> str | None:
    """Serialize a datetime as ISO-8601 with an explicit timezone marker.

    The DB columns are TIMESTAMP WITHOUT TIME ZONE storing UTC clock values,
    so SQLAlchemy returns naive datetimes. Bare `isoformat()` on a naive
    datetime emits no timezone — Dart's `DateTime.parse` then interprets it
    as LOCAL time and a session "just now" displays as e.g. "8h ago" for a
    UTC+8 user. Always append "Z" (matches AgentInstanceResponse.serialize_datetime
    in src/backend/models.py — REST and WS must agree on shape).
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()


def build_new_message_update(msg: Message) -> dict:
    """`update` payload for a newly inserted `messages` row (append-only)."""
    return {
        "entity": "messages",
        "entity_id": str(msg.id),
        "event_id": f"{msg.id}:insert",
        "body": {
            "t": "new-message",
            "id": str(msg.id),
            "instance_id": str(msg.agent_instance_id),
            "sender_type": msg.sender_type.value,
            "sender_user_id": (
                str(msg.sender_user_id) if msg.sender_user_id is not None else None
            ),
            "content": msg.content,
            "created_at": _iso(msg.created_at),
            "requires_user_input": msg.requires_user_input,
            "message_metadata": msg.message_metadata,
        },
    }


def build_message_update(msg: Message) -> dict:
    """`update` payload for a metadata patch on an existing `messages` row.

    Unlike `build_new_message_update` (append), this is a PATCH: clients
    merge `message_metadata` into the message they already have rather than
    inserting a new row. Used by the queue lifecycle to push
    `message_metadata["queue"]["status"]` transitions without resending the
    full message body.
    """
    status = (msg.message_metadata or {}).get("queue", {}).get("status")
    return {
        "entity": "messages",
        "entity_id": str(msg.id),
        "event_id": f"{msg.id}:queue:{status}",
        "body": {
            "t": "message-update",
            "id": str(msg.id),
            "instance_id": str(msg.agent_instance_id),
            "message_metadata": msg.message_metadata,
        },
    }


def _instance_row(inst: AgentInstance, t: str) -> dict:
    """Complete agent_instances row as JSON primitives (§2.4 mutable body)."""
    return {
        "t": t,
        "id": str(inst.id),
        "user_agent_id": str(inst.user_agent_id),
        "status": inst.status.value,
        "name": inst.name,
        "project": inst.project,
        "home_dir": inst.home_dir,
        "started_at": _iso(inst.started_at),
        "ended_at": _iso(inst.ended_at),
        "last_heartbeat_at": _iso(inst.last_heartbeat_at),
        # Liveness inputs, not the derived verdict. `live_state` is a function
        # of elapsed time, so a value sent here would be stale on arrival —
        # clients re-derive it on a timer from this heartbeat plus the machine
        # row they already receive via `build_machine_update`.
        "machine_id": str(inst.machine_id) if inst.machine_id else None,
        "instance_metadata": inst.instance_metadata,
        "session_config": inst.session_config,
        "has_git_changes": inst.git_diff is not None,
        "updated_at": _iso(inst.updated_at),
        "pinned_at": _iso(inst.pinned_at),
    }


def build_instance_created_update(inst: AgentInstance) -> dict:
    """`update` payload for a newly registered agent instance."""
    return {
        "entity": "agent_instances",
        "entity_id": str(inst.id),
        "event_id": f"{inst.id}:insert",
        "body": _instance_row(inst, "instance-created"),
    }


def build_instance_update(inst: AgentInstance) -> dict:
    """`update` payload for an agent instance status/metadata change."""
    return {
        "entity": "agent_instances",
        "entity_id": str(inst.id),
        "event_id": f"{inst.id}:update",
        "body": _instance_row(inst, "instance-update"),
    }


def build_machine_update(machine: Machine) -> dict:
    """`update` payload for a machine heartbeat or metadata change."""
    return {
        "entity": "machines",
        "entity_id": str(machine.id),
        "event_id": f"{machine.id}:update",
        "body": {
            "t": "machine-update",
            "id": str(machine.id),
            "display_name": machine.display_name,
            "hostname": machine.hostname,
            "platform": machine.platform,
            "home_dir": machine.home_dir,
            "last_heartbeat_at": _iso(machine.last_heartbeat_at),
            "machine_metadata": machine.machine_metadata,
            "created_at": _iso(machine.created_at),
            "updated_at": _iso(machine.updated_at),
        },
    }


def build_spawn_request_update(req: MachineSpawnRequest) -> dict:
    """`update` payload for a newly created spawn request (append-only event).

    The `machine_spawn_requests` row mutates as the daemon claims and completes
    it, but the `spawn-request` event fires once at creation; status changes
    travel over REST (Phase 2). The body is a snapshot at creation time.
    """
    return {
        "entity": "machine_spawn_requests",
        "entity_id": str(req.id),
        "event_id": f"{req.id}:insert",
        "body": {
            "t": "spawn-request",
            "id": str(req.id),
            "machine_id": str(req.machine_id),
            "requested_by_user_id": str(req.requested_by_user_id),
            "directory": req.directory,
            "agent": req.agent,
            "status": req.status,
            "message": req.message,
            "agent_instance_id": (
                str(req.agent_instance_id)
                if req.agent_instance_id is not None
                else None
            ),
            "created_at": _iso(req.created_at),
            "request_metadata": req.request_metadata,
        },
    }


def build_ephemeral(t: str, **fields: object) -> dict:
    """Build an `ephemeral` frame body (`{"t", ...}`) for broadcast_ephemeral."""
    return {"t": t, **fields}
