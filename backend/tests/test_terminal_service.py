"""TerminalService spawn/write/read/kill roundtrip (desktop terminal tab).

Runs real PTYs against ``/bin/cat`` and short shell commands — Unix only,
like the service itself.
"""

import os
import re
import sys
import threading
import time
from pathlib import Path

import pytest

from vicoa.terminal.service import TerminalService, default_shell

pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"), reason="PTY sessions are Unix-only"
)


class _Collector:
    def __init__(self) -> None:
        self.output = bytearray()
        self.output_event = threading.Event()
        self.exits: list[tuple[str, int | None]] = []
        self.exit_event = threading.Event()

    def on_output(self, pty_id: str, data: bytes) -> None:
        self.output.extend(data)
        self.output_event.set()

    def on_exit(self, pty_id: str, exit_code: int | None) -> None:
        self.exits.append((pty_id, exit_code))
        self.exit_event.set()

    def wait_for_output(self, needle: bytes, timeout: float = 10.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if needle in bytes(self.output):
                return True
            time.sleep(0.05)
        return False


@pytest.fixture
def collector() -> _Collector:
    return _Collector()


@pytest.fixture
def service(collector: _Collector):
    svc = TerminalService(on_output=collector.on_output, on_exit=collector.on_exit)
    yield svc
    svc.shutdown()


def test_spawn_write_read_kill_roundtrip(
    service: TerminalService, collector: _Collector, tmp_path: Path
) -> None:
    pty_id = service.spawn(str(tmp_path), 80, 24, command=["/bin/cat"])
    assert pty_id in service.live_session_ids()

    service.write(pty_id, b"hello-pty\n")
    # cat echoes the line back (plus tty echo of the input itself).
    assert collector.wait_for_output(b"hello-pty")

    service.kill(pty_id)
    assert collector.exit_event.wait(timeout=10.0)
    assert collector.exits and collector.exits[0][0] == pty_id
    assert pty_id not in service.live_session_ids()


def test_child_exit_reports_pty_exit(
    service: TerminalService, collector: _Collector, tmp_path: Path
) -> None:
    pty_id = service.spawn(
        str(tmp_path), 80, 24, command=["/bin/sh", "-c", "echo done-marker"]
    )
    assert collector.wait_for_output(b"done-marker")
    assert collector.exit_event.wait(timeout=10.0)
    assert collector.exits[0][0] == pty_id
    assert collector.exits[0][1] == 0


def test_spawn_applies_cwd(
    service: TerminalService, collector: _Collector, tmp_path: Path
) -> None:
    marker = tmp_path / "cwd-marker-dir"
    marker.mkdir()
    service.spawn(str(marker), 80, 24, command=["/bin/sh", "-c", "pwd"])
    assert collector.wait_for_output(b"cwd-marker-dir")


def test_spawn_rejects_missing_cwd(service: TerminalService, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cwd does not exist"):
        service.spawn(str(tmp_path / "nope"), 80, 24)


def test_session_cap_enforced(collector: _Collector, tmp_path: Path) -> None:
    svc = TerminalService(
        on_output=collector.on_output, on_exit=collector.on_exit, max_sessions=1
    )
    try:
        svc.spawn(str(tmp_path), 80, 24, command=["/bin/cat"])
        with pytest.raises(RuntimeError, match="session limit"):
            svc.spawn(str(tmp_path), 80, 24, command=["/bin/cat"])
    finally:
        svc.shutdown()


def test_write_to_unknown_pty_raises_keyerror(service: TerminalService) -> None:
    with pytest.raises(KeyError):
        service.write("missing", b"x")


def test_kill_reaps_sighup_ignoring_child(
    service: TerminalService, collector: _Collector, tmp_path: Path
) -> None:
    """Killing a tab reaps processes started in it, not just the shell.

    Closing the PTY sends SIGHUP to the foreground group, which is enough for a
    plain child — but a real dev server often traps SIGHUP. Here the child
    ignores SIGHUP (``trap '' HUP`` is inherited across exec), so only the
    process-group SIGTERM/SIGKILL from ``PTYManager.close(kill_group=True)``
    tears it down; a bare signal to the shell would leak it.
    """
    pty_id = service.spawn(
        str(tmp_path),
        80,
        24,
        command=["/bin/sh", "-c", "trap '' HUP; sleep 300 & echo CHILD_PID:$!; wait"],
    )
    assert collector.wait_for_output(b"CHILD_PID:")
    match = re.search(rb"CHILD_PID:(\d+)", bytes(collector.output))
    assert match is not None, "shell did not report the background child pid"
    child_pid = int(match.group(1))
    os.kill(child_pid, 0)  # alive before the kill (raises if not)

    service.kill(pty_id)
    assert collector.exit_event.wait(timeout=10.0)

    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        os.kill(child_pid, 9)  # don't leak the process out of the test
        pytest.fail(f"SIGHUP-ignoring child {child_pid} survived the terminal kill")


def test_unleased_session_is_never_reaped(
    service: TerminalService, tmp_path: Path
) -> None:
    """A session spawned without a lease (older, non-heartbeating client) has no
    deadline, so a sweep leaves it alone — the reaper is purely additive."""
    pty_id = service.spawn(str(tmp_path), 80, 24, command=["/bin/cat"])
    assert service.reap_expired() == []
    assert pty_id in service.live_session_ids()


def test_expired_lease_is_reaped(
    service: TerminalService, collector: _Collector, tmp_path: Path
) -> None:
    """This is the leak fix: a leased pty whose client stopped heartbeating (a
    browser reload/crash that never sent pty-kill) gets killed on the sweep."""
    pty_id = service.spawn(str(tmp_path), 80, 24, command=["/bin/cat"], lease_secs=60)
    assert pty_id in service.live_session_ids()
    # Simulate the client going away: force the lease past its deadline.
    service._sessions[pty_id].lease_deadline = time.monotonic() - 1.0
    assert service.reap_expired() == [pty_id]
    assert collector.exit_event.wait(timeout=10.0)
    assert pty_id not in service.live_session_ids()


def test_renew_extends_the_lease(service: TerminalService, tmp_path: Path) -> None:
    pty_id = service.spawn(str(tmp_path), 80, 24, command=["/bin/cat"], lease_secs=60)
    service._sessions[pty_id].lease_deadline = time.monotonic() - 1.0  # would reap now
    assert service.renew_leases([pty_id]) == [pty_id]
    # Renewed into the future, so the sweep now spares it.
    assert service.reap_expired() == []
    assert pty_id in service.live_session_ids()


def test_renew_unknown_id_is_a_noop(service: TerminalService) -> None:
    assert service.renew_leases(["never-existed"]) == []


def test_reaper_thread_kills_orphaned_lease(
    collector: _Collector, tmp_path: Path
) -> None:
    """End-to-end: the background reaper thread (not a manual sweep) reaps a
    stale lease on its own timer."""
    svc = TerminalService(
        on_output=collector.on_output,
        on_exit=collector.on_exit,
        reaper_interval=0.05,
    )
    try:
        pty_id = svc.spawn(str(tmp_path), 80, 24, command=["/bin/cat"], lease_secs=60)
        svc._sessions[pty_id].lease_deadline = time.monotonic() - 1.0
        assert collector.exit_event.wait(timeout=5.0)
        assert pty_id not in svc.live_session_ids()
    finally:
        svc.shutdown()


def test_default_shell_falls_back_per_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SHELL", raising=False)
    expected = "/bin/zsh" if sys.platform == "darwin" else "/bin/bash"
    assert default_shell() == expected
    monkeypatch.setenv("SHELL", "/bin/fish")
    assert default_shell() == "/bin/fish"
