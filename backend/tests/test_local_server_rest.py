"""Local server REST subset: nonce auth + backend-shape parity.

Covers the renderer subset (instances list/detail, message post, machines)
and the SDK subset the headless agent calls (register, agent message,
pending, status, user message, request-input, end session).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from vicoa.local_server.app import (
    LOCAL_FREE_AGENT_LIMIT,
    LOCAL_SUBSCRIPTION_ID,
    LOCAL_USER_ID,
    create_local_app,
)
from vicoa.local_server.store import LocalStore
from vicoa.terminal.service import TerminalService

NONCE = "0123456789abcdef0123456789abcdef"
ORIGIN = "http://localhost:3000"
AUTH = {"Authorization": f"Bearer {NONCE}"}


class StubDaemon:
    """The slice of MachineDaemon the local app consumes."""

    machine_id: str | None = None

    def _handle_rpc_request(self, frame: dict) -> dict:
        return {"echoed_method": frame.get("method")}

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
        return {"claude": True, "codex": False}

    def _capabilities(self) -> list[str]:
        return ["worktree"]


@pytest.fixture
def store(tmp_path: Path) -> Iterator[LocalStore]:
    s = LocalStore(tmp_path / "store.db")
    yield s
    s.close()


@pytest.fixture
def client(store: LocalStore) -> Iterator[TestClient]:
    app = create_local_app(
        daemon=StubDaemon(),
        store=store,
        nonce=NONCE,
        allowed_origin=ORIGIN,
        local_only=True,
        terminal=TerminalService(),
    )
    with TestClient(app) as test_client:
        yield test_client


def _register(client: TestClient, instance_id: str | None = None) -> str:
    payload: dict = {"agent_type": "Claude Code", "project": "/tmp/proj"}
    if instance_id:
        payload["agent_instance_id"] = instance_id
    response = client.post("/api/v1/agent-instances", json=payload, headers=AUTH)
    assert response.status_code == 201, response.text
    return response.json()["agent_instance_id"]


# ----------------------------------------------------------------------
# Health + auth
# ----------------------------------------------------------------------
def test_healthz_needs_no_auth(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "mode": "local-only",
        "machine_id": "local",
        # No cloud link exists in local-only mode; the tray reads null as
        # "nothing to report" (vs connecting/connected/auth_failed in cloud
        # mode).
        "cloud": None,
    }


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/agent-instances",
        "/api/v1/machines",
        "/api/v1/messages/pending?agent_instance_id=x",
        "/api/v1/files",
        "/api/v1/commands/claude",
        "/api/v1/commands",
        "/api/v1/agent-catalog",
        "/api/v1/machines/local/agent-models",
        "/api/v1/billing/subscription",
    ],
)
def test_rest_rejects_missing_bearer(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 401


def test_rest_rejects_wrong_nonce(client: TestClient) -> None:
    response = client.get(
        "/api/v1/agent-instances", headers={"Authorization": "Bearer wrong"}
    )
    assert response.status_code == 401


# ----------------------------------------------------------------------
# SDK subset
# ----------------------------------------------------------------------
def test_register_shape_and_conflict(client: TestClient) -> None:
    instance_id = "33333333-3333-3333-3333-333333333333"
    response = client.post(
        "/api/v1/agent-instances",
        json={
            "agent_type": "Claude Code",
            "agent_instance_id": instance_id,
            "transport": "ws",
            "source": "app",
            "session_config": {"agent": "claude"},
        },
        headers=AUTH,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["agent_instance_id"] == instance_id
    assert body["status"] == "ACTIVE"
    assert body["machine_id"] == "local"
    assert body["session_config"] == {"agent": "claude"}
    assert body["instance_metadata"] == {"transport": "ws", "source": "app"}
    assert body["agent_type_name"] == "Claude Code"

    duplicate = client.post(
        "/api/v1/agent-instances",
        json={"agent_type": "Claude Code", "agent_instance_id": instance_id},
        headers=AUTH,
    )
    assert duplicate.status_code == 409


def test_agent_message_returns_queued_user_messages(client: TestClient) -> None:
    instance_id = _register(client)
    # Renderer posts a user message; it must stay pending for the agent.
    posted = client.post(
        f"/api/v1/agent-instances/{instance_id}/messages",
        json={"content": "do the thing"},
        headers=AUTH,
    )
    assert posted.status_code == 200
    message = posted.json()
    assert message["sender_type"] == "USER"
    assert message["sender_user_id"] == LOCAL_USER_ID
    assert message["created_at"].endswith("Z")

    agent_reply = client.post(
        "/api/v1/messages/agent",
        json={
            "agent_instance_id": instance_id,
            "content": "on it",
            "requires_user_input": False,
        },
        headers=AUTH,
    )
    assert agent_reply.status_code == 200
    body = agent_reply.json()
    assert body["success"] is True
    assert body["agent_instance_id"] == instance_id
    assert [m["content"] for m in body["queued_user_messages"]] == ["do the thing"]
    # SDK-flavor MessageResponse (servers.api.models): no sender_user_* keys.
    assert set(body["queued_user_messages"][0]) == {
        "id",
        "content",
        "sender_type",
        "created_at",
        "requires_user_input",
        "message_metadata",
    }


def test_pending_flow_and_stale(client: TestClient) -> None:
    instance_id = _register(client)
    client.post(
        f"/api/v1/agent-instances/{instance_id}/messages",
        json={"content": "ping"},
        headers=AUTH,
    )
    pending = client.get(
        "/api/v1/messages/pending",
        params={"agent_instance_id": instance_id, "last_read_message_id": ""},
        headers=AUTH,
    )
    assert pending.status_code == 200
    body = pending.json()
    assert body["status"] == "ok"
    assert [m["content"] for m in body["messages"]] == ["ping"]

    stale = client.get(
        "/api/v1/messages/pending",
        params={
            "agent_instance_id": instance_id,
            "last_read_message_id": "not-the-cursor",
        },
        headers=AUTH,
    )
    assert stale.json()["status"] == "stale"


def test_status_update_shape(client: TestClient) -> None:
    instance_id = _register(client)
    response = client.put(
        f"/api/v1/agent-instances/{instance_id}/status",
        json={"status": "AWAITING_INPUT"},
        headers=AUTH,
    )
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "instance_id": instance_id,
        "status": "AWAITING_INPUT",
    }
    assert (
        client.put(
            f"/api/v1/agent-instances/{instance_id}/status",
            json={"status": "NOT_A_STATUS"},
            headers=AUTH,
        ).status_code
        == 400
    )
    assert (
        client.put(
            "/api/v1/agent-instances/44444444-4444-4444-4444-444444444444/status",
            json={"status": "ACTIVE"},
            headers=AUTH,
        ).status_code
        == 404
    )


def test_user_message_endpoint_marks_read(client: TestClient) -> None:
    instance_id = _register(client)
    response = client.post(
        "/api/v1/messages/user",
        json={
            "agent_instance_id": instance_id,
            "content": "noted",
            "mark_as_read": True,
        },
        headers=AUTH,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True and body["marked_as_read"] is True
    # Marked read on arrival: not pending.
    pending = client.get(
        "/api/v1/messages/pending",
        params={"agent_instance_id": instance_id},
        headers=AUTH,
    )
    assert pending.json()["messages"] == []


def test_request_input_and_end_session(client: TestClient) -> None:
    instance_id = _register(client)
    reply = client.post(
        "/api/v1/messages/agent",
        json={"agent_instance_id": instance_id, "content": "need input?"},
        headers=AUTH,
    ).json()
    marked = client.patch(
        f"/api/v1/messages/{reply['message_id']}/request-input", headers=AUTH
    )
    assert marked.status_code == 200
    body = marked.json()
    assert body["agent_instance_id"] == instance_id
    assert body["messages"] == [] and body["status"] == "ok"

    ended = client.post(
        "/api/v1/sessions/end",
        json={"agent_instance_id": instance_id},
        headers=AUTH,
    )
    assert ended.status_code == 200
    assert ended.json() == {
        "success": True,
        "agent_instance_id": instance_id,
        "final_status": "COMPLETED",
    }


# ----------------------------------------------------------------------
# Renderer subset
# ----------------------------------------------------------------------
def test_instance_list_and_detail_shapes(client: TestClient) -> None:
    instance_id = _register(client)
    client.post(
        f"/api/v1/agent-instances/{instance_id}/messages",
        json={"content": "hello there"},
        headers=AUTH,
    )

    listed = client.get("/api/v1/agent-instances", headers=AUTH)
    assert listed.status_code == 200
    page = listed.json()
    assert page["total"] == 1 and page["has_more"] is False
    item = page["items"][0]
    assert item["id"] == instance_id
    assert item["latest_message"] == "hello there"
    assert item["chat_length"] == 1
    assert item["machine_id"] == "local"

    detail = client.get(
        f"/api/v1/agent-instances/{instance_id}",
        params={"message_limit": 50},
        headers=AUTH,
    )
    assert detail.status_code == 200
    body = detail.json()
    # The exact field set the chat page's AgentInstanceDetail parser reads.
    assert {
        "id",
        "agent_type_id",
        "agent_type_name",
        "name",
        "status",
        "started_at",
        "ended_at",
        "git_diff",
        "messages",
        "last_read_message_id",
        "last_heartbeat_at",
        "access_level",
        "is_owner",
        "instance_metadata",
        "session_config",
        "project",
        "home_dir",
        "machine_id",
    } <= set(body)
    assert body["is_owner"] is True and body["access_level"] == "WRITE"
    assert [m["content"] for m in body["messages"]] == ["hello there"]

    missing = client.get(
        "/api/v1/agent-instances/55555555-5555-5555-5555-555555555555",
        headers=AUTH,
    )
    assert missing.status_code == 404


def test_detail_message_pagination_cursor(client: TestClient) -> None:
    instance_id = _register(client)
    for index in range(3):
        client.post(
            f"/api/v1/agent-instances/{instance_id}/messages",
            json={"content": f"m{index}"},
            headers=AUTH,
        )
    tail = client.get(
        f"/api/v1/agent-instances/{instance_id}",
        params={"message_limit": 2},
        headers=AUTH,
    ).json()["messages"]
    assert [m["content"] for m in tail] == ["m1", "m2"]
    older = client.get(
        f"/api/v1/agent-instances/{instance_id}",
        params={"message_limit": 2, "before_message_id": tail[0]["id"]},
        headers=AUTH,
    ).json()["messages"]
    assert [m["content"] for m in older] == ["m0"]


def test_machines_synthetic_row(client: TestClient) -> None:
    response = client.get("/api/v1/machines", headers=AUTH)
    assert response.status_code == 200
    machines = response.json()["machines"]
    assert len(machines) == 1
    machine = machines[0]
    assert machine["machine_id"] == "local"
    assert machine["metadata"]["available_agents"] == {
        "claude": True,
        "codex": False,
    }
    assert machine["metadata"]["capabilities"] == ["worktree"]
    assert machine["last_heartbeat_at"].endswith("Z")
    assert machine["recent_directories"] == []


# ----------------------------------------------------------------------
# Chat-input helpers: @-mention files + slash commands + new-session catalog
# ----------------------------------------------------------------------
def test_file_mentions_lists_project_files(client: TestClient, tmp_path: Path) -> None:
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    (project / "README.md").write_text("hi")
    (project / "src" / "main.py").write_text("print(1)")
    (project / ".gitignore").write_text("ignored.txt\n")
    (project / "ignored.txt").write_text("secret")

    response = client.get(
        "/api/v1/files", params={"project_path": str(project)}, headers=AUTH
    )
    assert response.status_code == 200
    body = response.json()
    assert body["project_path"] == str(project)
    assert body["file_count"] == len(body["files"])
    # Files surface as forward-slash paths relative to the project root.
    assert "README.md" in body["files"]
    assert "src/main.py" in body["files"]
    # Nested dirs surface as folder entries (trailing slash) — the same shape
    # the CLI syncs, so the renderer's parser handles them unchanged.
    assert "src/" in body["files"]
    # .gitignore'd files are excluded (same ignore rules as the cloud sync).
    assert "ignored.txt" not in body["files"]


def test_file_mentions_empty_without_project_path(client: TestClient) -> None:
    response = client.get("/api/v1/files", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"project_path": "", "files": [], "file_count": 0}


def test_slash_commands_claude_shape(client: TestClient) -> None:
    response = client.get("/api/v1/commands/claude", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["agent_type"] == "claude"
    assert isinstance(body["commands"], list)
    for command in body["commands"]:
        assert {"name", "description", "kind"} <= set(command)
        assert set(command) <= {"name", "description", "kind", "insert"}
        assert isinstance(command["name"], str)
        assert isinstance(command["description"], str)
        assert command["kind"] in {"command", "skill"}


def test_slash_commands_agent_without_source_is_empty(client: TestClient) -> None:
    # Codex now has a local source (~/.codex, ~/.agents); opencode does not.
    response = client.get("/api/v1/commands/opencode", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"agent_type": "opencode", "commands": []}


def test_slash_commands_list_shape(client: TestClient) -> None:
    response = client.get("/api/v1/commands", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    for entry in body:
        assert set(entry) == {"agent_type", "commands"}
        assert isinstance(entry["commands"], list)
    # An agent without a local source scans empty, so the list is empty.
    filtered = client.get(
        "/api/v1/commands", params={"agent_type": "opencode"}, headers=AUTH
    )
    assert filtered.status_code == 200
    assert filtered.json() == []


def test_agent_catalog_served_with_etag(client: TestClient) -> None:
    response = client.get("/api/v1/agent-catalog", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body.get("agents"), list) and body["agents"]
    etag = response.headers.get("etag")
    assert etag
    # Conditional GET short-circuits to 304 (renderer caches the catalog).
    cached = client.get(
        "/api/v1/agent-catalog", headers={**AUTH, "If-None-Match": etag}
    )
    assert cached.status_code == 304


def test_machine_agent_models_empty(client: TestClient) -> None:
    response = client.get("/api/v1/machines/local/agent-models", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"agent_models": {}}


# ----------------------------------------------------------------------
# Delete session + auth/billing stubs
# ----------------------------------------------------------------------
def test_delete_instance_removes_instance_and_messages(client: TestClient) -> None:
    instance_id = _register(client)
    client.post(
        f"/api/v1/agent-instances/{instance_id}/messages",
        json={"content": "hello"},
        headers=AUTH,
    )
    # Present before delete.
    assert client.get("/api/v1/agent-instances", headers=AUTH).json()["total"] == 1

    deleted = client.delete(f"/api/v1/agent-instances/{instance_id}", headers=AUTH)
    assert deleted.status_code == 200
    assert deleted.json() == {"message": "Agent instance deleted successfully"}

    # Gone from the list and its detail 404s; messages are wiped.
    listed = client.get("/api/v1/agent-instances", headers=AUTH).json()
    assert listed["total"] == 0 and listed["items"] == []
    assert (
        client.get(f"/api/v1/agent-instances/{instance_id}", headers=AUTH).status_code
        == 404
    )

    # Idempotent: re-deleting the soft-deleted row still returns 200 (cloud
    # parity — the row is found by id regardless of status).
    again = client.delete(f"/api/v1/agent-instances/{instance_id}", headers=AUTH)
    assert again.status_code == 200


def test_delete_unknown_instance_404(client: TestClient) -> None:
    missing = client.delete(
        "/api/v1/agent-instances/66666666-6666-6666-6666-666666666666",
        headers=AUTH,
    )
    assert missing.status_code == 404


def test_delete_requires_bearer(client: TestClient) -> None:
    instance_id = _register(client)
    assert client.delete(f"/api/v1/agent-instances/{instance_id}").status_code == 401
    # The unauthorized call must not have deleted it.
    assert client.get("/api/v1/agent-instances", headers=AUTH).json()["total"] == 1


def test_sync_user_returns_success(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/sync-user",
        json={"id": "abc", "email": "a@b.c", "display_name": None},
        headers=AUTH,
    )
    assert response.status_code == 200
    assert response.json() == {"message": "User synced successfully"}


def test_sync_user_requires_bearer(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/sync-user",
        json={"id": "abc", "email": "a@b.c", "display_name": None},
    )
    assert response.status_code == 401


def test_billing_subscription_free_shape(client: TestClient) -> None:
    response = client.get("/api/v1/billing/subscription", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {
        "id": LOCAL_SUBSCRIPTION_ID,
        "plan_type": "free",
        "agent_limit": LOCAL_FREE_AGENT_LIMIT,
        "current_period_end": None,
        "cancel_at_period_end": False,
        "provider": None,
    }


def test_machines_empty_in_cloud_mode(store: LocalStore, tmp_path: Path) -> None:
    app = create_local_app(
        daemon=StubDaemon(),
        store=LocalStore(tmp_path / "cloud-store.db"),
        nonce=NONCE,
        allowed_origin=ORIGIN,
        local_only=False,
        terminal=TerminalService(),
    )
    with TestClient(app) as cloud_client:
        response = cloud_client.get("/api/v1/machines", headers=AUTH)
        assert response.json() == {"machines": []}
        health = cloud_client.get("/healthz").json()
        assert health["mode"] == "cloud" and health["machine_id"] is None
