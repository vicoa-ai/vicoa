"""Pure unit tests: the SDK stamps the session's machine_id at registration.

Covers plans/machine-management.md D8 — register_agent_instance defaults
machine_id from the daemon state file (read_machine_id) so every wrapper that
registers through the SDK links its session to the machine, with no per-wrapper
edits. No DB, no real network.
"""

from __future__ import annotations

from vicoa.sdk.client import VicoaClient


def _client() -> VicoaClient:
    return VicoaClient(api_key="k", base_url="http://localhost:0")


def _capture_payload(client: VicoaClient, captured: dict) -> None:
    def _fake(method, path, json=None, params=None):
        captured["json"] = json
        return {"agent_instance_id": "inst-1", "status": "active"}

    client._make_request = _fake  # type: ignore[method-assign]


def test_sends_machine_id_from_daemon_state(monkeypatch) -> None:
    monkeypatch.setattr("vicoa.sdk.client.read_machine_id", lambda *_: "mac-xyz")
    client = _client()
    captured: dict = {}
    _capture_payload(client, captured)

    client.register_agent_instance(agent_type="claude")

    assert captured["json"]["machine_id"] == "mac-xyz"


def test_explicit_machine_id_overrides_state(monkeypatch) -> None:
    monkeypatch.setattr("vicoa.sdk.client.read_machine_id", lambda *_: "from-state")
    client = _client()
    captured: dict = {}
    _capture_payload(client, captured)

    client.register_agent_instance(agent_type="claude", machine_id="explicit")

    assert captured["json"]["machine_id"] == "explicit"


def test_omits_machine_id_when_unregistered(monkeypatch) -> None:
    """No daemon state (standalone wrapper) → the key is omitted, so the server
    leaves the session's machine link null rather than receiving an empty id."""
    monkeypatch.setattr("vicoa.sdk.client.read_machine_id", lambda *_: None)
    client = _client()
    captured: dict = {}
    _capture_payload(client, captured)

    client.register_agent_instance(agent_type="claude")

    assert "machine_id" not in captured["json"]


# --- async client: same machine_id behavior (used by headless codex/acp) ---

from vicoa.sdk.async_client import AsyncVicoaClient  # noqa: E402


def _async_client() -> AsyncVicoaClient:
    return AsyncVicoaClient(api_key="k", base_url="http://localhost:0")


def _capture_async_payload(client: AsyncVicoaClient, captured: dict) -> None:
    async def _fake(method, path, json=None, params=None):
        captured["json"] = json
        return {"agent_instance_id": "inst-1", "status": "active"}

    client._make_request = _fake  # type: ignore[method-assign]


async def test_async_sends_machine_id_from_daemon_state(monkeypatch) -> None:
    monkeypatch.setattr(
        "vicoa.sdk.async_client.read_machine_id", lambda *_: "mac-async"
    )
    client = _async_client()
    captured: dict = {}
    _capture_async_payload(client, captured)

    await client.register_agent_instance(agent_type="claude")

    assert captured["json"]["machine_id"] == "mac-async"


async def test_async_omits_machine_id_when_unregistered(monkeypatch) -> None:
    monkeypatch.setattr("vicoa.sdk.async_client.read_machine_id", lambda *_: None)
    client = _async_client()
    captured: dict = {}
    _capture_async_payload(client, captured)

    await client.register_agent_instance(agent_type="claude")

    assert "machine_id" not in captured["json"]
