"""The OpenCode CLI is found where its own installer puts it.

`curl -fsSL https://opencode.ai/install | bash` writes ~/.opencode/bin/opencode
and appends that dir to the user's shell rc — neither of which reaches a daemon
that is already running, or one whose PATH came from a shell started before the
install. Without the extra location, OpenCode reads as "not installed" on a
machine where `which opencode` works.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from vicoa.machine_daemon import MachineDaemon, _find_opencode_cli


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Sandbox `Path.home()`, `$HOME` and PATH so only what we place is found."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.delenv("NVM_BIN", raising=False)
    monkeypatch.delenv("NPM_CONFIG_PREFIX", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def _install_script_layout(home: Path) -> Path:
    """What the opencode install script leaves behind."""
    binary = home / ".opencode" / "bin" / "opencode"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    return binary


def test_finds_the_installer_placed_binary_off_path(fake_home: Path) -> None:
    binary = _install_script_layout(fake_home)
    assert _find_opencode_cli() == str(binary)


def test_none_when_nothing_is_installed(fake_home: Path) -> None:
    assert _find_opencode_cli() is None


def test_detection_reports_opencode_installed(fake_home: Path) -> None:
    _install_script_layout(fake_home)
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    assert daemon._check_agent_installation("opencode") is None


def test_spawn_passes_the_resolved_path_not_the_bare_name(fake_home: Path) -> None:
    # The child inherits the daemon's PATH, which is the one that could not find
    # the binary — so the command has to carry the absolute path.
    binary = _install_script_layout(fake_home)
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    cmd = daemon._build_headless_command(
        directory=os.getcwd(), agent="opencode", session_id=None, metadata=None
    )
    assert "--opencode-command" in cmd
    assert cmd[cmd.index("--opencode-command") + 1] == str(binary)
