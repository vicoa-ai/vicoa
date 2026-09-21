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


def test_create_worktree_with_a_name_uses_it_for_branch_and_dir(
    home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import create_worktree

    result = create_worktree(str(committed_repo), name=" feat-login ")

    assert "error" not in result, result
    assert result["branch"] == "feat-login"
    path = Path(result["path"])
    assert _worktree_branch(path) == "feat-login"
    # Same layout as a random name: the user's name is the middle dir.
    assert path.parent.name == "feat-login"
    assert path.name == "my-app"


def test_create_worktree_with_a_slash_name_nests_the_middle_dir(
    home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import create_worktree

    result = create_worktree(str(committed_repo), name="feat/login")

    assert "error" not in result, result
    assert result["branch"] == "feat/login"
    path = Path(result["path"])
    assert _worktree_branch(path) == "feat/login"
    assert path.parent.parent.name == "feat"
    assert path.parent.parent.parent.name == "my-app-worktrees"


def test_create_worktree_with_a_taken_name_errors_instead_of_suffixing(
    home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import create_worktree

    first = create_worktree(str(committed_repo), name="feat-login")
    assert "error" not in first, first

    # The user asked for THAT name: a silent `feat-login-2` would be a surprise.
    assert create_worktree(str(committed_repo), name="feat-login") == {
        "error": "name_taken"
    }
    # An existing branch (no worktree) is equally taken.
    _git(committed_repo, "branch", "hotfix")
    assert create_worktree(str(committed_repo), name="hotfix") == {
        "error": "name_taken"
    }


def test_create_worktree_with_an_invalid_name_errors(home: Path, committed_repo: Path):
    from vicoa.rpc.worktree_ops import create_worktree

    for bad in ("has space", "-leading-dash", "two..dots", "trailing.lock"):
        assert create_worktree(str(committed_repo), name=bad) == {
            "error": "invalid_name"
        }, bad


def test_create_worktree_with_a_blank_name_falls_back_to_random(
    home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import create_worktree

    result = create_worktree(str(committed_repo), name="   ")

    assert "error" not in result, result
    assert result["branch"].strip() and result["branch"] != "   "


# --- check_worktree_name ------------------------------------------------------


def test_check_worktree_name_free_name_is_available(home: Path, committed_repo: Path):
    from vicoa.rpc.worktree_ops import check_worktree_name

    assert check_worktree_name(str(committed_repo), "feat-login") == {"available": True}


def test_check_worktree_name_taken_name_suggests_a_free_suffix(
    home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import check_worktree_name, create_worktree

    create_worktree(str(committed_repo), name="feat-login")
    create_worktree(str(committed_repo), name="feat-login-2")

    assert check_worktree_name(str(committed_repo), "feat-login") == {
        "available": False,
        "reason": "name_taken",
        "suggestion": "feat-login-3",
    }


def test_check_worktree_name_existing_branch_is_taken(home: Path, committed_repo: Path):
    from vicoa.rpc.worktree_ops import check_worktree_name

    _git(committed_repo, "branch", "hotfix")

    verdict = check_worktree_name(str(committed_repo), "hotfix")
    assert verdict["available"] is False
    assert verdict["reason"] == "name_taken"
    assert verdict["suggestion"] == "hotfix-2"


def test_check_worktree_name_invalid_ref_has_no_suggestion(
    home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import check_worktree_name

    assert check_worktree_name(str(committed_repo), "has space") == {
        "available": False,
        "reason": "invalid_name",
    }
    assert check_worktree_name(str(committed_repo), "") == {
        "available": False,
        "reason": "invalid_name",
    }


def test_check_worktree_name_on_non_repo_returns_error(home: Path, tmp_path: Path):
    from vicoa.rpc.worktree_ops import check_worktree_name

    plain = tmp_path / "plain"
    plain.mkdir()

    assert check_worktree_name(str(plain), "feat") == {"error": "not_a_repo"}


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


def test_list_worktrees_reports_display_path_in_session_form(
    home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import create_worktree, list_worktrees

    created = create_worktree(str(committed_repo))

    [entry] = list_worktrees(str(committed_repo))["worktrees"]

    # `display_path` collapses HOME to `~` exactly like a session's registered
    # `project`, so the app can match a worktree to its sessions by equality.
    assert entry["display_path"].startswith("~/vicoa/workspaces/")
    assert entry["display_path"] == "~" + created["path"][len(str(home)) :]
    assert entry["prunable"] is False


def test_list_worktrees_flags_a_checkout_whose_directory_is_gone(
    home: Path, committed_repo: Path
):
    import shutil

    from vicoa.rpc.worktree_ops import create_worktree, list_worktrees

    created = create_worktree(str(committed_repo))
    shutil.rmtree(created["path"])  # removed behind git's back

    [entry] = list_worktrees(str(committed_repo))["worktrees"]

    assert entry["branch"] == created["branch"]
    assert entry["prunable"] is True


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
    # A hand-made worktree is deleted in place, never moved into our trash.
    assert not (home / "vicoa" / "workspaces").exists()
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


def test_remove_worktree_refuses_existing_dir_that_is_not_a_worktree(
    home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import remove_worktree
    from vicoa.rpc.worktree_paths import worktree_dir_for

    # A real directory under the workspaces root, but never a worktree of the
    # repo — confinement by identity must refuse to touch it.
    impostor = worktree_dir_for(committed_repo, "impostor")
    impostor.mkdir(parents=True)
    (impostor / "keep.txt").write_text("mine\n")

    assert remove_worktree(str(committed_repo), str(impostor), force=True) == {
        "error": "not_a_worktree"
    }
    assert (impostor / "keep.txt").exists()


def test_remove_worktree_is_a_noop_when_nothing_is_there(
    home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import remove_worktree
    from vicoa.rpc.worktree_paths import worktree_dir_for

    # Neither on disk nor registered: the app may be finishing bookkeeping for
    # a worktree that was already removed. Idempotent, distinguishable.
    ghost = worktree_dir_for(committed_repo, "ghost")

    assert remove_worktree(str(committed_repo), str(ghost), force=True) == {
        "ok": True,
        "already_removed": True,
    }


def test_remove_worktree_removes_a_stale_registration_from_the_main_checkout(
    home: Path, committed_repo: Path
):
    import shutil

    from vicoa.rpc.worktree_ops import create_worktree, list_worktrees, remove_worktree

    created = create_worktree(str(committed_repo))
    path = Path(created["path"])
    shutil.rmtree(path)  # the directory is gone; git still lists it as prunable
    assert list_worktrees(str(committed_repo))["worktrees"]

    # From the worktree's own (now missing) path nothing can run — this is the
    # `not_a_repo` the app used to surface; the main checkout must be the cwd.
    assert remove_worktree(created["path"], created["path"], force=True) == {
        "error": "not_a_repo"
    }
    result = remove_worktree(str(committed_repo), created["path"], force=True)

    assert result == {"ok": True}
    assert list_worktrees(str(committed_repo))["worktrees"] == []
    assert not path.parent.exists()  # the <branch> middle dir is swept too
    assert _branch_exists(committed_repo, created["branch"])


def test_remove_worktree_prunes_branch_dir_despite_finder_ds_store(
    home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import create_worktree, remove_worktree

    created = create_worktree(str(committed_repo))
    path = Path(created["path"])
    middle = path.parent
    (middle / ".DS_Store").write_bytes(b"\0")  # Finder browsed the folder

    assert remove_worktree(str(committed_repo), created["path"], force=False) == {
        "ok": True
    }
    assert not middle.exists()


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


def test_remove_worktree_trashes_managed_checkout_then_reclaims(
    home: Path, committed_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    """A managed worktree is renamed into `.trash/` and unregistered at once;
    unlinking its files is deferred to a background reclaim, so a checkout
    full of node_modules never holds the RPC (and the app's dialog) open."""
    from vicoa.rpc import worktree_ops
    from vicoa.rpc.worktree_ops import (
        TRASH_DIR_NAME,
        create_worktree,
        list_worktrees,
        remove_worktree,
    )

    created = create_worktree(str(committed_repo))
    path = Path(created["path"])
    (path / "node_modules").mkdir()
    (path / "node_modules" / "big.js").write_text("x" * 1024)

    # Capture the deferred reclaim instead of running it, so the intermediate
    # state (folder trashed, nothing unlinked yet) can be observed.
    deferred: list[Path] = []
    monkeypatch.setattr(worktree_ops, "_reclaim_in_background", deferred.append)

    assert remove_worktree(str(committed_repo), created["path"], force=True) == {
        "ok": True
    }

    # Gone as far as git and the original path are concerned, branch kept.
    assert not path.exists()
    assert not path.parent.exists()  # <branch> middle dir pruned immediately
    assert list_worktrees(str(committed_repo))["worktrees"] == []
    assert _branch_exists(committed_repo, created["branch"])
    # ...but the files themselves are still on disk, parked under .trash.
    assert len(deferred) == 1
    trashed = deferred[0]
    assert trashed.parent == path.parent.parent / TRASH_DIR_NAME
    assert (trashed / "node_modules" / "big.js").is_file()

    worktree_ops._reclaim(trashed)

    assert not trashed.exists()
    assert not trashed.parent.exists()  # emptied .trash is tidied away
    assert not trashed.parent.parent.exists()  # and the <project>-worktrees dir


def test_remove_worktree_reclaim_runs_on_a_background_thread(
    home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import (
        TRASH_DIR_NAME,
        create_worktree,
        remove_worktree,
        wait_for_reclaims,
    )

    created = create_worktree(str(committed_repo))
    path = Path(created["path"])
    (path / "scratch.txt").write_text("scratch\n")
    parent = path.parent.parent

    assert remove_worktree(str(committed_repo), created["path"], force=True) == {
        "ok": True
    }
    wait_for_reclaims()

    assert not (parent / TRASH_DIR_NAME).exists()
    assert not parent.exists()


def test_remove_worktree_unforced_ignores_ignored_files(
    home: Path, committed_repo: Path
):
    """git's cleanliness test skips ignored files (node_modules, build output),
    and so must ours — otherwise every real worktree would count as dirty."""
    from vicoa.rpc.worktree_ops import create_worktree, remove_worktree

    (committed_repo / ".git" / "info" / "exclude").write_text("node_modules/\n")
    created = create_worktree(str(committed_repo))
    path = Path(created["path"])
    (path / "node_modules").mkdir()
    (path / "node_modules" / "dep.js").write_text("module.exports = 1\n")

    assert remove_worktree(str(committed_repo), created["path"], force=False) == {
        "ok": True
    }
    assert not path.exists()


def test_remove_worktree_unforced_refuses_submodules(
    home: Path, committed_repo: Path, tmp_path: Path
):
    from vicoa.rpc.worktree_ops import create_worktree, remove_worktree

    # A second repo to embed as a submodule of the first.
    sub = tmp_path / "sub"
    sub.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(sub)], check=True)
    _git(sub, "config", "user.email", "test@example.com")
    _git(sub, "config", "user.name", "Test")
    _git(sub, "config", "commit.gpgsign", "false")
    (sub / "s.txt").write_text("s\n")
    _git(sub, "add", "s.txt")
    _git(sub, "commit", "-q", "-m", "sub")
    _git(
        committed_repo,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(sub),
        "vendor/sub",
    )
    _git(committed_repo, "commit", "-q", "-m", "add submodule")

    created = create_worktree(str(committed_repo))
    path = Path(created["path"])

    refused = remove_worktree(str(committed_repo), created["path"], force=False)
    assert "submodules" in refused.get("error", "")
    assert path.exists()

    assert remove_worktree(str(committed_repo), created["path"], force=True) == {
        "ok": True
    }
    assert not path.exists()


def test_remove_worktree_locked_is_refused_and_left_in_place(
    home: Path, committed_repo: Path
):
    from vicoa.rpc.worktree_ops import create_worktree, list_worktrees, remove_worktree

    created = create_worktree(str(committed_repo))
    path = Path(created["path"])
    (path / "keep.txt").write_text("keep\n")
    _git(committed_repo, "worktree", "lock", "--reason", "in use", str(path))

    result = remove_worktree(str(committed_repo), created["path"], force=True)

    assert "locked" in result.get("error", "")
    # The rename was undone: the checkout is exactly where it was, files intact,
    # still registered.
    assert (path / "keep.txt").is_file()
    assert [w["path"] for w in list_worktrees(str(committed_repo))["worktrees"]] == [
        str(path)
    ]


def test_sweep_trash_reclaims_what_an_earlier_daemon_left(home: Path):
    from vicoa.rpc.worktree_ops import TRASH_DIR_NAME, sweep_trash, wait_for_reclaims
    from vicoa.rpc.worktree_paths import workspaces_root

    parent = workspaces_root() / "my-app-worktrees"
    leftover = parent / TRASH_DIR_NAME / "feat-1234"
    leftover.mkdir(parents=True)
    (leftover / "node_modules").mkdir()
    (leftover / "node_modules" / "dep.js").write_text("1\n")
    # A live worktree dir beside it must be left alone.
    live = parent / "other" / "my-app"
    live.mkdir(parents=True)

    assert sweep_trash() == 1
    wait_for_reclaims()

    assert not leftover.exists()
    assert not (parent / TRASH_DIR_NAME).exists()
    assert live.is_dir()


def test_sweep_trash_without_a_workspaces_root_is_a_noop(home: Path):
    from vicoa.rpc.worktree_ops import sweep_trash

    assert sweep_trash() == 0


def test_list_worktrees_reports_the_main_checkout_from_any_path(
    home: Path, committed_repo: Path
):
    """`main_path` is the repo root whether asked from the checkout, a
    subfolder of it, or a linked worktree — what lets a client resolve the
    path it holds to the project's folder."""
    from vicoa.rpc.worktree_ops import create_worktree, list_worktrees

    (committed_repo / "apps" / "web").mkdir(parents=True)
    created = create_worktree(str(committed_repo))
    main = str(committed_repo.resolve())

    for cwd in (committed_repo, committed_repo / "apps" / "web", created["path"]):
        result = list_worktrees(str(cwd))
        assert "error" not in result, (cwd, result)
        assert str(Path(result["main_path"]).resolve()) == main
        assert result["main_display_path"]


def test_create_worktree_from_a_subfolder_forks_the_whole_repo(
    home: Path, committed_repo: Path
):
    """A monorepo session at `repo/apps/web` must fork `repo`, not treat the
    subfolder as the project: the checkout leaf and the managed root are keyed
    on the repo, and `repo_root` says which."""
    from vicoa.rpc.worktree_ops import create_worktree

    (committed_repo / "apps" / "web").mkdir(parents=True)
    created = create_worktree(str(committed_repo / "apps" / "web"), name="feat/x")

    assert "error" not in created, created
    assert Path(created["repo_root"]).resolve() == committed_repo.resolve()
    assert Path(created["path"]).name == committed_repo.name
    assert (Path(created["path"]) / "seed.txt").is_file()
