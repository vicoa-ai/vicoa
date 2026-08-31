"""Pure unit tests for the per-base-url credential store (no DB, no network).

Mirrors ``test_machine_state.py``: the credential file now holds one key per
normalized base URL (its "profile"), so a self-host login can't clobber the
cloud token, while a legacy single-key file still migrates transparently.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

from vicoa.constants import DEFAULT_API_URL
from vicoa.credentials_state import (
    clear_api_key,
    load_api_key,
    save_api_key,
)
from vicoa.machine_state import normalize_base_url

DEFAULT_KEY = normalize_base_url(DEFAULT_API_URL)


def test_legacy_flat_file_migrates_to_default_url(tmp_path: Path) -> None:
    """A pre-multi-profile ``{"write_key": ...}`` file is read as the entry for
    the default deployment, so an upgraded install keeps its login."""
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"write_key": "legacy-token"}))
    assert load_api_key(DEFAULT_API_URL, path) == "legacy-token"
    # A None base_url resolves the same default entry.
    assert load_api_key(None, path) == "legacy-token"


def test_per_base_url_isolation(tmp_path: Path) -> None:
    """Saving under one deployment never disturbs another's key."""
    path = tmp_path / "credentials.json"
    save_api_key("https://agents.vicoa.ai", "cloud-key", path)
    save_api_key("http://localhost:8080", "self-host-key", path)

    assert load_api_key("https://agents.vicoa.ai", path) == "cloud-key"
    assert load_api_key("http://localhost:8080", path) == "self-host-key"
    # Unknown deployment → no entry.
    assert load_api_key("https://other.example", path) is None


def test_url_normalization_matches_daemon_state(tmp_path: Path) -> None:
    """Trailing slash / case differences resolve to the same entry (same
    ``normalize_base_url`` the daemon keys its state by)."""
    path = tmp_path / "credentials.json"
    save_api_key("https://Agents.Vicoa.AI/", "k", path)
    assert load_api_key("https://agents.vicoa.ai", path) == "k"


def test_missing_and_malformed_files_return_none(tmp_path: Path) -> None:
    assert load_api_key("https://x", tmp_path / "nope.json") is None
    bad = tmp_path / "credentials.json"
    bad.write_text("{not json")
    assert load_api_key("https://x", bad) is None


def test_save_rewrites_legacy_file_without_losing_the_token(tmp_path: Path) -> None:
    """Writing a new deployment's key upgrades a legacy flat file to the map
    shape while preserving the original token under the default URL."""
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"write_key": "legacy-token"}))

    save_api_key("http://localhost:8080", "self-host-key", path)

    data = json.loads(path.read_text())
    assert "write_key" not in data  # legacy top-level key stripped
    assert data["keys"][DEFAULT_KEY]["write_key"] == "legacy-token"
    assert (
        data["keys"][normalize_base_url("http://localhost:8080")]["write_key"]
        == "self-host-key"
    )


def test_saved_file_is_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    save_api_key(DEFAULT_API_URL, "k", path)
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_clear_api_key_removes_only_that_entry(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    save_api_key("https://agents.vicoa.ai", "cloud-key", path)
    save_api_key("http://localhost:8080", "self-host-key", path)

    clear_api_key("http://localhost:8080", path)

    assert load_api_key("http://localhost:8080", path) is None
    assert load_api_key("https://agents.vicoa.ai", path) == "cloud-key"
