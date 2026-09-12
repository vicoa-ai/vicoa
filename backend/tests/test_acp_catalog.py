"""The one-click ACP catalog: every entry must install cleanly through the
same validator the daemon applies to a hand-edited config, and the served
agent-catalog payload must carry it.
"""

from __future__ import annotations

import json

from integrations.headless.generic_acp import GENERIC_ACP_AGENTS, spec_from_override
from protocol.acp_catalog import (
    ACP_CATALOG,
    catalog_entry,
    install_hint_for,
    provider_config_from_entry,
)
from protocol.agent_catalog import AGENT_CATALOG, AGENT_CATALOG_JSON
from protocol.provider_overrides import PROVIDER_ID_RE, validate_provider

BUILTIN_IDS = frozenset(GENERIC_ACP_AGENTS)


def test_catalog_is_non_trivial_and_ids_are_unique_slugs():
    assert len(ACP_CATALOG) >= 30
    ids = [entry["id"] for entry in ACP_CATALOG]
    assert len(ids) == len(set(ids))
    for provider_id in ids:
        assert PROVIDER_ID_RE.match(provider_id), provider_id


def test_catalog_never_shadows_a_builtin_or_first_party_agent():
    first_party = {agent["id"] for agent in AGENT_CATALOG["agents"]}
    for entry in ACP_CATALOG:
        assert entry["id"] not in BUILTIN_IDS, entry["id"]
        assert entry["id"] not in first_party, entry["id"]


def test_every_entry_installs_through_the_daemon_validator():
    for entry in ACP_CATALOG:
        config = provider_config_from_entry(entry)
        clean, errors = validate_provider(entry["id"], config, builtin_ids=BUILTIN_IDS)
        assert clean is not None, (entry["id"], errors)
        assert errors == [], (entry["id"], errors)
        assert clean["extends"] == "acp"
        assert clean["command"] == list(entry["command"])
        assert clean["label"] == entry["label"]
        # And the spec the daemon will spawn from is the catalog's command.
        spec = spec_from_override(entry["id"], clean, GENERIC_ACP_AGENTS)
        assert spec is not None
        assert [spec.binaries[0], *spec.acp_args] == list(entry["command"])
        assert spec.env == dict(entry.get("env") or {})


def test_entry_fields_are_the_documented_set():
    allowed = {"id", "label", "description", "command", "env", "install_url", "version"}
    for entry in ACP_CATALOG:
        assert set(entry) <= allowed, (entry["id"], set(entry) - allowed)
        assert entry["install_url"].startswith("https://"), entry["id"]
        assert entry["description"], entry["id"]
        assert isinstance(entry["command"], list) and entry["command"], entry["id"]


def test_install_hint_names_the_launcher_for_npx_and_uvx():
    npx = next(e for e in ACP_CATALOG if e["command"][0] == "npx")
    uvx = next(e for e in ACP_CATALOG if e["command"][0] == "uvx")
    bare = next(e for e in ACP_CATALOG if e["command"][0] not in ("npx", "uvx"))
    assert "Node.js" in install_hint_for(npx) and npx[
        "install_url"
    ] in install_hint_for(npx)
    assert "uv " in install_hint_for(uvx) and uvx["install_url"] in install_hint_for(
        uvx
    )
    assert bare["label"] in install_hint_for(bare) and bare[
        "install_url"
    ] in install_hint_for(bare)


def test_npx_and_uvx_entries_pin_a_version():
    # A launcher entry is one click precisely because the package downloads on
    # first use; an unpinned one would silently change under the user.
    for entry in ACP_CATALOG:
        launcher = entry["command"][0]
        if launcher == "npx":
            pkg = entry["command"][entry["command"].index("-y") + 1]
            assert "@" in pkg[1:], (entry["id"], pkg)
        elif launcher == "uvx":
            spec = entry["command"][entry["command"].index("--from") + 1]
            assert "==" in spec, (entry["id"], spec)


def test_lookup_and_served_payload():
    assert catalog_entry("cline") is not None
    assert catalog_entry("cursor") is None
    served = json.loads(AGENT_CATALOG_JSON)
    assert served["acp_catalog"] == ACP_CATALOG
    assert {e["id"] for e in served["acp_catalog"]} == {e["id"] for e in ACP_CATALOG}
