"""Daemon RPC handlers for the plugin system.

Management: scan / catalog / list / install / link / remove / enable / trust /
reload. Plugin pages (served by the renderer in a sandboxed iframe): read the
plugin's own files, read the local files its manifest declares, machine-scope
settings, and a per-plugin log.

Plugins live on disk under ``~/.vicoa/plugins/<id>/``, each a directory holding
a ``plugin.json`` and the files it names (HTML pages, later scripts). A plugin
directory is either a copy (``install``) or a **symlink** to a development
directory (``link``); for a linked plugin the files are read from the link
target, and removing it only removes the link. Nothing a plugin ships is ever
executed here, and **no install scripts are ever run**.

Mirrors the conventions of ``skills_ops`` (git clone / dir copy into place, a
hidden ``.vicoa-plugins.json`` provenance manifest, size/count guardrails).
Enable state lives in ``~/.vicoa/config.json`` under a ``plugins`` section;
per-plugin trust lives in ``~/.vicoa/daemon_state.json`` keyed by the manifest's
SHA-256, mirroring ``worktree_trust`` (editing a plugin's manifest re-arms the
trust prompt), next to each plugin's reload counter. Settings and logs are kept
beside the plugins, in ``.settings/<id>.json`` and ``.logs/<id>.log``, never
inside a plugin directory.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import shutil
import stat
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from protocol.plugin_manifest import (
    PLUGIN_API_VERSION,
    compute_catalog_etag,
    is_valid_plugin_id,
    validate_manifest,
    validate_setting_value,
    version_satisfies,
)
from protocol.plugin_paths import path_matches_any
from vicoa.machine_state import read_state_file, save_state_file
from vicoa.rpc.paths import OutsideRoot, resolve_inside_root

_MANIFEST_NAME = ".vicoa-plugins.json"
_PLUGIN_JSON = "plugin.json"
# Dot-dirs beside the plugins (a plugin id never starts with a dot).
_SETTINGS_DIR = ".settings"
_LOGS_DIR = ".logs"

# One RPC frame carries one file; keep reads well inside it.
_MAX_READ_BYTES = 1024 * 1024
_MAX_SETTINGS_BYTES = 64 * 1024
_MAX_LOG_BYTES = 256 * 1024
# Trim to this when the log outgrows _MAX_LOG_BYTES, so a busy plugin does not
# rewrite the whole file on every call.
_LOG_TRIM_TO_BYTES = 192 * 1024
_MAX_LOG_ENTRIES = 50
_MAX_LOG_MESSAGE = 2000
_DEFAULT_LOG_LINES = 200
_MAX_LOG_LINES = 2000
_LOG_LEVELS = {"info": "INFO", "warn": "WARN", "error": "ERROR"}

# RPC handlers run on a thread pool; serialize the read-modify-write files.
_settings_lock = threading.Lock()
_log_lock = threading.Lock()
_state_lock = threading.Lock()

# Guardrails on an installed plugin tree (excluding .git). Mirrors skills_ops.
_MAX_FILE_BYTES = 2 * 1024 * 1024
_MAX_TOTAL_BYTES = 25 * 1024 * 1024
_MAX_FILE_COUNT = 1024
_CLONE_TIMEOUT_S = 25  # must fit the WS RPC budget (~30s)

_GIT_URL_SCHEMES = ("https://", "http://", "git://", "ssh://", "file://", "git@")

# daemon_state.json key: {plugin_id: manifest_sha256}. Trust is a property of the
# machine, never synced to another device (same boundary as worktree_trust).
_TRUST_KEY = "plugin_trust"

# daemon_state.json key: {plugin_id: int}, bumped by ``plugin-reload``. It is in
# the catalog (and so its ETag), which is how open clients learn to reload.
_RELOAD_KEY = "plugin_reload_nonce"

# config.json section shape: {"enabled": bool, "states": {id: bool}}.
_CONFIG_KEY = "plugins"


# --------------------------------------------------------------------------- #
# Paths (resolved at call time so a redirected HOME in tests is honored)
# --------------------------------------------------------------------------- #
def plugins_dir() -> Path:
    return Path.home() / ".vicoa" / "plugins"


def _state_path() -> Path:
    return Path.home() / ".vicoa" / "daemon_state.json"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _settings_path(plugin_id: str) -> Path:
    return plugins_dir() / _SETTINGS_DIR / f"{plugin_id}.json"


def _log_path(plugin_id: str) -> Path:
    return plugins_dir() / _LOGS_DIR / f"{plugin_id}.log"


def _home() -> str:
    # Path.home() rather than os.path.expanduser so a redirected home in tests
    # is honored everywhere.
    return str(Path.home())


def _expand_home(path: str) -> str:
    if path == "~":
        return _home()
    if path.startswith("~/"):
        return _home() + path[1:]
    return path


def _vicoa_version() -> str:
    import vicoa

    return str(getattr(vicoa, "__version__", "unknown"))


# --------------------------------------------------------------------------- #
# Provenance manifest (DB-less, hidden inside plugins_dir)
# --------------------------------------------------------------------------- #
def _manifest_path() -> Path:
    return plugins_dir() / _MANIFEST_NAME


def _read_provenance() -> dict[str, dict[str, Any]]:
    try:
        with open(_manifest_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write_bytes(path: Path, data: bytes) -> bool:
    """Write ``data`` to ``path`` via a temp file + rename. False on failure."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".vicoa-tmp-")
    except OSError:
        return False
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def _atomic_write_json(path: Path, data: dict[str, Any]) -> bool:
    encoded = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")
    return _atomic_write_bytes(path, encoded)


def _write_provenance_entry(plugin_id: str, entry: dict[str, Any]) -> None:
    data = _read_provenance()
    data[plugin_id] = entry
    _atomic_write_json(_manifest_path(), data)


def _drop_provenance_entry(plugin_id: str) -> None:
    data = _read_provenance()
    if plugin_id in data:
        del data[plugin_id]
        _atomic_write_json(_manifest_path(), data)


# --------------------------------------------------------------------------- #
# Config (enable state)
# --------------------------------------------------------------------------- #
def _read_config_section() -> dict[str, Any]:
    # Lazy import to avoid an import cycle (cli -> commands.plugin -> plugin_ops).
    from vicoa.cli import load_user_config

    section = load_user_config().get(_CONFIG_KEY)
    return section if isinstance(section, dict) else {}


def _write_config_section(section: dict[str, Any]) -> None:
    from vicoa.cli import save_user_config

    save_user_config({_CONFIG_KEY: section})


def _plugins_enabled(section: dict[str, Any] | None = None) -> bool:
    sec = section if section is not None else _read_config_section()
    val = sec.get("enabled", True)
    return bool(val) if isinstance(val, bool) else True


def _is_enabled(plugin_id: str, section: dict[str, Any] | None = None) -> bool:
    sec = section if section is not None else _read_config_section()
    states = sec.get("states")
    if isinstance(states, dict) and plugin_id in states:
        return bool(states[plugin_id])
    return True  # installed plugins default to enabled


# --------------------------------------------------------------------------- #
# Trust (per manifest hash)
# --------------------------------------------------------------------------- #
def _manifest_hash(plugin_path: Path) -> str | None:
    try:
        raw = (plugin_path / _PLUGIN_JSON).read_bytes()
    except OSError:
        return None
    return hashlib.sha256(raw).hexdigest()


def is_plugin_trusted(
    plugin_id: str, plugin_path: Path, state_path: Path | None = None
) -> bool:
    current = _manifest_hash(plugin_path)
    if current is None:
        return False
    trust = read_state_file(state_path or _state_path()).get(_TRUST_KEY)
    if not isinstance(trust, dict):
        return False
    return trust.get(plugin_id) == current


def grant_plugin_trust(
    plugin_id: str,
    manifest_sha256: str | None = None,
    state_path: Path | None = None,
) -> dict[str, Any]:
    """Persist a trust grant for the plugin's current manifest hash.

    ``manifest_sha256`` is the hash of the manifest the user reviewed (the
    catalog's ``manifest_sha256``). When given, the grant is refused with
    ``manifest_changed`` if ``plugin.json`` changed since, so a plugin can't
    widen what it asks for while the prompt is open. The CLI, where the user
    trusts what is on disk now, omits it.
    """
    if not is_valid_plugin_id(plugin_id):
        return {"error": "invalid_plugin_id"}
    try:
        dest = resolve_inside_root(plugins_dir(), plugin_id)
    except OutsideRoot:
        return {"error": "invalid_plugin_id"}
    current = _manifest_hash(dest)
    if current is None:
        return {"error": "not_found"}
    if manifest_sha256 is not None and manifest_sha256 != current:
        return {
            "error": "manifest_changed",
            "message": "plugin.json changed after it was shown; review it again",
        }
    path = state_path or _state_path()
    with _state_lock:
        state = read_state_file(path)
        trust = state.get(_TRUST_KEY)
        if not isinstance(trust, dict):
            trust = {}
        trust[plugin_id] = current
        state[_TRUST_KEY] = trust
        save_state_file(state, path)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Reload counter
# --------------------------------------------------------------------------- #
def _reload_nonces(state: dict[str, Any]) -> dict[str, int]:
    raw = state.get(_RELOAD_KEY)
    if not isinstance(raw, dict):
        return {}
    return {
        k: v
        for k, v in raw.items()
        if isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool)
    }


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #
def _valid_git_url(url: Any) -> bool:
    return (
        isinstance(url, str)
        and bool(url.strip())
        and url.strip().startswith(_GIT_URL_SCHEMES)
    )


def _within_caps(src: Path) -> tuple[bool, str]:
    total = 0
    count = 0
    for dirpath, dirnames, filenames in os.walk(src):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for filename in filenames:
            try:
                size = (Path(dirpath) / filename).stat().st_size
            except OSError:
                continue
            if size > _MAX_FILE_BYTES:
                return False, "file_too_large"
            total += size
            count += 1
            if count > _MAX_FILE_COUNT:
                return False, "too_many_files"
            if total > _MAX_TOTAL_BYTES:
                return False, "plugin_too_large"
    return True, ""


def _parse_manifest(raw: bytes) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        parsed = json.loads(raw)
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError
        return None, [f"plugin.json unreadable: {exc}"]
    return validate_manifest(parsed)


def _load_manifest(plugin_path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    manifest, errors, _ = _load_manifest_hashed(plugin_path)
    return manifest, errors


def _load_manifest_hashed(
    plugin_path: Path,
) -> tuple[dict[str, Any] | None, list[str], str | None]:
    """The manifest and the SHA-256 of the very bytes it was parsed from, so a
    catalog entry's manifest and its trust flag always describe the same file."""
    try:
        raw = (plugin_path / _PLUGIN_JSON).read_bytes()
    except OSError as exc:
        return None, [f"plugin.json unreadable: {exc}"], None
    manifest, errors = _parse_manifest(raw)
    return manifest, errors, hashlib.sha256(raw).hexdigest()


def _trust_map() -> dict[str, Any]:
    trust = read_state_file(_state_path()).get(_TRUST_KEY)
    return trust if isinstance(trust, dict) else {}


def _has_client_bundle(plugin_path: Path) -> bool:
    return (plugin_path / "dist" / "client.js").is_file()


def _requirement_status(
    manifest: dict[str, Any] | None, version: str
) -> tuple[bool, str | None]:
    """``(requirements_ok, requirement_error)`` for this machine's Vicoa."""
    requirements = manifest.get("requirements") if manifest else None
    range_ = requirements.get("vicoa") if isinstance(requirements, dict) else None
    if not isinstance(range_, str) or version_satisfies(version, range_):
        return True, None
    return False, f"Needs Vicoa {range_.strip()}; this machine has {version}"


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #
def _scan() -> list[dict[str, Any]]:
    """Every installed plugin, with its validated manifest and metadata.

    Malformed plugins are included with ``manifest=None`` + ``errors`` so the
    management UI can surface them; the catalog filters them out. A linked
    plugin (a symlink) whose target is gone shows up the same way, so it can
    still be removed.
    """
    root = plugins_dir()
    provenance = _read_provenance()
    out: list[dict[str, Any]] = []
    if not root.is_dir():
        return out
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if child.name.startswith("."):
            continue  # provenance, .settings/, .logs/, temp files
        linked = child.is_symlink()
        if child.is_dir():
            manifest, errors, manifest_sha256 = _load_manifest_hashed(child)
        elif linked:
            manifest, errors, manifest_sha256 = (
                None,
                ["linked directory is missing"],
                None,
            )
        else:
            continue
        prov = provenance.get(child.name, {})
        entry: dict[str, Any] = {
            "dir": child.name,
            "path": str(child),
            "manifest": manifest,
            "errors": errors,
            "source": prov.get("source"),
            "installed_at": prov.get("installed_at"),
            "linked": linked,
            "link_target": _link_target(child) if linked else None,
            "manifest_sha256": manifest_sha256,
        }
        if manifest is not None:
            manifest["hasClientBundle"] = _has_client_bundle(child)
        out.append(entry)
    return out


def _link_target(link: Path) -> str | None:
    try:
        return os.readlink(link)
    except OSError:
        return None


# --------------------------------------------------------------------------- #
# RPC handlers
# --------------------------------------------------------------------------- #
def plugin_catalog(etag: str | None = None) -> dict[str, Any]:
    """The renderer-facing catalog: valid, id-keyed plugins with enable/trust
    flags. Returns ``{etag, not_modified: True}`` when the caller's ETag matches.
    """
    section = _read_config_section()
    plugins_on = _plugins_enabled(section)
    version = _vicoa_version()
    nonces = _reload_nonces(read_state_file(_state_path()))
    trust = _trust_map()
    plugins: list[dict[str, Any]] = []
    for entry in _scan():
        manifest = entry["manifest"]
        if manifest is None:
            continue  # malformed — visible only via plugin-list
        pid = manifest["id"]
        # Guard against a dir named differently from the manifest id: the on-disk
        # dir name is authoritative for trust/enable/remove.
        dir_name = entry["dir"]
        if not is_valid_plugin_id(dir_name):
            continue
        requirements_ok, requirement_error = _requirement_status(manifest, version)
        sha = entry["manifest_sha256"]
        plugins.append(
            {
                "id": pid,
                "dir": dir_name,
                "manifest": manifest,
                "enabled": _is_enabled(dir_name, section),
                "trusted": sha is not None and trust.get(dir_name) == sha,
                "manifest_sha256": sha,
                "server_available": False,  # plugin backends arrive in P5
                "source": entry["source"],
                "api_compatible": manifest["apiVersion"] <= PLUGIN_API_VERSION,
                "requirements_ok": requirements_ok,
                "requirement_error": requirement_error,
                "linked": entry["linked"],
                "reload_nonce": nonces.get(dir_name, 0),
            }
        )
    payload: dict[str, Any] = {
        "plugins_enabled": plugins_on,
        "plugins": plugins,
        "vicoa_version": version,
    }
    computed = compute_catalog_etag(payload)
    if etag is not None and etag == computed:
        return {"etag": computed, "not_modified": True}
    payload["etag"] = computed
    return payload


def plugin_list() -> dict[str, Any]:
    """Fuller listing (including malformed plugins + errors) for CLI / settings."""
    section = _read_config_section()
    version = _vicoa_version()
    trust = _trust_map()
    out: list[dict[str, Any]] = []
    for entry in _scan():
        manifest = entry["manifest"]
        dir_name = entry["dir"]
        sha = entry["manifest_sha256"]
        requirements_ok, requirement_error = _requirement_status(manifest, version)
        out.append(
            {
                "id": manifest["id"] if manifest else dir_name,
                "dir": dir_name,
                "name": (manifest.get("name") if manifest else None) or dir_name,
                "valid": manifest is not None,
                "errors": entry["errors"],
                "enabled": _is_enabled(dir_name, section),
                "trusted": bool(manifest)
                and sha is not None
                and trust.get(dir_name) == sha,
                "manifest_sha256": sha,
                "source": entry["source"],
                "installed_at": entry["installed_at"],
                "path": entry["path"],
                "linked": entry["linked"],
                "link_target": entry["link_target"],
                "requirements_ok": requirements_ok,
                "requirement_error": requirement_error,
                "contributes": _summarize(manifest) if manifest else {},
            }
        )
    return {"plugins_enabled": _plugins_enabled(section), "plugins": out}


def _summarize(manifest: dict[str, Any]) -> dict[str, int]:
    return {
        "themes": len(manifest.get("themes") or []),
        "sidebarItems": len(manifest.get("sidebarItems") or []),
        "composerActions": len(manifest.get("composerActions") or []),
        "slashCommands": len(manifest.get("slashCommands") or []),
        "surfaces": len(manifest.get("surfaces") or []),
        "permissions": len(manifest.get("permissions") or []),
    }


def _acquire_source(
    source: str, ref: str | None, tmp: str
) -> tuple[Path | None, dict[str, Any] | None]:
    """Materialize ``source`` into a temp dir. Returns (path, None) or (None, error)."""
    if isinstance(source, str) and os.path.isdir(os.path.expanduser(source)):
        src = Path(os.path.expanduser(source)).resolve()
        return src, None
    if not _valid_git_url(source):
        return None, {"error": "invalid_source"}
    clone_dir = os.path.join(tmp, "repo")
    cmd = ["git", "clone", "--depth", "1", "--single-branch"]
    if ref:
        cmd += ["--branch", ref]
    cmd += [source.strip(), clone_dir]
    try:
        subprocess.run(cmd, capture_output=True, timeout=_CLONE_TIMEOUT_S, check=True)
    except subprocess.TimeoutExpired:
        return None, {"error": "install_timeout"}
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "replace")[-400:].strip()
        return None, {"error": "clone_failed", "detail": detail}
    except FileNotFoundError:
        return None, {"error": "git_not_available"}
    return Path(clone_dir), None


def install_plugin(
    source: str,
    ref: str | None = None,
    subdir: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Install a plugin from a local directory or a git URL.

    The source root (or ``subdir`` within it) must contain a ``plugin.json`` with
    a valid ``id``; the plugin lands at ``~/.vicoa/plugins/<id>/``. NO scripts
    from the source are ever executed (git clone + copy only). Returns the
    installed summary or ``{"error": <code>}``.
    """
    tmp = tempfile.mkdtemp(prefix="vicoa-plugin-")
    try:
        src, err = _acquire_source(source, ref, tmp)
        if err is not None:
            return err
        assert src is not None
        if subdir:
            cleaned = os.path.normpath(subdir.strip().strip("/"))
            if cleaned.startswith("..") or os.path.isabs(cleaned):
                return {"error": "invalid_subdir"}
            src = src / cleaned

        if not (src / _PLUGIN_JSON).is_file():
            return {"error": "manifest_not_found"}

        manifest, errors = _load_manifest(src)
        if manifest is None:
            return {"error": "invalid_manifest", "detail": "; ".join(errors)[:400]}
        pid = manifest["id"]

        ok, cap_error = _within_caps(src)
        if not ok:
            return {"error": cap_error}

        root = plugins_dir()
        try:
            dest = resolve_inside_root(root, pid)
        except OutsideRoot:
            return {"error": "invalid_plugin_id"}

        if dest.is_symlink():
            # A linked development directory. Never copy over it (rmtree on the
            # link would fail, and following it would wipe the developer's
            # files); `remove` unlinks it first.
            return {
                "error": "plugin_linked",
                "message": f"'{pid}' is linked; remove the link before installing",
            }
        if dest.exists():
            if not overwrite:
                return {"error": "plugin_exists"}
            if os.path.realpath(src) == os.path.realpath(dest):
                # Reinstalling the installed copy onto itself would delete the
                # source before copying it.
                return {"error": "plugin_exists"}
            shutil.rmtree(dest)

        root.mkdir(parents=True, exist_ok=True)
        # symlinks=True copies links as links. Following them would copy what a
        # link points at (say ~/.ssh/id_rsa) into the plugin as a plain file,
        # which `plugin-file` would then serve; as a link, `plugin-file` sees
        # that it leaves the plugin and refuses it.
        shutil.copytree(src, dest, symlinks=True, ignore=shutil.ignore_patterns(".git"))

        installed_at = _utcnow_iso()
        _write_provenance_entry(
            pid,
            {
                "source": source.strip() if isinstance(source, str) else "",
                "ref": ref or "",
                "subdir": subdir or "",
                "installed_at": installed_at,
            },
        )
        return {
            "id": pid,
            "name": manifest.get("name") or pid,
            "path": str(dest),
            "installed_at": installed_at,
            "warnings": errors,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def remove_plugin(plugin_id: str) -> dict[str, Any]:
    """Uninstall a plugin and forget its enable/trust/provenance/reload state,
    settings and log.

    A linked plugin is only unlinked: the link target is the developer's own
    directory and is never deleted or modified.
    """
    if not is_valid_plugin_id(plugin_id):
        return {"error": "invalid_plugin_id"}
    try:
        dest = resolve_inside_root(plugins_dir(), plugin_id)
    except OutsideRoot:
        return {"error": "invalid_plugin_id"}
    if dest.is_symlink():  # checked first: is_dir() follows the link
        if not _unlink_dir_link(dest):
            return {"error": "remove_failed"}
    elif dest.is_dir():
        shutil.rmtree(dest, ignore_errors=True)
    else:
        return {"error": "not_found"}
    _drop_provenance_entry(plugin_id)
    _forget_plugin_files(plugin_id)

    # Forget enable state.
    section = _read_config_section()
    states = section.get("states")
    if isinstance(states, dict) and plugin_id in states:
        del states[plugin_id]
        section["states"] = states
        _write_config_section(section)

    # Forget trust and the reload counter.
    path = _state_path()
    with _state_lock:
        state = read_state_file(path)
        changed = False
        for key in (_TRUST_KEY, _RELOAD_KEY):
            section_map = state.get(key)
            if isinstance(section_map, dict) and plugin_id in section_map:
                del section_map[plugin_id]
                state[key] = section_map
                changed = True
        if changed:
            save_state_file(state, path)
    return {"ok": True}


def _unlink_dir_link(link: Path) -> bool:
    """Remove the symlink itself, never what it points at."""
    try:
        os.unlink(link)
        return True
    except OSError:
        pass
    if os.name == "nt":
        # A Windows directory symlink is removed with rmdir, which removes the
        # link and leaves the target alone.
        try:
            os.rmdir(link)
            return True
        except OSError:
            return False
    return False


def _forget_plugin_files(plugin_id: str) -> None:
    for path in (_settings_path(plugin_id), _log_path(plugin_id)):
        try:
            path.unlink()
        except OSError:
            pass


def set_plugin_enabled(plugin_id: str, enabled: bool) -> dict[str, Any]:
    if not is_valid_plugin_id(plugin_id):
        return {"error": "invalid_plugin_id"}
    try:
        dest = resolve_inside_root(plugins_dir(), plugin_id)
    except OutsideRoot:
        return {"error": "invalid_plugin_id"}
    if not dest.is_dir():
        return {"error": "not_found"}
    section = _read_config_section()
    states = section.get("states")
    if not isinstance(states, dict):
        states = {}
    states[plugin_id] = bool(enabled)
    section["states"] = states
    _write_config_section(section)
    return {"ok": True, "enabled": bool(enabled)}


def set_plugins_enabled(enabled: bool) -> dict[str, Any]:
    """Flip the global master switch for all plugins."""
    section = _read_config_section()
    section["enabled"] = bool(enabled)
    _write_config_section(section)
    return {"ok": True, "plugins_enabled": bool(enabled)}


# --------------------------------------------------------------------------- #
# Plugin lookup shared by the page-facing RPCs
# --------------------------------------------------------------------------- #
def _existing_plugin(plugin_id: Any) -> Path | dict[str, Any]:
    """The plugin's directory (a link counts), or an error result."""
    if not is_valid_plugin_id(plugin_id):
        return {"error": "invalid_plugin_id"}
    try:
        dest = resolve_inside_root(plugins_dir(), plugin_id)
    except OutsideRoot:
        return {"error": "invalid_plugin_id"}
    if not dest.is_dir():
        return {"error": "not_found"}
    return dest


def _not_trusted(message: str) -> dict[str, Any]:
    return {"error": "not_trusted", "message": message}


def _usable_plugin(plugin_id: Any) -> tuple[Path, dict[str, Any]] | dict[str, Any]:
    """``(plugin_dir, manifest)`` when the plugin may serve a page right now:
    it exists, its manifest is valid, plugins are on, it is enabled, and the
    manifest it has *now* is the one that was trusted."""
    found = _existing_plugin(plugin_id)
    if isinstance(found, dict):
        return found
    try:
        raw = (found / _PLUGIN_JSON).read_bytes()
    except OSError:
        return _not_trusted("plugin.json is unreadable")
    # Parse and hash the same bytes, so what is checked is what was trusted.
    manifest, _ = _parse_manifest(raw)
    if manifest is None:
        return _not_trusted("the manifest is invalid")
    section = _read_config_section()
    if not _plugins_enabled(section):
        return _not_trusted("plugins are turned off on this machine")
    if not _is_enabled(plugin_id, section):
        return _not_trusted("the plugin is disabled")
    trust = read_state_file(_state_path()).get(_TRUST_KEY)
    if not isinstance(trust, dict) or trust.get(plugin_id) != _sha256(raw):
        return _not_trusted("the plugin's manifest is not trusted on this machine")
    return found, manifest


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_text_file(path: str) -> dict[str, Any]:
    """The shared success / error shape of ``plugin-file`` and
    ``plugin-data-read`` for an already-confined, resolved ``path``."""
    try:
        st = os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return {"error": "not_found"}
    except OSError as exc:
        return {"error": "read_failed", "message": exc.strerror or str(exc)}
    if not stat.S_ISREG(st.st_mode):
        return {"error": "not_a_file"}
    if st.st_size > _MAX_READ_BYTES:
        return {"error": "too_large"}
    # O_NOFOLLOW: the path was resolved already, so a link here means it was
    # swapped since. O_NONBLOCK: never hang on a FIFO swapped in either.
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_BINARY", 0)
    )
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return {"error": "not_found"}
    except OSError as exc:
        return {"error": "read_failed", "message": exc.strerror or str(exc)}
    with os.fdopen(fd, "rb") as fh:
        st = os.fstat(fh.fileno())
        if not stat.S_ISREG(st.st_mode):
            return {"error": "not_a_file"}
        data = fh.read(_MAX_READ_BYTES + 1)
    if len(data) > _MAX_READ_BYTES:
        return {"error": "too_large"}
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        return {"error": "not_utf8"}
    return {
        "ok": True,
        "content": content,
        "size": len(data),
        "mtime": st.st_mtime,
        "sha256": _sha256(data),
    }


def _is_inside(path: str, root: str) -> bool:
    return path.startswith(root.rstrip(os.sep) + os.sep)


def _as_posix(path: str) -> str:
    """Glob matching works on ``/``-separated paths (Windows uses ``\\``)."""
    return path if os.sep == "/" else path.replace(os.sep, "/")


# --------------------------------------------------------------------------- #
# Page-facing RPC handlers
# --------------------------------------------------------------------------- #
def plugin_file(plugin_id: str, path: str) -> dict[str, Any]:
    """Read a file the plugin ships, e.g. a page's HTML.

    ``path`` is relative to the plugin's directory (for a linked plugin, the
    link target). Anything that would leave that directory, through ``..``, an
    absolute path or a symlink, is ``invalid_path``.
    """
    usable = _usable_plugin(plugin_id)
    if isinstance(usable, dict):
        return usable
    plugin_dir, _ = usable
    if (
        not isinstance(path, str)
        or not path
        or "\x00" in path
        or "\\" in path
        or path.startswith("/")
        or os.path.isabs(path)
        or ".." in path.split("/")
    ):
        return {"error": "invalid_path"}
    root = os.path.realpath(plugin_dir)
    target = os.path.realpath(os.path.join(root, path))
    if not _is_inside(target, root):
        return {"error": "invalid_path"}
    return _read_text_file(target)


def plugin_data_read(plugin_id: str, path: str) -> dict[str, Any]:
    """Read a local file the manifest's ``files`` globs allow.

    ``path`` is absolute or ``~/``-relative. Both the normalized path and its
    realpath must fall under the declared globs, so a symlink inside an
    allowed tree that points somewhere else is ``not_allowed``.
    """
    usable = _usable_plugin(plugin_id)
    if isinstance(usable, dict):
        return usable
    _, manifest = usable
    if (
        not isinstance(path, str)
        or "\x00" in path
        or not (path.startswith("/") or path.startswith("~/"))
        or ".." in path.replace("\\", "/").split("/")
    ):
        return {"error": "invalid_path"}
    globs = [g for g in manifest.get("files") or [] if isinstance(g, str)]
    home = _home()
    normalized = os.path.normpath(_expand_home(path))
    real = os.path.realpath(normalized)
    # The resolved path is matched with the home directory resolved too, so a
    # symlinked home still matches its own ``~/`` globs.
    allowed = path_matches_any(
        _as_posix(normalized), globs, _as_posix(home)
    ) and path_matches_any(_as_posix(real), globs, _as_posix(os.path.realpath(home)))
    if (
        not allowed
        or _is_sensitive(real, os.path.realpath(home))
        or _is_sensitive(normalized, home)
    ):
        return {"error": "not_allowed"}
    return _read_text_file(real)


# Places under the home directory a plugin may never read, whatever its globs
# say: Vicoa's own state (the API key that acts as the user, trust grants) and
# the usual credential stores.
_SENSITIVE_HOME_PATHS: tuple[str, ...] = (
    ".vicoa",
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".kube",
    ".docker",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".git-credentials",
    ".config/gcloud",
    ".config/gh",
    ".claude",
    ".codex",
    "Library/Keychains",
)


def _is_sensitive(path: str, home: str) -> bool:
    # Compared case-insensitively: on a case-insensitive disk (the macOS
    # default) ``~/.VICOA`` is ``~/.vicoa``, and realpath keeps the case typed.
    folded = path.casefold()
    for rel in _SENSITIVE_HOME_PATHS:
        base = os.path.join(home, rel).casefold()
        if folded == base or _is_inside(folded, base):
            return True
    return False


def _settings_schema(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    schema = manifest.get("settings")
    return schema if isinstance(schema, dict) else {}


def _read_stored_settings(plugin_id: str) -> dict[str, Any]:
    try:
        data = json.loads(_settings_path(plugin_id).read_bytes())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _valid_stored(
    schema: dict[str, dict[str, Any]], stored: dict[str, Any]
) -> dict[str, Any]:
    """Stored values still valid machine-scope settings under ``schema``."""
    return {
        key: value
        for key, value in stored.items()
        if isinstance(schema.get(key), dict)
        and schema[key].get("scope") == "machine"
        and validate_setting_value(schema[key], value)
    }


def _machine_values(
    schema: dict[str, dict[str, Any]], stored: dict[str, Any]
) -> dict[str, Any]:
    """Every machine-scope key: its stored value, else its default."""
    values: dict[str, Any] = {}
    for key, spec in schema.items():
        if spec.get("scope") != "machine":
            continue
        values[key] = stored[key] if key in stored else copy.deepcopy(spec["default"])
    return values


def plugin_settings_get(plugin_id: str) -> dict[str, Any]:
    """The settings schema and this machine's values (defaults overlaid with
    what was saved). Device-scope keys are in ``schema`` but not ``values``:
    the app keeps those itself."""
    found = _existing_plugin(plugin_id)
    if isinstance(found, dict):
        return found
    manifest, _ = _load_manifest(found)
    if manifest is None:
        return {"error": "invalid_manifest"}
    schema = _settings_schema(manifest)
    stored = _valid_stored(schema, _read_stored_settings(plugin_id))
    return {"ok": True, "schema": schema, "values": _machine_values(schema, stored)}


def plugin_settings_set(plugin_id: str, values: dict[str, Any]) -> dict[str, Any]:
    """Merge ``values`` into this machine's saved settings.

    All or nothing: one unknown, device-scope or ill-typed key fails the call
    with ``{"error": "invalid_setting", "key": k}`` and nothing is written.
    """
    usable = _usable_plugin(plugin_id)
    if isinstance(usable, dict):
        return usable
    _, manifest = usable
    if not isinstance(values, dict):
        return {"error": "invalid_setting", "message": "values must be an object"}
    schema = _settings_schema(manifest)
    for key, value in values.items():
        spec = schema.get(key)
        if not isinstance(spec, dict):
            return {"error": "invalid_setting", "key": key, "message": "unknown key"}
        if spec.get("scope") != "machine":
            return {
                "error": "invalid_setting",
                "key": key,
                "message": "device-scope settings are kept by the app",
            }
        if not validate_setting_value(spec, value):
            return {
                "error": "invalid_setting",
                "key": key,
                "message": f"expected a {spec.get('type')}",
            }
    with _settings_lock:
        stored = _valid_stored(schema, _read_stored_settings(plugin_id))
        stored.update(values)
        encoded = json.dumps(stored, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > _MAX_SETTINGS_BYTES:
            return {"error": "too_large", "message": "settings exceed 64 KiB"}
        if not _atomic_write_bytes(_settings_path(plugin_id), encoded.encode("utf-8")):
            return {"error": "write_failed"}
    return {"ok": True, "values": _machine_values(schema, stored)}


def reload_plugin(plugin_id: str) -> dict[str, Any]:
    """Bump the plugin's reload counter. It is part of the catalog, so the
    catalog ETag changes and open clients reload the plugin."""
    found = _existing_plugin(plugin_id)
    if isinstance(found, dict):
        return found
    path = _state_path()
    with _state_lock:
        state = read_state_file(path)
        nonces = _reload_nonces(state)
        nonce = max(nonces.get(plugin_id, 0), 0) + 1
        nonces[plugin_id] = nonce
        state[_RELOAD_KEY] = nonces
        save_state_file(state, path)
    return {"ok": True, "reload_nonce": nonce}


def _one_line(text: str) -> str:
    """Line breaks and other control characters become spaces, so one entry is
    one line and nothing can drive the terminal that prints it."""
    flat = " ".join(text.splitlines())
    return "".join(
        " " if ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F else ch for ch in flat
    )


def _log_timestamp(at: Any) -> str:
    """``at`` as an ISO 8601 UTC timestamp: an ISO string, or a number of epoch
    milliseconds (JavaScript's ``Date.now()``). Anything else means now."""
    when: datetime | None = None
    if isinstance(at, (int, float)) and not isinstance(at, bool):
        if math.isfinite(at):
            try:
                when = datetime.fromtimestamp(at / 1000, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                when = None
    elif isinstance(at, str) and len(at) <= 64:
        try:
            when = datetime.fromisoformat(at.replace("Z", "+00:00"))
        except ValueError:
            when = None
        if when is not None and when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
    if when is None:
        when = datetime.now(timezone.utc)
    stamp = when.astimezone(timezone.utc).isoformat(timespec="milliseconds")
    return stamp.replace("+00:00", "Z")


def _format_log_entry(entry: Any) -> str | None:
    if not isinstance(entry, dict):
        return None
    level = entry.get("level")
    tag = _LOG_LEVELS.get(level.lower(), "INFO") if isinstance(level, str) else "INFO"
    message = entry.get("message")
    if not isinstance(message, str):
        try:
            message = json.dumps(message, default=str)
        except (TypeError, ValueError):
            message = str(message)
    text = _one_line(message)[:_MAX_LOG_MESSAGE]
    return f"{_log_timestamp(entry.get('at'))} {tag} {text}"


def _trim_log(path: Path) -> None:
    """Drop the oldest whole lines once the log outgrows its cap."""
    try:
        if path.stat().st_size <= _MAX_LOG_BYTES:
            return
        data = path.read_bytes()
    except OSError:
        return
    start = len(data) - _LOG_TRIM_TO_BYTES
    if start > 0 and data[start - 1 : start] != b"\n":
        newline = data.find(b"\n", start)
        start = len(data) if newline == -1 else newline + 1
    _atomic_write_bytes(path, data[max(start, 0) :])


def plugin_log(plugin_id: str, entries: list[Any]) -> dict[str, Any]:
    """Append up to 50 ``{level, message, at?}`` entries to the plugin's log,
    one ``"<iso ts> <LEVEL> <message>"`` line each."""
    found = _existing_plugin(plugin_id)
    if isinstance(found, dict):
        return found
    if not isinstance(entries, list):
        return {"error": "invalid_entries", "message": "entries must be an array"}
    lines = [
        line
        for line in (_format_log_entry(e) for e in entries[:_MAX_LOG_ENTRIES])
        if line is not None
    ]
    if not lines:
        return {"ok": True}
    path = _log_path(plugin_id)
    with _log_lock:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8", errors="replace") as fh:
                fh.write("".join(f"{line}\n" for line in lines))
        except OSError:
            return {"error": "write_failed"}
        _trim_log(path)
    return {"ok": True}


def plugin_logs_read(plugin_id: str, limit: int = _DEFAULT_LOG_LINES) -> dict[str, Any]:
    """The last ``limit`` log lines (default 200, at most 2000), oldest first."""
    found = _existing_plugin(plugin_id)
    if isinstance(found, dict):
        return found
    if not isinstance(limit, int) or isinstance(limit, bool):
        limit = _DEFAULT_LOG_LINES
    limit = max(0, min(limit, _MAX_LOG_LINES))
    try:
        text = _log_path(plugin_id).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return {"ok": True, "lines": []}
    except OSError as exc:
        return {"error": "read_failed", "message": exc.strerror or str(exc)}
    lines = text.splitlines()
    return {"ok": True, "lines": lines[-limit:] if limit else []}


# --------------------------------------------------------------------------- #
# Development: link a directory in place
# --------------------------------------------------------------------------- #
def link_plugin(path: str) -> dict[str, Any]:
    """Link a development directory as a plugin, without copying it.

    ``~/.vicoa/plugins/<id>`` becomes a symlink to the directory's realpath, so
    edits show up on the next reload. Runs no scripts. Linking the same
    directory again is a no-op (``already: True``); any other plugin already
    using the id is ``already_installed``.
    """
    if not isinstance(path, str) or not path.strip():
        return {"error": "invalid_path"}
    given = path.strip()
    src = Path(_expand_home(given))
    if not src.is_dir():
        return {"error": "not_a_directory"}
    target = Path(os.path.realpath(src))
    if not (target / _PLUGIN_JSON).is_file():
        return {"error": "manifest_not_found"}
    manifest, errors = _load_manifest(target)
    if manifest is None:
        return {"error": "invalid_manifest", "detail": "; ".join(errors)[:400]}
    pid = manifest["id"]
    root = plugins_dir()
    try:
        dest = resolve_inside_root(root, pid)
    except OutsideRoot:
        return {"error": "invalid_plugin_id"}
    if dest.is_symlink() or dest.exists():
        if dest.is_symlink() and os.path.realpath(dest) == str(target):
            if _read_provenance().get(pid, {}).get("kind") != "link":
                _write_provenance_entry(
                    pid,
                    {"source": given, "kind": "link", "installed_at": _utcnow_iso()},
                )
            return {"ok": True, "id": pid, "already": True, "target": str(target)}
        return {"error": "already_installed"}
    try:
        root.mkdir(parents=True, exist_ok=True)
        os.symlink(target, dest, target_is_directory=True)
    except OSError as exc:
        return {"error": "link_failed", "message": exc.strerror or str(exc)}
    _write_provenance_entry(
        pid, {"source": given, "kind": "link", "installed_at": _utcnow_iso()}
    )
    return {"ok": True, "id": pid, "target": str(target), "warnings": errors}
