"""Tests for plugin manifest validation + catalog ETag (protocol.plugin_manifest)."""

from protocol.plugin_manifest import (
    compute_catalog_etag,
    is_valid_plugin_id,
    validate_manifest,
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
                    "action": {"type": "rpc", "method": "git-status"},
                },
                {"id": "d", "label": "D", "action": {"type": "bogus"}},
            ]
        )
    )
    assert clean is not None
    ids = {i["id"] for i in clean["sidebarItems"]}
    # javascript: url and bogus action dropped; https + rpc kept.
    assert ids == {"a", "c"}


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
