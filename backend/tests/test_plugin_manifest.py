"""Tests for plugin manifest validation + catalog ETag (protocol.plugin_manifest)."""

import pytest

from protocol.plugin_manifest import (
    PERMISSIONS,
    PLUGIN_API_VERSION,
    compute_catalog_etag,
    is_valid_plugin_id,
    parse_version,
    validate_manifest,
    validate_setting_value,
    version_satisfies,
)


def _base(**over):
    m = {"id": "demo", "apiVersion": 1}
    m.update(over)
    return m


def test_minimal_valid_manifest():
    clean, errors = validate_manifest(_base())
    assert clean is not None
    assert clean["id"] == "demo"
    assert clean["apiVersion"] == 1
    assert errors == []


def test_bad_id_rejected():
    clean, errors = validate_manifest(_base(id="Has Spaces"))
    assert clean is None
    assert errors


def test_non_dict_rejected():
    clean, _ = validate_manifest("nope")
    assert clean is None


def test_apiversion_must_be_int():
    clean, _ = validate_manifest({"id": "demo", "apiVersion": "1"})
    assert clean is None
    clean2, _ = validate_manifest({"id": "demo", "apiVersion": True})
    assert clean2 is None


def test_theme_unknown_tokens_dropped_known_kept():
    clean, _ = validate_manifest(
        _base(
            themes=[
                {
                    "id": "t",
                    "label": "T",
                    "base": "dark",
                    "tokens": {"primary": "267 84% 81%", "evil-token": "10px"},
                }
            ]
        )
    )
    assert clean is not None
    tokens = clean["themes"][0]["tokens"]
    assert tokens == {"primary": "267 84% 81%"}


def test_theme_unsafe_value_rejected():
    clean, errors = validate_manifest(
        _base(
            themes=[
                {
                    "id": "t",
                    "label": "T",
                    "base": "dark",
                    "tokens": {"primary": "10px; } body { display:none"},
                }
            ]
        )
    )
    # The only token was unsafe -> theme dropped entirely, and no themes remain.
    assert clean is not None
    assert "themes" not in clean
    assert any("unsafe" in e for e in errors)


def test_theme_url_value_rejected():
    clean, _ = validate_manifest(
        _base(
            themes=[
                {
                    "id": "t",
                    "label": "T",
                    "base": "dark",
                    "tokens": {"background": "url(https://evil)"},
                }
            ]
        )
    )
    assert clean is not None
    assert "themes" not in clean


def test_theme_bad_base_dropped():
    clean, _ = validate_manifest(
        _base(
            themes=[
                {
                    "id": "t",
                    "label": "T",
                    "base": "neon",
                    "tokens": {"primary": "1 2% 3%"},
                }
            ]
        )
    )
    assert "themes" not in (clean or {})


def test_sidebar_actions_validated():
    clean, _ = validate_manifest(
        _base(
            surfaces=[{"id": "home", "entry": "pages/index.html"}],
            sidebarItems=[
                {
                    "id": "a",
                    "label": "A",
                    "action": {"type": "open-url", "url": "https://x.com"},
                },
                {
                    "id": "b",
                    "label": "B",
                    "action": {"type": "open-url", "url": "javascript:evil"},
                },
                {
                    "id": "c",
                    "label": "C",
                    "action": {"type": "surface", "surfaceId": "home"},
                },
                {"id": "d", "label": "D", "action": {"type": "bogus"}},
                {
                    "id": "e",
                    "label": "E",
                    "action": {"type": "open-url", "url": "/dashboard/tasks"},
                },
            ],
        )
    )
    assert clean is not None
    ids = {i["id"] for i in clean["sidebarItems"]}
    # javascript: url and bogus action dropped; https, surface and app path kept.
    assert ids == {"a", "c", "e"}


def test_rpc_sidebar_action_removed():
    """The rpc action could call any daemon method (write-file included)."""
    clean, errors = validate_manifest(
        _base(
            sidebarItems=[
                {
                    "id": "w",
                    "label": "W",
                    "action": {
                        "type": "rpc",
                        "method": "write-file",
                        "params": {"path": "/tmp/x", "content": "y"},
                    },
                },
            ]
        )
    )
    assert clean is not None
    assert "sidebarItems" not in clean
    assert any("'rpc' action is no longer supported" in e for e in errors)


def test_open_url_rejects_protocol_relative_paths():
    """``//host`` is another site, not an app route; it would load in-app."""
    clean, _ = validate_manifest(
        _base(
            sidebarItems=[
                {
                    "id": f"u{n}",
                    "label": "U",
                    "action": {"type": "open-url", "url": url},
                }
                for n, url in enumerate(
                    ["//evil.example", "/\\evil.example", "/ok\\..\\x"]
                )
            ]
        )
    )
    assert clean is not None
    assert "sidebarItems" not in clean


def test_surface_id_must_be_a_slug():
    clean, _ = validate_manifest(
        _base(
            surfaces=[{"id": "home", "entry": "pages/index.html"}],
            sidebarItems=[
                {
                    "id": "a",
                    "label": "A",
                    "action": {"type": "surface", "surfaceId": "../../settings"},
                },
                {
                    "id": "b",
                    "label": "B",
                    "action": {"type": "surface", "surfaceId": "Home Page"},
                },
                {
                    "id": "c",
                    "label": "C",
                    "action": {"type": "surface", "surfaceId": "home"},
                },
            ],
        )
    )
    assert clean is not None
    assert [i["id"] for i in clean["sidebarItems"]] == ["c"]


def test_icon_whitelist_enforced():
    clean, _ = validate_manifest(
        _base(
            sidebarItems=[
                {
                    "id": "a",
                    "label": "A",
                    "icon": "not-a-real-icon",
                    "action": {"type": "open-url", "url": "/dashboard"},
                },
                {
                    "id": "b",
                    "label": "B",
                    "icon": "book-open",
                    "action": {"type": "open-url", "url": "/dashboard"},
                },
            ]
        )
    )
    assert clean is not None
    by_id = {i["id"]: i for i in clean["sidebarItems"]}
    assert "icon" not in by_id["a"]  # unknown icon dropped
    assert by_id["b"]["icon"] == "book-open"


def test_dashboard_icons_allowed():
    names = ["layout-dashboard", "bar-chart", "activity", "gauge", "kanban"]
    clean, _ = validate_manifest(
        _base(
            sidebarItems=[
                {
                    "id": name,
                    "label": name,
                    "icon": name,
                    "action": {"type": "open-url", "url": "/dashboard"},
                }
                for name in names
            ]
        )
    )
    assert clean is not None
    assert [i.get("icon") for i in clean["sidebarItems"]] == names


def test_composer_action_defaults_placement():
    clean, _ = validate_manifest(
        _base(
            composerActions=[
                {
                    "id": "x",
                    "label": "X",
                    "behavior": {"type": "insert-text", "text": "hi"},
                }
            ]
        )
    )
    assert clean is not None
    assert clean["composerActions"][0]["placement"] == "menu"


def test_is_valid_plugin_id():
    assert is_valid_plugin_id("catppuccin")
    assert is_valid_plugin_id("my-plugin_1")
    assert not is_valid_plugin_id("Bad")
    assert not is_valid_plugin_id("../escape")
    assert not is_valid_plugin_id(123)


def test_etag_stable_and_sensitive():
    a = compute_catalog_etag({"plugins": [{"id": "x", "enabled": True}]})
    b = compute_catalog_etag({"plugins": [{"id": "x", "enabled": True}]})
    c = compute_catalog_etag({"plugins": [{"id": "x", "enabled": False}]})
    assert a == b
    assert a != c


# --------------------------------------------------------------------------- #
# Manifest v2
# --------------------------------------------------------------------------- #
def _v2(**over):
    m = {"id": "demo", "apiVersion": 2}
    m.update(over)
    return m


def test_api_version_is_2():
    assert PLUGIN_API_VERSION == 2


def test_v1_manifest_still_validates_unchanged():
    clean, errors = validate_manifest(
        _base(
            sidebarItems=[
                {
                    "id": "docs",
                    "label": "Docs",
                    "action": {"type": "open-url", "url": "https://vicoa.ai"},
                }
            ]
        )
    )
    assert errors == []
    assert clean is not None
    assert set(clean) == {"id", "apiVersion", "sidebarItems"}


def test_full_v2_manifest_shape():
    clean, errors = validate_manifest(
        _v2(
            name="Dashboard",
            requirements={"vicoa": ">=1.10.0"},
            permissions=["projects:read", "tasks:read"],
            files=["~/**/.vicoa/dashboard.local.json"],
            network=["https://cdn.jsdelivr.net"],
            settings={
                "needsLabel": {
                    "type": "string",
                    "default": "needs-human",
                    "title": "Needs-you label",
                },
                "lanes": {"type": "object", "default": {}},
                "collapsed": {
                    "type": "array",
                    "items": "string",
                    "default": [],
                    "scope": "device",
                },
            },
            surfaces=[
                {
                    "id": "home",
                    "kind": "page",
                    "title": "Dashboard",
                    "entry": "pages/index.html",
                    "icon": "layout-dashboard",
                }
            ],
            sidebarItems=[
                {
                    "id": "open",
                    "label": "Dashboard",
                    "icon": "layout-dashboard",
                    "action": {"type": "surface", "surfaceId": "home"},
                }
            ],
            client="client.js",
            server="server.mjs",
        )
    )
    assert errors == []
    assert clean is not None
    assert clean["requirements"] == {"vicoa": ">=1.10.0"}
    assert clean["permissions"] == ["projects:read", "tasks:read"]
    assert clean["files"] == ["~/**/.vicoa/dashboard.local.json"]
    assert clean["network"] == ["https://cdn.jsdelivr.net"]
    assert clean["settings"] == {
        "needsLabel": {
            "type": "string",
            "default": "needs-human",
            "title": "Needs-you label",
            "scope": "machine",
        },
        "lanes": {"type": "object", "default": {}, "scope": "machine"},
        "collapsed": {
            "type": "array",
            "items": "string",
            "default": [],
            "scope": "device",
        },
    }
    assert clean["surfaces"] == [
        {
            "id": "home",
            "kind": "page",
            "title": "Dashboard",
            "entry": "pages/index.html",
            "icon": "layout-dashboard",
        }
    ]
    assert clean["sidebarItems"][0]["action"] == {
        "type": "surface",
        "surfaceId": "home",
    }
    assert clean["client"] == "client.js"
    assert clean["server"] == "server.mjs"


def test_unknown_top_level_fields_are_not_passed_through():
    clean, _ = validate_manifest(_v2(evil={"x": 1}, activation=["*"]))
    assert clean == {"id": "demo", "apiVersion": 2}


# -- requirements ----------------------------------------------------------- #
@pytest.mark.parametrize(
    "value, expected",
    [
        ("1.10.0", (1, 10, 0)),
        ("1.10", (1, 10, 0)),
        ("2", (2, 0, 0)),
        ("v1.2.3", (1, 2, 3)),
        ("  1.2.3 ", (1, 2, 3)),
        ("unknown", None),
        ("1.10.0rc1", None),
        ("1.2.3.4", None),
        ("", None),
        ("1..2", None),
        ("\u0661.2.3", None),  # Arabic-Indic digit one: ASCII digits only
    ],
)
def test_parse_version(value, expected):
    assert parse_version(value) == expected


@pytest.mark.parametrize(
    "version, range_, expected",
    [
        ("1.10.0", ">=1.10.0", True),
        ("1.9.11", ">=1.10.0", False),
        ("1.10.0", ">1.10", False),
        ("1.10.1", ">1.10", True),
        ("1.10.0", "<=1.10", True),
        ("2.0.0", "<2", False),
        ("1.99.0", ">=1.10.0 <2", True),
        ("1.99.0", ">=1.10.0, <2.0.0", True),
        ("2.0.0", ">=1.10.0,<2", False),
        ("1.10.0", "=1.10", True),
        ("1.10.0", "1.10.0", True),
        ("1.10.1", "1.10", False),
        ("1.10.0", ">=v1.10.0", True),
        ("v1.10.0", ">=1.10.0", True),
        # Unparseable versions (dev builds) always pass.
        ("unknown", ">=99", True),
        ("1.10.0.dev3", ">=99", True),
        # Invalid ranges never pass.
        ("1.10.0", ">= 1.10.0", False),
        ("1.10.0", "^1.10", False),
        ("1.10.0", "", False),
        ("1.10.0", "1.x", False),
    ],
)
def test_version_satisfies(version, range_, expected):
    assert version_satisfies(version, range_) is expected


def test_requirements_kept_verbatim():
    clean, errors = validate_manifest(
        _v2(requirements={"vicoa": ">=1.10.0 <2, >1.10.1"})
    )
    assert clean is not None
    assert clean["requirements"] == {"vicoa": ">=1.10.0 <2, >1.10.1"}
    assert errors == []


@pytest.mark.parametrize(
    "requirements",
    [
        {"vicoa": "^1.0"},
        {"vicoa": ">= 1.0"},
        {"vicoa": ""},
        {"vicoa": 110},
        {"vicoa": "1.0 || 2.0"},
        "1.0",
        ["1.0"],
    ],
)
def test_invalid_requirements_dropped_with_warning(requirements):
    clean, errors = validate_manifest(_v2(requirements=requirements))
    assert clean is not None
    assert "requirements" not in clean
    assert any("requirements" in e for e in errors)


def test_requirements_unknown_key_warned():
    clean, errors = validate_manifest(
        _v2(requirements={"vicoa": ">=1.0", "node": ">=20"})
    )
    assert clean is not None
    assert clean["requirements"] == {"vicoa": ">=1.0"}
    assert any("'node'" in e for e in errors)


# -- permissions ------------------------------------------------------------ #
def test_permission_set():
    assert PERMISSIONS == {
        "projects:read",
        "tasks:read",
        "tasks:write",
        "sessions:read",
        "sessions:write",
        "sessions:start",
        "automations:read",
        "automations:run",
        "backend",
    }


def test_permissions_deduped_in_order_unknown_warned():
    clean, errors = validate_manifest(
        _v2(
            permissions=[
                "tasks:write",
                "projects:read",
                "tasks:write",
                "files:write",
                42,
                "projects:read",
            ]
        )
    )
    assert clean is not None
    assert clean["permissions"] == ["tasks:write", "projects:read"]
    assert sum("permissions" in e for e in errors) == 2


def test_permissions_not_a_list():
    clean, errors = validate_manifest(_v2(permissions="tasks:read"))
    assert clean is not None
    assert "permissions" not in clean
    assert errors


# -- files ------------------------------------------------------------------ #
def test_files_rules():
    good = ["~/**/.vicoa/dashboard.local.json", "/data/*.json", "~/notes/?.md"]
    bad = [
        "relative/*.json",
        "~user/x",
        "~",
        "/data/../etc/passwd",
        "~/a/../../b",
        "/data/a\\b",
        "/data/\x00x",
        "/" + "a" * 500,
        "",
        7,
    ]
    clean, errors = validate_manifest(_v2(files=good + bad))
    assert clean is not None
    assert clean["files"] == good
    assert len(errors) == len(bad)


def test_files_capped_at_32():
    clean, errors = validate_manifest(_v2(files=[f"/d/{i}.json" for i in range(40)]))
    assert clean is not None
    assert len(clean["files"]) == 32
    assert any("32" in e for e in errors)


# -- network ---------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://cdn.jsdelivr.net", "https://cdn.jsdelivr.net"),
        ("https://CDN.JSDelivr.net/", "https://cdn.jsdelivr.net"),
        ("https://api.example.com:8443", "https://api.example.com:8443"),
        ("https://1.2.3.4", "https://1.2.3.4"),
        ("https://1.2.3.4:443/", "https://1.2.3.4:443"),
        ("http://localhost", "http://localhost"),
        ("http://localhost:3000", "http://localhost:3000"),
        ("http://127.0.0.1:8080/", "http://127.0.0.1:8080"),
    ],
)
def test_network_origins_kept_normalized(raw, expected):
    clean, errors = validate_manifest(_v2(network=[raw]))
    assert clean is not None
    assert clean["network"] == [expected]
    assert errors == []


@pytest.mark.parametrize(
    "raw",
    [
        "http://example.com",  # plain http only for localhost
        "http://10.0.0.1",
        "https://example.com/path",
        "https://example.com//",  # only ONE trailing slash is stripped
        "https://example.com?q=1",
        "https://example.com#x",
        "https://user@example.com",
        "https://user:pw@example.com",
        "https://exa mple.com",
        "https://example.com;",
        "https://example.com'",
        'https://"example.com"',
        "https://*",
        "https://*.*.example.com",
        "https://a.*.example.com",
        "https://-bad.example.com",
        "https://999.1.1.1",
        "https://1.2.3",
        "https://*.1.2.3.4",
        "https://example.com:0",
        "https://example.com:70000",
        "https://example.com:",
        "wss://example.com",
        "data:",
        "*",
        "'self'",
        "example.com",
        "",
        42,
    ],
)
def test_network_bad_origins_dropped(raw):
    clean, errors = validate_manifest(_v2(network=[raw]))
    assert clean is not None
    assert "network" not in clean
    assert len(errors) == 1


def test_network_deduped_after_normalizing():
    clean, _ = validate_manifest(
        _v2(network=["https://a.example", "https://A.example/", "https://b.example"])
    )
    assert clean is not None
    assert clean["network"] == ["https://a.example", "https://b.example"]


# -- settings --------------------------------------------------------------- #
def test_settings_defaults_filled_per_type():
    clean, errors = validate_manifest(
        _v2(
            settings={
                "s": {"type": "string"},
                "n": {"type": "number"},
                "b": {"type": "boolean"},
                "a": {"type": "array"},
                "o": {"type": "object"},
                "e": {"type": "string", "enum": ["low", "high"]},
            }
        )
    )
    assert errors == []
    assert clean is not None
    settings = clean["settings"]
    assert {k: v["default"] for k, v in settings.items()} == {
        "s": "",
        "n": 0,
        "b": False,
        "a": [],
        "o": {},
        "e": "low",
    }
    assert all(v["scope"] == "machine" for v in settings.values())
    assert settings["a"]["items"] == "string"
    assert settings["e"]["enum"] == ["low", "high"]


def test_settings_title_description_and_device_scope():
    clean, errors = validate_manifest(
        _v2(
            settings={
                "x": {
                    "type": "boolean",
                    "default": True,
                    "title": "X",
                    "description": "Longer words.",
                    "scope": "device",
                }
            }
        )
    )
    assert errors == []
    assert clean is not None
    assert clean["settings"]["x"] == {
        "type": "boolean",
        "default": True,
        "title": "X",
        "description": "Longer words.",
        "scope": "device",
    }


@pytest.mark.parametrize(
    "spec",
    [
        {"type": "date"},
        {},
        "string",
        {"type": "string", "scope": "cloud"},
        {"type": "string", "default": 3},
        {"type": "number", "default": "3"},
        {"type": "number", "default": True},
        {"type": "number", "default": float("nan")},
        {"type": "boolean", "default": 0},
        {"type": "array", "default": [1, 2]},
        {"type": "array", "items": "number"},
        {"type": "string", "items": "string"},
        {"type": "object", "default": []},
        {"type": "number", "enum": ["1"]},
        {"type": "string", "enum": []},
        {"type": "string", "enum": [""]},
        {"type": "string", "enum": ["a", 1]},
        {"type": "string", "enum": [str(i) for i in range(65)]},
        {"type": "string", "enum": ["a", "b"], "default": "c"},
        {"type": "string", "default": "x" * (16 * 1024)},
        {"type": "object", "default": {"k": "x" * (16 * 1024)}},
    ],
)
def test_invalid_setting_dropped_with_warning(spec):
    clean, errors = validate_manifest(
        _v2(settings={"good": {"type": "string"}, "k": spec})
    )
    assert clean is not None
    assert list(clean["settings"]) == ["good"]
    assert any("'k'" in e for e in errors)


def test_setting_keys_validated_and_capped():
    raw = {f"k{i}": {"type": "string"} for i in range(70)}
    raw["1bad"] = {"type": "string"}
    clean, errors = validate_manifest(_v2(settings=raw))
    assert clean is not None
    assert len(clean["settings"]) == 64
    assert any("64" in e for e in errors)

    clean, errors = validate_manifest(
        _v2(
            settings={
                "1bad": {"type": "string"},
                "has-dash": {"type": "string"},
                "a" * 65: {"type": "string"},
                "ok_Key9": {"type": "string"},
            }
        )
    )
    assert clean is not None
    assert list(clean["settings"]) == ["ok_Key9"]
    assert len(errors) == 3


def test_setting_overlong_title_dropped_setting_kept():
    clean, errors = validate_manifest(
        _v2(settings={"x": {"type": "string", "title": "t" * 201}})
    )
    assert clean is not None
    assert "title" not in clean["settings"]["x"]
    assert errors


def test_validate_setting_value():
    assert validate_setting_value({"type": "string"}, "x")
    assert not validate_setting_value({"type": "string"}, 1)
    enum = {"type": "string", "enum": ["a", "b"]}
    assert validate_setting_value(enum, "a")
    assert not validate_setting_value(enum, "c")
    assert validate_setting_value({"type": "number"}, 3)
    assert validate_setting_value({"type": "number"}, 3.5)
    assert validate_setting_value({"type": "number"}, 10**400)
    assert not validate_setting_value({"type": "number"}, True)
    assert not validate_setting_value({"type": "number"}, float("inf"))
    assert not validate_setting_value({"type": "number"}, "3")
    assert validate_setting_value({"type": "boolean"}, False)
    assert not validate_setting_value({"type": "boolean"}, 0)
    assert validate_setting_value({"type": "array"}, ["a"])
    assert validate_setting_value({"type": "array"}, [])
    assert not validate_setting_value({"type": "array"}, ["a", 1])
    assert not validate_setting_value({"type": "array"}, "a")
    assert validate_setting_value({"type": "object"}, {"a": [1]})
    assert not validate_setting_value({"type": "object"}, [])
    assert not validate_setting_value({"type": "nope"}, "x")
    assert not validate_setting_value({"type": "string"}, None)


# -- surfaces --------------------------------------------------------------- #
def test_surface_defaults_kind_page_and_drops_unknown_icon():
    clean, errors = validate_manifest(
        _v2(surfaces=[{"id": "home", "entry": "index.html", "icon": "skull"}])
    )
    assert clean is not None
    assert clean["surfaces"] == [{"id": "home", "kind": "page", "entry": "index.html"}]
    assert any("icon" in e for e in errors)


def test_surface_kinds():
    clean, errors = validate_manifest(
        _v2(
            surfaces=[
                {"id": "a", "kind": "page", "entry": "a.html"},
                {"id": "b", "kind": "panel", "entry": "b.html"},
                {"id": "c", "kind": "modal", "entry": "c.html"},
                {"id": "d", "kind": "window", "entry": "d.html"},
            ]
        )
    )
    assert clean is not None
    assert [s["kind"] for s in clean["surfaces"]] == ["page", "panel", "modal"]
    assert len(errors) == 1


@pytest.mark.parametrize(
    "entry",
    [
        "/pages/index.html",
        "../index.html",
        "pages/../../index.html",
        "./index.html",
        "pages/./index.html",
        "pages//index.html",
        "pages/index.html/",
        "pages\\index.html",
        "pages/index.htm",
        "pages/index.js",
        "pages/index.HTML",
        "a" * 296 + ".html",
        "",
        None,
        3,
    ],
)
def test_surface_bad_entry_dropped(entry):
    clean, errors = validate_manifest(_v2(surfaces=[{"id": "home", "entry": entry}]))
    assert clean is not None
    assert "surfaces" not in clean
    assert errors


@pytest.mark.parametrize("sid", ["Home", "../x", "a b", "", None, "-x"])
def test_surface_id_slug(sid):
    clean, _ = validate_manifest(_v2(surfaces=[{"id": sid, "entry": "a.html"}]))
    assert clean is not None
    assert "surfaces" not in clean


def test_surface_duplicate_ids_keep_first_and_cap():
    clean, errors = validate_manifest(
        _v2(
            surfaces=[
                {"id": "home", "entry": "first.html"},
                {"id": "home", "entry": "second.html"},
            ]
        )
    )
    assert clean is not None
    assert [s["entry"] for s in clean["surfaces"]] == ["first.html"]
    assert any("duplicate" in e for e in errors)

    many = [{"id": f"s{i}", "entry": "a.html"} for i in range(20)]
    clean, errors = validate_manifest(_v2(surfaces=many))
    assert clean is not None
    assert len(clean["surfaces"]) == 16
    assert any("16" in e for e in errors)


def test_surface_title_capped():
    clean, errors = validate_manifest(
        _v2(surfaces=[{"id": "home", "entry": "a.html", "title": "t" * 201}])
    )
    assert clean is not None
    assert "title" not in clean["surfaces"][0]
    assert errors


def test_sidebar_surface_must_name_a_declared_page():
    clean, errors = validate_manifest(
        _v2(
            surfaces=[
                {"id": "home", "entry": "home.html"},
                {"id": "side", "kind": "panel", "entry": "side.html"},
            ],
            sidebarItems=[
                {
                    "id": "ok",
                    "label": "OK",
                    "action": {"type": "surface", "surfaceId": "home"},
                },
                {
                    "id": "panel",
                    "label": "Panel",
                    "action": {"type": "surface", "surfaceId": "side"},
                },
                {
                    "id": "ghost",
                    "label": "Ghost",
                    "action": {"type": "surface", "surfaceId": "missing"},
                },
            ],
        )
    )
    assert clean is not None
    assert [i["id"] for i in clean["sidebarItems"]] == ["ok"]
    assert sum("not a declared page" in e for e in errors) == 2


def test_sidebar_surface_dropped_when_its_surface_is_invalid():
    clean, errors = validate_manifest(
        _v2(
            surfaces=[{"id": "home", "entry": "../escape.html"}],
            sidebarItems=[
                {
                    "id": "open",
                    "label": "Open",
                    "action": {"type": "surface", "surfaceId": "home"},
                }
            ],
        )
    )
    assert clean is not None
    assert "sidebarItems" not in clean
    assert len(errors) == 2


# -- client / server -------------------------------------------------------- #
@pytest.mark.parametrize("value", ["client.js", "dist/client.mjs"])
def test_entry_points_kept(value):
    clean, errors = validate_manifest(_v2(client=value, server=value))
    assert clean is not None
    assert clean["client"] == value
    assert clean["server"] == value
    assert errors == []


@pytest.mark.parametrize(
    "value", ["/abs/client.js", "../client.js", "client.ts", "a\\b.js", "", 1]
)
def test_bad_entry_points_dropped(value):
    clean, errors = validate_manifest(_v2(client=value, server=value))
    assert clean is not None
    assert "client" not in clean
    assert "server" not in clean
    assert len(errors) == 2


def test_wildcard_network_origins_refused():
    """``*.com`` would open the page to every .com site; list hosts one by one."""
    for origin in ["https://*.example.com", "https://*.com", "https://*.github.io"]:
        clean, errors = validate_manifest(_base(apiVersion=2, network=[origin]))
        assert clean is not None and "network" not in clean, origin
        assert errors


def test_files_globs_must_name_a_place():
    ok = ["~/data/**", "~/**/notes.json", "/srv/app/*.json", "~/a/*"]
    bad = ["~/**", "/**", "/*", "~/*", "~/*/*", "~/**/*"]
    clean, _ = validate_manifest(_base(apiVersion=2, files=ok + bad))
    assert clean is not None
    assert clean["files"] == ok


def test_app_paths_refuse_control_characters():
    """URL parsing drops tabs and newlines, so /<tab>/host would leave the app."""
    clean, _ = validate_manifest(
        _base(
            sidebarItems=[
                {
                    "id": f"x{n}",
                    "label": "X",
                    "action": {"type": "open-url", "url": url},
                }
                for n, url in enumerate(
                    ["/\t/evil.example", "/\n/evil.example", "/ok\x7f"]
                )
            ]
        )
    )
    assert clean is not None
    assert "sidebarItems" not in clean
