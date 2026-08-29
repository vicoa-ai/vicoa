"""Path confinement for daemon-side RPC handlers.

Every file/git op must call `resolve_inside_project` on caller-supplied paths
before touching the FS. The helper resolves symlinks and refuses anything that
lands outside the project root.
"""

from __future__ import annotations

import os
from pathlib import Path


class OutsideProject(Exception):
    """Raised when a caller-supplied path resolves outside the project root."""


class OutsideRoot(Exception):
    """Raised when a skill path resolves to (or outside of) its managed root."""


def resolve_inside_project(project_root: Path, rel: str) -> Path:
    """Return the absolute, realpath-resolved path for `rel` inside `project_root`.

    Raises `OutsideProject` if the resolved path escapes the root (via `..`,
    symlink, or absolute input).
    """
    root = project_root.resolve()
    target = (project_root / rel).resolve()
    if target == root:
        return target
    if not str(target).startswith(str(root) + os.sep):
        raise OutsideProject(str(target))
    return target


def resolve_inside_root(root: Path, rel: str) -> Path:
    """Return the path for a skill dir `rel` that is a *direct child* of `root`.

    A skill is always a direct child of its managed root, and that child is
    routinely a **symlink** — skills are commonly linked into `~/.claude/skills`
    from a repo (e.g. `~/.claude/skills/foo -> /repo/skills/foo`). So, unlike
    `resolve_inside_project` (which fully resolves and would reject such a link
    as an escape), we confine by the child's *parent*: the parent must resolve
    to `root` and the leaf must be a single, non-traversing component. That lets
    a legitimately symlinked skill through while still refusing `..`, absolute
    inputs, and multi-segment paths. The leaf itself is left unresolved so the
    caller sees the managed path, not the link target. Raises `OutsideRoot`
    otherwise (the root itself is never a valid target — a skill is a child).
    """
    base = root.resolve()
    target = root / rel
    name = target.name
    if name in ("", ".", ".."):
        raise OutsideRoot(str(target))
    if target.parent.resolve() != base:
        raise OutsideRoot(str(target))
    return target
