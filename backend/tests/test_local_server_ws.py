"""Local /ws endpoint: nonce subprotocol auth, cloud frame grammar, pty RPC.

Mirrors the cloud handshake tests (tests/test_ws_endpoint.py) but against the
desktop local server: credentials ride the subprotocol list
(``vicoa-local.<nonce>`` for the renderer, ``vicoa-key.<nonce>`` for the
headless child), Origin is pinned when present, and rpc-calls route into the
local dispatcher without a machine-routing hop.
"""

import base64
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from vicoa.local_server.app import create_local_app
from vicoa.local_server.store import LocalStore
from vicoa.terminal.service import TerminalService

NONCE = "fedcba9876543210fedcba9876543210"
ORIGIN = "http://localhost:3000"
GOOD_SUBPROTOCOLS = ["vicoa-ws", f"vicoa-local.{NONCE}"]
AUTH = {"Authorization": f"Bearer {NONCE}"}


class StubDaemon:
    machine_id: str | None = None

    def _handle_rpc_request(self, frame: dict) -> dict:
        method = frame.get("method")
        if method == "list-files":
            return {"entries": []}
        return {"error": f"unknown RPC method: {method}"}

    def _supported_rpc_methods(self) -> list[str]:
        return [
            "spawn-session",
            "list-files",
            "read-file",
            "git-status",
            "git-diff",
            "git-worktree-list",
            "git-worktree-remove",
        ]

    def _detect_available_agents(self) -> dict[str, bool]:
        return {"claude": True}

    def _capabilities(self) -> list[str]:
        return ["worktree"]


@pytest.fixture
def store(tmp_path: Path) -> Iterator[LocalStore]:
    s = LocalStore(tmp_path / "store.db")
    yield s
    s.close()


@pytest.fixture
def terminal() -> Iterator[TerminalService]:
    svc = TerminalService()
    yield svc
    svc.shutdown()


@pytest.fixture
def client(store: LocalStore, terminal: TerminalService) -> Iterator[TestClient]:
    app = create_local_app(
        daemon=StubDaemon(),
        store=store,
        nonce=NONCE,
        allowed_origin=ORIGIN,
        local_only=True,
        terminal=terminal,
    )
    with TestClient(app) as test_client:
        yield test_client


def _handshake(ws: Any, scope: str = "user-scoped", **fields: Any) -> dict:
    ws.send_json({"type": "hello", "scope": scope, **fields})
    return ws.receive_json()


# ----------------------------------------------------------------------
# Handshake / auth
# ----------------------------------------------------------------------
def test_accepts_renderer_nonce_subprotocol(client: TestClient) -> None:
    with client.websocket_connect("/ws", subprotocols=GOOD_SUBPROTOCOLS) as ws:
        info = _handshake(ws)
        assert info["type"] == "server_info"
        assert info["body"]["server_version"] == "1.0.0"
        assert isinstance(info["body"]["user_id"], str)
        assert ws.accepted_subprotocol == "vicoa-ws"


def test_accepts_headless_child_vicoa_key_subprotocol(client: TestClient) -> None:
    with client.websocket_connect(
        "/ws", subprotocols=["vicoa-ws", f"vicoa-key.{NONCE}"]
    ) as ws:
        info = _handshake(ws, scope="session-scoped", instance_id="abc")
        assert info["type"] == "server_info"


def test_rejects_wrong_nonce(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(
            "/ws", subprotocols=["vicoa-ws", "vicoa-local.wrong-nonce"]
        ) as ws:
            ws.receive_json()
    assert excinfo.value.code == 4401


def test_rejects_missing_credential_subprotocol(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws", subprotocols=["vicoa-ws"]) as ws:
            ws.receive_json()
    assert excinfo.value.code == 4401


def test_rejects_foreign_origin(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(
            "/ws",
            subprotocols=GOOD_SUBPROTOCOLS,
            headers={"Origin": "http://evil.example"},
        ) as ws:
            ws.receive_json()
    assert excinfo.value.code == 4403


def test_accepts_allowed_origin(client: TestClient) -> None:
    with client.websocket_connect(
        "/ws", subprotocols=GOOD_SUBPROTOCOLS, headers={"Origin": ORIGIN}
    ) as ws:
        assert _handshake(ws)["type"] == "server_info"


def test_agent_vicoa_key_is_exempt_from_origin_check(client: TestClient) -> None:
    """The headless agent connects with ``vicoa-key.`` and a loopback Origin
    that ``websocket-client`` stamps automatically (``http://127.0.0.1:<port>``,
    which never matches the renderer origin). It must NOT be rejected — the
    nonce is the credential; only the browser renderer (``vicoa-local.``) is
    Origin-checked. Regression for the local-mode "agent never replies" bug
    (its session WS was 403'd, so user messages never reached Claude)."""
    with client.websocket_connect(
        "/ws",
        subprotocols=["vicoa-ws", f"vicoa-key.{NONCE}"],
        headers={"Origin": "http://127.0.0.1:8931"},
    ) as ws:
        info = _handshake(ws, scope="session-scoped", instance_id="abc")
        assert info["type"] == "server_info"


def test_rejects_malformed_hello(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws", subprotocols=GOOD_SUBPROTOCOLS) as ws:
            ws.send_json({"type": "hello", "scope": "galaxy-scoped"})
            ws.receive_json()
    assert excinfo.value.code == 4400


def test_ping_pong(client: TestClient) -> None:
    with client.websocket_connect("/ws", subprotocols=GOOD_SUBPROTOCOLS) as ws:
        _handshake(ws)
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


# ----------------------------------------------------------------------
# Catch-up fetches
# ----------------------------------------------------------------------
def test_fetch_machines_returns_synthetic_local_row(client: TestClient) -> None:
    with client.websocket_connect("/ws", subprotocols=GOOD_SUBPROTOCOLS) as ws:
        _handshake(ws)
        ws.send_json({"type": "fetch_machines_request", "request_id": "m1"})
        frame = ws.receive_json()
        assert frame["type"] == "fetch_machines_response"
        assert frame["request_id"] == "m1"
        [row] = frame["rows"]
        assert row["t"] == "machine-update"
        assert row["id"] == "local"
        assert row["machine_metadata"]["available_agents"] == {"claude": True}


def test_fetch_instances_and_messages_roundtrip(
    client: TestClient, store: LocalStore
) -> None:
    inst = store.register_instance(agent_type="Claude Code")
    store.add_user_message(agent_instance_id=inst.id, content="hi", mark_as_read=False)
    store.add_agent_message(agent_instance_id=inst.id, content="hello back")

    with client.websocket_connect("/ws", subprotocols=GOOD_SUBPROTOCOLS) as ws:
        _handshake(ws)
        ws.send_json(
            {
                "type": "fetch_instances_request",
                "request_id": "i1",
                "updated_after": None,
            }
        )
        frame = ws.receive_json()
        assert frame["type"] == "fetch_instances_response"
        assert [row["id"] for row in frame["rows"]] == [inst.id]

        ws.send_json(
            {
                "type": "fetch_messages_request",
                "request_id": "f1",
                "instance_id": inst.id,
                "after": None,
            }
        )
        frame = ws.receive_json()
        assert frame["type"] == "fetch_messages_response"
        assert frame["instance_id"] == inst.id
        assert frame["has_more"] is False
        # user-scoped hello → full conversation, cloud policy.
        assert [row["content"] for row in frame["rows"]] == ["hi", "hello back"]


def test_session_scope_gets_user_messages_only(
    client: TestClient, store: LocalStore
) -> None:
    inst = store.register_instance(agent_type="Claude Code")
    store.add_user_message(
        agent_instance_id=inst.id, content="only-user-rows", mark_as_read=False
    )
    with client.websocket_connect(
        "/ws", subprotocols=["vicoa-ws", f"vicoa-key.{NONCE}"]
    ) as ws:
        _handshake(ws, scope="session-scoped", instance_id=inst.id)
        ws.send_json(
            {
                "type": "fetch_messages_request",
                "request_id": "catch-up",
                "instance_id": inst.id,
                "after": None,
            }
        )
        frame = ws.receive_json()
        assert [row["content"] for row in frame["rows"]] == ["only-user-rows"]
        assert all(row["sender_type"] == "USER" for row in frame["rows"])


# ----------------------------------------------------------------------
# Live update broadcast
# ----------------------------------------------------------------------
def test_rest_write_broadcasts_update_frames(client: TestClient) -> None:
    with client.websocket_connect("/ws", subprotocols=GOOD_SUBPROTOCOLS) as ws:
        _handshake(ws)
        response = client.post(
            "/api/v1/agent-instances",
            json={"agent_type": "Claude Code"},
            headers=AUTH,
        )
        instance_id = response.json()["agent_instance_id"]
        client.post(
            f"/api/v1/agent-instances/{instance_id}/messages",
            json={"content": "broadcast me"},
            headers=AUTH,
        )
        created = ws.receive_json()
        assert created["type"] == "update"
        assert created["payload"]["body"]["t"] == "instance-created"
        assert created["payload"]["entity_id"] == instance_id
        new_message = ws.receive_json()
        assert new_message["type"] == "update"
        assert new_message["payload"]["body"]["t"] == "new-message"
        assert new_message["payload"]["body"]["content"] == "broadcast me"


# ----------------------------------------------------------------------
# RPC
# ----------------------------------------------------------------------
def test_rpc_call_routes_into_daemon_dispatch(client: TestClient) -> None:
    with client.websocket_connect("/ws", subprotocols=GOOD_SUBPROTOCOLS) as ws:
        _handshake(ws)
        ws.send_json(
            {
                "type": "rpc-call",
                "request_id": "r1",
                # Any machine_id is accepted — single-machine locality.
                "machine_id": "whatever",
                "method": "list-files",
                "params": {"cwd": "/tmp", "path": ""},
            }
        )
        frame = ws.receive_json()
        assert frame == {
            "type": "rpc-result",
            "request_id": "r1",
            "result": {"entries": []},
        }


def test_rpc_unknown_method_returns_error_result(client: TestClient) -> None:
    with client.websocket_connect("/ws", subprotocols=GOOD_SUBPROTOCOLS) as ws:
        _handshake(ws)
        ws.send_json(
            {
                "type": "rpc-call",
                "request_id": "r2",
                "machine_id": "local",
                "method": "no-such-method",
                "params": {},
            }
        )
        frame = ws.receive_json()
        assert frame["type"] == "rpc-result"
        assert "unknown RPC method" in frame["result"]["error"]


def test_git_worktree_create_on_non_repo_errors(
    client: TestClient, tmp_path: Path
) -> None:
    with client.websocket_connect("/ws", subprotocols=GOOD_SUBPROTOCOLS) as ws:
        _handshake(ws)
        ws.send_json(
            {
                "type": "rpc-call",
                "request_id": "r3",
                "machine_id": "local",
                "method": "git-worktree-create",
                "params": {"cwd": str(tmp_path)},
            }
        )
        frame = ws.receive_json()
        assert frame["type"] == "rpc-result"
        assert frame["result"] == {"error": "not_a_repo"}


@pytest.mark.skipif(sys.platform.startswith("win"), reason="PTY sessions are Unix-only")
def test_pty_spawn_output_exit_over_ws(client: TestClient, tmp_path: Path) -> None:
    with client.websocket_connect("/ws", subprotocols=GOOD_SUBPROTOCOLS) as ws:
        _handshake(ws)
        ws.send_json(
            {
                "type": "rpc-call",
                "request_id": "pty1",
                "machine_id": "local",
                "method": "pty-spawn",
                "params": {
                    "cwd": str(tmp_path),
                    "cols": 80,
                    "rows": 24,
                    "command": ["/bin/sh", "-c", "echo pty-roundtrip"],
                },
            }
        )
        pty_id: str | None = None
        output = b""
        exit_frame: dict | None = None
        # Frames interleave (rpc-result vs reader-thread pushes) — collect
        # until the session reports exit.
        for _ in range(50):
            frame = ws.receive_json()
            if frame["type"] == "rpc-result" and frame["request_id"] == "pty1":
                pty_id = frame["result"]["pty_id"]
            elif frame["type"] == "pty-output":
                output += base64.b64decode(frame["data"])
            elif frame["type"] == "pty-exit":
                exit_frame = frame
                break
        assert pty_id is not None
        assert b"pty-roundtrip" in output
        assert exit_frame is not None
        assert exit_frame["pty_id"] == pty_id
        assert exit_frame["exit_code"] == 0


@pytest.mark.skipif(sys.platform.startswith("win"), reason="PTY sessions are Unix-only")
def test_pty_write_and_kill_over_ws(client: TestClient, tmp_path: Path) -> None:
    with client.websocket_connect("/ws", subprotocols=GOOD_SUBPROTOCOLS) as ws:
        _handshake(ws)
        ws.send_json(
            {
                "type": "rpc-call",
                "request_id": "spawn",
                "machine_id": "local",
                "method": "pty-spawn",
                "params": {
                    "cwd": str(tmp_path),
                    "cols": 80,
                    "rows": 24,
                    "command": ["/bin/cat"],
                },
            }
        )
        result = ws.receive_json()
        assert result["type"] == "rpc-result"
        pty_id = result["result"]["pty_id"]

        ws.send_json(
            {
                "type": "rpc-call",
                "request_id": "write",
                "machine_id": "local",
                "method": "pty-write",
                "params": {
                    "pty_id": pty_id,
                    "data": base64.b64encode(b"echo-me\n").decode("ascii"),
                },
            }
        )
        output = b""
        saw_write_ack = False
        for _ in range(50):
            frame = ws.receive_json()
            if frame["type"] == "rpc-result" and frame["request_id"] == "write":
                saw_write_ack = True
                assert frame["result"] == {}
            elif frame["type"] == "pty-output":
                output += base64.b64decode(frame["data"])
            if saw_write_ack and b"echo-me" in output:
                break
        assert saw_write_ack and b"echo-me" in output

        ws.send_json(
            {
                "type": "rpc-call",
                "request_id": "kill",
                "machine_id": "local",
                "method": "pty-kill",
                "params": {"pty_id": pty_id},
            }
        )
        # The pty-exit push races the kill's rpc-result (the reader thread
        # finalizes while kill() is still closing) — collect until both land.
        saw_kill_ack = False
        saw_exit = False
        for _ in range(50):
            frame = ws.receive_json()
            if frame["type"] == "rpc-result" and frame["request_id"] == "kill":
                saw_kill_ack = True
            elif frame["type"] == "pty-exit" and frame["pty_id"] == pty_id:
                saw_exit = True
            if saw_kill_ack and saw_exit:
                break
        assert saw_kill_ack and saw_exit


def test_pty_write_unknown_id_returns_error_result(client: TestClient) -> None:
    with client.websocket_connect("/ws", subprotocols=GOOD_SUBPROTOCOLS) as ws:
        _handshake(ws)
        ws.send_json(
            {
                "type": "rpc-call",
                "request_id": "w1",
                "machine_id": "local",
                "method": "pty-write",
                "params": {
                    "pty_id": "missing",
                    "data": base64.b64encode(b"x").decode("ascii"),
                },
            }
        )
        frame = ws.receive_json()
        assert frame["type"] == "rpc-result"
        assert "unknown pty_id" in frame["result"]["error"]
