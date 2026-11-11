"""Plugin manifest schema, validation, and catalog ETag.

A plugin ships a ``plugin.json`` that the daemon reads off disk, validates here,
and returns through the ``plugin-catalog`` RPC. The renderer mirror of this
schema lives in ``apps/web/lib/plugins/types.ts`` — keep the two in sync.

What a manifest can declare:

- **Static contributions (v1):** ``themes`` (whitelisted color tokens),
  ``sidebarItems`` (open a URL or one of the plugin's pages),
  ``composerActions`` and ``slashCommands``. Nothing here runs code.
- **Pages (v2):** ``surfaces`` name HTML files inside the plugin directory that
  the renderer shows in a sandboxed iframe. The page reaches Vicoa only through
  the host's ``window.vicoa`` bridge, which enforces what the manifest asks for:
  ``permissions`` (Vicoa data the page may read or change), ``files`` (local
  files it may read, as globs; see ``protocol.plugin_paths``) and ``network``
  (origins its content security policy lets it reach).
- **Settings (v2):** a small typed ``settings`` schema; values live on the
  plugin's machine (``scope: "machine"``) or in the one browser
  (``scope: "device"``).
- ``requirements.vicoa`` (a version range the machine's Vicoa must satisfy),
  and ``client`` / ``server`` entry points reserved for later phases.

Validation is *tolerant*: a malformed individual field or contribution (one bad
theme, an unknown permission) is dropped with a recorded warning rather than
failing the whole plugin, but a manifest missing a usable ``id`` /
``apiVersion`` is rejected outright. The daemon only ever hands the renderer the
sanitized shape, so the client never sees a token, icon, path or origin it isn't
prepared for. The renderer re-checks what it injects (defense in depth), but the
authoritative allow-lists are here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from typing import Any, TypeGuard

# Manifests declaring a higher apiVersion than this are surfaced but the host
# renderer skips them (it cannot understand a newer contract).
PLUGIN_API_VERSION = 2

# What a plugin page may ask the bridge for. Each one is listed in the trust
# prompt; the renderer refuses bridge calls the manifest did not declare.
PERMISSIONS: frozenset[str] = frozenset(
    {
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
)

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
        "menu",
        "menu-foreground",
        "menu-border",
        "menu-elevated",
        "surface-nav",
        "surface-canvas",
        "success",
        "warning",
        "info",
        "user-bubble",
        "composer",
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
        "layout-dashboard",
        "bar-chart",
        "activity",
        "gauge",
        "kanban",
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


def _q(v: Any) -> str:
    """A value quoted for a warning, cut short so a huge field can't bloat it."""
    text = repr(v)
    return text if len(text) <= 80 else text[:77] + "..."


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
    # ``open-url`` and ``surface`` only. The old ``rpc`` action (call any daemon
    # method on click) was removed: it let a declarative manifest reach methods
    # like ``write-file``, and the trust prompt could not say what a click would
    # do. Logic that needs the machine belongs in a plugin backend instead.
    if not isinstance(raw, dict):
        return None
    kind = raw.get("type")
    if kind == "open-url":
        url = raw.get("url")
        if not _is_str(url) or not (
            url.startswith("https://") or url.startswith("http://") or _is_app_path(url)
        ):
            return None
        return {
            "type": "open-url",
            "url": url,
            "external": bool(raw.get("external", False)),
        }
    if kind == "surface":
        # The id becomes a URL path segment, so hold it to the plugin-id slug.
        surface_id = raw.get("surfaceId")
        if not isinstance(surface_id, str) or not _ID_RE.match(surface_id):
            return None
        return {"type": "surface", "surfaceId": surface_id}
    return None


def _is_app_path(url: str) -> bool:
    """An in-app route like ``/dashboard/tasks``.

    ``//host`` and ``/\\host`` are protocol-relative: a browser resolves them to
    another site, which would load inside the app window. So is ``/<tab>/host``,
    because URL parsing drops tabs and newlines, so control characters are
    refused too.
    """
    return (
        url.startswith("/")
        and not url.startswith("//")
        and "\\" not in url
        and not any(ord(c) < 0x20 or ord(c) == 0x7F for c in url)
    )


def _clean_sidebar_item(
    raw: Any, errors: list[str], page_surfaces: frozenset[str] = frozenset()
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    iid = raw.get("id")
    label = raw.get("label")
    if not _is_str(iid) or not _is_str(label):
        errors.append("sidebarItem: missing id/label")
        return None
    raw_action = raw.get("action")
    action = _clean_sidebar_action(raw_action)
    if action is None:
        kind = raw_action.get("type") if isinstance(raw_action, dict) else None
        if kind == "rpc":
            errors.append(
                f"sidebarItem {iid!r}: the 'rpc' action is no longer supported"
            )
        else:
            errors.append(f"sidebarItem {iid!r}: invalid action")
        return None
    if action["type"] == "surface" and action["surfaceId"] not in page_surfaces:
        errors.append(
            f"sidebarItem {iid!r}: surface {action['surfaceId']!r} is not a"
            " declared page"
        )
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


# --------------------------------------------------------------------------- #
# requirements: version ranges
# --------------------------------------------------------------------------- #
# ASCII digits only ([0-9], not \d, which also takes other scripts' digits).
_VERSION_RE = re.compile(r"v?([0-9]+)(?:\.([0-9]+))?(?:\.([0-9]+))?")
_COMPARATOR_RE = re.compile(r"(>=|<=|>|<|=)?(v?[0-9]+(?:\.[0-9]+){0,2})")
_RANGE_SEP_RE = re.compile(r"[\s,]+")
_MAX_RANGE_LEN = 200

Version = tuple[int, int, int]


def parse_version(s: str) -> Version | None:
    """``"1.10"`` -> ``(1, 10, 0)``; ``None`` when it isn't a plain version.

    Accepts surrounding whitespace, an optional leading ``v`` and one to three
    dot-separated numbers (missing parts are 0). Anything else, such as
    ``"unknown"`` or ``"1.10.0rc1"``, is unparseable.
    """
    if not isinstance(s, str):
        return None
    m = _VERSION_RE.fullmatch(s.strip())
    if m is None:
        return None
    return (int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0))


def _parse_range(range_: Any) -> list[tuple[str, Version]] | None:
    """Comparators of a range like ``">=1.10.0 <2"``, or ``None`` if invalid.

    One or more comparators separated by whitespace and/or commas. Each is an
    optional operator (``>=`` ``>`` ``<=`` ``<`` ``=``; none means ``=``)
    directly followed by a version as in :func:`parse_version` (so ``">= 1.2"``,
    with a space, is invalid).
    """
    if not isinstance(range_, str) or len(range_) > _MAX_RANGE_LEN:
        return None
    parts = [p for p in _RANGE_SEP_RE.split(range_) if p]
    if not parts:
        return None
    out: list[tuple[str, Version]] = []
    for part in parts:
        m = _COMPARATOR_RE.fullmatch(part)
        if m is None:
            return None
        version = parse_version(m.group(2))
        if version is None:
            return None
        out.append((m.group(1) or "=", version))
    return out


def _compare(current: Version, op: str, target: Version) -> bool:
    if op == ">=":
        return current >= target
    if op == ">":
        return current > target
    if op == "<=":
        return current <= target
    if op == "<":
        return current < target
    return current == target


def version_satisfies(version: str, range_: str) -> bool:
    """Whether ``version`` satisfies every comparator in ``range_``.

    An unparseable ``version`` (``"unknown"``, a dev or pre-release build)
    always satisfies, so a development build never locks plugins out. An
    invalid ``range_`` is never satisfied (the validator drops those, so a
    clean manifest never carries one).
    """
    current = parse_version(version)
    if current is None:
        return True
    comparators = _parse_range(range_)
    if comparators is None:
        return False
    return all(_compare(current, op, target) for op, target in comparators)


def _clean_requirements(raw: Any, errors: list[str]) -> dict[str, str] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append("requirements: not an object")
        return None
    for key in raw:
        if key != "vicoa":
            errors.append(f"requirements: unknown key {_q(key)} ignored")
    range_ = raw.get("vicoa")
    if range_ is None:
        return None
    if _parse_range(range_) is None:
        errors.append(f"requirements: invalid vicoa range {_q(range_)}")
        return None
    return {"vicoa": range_}


# --------------------------------------------------------------------------- #
# permissions / files / network
# --------------------------------------------------------------------------- #
_MAX_PERMISSION_ENTRIES = 64
_MAX_FILES = 32
_MAX_FILE_GLOB = 500
_MAX_NETWORK = 32
_MAX_ORIGIN = 300


def _clean_permissions(raw: Any, errors: list[str]) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        errors.append("permissions: not an array")
        return []
    if len(raw) > _MAX_PERMISSION_ENTRIES:
        errors.append(
            f"permissions: only the first {_MAX_PERMISSION_ENTRIES} entries are read"
        )
    out: list[str] = []
    for perm in raw[:_MAX_PERMISSION_ENTRIES]:
        if not isinstance(perm, str) or perm not in PERMISSIONS:
            errors.append(f"permissions: unknown permission {_q(perm)}")
            continue
        if perm not in out:
            out.append(perm)
    return out


def is_valid_files_glob(value: Any) -> bool:
    """A ``files`` entry: ``~/`` or ``/`` anchored, no ``..`` segment, no NUL or
    backslash, at most 500 characters, and naming some place: at least one
    segment must be more than ``*`` and ``?``. ``~/data/**`` and
    ``~/**/notes.json`` are fine; ``~/**``, ``/*`` and ``~/*/*`` (a whole tree)
    are not."""
    if not (
        _is_str(value, max_len=_MAX_FILE_GLOB)
        and (value.startswith("~/") or value.startswith("/"))
        and "\x00" not in value
        and "\\" not in value
        and ".." not in value.split("/")
    ):
        return False
    segments = value.split("/")[1:]  # drop "~" or the empty root segment
    return any(seg.strip("*?") for seg in segments)


def _clean_files(raw: Any, errors: list[str]) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        errors.append("files: not an array")
        return []
    if len(raw) > _MAX_FILES:
        errors.append(f"files: only the first {_MAX_FILES} entries are kept")
    out: list[str] = []
    for glob in raw[:_MAX_FILES]:
        if not is_valid_files_glob(glob):
            errors.append(f"files: invalid path glob {_q(glob)}")
            continue
        if glob not in out:
            out.append(glob)
    return out


_DNS_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HTTPS_ORIGIN_RE = re.compile(
    rf"https://((?:\*\.)?{_DNS_LABEL}(?:\.{_DNS_LABEL})*)(?::([0-9]{{1,5}}))?"
)
_HTTP_LOCAL_ORIGIN_RE = re.compile(
    r"http://(?:localhost|127\.0\.0\.1)(?::([0-9]{1,5}))?"
)


def _is_ipv4(host: str) -> bool:
    parts = host.split(".")
    return len(parts) == 4 and all(
        0 < len(p) <= 3 and p.isdigit() and int(p) <= 255 for p in parts
    )


def clean_origin(raw: Any) -> str | None:
    """A ``network`` entry normalized to a CSP source, or ``None`` if invalid.

    ``https://host[:port]`` where host is a DNS name or an IPv4 address, plus
    ``http://localhost[:port]``
    and ``http://127.0.0.1[:port]``. Lowercased, one trailing ``/`` removed;
    anything with a path, query, fragment, userinfo, whitespace, quote or ``;``
    is refused. A host whose last label is all digits must be an IPv4 address.
    Wildcards (``https://*.example.com``) are refused: ``*.com`` or
    ``*.github.io`` would let a page reach anyone's site while the trust prompt
    looks narrow, so each host is listed on its own.
    """
    if not isinstance(raw, str) or not 0 < len(raw) <= _MAX_ORIGIN:
        return None
    value = raw.lower()
    if value.endswith("/"):
        value = value[:-1]
    https = _HTTPS_ORIGIN_RE.fullmatch(value)
    if https is not None:
        host, port = https.group(1), https.group(2)
        if host.startswith("*."):
            return None
        if host.rsplit(".", 1)[-1].isdigit() and (
            host.startswith("*.") or not _is_ipv4(host)
        ):
            return None
    else:
        local = _HTTP_LOCAL_ORIGIN_RE.fullmatch(value)
        if local is None:
            return None
        port = local.group(1)
    if port is not None and not 1 <= int(port) <= 65535:
        return None
    return value


def _clean_network(raw: Any, errors: list[str]) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        errors.append("network: not an array")
        return []
    if len(raw) > _MAX_NETWORK:
        errors.append(f"network: only the first {_MAX_NETWORK} entries are kept")
    out: list[str] = []
    for entry in raw[:_MAX_NETWORK]:
        origin = clean_origin(entry)
        if origin is None:
            errors.append(f"network: invalid origin {_q(entry)}")
            continue
        if origin not in out:
            out.append(origin)
    return out


# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #
_SETTING_KEY_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
_SETTING_TYPES = ("string", "number", "boolean", "array", "object")
_SETTING_SCOPES = ("machine", "device")
_MAX_SETTINGS = 64
_MAX_ENUM = 64
_MAX_SETTING_DEFAULT_BYTES = 16 * 1024


def _empty_default(kind: str) -> Any:
    """The default a setting gets when it declares none (a fresh container)."""
    empty: dict[str, Any] = {
        "string": "",
        "number": 0,
        "boolean": False,
        "array": [],
        "object": {},
    }
    return empty[kind]


def validate_setting_value(spec: dict[str, Any], value: Any) -> bool:
    """Whether ``value`` fits a (clean) setting ``spec``.

    ``string`` (and in ``enum`` when one is given), ``number`` (int or finite
    float, never a bool), ``boolean``, ``array`` (of strings) or ``object``.
    """
    kind = spec.get("type")
    if kind == "string":
        if not isinstance(value, str):
            return False
        enum = spec.get("enum")
        return not isinstance(enum, list) or value in enum
    if kind == "number":
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        return isinstance(value, float) and math.isfinite(value)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "array":
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    if kind == "object":
        return isinstance(value, dict)
    return False


def _json_size(value: Any) -> int:
    return len(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _clean_setting(key: str, raw: Any, errors: list[str]) -> dict[str, Any] | None:
    """One settings entry. ``null`` for an optional field means "absent"."""
    where = f"setting {key!r}"
    if not isinstance(raw, dict):
        errors.append(f"{where}: not an object")
        return None
    kind = raw.get("type")
    if kind not in _SETTING_TYPES:
        errors.append(f"{where}: type must be one of {', '.join(_SETTING_TYPES)}")
        return None
    scope = raw.get("scope")
    if scope is None:
        scope = "machine"
    if scope not in _SETTING_SCOPES:
        errors.append(f"{where}: scope must be 'machine' or 'device'")
        return None
    spec: dict[str, Any] = {"type": kind}

    enum = raw.get("enum")
    if enum is not None:
        if (
            kind != "string"
            or not isinstance(enum, list)
            or not 0 < len(enum) <= _MAX_ENUM
            or not all(_is_str(e) for e in enum)
        ):
            errors.append(
                f"{where}: enum must be 1-{_MAX_ENUM} non-empty strings on a"
                " string setting"
            )
            return None
        spec["enum"] = list(enum)

    items = raw.get("items")
    if items is not None and (kind != "array" or items != "string"):
        errors.append(f"{where}: items must be 'string', on an array setting")
        return None
    if kind == "array":
        spec["items"] = "string"

    default = raw.get("default")
    if default is None:
        default = spec["enum"][0] if "enum" in spec else _empty_default(kind)
    elif not validate_setting_value(spec, default):
        errors.append(f"{where}: default does not match its type")
        return None
    elif _json_size(default) > _MAX_SETTING_DEFAULT_BYTES:
        errors.append(f"{where}: default is larger than 16 KiB")
        return None
    spec["default"] = default
    spec["scope"] = scope

    for field, max_len in (("title", 200), ("description", 1000)):
        val = raw.get(field)
        if val is None:
            continue
        if _is_str(val, max_len=max_len):
            spec[field] = val
        else:
            errors.append(f"{where}: {field} dropped (not a string up to {max_len})")
    return spec


def _clean_settings(raw: Any, errors: list[str]) -> dict[str, dict[str, Any]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        errors.append("settings: not an object")
        return {}
    if len(raw) > _MAX_SETTINGS:
        errors.append(f"settings: only the first {_MAX_SETTINGS} keys are kept")
    out: dict[str, dict[str, Any]] = {}
    for key in list(raw)[:_MAX_SETTINGS]:
        if not isinstance(key, str) or not _SETTING_KEY_RE.fullmatch(key):
            errors.append(f"settings: invalid key {_q(key)}")
            continue
        spec = _clean_setting(key, raw[key], errors)
        if spec is not None:
            out[key] = spec
    return out


# --------------------------------------------------------------------------- #
# surfaces and entry points
# --------------------------------------------------------------------------- #
_SURFACE_KINDS = ("page", "panel", "modal")
_MAX_SURFACES = 16
_MAX_ENTRY = 300


def is_valid_entry_path(value: Any, suffixes: tuple[str, ...] = (".html",)) -> bool:
    """A file inside the plugin directory, as a relative POSIX path.

    No leading ``/``, no empty, ``.`` or ``..`` segment, no backslash or NUL,
    at most 300 characters, ending in one of ``suffixes``.
    """
    if not _is_str(value, max_len=_MAX_ENTRY):
        return False
    if value.startswith("/") or "\\" in value or "\x00" in value:
        return False
    if any(seg in ("", ".", "..") for seg in value.split("/")):
        return False
    return value.endswith(suffixes)


def _clean_surface(raw: Any, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        errors.append("surface: not an object")
        return None
    sid = raw.get("id")
    if not isinstance(sid, str) or not _ID_RE.match(sid):
        errors.append(f"surface {_q(sid)}: id must be a lowercase slug")
        return None
    kind = raw.get("kind")
    if kind is None:
        kind = "page"
    if kind not in _SURFACE_KINDS:
        errors.append(f"surface {sid!r}: kind must be page, panel or modal")
        return None
    entry = raw.get("entry")
    if not is_valid_entry_path(entry):
        errors.append(
            f"surface {sid!r}: entry must be a relative path to an .html file"
            " inside the plugin"
        )
        return None
    out: dict[str, Any] = {"id": sid, "kind": kind, "entry": entry}
    title = raw.get("title")
    if title is not None:
        if _is_str(title):
            out["title"] = title
        else:
            errors.append(f"surface {sid!r}: title dropped")
    icon = raw.get("icon")
    if icon is not None:
        cleaned_icon = _clean_icon(icon)
        if cleaned_icon:
            out["icon"] = cleaned_icon
        else:
            errors.append(f"surface {sid!r}: unknown icon {_q(icon)} dropped")
    return out


def _clean_surfaces(raw: Any, errors: list[str]) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        errors.append("surfaces: not an array")
        return []
    if len(raw) > _MAX_SURFACES:
        errors.append(f"surfaces: only the first {_MAX_SURFACES} are kept")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in raw[:_MAX_SURFACES]:
        surface = _clean_surface(entry, errors)
        if surface is None:
            continue
        if surface["id"] in seen:
            errors.append(f"surface {surface['id']!r}: duplicate id dropped")
            continue
        seen.add(surface["id"])
        out.append(surface)
    return out


def _clean_list(
    raw: Any,
    cleaner: Callable[[Any, list[str]], dict[str, Any] | None],
    errors: list[str],
    *,
    limit: int = 64,
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

    requirements = _clean_requirements(raw.get("requirements"), errors)
    if requirements:
        clean["requirements"] = requirements
    permissions = _clean_permissions(raw.get("permissions"), errors)
    if permissions:
        clean["permissions"] = permissions
    files = _clean_files(raw.get("files"), errors)
    if files:
        clean["files"] = files
    network = _clean_network(raw.get("network"), errors)
    if network:
        clean["network"] = network
    settings = _clean_settings(raw.get("settings"), errors)
    if settings:
        clean["settings"] = settings
    for key in ("client", "server"):
        entry_point = raw.get(key)
        if entry_point is None:
            continue
        if is_valid_entry_path(entry_point, (".js", ".mjs")):
            clean[key] = entry_point
        else:
            errors.append(
                f"{key}: must be a relative path to a .js or .mjs file inside the"
                " plugin"
            )

    themes = _clean_list(raw.get("themes"), _clean_theme, errors)
    if themes:
        clean["themes"] = themes
    # Surfaces before sidebar items: a sidebar item may only open a declared page.
    surfaces = _clean_surfaces(raw.get("surfaces"), errors)
    if surfaces:
        clean["surfaces"] = surfaces
    page_surfaces = frozenset(s["id"] for s in surfaces if s["kind"] == "page")
    sidebar = _clean_list(
        raw.get("sidebarItems"),
        lambda item, errs: _clean_sidebar_item(item, errs, page_surfaces),
        errors,
    )
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
