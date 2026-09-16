"""A tty that stops draining must not wedge the daemon's pty writer.

``pty-write`` runs on ONE ordered worker shared by every terminal on the
machine, so an unbounded retry on a full input queue freezes input for all of
them — the shape of the "worktree setup hangs" bug. The write is bounded
instead: partial writes still complete, a permanently full queue times out.
"""

import errno
import os
from typing import Any

import pytest
from vicoa.terminal.pty_manager import PTYManager
from vicoa.terminal.rpc import handle_pty_rpc


def _manager() -> PTYManager:
    manager = PTYManager(log_func=lambda _msg: None)
    manager.master_fd = 999  # never written to — os.write is patched per test
    return manager


def test_partial_writes_are_resumed_until_everything_lands(monkeypatch: Any) -> None:
    written = bytearray()

    def fake_write(fd: int, data: memoryview) -> int:
        chunk = bytes(data[:7])  # a stingy tty: 7 bytes at a time
        written.extend(chunk)
        return len(chunk)

    monkeypatch.setattr(os, "write", fake_write)
    _manager().write_to_pty(b"echo hello world" * 4)
    assert bytes(written) == b"echo hello world" * 4


def test_a_tty_that_never_drains_gives_up_instead_of_spinning(monkeypatch: Any) -> None:
    accepted = 32

    def fake_write(fd: int, data: memoryview) -> int:
        nonlocal accepted
        if accepted <= 0:
            raise BlockingIOError(errno.EAGAIN, "resource temporarily unavailable")
        taken = min(accepted, len(data))
        accepted -= taken
        return taken

    monkeypatch.setattr(os, "write", fake_write)
    with pytest.raises(TimeoutError) as excinfo:
        _manager().write_to_pty(b"x" * 128, timeout=0.05)
    # The message names what got through, so a daemon log says how much was lost.
    assert "32/128" in str(excinfo.value)


def test_a_stalled_write_is_reported_as_an_rpc_error(monkeypatch: Any) -> None:
    class StalledTerminal:
        def write(self, pty_id: str, data: bytes) -> None:
            raise TimeoutError("pty write stalled: 0/128 bytes accepted in 5s")

    result = handle_pty_rpc(
        StalledTerminal(),  # type: ignore[arg-type]
        "pty-write",
        {"pty_id": "p1", "data": "eA=="},
    )
    assert result is not None and "pty write stalled" in str(result.get("error"))
