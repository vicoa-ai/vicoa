"""Pure unit tests for the shared daemon-state reader (no DB, no network).

Covers plans/machine-management.md D8 — the wrapper/SDK reads the persisted
machine_id from ~/.vicoa/daemon_state.json so a session can be stamped with the
machine it runs on.
"""

from __future__ import annotations

import json
from pathlib import Path

from vicoa.machine_state import read_machine_id


def test_legacy_flat_state_migrates_to_default_url(tmp_path: Path) -> None:
    """A pre-multi-daemon state file with a top-level ``machine_id`` is
    treated as the entry for the default API URL — so a wrapper that has been
    upgraded keeps reading the same machine_id it had before."""
    state = tmp_path / "daemon_state.json"
    state.write_text(json.dumps({"machine_id": "mac-123", "daemon_pid": 9}))
    assert read_machine_id(state_path=state) == "mac-123"


def test_returns_per_base_url_machine_id(tmp_path: Path) -> None:
    """Multi-daemon shape: each base_url has its own machine_id entry."""
    state = tmp_path / "daemon_state.json"
    state.write_text(
        json.dumps(
            {
                "daemons": {
                    "https://agents.vicoa.ai": {"machine_id": "mac-prod"},
                    "http://localhost:8080": {"machine_id": "mac-local"},
                }
            }
        )
    )
    assert read_machine_id("https://agents.vicoa.ai", state) == "mac-prod"
    assert read_machine_id("http://localhost:8080", state) == "mac-local"
    # Unknown URL → no entry → None.
    assert read_machine_id("https://other.example", state) is None


def test_missing_file_returns_none(tmp_path: Path) -> None:
    assert read_machine_id(state_path=tmp_path / "does-not-exist.json") is None


def test_absent_machine_id_key_returns_none(tmp_path: Path) -> None:
    state = tmp_path / "daemon_state.json"
    state.write_text(json.dumps({"daemon_pid": 9}))
    assert read_machine_id(state_path=state) is None


def test_malformed_json_returns_none(tmp_path: Path) -> None:
    state = tmp_path / "daemon_state.json"
    state.write_text("{not json")
    assert read_machine_id(state_path=state) is None
