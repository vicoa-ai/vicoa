"""The SDK sends the title the daemon handed over with an auto-named worktree.

The daemon puts it in VICOA_SESSION_TITLE when the server named the spawn's
worktree from its prompt (`protocol.worktree_naming`); registration carries it
so the session opens titled, and the server's own title generation skips a
session that already has a name. No DB, no real network.
"""

from __future__ import annotations

import asyncio

import pytest

from vicoa.sdk.async_client import AsyncVicoaClient
from vicoa.sdk.client import VicoaClient
from vicoa.utils import SESSION_TITLE_ENV


@pytest.fixture(autouse=True)
def _no_git_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in ("vicoa.sdk.client", "vicoa.sdk.async_client"):
        monkeypatch.setattr(f"{module}.get_worktree_name", lambda _p: None)
        monkeypatch.setattr(f"{module}.get_git_identity", lambda _p: (None, None))


def _client(captured: list[dict]) -> VicoaClient:
    client = VicoaClient(api_key="k", base_url="http://localhost:0")

    def _fake(method, path, json=None, params=None, timeout=None):
        captured.append(json or {})
        return {"agent_instance_id": "inst-1", "status": "active"}

    client._make_request = _fake  # type: ignore[method-assign]
    return client


def test_sends_the_handed_over_title_once(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    monkeypatch.setenv(SESSION_TITLE_ENV, "Fix Safari logout")
    captured: list[dict] = []
    client = _client(captured)

    client.register_agent_instance(agent_type="claude", machine_id="m")
    client.register_agent_instance(agent_type="claude", machine_id="m")

    assert captured[0]["name"] == "Fix Safari logout"
    # A later re-register must not overwrite a title the user changed since.
    assert "name" not in captured[1]
    assert SESSION_TITLE_ENV not in os.environ


def test_an_explicit_name_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SESSION_TITLE_ENV, "Fix Safari logout")
    captured: list[dict] = []

    _client(captured).register_agent_instance(
        agent_type="codex", name="Codex", machine_id="m"
    )

    assert captured[0]["name"] == "Codex"


def test_no_title_without_the_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SESSION_TITLE_ENV, raising=False)
    captured: list[dict] = []

    _client(captured).register_agent_instance(agent_type="claude", machine_id="m")

    assert "name" not in captured[0]


def test_async_client_sends_it_too(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SESSION_TITLE_ENV, "Fix Safari logout")
    captured: list[dict] = []
    client = AsyncVicoaClient(api_key="k", base_url="http://localhost:0")

    async def _fake(method, path, json=None, params=None, timeout=None):
        captured.append(json or {})
        return {"agent_instance_id": "inst-1", "status": "active"}

    client._make_request = _fake  # type: ignore[method-assign]

    asyncio.run(client.register_agent_instance(agent_type="claude", machine_id="m"))

    assert captured[0]["name"] == "Fix Safari logout"
