"""Pure unit tests: the daemon reports which agent CLIs are installed.

Covers plans/machine-management.md D2/D3 — `available_agents` is detected once
at registration (no per-loop `--version` spawns) and ridealong in the register
payload's metadata. No DB, no real network/state-file writes.
"""

from __future__ import annotations

import pytest

from vicoa.machine_daemon import MachineDaemon


@pytest.fixture
def daemon() -> MachineDaemon:
    return MachineDaemon(api_key="test-key", base_url="http://localhost:0")


def test_detect_available_agents_maps_installed_to_true(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """`_check_agent_installation` returns None when installed; that maps to
    True. Anything else (an error string) maps to False."""
    installed = {"claude", "opencode"}
    monkeypatch.setattr(
        daemon,
        "_check_agent_installation",
        lambda agent: None if agent in installed else "not found",
    )
    assert daemon._detect_available_agents() == {
        "claude": True,
        "codex": False,
        "opencode": True,
        "cursor": False,
        "gemini": False,
        "copilot": False,
        "kimi": False,
        "hermes": False,
        "omp": False,
        "pi": False,
    }


def test_register_payload_includes_available_agents(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """The register payload carries available_agents under metadata so the app
    can render installable agents per machine (D2)."""

    class _FakeResp:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "machine_id": "mac-1",
                "display_name": None,
                "hostname": "h",
                "platform": "p",
            }

    captured: dict = {}

    def _fake_post(path: str, payload: dict):
        captured["payload"] = payload
        return _FakeResp()

    # Per-base-url persistence helpers replaced the old _load_state /
    # _save_state pair when daemons became multi-URL.
    monkeypatch.setattr(daemon, "_load_entry", lambda: {})
    monkeypatch.setattr(daemon, "_persist_entry", lambda updates: None)
    monkeypatch.setattr(daemon, "_post", _fake_post)
    monkeypatch.setattr(
        daemon,
        "_check_agent_installation",
        lambda agent: None if agent == "claude" else "not found",
    )

    daemon.register_machine()

    available = captured["payload"]["metadata"]["available_agents"]
    assert available["claude"] is True
    assert all(
        available[agent] is False
        for agent in (
            "codex",
            "opencode",
            "cursor",
            "gemini",
            "copilot",
            "kimi",
            "hermes",
        )
    )


def test_register_payload_advertises_worktree_capability(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """The register payload advertises `worktree` under metadata.capabilities so
    the app can feature-detect — an old daemon omits it and the app hides the
    worktree option rather than silently spawning in the base dir."""

    class _FakeResp:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"machine_id": "mac-1", "display_name": None, "hostname": "h"}

    captured: dict = {}

    def _fake_post(path: str, payload: dict):
        captured["payload"] = payload
        return _FakeResp()

    monkeypatch.setattr(daemon, "_load_entry", lambda: {})
    monkeypatch.setattr(daemon, "_persist_entry", lambda updates: None)
    monkeypatch.setattr(daemon, "_post", _fake_post)
    monkeypatch.setattr(daemon, "_check_agent_installation", lambda agent: None)

    daemon.register_machine()

    assert "worktree" in captured["payload"]["metadata"]["capabilities"]


def test_register_payload_includes_hardware_id(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """The register payload carries the hashed hardware id so the backend can
    dedup a machine on (user_id, hardware_id) — the identity anchor that
    survives re-auth/key rotation."""
    from vicoa import machine_daemon

    class _FakeResp:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"machine_id": "mac-1", "display_name": None, "hostname": "h"}

    captured: dict = {}

    def _fake_post(path: str, payload: dict):
        captured["payload"] = payload
        return _FakeResp()

    monkeypatch.setattr(daemon, "_load_entry", lambda: {})
    monkeypatch.setattr(daemon, "_persist_entry", lambda updates: None)
    monkeypatch.setattr(daemon, "_post", _fake_post)
    monkeypatch.setattr(daemon, "_check_agent_installation", lambda agent: None)
    monkeypatch.setattr(machine_daemon, "hardware_id_hash", lambda: "HWHASH")

    daemon.register_machine()

    assert captured["payload"]["hardware_id"] == "HWHASH"


def test_scan_agents_rpc_returns_fresh_map(daemon: MachineDaemon, monkeypatch) -> None:
    """The RPC re-probes rather than replaying the registration-time answer —
    that is its entire reason to exist (an agent installed after boot)."""
    monkeypatch.setattr(daemon, "push_available_agents", lambda agents: None)
    monkeypatch.setattr(
        daemon,
        "_check_agent_installation",
        lambda agent: None if agent == "opencode" else "not found",
    )

    result = daemon.scan_agents_rpc()

    assert result["available_agents"]["opencode"] is True
    assert result["available_agents"]["claude"] is False


def test_scan_agents_is_advertised(daemon: MachineDaemon) -> None:
    """Local dispatch falls through to the daemon with no allowlist, so a
    method missing from `_supported_rpc_methods` still works locally while
    silently failing `no_handler` on the cloud path. Pin both."""
    assert "scan-agents" in daemon._supported_rpc_methods()
    assert "error" not in daemon._handle_rpc_request({"method": "scan-agents"})


def test_agent_scan_capability_is_advertised(daemon: MachineDaemon) -> None:
    """The app hides the Rescan button unless the daemon says it can serve it;
    an old daemon omits the flag and the button never appears."""
    assert "agent-scan" in daemon._capabilities()


def test_scan_push_omits_cwd(daemon: MachineDaemon, monkeypatch) -> None:
    """Re-register refreshes available_agents in place, but the backend
    prepends any `cwd` it receives to recent_directories — so a scan must not
    send one, or it would pollute the user's directory picker every press."""

    class _FakeResp:
        def raise_for_status(self) -> None:
            pass

    captured: dict = {}

    def _fake_post(path: str, payload: dict):
        captured["path"] = path
        captured["payload"] = payload
        return _FakeResp()

    daemon.machine_id = "mac-1"
    monkeypatch.setattr(daemon, "_post", _fake_post)

    daemon.push_available_agents({"claude": True})

    assert captured["path"] == "/api/v1/machines/register"
    assert captured["payload"]["machine_id"] == "mac-1"
    assert captured["payload"]["metadata"]["available_agents"] == {"claude": True}
    assert "cwd" not in captured["payload"]["metadata"]


def test_scan_push_noop_without_machine_id(daemon: MachineDaemon, monkeypatch) -> None:
    """A local-only daemon has no cloud row to refresh; the RPC's return value
    is still correct, so this must not raise."""

    def _fail(*args, **kwargs):
        raise AssertionError("should not POST without a machine_id")

    monkeypatch.setattr(daemon, "_post", _fail)
    daemon.machine_id = None

    daemon.push_available_agents({"claude": True})


def test_scan_survives_publish_failure(daemon: MachineDaemon, monkeypatch) -> None:
    """Publishing is best-effort: the caller already holds the fresh map, so a
    cloud hiccup must not fail the user's scan."""

    def _boom(*args, **kwargs):
        raise RuntimeError("network down")

    daemon.machine_id = "mac-1"
    monkeypatch.setattr(daemon, "_post", _boom)
    monkeypatch.setattr(
        daemon,
        "_check_agent_installation",
        lambda agent: None if agent == "claude" else "not found",
    )

    result = daemon.scan_agents_rpc()

    assert result["available_agents"]["claude"] is True
