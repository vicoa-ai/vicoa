"""Daemon RPC handlers for git worktree lifecycle — create / list / remove.

See `plans/todos/vicoa-app-worktree.md`. Worktrees are created OUTSIDE the
user's repo, under `~/vicoa/workspaces/<project>-worktrees/<branch>/<project>`,
so they never pollute an arbitrary repo's `git status` and the spawned
session's `project` (its cwd) reads as the project name, not the branch slug.
Creation targets are daemon-computed (never app-supplied); removal is confined
by identity to real linked worktrees of the repo (checked against `git worktree
list`), so the main checkout and arbitrary paths are never removable.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from vicoa.rpc.worktree_names import generate_unique_name
from vicoa.rpc.worktree_paths import (
    UnmanagedWorktree,
    assert_managed_worktree,
    repo_basename,
    workspaces_root,
    worktrees_parent_dir,
    worktree_dir_for,  # noqa: F401  (kept for callers/tests of the path layout)
)


def _is_git_repo(abs_dir: Path) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(abs_dir), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0 and proc.stdout.strip() == b"true"


def _branch_exists(repo: Path, name: str) -> bool:
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "rev-parse",
            "--verify",
            "--quiet",
            f"refs/heads/{name}",
        ],
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def create_worktree(repo_dir: str) -> dict[str, Any]:
    """Fork a fresh branch + checkout off `repo_dir`'s current HEAD.

    Returns `{"path", "branch"}` on success or `{"error"}` if the directory is
    not a git repo or `git worktree add` fails (e.g. unborn HEAD). The branch
    name equals the worktree name; both are daemon-generated and unique.
    """
    abs_repo = Path(os.path.expanduser(repo_dir)).resolve()
    if not _is_git_repo(abs_repo):
        return {"error": "not_a_repo"}

    parent = worktrees_parent_dir(abs_repo)
    parent.mkdir(parents=True, exist_ok=True)

    # `name` (the branch) is the middle dir; the checkout leaf is the project
    # basename so the session's `project` displays as the project name. The
    # collision check is on the middle dir under `parent`.
    name = generate_unique_name(parent, is_taken=lambda n: _branch_exists(abs_repo, n))
    path = parent / name / repo_basename(abs_repo)

    # `git worktree add` creates the intermediate <branch> dir and the leaf.
    proc = subprocess.run(
        ["git", "-C", str(abs_repo), "worktree", "add", "-b", name, str(path)],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        # Drop the empty <branch> middle dir if git left one before failing.
        _prune_empty_dirs(path.parent)
        return {
            "error": proc.stderr.decode("utf-8", errors="replace").strip()
            or "worktree_add_failed"
        }

    return {"path": str(path), "branch": name}


def _prune_empty_dirs(start: Path) -> None:
    """Remove now-empty dirs from `start` up to (not including) the workspaces
    root — used after a worktree is removed so the `<branch>` middle dir (and an
    emptied `<project>-worktrees` parent) don't linger.
    """
    root = workspaces_root().resolve()
    current = start.resolve()
    while current != root and str(current).startswith(str(root) + os.sep):
        try:
            current.rmdir()  # only succeeds if empty
        except OSError:
            break
        current = current.parent


def _is_managed(path: str) -> bool:
    try:
        assert_managed_worktree(path)
    except UnmanagedWorktree:
        return False
    return True


def _parse_worktree_porcelain(blob: bytes) -> list[dict[str, Any]]:
    """Parse `git worktree list --porcelain` into one record per worktree.

    Records are blank-line separated. Each starts with a `worktree <path>`
    line, followed by `HEAD <sha>` and either `branch refs/heads/<name>` or a
    bare `detached` line.
    """
    records: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in blob.decode("utf-8", errors="replace").splitlines():
        if raw_line.startswith("worktree "):
            current = {"path": raw_line[len("worktree ") :], "branch": "", "head": ""}
            records.append(current)
        elif current is None:
            continue
        elif raw_line.startswith("HEAD "):
            current["head"] = raw_line[len("HEAD ") :]
        elif raw_line.startswith("branch "):
            ref = raw_line[len("branch ") :]
            current["branch"] = ref.removeprefix("refs/heads/")
        elif raw_line == "detached":
            current["detached"] = True
    return records


def list_worktrees(cwd: str) -> dict[str, Any]:
    """List a repo's worktrees, excluding the main one.

    Returns `{"worktrees": [{path, branch, head, managed}]}` or
    `{"error": "not_a_repo"}`. `managed` marks worktrees the daemon created
    (under `~/vicoa/workspaces/`) — only those are removable by the app; the
    user's own hand-made worktrees are flagged unmanaged.
    """
    abs_dir = Path(os.path.expanduser(cwd)).resolve()
    if not _is_git_repo(abs_dir):
        return {"error": "not_a_repo"}

    proc = subprocess.run(
        ["git", "-C", str(abs_dir), "worktree", "list", "--porcelain"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return {"error": "not_a_repo"}

    records = _parse_worktree_porcelain(proc.stdout)
    # The first record is always the main worktree — drop it.
    linked = records[1:]

    worktrees = [
        {
            "path": rec["path"],
            "branch": rec.get("branch", ""),
            "head": rec.get("head", ""),
            "managed": _is_managed(rec["path"]),
        }
        for rec in linked
    ]
    return {"worktrees": worktrees}


def remove_worktree(
    cwd: str, worktree_path: str, force: bool = False
) -> dict[str, Any]:
    """Remove a worktree's checkout; never delete its branch.

    Confinement is by identity, not path prefix: `worktree_path` must be a real
    *linked* worktree of the repo at `cwd` (managed or hand-made), checked
    against `git worktree list`. Since that listing drops the main worktree,
    the main checkout is never removable, and any path that isn't a worktree is
    rejected as `not_a_worktree`. The branch is always kept, so commits stay
    recoverable from a desktop. Returns `{"ok": True}` or `{"error": ...}`.
    """
    abs_repo = Path(os.path.expanduser(cwd)).resolve()
    if not _is_git_repo(abs_repo):
        return {"error": "not_a_repo"}

    resolved = Path(os.path.expanduser(worktree_path)).resolve()

    listing = list_worktrees(cwd)
    if "error" in listing:
        return listing
    listed = {Path(w["path"]).resolve() for w in listing["worktrees"]}
    if resolved not in listed:
        return {"error": "not_a_worktree"}

    argv = ["git", "-C", str(abs_repo), "worktree", "remove"]
    if force:
        argv.append("--force")
    argv.append(str(resolved))

    proc = subprocess.run(argv, capture_output=True, check=False)
    if proc.returncode != 0:
        return {
            "error": proc.stderr.decode("utf-8", errors="replace").strip()
            or "remove_failed"
        }
    # `git worktree remove` deletes the checkout leaf but leaves the `<branch>`
    # middle dir behind — prune it (and an emptied parent) so the tree stays clean.
    _prune_empty_dirs(resolved.parent)
    return {"ok": True}
