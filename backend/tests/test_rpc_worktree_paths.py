"""Path confinement for daemon-side worktree ops.

Worktrees live OUTSIDE any user repo, under a daemon-computed root
(`~/vicoa/workspaces/<project>-worktrees/<branch>/<project>`). The app never
supplies a write path; the daemon computes the target and refuses to remove
anything that does not resolve under that root. This suite is the golden table
for that contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_assert_managed_worktree_rejects_path_outside_workspaces_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from vicoa.rpc import worktree_paths

    monkeypatch.setenv("HOME", str(tmp_path))

    with pytest.raises(worktree_paths.UnmanagedWorktree):
        worktree_paths.assert_managed_worktree("/etc/passwd")


def test_repo_basename_is_project_folder_name(tmp_path: Path):
    from vicoa.rpc import worktree_paths

    repo = tmp_path / "my-app"
    repo.mkdir()
    assert worktree_paths.repo_basename(repo) == "my-app"


def test_worktree_dir_for_nests_branch_then_project_basename(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from vicoa.rpc import worktree_paths

    monkeypatch.setenv("HOME", str(tmp_path))
    repo = tmp_path / "proj" / "my-app"
    repo.mkdir(parents=True)

    target = worktree_paths.worktree_dir_for(repo, "brave-river")
    root = worktree_paths.workspaces_root()

    # <workspaces>/my-app-worktrees/brave-river/my-app
    assert target == root / "my-app-worktrees" / "brave-river" / "my-app"
    # Leaf is the project name (so the session's `project` reads as the
    # project, not the branch); the branch is the middle dir.
    assert target.name == "my-app"
    assert target.parent.name == "brave-river"


def test_worktree_dir_for_lands_under_workspaces_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from vicoa.rpc import worktree_paths

    monkeypatch.setenv("HOME", str(tmp_path))
    repo = tmp_path / "proj" / "my-app"
    repo.mkdir(parents=True)

    target = worktree_paths.worktree_dir_for(repo, "brave-river")

    # Confinement check passes for the freshly-computed nested target.
    target.mkdir(parents=True)
    assert worktree_paths.assert_managed_worktree(target) == target.resolve()


def test_assert_managed_worktree_rejects_symlink_escape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from vicoa.rpc import worktree_paths

    monkeypatch.setenv("HOME", str(tmp_path))
    root = worktree_paths.workspaces_root()
    root.mkdir(parents=True)

    outside = tmp_path / "outside"
    outside.mkdir()
    # A symlink that lives under the root but points outside it.
    link = root / "escape"
    link.symlink_to(outside)

    with pytest.raises(worktree_paths.UnmanagedWorktree):
        worktree_paths.assert_managed_worktree(link)
