"""Wire-level integration test: ACPClient against a real fake-agent subprocess.

Exercises the full stdio JSON-RPC loop the generic agents ride on:
initialize → session/new → session/prompt with a streamed session/update,
an agent→client session/request_permission round-trip, and non-JSON stdout
noise (Gemini leaks log lines onto stdout — the client must skip them).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

from integrations.headless.acp_client import ACPClient


_FAKE_AGENT = r"""
import json
import sys


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


# Non-JSON stdout noise before the protocol starts (Gemini does this).
print("booting fake agent...", flush=True)

pending_prompt_id = None
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    method = msg.get("method")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {
            "protocolVersion": 1,
            "agentCapabilities": {"loadSession": False},
            "authMethods": [],
        }})
    elif method == "session/new":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {
            "sessionId": "s1",
            "modes": {"currentModeId": "agent",
                      "availableModes": [{"id": "agent"}, {"id": "plan"}]},
        }})
    elif method == "session/prompt":
        sid = msg["params"]["sessionId"]
        pending_prompt_id = msg["id"]
        send({"jsonrpc": "2.0", "method": "session/update", "params": {
            "sessionId": sid,
            "update": {"sessionUpdate": "agent_message_chunk",
                       "content": {"type": "text", "text": "working..."}},
        }})
        send({"jsonrpc": "2.0", "id": 999,
              "method": "session/request_permission", "params": {
                  "sessionId": sid,
                  "toolCall": {"toolCallId": "t1", "title": "Edit", "kind": "edit"},
                  "options": [
                      {"optionId": "allow", "name": "Allow", "kind": "allow_once"},
                      {"optionId": "reject", "name": "Reject", "kind": "reject_once"},
                  ]}})
    elif msg.get("id") == 999 and "result" in msg:
        selected = msg["result"]["outcome"].get("optionId")
        send({"jsonrpc": "2.0", "id": pending_prompt_id, "result": {
            "stopReason": "end_turn", "_selected": selected}})
"""


def test_acp_client_full_wire_roundtrip(tmp_path: Path) -> None:
    agent_script = tmp_path / "fake_acp_agent.py"
    agent_script.write_text(_FAKE_AGENT)

    notifications: list[tuple[str, Dict[str, Any]]] = []
    permission_requests: list[Dict[str, Any]] = []

    def on_request(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        assert method == "session/request_permission"
        permission_requests.append(params)
        return {"outcome": {"outcome": "selected", "optionId": "allow"}}

    client = ACPClient(
        command=[sys.executable, str(agent_script)],
        cwd=str(tmp_path),
        on_notification=lambda m, p: notifications.append((m, p)),
        on_request=on_request,
    )
    client.start()
    try:
        init = client.send_request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False},
                    "terminal": False,
                },
                "clientInfo": {"name": "vicoa", "version": "test"},
            },
            timeout=15.0,
        )
        init.raise_for_error()
        assert init.result is not None and init.result["protocolVersion"] == 1

        new = client.send_request(
            "session/new", {"cwd": str(tmp_path), "mcpServers": []}, timeout=15.0
        )
        new.raise_for_error()
        assert new.result is not None
        session_id = new.result["sessionId"]
        assert new.result["modes"]["currentModeId"] == "agent"

        prompt = client.send_request(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": "hi"}]},
            timeout=15.0,
        )
        prompt.raise_for_error()
        assert prompt.result is not None
        # The fake agent echoes the permission answer back into the prompt
        # result — proves the agent→client request round-trip completed
        # while the prompt request was still pending.
        assert prompt.result["stopReason"] == "end_turn"
        assert prompt.result["_selected"] == "allow"

        assert (
            permission_requests and permission_requests[0]["toolCall"]["kind"] == "edit"
        )
        update_methods = [m for m, _ in notifications]
        assert "session/update" in update_methods
    finally:
        client.stop()
