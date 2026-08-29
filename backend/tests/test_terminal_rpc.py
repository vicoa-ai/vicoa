"""Shared pty-* dispatch (vicoa.terminal.rpc) used by both the local server and
the cloud daemon. The contract both callers rely on: pty methods return a dict,
non-pty methods return None (so the caller falls through to its own handlers).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from vicoa.terminal.rpc import PTY_RPC_METHODS, handle_pty_rpc
from vicoa.terminal.service import TerminalService

pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"), reason="PTY sessions are Unix-only"
)


def test_non_pty_method_returns_none() -> None:
    service = TerminalService()
    assert handle_pty_rpc(service, "git-status", {"cwd": "/"}) is None
    assert handle_pty_rpc(service, "spawn-session", {}) is None


def test_pty_methods_are_the_advertised_set() -> None:
    assert set(PTY_RPC_METHODS) == {
        "pty-spawn",
        "pty-write",
        "pty-resize",
        "pty-kill",
        "pty-heartbeat",
    }


def test_spawn_write_kill_roundtrip(tmp_path: Path) -> None:
    service = TerminalService()
    try:
        spawn = handle_pty_rpc(
            service,
            "pty-spawn",
            {"cwd": str(tmp_path), "cols": 80, "rows": 24, "command": ["/bin/cat"]},
        )
        assert spawn is not None
        pty_id = spawn["pty_id"]
        assert pty_id in service.live_session_ids()
        # Advertises ordered input so the client may pipeline keystrokes.
        assert spawn["ordered_input"] is True

        assert (
            handle_pty_rpc(service, "pty-write", {"pty_id": pty_id, "data": "aGk="})
            == {}
        )
        assert (
            handle_pty_rpc(
                service, "pty-resize", {"pty_id": pty_id, "cols": 100, "rows": 40}
            )
            == {}
        )
        assert handle_pty_rpc(service, "pty-kill", {"pty_id": pty_id}) == {}
    finally:
        service.shutdown()


def test_bad_base64_is_a_clean_error(tmp_path: Path) -> None:
    service = TerminalService()
    try:
        spawn = handle_pty_rpc(
            service,
            "pty-spawn",
            {"cwd": str(tmp_path), "command": ["/bin/cat"]},
        )
        assert spawn is not None
        result = handle_pty_rpc(
            service, "pty-write", {"pty_id": spawn["pty_id"], "data": "not base64!!"}
        )
        assert result is not None and "error" in result
    finally:
        service.shutdown()


def test_spawn_missing_cwd_is_an_error() -> None:
    service = TerminalService()
    result = handle_pty_rpc(service, "pty-spawn", {})
    assert result == {"error": "pty-spawn requires a cwd"}


def test_write_to_unknown_pty_is_a_clean_error() -> None:
    service = TerminalService()
    result = handle_pty_rpc(service, "pty-write", {"pty_id": "missing", "data": "aGk="})
    assert result is not None and "unknown pty_id" in result["error"]


def test_heartbeat_renews_leased_session(tmp_path: Path) -> None:
    service = TerminalService()
    try:
        spawn = handle_pty_rpc(
            service,
            "pty-spawn",
            {"cwd": str(tmp_path), "command": ["/bin/cat"], "lease_secs": 60},
        )
        assert spawn is not None
        pty_id = spawn["pty_id"]
        # Only the live, leased id is echoed back; an unknown id is dropped.
        result = handle_pty_rpc(
            service,
            "pty-heartbeat",
            {"pty_ids": [pty_id, "stale-id"], "lease_secs": 60},
        )
        assert result == {"renewed": [pty_id]}
    finally:
        service.shutdown()


def test_heartbeat_requires_a_pty_ids_list() -> None:
    service = TerminalService()
    result = handle_pty_rpc(service, "pty-heartbeat", {"pty_ids": "nope"})
    assert result is not None and "error" in result
