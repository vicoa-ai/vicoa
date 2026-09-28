"""Builders for local WebSocket ``update`` payloads.

These mirror ``shared/websocket/envelope.py`` field-for-field so the web
renderer parses local frames exactly like cloud frames. They are duplicated
(not imported) because ``shared.*`` is not part of the packaged CLI
distribution — shape parity is enforced by ``tests/test_local_envelopes.py``.

Timestamps are stored wire-ready by :mod:`vicoa.local_server.store`
(``YYYY-MM-DDTHH:MM:SS.ffffffZ``), so builders pass them through unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import StoredInstance, StoredMessage


def build_new_message_update(msg: "StoredMessage") -> dict:
    """``update`` payload for a newly inserted message row (append-only)."""
    return {
        "entity": "messages",
        "entity_id": msg.id,
        "event_id": f"{msg.id}:insert",
        "body": {
            "t": "new-message",
            "id": msg.id,
            "instance_id": msg.agent_instance_id,
            "sender_type": msg.sender_type,
            "sender_user_id": msg.sender_user_id,
            "content": msg.content,
            "created_at": msg.created_at,
            "requires_user_input": msg.requires_user_input,
            "message_metadata": msg.message_metadata,
        },
    }


def _instance_row(inst: "StoredInstance", t: str) -> dict:
    """Complete instance row as JSON primitives (mirrors envelope._instance_row)."""
    return {
        "t": t,
        "id": inst.id,
        "user_agent_id": inst.user_agent_id,
        "status": inst.status,
        "name": inst.name,
        "project": inst.project,
        "home_dir": inst.home_dir,
        "started_at": inst.started_at,
        "ended_at": inst.ended_at,
        "last_heartbeat_at": inst.last_heartbeat_at,
        "machine_id": inst.machine_id,
        "instance_metadata": inst.instance_metadata,
        "session_config": inst.session_config,
        "has_git_changes": inst.git_diff is not None,
        "updated_at": inst.updated_at,
        "pinned_at": inst.pinned_at,
    }


def build_instance_created_update(inst: "StoredInstance") -> dict:
    """``update`` payload for a newly registered agent instance."""
    return {
        "entity": "agent_instances",
        "entity_id": inst.id,
        "event_id": f"{inst.id}:insert",
        "body": _instance_row(inst, "instance-created"),
    }


def build_instance_update(inst: "StoredInstance") -> dict:
    """``update`` payload for an agent instance status/metadata change."""
    return {
        "entity": "agent_instances",
        "entity_id": inst.id,
        "event_id": f"{inst.id}:update",
        "body": _instance_row(inst, "instance-update"),
    }


def build_machine_update_body(
    *,
    machine_id: str,
    display_name: str | None,
    hostname: str | None,
    platform: str | None,
    home_dir: str | None,
    last_heartbeat_at: str | None,
    machine_metadata: dict | None,
    created_at: str | None,
    updated_at: str | None,
) -> dict:
    """A ``machine-update`` body (mirrors envelope.build_machine_update)."""
    return {
        "t": "machine-update",
        "id": machine_id,
        "display_name": display_name,
        "hostname": hostname,
        "platform": platform,
        "home_dir": home_dir,
        "last_heartbeat_at": last_heartbeat_at,
        "machine_metadata": machine_metadata,
        "created_at": created_at,
        "updated_at": updated_at,
    }
