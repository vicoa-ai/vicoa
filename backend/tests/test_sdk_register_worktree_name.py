"""The SDK stamps the session's worktree at registration.

Same shape as test_sdk_register_machine_id: defaulting lives in
`register_agent_instance` so all five wrapper call sites report the worktree
with no per-wrapper edits (plans/todos/sidebar-worktree-grouping.md). No DB, no
real network, no real git — `get_worktree_name` is covered separately in
test_utils_worktree_name.py.
"""

from __future__ import annotations

from vicoa.sdk.async_client import AsyncVicoaClient
from vicoa.sdk.client import VicoaClient


def _client() -> VicoaClient:
    return VicoaClient(api_key="k", base_url="http://localhost:0")


def _capture_payload(client: VicoaClient, captured: dict) -> None:
    def _fake(method, path, json=None, params=None):
        captured["json"] = json
        return {"agent_instance_id": "inst-1", "status": "active"}

    client._make_request = _fake  # type: ignore[method-assign]


def test_sends_detected_worktree_name(monkeypatch) -> None:
    monkeypatch.setattr("vicoa.sdk.client.get_worktree_name", lambda _p: "brave-otter")
    client = _client()
    captured: dict = {}
    _capture_payload(client, captured)

    client.register_agent_instance(agent_type="claude", project="~/wt/x")

    assert captured["json"]["worktree_name"] == "brave-otter"


def test_probes_the_project_path_not_the_cwd(monkeypatch) -> None:
    """`project` is the session's directory; the daemon's own cwd is unrelated."""
    seen: dict = {}

    def _probe(path):
        seen["path"] = path
        return None

    monkeypatch.setattr("vicoa.sdk.client.get_worktree_name", _probe)
    client = _client()
    _capture_payload(client, {})

    client.register_agent_instance(agent_type="claude", project="~/projects/app")

    assert seen["path"] == "~/projects/app"


def test_omits_worktree_name_for_a_main_checkout(monkeypatch) -> None:
    """Absent key, not null — decision #4: no synthetic "main" bucket."""
    monkeypatch.setattr("vicoa.sdk.client.get_worktree_name", lambda _p: None)
    client = _client()
    captured: dict = {}
    _capture_payload(client, captured)

    client.register_agent_instance(agent_type="claude", project="~/projects/app")

    assert "worktree_name" not in captured["json"]


def test_explicit_worktree_name_skips_the_git_probe(monkeypatch) -> None:
    def _never(_p):
        raise AssertionError("git should not be probed when caller supplies a name")

    monkeypatch.setattr("vicoa.sdk.client.get_worktree_name", _never)
    client = _client()
    captured: dict = {}
    _capture_payload(client, captured)

    client.register_agent_instance(agent_type="claude", worktree_name="explicit")

    assert captured["json"]["worktree_name"] == "explicit"


# --- async client: same behavior (used by headless codex/acp) ---


def _async_client() -> AsyncVicoaClient:
    return AsyncVicoaClient(api_key="k", base_url="http://localhost:0")


async def test_async_client_sends_detected_worktree_name(monkeypatch) -> None:
    monkeypatch.setattr(
        "vicoa.sdk.async_client.get_worktree_name", lambda _p: "calm-river"
    )
    client = _async_client()
    captured: dict = {}

    async def _fake(method, path, json=None, params=None):
        captured["json"] = json
        return {"agent_instance_id": "inst-1", "status": "active"}

    client._make_request = _fake  # type: ignore[method-assign]

    await client.register_agent_instance(agent_type="codex", project="~/wt/y")

    assert captured["json"]["worktree_name"] == "calm-river"
