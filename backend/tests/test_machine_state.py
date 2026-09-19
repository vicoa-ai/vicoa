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


# --- wait_for_machine_id: the first-run race with an autostarted daemon ---

import os  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

from vicoa.machine_state import (  # noqa: E402
    daemon_registration_pending,
    update_daemon_entry,
    wait_for_machine_id,
)

URL = "https://agents.vicoa.ai"


def _write(state: Path, entry: dict) -> None:
    state.write_text(json.dumps({"daemons": {URL: entry}}))


def test_no_state_file_does_not_wait(tmp_path: Path) -> None:
    """Standalone wrapper (no daemon ever) → None at once, no 3 s stall."""
    state = tmp_path / "daemon_state.json"
    started = time.monotonic()
    assert wait_for_machine_id(URL, timeout=2.0, state_path=state) is None
    assert time.monotonic() - started < 0.5
    assert daemon_registration_pending(URL, state_path=state) is False


def test_registered_daemon_returns_machine_id_immediately(tmp_path: Path) -> None:
    state = tmp_path / "daemon_state.json"
    _write(state, {"daemon_pid": os.getpid(), "machine_id": "mac-1"})
    assert wait_for_machine_id(URL, timeout=2.0, state_path=state) == "mac-1"
    assert daemon_registration_pending(URL, state_path=state) is False


def test_pid_without_machine_id_is_pending(tmp_path: Path) -> None:
    """`ensure_background_daemon_running` stamps the pid before the daemon's
    /machines/register lands — that window is the pending state."""
    state = tmp_path / "daemon_state.json"
    _write(state, {"daemon_pid": os.getpid()})
    assert daemon_registration_pending(URL, state_path=state) is True


def test_waits_for_registration_then_returns(tmp_path: Path) -> None:
    """Daemon is mid-registration: the wait picks up the machine_id as soon as
    it lands, well before the timeout."""
    state = tmp_path / "daemon_state.json"
    _write(state, {"daemon_pid": os.getpid()})

    def _register_later() -> None:
        time.sleep(0.3)
        update_daemon_entry(URL, {"machine_id": "mac-late"}, state)

    threading.Thread(target=_register_later, daemon=True).start()
    started = time.monotonic()
    assert wait_for_machine_id(URL, timeout=3.0, state_path=state) == "mac-late"
    elapsed = time.monotonic() - started
    assert 0.25 <= elapsed < 1.5


def test_gives_up_at_timeout(tmp_path: Path) -> None:
    """A daemon that never registers (dead key, no network) costs one bounded
    wait, then the session proceeds unlinked."""
    state = tmp_path / "daemon_state.json"
    _write(state, {"daemon_pid": os.getpid()})
    started = time.monotonic()
    assert wait_for_machine_id(URL, timeout=0.3, state_path=state) is None
    assert 0.25 <= time.monotonic() - started < 1.0


def test_dead_pid_is_not_pending(tmp_path: Path, monkeypatch) -> None:
    """A stale pid from a crashed daemon must not make every wrapper wait."""
    state = tmp_path / "daemon_state.json"
    _write(state, {"daemon_pid": 2**22 + 12345})
    monkeypatch.setattr("vicoa.machine_state._pid_alive", lambda _pid: False)
    started = time.monotonic()
    assert wait_for_machine_id(URL, timeout=2.0, state_path=state) is None
    assert time.monotonic() - started < 0.5


def test_other_base_url_entry_does_not_count(tmp_path: Path) -> None:
    """Pending is per base_url: a prod daemon registering doesn't stall a
    wrapper pointed at a dev backend."""
    state = tmp_path / "daemon_state.json"
    _write(state, {"daemon_pid": os.getpid()})
    assert (
        daemon_registration_pending("http://localhost:8000", state_path=state) is False
    )
