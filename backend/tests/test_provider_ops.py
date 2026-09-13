"""Settings → Providers / `vicoa provider`: add, remove, list and — the part
track A could not do — *probe* a provider by running the real handshake
against a fake ACP agent.

The fake agent is a tiny NDJSON JSON-RPC server written to tmp_path; its
behaviour is picked with FAKE_ACP_MODE so one script covers the happy path,
auth-required, and "not actually an ACP server". No external CLI is needed,
so this runs everywhere the unit suite does.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from integrations.headless import generic_acp
from vicoa.rpc import provider_ops

FAKE_AGENT = textwrap.dedent(
    """
    import json, os, sys
    mode = os.environ.get("FAKE_ACP_MODE", "ok")
    if mode == "garbage":
        sys.stderr.write("error: unknown command 'acp'\\n")
        sys.stderr.flush()
        sys.exit(2)
    authed = mode != "auth"
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if method == "initialize":
            if mode == "hang":
                import time; time.sleep(30)
            result = {
                "protocolVersion": params.get("protocolVersion"),
                "agentCapabilities": {"loadSession": False},
                "authMethods": [{"id": "oauth", "name": "Log in"}],
                "agentInfo": {"name": "fake-agent", "version": "0.1.0"},
            }
            print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}), flush=True)
        elif method == "authenticate":
            authed = True
            print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": {}}), flush=True)
        elif method == "session/new":
            if not authed:
                err = {"code": -32000, "message": "Authentication required"}
                print(json.dumps({"jsonrpc": "2.0", "id": mid, "error": err}), flush=True)
                continue
            assert isinstance(params.get("mcpServers"), list)
            result = {
                "sessionId": "sess-1",
                "modes": {
                    "currentModeId": "build",
                    "availableModes": [
                        {"id": "build", "name": "Build"},
                        {"id": "plan", "name": "Plan"},
                    ],
                },
                "models": {
                    "currentModelId": "fast",
                    "availableModels": [
                        {"modelId": "fast", "name": "Fast"},
                        {"modelId": "smart", "name": "Smart"},
                    ],
                },
            }
            print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}), flush=True)
        else:
            err = {"code": -32601, "message": "Method not found"}
            print(json.dumps({"jsonrpc": "2.0", "id": mid, "error": err}), flush=True)
    """
)


@pytest.fixture
def config_path(isolate_user_config: Path) -> Path:
    """The scratch ~/.vicoa/config.json; the rootdir conftest does the patching."""
    return isolate_user_config


@pytest.fixture
def fake_agent(tmp_path: Path) -> list[str]:
    script = tmp_path / "fake_acp_agent.py"
    script.write_text(FAKE_AGENT)
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return [sys.executable, str(script)]


def _read(config_path: Path) -> dict:
    return json.loads(config_path.read_text())


# ----------------------------------------------------------------------------
# add / remove / list
# ----------------------------------------------------------------------------


def test_add_from_catalog_entry_writes_the_documented_shape(config_path: Path):
    entry = {
        "id": "goose",
        "label": "goose",
        "description": "Block's agent",
        "command": ["goose", "acp"],
        "install_url": "https://block.github.io/goose/",
        "version": "1.33.1",
    }
    row = provider_ops.provider_add(entry)
    assert "error" not in row
    assert row["id"] == "goose" and row["source"] == "config"

    written = _read(config_path)["agents"]["providers"]["goose"]
    assert written["extends"] == "acp"
    assert written["label"] == "goose"
    assert written["command"] == ["goose", "acp"]
    assert written["description"] == "Block's agent"
    # UI-only fields do not leak into the file; install_url becomes the hint.
    assert "install_url" not in written and "version" not in written
    assert "https://block.github.io/goose/" in written["install_hint"]
    # Spawnable immediately, no daemon restart: the cache is mtime-keyed.
    assert "goose" in generic_acp.effective_acp_agents()


def test_add_keeps_sibling_agents_keys(config_path: Path):
    config_path.write_text(
        json.dumps({"agents": {"other": 1, "providers": {}}, "x": 2})
    )
    provider_ops.provider_add({"id": "amp-acp", "label": "Amp", "command": ["amp-acp"]})
    data = _read(config_path)
    assert data["agents"]["other"] == 1 and data["x"] == 2
    assert "amp-acp" in data["agents"]["providers"]


def test_add_rejects_duplicate_bad_id_and_builtin(config_path: Path):
    ok = provider_ops.provider_add(
        {"id": "goose", "label": "goose", "command": ["goose", "acp"]}
    )
    assert "error" not in ok
    dup = provider_ops.provider_add(
        {"id": "goose", "label": "goose", "command": ["goose", "acp"]}
    )
    assert "already" in dup["error"]
    bad = provider_ops.provider_add({"id": "Goose!", "label": "x", "command": ["x"]})
    assert "must match" in bad["error"]
    builtin = provider_ops.provider_add(
        {"id": "cursor", "label": "x", "command": ["x"]}
    )
    assert "built-in" in builtin["error"]
    missing_cmd = provider_ops.provider_add({"id": "nocmd", "label": "No"})
    assert "command" in missing_cmd["error"]


def test_add_overwrite_replaces(config_path: Path):
    provider_ops.provider_add(
        {"id": "goose", "label": "goose", "command": ["goose", "acp"]}
    )
    row = provider_ops.provider_add(
        {"id": "goose", "label": "Goose v2", "command": ["goose2", "acp"]},
        overwrite=True,
    )
    assert row["label"] == "Goose v2"
    assert _read(config_path)["agents"]["providers"]["goose"]["command"] == [
        "goose2",
        "acp",
    ]


def test_remove_and_enable(config_path: Path):
    provider_ops.provider_add(
        {"id": "goose", "label": "goose", "command": ["goose", "acp"]}
    )
    assert provider_ops.provider_set_enabled("goose", False) == {
        "id": "goose",
        "enabled": False,
    }
    assert "goose" not in generic_acp.effective_acp_agents()
    rows = {r["id"]: r for r in provider_ops.provider_list()["providers"]}
    assert rows["goose"]["enabled"] is False and rows["goose"]["label"] == "goose"

    assert provider_ops.provider_set_enabled("goose", True) == {
        "id": "goose",
        "enabled": True,
    }
    assert "goose" in generic_acp.effective_acp_agents()

    assert provider_ops.provider_remove("goose") == {"id": "goose", "removed": True}
    assert "goose" not in _read(config_path)["agents"]["providers"]
    assert "not in your config" in provider_ops.provider_remove("goose")["error"]
    assert "built in" in provider_ops.provider_remove("cursor")["error"]


def test_disable_builtin_then_reenable_leaves_no_empty_override(config_path: Path):
    provider_ops.provider_set_enabled("cursor", False)
    assert _read(config_path)["agents"]["providers"]["cursor"] == {"enabled": False}
    assert "cursor" not in generic_acp.effective_acp_agents()
    provider_ops.provider_set_enabled("cursor", True)
    assert "cursor" not in _read(config_path)["agents"]["providers"]
    assert "cursor" in generic_acp.effective_acp_agents()


def test_list_marks_source_and_install_state(
    config_path: Path, fake_agent: list[str], monkeypatch
):
    provider_ops.provider_add({"id": "fake", "label": "Fake", "command": fake_agent})
    provider_ops.provider_add(
        {"id": "ghost", "label": "Ghost", "command": ["definitely-not-a-binary-xyz"]}
    )
    rows = {r["id"]: r for r in provider_ops.provider_list()["providers"]}
    assert rows["cursor"]["source"] == "builtin"
    assert rows["fake"]["source"] == "config" and rows["fake"]["installed"] is True
    assert rows["ghost"]["installed"] is False and rows["ghost"]["binary"] is None


# ----------------------------------------------------------------------------
# probe
# ----------------------------------------------------------------------------


def test_probe_unknown_and_missing_binary(config_path: Path):
    assert "unknown provider" in provider_ops.provider_probe("nope")["error"]
    provider_ops.provider_add(
        {
            "id": "ghost",
            "label": "Ghost",
            "command": ["definitely-not-a-binary-xyz", "acp"],
            "install_hint": "brew install ghost",
        }
    )
    result = provider_ops.provider_probe("ghost")
    assert result["ok"] is False and result["stage"] == "binary"
    assert result["installed"] is False
    assert "brew install ghost" in result["error"]


def test_probe_ok_reports_agent_models_and_modes(
    config_path: Path, fake_agent: list[str]
):
    provider_ops.provider_add({"id": "fake", "label": "Fake", "command": fake_agent})
    result = provider_ops.provider_probe("fake", timeout=20)
    assert result["ok"] is True, result
    assert result["stage"] == "ok"
    assert result["installed"] is True
    assert result["agent"] == {"name": "fake-agent", "version": "0.1.0"}
    assert result["protocol_version"] == 1
    assert result["auth_methods"] == ["oauth"]
    assert result["session_id"] == "sess-1"
    assert result["models"] == [
        {"id": "fast", "label": "Fast"},
        {"id": "smart", "label": "Smart"},
    ]
    assert result["modes"] == [
        {"id": "build", "label": "Build"},
        {"id": "plan", "label": "Plan"},
    ]
    assert result["elapsed_ms"] >= 0


def test_probe_authenticates_when_required(config_path: Path, fake_agent: list[str]):
    provider_ops.provider_add(
        {
            "id": "fake",
            "label": "Fake",
            "command": fake_agent,
            "env": {"FAKE_ACP_MODE": "auth"},
        }
    )
    result = provider_ops.provider_probe("fake", timeout=20)
    assert result["ok"] is True, result
    assert result["session_id"] == "sess-1"


def test_probe_not_an_acp_server_stops_at_initialize_with_stderr(
    config_path: Path, fake_agent: list[str]
):
    provider_ops.provider_add(
        {
            "id": "fake",
            "label": "Fake",
            "command": fake_agent,
            "env": {"FAKE_ACP_MODE": "garbage"},
        }
    )
    result = provider_ops.provider_probe("fake", timeout=20)
    assert result["ok"] is False
    assert result["stage"] == "initialize"
    assert "exited with code 2" in result["error"]
    assert "unknown command 'acp'" in result["error"]
    assert result["stderr"] == ["error: unknown command 'acp'"]


def test_probe_times_out_on_a_silent_agent(config_path: Path, fake_agent: list[str]):
    provider_ops.provider_add(
        {
            "id": "fake",
            "label": "Fake",
            "command": fake_agent,
            "env": {"FAKE_ACP_MODE": "hang"},
        }
    )
    result = provider_ops.provider_probe("fake", timeout=2)
    assert result["ok"] is False and result["stage"] == "initialize"
    assert "within 2s" in result["error"]


def test_probe_uses_a_scratch_cwd_and_cleans_it(
    config_path: Path, fake_agent: list[str], tmp_path: Path
):
    provider_ops.provider_add({"id": "fake", "label": "Fake", "command": fake_agent})
    before = {
        p for p in Path(os.environ.get("TMPDIR", "/tmp")).glob("vicoa-provider-probe-*")
    }
    provider_ops.provider_probe("fake", timeout=20)
    after = {
        p for p in Path(os.environ.get("TMPDIR", "/tmp")).glob("vicoa-provider-probe-*")
    }
    assert after <= before
