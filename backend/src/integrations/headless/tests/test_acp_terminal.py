"""ACP client-side terminal support.

Advertising ``clientCapabilities.terminal`` is what moves an agent's shell
commands into processes Vicoa owns. These tests pin the four properties that
make it worth doing: output is captured, the tail survives truncation, exit
status is reported, and nothing outlives the session.
"""

from __future__ import annotations

import os
import sys
import threading
import time

import pytest

from integrations.headless.acp_terminal import (
    DEFAULT_OUTPUT_BYTE_LIMIT,
    TerminalManager,
    TerminalNotFound,
)


@pytest.fixture
def manager(tmp_path):
    mgr = TerminalManager(default_cwd=str(tmp_path))
    yield mgr
    mgr.close_all()


def _python(manager: TerminalManager, code: str, **params) -> str:
    created = manager.create(
        {"command": sys.executable, "args": ["-c", code], **params}
    )
    return created["terminalId"]


def _wait_output(manager: TerminalManager, terminal_id: str) -> dict:
    manager.wait_for_exit({"terminalId": terminal_id})
    # The exit watcher and the output pump are separate threads; give the pump
    # a moment to drain the pipe it is still reading.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        snapshot = manager.output({"terminalId": terminal_id})
        if snapshot["output"]:
            return snapshot
        time.sleep(0.01)
    return manager.output({"terminalId": terminal_id})


def test_captures_stdout_and_stderr_and_reports_exit_code(manager) -> None:
    terminal_id = _python(
        manager,
        "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)",
    )

    exit_status = manager.wait_for_exit({"terminalId": terminal_id})
    snapshot = _wait_output(manager, terminal_id)

    assert exit_status == {"exitCode": 3, "signal": None}
    assert "out" in snapshot["output"]
    assert "err" in snapshot["output"]
    assert snapshot["truncated"] is False
    assert snapshot["exitStatus"] == {"exitCode": 3, "signal": None}


def test_truncation_keeps_the_tail(manager) -> None:
    """A build log's useful end must survive the cap, not its start."""
    terminal_id = _python(
        manager,
        "print('A' * 500); print('TAIL-MARKER')",
        outputByteLimit=64,
    )

    manager.wait_for_exit({"terminalId": terminal_id})
    snapshot = manager.output({"terminalId": terminal_id})
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not snapshot["truncated"]:
        time.sleep(0.01)
        snapshot = manager.output({"terminalId": terminal_id})

    assert snapshot["truncated"] is True
    assert len(snapshot["output"].encode("utf-8")) <= 64
    # The end of the stream survives; the 500 A's that preceded it do not.
    assert snapshot["output"].rstrip().endswith("TAIL-MARKER")
    assert "A" * 100 not in snapshot["output"]


def test_output_is_bounded_even_without_an_agent_limit(manager) -> None:
    """An agent that names no limit still gets a bounded buffer — the output
    is held in memory for the terminal's whole life."""
    terminal_id = _python(manager, "print('x')")
    manager.wait_for_exit({"terminalId": terminal_id})

    with manager._lock:
        terminal = manager._terminals[terminal_id]
    assert terminal.output_byte_limit == DEFAULT_OUTPUT_BYTE_LIMIT


def test_wait_for_exit_blocks_until_the_command_finishes(manager) -> None:
    terminal_id = _python(manager, "import time; time.sleep(0.4)")

    started = time.monotonic()
    exit_status = manager.wait_for_exit({"terminalId": terminal_id})

    assert exit_status["exitCode"] == 0
    assert time.monotonic() - started >= 0.3


def test_kill_stops_the_command_but_keeps_its_output_readable(manager) -> None:
    """The agent still wants to read what the command printed before it was
    stopped, so kill must not release the terminal."""
    terminal_id = _python(
        manager, "import time, sys; print('before'); sys.stdout.flush(); time.sleep(30)"
    )

    # Kill only once the command has actually printed — otherwise the test
    # races the interpreter's startup and proves nothing about the buffer.
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if "before" in manager.output({"terminalId": terminal_id})["output"]:
            break
        time.sleep(0.01)

    manager.kill({"terminalId": terminal_id})
    snapshot = _wait_output(manager, terminal_id)

    assert "before" in snapshot["output"]
    assert snapshot["exitStatus"]["signal"] == "SIGTERM"


def test_release_forgets_the_terminal(manager) -> None:
    terminal_id = _python(manager, "print('done')")
    manager.release({"terminalId": terminal_id})

    with pytest.raises(TerminalNotFound):
        manager.output({"terminalId": terminal_id})


def test_close_all_kills_a_command_the_agent_never_released(manager) -> None:
    """The backstop: a session that ends mid-command must not leave it running."""
    terminal_id = _python(manager, "import time; time.sleep(30)")
    with manager._lock:
        process = manager._terminals[terminal_id].process

    manager.close_all()

    assert process.wait(timeout=5) is not None
    assert process.poll() is not None


def test_unknown_terminal_id_is_rejected(manager) -> None:
    with pytest.raises(TerminalNotFound):
        manager.wait_for_exit({"terminalId": "term-999"})


def test_create_requires_a_command(manager) -> None:
    with pytest.raises(ValueError):
        manager.create({"args": ["-c", "print(1)"]})


def test_env_entries_are_applied(manager) -> None:
    terminal_id = _python(
        manager,
        "import os; print(os.environ['VICOA_TEST_VAR'])",
        env=[{"name": "VICOA_TEST_VAR", "value": "hello"}],
    )

    snapshot = _wait_output(manager, terminal_id)

    assert "hello" in snapshot["output"]


def test_concurrent_waiters_all_get_the_exit_status(manager) -> None:
    """wait_for_exit is answered on a per-request thread, so several may be
    outstanding at once — including alongside output polling."""
    terminal_id = _python(manager, "import time; time.sleep(0.2)")
    results: list[dict] = []

    def _wait() -> None:
        results.append(manager.wait_for_exit({"terminalId": terminal_id}))

    threads = [threading.Thread(target=_wait) for _ in range(3)]
    for thread in threads:
        thread.start()
    # Polling output while waiters are parked must not deadlock.
    manager.output({"terminalId": terminal_id})
    for thread in threads:
        thread.join(timeout=5)

    assert results == [{"exitCode": 0, "signal": None}] * 3


@pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups only")
def test_kill_reaches_the_whole_process_tree(manager, tmp_path) -> None:
    """Signalling only the leader leaves a forked server running after the
    session that started it is gone — the exact orphan this capability exists
    to prevent."""
    child_pid_file = tmp_path / "child.pid"
    terminal_id = _python(
        manager,
        (
            "import subprocess, sys, time, pathlib;"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']);"
            f"pathlib.Path({str(child_pid_file)!r}).write_text(str(child.pid));"
            "time.sleep(30)"
        ),
    )

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and not child_pid_file.exists():
        time.sleep(0.01)
    child_pid = int(child_pid_file.read_text())

    manager.kill({"terminalId": terminal_id})
    manager.wait_for_exit({"terminalId": terminal_id})

    # The grandchild must be gone too. It is not ours to reap, so poll for the
    # signal to land rather than asserting immediately.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except OSError:
            return
        time.sleep(0.01)
    pytest.fail(f"grandchild {child_pid} survived the terminal kill")
