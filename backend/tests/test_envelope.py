"""Behavioral tests for update/ephemeral frame builders (websocket-migration §2.4-2.7).

Envelope builders snapshot one ORM row into a plain dict of JSON primitives.
They run inside the transaction (§2.7) and must never leave a lazy ORM
attribute, UUID, datetime, or enum in the result — every test asserts the
payload survives `json.dumps`.
"""

import json
from datetime import datetime, timezone
from uuid import uuid4

from shared.database.enums import AgentStatus, SenderType
from shared.database.models import (
    AgentInstance,
    Machine,
    MachineSpawnRequest,
    Message,
)
from shared.websocket.envelope import (
    build_ephemeral,
    build_instance_created_update,
    build_instance_update,
    build_machine_update,
    build_message_update,
    build_new_message_update,
    build_spawn_request_update,
)


def _instance() -> AgentInstance:
    return AgentInstance(
        id=uuid4(),
        user_agent_id=uuid4(),
        user_id=uuid4(),
        status=AgentStatus.ACTIVE,
        started_at=_TS,
        ended_at=None,
        last_heartbeat_at=_TS,
        git_diff=None,
        name="my-session",
        project="/code",
        home_dir="/home/nick",
        instance_metadata={"k": "v"},
        updated_at=_TS,
    )


_TS = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_build_new_message_update_produces_a_messages_payload() -> None:
    msg = Message(
        id=uuid4(),
        agent_instance_id=uuid4(),
        sender_type=SenderType.AGENT,
        sender_user_id=None,
        content="hello",
        created_at=_TS,
        requires_user_input=False,
        message_metadata=None,
    )

    payload = build_new_message_update(msg)

    assert payload["entity"] == "messages"
    assert payload["entity_id"] == str(msg.id)
    assert payload["event_id"] == f"{msg.id}:insert"
    assert payload["body"]["t"] == "new-message"
    assert payload["body"]["instance_id"] == str(msg.agent_instance_id)
    assert payload["body"]["content"] == "hello"
    assert payload["body"]["created_at"] == _TS.isoformat()
    json.dumps(payload)  # §2.7: JSON-serializable, no lazy ORM attributes


def test_build_message_update_produces_a_queue_patch_payload() -> None:
    msg = Message(
        id=uuid4(),
        agent_instance_id=uuid4(),
        sender_type=SenderType.AGENT,
        sender_user_id=None,
        content="hello",
        created_at=_TS,
        requires_user_input=False,
        message_metadata={"queue": {"status": "running"}},
    )

    payload = build_message_update(msg)

    assert payload["entity"] == "messages"
    assert payload["entity_id"] == str(msg.id)
    assert payload["event_id"] == f"{msg.id}:queue:running"
    assert payload["body"]["t"] == "message-update"
    assert payload["body"]["id"] == str(msg.id)
    assert payload["body"]["instance_id"] == str(msg.agent_instance_id)
    assert payload["body"]["message_metadata"] == {"queue": {"status": "running"}}
    json.dumps(payload)  # §2.7: JSON-serializable, no lazy ORM attributes


def test_build_message_update_handles_missing_queue_metadata() -> None:
    msg = Message(
        id=uuid4(),
        agent_instance_id=uuid4(),
        sender_type=SenderType.AGENT,
        sender_user_id=None,
        content="hello",
        created_at=_TS,
        requires_user_input=False,
        message_metadata=None,
    )

    payload = build_message_update(msg)

    assert payload["event_id"] == f"{msg.id}:queue:None"
    assert payload["body"]["message_metadata"] is None
    json.dumps(payload)


def test_build_instance_update_carries_the_full_row_with_updated_at() -> None:
    inst = _instance()

    payload = build_instance_update(inst)

    assert payload["entity"] == "agent_instances"
    assert payload["entity_id"] == str(inst.id)
    assert payload["event_id"] == f"{inst.id}:update"
    assert payload["body"]["t"] == "instance-update"
    assert payload["body"]["id"] == str(inst.id)
    assert payload["body"]["status"] == "ACTIVE"
    assert payload["body"]["name"] == "my-session"
    assert payload["body"]["has_git_changes"] is False
    assert payload["body"]["updated_at"] == _TS.isoformat()
    json.dumps(payload)


def test_build_instance_created_update_uses_the_created_discriminator() -> None:
    inst = _instance()

    payload = build_instance_created_update(inst)

    assert payload["entity"] == "agent_instances"
    assert payload["event_id"] == f"{inst.id}:insert"
    assert payload["body"]["t"] == "instance-created"
    assert payload["body"]["updated_at"] == _TS.isoformat()
    json.dumps(payload)


def test_build_machine_update_carries_the_full_row_with_updated_at() -> None:
    machine = Machine(
        id=uuid4(),
        user_id=uuid4(),
        display_name="laptop",
        hostname="nick-mbp",
        platform="darwin",
        home_dir="/home/nick",
        last_heartbeat_at=_TS,
        created_at=_TS,
        updated_at=_TS,
        machine_metadata=None,
    )

    payload = build_machine_update(machine)

    assert payload["entity"] == "machines"
    assert payload["entity_id"] == str(machine.id)
    assert payload["event_id"] == f"{machine.id}:update"
    assert payload["body"]["t"] == "machine-update"
    assert payload["body"]["hostname"] == "nick-mbp"
    assert payload["body"]["updated_at"] == _TS.isoformat()
    json.dumps(payload)


def test_build_spawn_request_update_produces_an_append_only_payload() -> None:
    req = MachineSpawnRequest(
        id=uuid4(),
        machine_id=uuid4(),
        requested_by_user_id=uuid4(),
        directory="/code",
        agent="claude",
        status="pending",
        message=None,
        agent_instance_id=None,
        created_at=_TS,
        claimed_at=None,
        completed_at=None,
        request_metadata=None,
    )

    payload = build_spawn_request_update(req)

    assert payload["entity"] == "machine_spawn_requests"
    assert payload["entity_id"] == str(req.id)
    assert payload["event_id"] == f"{req.id}:insert"
    assert payload["body"]["t"] == "spawn-request"
    assert payload["body"]["machine_id"] == str(req.machine_id)
    assert payload["body"]["directory"] == "/code"
    assert payload["body"]["agent_instance_id"] is None
    json.dumps(payload)


def test_build_ephemeral_wraps_a_typed_body() -> None:
    body = build_ephemeral("machine-alive", machine_id="m1")

    assert body == {"t": "machine-alive", "machine_id": "m1"}
