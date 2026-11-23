"""An agent the daemon detects is an agent its session can start.

Detection (`_check_agent_installation`, which feeds `available_agents`) uses
the wide `find_npm_cli` search; a session runner left to itself looks only on
the PATH it inherits from the daemon. When an installer put the CLI somewhere
that PATH doesn't reach (an install made after the daemon started; Codex's
Windows installer, which only edits the user PATH), the picker said
"installed" and the session died at start. The daemon now hands the runner the
path detection found, in both the source and the frozen (desktop) command.
"""

from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path

import pytest

from vicoa import cli, machine_daemon, utils
from vicoa.machine_daemon import MachineDaemon


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Sandbox home and PATH so only what a test places can be found."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.delenv("NVM_BIN", raising=False)
    monkeypatch.delenv("NPM_CONFIG_PREFIX", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def _daemon() -> MachineDaemon:
    return MachineDaemon(api_key="test-key", base_url="http://localhost:0")


def _codex_windows_install(home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """What `irm https://chatgpt.com/codex/install.ps1 | iex` leaves behind."""
    local_appdata = home / "AppData" / "Local"
    binary = local_appdata / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"
    binary.parent.mkdir(parents=True)
    binary.write_text("")
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setattr(utils, "_is_windows", lambda: True)
    return binary


# ----- detection -----


def test_finds_codex_where_its_windows_installer_puts_it(
    fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _codex_windows_install(fake_home, monkeypatch)
    assert utils.find_codex_cli() == str(binary)


def test_detection_reports_that_codex_installed(
    fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _codex_windows_install(fake_home, monkeypatch)
    assert _daemon()._check_agent_installation("codex") is None


# ----- the command carries what detection found -----


def test_source_codex_command_carries_the_resolved_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(machine_daemon, "find_codex_cli", lambda: "/opt/codex/codex")
    cmd = _daemon()._build_headless_command(
        directory=os.getcwd(), agent="codex", session_id="s1", metadata=None
    )
    assert "--codex-binary=/opt/codex/codex" in cmd


def test_no_binary_flag_when_codex_was_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The runner then falls back to its own PATH lookup, as before.
    monkeypatch.setattr(machine_daemon, "find_codex_cli", lambda: None)
    cmd = _daemon()._build_headless_command(
        directory=os.getcwd(), agent="codex", session_id="s1", metadata=None
    )
    assert not any(arg.startswith("--codex-binary") for arg in cmd)


@pytest.mark.parametrize(
    ("agent", "expected"),
    [
        ("codex", "--codex-binary=/opt/codex/codex"),
        ("opencode", "--opencode-command=/opt/opencode/opencode"),
    ],
)
def test_frozen_command_carries_the_resolved_binary(
    monkeypatch: pytest.MonkeyPatch, agent: str, expected: str
) -> None:
    # The desktop app runs the frozen daemon, which launches every session as
    # `<vicoa> headless`; that path used to pass neither.
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(machine_daemon, "find_codex_cli", lambda: "/opt/codex/codex")
    monkeypatch.setattr(
        machine_daemon, "find_opencode_cli", lambda: "/opt/opencode/opencode"
    )
    cmd = _daemon()._build_headless_command(
        directory=os.getcwd(), agent=agent, session_id="s1", metadata=None
    )
    assert cmd[1] == "headless"
    assert expected in cmd


# ----- `vicoa headless` passes the flag through to the runner -----


def _run_headless(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> list[str]:
    """Run `vicoa headless` and return the argv its runner module received."""
    received: list[str] = []
    real_import = importlib.import_module

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith("integrations.headless."):
            return types.SimpleNamespace(main=lambda: received.extend(sys.argv))
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(importlib, "import_module", fake_import)
    monkeypatch.setattr(cli, "ensure_api_key", lambda args: "k")
    monkeypatch.setattr(cli, "sync_user_commands_async", lambda *a: None)
    monkeypatch.setattr(cli, "sync_project_files_async", lambda *a: None)
    monkeypatch.setattr(sys, "argv", ["vicoa", "headless", *argv])
    cli.main()
    return received


def test_headless_hands_the_codex_binary_to_the_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received = _run_headless(
        monkeypatch, ["--agent", "codex", "--codex-binary=/opt/codex/codex"]
    )
    assert "--codex-binary=/opt/codex/codex" in received


def test_headless_hands_the_opencode_binary_to_the_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from integrations.headless.opencode_acp import build_arg_parser

    received = _run_headless(
        monkeypatch,
        ["--agent", "opencode", "--opencode-command=/opt/opencode/opencode"],
    )
    args, _ = build_arg_parser().parse_known_args(received[1:])
    assert args.opencode_command == "/opt/opencode/opencode"
