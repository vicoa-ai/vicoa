"""The SDK stamps the session's git identity (repo root + origin remote).

Same shape as test_sdk_register_worktree_name: defaulting lives in
`register_agent_instance` so every wrapper reports it with no per-wrapper edits.
The server uses these to attach a session to its formal project — a linked
worktree, whose cwd sits outside the repo, is matched by repo_root/remote. No
DB, no real network, no real git — `get_git_identity` is covered separately in
test_utils_worktree_name.py's git probes.
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


def test_sends_probed_repo_root_and_remote(monkeypatch) -> None:
    monkeypatch.setattr(
        "vicoa.sdk.client.get_git_identity",
        lambda _p: ("/home/nick/alpha", "git@github.com:vicoa-ai/vicoa.git"),
    )
    client = _client()
    captured: dict = {}
    _capture_payload(client, captured)

    client.register_agent_instance(agent_type="claude", project="~/wt/x")

    assert captured["json"]["repo_root"] == "/home/nick/alpha"
    assert captured["json"]["git_remote_url"] == "git@github.com:vicoa-ai/vicoa.git"


def test_probes_the_project_path(monkeypatch) -> None:
    seen: dict = {}

    def _probe(path):
        seen["path"] = path
        return (None, None)

    monkeypatch.setattr("vicoa.sdk.client.get_git_identity", _probe)
    client = _client()
    _capture_payload(client, {})

    client.register_agent_instance(agent_type="claude", project="~/projects/app")

    assert seen["path"] == "~/projects/app"


def test_omits_keys_for_a_non_git_dir(monkeypatch) -> None:
    """Absent keys, not null — nothing to attribute to."""
    monkeypatch.setattr("vicoa.sdk.client.get_git_identity", lambda _p: (None, None))
    client = _client()
    captured: dict = {}
    _capture_payload(client, captured)

    client.register_agent_instance(agent_type="claude", project="~/projects/app")

    assert "repo_root" not in captured["json"]
    assert "git_remote_url" not in captured["json"]


def test_explicit_values_skip_the_git_probe(monkeypatch) -> None:
    def _never(_p):
        raise AssertionError("git should not be probed when caller supplies both")

    monkeypatch.setattr("vicoa.sdk.client.get_git_identity", _never)
    client = _client()
    captured: dict = {}
    _capture_payload(client, captured)

    client.register_agent_instance(
        agent_type="claude",
        repo_root="/explicit/root",
        git_remote_url="https://example.com/r.git",
    )

    assert captured["json"]["repo_root"] == "/explicit/root"
    assert captured["json"]["git_remote_url"] == "https://example.com/r.git"


# --- async client: same behavior (used by headless codex/acp) ---


def _async_client() -> AsyncVicoaClient:
    return AsyncVicoaClient(api_key="k", base_url="http://localhost:0")


async def test_async_client_sends_probed_git_identity(monkeypatch) -> None:
    monkeypatch.setattr(
        "vicoa.sdk.async_client.get_git_identity",
        lambda _p: ("/home/nick/beta", None),
    )
    client = _async_client()
    captured: dict = {}

    async def _fake(method, path, json=None, params=None):
        captured["json"] = json
        return {"agent_instance_id": "inst-1", "status": "active"}

    client._make_request = _fake  # type: ignore[method-assign]

    await client.register_agent_instance(agent_type="codex", project="~/wt/y")

    assert captured["json"]["repo_root"] == "/home/nick/beta"
    assert "git_remote_url" not in captured["json"]  # remote absent → key omitted
