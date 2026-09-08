"""Daemon RPC handlers for `list-open-apps` and `open-path`.

"Open in Finder / VS Code / Ghostty…" from the web, desktop or mobile client.
The files live on the *daemon's* machine, so the launch has to happen here —
the client only ever names an app by id from the catalog below.

**Why a fixed catalog instead of a free-form command.** A client is remote and
only as trusted as the account it authenticated with; accepting an arbitrary
argv from it would turn the Files panel into a remote shell. So the wire
protocol carries an opaque `app` id, this module maps it to an argv built from
constants, and anything unknown is refused. Adding an app is one `_AppSpec`
row — that is the extension point.

Detection is per-call and cheap (`shutil.which` + a few `Path.exists`): an app
installed after the daemon started shows up on the next `list-open-apps`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from vicoa.rpc.paths import OutsideProject, resolve_inside_project

# Where macOS keeps .app bundles. Utilities is separate because Terminal.app
# lives there (`/System/Applications/Utilities` on Ventura and later).
_MAC_APP_ROOTS = (
    "/Applications",
    "/Applications/Utilities",
    "/System/Applications",
    "/System/Applications/Utilities",
    "~/Applications",
)


@dataclass(frozen=True)
class _AppSpec:
    """One openable application.

    `platform` is a `sys.platform` value, or `"*"` for "wherever it's found".
    `target` says what the app wants handed to it: `"path"` opens the file or
    folder itself (editors, Finder), `"dir"` always resolves to a directory
    (terminals `cd` into it, so a file target means its parent).

    Availability is resolved in order: `special` (a built-in OS launcher, always
    present) → `command` on PATH → `mac_app` bundle. The macOS bundle fallback
    matters because plenty of people never run VS Code's "Install 'code' command
    in PATH", and `open -a "Visual Studio Code" <path>` works regardless.
    """

    id: str
    label: str
    kind: str
    platform: str
    target: str = "path"
    #: Built-in OS launcher with argv the generic branches can't express.
    special: str | None = None
    #: CLI executable looked up on PATH.
    command: str | None = None
    #: Fixed args inserted between the command and the path.
    command_args: tuple[str, ...] = ()
    #: Template for the path argument, e.g. `--working-directory={path}`.
    #: Defaults to passing the path as its own bare argument.
    path_arg: str | None = None
    #: macOS .app bundle name (no `.app` suffix), used via `open -a`.
    mac_app: str | None = None


# Adding an app = adding a row here. Order is the order the client renders.
_CATALOG: tuple[_AppSpec, ...] = (
    # ── File managers ────────────────────────────────────────────────────────
    _AppSpec("finder", "Finder", "file-manager", "darwin", special="finder"),
    _AppSpec("explorer", "File Explorer", "file-manager", "win32", special="explorer"),
    _AppSpec(
        "file-manager",
        "File Manager",
        "file-manager",
        "linux",
        target="dir",
        command="xdg-open",
    ),
    # ── Editors ──────────────────────────────────────────────────────────────
    _AppSpec(
        "vscode", "VS Code", "editor", "*", command="code", mac_app="Visual Studio Code"
    ),
    _AppSpec(
        "vscode-insiders",
        "VS Code Insiders",
        "editor",
        "*",
        command="code-insiders",
        mac_app="Visual Studio Code - Insiders",
    ),
    _AppSpec(
        "cursor",
        "Cursor",
        "editor",
        "*",
        # Cursor otherwise reuses the last active workbench, which would open
        # this project inside an unrelated window.
        command_args=("--new-window",),
        command="cursor",
        mac_app="Cursor",
    ),
    _AppSpec(
        "windsurf", "Windsurf", "editor", "*", command="windsurf", mac_app="Windsurf"
    ),
    _AppSpec("zed", "Zed", "editor", "*", command="zed", mac_app="Zed"),
    _AppSpec(
        "sublime", "Sublime Text", "editor", "*", command="subl", mac_app="Sublime Text"
    ),
    _AppSpec(
        "intellij",
        "IntelliJ IDEA",
        "editor",
        "*",
        command="idea",
        mac_app="IntelliJ IDEA",
    ),
    _AppSpec(
        "webstorm", "WebStorm", "editor", "*", command="webstorm", mac_app="WebStorm"
    ),
    _AppSpec("pycharm", "PyCharm", "editor", "*", command="pycharm", mac_app="PyCharm"),
    _AppSpec("goland", "GoLand", "editor", "*", command="goland", mac_app="GoLand"),
    # ── Terminals ────────────────────────────────────────────────────────────
    _AppSpec(
        "terminal", "Terminal", "terminal", "darwin", target="dir", mac_app="Terminal"
    ),
    _AppSpec("iterm", "iTerm", "terminal", "darwin", target="dir", mac_app="iTerm"),
    _AppSpec("warp", "Warp", "terminal", "darwin", target="dir", mac_app="Warp"),
    _AppSpec(
        "ghostty",
        "Ghostty",
        "terminal",
        "*",
        target="dir",
        command="ghostty",
        # Ghostty's config parser only accepts `--key=value`.
        path_arg="--working-directory={path}",
        mac_app="Ghostty",
    ),
    _AppSpec(
        "windows-terminal",
        "Windows Terminal",
        "terminal",
        "win32",
        target="dir",
        command="wt",
        command_args=("-d",),
    ),
    _AppSpec(
        "gnome-terminal",
        "GNOME Terminal",
        "terminal",
        "linux",
        target="dir",
        command="gnome-terminal",
        path_arg="--working-directory={path}",
    ),
    _AppSpec(
        "konsole",
        "Konsole",
        "terminal",
        "linux",
        target="dir",
        command="konsole",
        command_args=("--workdir",),
    ),
    _AppSpec(
        "kitty",
        "kitty",
        "terminal",
        "linux",
        target="dir",
        command="kitty",
        command_args=("-d",),
    ),
    _AppSpec(
        "alacritty",
        "Alacritty",
        "terminal",
        "linux",
        target="dir",
        command="alacritty",
        command_args=("--working-directory",),
    ),
    _AppSpec(
        "wezterm",
        "WezTerm",
        "terminal",
        "linux",
        target="dir",
        command="wezterm",
        command_args=("start", "--cwd"),
    ),
)

#: An argv builder: `(absolute path, whether it is a directory) -> argv`.
_Launcher = Callable[[str, bool], list[str]]


def _mac_app_installed(name: str) -> bool:
    return any(
        Path(root).expanduser().joinpath(f"{name}.app").exists()
        for root in _MAC_APP_ROOTS
    )


def _resolve_launcher(spec: _AppSpec) -> _Launcher | None:
    """Argv builder for `spec` on this machine, or None when it isn't installed."""
    if spec.platform != "*" and spec.platform != sys.platform:
        return None

    if spec.special == "finder":
        # Reveal semantics for a file (select it in its folder), open for a dir.
        return lambda path, is_dir: ["open", path] if is_dir else ["open", "-R", path]
    if spec.special == "explorer":
        exe = shutil.which("explorer") or "explorer"
        return lambda path, is_dir: [exe, path] if is_dir else [exe, f"/select,{path}"]

    if spec.command:
        executable = shutil.which(spec.command)
        if executable:
            args = spec.command_args
            template = spec.path_arg
            return lambda path, _is_dir: [
                executable,
                *args,
                template.format(path=path) if template else path,
            ]

    if spec.mac_app and sys.platform == "darwin" and _mac_app_installed(spec.mac_app):
        app = spec.mac_app
        return lambda path, _is_dir: ["open", "-a", app, path]

    return None


def _available_specs() -> list[tuple[_AppSpec, _Launcher]]:
    resolved = ((spec, _resolve_launcher(spec)) for spec in _CATALOG)
    return [(spec, launcher) for spec, launcher in resolved if launcher is not None]


def list_open_apps() -> dict[str, Any]:
    """Apps installed on this machine that can open a project path.

    Returns only what actually resolves here, so the client can render the menu
    without knowing anything about the daemon's OS.
    """
    return {
        "platform": sys.platform,
        "apps": [
            {
                "id": spec.id,
                "label": spec.label,
                "kind": spec.kind,
                "target": spec.target,
            }
            for spec, _ in _available_specs()
        ],
    }


def _spawn(argv: list[str]) -> None:
    """Launch detached — the app must outlive this RPC, and we never read it."""
    popen_kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        # No console flash for the CLI shims (`code.cmd`, `wt`).
        popen_kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )
    else:
        popen_kwargs["start_new_session"] = True
    subprocess.Popen(argv, **popen_kwargs)


def open_path(cwd: str, app: str, path: str = "") -> dict[str, Any]:
    """Open `path` (project-relative; `""` is the project root) in `app`.

    `app` is an id from `list_open_apps`; an unknown or uninstalled one is
    refused rather than shelled out. Errors mirror the other file RPCs
    (`path_not_found` / `outside_project`) plus `unknown_app`, `app_not_found`
    and `launch_failed`.
    """
    project_root = Path(os.path.expanduser(cwd))
    if not project_root.is_dir():
        return {"error": "path_not_found"}
    try:
        target = resolve_inside_project(project_root, path)
    except OutsideProject:
        return {"error": "outside_project"}
    if not target.exists():
        return {"error": "path_not_found"}

    spec = next((s for s in _CATALOG if s.id == app), None)
    if spec is None:
        return {"error": "unknown_app"}
    launcher = _resolve_launcher(spec)
    if launcher is None:
        return {"error": "app_not_found"}

    is_dir = target.is_dir()
    if spec.target == "dir" and not is_dir:
        # Terminals cd into the target; a file means "its folder".
        target = target.parent
        is_dir = True

    try:
        _spawn(launcher(str(target), is_dir))
    except OSError:
        return {"error": "launch_failed"}
    return {"ok": True}
