"""`get_worktree_name` — the signal that lets the sidebar sub-group by worktree.

Every case runs against a real temp git repo, because the whole point of the
helper is that it asks git rather than pattern-matching paths. The submodule
test is the load-bearing one: the obvious "is the common dir's parent the
worktree root?" implementation passes every other test here and still mislabels
every submodule checkout as a worktree.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from vicoa.utils import get_worktree_name


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True
    )


def _init(repo: Path) -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "seed.txt").write_text("seed\n")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-q", "-m", "seed")
    return repo


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _init(tmp_path / "src" / "my-app")


def test_main_checkout_has_no_worktree_name(repo: Path):
    assert get_worktree_name(str(repo)) is None


def test_linked_worktree_reports_its_branch(repo: Path, tmp_path: Path):
    checkout = tmp_path / "wt" / "brave-otter" / "my-app"
    _git(repo, "worktree", "add", "-q", "-b", "brave-otter", str(checkout))

    assert get_worktree_name(str(checkout)) == "brave-otter"


def test_subdirectory_of_a_worktree_still_reports_the_branch(
    repo: Path, tmp_path: Path
):
    checkout = tmp_path / "wt" / "calm-river" / "my-app"
    _git(repo, "worktree", "add", "-q", "-b", "calm-river", str(checkout))
    nested = checkout / "pkg" / "deep"
    nested.mkdir(parents=True)

    assert get_worktree_name(str(nested)) == "calm-river"


def test_detached_worktree_falls_back_to_its_directory_name(repo: Path, tmp_path: Path):
    head = _git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    checkout = tmp_path / "wt" / "detached-leaf"
    _git(repo, "worktree", "add", "-q", "--detach", str(checkout), head)

    assert get_worktree_name(str(checkout)) == "detached-leaf"


def test_submodule_checkout_is_not_a_worktree(tmp_path: Path):
    """A submodule's git-common-dir is `<super>/.git/modules/<name>`.

    Its parent is `modules/`, never the submodule root — so a parent-vs-root
    comparison flags it as a linked worktree. vicoa-backend is itself a
    submodule of vicoa-ai, so that bug would mislabel this repo's own sessions.
    """
    inner = _init(tmp_path / "origin" / "inner")
    super_repo = _init(tmp_path / "super")
    subprocess.run(
        [
            "git",
            "-C",
            str(super_repo),
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "-q",
            "add",
            str(inner),
            "inner",
        ],
        check=True,
        capture_output=True,
    )

    assert get_worktree_name(str(super_repo / "inner")) is None


def test_non_git_directory_is_none(tmp_path: Path):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()

    assert get_worktree_name(str(plain)) is None


def test_missing_directory_is_none(tmp_path: Path):
    assert get_worktree_name(str(tmp_path / "nope")) is None


def test_tilde_paths_are_expanded(repo: Path, tmp_path: Path, monkeypatch):
    """Callers pass `project`, which is stored tilde-abbreviated."""
    checkout = tmp_path / "home" / "wt" / "swift-fox" / "my-app"
    _git(repo, "worktree", "add", "-q", "-b", "swift-fox", str(checkout))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    assert get_worktree_name("~/wt/swift-fox/my-app") == "swift-fox"


def test_git_failure_never_raises(monkeypatch, repo: Path):
    def boom(*_args, **_kwargs):
        raise OSError("git not found")

    monkeypatch.setattr(subprocess, "run", boom)

    assert get_worktree_name(str(repo)) is None
