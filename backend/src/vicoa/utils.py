"""Utility functions for Vicoa CLI."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Optional


def derive_ws_url(base_url: str) -> str:
    """Default WS URL = REST base URL with scheme swap and a `/ws` path.

    One derivation covers production (``https://agents.vicoa.ai`` →
    ``wss://agents.vicoa.ai/ws``), the legacy port-8443 hostname
    (``https://api.vicoa.ai:8443`` → ``wss://api.vicoa.ai:8443/ws``), and
    local dev (``http://localhost:8080`` → ``ws://localhost:8080/ws``).
    Set ``VICOA_WS_URL`` to override when host or path differs.
    """
    if base_url.startswith("https://"):
        return f"wss://{base_url[len('https://') :].rstrip('/')}/ws"
    if base_url.startswith("http://"):
        return f"ws://{base_url[len('http://') :].rstrip('/')}/ws"
    return base_url


def get_project_path(path: str | None = None) -> str:
    """Format a project path to use ~ for home directory.

    This creates a more readable path representation by replacing the home
    directory prefix with ~, consistent with how paths are displayed across
    agent instances.

    Args:
        path: The path to format. If None, uses current working directory.

    Returns:
        The formatted path with ~ replacing home directory if applicable.

    Examples:
        >>> format_project_path("/Users/john/projects/myapp")
        "~/projects/myapp"
        >>> format_project_path("/opt/app")
        "/opt/app"
    """
    project_path = os.path.abspath(path) if path else os.getcwd()
    home_dir = str(Path.home())

    if project_path.startswith(home_dir):
        return "~" + project_path[len(home_dir) :]

    return project_path


def get_worktree_name(path: str | None = None) -> str | None:
    """Name of the linked git worktree ``path`` sits in, or ``None``.

    Sessions report this at registration so the sidebar can sub-group a
    project's sessions by worktree (see
    ``plans/todos/sidebar-worktree-grouping.md``). Deliberately ``None`` for a
    repo's *main* checkout and for non-git directories: a plain session has no
    worktree, and the UI renders those directly under the project rather than
    inventing a "main" bucket.

    Detection is ``git-dir != git-common-dir``, which is the only reliable
    signal. Comparing the worktree root against the parent of the common dir
    looks equivalent but misidentifies every **submodule** as a worktree — a
    submodule's common dir is ``<super>/.git/modules/<name>``, whose parent is
    not the submodule's root. This repo is itself a submodule, so that variant
    would mislabel its own sessions.

    The name is the checked-out branch, which for daemon-created worktrees is
    also the directory git checked it out into
    (``~/vicoa/workspaces/<project>-worktrees/<branch>/<project>``). A detached
    HEAD has no branch, so it falls back to the worktree root's directory name.

    Never raises: a missing git, a non-repo path, or a slow/hung git all yield
    ``None``, since registration must not fail over a display nicety.
    """
    target = os.path.expanduser(path) if path else os.getcwd()
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                target,
                "rev-parse",
                "--git-dir",
                "--git-common-dir",
                "--abbrev-ref",
                "HEAD",
                "--show-toplevel",
            ],
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None

    lines = proc.stdout.decode("utf-8", errors="replace").splitlines()
    if len(lines) < 4:
        return None
    git_dir, common_dir, branch, toplevel = (line.strip() for line in lines[:4])

    # git prints these relative to `target` when the repo is right there (both
    # come back as ".git" for a main checkout), so resolve before comparing —
    # equal paths can still be unequal strings.
    def _resolve(raw: str) -> str:
        return os.path.normpath(os.path.join(target, raw))

    if _resolve(git_dir) == _resolve(common_dir):
        return None  # main checkout, not a linked worktree

    if branch and branch != "HEAD":
        return branch
    return os.path.basename(os.path.normpath(toplevel)) or None


def _is_windows() -> bool:
    """Whether we're running on Windows.

    Wrapped in a helper (rather than inlining ``os.name == "nt"``) so tests
    can flip it without mutating ``os.name`` — mutating ``os.name`` makes
    ``pathlib`` dispatch to ``WindowsPath``, which can't be instantiated on a
    POSIX host.
    """
    return os.name == "nt"


# Executable suffixes to try when a candidate path is stored without an
# explicit extension. npm shims land as ``.cmd`` (and a bare shell shim), the
# Claude Code native installer / winget links as ``.exe``. A fixed list rather
# than the full ``PATHEXT`` so we never match an unrelated ``claude.py``.
_WINDOWS_EXE_SUFFIXES = (".exe", ".cmd", ".bat", ".ps1")


def _resolve_executable(candidate: Path) -> str | None:
    """Return ``candidate`` if it's a file, trying Windows suffixes too.

    On Windows the candidate dirs hold ``<name>.exe`` / ``<name>.cmd`` rather
    than a bare ``<name>``, so a plain ``is_file()`` on the extensionless path
    misses the very install it's meant to find.
    """
    try:
        if candidate.is_file():
            return str(candidate)
    except OSError:
        return None
    if _is_windows():
        for suffix in _WINDOWS_EXE_SUFFIXES:
            variant = candidate.with_name(candidate.name + suffix)
            try:
                if variant.is_file():
                    return str(variant)
            except OSError:
                continue
    return None


_NVM_VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def _installed_nvm_versions(
    versions_root: Path,
) -> list[tuple[tuple[int, int, int], Path]]:
    """Installed nvm node versions, newest first, as ``((maj, min, pat), dir)``."""
    found: list[tuple[tuple[int, int, int], Path]] = []
    try:
        for child in versions_root.iterdir():
            m = _NVM_VERSION_RE.match(child.name)
            if m and child.is_dir():
                found.append(((int(m[1]), int(m[2]), int(m[3])), child))
    except OSError:
        return []
    found.sort(key=lambda item: item[0], reverse=True)
    return found


def _read_nvm_alias(alias_dir: Path, name: str, _depth: int = 0) -> Optional[str]:
    """Resolve an nvm alias file to its target, following alias chains.

    nvm stores ``default`` (and ``lts/*`` → ``lts/<codename>`` → ``vX.Y.Z``) as
    plain files whose contents may name another alias; follow that chain,
    bounded, until we reach a version-ish token. Returns None on any read error
    or an over-long chain.
    """
    if _depth > 5:
        return None
    try:
        target = (alias_dir / name).read_text().strip()
    except OSError:
        return None
    if not target:
        return None
    # Follow when the target names another alias (e.g. `default` → `lts/*`).
    if (alias_dir / target).is_file():
        return _read_nvm_alias(alias_dir, target, _depth + 1)
    return target


def _nvm_default_node_bin(nvm_root: Path) -> Optional[Path]:
    """``bin/`` of the node version nvm's ``default`` alias selects, if installed.

    nvm keeps many node versions installed but only one is *selected* per shell.
    A CLI left behind in an old, no-longer-default version dir is one the user's
    ``which <name>`` can no longer see, so treating it as installed is a false
    positive (an agent lingering in Providers after the user upgraded node and
    dropped the global install). This mirrors what a login shell's
    ``nvm use default`` puts on PATH — the daemon (often launched with a minimal
    PATH that omits it) then finds the same CLIs the user can, and nothing more.

    Handles the alias spellings nvm actually writes: a concrete ``v22.23.2``, a
    partial ``22`` / ``22.23`` (highest installed match), and
    ``node`` / ``stable`` (highest installed overall). Returns None when nvm is
    absent, no ``default`` alias is set, or the alias resolves to no installed
    version. Requiring the alias is deliberate: without it nvm wouldn't select
    any version for a login shell either (the caller has already tried
    ``NVM_BIN`` and PATH), so a leftover global in some installed-but-unselected
    version must not read as installed.
    """
    installed = _installed_nvm_versions(nvm_root / "versions" / "node")
    if not installed:
        return None

    target = _read_nvm_alias(nvm_root / "alias", "default")
    if target is None:
        return None
    if target in {"node", "stable", "latest", "current", "*"}:
        return installed[0][1] / "bin"

    wanted = [part for part in target.lstrip("v").split(".") if part]
    if not wanted or not all(part.isdigit() for part in wanted):
        return None  # unrecognized alias spelling — don't guess
    prefix = tuple(int(part) for part in wanted[:3])
    for version, path in installed:  # newest-first: first prefix match wins
        if version[: len(prefix)] == prefix:
            return path / "bin"
    return None


def find_npm_cli(
    name: str,
    *,
    extra_locations: Iterable[Path] = (),
) -> str | None:
    """Locate an npm/node-installed CLI binary under a non-login PATH.

    The daemon (especially when started by systemd or as a background
    ``Popen`` without a login shell) frequently runs with a minimal PATH
    that omits the dirs where npm-global / nvm / Volta / snap / brew
    install binaries — so ``shutil.which`` alone misses CLIs the user can
    plainly run from their terminal. On Windows the same gap bites even
    harder: PATH edits only apply to *new* sessions, so a daemon started
    before the install never sees it, and npm / winget / the native
    installer each land the binary in a different non-PATH dir. This helper
    layers fallbacks so a CLI installed by any of those tools is still found.

    Search order:
      1. ``shutil.which`` (system PATH; honors PATHEXT on Windows).
      2. ``$NVM_BIN/<name>`` (set by nvm in active shells).
      3. ``$NPM_CONFIG_PREFIX/bin/<name>``.
      4. Well-known per-user / system install dirs (POSIX and, on Windows,
         ``%LOCALAPPDATA%\\Microsoft\\WinGet\\Links``, ``%APPDATA%\\npm``,
         ``%USERPROFILE%\\.local\\bin`` and the machine-scope WinGet links).
      5. ``<nvm-default-version>/bin/<name>`` — the node version nvm's
         ``default`` alias selects (NOT every installed version). Covers the
         dominant Ubuntu/Debian case where users install Node via nvm and the
         daemon's PATH never has nvm's shell-sourced entry, without matching a
         stale global left in some other, no-longer-selected version dir.
      6. ``~/.volta/bin/<name>``.
      7. ``/snap/bin/<name>``.
      8. ``extra_locations`` (caller-supplied per-CLI overrides).
      9. ``npm config get prefix`` → ``<prefix>/bin/<name>`` (POSIX) or
         ``<prefix>/<name>`` (Windows) as a last resort (only if ``npm``
         itself is on PATH).

    On Windows every candidate is additionally probed with the
    ``_WINDOWS_EXE_SUFFIXES`` extensions, since the files there carry
    ``.exe`` / ``.cmd`` rather than a bare name.

    Returns ``None`` if nothing matches.
    """
    if cli := shutil.which(name):
        return cli

    candidates: list[Path] = []

    nvm_bin = os.environ.get("NVM_BIN")
    if nvm_bin:
        candidates.append(Path(nvm_bin) / name)

    npm_prefix = os.environ.get("NPM_CONFIG_PREFIX")
    if npm_prefix:
        candidates.append(Path(npm_prefix) / "bin" / name)

    home = Path.home()
    candidates.extend(
        [
            home / ".npm-global" / "bin" / name,
            Path("/usr/local/bin") / name,
            home / ".local" / "bin" / name,
            home / "node_modules" / ".bin" / name,
            home / ".yarn" / "bin" / name,
            Path("/home/linuxbrew/.linuxbrew/bin") / name,
        ]
    )

    if _is_windows():
        # Windows install dirs that are frequently absent from a daemon's
        # inherited PATH. ``~/.local/bin`` (native installer) is already
        # covered above; the rest are winget links and npm-global.
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            candidates.append(
                Path(local_appdata) / "Microsoft" / "WinGet" / "Links" / name
            )
        appdata = os.environ.get("APPDATA")
        if appdata:
            # npm global bins live directly in the prefix on Windows, not bin/.
            candidates.append(Path(appdata) / "npm" / name)
        program_files = os.environ.get("ProgramFiles")
        if program_files:
            # Machine-scope winget install (``--scope machine``).
            candidates.append(Path(program_files) / "WinGet" / "Links" / name)

    # Probe ONLY the nvm-`default` version's bin — not every version ever
    # installed. Scanning all of them makes a stale global in an old,
    # no-longer-selected version dir read as "installed" even though the user's
    # `which <name>` can't see it (their agent kept showing in Providers after a
    # node upgrade dropped the global install). See `_nvm_default_node_bin`.
    default_node_bin = _nvm_default_node_bin(home / ".nvm")
    if default_node_bin is not None:
        candidates.append(default_node_bin / name)

    candidates.extend(
        [
            home / ".volta" / "bin" / name,
            Path("/snap/bin") / name,
        ]
    )

    candidates.extend(extra_locations)

    for candidate in candidates:
        resolved = _resolve_executable(candidate)
        if resolved:
            return resolved

    # Last resort: ask npm itself for its global prefix. Useful when the
    # user customized it (`npm config set prefix ...`) to somewhere not
    # in any of the above lists.
    npm = shutil.which("npm")
    if npm:
        try:
            result = subprocess.run(
                [npm, "config", "get", "prefix"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            prefix = result.stdout.strip()
            if prefix:
                # Windows puts global bins in the prefix root; POSIX in bin/.
                bin_candidate = (
                    Path(prefix) / name
                    if _is_windows()
                    else Path(prefix) / "bin" / name
                )
                resolved = _resolve_executable(bin_candidate)
                if resolved:
                    return resolved
        except Exception:
            pass

    return None
