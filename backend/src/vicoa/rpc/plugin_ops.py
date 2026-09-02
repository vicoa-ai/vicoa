"""Daemon RPC handlers for the plugin system: scan / catalog / install / remove
/ enable / trust.

Plugins live on disk under ``~/.vicoa/plugins/<id>/``, each a directory holding
a ``plugin.json`` (Tier 1 manifest) and optionally a ``dist/`` bundle (Tier 2,
read only on the desktop renderer — never executed here). This module owns the
*management* surface; the renderer reads the result through ``plugin-catalog``.

Mirrors the conventions of ``skills_ops`` (git clone / dir copy into place, a
hidden ``.vicoa-plugins.json`` provenance manifest, size/count guardrails, and —
crucially — **no install scripts are ever run**). Enable state lives in
``~/.vicoa/config.json`` under a ``plugins`` section; per-plugin trust lives in
``~/.vicoa/daemon_state.json`` keyed by the manifest's SHA-256, mirroring
``worktree_trust`` (editing a plugin's manifest re-arms the trust prompt).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from protocol.plugin_manifest import (
    PLUGIN_API_VERSION,
    compute_catalog_etag,
    is_valid_plugin_id,
    validate_manifest,
)
from vicoa.machine_state import read_state_file, save_state_file
from vicoa.rpc.paths import OutsideRoot, resolve_inside_root

_MANIFEST_NAME = ".vicoa-plugins.json"
_PLUGIN_JSON = "plugin.json"

# Guardrails on an installed plugin tree (excluding .git). Mirrors skills_ops.
_MAX_FILE_BYTES = 2 * 1024 * 1024
_MAX_TOTAL_BYTES = 25 * 1024 * 1024
_MAX_FILE_COUNT = 1024
_CLONE_TIMEOUT_S = 25  # must fit the WS RPC budget (~30s)

_GIT_URL_SCHEMES = ("https://", "http://", "git://", "ssh://", "file://", "git@")

# daemon_state.json key: {plugin_id: manifest_sha256}. Trust is a property of the
# machine, never synced to another device (same boundary as worktree_trust).
_TRUST_KEY = "plugin_trust"

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


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".vicoa-tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


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
    plugin_id: str, state_path: Path | None = None
) -> dict[str, Any]:
    """Persist a trust grant for the plugin's *current* manifest hash."""
    if not is_valid_plugin_id(plugin_id):
        return {"error": "invalid_plugin_id"}
    try:
        dest = resolve_inside_root(plugins_dir(), plugin_id)
    except OutsideRoot:
        return {"error": "invalid_plugin_id"}
    current = _manifest_hash(dest)
    if current is None:
        return {"error": "not_found"}
    path = state_path or _state_path()
    state = read_state_file(path)
    trust = state.get(_TRUST_KEY)
    if not isinstance(trust, dict):
        trust = {}
    trust[plugin_id] = current
    state[_TRUST_KEY] = trust
    save_state_file(state, path)
    return {"ok": True}


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


def _load_manifest(plugin_path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        raw = json.loads((plugin_path / _PLUGIN_JSON).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"plugin.json unreadable: {exc}"]
    return validate_manifest(raw)


def _has_client_bundle(plugin_path: Path) -> bool:
    return (plugin_path / "dist" / "client.js").is_file()


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #
def _scan() -> list[dict[str, Any]]:
    """Every installed plugin, with its validated manifest and metadata.

    Malformed plugins are included with ``manifest=None`` + ``errors`` so the
    management UI can surface them; the catalog filters them out.
    """
    root = plugins_dir()
    provenance = _read_provenance()
    out: list[dict[str, Any]] = []
    if not root.is_dir():
        return out
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.name.startswith("."):
            continue
        manifest, errors = _load_manifest(child)
        prov = provenance.get(child.name, {})
        entry: dict[str, Any] = {
            "dir": child.name,
            "path": str(child),
            "manifest": manifest,
            "errors": errors,
            "source": prov.get("source"),
            "installed_at": prov.get("installed_at"),
        }
        if manifest is not None:
            manifest["hasClientBundle"] = _has_client_bundle(child)
        out.append(entry)
    return out


# --------------------------------------------------------------------------- #
# RPC handlers
# --------------------------------------------------------------------------- #
def plugin_catalog(etag: str | None = None) -> dict[str, Any]:
    """The renderer-facing catalog: valid, id-keyed plugins with enable/trust
    flags. Returns ``{etag, not_modified: True}`` when the caller's ETag matches.
    """
    section = _read_config_section()
    plugins_on = _plugins_enabled(section)
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
        plugin_path = plugins_dir() / dir_name
        plugins.append(
            {
                "id": pid,
                "dir": dir_name,
                "manifest": manifest,
                "enabled": _is_enabled(dir_name, section),
                "trusted": is_plugin_trusted(dir_name, plugin_path),
                "server_available": False,  # Tier 2 subprocess arrives in P3
                "source": entry["source"],
                "api_compatible": manifest["apiVersion"] <= PLUGIN_API_VERSION,
            }
        )
    payload: dict[str, Any] = {"plugins_enabled": plugins_on, "plugins": plugins}
    computed = compute_catalog_etag(payload)
    if etag is not None and etag == computed:
        return {"etag": computed, "not_modified": True}
    payload["etag"] = computed
    return payload


def plugin_list() -> dict[str, Any]:
    """Fuller listing (including malformed plugins + errors) for CLI / settings."""
    section = _read_config_section()
    out: list[dict[str, Any]] = []
    for entry in _scan():
        manifest = entry["manifest"]
        dir_name = entry["dir"]
        plugin_path = plugins_dir() / dir_name
        out.append(
            {
                "id": manifest["id"] if manifest else dir_name,
                "dir": dir_name,
                "name": (manifest.get("name") if manifest else None) or dir_name,
                "valid": manifest is not None,
                "errors": entry["errors"],
                "enabled": _is_enabled(dir_name, section),
                "trusted": is_plugin_trusted(dir_name, plugin_path)
                if manifest
                else False,
                "source": entry["source"],
                "installed_at": entry["installed_at"],
                "path": entry["path"],
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

        if dest.exists():
            if not overwrite:
                return {"error": "plugin_exists"}
            shutil.rmtree(dest)

        root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".git"))

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
    """Delete an installed plugin and forget its enable/trust/provenance state."""
    if not is_valid_plugin_id(plugin_id):
        return {"error": "invalid_plugin_id"}
    try:
        dest = resolve_inside_root(plugins_dir(), plugin_id)
    except OutsideRoot:
        return {"error": "invalid_plugin_id"}
    if not dest.is_dir():
        return {"error": "not_found"}
    shutil.rmtree(dest, ignore_errors=True)
    _drop_provenance_entry(plugin_id)

    # Forget enable state.
    section = _read_config_section()
    states = section.get("states")
    if isinstance(states, dict) and plugin_id in states:
        del states[plugin_id]
        section["states"] = states
        _write_config_section(section)

    # Forget trust.
    path = _state_path()
    state = read_state_file(path)
    trust = state.get(_TRUST_KEY)
    if isinstance(trust, dict) and plugin_id in trust:
        del trust[plugin_id]
        state[_TRUST_KEY] = trust
        save_state_file(state, path)
    return {"ok": True}


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
