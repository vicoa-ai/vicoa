"""Plugin manifest schema, validation, and catalog ETag.

The wire contract for **Tier 1** (declarative, no code execution) plugins. A
plugin ships a ``plugin.json`` that the daemon reads off disk, validates here,
and returns through the ``plugin-catalog`` RPC. The renderer mirror of this
schema lives in ``apps/web/lib/plugins/types.ts`` — keep the two in sync.

Validation is *tolerant*: a malformed individual contribution (one bad theme,
one bad sidebar item) is dropped with a recorded warning rather than failing the
whole plugin, but a manifest missing a usable ``id`` / ``apiVersion`` is
rejected outright. The daemon only ever hands the renderer the sanitized shape,
so the client never sees a token or icon it isn't prepared for. The renderer
additionally re-sanitizes theme token *values* before injecting them (defense in
depth), but the authoritative allow-lists are here.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, TypeGuard

# Manifests declaring a higher apiVersion than this are surfaced but the host
# renderer skips them (it cannot understand a newer contract).
PLUGIN_API_VERSION = 1

# Theme tokens a plugin may override — the shadcn custom properties from
# apps/web/app/globals.css. Anything outside this set is dropped so a theme can
# never inject an arbitrary CSS custom property.
THEME_TOKEN_WHITELIST: frozenset[str] = frozenset(
    {
        "background",
        "foreground",
        "card",
        "card-foreground",
        "popover",
        "popover-foreground",
        "primary",
        "primary-foreground",
        "secondary",
        "secondary-foreground",
        "muted",
        "muted-foreground",
        "accent",
        "accent-foreground",
        "destructive",
        "destructive-foreground",
        "border",
        "input",
        "ring",
        "chart-1",
        "chart-2",
        "chart-3",
        "chart-4",
        "chart-5",
        "sidebar-background",
        "sidebar-foreground",
        "sidebar-primary",
        "sidebar-primary-foreground",
        "sidebar-accent",
        "sidebar-accent-foreground",
        "sidebar-border",
        "sidebar-ring",
        "message-text",
        "radius",
    }
)

# Controlled icon names a plugin may reference. The renderer's <Icon> maps these
# to concrete lucide-react components (apps/web/components/plugins/plugin-icon.tsx);
# an unknown name is dropped and the renderer falls back to a default glyph, so
# the two lists must agree.
ICON_WHITELIST: frozenset[str] = frozenset(
    {
        "book-open",
        "list-todo",
        "calendar-clock",
        "layers",
        "settings",
        "terminal",
        "sparkles",
        "zap",
        "star",
        "link",
        "external-link",
        "folder",
        "file",
        "search",
        "plus",
        "play",
        "refresh-cw",
        "bell",
        "bot",
        "code",
        "git-branch",
        "message-square",
        "bug",
        "wrench",
        "palette",
        "puzzle",
        "rocket",
        "globe",
        "database",
        "cloud",
        "key",
        "lock",
        "shield",
        "check",
        "clipboard",
        "download",
        "upload",
        "command",
        "panel-left",
    }
)

# A plugin id doubles as its on-disk directory name, so keep it a strict slug.
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def is_valid_plugin_id(value: Any) -> bool:
    """Whether ``value`` is a well-formed plugin id (a lowercase dir-safe slug)."""
    return isinstance(value, str) and bool(_ID_RE.match(value))


# Theme token value: digits, letters, whitespace, and the punctuation used in
# HSL triplets / lengths / hex / rgb()/hsl(). Notably excludes ; { } < > " ' : @
# so a value cannot close the declaration or start a new rule. Mirrors the
# renderer's SAFE_VALUE.
_TOKEN_VALUE_RE = re.compile(r"^[0-9a-zA-Z%.,()/#\s_-]{1,64}$")

_MAX_STR = 200


def _is_str(v: Any, *, max_len: int = _MAX_STR) -> TypeGuard[str]:
    return isinstance(v, str) and 0 < len(v) <= max_len


def _clean_icon(raw: Any) -> str | None:
    return raw if isinstance(raw, str) and raw in ICON_WHITELIST else None


def _clean_theme(raw: Any, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        errors.append("theme: not an object")
        return None
    tid = raw.get("id")
    label = raw.get("label")
    base = raw.get("base")
    if not _is_str(tid) or not _is_str(label):
        errors.append("theme: missing id/label")
        return None
    if base not in ("dark", "light"):
        errors.append(f"theme {tid!r}: base must be 'dark' or 'light'")
        return None
    tokens_in = raw.get("tokens")
    if not isinstance(tokens_in, dict):
        errors.append(f"theme {tid!r}: tokens must be an object")
        return None
    tokens: dict[str, str] = {}
    for name, value in tokens_in.items():
        if name not in THEME_TOKEN_WHITELIST:
            continue  # silently drop unknown tokens
        if not isinstance(value, str):
            continue
        trimmed = value.strip()
        low = trimmed.lower()
        if not _TOKEN_VALUE_RE.match(trimmed) or "url(" in low or "expression" in low:
            errors.append(f"theme {tid!r}: token {name!r} has an unsafe value")
            continue
        tokens[name] = trimmed
    if not tokens:
        errors.append(f"theme {tid!r}: no valid tokens")
        return None
    return {"id": tid, "label": label, "base": base, "tokens": tokens}


def _clean_sidebar_action(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    kind = raw.get("type")
    if kind == "open-url":
        url = raw.get("url")
        if not _is_str(url) or not (
            url.startswith("https://")
            or url.startswith("http://")
            or url.startswith("/")
        ):
            return None
        return {
            "type": "open-url",
            "url": url,
            "external": bool(raw.get("external", False)),
        }
    if kind == "rpc":
        method = raw.get("method")
        if not _is_str(method):
            return None
        params = raw.get("params")
        return {
            "type": "rpc",
            "method": method,
            "params": params if isinstance(params, dict) else {},
        }
    if kind == "surface":
        surface_id = raw.get("surfaceId")
        if not _is_str(surface_id):
            return None
        return {"type": "surface", "surfaceId": surface_id}
    return None


def _clean_sidebar_item(raw: Any, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    iid = raw.get("id")
    label = raw.get("label")
    if not _is_str(iid) or not _is_str(label):
        errors.append("sidebarItem: missing id/label")
        return None
    action = _clean_sidebar_action(raw.get("action"))
    if action is None:
        errors.append(f"sidebarItem {iid!r}: invalid action")
        return None
    slot = raw.get("slot")
    out: dict[str, Any] = {
        "id": iid,
        "label": label,
        "slot": slot if slot in ("nav", "footer") else "nav",
        "action": action,
    }
    icon = _clean_icon(raw.get("icon"))
    if icon:
        out["icon"] = icon
    return out


def _clean_composer_behavior(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    kind = raw.get("type")
    if kind == "insert-text":
        text = raw.get("text")
        return (
            {"type": "insert-text", "text": text}
            if _is_str(text, max_len=4000)
            else None
        )
    if kind == "insert-path-ref":
        path = raw.get("path")
        return (
            {"type": "insert-path-ref", "path": path}
            if _is_str(path, max_len=4000)
            else None
        )
    if kind == "panel":
        panel_id = raw.get("panelId")
        return {"type": "panel", "panelId": panel_id} if _is_str(panel_id) else None
    return None


def _clean_composer_action(raw: Any, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    aid = raw.get("id")
    label = raw.get("label")
    if not _is_str(aid) or not _is_str(label):
        errors.append("composerAction: missing id/label")
        return None
    behavior = _clean_composer_behavior(raw.get("behavior"))
    if behavior is None:
        errors.append(f"composerAction {aid!r}: invalid behavior")
        return None
    placement = raw.get("placement")
    out: dict[str, Any] = {
        "id": aid,
        "label": label,
        "placement": placement if placement in ("menu", "toolbar") else "menu",
        "behavior": behavior,
    }
    icon = _clean_icon(raw.get("icon"))
    if icon:
        out["icon"] = icon
    return out


def _clean_slash_command(raw: Any, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    cid = raw.get("id")
    command = raw.get("command")
    insert_text = raw.get("insertText")
    if (
        not _is_str(cid)
        or not _is_str(command)
        or not _is_str(insert_text, max_len=4000)
    ):
        errors.append("slashCommand: missing id/command/insertText")
        return None
    out: dict[str, Any] = {"id": cid, "command": command, "insertText": insert_text}
    label = raw.get("label")
    if _is_str(label):
        out["label"] = label
    return out


def _clean_list(
    raw: Any, cleaner: Any, errors: list[str], *, limit: int = 64
) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        errors.append("contribution list is not an array")
        return []
    out: list[dict[str, Any]] = []
    for entry in raw[:limit]:
        cleaned = cleaner(entry, errors)
        if cleaned is not None:
            out.append(cleaned)
    return out


def validate_manifest(raw: Any) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate and sanitize a parsed ``plugin.json``.

    Returns ``(clean_manifest, errors)``. ``clean_manifest`` is ``None`` only
    when the manifest lacks a usable ``id`` / ``apiVersion``; otherwise it is a
    minimal, whitelisted dict safe to hand to the renderer. ``errors`` collects
    non-fatal warnings about dropped contributions.
    """
    errors: list[str] = []
    if not isinstance(raw, dict):
        return None, ["manifest is not a JSON object"]

    pid = raw.get("id")
    if not isinstance(pid, str) or not _ID_RE.match(pid):
        return None, ["manifest 'id' missing or not a lowercase slug"]

    api = raw.get("apiVersion")
    if not isinstance(api, int) or isinstance(api, bool) or api < 1:
        return None, [f"plugin {pid!r}: 'apiVersion' must be a positive integer"]

    clean: dict[str, Any] = {"id": pid, "apiVersion": api}
    for key in ("name", "description", "version", "author", "homepage"):
        val = raw.get(key)
        if _is_str(val, max_len=500):
            clean[key] = val

    themes = _clean_list(raw.get("themes"), _clean_theme, errors)
    if themes:
        clean["themes"] = themes
    sidebar = _clean_list(raw.get("sidebarItems"), _clean_sidebar_item, errors)
    if sidebar:
        clean["sidebarItems"] = sidebar
    composer = _clean_list(raw.get("composerActions"), _clean_composer_action, errors)
    if composer:
        clean["composerActions"] = composer
    slash = _clean_list(raw.get("slashCommands"), _clean_slash_command, errors)
    if slash:
        clean["slashCommands"] = slash

    return clean, errors


def compute_catalog_etag(payload: Any) -> str:
    """SHA-256 of the canonical JSON for a catalog payload.

    Includes the full catalog (manifests + enabled/trusted flags), so any
    install / edit / enable-toggle changes the ETag and the renderer re-fetches.
    """
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
