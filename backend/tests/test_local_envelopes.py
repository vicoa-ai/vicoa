"""Shape parity: local envelope builders vs the cloud's shared builders.

``vicoa.local_server`` cannot import ``shared.*`` at runtime (not part of the
packaged CLI), so the local builders duplicate the shapes. This test is the
drift guard: identical input rows must produce byte-identical payloads.
"""

from datetime import datetime
from uuid import uuid4

from shared.database.enums import AgentStatus, SenderType
from shared.database.models import AgentInstance, Machine, Message
from shared.websocket.envelope import (
    build_instance_created_update as shared_instance_created,
    build_instance_update as shared_instance_update,
    build_machine_update as shared_machine_update,
    build_new_message_update as shared_new_message,
)

from servers.shared.db.queries import WS_FETCH_PAGE_LIMIT, WS_FETCH_SAFETY_WINDOW
from vicoa.local_server import envelopes as local_envelopes
from vicoa.local_server import store as local_store_module
from vicoa.local_server.store import StoredInstance, StoredMessage

# Naive UTC, matching the cloud DB's TIMESTAMP WITHOUT TIME ZONE columns —
# shared._iso appends "Z", which is exactly the local store's wire format.
_TS = datetime(2026, 5, 20, 12, 0, 0, 123456)
_TS_WIRE = "2026-05-20T12:00:00.123456Z"


def test_new_message_payload_parity() -> None:
    message_id = uuid4()
    instance_id = uuid4()
    orm = Message(
        id=message_id,
        agent_instance_id=instance_id,
        sender_type=SenderType.USER,
        sender_user_id=None,
        content="hello",
        created_at=_TS,
        requires_user_input=True,
        message_metadata={"k": "v"},
    )
    stored = StoredMessage(
        id=str(message_id),
        agent_instance_id=str(instance_id),
        sender_type="USER",
        content="hello",
        requires_user_input=True,
        message_metadata={"k": "v"},
        created_at=_TS_WIRE,
        sender_user_id=None,
        seq=1,
    )
    assert local_envelopes.build_new_message_update(stored) == shared_new_message(orm)


# A minimal valid unified diff — the ORM's git_diff validator rejects
# anything else, and has_git_changes parity needs a non-null diff.
_GIT_DIFF = (
    "diff --git a/f.txt b/f.txt\n"
    "index 0000000..1111111 100644\n"
    "--- a/f.txt\n"
    "+++ b/f.txt\n"
    "@@ -1 +1 @@\n"
    "-a\n"
    "+b\n"
)


def _paired_instance() -> tuple[AgentInstance, StoredInstance]:
    instance_id = uuid4()
    user_agent_id = uuid4()
    orm = AgentInstance(
        id=instance_id,
        user_agent_id=user_agent_id,
        user_id=uuid4(),
        status=AgentStatus.AWAITING_INPUT,
        started_at=_TS,
        ended_at=None,
        last_heartbeat_at=_TS,
        git_diff=_GIT_DIFF,
        name="my session",
        project="/code",
        home_dir="/home/nick",
        instance_metadata={"source": "app"},
        session_config={"agent": "claude"},
        updated_at=_TS,
        pinned_at=None,
    )
    stored = StoredInstance(
        id=str(instance_id),
        user_agent_id=str(user_agent_id),
        agent_type_name="Claude Code",
        status="AWAITING_INPUT",
        name="my session",
        project="/code",
        home_dir="/home/nick",
        machine_id=None,
        started_at=_TS_WIRE,
        ended_at=None,
        last_heartbeat_at=_TS_WIRE,
        last_read_message_id=None,
        instance_metadata={"source": "app"},
        session_config={"agent": "claude"},
        git_diff=_GIT_DIFF,
        updated_at=_TS_WIRE,
        pinned_at=None,
    )
    return orm, stored


def test_instance_created_payload_parity() -> None:
    orm, stored = _paired_instance()
    assert local_envelopes.build_instance_created_update(
        stored
    ) == shared_instance_created(orm)


def test_instance_update_payload_parity() -> None:
    orm, stored = _paired_instance()
    assert local_envelopes.build_instance_update(stored) == shared_instance_update(orm)


def test_machine_update_body_parity() -> None:
    machine_id = uuid4()
    orm = Machine(
        id=machine_id,
        user_id=uuid4(),
        display_name="mac",
        hostname="mac.local",
        platform="macOS-15",
        home_dir="/Users/dev",
        last_heartbeat_at=_TS,
        machine_metadata={"available_agents": {"claude": True}},
        created_at=_TS,
        updated_at=_TS,
    )
    local_body = local_envelopes.build_machine_update_body(
        machine_id=str(machine_id),
        display_name="mac",
        hostname="mac.local",
        platform="macOS-15",
        home_dir="/Users/dev",
        last_heartbeat_at=_TS_WIRE,
        machine_metadata={"available_agents": {"claude": True}},
        created_at=_TS_WIRE,
        updated_at=_TS_WIRE,
    )
    assert local_body == shared_machine_update(orm)["body"]


def test_agent_status_values_parity() -> None:
    assert local_store_module.AGENT_STATUS_VALUES == {
        status.value for status in AgentStatus
    }


def test_ws_fetch_constants_parity() -> None:
    assert local_store_module.WS_FETCH_PAGE_LIMIT == WS_FETCH_PAGE_LIMIT
    assert local_store_module.WS_FETCH_SAFETY_WINDOW == WS_FETCH_SAFETY_WINDOW


def test_store_timestamps_use_the_wire_format() -> None:
    stamp = local_store_module.utc_now_iso()
    assert stamp.endswith("Z")
    # Fixed-width (microseconds always present) so lexicographic order is
    # chronological order.
    assert len(stamp) == len(_TS_WIRE)
