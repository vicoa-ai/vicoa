"""Headless session launch: one Popen for both spawn paths, Windows-safe.

Covers MachineDaemon._launch_session_process (shared by the app's
``spawn-session`` RPC and the queued spawn requests ``vicoa session start``
files), the Windows creation flags it passes, and how a Windows startup
failure (0xC0000142, reported by Popen as 3221225794) reads in the error each
path surfaces.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from vicoa import machine_daemon
from vicoa.machine_daemon import MachineDaemon, _describe_exit_code


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    return tmp_path


@pytest.fixture
def daemon(monkeypatch: pytest.MonkeyPatch) -> MachineDaemon:
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    monkeypatch.setattr(daemon, "send_heartbeat", lambda: None)
    monkeypatch.setattr(daemon, "_check_agent_installation", lambda agent: None)
    monkeypatch.setattr(daemon, "_build_headless_command", lambda **kw: ["agent"])
    return daemon


class _FakeProcess:
    pid = 4321

    def __init__(self, exit_code: int | None = None) -> None:
        self._exit_code = exit_code

    def poll(self) -> int | None:
        return self._exit_code

    def terminate(self) -> None:
        self._exit_code = -15


def _capture_popen(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_popen(command: list[str], **kw: Any) -> _FakeProcess:
        captured["command"] = command
        captured.update(kw)
        return _FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    return captured


# ----- exit code rendering -----


@pytest.mark.parametrize("code", [0, 1, 2, 255, -9, -15])
def test_ordinary_exit_codes_are_left_alone(code: int) -> None:
    assert _describe_exit_code(code) == str(code)


def test_dll_init_failed_is_rendered_in_hex_with_its_name() -> None:
    assert _describe_exit_code(3221225794) == (
        "0xC0000142 (STATUS_DLL_INIT_FAILED: Windows could not initialize the process)"
    )


def test_unknown_windows_status_is_still_hex() -> None:
    assert _describe_exit_code(0xC0000409) == "0xC0000409"


# ----- the shared launch -----


def test_launch_detaches_the_child(
    daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    captured = _capture_popen(monkeypatch)

    daemon._launch_session_process(
        ["agent"], cwd=str(tmp_path), env={"A": "1"}, session_id="s1"
    )

    assert captured["cwd"] == str(tmp_path)
    assert captured["env"] == {"A": "1"}
    assert captured["start_new_session"] is True
    assert captured["creationflags"] == 0
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stdout"] is subprocess.DEVNULL
    # stderr is the per-session log, and the daemon's copy is closed after.
    assert captured["stderr"].name == str(daemon._session_stderr_path("s1"))
    assert captured["stderr"].closed


@pytest.mark.parametrize(
    ("daemon_has_console", "expected_flags"),
    [
        # CLI-started daemon (DETACHED_PROCESS): each session gets a console of
        # its own, and without CREATE_NO_WINDOW that console gets a window,
        # which is where 0xC0000142 comes from.
        (False, 0x08000000),
        # Desktop-app daemon: sessions share its console, as they always did.
        (True, 0),
    ],
)
def test_launch_on_windows_hides_the_console_only_for_a_consoleless_daemon(
    daemon: MachineDaemon,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    daemon_has_console: bool,
    expected_flags: int,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(
        machine_daemon, "_attached_to_console", lambda: daemon_has_console
    )
    captured = _capture_popen(monkeypatch)

    daemon._launch_session_process(
        ["agent"], cwd=str(tmp_path), env={}, session_id="s1"
    )

    # Never CREATE_NEW_PROCESS_GROUP: it would disable Ctrl+C for the whole
    # session tree.
    assert captured["creationflags"] == expected_flags


def _fake_windll(get_console_process_list: Any) -> SimpleNamespace:
    return SimpleNamespace(
        kernel32=SimpleNamespace(GetConsoleProcessList=get_console_process_list)
    )


def _raise(*_: Any) -> int:
    raise OSError("probe failed")


@pytest.mark.parametrize(
    ("get_console_process_list", "expected"),
    [
        (lambda buf, size: 2, True),  # attached, alongside one other process
        (lambda buf, size: 0, False),  # no console: the call fails with 0
        (_raise, False),  # a broken probe falls back to hiding the window
    ],
)
def test_console_probe(
    monkeypatch: pytest.MonkeyPatch, get_console_process_list: Any, expected: bool
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        ctypes, "windll", _fake_windll(get_console_process_list), raising=False
    )
    assert machine_daemon._attached_to_console() is expected


def test_console_probe_is_windows_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert machine_daemon._attached_to_console() is False


# ----- both spawn paths go through it -----


def _stub_launch(
    daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch, process: _FakeProcess
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_launch(command: list[str], **kw: Any) -> _FakeProcess:
        calls.append({"command": command, **kw})
        return process

    monkeypatch.setattr(daemon, "_launch_session_process", fake_launch)
    return calls


def test_queued_spawn_request_reports_windows_failure_readably(
    daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _stub_launch(daemon, monkeypatch, _FakeProcess(exit_code=3221225794))
    reports: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        daemon,
        "report_request_status",
        lambda request_id, status, **kw: reports.append((status, kw)) or True,
    )

    daemon.process_request(
        {
            "request_id": "r1",
            "directory": str(tmp_path),
            "agent": "codex",
            "agent_instance_id": "s1",
        }
    )

    assert calls and calls[0]["session_id"] == "s1"
    assert calls[0]["cwd"] == str(tmp_path)
    assert reports == [
        (
            "error",
            {
                "message": "Headless process exited with code 0xC0000142 "
                "(STATUS_DLL_INIT_FAILED: Windows could not initialize the process)"
            },
        )
    ]


def test_spawn_session_rpc_uses_the_shared_launch(
    daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _stub_launch(daemon, monkeypatch, _FakeProcess())
    monkeypatch.setattr(daemon, "_monitor_session_process", lambda **kw: None)
    monkeypatch.setattr(
        daemon, "_wait_for_registration", lambda session_id, process, **kw: None
    )

    result = daemon.spawn_session_rpc(
        {"params": {"directory": str(tmp_path), "agent": "codex"}}
    )

    assert "error" not in result
    assert calls and calls[0]["session_id"] == result["agent_instance_id"]
    assert calls[0]["cwd"] == str(tmp_path)


def test_rpc_wait_surfaces_the_windows_status_instead_of_try_again(
    daemon: MachineDaemon,
) -> None:
    # The child died before running a line, so its stderr log is empty.
    failure = daemon._wait_for_registration(
        "s1",
        _FakeProcess(exit_code=3221225794),  # type: ignore[arg-type]
        timeout=2.0,
    )
    assert failure == (
        "Couldn't start the session: the agent exited with 0xC0000142 "
        "(STATUS_DLL_INIT_FAILED: Windows could not initialize the process)"
    )
