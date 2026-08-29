"""Unit tests: SDK client forwards session_config into the self-register POST.

The headless wrappers go through `VicoaClient.register_agent_instance` /
`AsyncVicoaClient.register_agent_instance`, so the session_config wiring
must land in both. We mock the HTTP layer and inspect the JSON body —
plan/session-config-storage.md tier 3b §6.5.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from vicoa.sdk.async_client import AsyncVicoaClient
from vicoa.sdk.client import VicoaClient


CLAUDE_CONFIG = {
    "agent": "claude",
    "model": "claude-sonnet-4-6",
    "thinking_effort": "low",
    "permission_mode": "acceptEdits",
}

REGISTER_RESPONSE: dict[str, Any] = {
    "agent_instance_id": "00000000-0000-0000-0000-000000000001",
    "agent_type_id": None,
    "agent_type_name": "claude",
    "status": "ACTIVE",
    "name": None,
    "instance_metadata": None,
    "project": None,
    "home_dir": None,
    "session_config": CLAUDE_CONFIG,
}


def test_sync_client_forwards_session_config(monkeypatch: pytest.MonkeyPatch) -> None:
    client = VicoaClient(api_key="test", base_url="http://example.invalid")
    captured: dict[str, Any] = {}

    def fake_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return REGISTER_RESPONSE

    monkeypatch.setattr(client, "_make_request", fake_request)

    client.register_agent_instance(
        agent_type="claude",
        session_config=CLAUDE_CONFIG,
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/agent-instances"
    assert captured["json"]["session_config"] == CLAUDE_CONFIG


def test_sync_client_omits_session_config_when_not_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = VicoaClient(api_key="test", base_url="http://example.invalid")
    captured: dict[str, Any] = {}

    def fake_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        captured["json"] = kwargs.get("json")
        return REGISTER_RESPONSE

    monkeypatch.setattr(client, "_make_request", fake_request)

    client.register_agent_instance(agent_type="claude")

    assert "session_config" not in captured["json"], (
        "Omitting the kwarg must NOT serialize a null session_config — the "
        "activate-existing branch on the server uses field-present semantics "
        "and an explicit null would erase any pre-staged value."
    )


async def test_async_client_forwards_session_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AsyncVicoaClient(api_key="test", base_url="http://example.invalid")
    captured: dict[str, Any] = {}

    async def fake_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return REGISTER_RESPONSE

    monkeypatch.setattr(client, "_make_request", fake_request)

    await client.register_agent_instance(
        agent_type="claude",
        session_config=CLAUDE_CONFIG,
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/agent-instances"
    assert captured["json"]["session_config"] == CLAUDE_CONFIG


async def test_async_client_omits_session_config_when_not_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AsyncVicoaClient(api_key="test", base_url="http://example.invalid")
    captured: dict[str, Any] = {}

    async def fake_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        captured["json"] = kwargs.get("json")
        return REGISTER_RESPONSE

    monkeypatch.setattr(client, "_make_request", fake_request)

    await client.register_agent_instance(agent_type="claude")

    assert "session_config" not in captured["json"]


# Silence unused import warning — we keep MagicMock available for future
# expansions of this file.
_ = MagicMock
