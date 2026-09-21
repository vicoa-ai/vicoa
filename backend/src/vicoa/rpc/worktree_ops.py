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
import shutil
import subprocess
import threading
import time
import weakref
from pathlib import Path
from typing import Any

from vicoa.rpc.worktree_names import disambiguate, generate_unique_name
from vicoa.utils import get_project_path
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


def _is_valid_branch_name(name: str) -> bool:
    """git's own verdict on `name` as a branch — the single source of truth
    for what a user-typed worktree name may look like (the web mirrors the
    common rules for instant feedback, but this is what decides)."""
    proc = subprocess.run(
        ["git", "check-ref-format", "--branch", name],
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def check_worktree_name(cwd: str, name: str) -> dict[str, Any]:
    """Whether `name` is free to become a new worktree (+ branch) of `cwd`'s repo.

    Returns `{"available": True}`, or `{"available": False, "reason":
    "invalid_name" | "name_taken", "suggestion"?: str}` — `suggestion` is the
    first free `name-2`, `name-3`, … for a taken name, so the app can offer a
    one-click fix. A name is taken if the branch exists or the worktree's
    middle dir does (the same test `create_worktree` applies to a random
    name). `{"error": "not_a_repo"}` for a non-repo.
    """
    abs_repo = Path(os.path.expanduser(cwd)).resolve()
    if not _is_git_repo(abs_repo):
        return {"error": "not_a_repo"}

    candidate = name.strip()
    if not candidate or not _is_valid_branch_name(candidate):
        return {"available": False, "reason": "invalid_name"}

    parent = worktrees_parent_dir(abs_repo)

    def is_taken(n: str) -> bool:
        return _branch_exists(abs_repo, n)

    if (parent / candidate).exists() or is_taken(candidate):
        return {
            "available": False,
            "reason": "name_taken",
            "suggestion": disambiguate(parent, candidate, is_taken=is_taken),
        }
    return {"available": True}


def _toplevel(abs_dir: Path) -> Path | None:
    """The working tree's top-level directory for any path inside it (a
    subdirectory of a checkout resolves to the checkout), or None outside git."""
    proc = subprocess.run(
        ["git", "-C", str(abs_dir), "rev-parse", "--show-toplevel"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    raw = proc.stdout.decode("utf-8", errors="replace").strip()
    return Path(raw).resolve() if raw else None


def create_worktree(repo_dir: str, name: str | None = None) -> dict[str, Any]:
    """Fork a fresh branch + checkout off `repo_dir`'s current HEAD.

    `repo_dir` may be any directory inside the checkout — a monorepo session
    started at `repo/apps/web` forks the whole repo, not the subfolder — so the
    worktree is keyed on the top-level and `repo_root` in the result says
    which. Returns `{"path", "branch", "repo_root"}` on success or `{"error"}`
    if the directory is not a git repo or `git worktree add` fails (e.g.
    unborn HEAD). The branch name equals the worktree name. Without `name` the
    daemon generates a unique random slug; with one, the user's choice is used
    verbatim and a collision is an error (`name_taken`) rather than a silent
    `-2` — they asked for THAT name. An invalid ref is `invalid_name`.
    """
    abs_dir = Path(os.path.expanduser(repo_dir)).resolve()
    if not _is_git_repo(abs_dir):
        return {"error": "not_a_repo"}
    abs_repo = _toplevel(abs_dir) or abs_dir

    parent = worktrees_parent_dir(abs_repo)
    parent.mkdir(parents=True, exist_ok=True)

    # `name` (the branch) is the middle dir; the checkout leaf is the project
    # basename so the session's `project` displays as the project name. The
    # collision check is on the middle dir under `parent`.
    if name is not None and name.strip():
        verdict = check_worktree_name(str(abs_repo), name)
        if not verdict.get("available"):
            return {"error": str(verdict.get("reason") or "invalid_name")}
        name = name.strip()
    else:
        name = generate_unique_name(
            parent, is_taken=lambda n: _branch_exists(abs_repo, n)
        )
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

    return {"path": str(path), "branch": name, "repo_root": str(abs_repo)}


def _prune_empty_dirs(start: Path) -> None:
    """Remove now-empty dirs from `start` up to (not including) the workspaces
    root — used after a worktree is removed so the `<branch>` middle dir (and an
    emptied `<project>-worktrees` parent) don't linger.
    """
    root = workspaces_root().resolve()
    current = start.resolve()
    while current != root and str(current).startswith(str(root) + os.sep):
        try:
            # Finder drops a `.DS_Store` into any folder it has shown, which
            # would otherwise make rmdir fail and leave the `<branch>` dir
            # behind forever. It is pure Finder metadata, safe to drop.
            entries = list(current.iterdir())
            if entries and all(e.name == ".DS_Store" for e in entries):
                for e in entries:
                    e.unlink()
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
    bare `detached` line. Git >= 2.36 adds `prunable <reason>` when the
    checkout directory is gone but the registration remains.
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
        elif raw_line == "prunable" or raw_line.startswith("prunable "):
            current["prunable"] = True
    return records


def list_worktrees(cwd: str) -> dict[str, Any]:
    """List a repo's linked worktrees, plus where its main checkout is.

    Returns `{"main_path", "main_display_path", "main_branch", "worktrees":
    [{path, display_path, branch, head, managed, prunable}]}` or `{"error":
    "not_a_repo"}`. `cwd` may be any directory of the repo — a subfolder or a
    linked worktree — which is what makes `main_path` useful: it lets a client
    resolve whatever path it holds to the repo's root (the project's folder)
    and tell "this cwd *is* a worktree" from "this cwd is the checkout".
    `main_branch` is what the main checkout has checked out (`""` when
    detached), so a caller addressing checkouts by branch name — `vicoa
    session update --worktree` — can tell "back to main" from a worktree.
    `managed` marks worktrees the daemon created (under `~/vicoa/workspaces/`)
    — only those are removable by the app; the user's own hand-made worktrees
    are flagged unmanaged.

    `display_path` is the home-collapsed form (`~/…`) produced by the same
    helper a session's `project` is registered with, so the app can match a
    worktree to the sessions running in it by plain string equality.
    `prunable` is git's own verdict that the checkout directory is gone while
    the registration lingers — the app shows such a worktree as deleted.
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
    if not records:
        return {"error": "not_a_repo"}
    # The first record is always the main worktree: reported on its own, not
    # in the list (it is never removable and never a "worktree" to the app).
    main_path = records[0]["path"]
    linked = records[1:]

    worktrees = [
        {
            "path": rec["path"],
            "display_path": get_project_path(rec["path"]),
            "branch": rec.get("branch", ""),
            "head": rec.get("head", ""),
            "managed": _is_managed(rec["path"]),
            "prunable": bool(rec.get("prunable", False)),
        }
        for rec in linked
    ]
    return {
        "main_path": main_path,
        "main_display_path": get_project_path(main_path),
        "main_branch": records[0].get("branch", ""),
        "worktrees": worktrees,
    }


def remove_worktree(
    cwd: str, worktree_path: str, force: bool = False
) -> dict[str, Any]:
    """Remove a worktree's checkout; never delete its branch.

    Confinement is by identity, not path prefix: `worktree_path` must be a real
    *linked* worktree of the repo at `cwd` (managed or hand-made), checked
    against `git worktree list`. Since that listing drops the main worktree,
    the main checkout is never removable, and an existing path that isn't a
    worktree is rejected as `not_a_worktree`. The branch is always kept, so
    commits stay recoverable from a desktop.

    `cwd` should be the repo's MAIN checkout, not the worktree itself: a
    worktree whose directory is already gone (removed by hand, or by an earlier
    removal whose RPC timed out) cannot host the git call. Such a stale entry
    is still removed cleanly from the main checkout (git prunes it), and a path
    that is neither on disk nor registered is reported as already removed —
    idempotent, so the app can always finish its own bookkeeping.

    A managed worktree is not unlinked here: it is renamed into the project's
    `.trash/` and unregistered (milliseconds), and its files are reclaimed on a
    background thread — see `_remove_via_trash`. A hand-made worktree goes
    through plain `git worktree remove`, which deletes inline; the user's own
    folders are never moved around.

    Returns `{"ok": True}` (with `"already_removed": True` for the no-op case)
    or `{"error": ...}`.
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
        if resolved.exists():
            return {"error": "not_a_worktree"}
        # Nothing on disk and nothing registered: it is already gone. Still
        # sweep the `<branch>` middle dir a previous removal may have left.
        _prune_empty_dirs(resolved.parent)
        return {"ok": True, "already_removed": True}

    if _is_managed(str(resolved)):
        trashed = _remove_via_trash(abs_repo, resolved, force)
        if trashed is not None:
            return trashed

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


# ── Fast removal: rename away now, reclaim disk in the background ─────────────
#
# `git worktree remove` unlinks the whole checkout inline, and a checkout with
# node_modules / a venv in it is tens of thousands of files — seconds on a warm
# cache, far more on a cold one — during which the app's delete sits waiting on
# the RPC. Renaming the folder into a sibling `.trash/` is a single atomic
# metadata op (same parent → same volume): from then on git and the filesystem
# both agree the worktree is gone, and the only work left is reclaiming space,
# which no one needs to wait for. A crash mid-reclaim leaves plain garbage under
# `.trash/`, which the daemon sweeps on its next start.

TRASH_DIR_NAME = ".trash"

# Reclaim threads in flight (weak, so finished ones vanish); tests wait on them.
_reclaimers: "weakref.WeakSet[threading.Thread]" = weakref.WeakSet()


def _git_stderr(proc: subprocess.CompletedProcess[bytes], fallback: str) -> str:
    return proc.stderr.decode("utf-8", errors="replace").strip() or fallback


def _refuse_unless_forced(worktree: Path) -> str | None:
    """git's own preconditions for an un-forced `worktree remove`, as an error
    string (or None when the worktree may go). Mirrors builtin/worktree.c:
    no submodules in the index, and `status --porcelain` empty — ignored files
    (node_modules, build output) don't count, exactly as for git."""
    ls = subprocess.run(
        ["git", "-C", str(worktree), "ls-files", "--stage"],
        capture_output=True,
        check=False,
    )
    if ls.returncode == 0 and any(
        line.startswith(b"160000 ") for line in ls.stdout.splitlines()
    ):
        return "working trees containing submodules cannot be moved or removed"
    status = subprocess.run(
        [
            "git",
            "-C",
            str(worktree),
            "status",
            "--porcelain",
            "--ignore-submodules=none",
        ],
        capture_output=True,
        check=False,
    )
    if status.returncode != 0:
        return _git_stderr(status, "status_failed")
    if status.stdout.strip():
        return (
            f"fatal: '{worktree}' contains modified or untracked files, "
            "use --force to delete it"
        )
    return None


def _remove_via_trash(
    abs_repo: Path, worktree: Path, force: bool
) -> dict[str, Any] | None:
    """Rename `worktree` into `<project>-worktrees/.trash/` and unregister it.

    Returns the RPC result, or None when the rename itself is impossible (a
    cross-volume layout, or Windows refusing to move a folder with open handles)
    so the caller falls back to the plain synchronous `git worktree remove`.
    An un-forced call keeps git's refusals (dirty tree, submodules); a locked
    worktree is refused by git after the rename, and moved straight back.
    """
    if not force:
        refusal = _refuse_unless_forced(worktree)
        if refusal is not None:
            return {"error": refusal}

    trash_root = worktrees_parent_dir(abs_repo) / TRASH_DIR_NAME
    try:
        trash_root.mkdir(parents=True, exist_ok=True)
        target = trash_root / f"{worktree.parent.name}-{time.time_ns()}"
        os.rename(worktree, target)
    except OSError:
        return None

    # The registration now points at a missing folder; `remove` on that path
    # drops it (like it does for a checkout deleted by hand) and keeps the branch.
    proc = subprocess.run(
        ["git", "-C", str(abs_repo), "worktree", "remove", "--force", str(worktree)],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        # Locked, most likely. Nothing was deleted, so undo the rename and
        # report git's reason — the worktree is exactly as it was.
        try:
            os.rename(target, worktree)
        except OSError:
            pass
        return {"error": _git_stderr(proc, "remove_failed")}

    _prune_empty_dirs(worktree.parent)
    _reclaim_in_background(target)
    return {"ok": True}


def _reclaim(trash_dir: Path) -> None:
    """Delete one trashed checkout, then tidy an emptied `.trash/` + parent."""
    shutil.rmtree(trash_dir, ignore_errors=True)
    _prune_empty_dirs(trash_dir.parent)


def _reclaim_in_background(trash_dir: Path) -> threading.Thread:
    thread = threading.Thread(
        target=_reclaim,
        args=(trash_dir,),
        name="vicoa-worktree-reclaim",
        daemon=True,
    )
    _reclaimers.add(thread)
    thread.start()
    return thread


def wait_for_reclaims(timeout: float = 30.0) -> None:
    """Block until every in-flight reclaim has finished (tests / shutdown)."""
    deadline = time.monotonic() + timeout
    for thread in list(_reclaimers):
        thread.join(timeout=max(0.0, deadline - time.monotonic()))


def sweep_trash() -> int:
    """Reclaim whatever an earlier daemon left under any `<project>-worktrees/.trash/`
    (it exited mid-delete). Returns the number of folders handed to reclaimers.
    Confined to the workspaces root: nothing outside it is ever touched.
    """
    root = workspaces_root()
    if not root.is_dir():
        return 0
    count = 0
    for parent in root.iterdir():
        trash_root = parent / TRASH_DIR_NAME
        if not trash_root.is_dir():
            continue
        for leftover in trash_root.iterdir():
            if leftover.is_dir() and not leftover.is_symlink():
                _reclaim_in_background(leftover)
                count += 1
    return count
