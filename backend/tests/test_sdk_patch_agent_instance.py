"""Unit tests for SDK patch_agent_instance — sync + async.

This is the call site used by the Claude TUI wrapper's JSONLMonitor when
it observes a model or permission_mode change in the Claude jsonl. We
mock the HTTP layer and inspect the PATCH body.
"""

from __future__ import annotations

from typing import Any

import pytest

from vicoa.sdk.async_client import AsyncVicoaClient
from vicoa.sdk.client import VicoaClient


INSTANCE_ID = "00000000-0000-0000-0000-000000000001"
RESPONSE: dict[str, Any] = {
    "agent_instance_id": INSTANCE_ID,
    "agent_type_id": None,
    "agent_type_name": "claude",
    "status": "ACTIVE",
    "name": None,
    "instance_metadata": None,
    "project": None,
    "home_dir": None,
    "session_config": {"agent": "claude", "model": "claude-opus-4-7"},
}


def test_sync_patches_session_config(monkeypatch: pytest.MonkeyPatch) -> None:
    client = VicoaClient(api_key="t", base_url="http://example.invalid")
    captured: dict[str, Any] = {}

    def fake_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return RESPONSE

    monkeypatch.setattr(client, "_make_request", fake_request)

    client.patch_agent_instance(
        agent_instance_id=INSTANCE_ID,
        session_config={"model": "claude-opus-4-7"},
    )
    assert captured["method"] == "PATCH"
    assert captured["path"] == f"/api/v1/agent-instances/{INSTANCE_ID}"
    assert captured["json"] == {"session_config": {"model": "claude-opus-4-7"}}


def test_sync_omits_unset_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty kwargs shouldn't send empty PATCH — the wrapper should noop in
    that case at the call site, but the SDK shouldn't fabricate fields."""
    client = VicoaClient(api_key="t", base_url="http://example.invalid")
    captured: dict[str, Any] = {}

    def fake_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        captured["json"] = kwargs.get("json")
        return RESPONSE

    monkeypatch.setattr(client, "_make_request", fake_request)

    client.patch_agent_instance(agent_instance_id=INSTANCE_ID, name="renamed")
    assert captured["json"] == {"name": "renamed"}, (
        "Only the explicitly-passed name should land in the PATCH body — "
        "session_config wasn't passed, so the server's field-present "
        "semantics preserve it."
    )


async def test_async_patches_session_config(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AsyncVicoaClient(api_key="t", base_url="http://example.invalid")
    captured: dict[str, Any] = {}

    async def fake_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return RESPONSE

    monkeypatch.setattr(client, "_make_request", fake_request)

    await client.patch_agent_instance(
        agent_instance_id=INSTANCE_ID,
        session_config={"permission_mode": "acceptEdits"},
    )
    assert captured["method"] == "PATCH"
    assert captured["json"] == {"session_config": {"permission_mode": "acceptEdits"}}
