"""Tests for the plugin RPC handlers: install / catalog / enable / trust / remove,
and the v2 page-facing handlers (plugin files, declared local files, settings,
reload, logs, link)."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from vicoa.rpc import plugin_ops


@pytest.fixture()
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    monkeypatch.setenv("HOME", str(fake_home))
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


# --------------------------------------------------------------------------- #
# v2 helpers
# --------------------------------------------------------------------------- #
def _page_plugin_dir(
    parent: Path, plugin_id: str = "pager", **manifest_over: Any
) -> Path:
    """A v2 plugin source dir with one page, under ``parent``."""
    src = parent / f"src-{plugin_id}"
    (src / "pages").mkdir(parents=True)
    manifest: dict[str, Any] = {
        "id": plugin_id,
        "apiVersion": 2,
        "name": "Pager",
        "permissions": ["tasks:read"],
        "surfaces": [{"id": "home", "entry": "pages/index.html"}],
    }
    manifest.update(manifest_over)
    (src / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (src / "pages" / "index.html").write_text("<h1>hi</h1>", encoding="utf-8")
    return src


def _install_trusted(parent: Path, plugin_id: str = "pager", **over: Any) -> Path:
    src = _page_plugin_dir(parent, plugin_id, **over)
    assert plugin_ops.install_plugin(source=str(src)).get("id") == plugin_id
    assert plugin_ops.grant_plugin_trust(plugin_id) == {"ok": True}
    return Path.home() / ".vicoa" / "plugins" / plugin_id


def _entry(catalog: dict[str, Any], plugin_id: str) -> dict[str, Any]:
    return next(p for p in catalog["plugins"] if p["id"] == plugin_id)


# --------------------------------------------------------------------------- #
# Catalog / list fields
# --------------------------------------------------------------------------- #
def test_catalog_v2_fields(home: Path, tmp_path: Path):
    _install_trusted(tmp_path)
    cat = plugin_ops.plugin_catalog()
    assert cat["vicoa_version"] == plugin_ops._vicoa_version()
    entry = _entry(cat, "pager")
    assert entry["requirements_ok"] is True
    assert entry["requirement_error"] is None
    assert entry["linked"] is False
    assert entry["reload_nonce"] == 0
    assert entry["api_compatible"] is True


def test_catalog_requirements_not_met(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _install_trusted(tmp_path, requirements={"vicoa": ">=1.10.0"})
    monkeypatch.setattr(plugin_ops, "_vicoa_version", lambda: "1.9.11")
    cat = plugin_ops.plugin_catalog()
    assert cat["vicoa_version"] == "1.9.11"
    entry = _entry(cat, "pager")
    assert entry["requirements_ok"] is False
    assert entry["requirement_error"] == (
        "Needs Vicoa >=1.10.0; this machine has 1.9.11"
    )
    listed = next(p for p in plugin_ops.plugin_list()["plugins"] if p["id"] == "pager")
    assert listed["requirements_ok"] is False
    assert listed["requirement_error"] == entry["requirement_error"]

    # The version is in the payload, so a CLI upgrade changes the ETag.
    monkeypatch.setattr(plugin_ops, "_vicoa_version", lambda: "1.10.0")
    cat2 = plugin_ops.plugin_catalog()
    assert _entry(cat2, "pager")["requirements_ok"] is True
    assert cat2["etag"] != cat["etag"]

    # Dev builds report an unparseable version and pass.
    monkeypatch.setattr(plugin_ops, "_vicoa_version", lambda: "unknown")
    assert _entry(plugin_ops.plugin_catalog(), "pager")["requirements_ok"] is True


def test_newer_api_version_not_compatible(home: Path, tmp_path: Path):
    _install_trusted(tmp_path, apiVersion=3)
    assert _entry(plugin_ops.plugin_catalog(), "pager")["api_compatible"] is False


def test_list_summarizes_surfaces_and_permissions(home: Path, tmp_path: Path):
    _install_trusted(tmp_path, permissions=["tasks:read", "projects:read"])
    listed = next(p for p in plugin_ops.plugin_list()["plugins"] if p["id"] == "pager")
    assert listed["contributes"]["surfaces"] == 1
    assert listed["contributes"]["permissions"] == 2
    assert listed["linked"] is False
    assert listed["link_target"] is None


def test_scan_skips_settings_and_logs_dirs(home: Path, tmp_path: Path):
    _install_trusted(tmp_path, settings={"label": {"type": "string", "default": "x"}})
    plugin_ops.plugin_settings_set("pager", {"label": "y"})
    plugin_ops.plugin_log("pager", [{"level": "info", "message": "hi"}])
    root = home / ".vicoa" / "plugins"
    assert (root / ".settings").is_dir() and (root / ".logs").is_dir()
    assert [p["dir"] for p in plugin_ops.plugin_list()["plugins"]] == ["pager"]


def test_install_copies_symlinks_as_links(home: Path, tmp_path: Path):
    """A link to a secret must not become a plain copy of the secret."""
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET", encoding="utf-8")
    src = _page_plugin_dir(tmp_path)
    os.symlink(secret, src / "pages" / "leak.txt")
    plugin_ops.install_plugin(source=str(src))
    plugin_ops.grant_plugin_trust("pager")
    installed = home / ".vicoa" / "plugins" / "pager" / "pages" / "leak.txt"
    assert installed.is_symlink()
    assert plugin_ops.plugin_file("pager", "pages/leak.txt") == {
        "error": "invalid_path"
    }


def test_reinstall_onto_itself_refused(home: Path, tmp_path: Path):
    dest = _install_trusted(tmp_path)
    result = plugin_ops.install_plugin(source=str(dest), overwrite=True)
    assert result["error"] == "plugin_exists"
    assert (dest / "plugin.json").is_file()


# --------------------------------------------------------------------------- #
# plugin-file
# --------------------------------------------------------------------------- #
def test_plugin_file_ok(home: Path, tmp_path: Path):
    dest = _install_trusted(tmp_path)
    result = plugin_ops.plugin_file("pager", "pages/index.html")
    assert result["ok"] is True
    assert result["content"] == "<h1>hi</h1>"
    assert result["size"] == len(b"<h1>hi</h1>")
    assert result["sha256"] == hashlib.sha256(b"<h1>hi</h1>").hexdigest()
    assert result["mtime"] == pytest.approx(
        (dest / "pages" / "index.html").stat().st_mtime
    )


@pytest.mark.parametrize(
    "path",
    [
        "../secret.txt",
        "pages/../../secret.txt",
        "pages/../index.html",  # any .. segment, even one that stays inside
        "/etc/passwd",
        "",
        "pages\\index.html",
        "pages/\x00.html",
        ".",
        None,
        42,
    ],
)
def test_plugin_file_invalid_paths(home: Path, tmp_path: Path, path: Any):
    _install_trusted(tmp_path)
    assert plugin_ops.plugin_file("pager", path) == {"error": "invalid_path"}


def test_plugin_file_symlink_escape(home: Path, tmp_path: Path):
    dest = _install_trusted(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET", encoding="utf-8")
    os.symlink(secret, dest / "pages" / "escape.txt")
    os.symlink(tmp_path, dest / "pages" / "outside")
    assert plugin_ops.plugin_file("pager", "pages/escape.txt") == {
        "error": "invalid_path"
    }
    assert plugin_ops.plugin_file("pager", "pages/outside/secret.txt") == {
        "error": "invalid_path"
    }
    # A link that stays inside the plugin is fine.
    os.symlink(dest / "pages" / "index.html", dest / "pages" / "alias.html")
    assert plugin_ops.plugin_file("pager", "pages/alias.html")["ok"] is True


def test_plugin_file_errors(home: Path, tmp_path: Path):
    dest = _install_trusted(tmp_path)
    assert plugin_ops.plugin_file("pager", "pages/missing.html") == {
        "error": "not_found"
    }
    assert plugin_ops.plugin_file("pager", "pages") == {"error": "not_a_file"}
    (dest / "pages" / "big.html").write_bytes(b"x" * (1024 * 1024 + 1))
    assert plugin_ops.plugin_file("pager", "pages/big.html") == {"error": "too_large"}
    (dest / "pages" / "max.html").write_bytes(b"x" * (1024 * 1024))
    assert plugin_ops.plugin_file("pager", "pages/max.html")["size"] == 1024 * 1024
    (dest / "pages" / "bin.html").write_bytes(b"\xff\xfe\x00")
    assert plugin_ops.plugin_file("pager", "pages/bin.html") == {"error": "not_utf8"}
    if hasattr(os, "mkfifo"):
        os.mkfifo(dest / "pages" / "fifo.html")
        assert plugin_ops.plugin_file("pager", "pages/fifo.html") == {
            "error": "not_a_file"
        }


def test_plugin_file_requires_usable(home: Path, tmp_path: Path):
    src = _page_plugin_dir(tmp_path)
    plugin_ops.install_plugin(source=str(src))
    # Installed but never trusted.
    assert plugin_ops.plugin_file("pager", "pages/index.html")["error"] == (
        "not_trusted"
    )
    plugin_ops.grant_plugin_trust("pager")
    assert plugin_ops.plugin_file("pager", "pages/index.html")["ok"] is True

    plugin_ops.set_plugin_enabled("pager", False)
    assert plugin_ops.plugin_file("pager", "pages/index.html")["error"] == (
        "not_trusted"
    )
    plugin_ops.set_plugin_enabled("pager", True)

    plugin_ops.set_plugins_enabled(False)
    assert plugin_ops.plugin_file("pager", "pages/index.html")["error"] == (
        "not_trusted"
    )
    plugin_ops.set_plugins_enabled(True)

    # Editing the manifest re-arms trust.
    manifest_path = home / ".vicoa" / "plugins" / "pager" / "plugin.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["name"] = "Changed"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert plugin_ops.plugin_file("pager", "pages/index.html")["error"] == (
        "not_trusted"
    )

    assert plugin_ops.plugin_file("ghost", "pages/index.html") == {"error": "not_found"}
    assert plugin_ops.plugin_file("../x", "a.html") == {"error": "invalid_plugin_id"}


def test_plugin_file_invalid_manifest_not_trusted(home: Path, tmp_path: Path):
    _install_trusted(tmp_path)
    manifest_path = home / ".vicoa" / "plugins" / "pager" / "plugin.json"
    manifest_path.write_text("{ broken", encoding="utf-8")
    plugin_ops.grant_plugin_trust("pager")  # trusting the broken bytes
    assert plugin_ops.plugin_file("pager", "pages/index.html")["error"] == (
        "not_trusted"
    )


# --------------------------------------------------------------------------- #
# plugin-data-read
# --------------------------------------------------------------------------- #
def _data_plugin(tmp_path: Path, home: Path) -> Path:
    project = home / "projects" / "a" / ".vicoa"
    project.mkdir(parents=True)
    (project / "dashboard.local.json").write_text('{"n": 1}', encoding="utf-8")
    (project / "other.json").write_text("{}", encoding="utf-8")
    return _install_trusted(
        tmp_path, files=["~/**/.vicoa/dashboard.local.json", "/nowhere/*.json"]
    )


def test_data_read_allowed(home: Path, tmp_path: Path):
    _data_plugin(tmp_path, home)
    for path in (
        "~/projects/a/.vicoa/dashboard.local.json",
        str(home / "projects" / "a" / ".vicoa" / "dashboard.local.json"),
        "~/projects/./a/.vicoa//dashboard.local.json",  # normalized first
    ):
        result = plugin_ops.plugin_data_read("pager", path)
        assert result["ok"] is True, path
        assert result["content"] == '{"n": 1}'
        assert result["sha256"] == hashlib.sha256(b'{"n": 1}').hexdigest()


def test_data_read_not_matching(home: Path, tmp_path: Path):
    _data_plugin(tmp_path, home)
    assert plugin_ops.plugin_data_read("pager", "~/projects/a/.vicoa/other.json") == {
        "error": "not_allowed"
    }
    # Not revealed whether a file outside the globs exists.
    assert plugin_ops.plugin_data_read("pager", "~/nope/x.json") == {
        "error": "not_allowed"
    }
    # Inside the globs but missing.
    assert plugin_ops.plugin_data_read(
        "pager", "~/projects/b/.vicoa/dashboard.local.json"
    ) == {"error": "not_found"}


@pytest.mark.parametrize(
    "path",
    [
        "projects/a/.vicoa/dashboard.local.json",
        "~projects/a",
        "~",
        "~/projects/../projects/a/.vicoa/dashboard.local.json",
        "~/x/..\\..\\etc",
        "/etc/../etc/passwd",
        "/etc/\x00",
        None,
    ],
)
def test_data_read_invalid_path(home: Path, tmp_path: Path, path: Any):
    _data_plugin(tmp_path, home)
    assert plugin_ops.plugin_data_read("pager", path) == {"error": "invalid_path"}


def test_data_read_symlink_out_of_allowed_tree(home: Path, tmp_path: Path):
    _data_plugin(tmp_path, home)
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET", encoding="utf-8")
    sneaky = home / "projects" / "b" / ".vicoa"
    sneaky.mkdir(parents=True)
    os.symlink(secret, sneaky / "dashboard.local.json")
    assert plugin_ops.plugin_data_read(
        "pager", "~/projects/b/.vicoa/dashboard.local.json"
    ) == {"error": "not_allowed"}

    # A linked directory along the way that lands inside the globs is fine.
    os.symlink(home / "projects" / "a", home / "projects" / "c")
    result = plugin_ops.plugin_data_read(
        "pager", "~/projects/c/.vicoa/dashboard.local.json"
    )
    assert result["ok"] is True


def test_data_read_without_files_declared(home: Path, tmp_path: Path):
    _install_trusted(tmp_path)
    target = home / "x.json"
    target.write_text("{}", encoding="utf-8")
    assert plugin_ops.plugin_data_read("pager", "~/x.json") == {"error": "not_allowed"}


def test_data_read_requires_trust(home: Path, tmp_path: Path):
    src = _page_plugin_dir(tmp_path, files=["~/*.json"])
    plugin_ops.install_plugin(source=str(src))
    (home / "x.json").write_text("{}", encoding="utf-8")
    assert plugin_ops.plugin_data_read("pager", "~/x.json")["error"] == "not_trusted"
    plugin_ops.grant_plugin_trust("pager")
    assert plugin_ops.plugin_data_read("pager", "~/x.json")["ok"] is True


def test_data_read_size_and_type_checks(home: Path, tmp_path: Path):
    _install_trusted(tmp_path, files=["~/data/**"])
    data = home / "data"
    (data / "dir").mkdir(parents=True)
    (data / "big.txt").write_bytes(b"x" * (1024 * 1024 + 1))
    (data / "bin.txt").write_bytes(b"\xff")
    assert plugin_ops.plugin_data_read("pager", "~/data/big.txt") == {
        "error": "too_large"
    }
    assert plugin_ops.plugin_data_read("pager", "~/data/bin.txt") == {
        "error": "not_utf8"
    }
    assert plugin_ops.plugin_data_read("pager", "~/data/dir") == {"error": "not_a_file"}


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
_SETTINGS = {
    "needsLabel": {"type": "string", "default": "needs-human", "title": "Label"},
    "limit": {"type": "number", "default": 5},
    "mode": {"type": "string", "enum": ["compact", "full"]},
    "lanes": {"type": "object"},
    "collapsed": {"type": "array", "items": "string", "scope": "device"},
}


def test_settings_get_defaults(home: Path, tmp_path: Path):
    src = _page_plugin_dir(tmp_path, settings=_SETTINGS)
    plugin_ops.install_plugin(source=str(src))  # trust not required to read
    result = plugin_ops.plugin_settings_get("pager")
    assert result["ok"] is True
    assert set(result["schema"]) == set(_SETTINGS)
    assert result["schema"]["collapsed"]["scope"] == "device"
    # Machine-scope keys only.
    assert result["values"] == {
        "needsLabel": "needs-human",
        "limit": 5,
        "mode": "compact",
        "lanes": {},
    }


def test_settings_get_without_schema(home: Path, tmp_path: Path):
    _install_trusted(tmp_path)
    assert plugin_ops.plugin_settings_get("pager") == {
        "ok": True,
        "schema": {},
        "values": {},
    }


def test_settings_get_errors(home: Path, tmp_path: Path):
    assert plugin_ops.plugin_settings_get("ghost") == {"error": "not_found"}
    broken = home / ".vicoa" / "plugins" / "broken"
    broken.mkdir(parents=True)
    (broken / "plugin.json").write_text("nope", encoding="utf-8")
    assert plugin_ops.plugin_settings_get("broken") == {"error": "invalid_manifest"}


def test_settings_set_and_get(home: Path, tmp_path: Path):
    _install_trusted(tmp_path, settings=_SETTINGS)
    result = plugin_ops.plugin_settings_set(
        "pager", {"needsLabel": "blocked", "lanes": {"build": ["a"]}}
    )
    assert result == {
        "ok": True,
        "values": {
            "needsLabel": "blocked",
            "limit": 5,
            "mode": "compact",
            "lanes": {"build": ["a"]},
        },
    }
    # Merged, not replaced.
    plugin_ops.plugin_settings_set("pager", {"limit": 2.5, "mode": "full"})
    values = plugin_ops.plugin_settings_get("pager")["values"]
    assert values == {
        "needsLabel": "blocked",
        "limit": 2.5,
        "mode": "full",
        "lanes": {"build": ["a"]},
    }
    stored = json.loads(
        (home / ".vicoa" / "plugins" / ".settings" / "pager.json").read_text()
    )
    assert stored == values


@pytest.mark.parametrize(
    "values, key",
    [
        ({"limit": "five"}, "limit"),
        ({"limit": True}, "limit"),
        ({"mode": "huge"}, "mode"),
        ({"needsLabel": None}, "needsLabel"),
        ({"unknown": 1}, "unknown"),
        ({"collapsed": ["x"]}, "collapsed"),  # device scope: the app keeps it
        ({"needsLabel": "fine", "limit": "bad"}, "limit"),
    ],
)
def test_settings_set_invalid_writes_nothing(
    home: Path, tmp_path: Path, values: dict[str, Any], key: str
):
    _install_trusted(tmp_path, settings=_SETTINGS)
    result = plugin_ops.plugin_settings_set("pager", values)
    assert result["error"] == "invalid_setting"
    assert result["key"] == key
    assert not (home / ".vicoa" / "plugins" / ".settings" / "pager.json").exists()
    assert plugin_ops.plugin_settings_get("pager")["values"]["needsLabel"] == (
        "needs-human"
    )


def test_settings_set_requires_trust(home: Path, tmp_path: Path):
    src = _page_plugin_dir(tmp_path, settings=_SETTINGS)
    plugin_ops.install_plugin(source=str(src))
    result = plugin_ops.plugin_settings_set("pager", {"limit": 1})
    assert result["error"] == "not_trusted"


def test_settings_set_not_an_object(home: Path, tmp_path: Path):
    _install_trusted(tmp_path, settings=_SETTINGS)
    assert plugin_ops.plugin_settings_set("pager", ["limit"])["error"] == (  # type: ignore[arg-type]
        "invalid_setting"
    )


def test_settings_total_size_capped(home: Path, tmp_path: Path):
    _install_trusted(tmp_path, settings=_SETTINGS)
    result = plugin_ops.plugin_settings_set("pager", {"lanes": {"x": "y" * 70_000}})
    assert result["error"] == "too_large"
    assert not (home / ".vicoa" / "plugins" / ".settings" / "pager.json").exists()


def test_settings_invalid_stored_values_dropped(home: Path, tmp_path: Path):
    _install_trusted(tmp_path, settings=_SETTINGS)
    stored = home / ".vicoa" / "plugins" / ".settings" / "pager.json"
    stored.parent.mkdir(parents=True)
    stored.write_text(
        json.dumps(
            {
                "needsLabel": 7,  # wrong type now
                "mode": "full",
                "gone": "removed from the schema",
                "collapsed": ["device keys never live here"],
            }
        ),
        encoding="utf-8",
    )
    values = plugin_ops.plugin_settings_get("pager")["values"]
    assert values == {
        "needsLabel": "needs-human",
        "limit": 5,
        "mode": "full",
        "lanes": {},
    }
    # The next write keeps only what is still valid.
    plugin_ops.plugin_settings_set("pager", {"limit": 1})
    assert json.loads(stored.read_text()) == {"mode": "full", "limit": 1}


def test_settings_corrupt_file_ignored(home: Path, tmp_path: Path):
    _install_trusted(tmp_path, settings=_SETTINGS)
    stored = home / ".vicoa" / "plugins" / ".settings" / "pager.json"
    stored.parent.mkdir(parents=True)
    stored.write_text("{ not json", encoding="utf-8")
    assert plugin_ops.plugin_settings_get("pager")["values"]["limit"] == 5


# --------------------------------------------------------------------------- #
# Reload
# --------------------------------------------------------------------------- #
def test_reload_bumps_nonce_and_etag(home: Path, tmp_path: Path):
    _install_trusted(tmp_path)
    before = plugin_ops.plugin_catalog()
    assert plugin_ops.reload_plugin("pager") == {"ok": True, "reload_nonce": 1}
    after = plugin_ops.plugin_catalog()
    assert _entry(after, "pager")["reload_nonce"] == 1
    assert after["etag"] != before["etag"]
    assert plugin_ops.plugin_catalog(etag=before["etag"]).get("not_modified") is None
    assert plugin_ops.reload_plugin("pager") == {"ok": True, "reload_nonce": 2}
    # Reloading does not touch trust.
    assert _entry(plugin_ops.plugin_catalog(), "pager")["trusted"] is True


def test_reload_unknown_plugin(home: Path):
    assert plugin_ops.reload_plugin("ghost") == {"error": "not_found"}
    assert plugin_ops.reload_plugin("../x") == {"error": "invalid_plugin_id"}


# --------------------------------------------------------------------------- #
# Logs
# --------------------------------------------------------------------------- #
def test_log_append_and_read(home: Path, tmp_path: Path):
    _install_trusted(tmp_path)
    assert plugin_ops.plugin_log(
        "pager",
        [
            {"level": "info", "message": "hello", "at": "2026-11-10T08:00:00Z"},
            {"level": "warn", "message": "two\nlines\r\nhere", "at": 1_762_761_600_000},
            {"level": "error", "message": {"code": 1}},
            {"level": "debug", "message": "\x1b[31mred\x1b[0m"},
            "not an entry",
        ],
    ) == {"ok": True}
    lines = plugin_ops.plugin_logs_read("pager")["lines"]
    assert len(lines) == 4
    assert lines[0] == "2026-11-10T08:00:00.000Z INFO hello"
    assert lines[1] == "2025-11-10T08:00:00.000Z WARN two lines here"
    assert lines[2].endswith(' ERROR {"code": 1}')
    assert lines[3].endswith(" INFO  [31mred [0m")
    ts = lines[2].split(" ", 1)[0]
    assert ts.endswith("Z") and "T" in ts


def test_log_caps(home: Path, tmp_path: Path):
    _install_trusted(tmp_path)
    plugin_ops.plugin_log(
        "pager", [{"level": "info", "message": f"m{i}"} for i in range(60)]
    )
    lines = plugin_ops.plugin_logs_read("pager", limit=2000)["lines"]
    assert len(lines) == 50
    assert lines[-1].endswith(" m49")

    plugin_ops.plugin_log("pager", [{"level": "info", "message": "x" * 5000}])
    last = plugin_ops.plugin_logs_read("pager", limit=1)["lines"]
    assert len(last) == 1
    assert last[0].split(" ", 2)[2] == "x" * 2000


def test_log_trimmed_to_cap(home: Path, tmp_path: Path):
    _install_trusted(tmp_path)
    for batch in range(10):
        plugin_ops.plugin_log(
            "pager",
            [
                {"level": "info", "message": f"b{batch}-{i}-" + "y" * 1000}
                for i in range(50)
            ],
        )
    log = home / ".vicoa" / "plugins" / ".logs" / "pager.log"
    assert log.stat().st_size <= 256 * 1024
    lines = plugin_ops.plugin_logs_read("pager", limit=2000)["lines"]
    # Oldest dropped, newest kept, and every line whole.
    assert lines[-1].split(" ", 2)[2].startswith("b9-49-")
    assert not any(" b0-0-" in line for line in lines)
    assert all(line.split(" ")[1] == "INFO" for line in lines)


def test_logs_read_limits(home: Path, tmp_path: Path):
    _install_trusted(tmp_path)
    assert plugin_ops.plugin_logs_read("pager") == {"ok": True, "lines": []}
    plugin_ops.plugin_log(
        "pager", [{"level": "info", "message": f"m{i}"} for i in range(5)]
    )
    assert len(plugin_ops.plugin_logs_read("pager", limit=3)["lines"]) == 3
    assert plugin_ops.plugin_logs_read("pager", limit=0)["lines"] == []
    assert len(plugin_ops.plugin_logs_read("pager", limit="x")["lines"]) == 5  # type: ignore[arg-type]
    assert plugin_ops.plugin_logs_read("ghost") == {"error": "not_found"}


def test_log_errors(home: Path, tmp_path: Path):
    assert plugin_ops.plugin_log("ghost", [])["error"] == "not_found"
    _install_trusted(tmp_path)
    assert plugin_ops.plugin_log("pager", "nope")["error"] == "invalid_entries"  # type: ignore[arg-type]
    assert plugin_ops.plugin_log("pager", []) == {"ok": True}


# --------------------------------------------------------------------------- #
# Link
# --------------------------------------------------------------------------- #
def test_link_and_read_through_link(home: Path, tmp_path: Path):
    dev = _page_plugin_dir(tmp_path)
    result = plugin_ops.link_plugin(str(dev))
    assert result["ok"] is True
    assert result["id"] == "pager"
    link = home / ".vicoa" / "plugins" / "pager"
    assert link.is_symlink()
    assert os.path.realpath(link) == os.path.realpath(dev)

    prov = json.loads((home / ".vicoa" / "plugins" / ".vicoa-plugins.json").read_text())
    assert prov["pager"]["kind"] == "link"
    assert prov["pager"]["source"] == str(dev)
    assert prov["pager"]["installed_at"]

    entry = _entry(plugin_ops.plugin_catalog(), "pager")
    assert entry["linked"] is True
    listed = plugin_ops.plugin_list()["plugins"][0]
    assert listed["linked"] is True
    assert listed["link_target"] == os.path.realpath(dev)

    # Edits in the dev dir are served straight away (root = link target).
    plugin_ops.grant_plugin_trust("pager")
    (dev / "pages" / "index.html").write_text("<h1>edited</h1>", encoding="utf-8")
    assert plugin_ops.plugin_file("pager", "pages/index.html")["content"] == (
        "<h1>edited</h1>"
    )


def test_link_with_tilde_path(home: Path):
    dev = _page_plugin_dir(home)
    result = plugin_ops.link_plugin(f"~/{dev.name}")
    assert result["ok"] is True
    prov = json.loads((home / ".vicoa" / "plugins" / ".vicoa-plugins.json").read_text())
    assert prov["pager"]["source"] == f"~/{dev.name}"


def test_link_twice(home: Path, tmp_path: Path):
    dev = _page_plugin_dir(tmp_path)
    assert plugin_ops.link_plugin(str(dev))["ok"] is True
    again = plugin_ops.link_plugin(str(dev))
    assert again["ok"] is True
    assert again["already"] is True

    other_parent = tmp_path / "other"
    other_parent.mkdir()
    other = _page_plugin_dir(other_parent)  # same id, different directory
    assert plugin_ops.link_plugin(str(other)) == {"error": "already_installed"}


def test_link_over_installed_copy_refused(home: Path, tmp_path: Path):
    _install_trusted(tmp_path)
    dev_parent = tmp_path / "dev"
    dev_parent.mkdir()
    dev = _page_plugin_dir(dev_parent)
    assert plugin_ops.link_plugin(str(dev)) == {"error": "already_installed"}


def test_link_errors(home: Path, tmp_path: Path):
    assert plugin_ops.link_plugin(str(tmp_path / "missing"))["error"] == (
        "not_a_directory"
    )
    empty = tmp_path / "empty"
    empty.mkdir()
    assert plugin_ops.link_plugin(str(empty))["error"] == "manifest_not_found"
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "plugin.json").write_text('{"apiVersion": 2}', encoding="utf-8")
    assert plugin_ops.link_plugin(str(bad))["error"] == "invalid_manifest"
    assert plugin_ops.link_plugin("")["error"] == "invalid_path"


def test_install_over_link_refused(home: Path, tmp_path: Path):
    dev = _page_plugin_dir(tmp_path)
    plugin_ops.link_plugin(str(dev))
    copy_parent = tmp_path / "copy"
    copy_parent.mkdir()
    copy_src = _page_plugin_dir(copy_parent)
    for overwrite in (False, True):
        result = plugin_ops.install_plugin(source=str(copy_src), overwrite=overwrite)
        assert result["error"] == "plugin_linked"
    assert (home / ".vicoa" / "plugins" / "pager").is_symlink()
    assert (dev / "pages" / "index.html").read_text() == "<h1>hi</h1>"


def test_remove_linked_keeps_target(home: Path, tmp_path: Path):
    dev = _page_plugin_dir(
        tmp_path, settings={"label": {"type": "string", "default": "x"}}
    )
    plugin_ops.link_plugin(str(dev))
    plugin_ops.grant_plugin_trust("pager")
    plugin_ops.plugin_settings_set("pager", {"label": "y"})
    plugin_ops.plugin_log("pager", [{"level": "info", "message": "hi"}])
    plugin_ops.reload_plugin("pager")
    before = sorted(str(p.relative_to(dev)) for p in dev.rglob("*"))

    assert plugin_ops.remove_plugin("pager") == {"ok": True}

    root = home / ".vicoa" / "plugins"
    assert not (root / "pager").exists()
    assert not (root / "pager").is_symlink()
    # The developer's directory and every file in it are untouched.
    assert dev.is_dir()
    assert sorted(str(p.relative_to(dev)) for p in dev.rglob("*")) == before
    assert (dev / "pages" / "index.html").read_text() == "<h1>hi</h1>"
    assert json.loads((dev / "plugin.json").read_text())["id"] == "pager"
    # Provenance, settings, logs, trust, reload counter forgotten.
    assert "pager" not in json.loads((root / ".vicoa-plugins.json").read_text())
    assert not (root / ".settings" / "pager.json").exists()
    assert not (root / ".logs" / "pager.log").exists()
    state = json.loads((home / ".vicoa" / "daemon_state.json").read_text())
    assert "pager" not in state.get("plugin_trust", {})
    assert "pager" not in state.get("plugin_reload_nonce", {})


def test_remove_dangling_link(home: Path, tmp_path: Path):
    dev = _page_plugin_dir(tmp_path)
    plugin_ops.link_plugin(str(dev))
    moved = tmp_path / "moved"
    dev.rename(moved)
    listed = plugin_ops.plugin_list()["plugins"]
    assert listed[0]["valid"] is False
    assert listed[0]["linked"] is True
    assert plugin_ops.plugin_catalog()["plugins"] == []
    assert plugin_ops.remove_plugin("pager") == {"ok": True}
    assert not (home / ".vicoa" / "plugins" / "pager").is_symlink()
    assert (moved / "plugin.json").is_file()


def test_remove_installed_clears_settings_and_logs(home: Path, tmp_path: Path):
    _install_trusted(tmp_path, settings={"label": {"type": "string"}})
    plugin_ops.plugin_settings_set("pager", {"label": "y"})
    plugin_ops.plugin_log("pager", [{"level": "info", "message": "hi"}])
    assert plugin_ops.remove_plugin("pager") == {"ok": True}
    root = home / ".vicoa" / "plugins"
    assert not (root / "pager").exists()
    assert not (root / ".settings" / "pager.json").exists()
    assert not (root / ".logs" / "pager.log").exists()


# --------------------------------------------------------------------------- #
# Daemon dispatch
# --------------------------------------------------------------------------- #
_V2_METHODS = [
    "plugin-file",
    "plugin-data-read",
    "plugin-settings-get",
    "plugin-settings-set",
    "plugin-reload",
    "plugin-log",
    "plugin-logs-read",
    "plugin-link",
]


def test_daemon_routes_and_advertises_v2_methods(home: Path, tmp_path: Path):
    from vicoa.machine_daemon import MachineDaemon

    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    supported = daemon._supported_rpc_methods()
    for method in _V2_METHODS:
        assert method in supported, method

    dev = _page_plugin_dir(tmp_path)

    def call(method: str, **params: Any) -> dict[str, Any]:
        return daemon._handle_rpc_request({"method": method, "params": params})

    assert call("plugin-link", path=str(dev))["id"] == "pager"
    plugin_ops.grant_plugin_trust("pager")
    assert call("plugin-file", plugin_id="pager", path="pages/index.html")["ok"]
    assert call("plugin-data-read", plugin_id="pager", path="~/x")["error"] == (
        "not_allowed"
    )
    assert call("plugin-settings-get", plugin_id="pager")["ok"]
    assert call("plugin-settings-set", plugin_id="pager", values={})["ok"]
    assert call("plugin-reload", plugin_id="pager")["reload_nonce"] == 1
    assert call(
        "plugin-log", plugin_id="pager", entries=[{"level": "info", "message": "m"}]
    ) == {"ok": True}
    assert len(call("plugin-logs-read", plugin_id="pager", limit=5)["lines"]) == 1


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _cli(*argv: str) -> int:
    import argparse

    from vicoa.commands.plugin import add_plugin_subparser, run_plugin_command

    parser = argparse.ArgumentParser()
    add_plugin_subparser(parser.add_subparsers(dest="command"))
    return run_plugin_command(parser.parse_args(["plugin", *argv]))


def test_cli_init_basic_template_validates(home: Path, tmp_path: Path):
    from protocol.plugin_manifest import validate_manifest

    target = tmp_path / "basic"
    assert _cli("init", str(target)) == 0
    clean, errors = validate_manifest(json.loads((target / "plugin.json").read_text()))
    assert errors == []
    assert clean is not None
    assert clean["id"] == "my-plugin"
    assert clean["themes"] and clean["sidebarItems"] and clean["composerActions"]


def test_cli_init_page_template(home: Path, tmp_path: Path):
    from protocol.plugin_manifest import validate_manifest

    target = tmp_path / "hello"
    assert _cli("init", str(target), "--template", "page", "--id", "hello-page") == 0
    clean, errors = validate_manifest(json.loads((target / "plugin.json").read_text()))
    assert errors == []
    assert clean is not None
    assert clean["apiVersion"] == 2
    assert clean["name"] == "Hello Page"
    assert clean["permissions"] == ["tasks:read", "projects:read"]
    assert clean["surfaces"] == [
        {
            "id": "home",
            "kind": "page",
            "title": "Hello Page",
            "entry": "pages/index.html",
            "icon": "layout-dashboard",
        }
    ]
    assert clean["sidebarItems"][0]["action"] == {
        "type": "surface",
        "surfaceId": "home",
    }
    page = (target / "pages" / "index.html").read_text()
    for needle in (
        "vicoa.context.get()",
        "vicoa.tasks.list({ limit: 5 })",
        "vicoa.open.task(task.id)",
        "var(--vicoa-background",
        "Hello Page",
    ):
        assert needle in page, needle
    # Self-contained: nothing loaded from the network.
    assert "http://" not in page and "https://" not in page and " src=" not in page

    # The page serves through the daemon once linked and trusted.
    assert _cli("link", str(target)) == 0
    plugin_ops.grant_plugin_trust("hello-page")
    assert plugin_ops.plugin_file("hello-page", "pages/index.html")["content"] == page


def test_cli_init_rejects_bad_id_and_non_empty_dir(home: Path, tmp_path: Path):
    assert _cli("init", str(tmp_path / "x"), "--id", "Bad Id") == 1
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "file").write_text("x")
    assert _cli("init", str(busy)) == 1


def test_cli_link_ls_reload_logs_remove(
    home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    dev = _page_plugin_dir(tmp_path)
    assert _cli("link", str(dev)) == 0
    assert "Linked 'pager'" in capsys.readouterr().out
    assert _cli("link", str(dev)) == 0
    assert "already linked" in capsys.readouterr().out

    assert _cli("ls") == 0
    out = capsys.readouterr().out
    assert "linked" in out
    assert "surfaces:1" in out and "permissions:1" in out
    assert f"-> {os.path.realpath(dev)}" in out

    assert _cli("reload", "pager") == 0
    assert _entry(plugin_ops.plugin_catalog(), "pager")["reload_nonce"] == 1
    assert _cli("reload", "ghost") == 1

    capsys.readouterr()
    assert _cli("logs", "pager") == 0
    assert "No log entries" in capsys.readouterr().out
    plugin_ops.plugin_log(
        "pager", [{"level": "warn", "message": f"m{i}"} for i in range(3)]
    )
    assert _cli("logs", "pager", "-n", "2") == 0
    printed = capsys.readouterr().out.strip().splitlines()
    assert len(printed) == 2 and printed[-1].endswith("WARN m2")

    assert _cli("remove", "pager") == 0
    assert (dev / "plugin.json").is_file()


# --------------------------------------------------------------------------- #
# Security review fixes
# --------------------------------------------------------------------------- #
def test_trust_is_bound_to_the_manifest_shown(home: Path, tmp_path: Path):
    """A plugin can't widen its manifest while the trust prompt is open."""
    src = _page_plugin_dir(tmp_path, "pager")
    assert plugin_ops.install_plugin(source=str(src)).get("id") == "pager"
    shown = _entry(plugin_ops.plugin_catalog(), "pager")
    assert shown["trusted"] is False
    reviewed = shown["manifest_sha256"]
    assert isinstance(reviewed, str) and len(reviewed) == 64

    # The plugin's agent rewrites plugin.json after the prompt rendered.
    installed = home / ".vicoa" / "plugins" / "pager" / "plugin.json"
    wider = json.loads(installed.read_text())
    wider["permissions"] = ["tasks:read", "tasks:write", "sessions:start"]
    installed.write_text(json.dumps(wider), encoding="utf-8")

    result = plugin_ops.grant_plugin_trust("pager", manifest_sha256=reviewed)
    assert result["error"] == "manifest_changed"
    assert _entry(plugin_ops.plugin_catalog(), "pager")["trusted"] is False

    # Approving what is on disk now works, and the catalog agrees.
    now = _entry(plugin_ops.plugin_catalog(), "pager")["manifest_sha256"]
    assert plugin_ops.grant_plugin_trust("pager", manifest_sha256=now) == {"ok": True}
    entry = _entry(plugin_ops.plugin_catalog(), "pager")
    assert entry["trusted"] is True and entry["manifest_sha256"] == now


def test_data_read_never_reaches_credentials(home: Path, tmp_path: Path):
    """Even a glob that matches ~/.vicoa can't read the user's API key."""
    (home / ".vicoa").mkdir(exist_ok=True)
    (home / ".vicoa" / "credentials.json").write_text('{"api_key": "x"}')
    (home / ".ssh").mkdir()
    (home / ".ssh" / "config.json").write_text("{}")
    (home / "projects" / "a" / ".vicoa").mkdir(parents=True)
    (home / "projects" / "a" / ".vicoa" / "dashboard.local.json").write_text("{}")
    _install_trusted(tmp_path, files=["~/**/*.json"])
    for path in [
        "~/.vicoa/credentials.json",
        "~/.VICOA/credentials.json",
        "~/.ssh/config.json",
    ]:
        assert plugin_ops.plugin_data_read("pager", path) == {"error": "not_allowed"}, (
            path
        )
    ok = plugin_ops.plugin_data_read(
        "pager", "~/projects/a/.vicoa/dashboard.local.json"
    )
    assert ok.get("ok") is True


def test_data_read_refuses_a_link_into_credentials(home: Path, tmp_path: Path):
    (home / ".vicoa").mkdir(exist_ok=True)
    (home / ".vicoa" / "credentials.json").write_text('{"api_key": "x"}')
    (home / "data").mkdir()
    (home / "data" / "notes.json").symlink_to(home / ".vicoa" / "credentials.json")
    _install_trusted(tmp_path, files=["~/data/*.json", "~/**/*.json"])
    assert plugin_ops.plugin_data_read("pager", "~/data/notes.json") == {
        "error": "not_allowed"
    }
