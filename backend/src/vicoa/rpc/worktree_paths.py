"""Path layout + confinement for daemon-side git worktrees.

Worktrees live OUTSIDE any user repo, under a daemon-computed root
(`~/vicoa/workspaces/<project>-worktrees/<branch>/<project>`). The leaf is the
project name so a worktree session's `project` (its cwd) displays as the
project, not the random branch slug. The app never supplies a write path: the
daemon computes creation targets, and `assert_managed_worktree` flags which
listed worktrees live under this root (removal itself is confined by identity to
real worktrees of the repo, in `worktree_ops.remove_worktree`). This is
deliberately separate from `paths.resolve_inside_project` — worktree paths are
*outside* the repo.
"""

from __future__ import annotations

import os
from pathlib import Path


class UnmanagedWorktree(Exception):
    """Raised when a path does not resolve under the vicoa workspaces root."""


def workspaces_root() -> Path:
    """`~/vicoa/workspaces` — read at call time so HOME is honoured in tests."""
    return Path.home() / "vicoa" / "workspaces"


def repo_basename(repo_dir: str | os.PathLike[str]) -> str:
    """The project folder name, e.g. `vicoa-backend`."""
    return Path(repo_dir).resolve().name


def worktrees_parent_dir(repo_dir: str | os.PathLike[str]) -> Path:
    """Per-project grouping dir: `~/vicoa/workspaces/<project>-worktrees`."""
    return workspaces_root() / f"{repo_basename(repo_dir)}-worktrees"


def worktree_dir_for(repo_dir: str | os.PathLike[str], name: str) -> Path:
    """Absolute checkout path for worktree `name`:
    `<workspaces>/<project>-worktrees/<name>/<project>`.

    The leaf is the project basename (so the spawned session's `project`
    displays as the project name); `name` — the branch — is the middle dir.
    """
    return worktrees_parent_dir(repo_dir) / name / repo_basename(repo_dir)


def assert_managed_worktree(path: str | os.PathLike[str]) -> Path:
    """Return the realpath of `path` if it lives under the workspaces root.

    Resolves symlinks before checking, so a symlink under the root that points
    elsewhere is rejected. Raises `UnmanagedWorktree` otherwise.
    """
    root = workspaces_root().resolve()
    target = Path(path).resolve()
    if not str(target).startswith(str(root) + os.sep):
        raise UnmanagedWorktree(str(target))
    return target
