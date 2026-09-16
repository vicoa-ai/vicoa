"""`vicoa.rpc.open_ops` — the `list-open-apps` / `open-path` daemon RPCs.

The launch itself is stubbed everywhere: these assert the argv the daemon would
run (and, more importantly, everything it refuses to run) rather than opening
Finder on the machine running the suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from vicoa.rpc import open_ops


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "readme.md").write_text("hi")
    (tmp_path / "src").mkdir()
    return tmp_path


@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Capture argv instead of launching anything."""
    calls: list[list[str]] = []
    monkeypatch.setattr(open_ops, "_spawn", calls.append)
    return calls


def _force_mac(monkeypatch: pytest.MonkeyPatch, *, installed: bool = True) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(open_ops, "_mac_app_installed", lambda _name: installed)


# ── list-open-apps ───────────────────────────────────────────────────────────


def test_lists_only_apps_for_this_platform(monkeypatch: pytest.MonkeyPatch):
    _force_mac(monkeypatch)
    monkeypatch.setattr(open_ops.shutil, "which", lambda _cmd: None)

    result = open_ops.list_open_apps()

    assert result["platform"] == "darwin"
    ids = {app["id"] for app in result["apps"]}
    assert "finder" in ids
    # Windows/Linux-only entries never leak into a macOS menu.
    assert "explorer" not in ids
    assert "konsole" not in ids


def test_omits_apps_that_are_not_installed(monkeypatch: pytest.MonkeyPatch):
    _force_mac(monkeypatch, installed=False)
    monkeypatch.setattr(open_ops.shutil, "which", lambda _cmd: None)

    ids = {app["id"] for app in open_ops.list_open_apps()["apps"]}

    # Finder and `open` are built into the OS; every third-party app resolved
    # to nothing.
    assert ids == {"default", "finder"}


def test_default_app_is_a_file_only_row(monkeypatch: pytest.MonkeyPatch):
    _force_mac(monkeypatch, installed=False)
    monkeypatch.setattr(open_ops.shutil, "which", lambda _cmd: None)

    apps = {app["id"]: app for app in open_ops.list_open_apps()["apps"]}

    # Listed first: it is the row a generated .xlsx wants.
    assert open_ops.list_open_apps()["apps"][0]["id"] == "default"
    assert apps["default"] == {
        "id": "default",
        "label": "Default app",
        "kind": "default",
        "target": "file",
    }


def test_linux_default_app_needs_xdg_open(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(open_ops.shutil, "which", lambda _cmd: None)

    ids = {app["id"] for app in open_ops.list_open_apps()["apps"]}

    # No xdg-open: neither the default app nor the file manager can be offered.
    assert "default" not in ids
    assert "file-manager" not in ids


def test_cli_on_path_makes_an_editor_available(monkeypatch: pytest.MonkeyPatch):
    _force_mac(monkeypatch, installed=False)
    monkeypatch.setattr(
        open_ops.shutil,
        "which",
        lambda cmd: "/usr/local/bin/code" if cmd == "code" else None,
    )

    apps = {app["id"]: app for app in open_ops.list_open_apps()["apps"]}

    assert apps["vscode"]["kind"] == "editor"
    assert apps["vscode"]["target"] == "path"


# ── open-path ────────────────────────────────────────────────────────────────


def test_finder_reveals_a_file_but_opens_a_directory(
    monkeypatch: pytest.MonkeyPatch, project: Path, spawned: list[list[str]]
):
    _force_mac(monkeypatch)

    assert open_ops.open_path(str(project), "finder", "readme.md") == {"ok": True}
    assert spawned[-1] == ["open", "-R", str(project / "readme.md")]

    assert open_ops.open_path(str(project), "finder", "") == {"ok": True}
    assert spawned[-1] == ["open", str(project)]


def test_editor_cli_gets_the_path_as_its_own_argument(
    monkeypatch: pytest.MonkeyPatch, project: Path, spawned: list[list[str]]
):
    _force_mac(monkeypatch, installed=False)
    monkeypatch.setattr(
        open_ops.shutil,
        "which",
        lambda cmd: "/usr/local/bin/cursor" if cmd == "cursor" else None,
    )

    assert open_ops.open_path(str(project), "cursor", "src") == {"ok": True}
    assert spawned == [["/usr/local/bin/cursor", "--new-window", str(project / "src")]]


def test_mac_bundle_is_the_fallback_when_no_cli_shim_is_installed(
    monkeypatch: pytest.MonkeyPatch, project: Path, spawned: list[list[str]]
):
    _force_mac(monkeypatch)
    monkeypatch.setattr(open_ops.shutil, "which", lambda _cmd: None)

    assert open_ops.open_path(str(project), "vscode", "readme.md") == {"ok": True}
    assert spawned == [["open", "-a", "Visual Studio Code", str(project / "readme.md")]]


def test_terminal_target_collapses_a_file_to_its_directory(
    monkeypatch: pytest.MonkeyPatch, project: Path, spawned: list[list[str]]
):
    _force_mac(monkeypatch)
    monkeypatch.setattr(open_ops.shutil, "which", lambda _cmd: None)

    assert open_ops.open_path(str(project), "terminal", "readme.md") == {"ok": True}
    assert spawned == [["open", "-a", "Terminal", str(project)]]


def test_path_arg_template_is_joined_for_apps_that_need_it(
    monkeypatch: pytest.MonkeyPatch, project: Path, spawned: list[list[str]]
):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        open_ops.shutil,
        "which",
        lambda cmd: "/usr/bin/ghostty" if cmd == "ghostty" else None,
    )

    assert open_ops.open_path(str(project), "ghostty", "src") == {"ok": True}
    assert spawned == [["/usr/bin/ghostty", f"--working-directory={project / 'src'}"]]


# ── default app ──────────────────────────────────────────────────────────────


def test_default_app_hands_the_file_to_the_os_on_each_platform(
    monkeypatch: pytest.MonkeyPatch, project: Path, spawned: list[list[str]]
):
    doc = str(project / "readme.md")

    _force_mac(monkeypatch)
    assert open_ops.open_path(str(project), "default", "readme.md") == {"ok": True}
    assert spawned[-1] == ["open", doc]

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        open_ops.shutil,
        "which",
        lambda cmd: r"C:\Windows\explorer.exe" if cmd == "explorer" else None,
    )
    assert open_ops.open_path(str(project), "default", "readme.md") == {"ok": True}
    # ShellExecute's default verb — a double-click — not `/select,` (reveal).
    assert spawned[-1] == [r"C:\Windows\explorer.exe", doc]

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        open_ops.shutil,
        "which",
        lambda cmd: "/usr/bin/xdg-open" if cmd == "xdg-open" else None,
    )
    assert open_ops.open_path(str(project), "default", "readme.md") == {"ok": True}
    assert spawned[-1] == ["/usr/bin/xdg-open", doc]


def test_default_app_refuses_a_directory(
    monkeypatch: pytest.MonkeyPatch, project: Path, spawned: list[list[str]]
):
    _force_mac(monkeypatch)

    # A folder's "default app" is the file manager, which has its own row.
    assert open_ops.open_path(str(project), "default", "src") == {"error": "not_a_file"}
    assert open_ops.open_path(str(project), "default", "") == {"error": "not_a_file"}
    assert spawned == []


@pytest.mark.parametrize(
    "name",
    ["setup.exe", "run.bat", "deploy.command", "build.sh", "tool.jar", "Installer.PKG"],
)
def test_default_app_refuses_what_the_os_would_execute(
    monkeypatch: pytest.MonkeyPatch, project: Path, spawned: list[list[str]], name: str
):
    _force_mac(monkeypatch)
    (project / name).write_text("")

    assert open_ops.open_path(str(project), "default", name) == {
        "error": "not_openable"
    }
    assert spawned == []


@pytest.mark.skipif(sys.platform == "win32", reason="mode bits are POSIX")
def test_default_app_refuses_an_executable_bit_on_posix(
    monkeypatch: pytest.MonkeyPatch, project: Path, spawned: list[list[str]]
):
    _force_mac(monkeypatch)
    binary = project / "mytool"
    binary.write_text("")
    binary.chmod(0o755)

    # macOS `open` runs a +x file it has no other type for in Terminal.
    assert open_ops.open_path(str(project), "default", "mytool") == {
        "error": "not_openable"
    }
    assert spawned == []

    # The same file with the bit cleared is an ordinary document.
    binary.chmod(0o644)
    assert open_ops.open_path(str(project), "default", "mytool") == {"ok": True}


def test_executable_guard_only_applies_to_the_default_app(
    monkeypatch: pytest.MonkeyPatch, project: Path, spawned: list[list[str]]
):
    _force_mac(monkeypatch)
    monkeypatch.setattr(open_ops.shutil, "which", lambda _cmd: None)
    (project / "build.sh").write_text("")

    # An editor opens a script as text; revealing it is just Finder.
    assert open_ops.open_path(str(project), "vscode", "build.sh") == {"ok": True}
    assert open_ops.open_path(str(project), "finder", "build.sh") == {"ok": True}
    assert len(spawned) == 2


# ── Linux file manager ───────────────────────────────────────────────────────


def _force_linux(monkeypatch: pytest.MonkeyPatch, *tools: str) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        open_ops.shutil,
        "which",
        lambda cmd: f"/usr/bin/{cmd}" if cmd in tools else None,
    )


def test_linux_file_manager_selects_a_file_over_dbus(
    monkeypatch: pytest.MonkeyPatch, project: Path, spawned: list[list[str]]
):
    _force_linux(monkeypatch, "xdg-open", "dbus-send")

    assert open_ops.open_path(str(project), "file-manager", "readme.md") == {"ok": True}
    argv = spawned[-1]
    # The file's URI and its folder travel as `$1`/`$2`; the script is constant
    # and falls back to xdg-open of the folder when no file manager answers.
    assert argv[:2] == ["sh", "-c"]
    assert "org.freedesktop.FileManager1.ShowItems" in argv[2]
    assert argv[2].endswith('|| exec xdg-open "$2"')
    assert argv[3:] == ["vicoa-reveal", (project / "readme.md").as_uri(), str(project)]


def test_linux_file_manager_without_dbus_opens_the_folder(
    monkeypatch: pytest.MonkeyPatch, project: Path, spawned: list[list[str]]
):
    _force_linux(monkeypatch, "xdg-open")

    assert open_ops.open_path(str(project), "file-manager", "readme.md") == {"ok": True}
    assert spawned[-1] == ["/usr/bin/xdg-open", str(project)]


def test_linux_file_manager_opens_a_directory_directly(
    monkeypatch: pytest.MonkeyPatch, project: Path, spawned: list[list[str]]
):
    _force_linux(monkeypatch, "xdg-open", "dbus-send")

    assert open_ops.open_path(str(project), "file-manager", "src") == {"ok": True}
    assert spawned[-1] == ["/usr/bin/xdg-open", str(project / "src")]


# ── refusals ─────────────────────────────────────────────────────────────────


def test_unknown_app_id_never_launches_anything(
    project: Path, spawned: list[list[str]]
):
    assert open_ops.open_path(str(project), "rm -rf /") == {"error": "unknown_app"}
    assert open_ops.open_path(str(project), "sh") == {"error": "unknown_app"}
    assert spawned == []


def test_known_app_that_is_not_installed_is_refused(
    monkeypatch: pytest.MonkeyPatch, project: Path, spawned: list[list[str]]
):
    _force_mac(monkeypatch, installed=False)
    monkeypatch.setattr(open_ops.shutil, "which", lambda _cmd: None)

    assert open_ops.open_path(str(project), "zed", "") == {"error": "app_not_found"}
    assert spawned == []


def test_path_outside_the_project_is_refused(
    monkeypatch: pytest.MonkeyPatch, project: Path, spawned: list[list[str]]
):
    _force_mac(monkeypatch)

    assert open_ops.open_path(str(project), "finder", "../..") == {
        "error": "outside_project"
    }
    assert spawned == []


def test_missing_path_is_refused(
    monkeypatch: pytest.MonkeyPatch, project: Path, spawned: list[list[str]]
):
    _force_mac(monkeypatch)

    assert open_ops.open_path(str(project), "finder", "nope.md") == {
        "error": "path_not_found"
    }
    assert open_ops.open_path(str(project / "gone"), "finder") == {
        "error": "path_not_found"
    }
    assert spawned == []


def test_launch_failure_is_reported_not_raised(
    monkeypatch: pytest.MonkeyPatch, project: Path
):
    _force_mac(monkeypatch)

    def boom(_argv: list[str]) -> None:
        raise OSError("no such executable")

    monkeypatch.setattr(open_ops, "_spawn", boom)

    assert open_ops.open_path(str(project), "finder", "") == {"error": "launch_failed"}
