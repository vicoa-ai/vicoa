"""Daemon-side worktree ops — create / list / remove.

Each test drives one slice of the worktree lifecycle against a real temp git
repo. HOME is redirected per-test so `~/vicoa/workspaces` lands under tmp_path
and never touches the developer's machine.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True
    )


@pytest.fixture
def committed_repo(tmp_path: Path) -> Path:
    """An initialized git repo with one commit on `main`."""
    repo = tmp_path / "src" / "my-app"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "seed.txt").write_text("seed\n")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-q", "-m", "seed")
    return repo


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect HOME so the workspaces root lives under tmp_path."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    return h


def _worktree_branch(path: Path) -> str:
    return (
        subprocess.run(
            ["git", "-C", str(path), "branch", "--show-current"],
            check=True,
            capture_output=True,
        )
        .stdout.decode()
        .strip()
    )


# --- create_worktree ----------------------------------------------------------


def test_create_worktree_makes_a_checkout_on_a_new_branch(
    home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import create_worktree

    result = create_worktree(str(committed_repo))

    assert "error" not in result, result
    path = Path(result["path"])
    assert path.is_dir()
    # The worktree is checked out on the freshly-created branch...
    assert _worktree_branch(path) == result["branch"]
    # ...laid out as <workspaces>/<project>-worktrees/<branch>/<project> so the
    # leaf (the session's cwd) is the project name, not the branch slug.
    root = home / "vicoa" / "workspaces"
    assert str(path).startswith(str(root.resolve()))
    assert path.name == "my-app"
    assert path.parent.name == result["branch"]
    assert path.parent.parent.name == "my-app-worktrees"


def test_create_worktree_on_non_repo_returns_structured_error(
    home: Path, tmp_path: Path
):
    from vicoa.rpc.worktree_ops import create_worktree

    plain = tmp_path / "plain"
    plain.mkdir()

    assert create_worktree(str(plain)) == {"error": "not_a_repo"}


def test_create_worktree_on_repo_without_commits_succeeds_gracefully(
    home: Path, tmp_path: Path
):
    from vicoa.rpc.worktree_ops import create_worktree

    repo = tmp_path / "empty"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)

    # Unborn HEAD: git creates the worktree on a fresh unborn branch rather
    # than failing. The handler must not crash and must return a well-formed
    # result (the empty-checkout case is a UI concern, not a daemon error).
    result = create_worktree(str(repo))
    assert "error" not in result, result
    assert Path(result["path"]).is_dir()


def test_two_worktrees_in_same_repo_are_distinct(home: Path, committed_repo: Path):
    from vicoa.rpc.worktree_ops import create_worktree

    r1 = create_worktree(str(committed_repo))
    r2 = create_worktree(str(committed_repo))

    assert r1["path"] != r2["path"]
    assert r1["branch"] != r2["branch"]
    assert Path(r1["path"]).is_dir()
    assert Path(r2["path"]).is_dir()


# --- list_worktrees -----------------------------------------------------------


def test_list_worktrees_returns_managed_worktree_and_excludes_main(
    home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import create_worktree, list_worktrees

    created = create_worktree(str(committed_repo))

    result = list_worktrees(str(committed_repo))
    assert "error" not in result, result
    worktrees = result["worktrees"]

    # The main worktree (the repo itself) is never listed.
    resolved_paths = {str(Path(w["path"]).resolve()) for w in worktrees}
    assert str(committed_repo.resolve()) not in resolved_paths

    # The freshly-created worktree is listed, on its branch, flagged managed.
    match = next(w for w in worktrees if w["branch"] == created["branch"])
    assert str(Path(match["path"]).resolve()) == str(Path(created["path"]).resolve())
    assert match["managed"] is True
    assert len(match["head"]) >= 7


def test_list_worktrees_flags_unmanaged_worktrees(
    home: Path, committed_repo: Path, tmp_path: Path
):
    from vicoa.rpc.worktree_ops import list_worktrees

    # A worktree the user made by hand, OUTSIDE ~/vicoa/workspaces.
    hand_made = tmp_path / "hand-made-wt"
    subprocess.run(
        [
            "git",
            "-C",
            str(committed_repo),
            "worktree",
            "add",
            "-b",
            "manual",
            str(hand_made),
        ],
        check=True,
        capture_output=True,
    )

    worktrees = list_worktrees(str(committed_repo))["worktrees"]
    match = next(w for w in worktrees if w["branch"] == "manual")
    assert match["managed"] is False


def test_list_worktrees_on_non_repo_returns_error(home: Path, tmp_path: Path):
    from vicoa.rpc.worktree_ops import list_worktrees

    plain = tmp_path / "plain"
    plain.mkdir()
    assert list_worktrees(str(plain)) == {"error": "not_a_repo"}


# --- remove_worktree ----------------------------------------------------------


def _branch_exists(repo: Path, name: str) -> bool:
    return (
        subprocess.run(
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
        ).returncode
        == 0
    )


def test_remove_worktree_deletes_checkout_but_keeps_branch(
    home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import create_worktree, remove_worktree

    created = create_worktree(str(committed_repo))
    path = Path(created["path"])
    assert path.is_dir()

    result = remove_worktree(str(committed_repo), created["path"], force=False)

    assert result == {"ok": True}
    assert not path.exists()
    # The branch survives -> commits made in the worktree are recoverable.
    assert _branch_exists(committed_repo, created["branch"])


def test_remove_worktree_prunes_empty_branch_dir(home: Path, committed_repo: Path):
    from vicoa.rpc.worktree_ops import create_worktree, remove_worktree

    created = create_worktree(str(committed_repo))
    path = Path(created["path"])
    middle = path.parent  # the <branch> dir

    remove_worktree(str(committed_repo), created["path"], force=False)

    # git removes the checkout leaf but leaves the <branch> middle dir behind;
    # the handler prunes it so <project>-worktrees doesn't fill with empties.
    assert not path.exists()
    assert not middle.exists()


def test_remove_worktree_allows_unmanaged_worktree(
    home: Path, committed_repo: Path, tmp_path: Path
):
    from vicoa.rpc.worktree_ops import remove_worktree

    # A worktree the user made by hand, outside ~/vicoa/workspaces. Removal is
    # confined by identity to real worktrees of the repo, not to the managed
    # root, so this is removable — but the branch is kept.
    hand_made = tmp_path / "hand-made-wt"
    subprocess.run(
        [
            "git",
            "-C",
            str(committed_repo),
            "worktree",
            "add",
            "-b",
            "manual",
            str(hand_made),
        ],
        check=True,
        capture_output=True,
    )

    result = remove_worktree(str(committed_repo), str(hand_made), force=True)

    assert result == {"ok": True}
    assert not hand_made.exists()  # checkout removed
    # The branch survives, so commits stay recoverable.
    branch_check = subprocess.run(
        [
            "git",
            "-C",
            str(committed_repo),
            "rev-parse",
            "--verify",
            "--quiet",
            "refs/heads/manual",
        ],
        capture_output=True,
        check=False,
    )
    assert branch_check.returncode == 0


def test_remove_worktree_refuses_managed_path_that_is_not_a_worktree(
    home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import remove_worktree
    from vicoa.rpc.worktree_paths import worktree_dir_for

    # A path under the workspaces root for this repo, but no such worktree.
    ghost = worktree_dir_for(committed_repo, "ghost")

    assert remove_worktree(str(committed_repo), str(ghost), force=True) == {
        "error": "not_a_worktree"
    }


def test_remove_worktree_dirty_needs_force(home: Path, committed_repo: Path):
    from vicoa.rpc.worktree_ops import create_worktree, remove_worktree

    created = create_worktree(str(committed_repo))
    path = Path(created["path"])
    # Make the worktree dirty.
    (path / "untracked.txt").write_text("scratch\n")

    # Without force, git refuses to drop a dirty worktree.
    refused = remove_worktree(str(committed_repo), created["path"], force=False)
    assert "error" in refused
    assert path.exists()

    # With force, it goes.
    forced = remove_worktree(str(committed_repo), created["path"], force=True)
    assert forced == {"ok": True}
    assert not path.exists()
