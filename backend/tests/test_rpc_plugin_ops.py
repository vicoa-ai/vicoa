"""Tests for the plugin RPC handlers (install / catalog / enable / trust / remove)."""

import json
from pathlib import Path

import pytest

from vicoa.rpc import plugin_ops


@pytest.fixture()
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    return fake_home


def _make_plugin_dir(tmp_path: Path, plugin_id: str, **manifest_over) -> Path:
    src = tmp_path / f"src-{plugin_id}"
    src.mkdir()
    manifest = {
        "id": plugin_id,
        "apiVersion": 1,
        "name": plugin_id.title(),
        "themes": [
            {
                "id": "t",
                "label": "T",
                "base": "dark",
                "tokens": {"primary": "267 84% 81%"},
            }
        ],
    }
    manifest.update(manifest_over)
    (src / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    return src


def test_install_from_directory(home: Path, tmp_path: Path):
    src = _make_plugin_dir(tmp_path, "demo")
    result = plugin_ops.install_plugin(source=str(src))
    assert result.get("id") == "demo"
    dest = home / ".vicoa" / "plugins" / "demo"
    assert (dest / "plugin.json").is_file()
    # Provenance recorded.
    prov = json.loads((home / ".vicoa" / "plugins" / ".vicoa-plugins.json").read_text())
    assert prov["demo"]["source"] == str(src)


def test_install_rejects_invalid_manifest(home: Path, tmp_path: Path):
    src = tmp_path / "bad"
    src.mkdir()
    (src / "plugin.json").write_text(
        json.dumps({"apiVersion": 1}), encoding="utf-8"
    )  # no id
    result = plugin_ops.install_plugin(source=str(src))
    assert result.get("error") == "invalid_manifest"


def test_install_missing_manifest(home: Path, tmp_path: Path):
    src = tmp_path / "empty"
    src.mkdir()
    result = plugin_ops.install_plugin(source=str(src))
    assert result.get("error") == "manifest_not_found"


def test_install_exists_without_overwrite(home: Path, tmp_path: Path):
    src = _make_plugin_dir(tmp_path, "demo")
    assert plugin_ops.install_plugin(source=str(src)).get("id") == "demo"
    again = plugin_ops.install_plugin(source=str(src))
    assert again.get("error") == "plugin_exists"
    assert (
        plugin_ops.install_plugin(source=str(src), overwrite=True).get("id") == "demo"
    )


def test_catalog_enable_and_trust_flow(home: Path, tmp_path: Path):
    src = _make_plugin_dir(tmp_path, "demo")
    plugin_ops.install_plugin(source=str(src))

    cat = plugin_ops.plugin_catalog()
    assert "etag" in cat
    entry = next(p for p in cat["plugins"] if p["id"] == "demo")
    assert entry["enabled"] is True
    assert entry["trusted"] is False
    assert entry["server_available"] is False

    # ETag conditional GET.
    assert plugin_ops.plugin_catalog(etag=cat["etag"]).get("not_modified") is True

    # Grant trust -> reflected, and ETag changes.
    assert plugin_ops.grant_plugin_trust("demo") == {"ok": True}
    cat2 = plugin_ops.plugin_catalog()
    assert next(p for p in cat2["plugins"] if p["id"] == "demo")["trusted"] is True
    assert cat2["etag"] != cat["etag"]

    # Editing the manifest re-arms trust (hash changes).
    dest = home / ".vicoa" / "plugins" / "demo"
    manifest = json.loads((dest / "plugin.json").read_text())
    manifest["name"] = "Renamed"
    (dest / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert plugin_ops.is_plugin_trusted("demo", dest) is False


def test_disable_and_global_switch(home: Path, tmp_path: Path):
    plugin_ops.install_plugin(source=str(_make_plugin_dir(tmp_path, "demo")))

    assert plugin_ops.set_plugin_enabled("demo", False)["enabled"] is False
    assert (
        next(p for p in plugin_ops.plugin_catalog()["plugins"] if p["id"] == "demo")[
            "enabled"
        ]
        is False
    )

    assert plugin_ops.set_plugins_enabled(False)["plugins_enabled"] is False
    assert plugin_ops.plugin_catalog()["plugins_enabled"] is False


def test_remove_clears_state(home: Path, tmp_path: Path):
    plugin_ops.install_plugin(source=str(_make_plugin_dir(tmp_path, "demo")))
    plugin_ops.grant_plugin_trust("demo")
    plugin_ops.set_plugin_enabled("demo", False)

    assert plugin_ops.remove_plugin("demo") == {"ok": True}
    assert not (home / ".vicoa" / "plugins" / "demo").exists()
    assert plugin_ops.plugin_catalog()["plugins"] == []
    # Trust + provenance forgotten.
    assert (
        plugin_ops.is_plugin_trusted("demo", home / ".vicoa" / "plugins" / "demo")
        is False
    )
    prov = json.loads((home / ".vicoa" / "plugins" / ".vicoa-plugins.json").read_text())
    assert "demo" not in prov


def test_remove_invalid_id(home: Path):
    assert plugin_ops.remove_plugin("../etc")["error"] == "invalid_plugin_id"
    assert plugin_ops.remove_plugin("ghost")["error"] == "not_found"


def test_malformed_plugin_visible_in_list_not_catalog(home: Path, tmp_path: Path):
    # Install a good one, then drop a broken plugin dir alongside it.
    plugin_ops.install_plugin(source=str(_make_plugin_dir(tmp_path, "good")))
    broken = home / ".vicoa" / "plugins" / "broken"
    broken.mkdir(parents=True)
    (broken / "plugin.json").write_text("{ not json", encoding="utf-8")

    listing = plugin_ops.plugin_list()
    ids = {p["id"]: p for p in listing["plugins"]}
    assert ids["broken"]["valid"] is False
    assert ids["broken"]["errors"]

    catalog_ids = {p["id"] for p in plugin_ops.plugin_catalog()["plugins"]}
    assert catalog_ids == {"good"}
