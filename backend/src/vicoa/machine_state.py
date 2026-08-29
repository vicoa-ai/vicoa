"""Shared access to the daemon state file (``~/.vicoa/daemon_state.json``).

The machine daemon persists its ``machine_id`` and ``daemon_pid`` here at
registration. Both the daemon and the SDK read from this single source so a
wrapper can stamp the session it creates with the machine it runs on, with no
env var and no second source of truth (machine-management D8).

The file holds a ``daemons`` map keyed by normalized base URL so multiple
daemons can run side-by-side (e.g. one against prod and one against a staging
backend). Legacy state files with top-level ``daemon_pid``/``machine_id`` are
auto-migrated to ``daemons[<default-url>]`` the first time they're read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vicoa.constants import DEFAULT_API_URL

STATE_PATH = Path.home() / ".vicoa" / "daemon_state.json"

# Per-base-url entry keys — kept as module constants so callers don't sprinkle
# magic strings.
_PID_KEY = "daemon_pid"
_MACHINE_ID_KEY = "machine_id"
_DISPLAY_NAME_KEY = "display_name"


def normalize_base_url(url: str | None) -> str:
    """Canonical key used to look up a daemon entry by its ``--base-url``.

    Strips trailing slashes and lowercases the scheme + host so
    ``https://Agents.Vicoa.AI/`` and ``https://agents.vicoa.ai`` resolve to the
    same daemon. Falls back to the default API URL when the caller passes
    ``None`` so SDK callers that don't know which base_url they're running
    against still hit the only entry that exists on most machines.
    """
    raw = (url or DEFAULT_API_URL).strip()
    return raw.rstrip("/").lower()


def read_state_file(state_path: Path = STATE_PATH) -> dict[str, Any]:
    """Return the parsed daemon state, or ``{}`` if missing/unreadable."""
    if not state_path.exists():
        return {}
    try:
        with state_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state_file(state: dict[str, Any], state_path: Path = STATE_PATH) -> None:
    """Persist daemon state. Creates the parent dir on first write."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


def _get_daemons_section(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the ``daemons`` map, migrating from the legacy flat shape.

    Pre-multi-daemon state files held ``daemon_pid`` / ``machine_id`` /
    ``display_name`` at the top level. We treat that as the entry for the
    default API URL on first read so existing installs don't lose their
    machine registration when they upgrade.
    """
    daemons = state.get("daemons")
    if isinstance(daemons, dict):
        return {k: v for k, v in daemons.items() if isinstance(v, dict)}

    legacy_entry: dict[str, Any] = {}
    legacy_pid = state.get(_PID_KEY)
    if isinstance(legacy_pid, int):
        legacy_entry[_PID_KEY] = legacy_pid
    legacy_machine_id = state.get(_MACHINE_ID_KEY)
    if isinstance(legacy_machine_id, str) and legacy_machine_id:
        legacy_entry[_MACHINE_ID_KEY] = legacy_machine_id
    legacy_display = state.get(_DISPLAY_NAME_KEY)
    if isinstance(legacy_display, str) and legacy_display:
        legacy_entry[_DISPLAY_NAME_KEY] = legacy_display

    if legacy_entry:
        return {normalize_base_url(DEFAULT_API_URL): legacy_entry}
    return {}


def _write_daemons_section(
    state: dict[str, Any], daemons: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Write ``daemons`` back into ``state`` and strip the legacy flat keys."""
    state["daemons"] = daemons
    state.pop(_PID_KEY, None)
    state.pop(_MACHINE_ID_KEY, None)
    state.pop(_DISPLAY_NAME_KEY, None)
    return state


def list_daemon_entries(
    state_path: Path = STATE_PATH,
) -> dict[str, dict[str, Any]]:
    """Return ``{normalized_base_url: entry}`` for every persisted daemon."""
    return _get_daemons_section(read_state_file(state_path))


def read_daemon_entry(
    base_url: str | None, state_path: Path = STATE_PATH
) -> dict[str, Any]:
    """Return the entry for ``base_url`` (empty dict if absent)."""
    return list_daemon_entries(state_path).get(normalize_base_url(base_url), {})


def write_daemon_entry(
    base_url: str | None,
    entry: dict[str, Any],
    state_path: Path = STATE_PATH,
) -> None:
    """Upsert the entry for ``base_url``. Pass an empty dict to clear it."""
    state = read_state_file(state_path)
    daemons = _get_daemons_section(state)
    key = normalize_base_url(base_url)
    if entry:
        daemons[key] = entry
    else:
        daemons.pop(key, None)
    save_state_file(_write_daemons_section(state, daemons), state_path)


def update_daemon_entry(
    base_url: str | None,
    updates: dict[str, Any],
    state_path: Path = STATE_PATH,
) -> dict[str, Any]:
    """Merge ``updates`` into the entry for ``base_url`` and persist.

    Keys mapped to ``None`` are removed from the entry; everything else is
    upserted. Returns the resulting entry so callers can keep it in memory
    without a second read.
    """
    state = read_state_file(state_path)
    daemons = _get_daemons_section(state)
    key = normalize_base_url(base_url)
    entry = dict(daemons.get(key, {}))
    for field, value in updates.items():
        if value is None:
            entry.pop(field, None)
        else:
            entry[field] = value
    if entry:
        daemons[key] = entry
    else:
        daemons.pop(key, None)
    save_state_file(_write_daemons_section(state, daemons), state_path)
    return entry


def clear_daemon_pid(base_url: str | None, state_path: Path = STATE_PATH) -> None:
    """Drop the ``daemon_pid`` field for ``base_url`` (machine_id stays)."""
    update_daemon_entry(base_url, {_PID_KEY: None}, state_path)


def read_machine_id(
    base_url: str | None = None, state_path: Path = STATE_PATH
) -> str | None:
    """Return the persisted ``machine_id`` for ``base_url``, or ``None``.

    Defaults to the canonical API URL so legacy callers without a base_url
    still resolve the single entry on a normal install. Never raises: a
    missing file, malformed JSON, or an absent/blank ``machine_id`` all yield
    ``None`` so a wrapper falls back to an unlinked session rather than
    failing to start.
    """
    entry = read_daemon_entry(base_url, state_path)
    machine_id = entry.get(_MACHINE_ID_KEY)
    return machine_id if isinstance(machine_id, str) and machine_id else None
