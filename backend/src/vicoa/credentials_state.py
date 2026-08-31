"""Per-base-url access to the CLI credential file (``~/.vicoa/credentials.json``).

Historically this file held a single ``{"write_key": "<token>"}`` — one key per
machine, regardless of which deployment the machine pointed at. Logging into a
self-host then overwrote the cloud token in the same flat file, and because the
file was global the *prod* daemon would silently start using the self-host key.

The file now holds a ``keys`` map keyed by normalized base URL, so a machine can
hold one key per deployment (its "profile") side by side — the exact shape and
migration story as the sibling ``daemon_state.json`` (:mod:`vicoa.machine_state`).
Legacy flat files with a top-level ``write_key`` are auto-migrated to
``keys[<default-url>]`` the first time they're read, so upgrades never lose the
existing login.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from vicoa.constants import DEFAULT_API_URL
from vicoa.machine_state import normalize_base_url

CREDENTIALS_PATH = Path.home() / ".vicoa" / "credentials.json"

# The single per-entry field — kept as a module constant so callers don't
# sprinkle the magic string. Matches the legacy flat file's key name so the
# migration is a straight lift.
_WRITE_KEY = "write_key"


def read_credentials_file(path: Path = CREDENTIALS_PATH) -> dict[str, Any]:
    """Return the parsed credentials, or ``{}`` if missing/unreadable."""
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_credentials_file(state: dict[str, Any], path: Path = CREDENTIALS_PATH) -> None:
    """Persist credentials with owner-only permissions (0700 dir, 0600 file)."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def _get_keys_section(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the ``keys`` map, migrating from the legacy flat shape.

    Pre-multi-profile files held ``write_key`` at the top level. We treat that
    as the entry for the default API URL on first read so existing installs
    keep their login when they upgrade.
    """
    keys = state.get("keys")
    if isinstance(keys, dict):
        return {k: v for k, v in keys.items() if isinstance(v, dict)}

    legacy_token = state.get(_WRITE_KEY)
    if isinstance(legacy_token, str) and legacy_token:
        return {normalize_base_url(DEFAULT_API_URL): {_WRITE_KEY: legacy_token}}
    return {}


def _write_keys_section(
    state: dict[str, Any], keys: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Write ``keys`` back into ``state`` and strip the legacy flat key."""
    state["keys"] = keys
    state.pop(_WRITE_KEY, None)
    return state


def load_api_key(
    base_url: str | None = None, path: Path = CREDENTIALS_PATH
) -> str | None:
    """Return the stored write key for ``base_url``, or ``None``.

    Defaults to the canonical API URL so callers without a base_url still
    resolve the single entry on a normal install (matches
    :func:`vicoa.machine_state.read_machine_id`).
    """
    entry = _get_keys_section(read_credentials_file(path)).get(
        normalize_base_url(base_url), {}
    )
    token = entry.get(_WRITE_KEY)
    return token if isinstance(token, str) and token else None


def save_api_key(base_url: str | None, key: str, path: Path = CREDENTIALS_PATH) -> None:
    """Upsert the write key for ``base_url``. Rewrites a legacy flat file."""
    state = read_credentials_file(path)
    keys = _get_keys_section(state)
    keys[normalize_base_url(base_url)] = {_WRITE_KEY: key}
    save_credentials_file(_write_keys_section(state, keys), path)


def clear_api_key(base_url: str | None, path: Path = CREDENTIALS_PATH) -> None:
    """Drop the entry for ``base_url`` (for a future ``vicoa logout``)."""
    state = read_credentials_file(path)
    keys = _get_keys_section(state)
    if keys.pop(normalize_base_url(base_url), None) is None:
        return
    save_credentials_file(_write_keys_section(state, keys), path)
