"""The PTY extraction is a file move: the old import path must keep working.

Desktop-app v1 deliverable 1 — ``PTYManager`` lives in
``vicoa.terminal.pty_manager``; the Claude wrapper's historical import paths
re-export the very same class object (shim, not a copy).
"""

from integrations.cli_wrappers.claude_code.terminal import PTYManager as WrapperPkgPTY
from integrations.cli_wrappers.claude_code.terminal.pty_manager import (
    PTYManager as WrapperModulePTY,
)
from vicoa.terminal import PTYManager as TerminalPkgPTY
from vicoa.terminal.pty_manager import PTYManager


def test_old_module_path_reexports_the_same_class() -> None:
    assert WrapperModulePTY is PTYManager


def test_wrapper_package_still_exports_ptymanager() -> None:
    assert WrapperPkgPTY is PTYManager


def test_new_package_exports_ptymanager() -> None:
    assert TerminalPkgPTY is PTYManager


def test_class_shape_is_unchanged() -> None:
    expected = {
        "create_pty",
        "write_to_pty",
        "read_from_pty",
        "close",
        "is_child_alive",
        "wait_for_child",
        "set_raw_mode",
        "restore_terminal",
        "suspend_for_ctrl_z",
    }
    assert expected.issubset(set(dir(PTYManager)))
