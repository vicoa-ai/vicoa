"""Daemon-side git-op RPC handlers — status + diff.

Covers `plans/todos/vicoa-app-git-tab.md` §Phase B git_ops.py. Each test
exercises one slice of the contract; the suite as a whole is the golden table
the Flutter Git tab consumes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _git(repo: Path, *args: str, **kw) -> subprocess.CompletedProcess[bytes]:
    """Run `git -C repo ...` with quiet defaults and check=True."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        **kw,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """An initialized empty git repo at `tmp_path`, branch `main`, no commits."""
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(tmp_path)],
        check=True,
    )
    # Pin identity so commit-creating fixtures further down don't depend on
    # the developer's global git config.
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    return tmp_path


@pytest.fixture
def committed_repo(git_repo: Path) -> Path:
    """A repo with one committed file `seed.txt` on `main`."""
    (git_repo / "seed.txt").write_text("seed\n")
    _git(git_repo, "add", "seed.txt")
    _git(git_repo, "commit", "-q", "-m", "seed")
    return git_repo


# --- git_status: basics --------------------------------------------------------


def test_git_status_clean_repo_returns_branch_main_and_no_changes(
    committed_repo: Path,
):
    from vicoa.rpc.git_ops import git_status

    result = git_status(cwd=str(committed_repo))
    assert result["branch"] == "main"
    assert result["staged"] == []
    assert result["unstaged"] == []
    assert result["untracked"] == []


def test_git_status_non_git_directory_returns_not_a_repo(tmp_path: Path):
    from vicoa.rpc.git_ops import git_status

    result = git_status(cwd=str(tmp_path))
    assert result == {"error": "not_a_repo"}


# --- git_status: file enumeration ---------------------------------------------


def _hash_object(repo: Path, path: str) -> str:
    return _git(repo, "hash-object", path).stdout.decode().strip()


def test_git_status_unstaged_modified_file_is_listed_with_numstat_and_hash(
    committed_repo: Path,
):
    # Worktree-vs-index modification. Numstat is worktree-vs-index; content_hash
    # is the hash of the working-tree content.
    from vicoa.rpc.git_ops import git_status

    (committed_repo / "seed.txt").write_text("seed\nadded\n")
    result = git_status(cwd=str(committed_repo))
    expected_hash = _hash_object(committed_repo, "seed.txt")
    assert result["staged"] == []
    assert result["untracked"] == []
    assert result["unstaged"] == [
        {
            "path": "seed.txt",
            "status": "M",
            "additions": 1,
            "deletions": 0,
            "content_hash": expected_hash,
        }
    ]


def test_git_status_staged_added_file_is_listed_with_index_oid(
    committed_repo: Path,
):
    # Staged add: index vs HEAD. content_hash uses the index OID directly (no
    # hash-object call needed — porcelain v2 carries it as hI).
    from vicoa.rpc.git_ops import git_status

    (committed_repo / "new.txt").write_text("hello\nworld\n")
    _git(committed_repo, "add", "new.txt")
    result = git_status(cwd=str(committed_repo))
    expected_hash = _hash_object(committed_repo, "new.txt")
    assert result["unstaged"] == []
    assert result["untracked"] == []
    assert result["staged"] == [
        {
            "path": "new.txt",
            "status": "A",
            "additions": 2,
            "deletions": 0,
            "content_hash": expected_hash,
        }
    ]


def test_git_status_untracked_file_is_listed_with_line_count(
    committed_repo: Path,
):
    # Untracked: numstat-style additions = line count of the working-tree file,
    # deletions = 0. content_hash from hash-object of working-tree content.
    from vicoa.rpc.git_ops import git_status

    (committed_repo / "notes.txt").write_text("a\nb\nc\n")
    result = git_status(cwd=str(committed_repo))
    expected_hash = _hash_object(committed_repo, "notes.txt")
    assert result["staged"] == []
    assert result["unstaged"] == []
    assert result["untracked"] == [
        {
            "path": "notes.txt",
            "status": "??",
            "additions": 3,
            "deletions": 0,
            "content_hash": expected_hash,
        }
    ]


def test_git_status_expands_files_inside_a_new_directory(committed_repo: Path):
    # The reported bug: at git's default `-unormal` a newly created directory
    # collapses into one `? newdir/` record, so the Git tab showed a single
    # unopenable row and `git_diff` on it returned an empty diff. `-uall` makes
    # git list each file, and each gets its own count and hash.
    from vicoa.rpc.git_ops import git_status

    (committed_repo / "newdir" / "sub").mkdir(parents=True)
    (committed_repo / "newdir" / "one.txt").write_text("a\nb\n")
    (committed_repo / "newdir" / "sub" / "two.txt").write_text("c\n")

    result = git_status(cwd=str(committed_repo))
    assert [e["path"] for e in result["untracked"]] == [
        "newdir/one.txt",
        "newdir/sub/two.txt",
    ]
    assert [e["additions"] for e in result["untracked"]] == [2, 1]
    assert all(e["content_hash"] is not None for e in result["untracked"])


def test_git_diff_of_a_file_in_a_new_directory_renders(committed_repo: Path):
    # The other half of the same bug: with status expanding the directory, each
    # nested path must produce a real synthesized diff rather than the empty
    # stub the directory guard returns.
    from vicoa.rpc.git_ops import git_diff

    (committed_repo / "newdir").mkdir()
    (committed_repo / "newdir" / "one.txt").write_text("a\nb\n")

    result = git_diff(
        cwd=str(committed_repo),
        path="newdir/one.txt",
        staged=False,
        ignore_whitespace=False,
    )
    assert len(result["hunks"]) == 1
    assert [ln["content"] for ln in result["hunks"][0]["lines"]] == ["a", "b"]


def test_git_status_still_collapses_an_embedded_repo_under_uall(
    committed_repo: Path,
):
    # `-uall` expands ordinary directories but git will not descend into one
    # carrying its own `.git`. That record keeps its trailing slash, which is
    # what `git_diff`'s directory guard and the hash-object skip both key on.
    from vicoa.rpc.git_ops import git_status

    nested = committed_repo / "embedded"
    nested.mkdir()
    subprocess.run(["git", "init", "-q", str(nested)], check=True)
    (nested / "x.txt").write_text("x\n")

    result = git_status(cwd=str(committed_repo))
    assert [e["path"] for e in result["untracked"]] == ["embedded/"]
    assert result["untracked"][0]["content_hash"] is None


def test_git_status_untracked_binary_reports_zero_additions(committed_repo: Path):
    # Counting "lines" of a binary is meaningless, and `git_diff` reports the
    # same file as is_binary with no hunks — the two must agree.
    from vicoa.rpc.git_ops import git_status

    (committed_repo / "blob.bin").write_bytes(b"\x00\x01\x02\n\n\n")
    result = git_status(cwd=str(committed_repo))
    assert result["untracked"][0]["additions"] == 0


def test_git_status_untracked_symlink_counts_as_one_line(committed_repo: Path):
    # git stores the target path as the blob content — one line. Following the
    # link would count the target's lines, or fail on a link to a directory.
    from vicoa.rpc.git_ops import git_status

    (committed_repo / "link").symlink_to("seed.txt")
    result = git_status(cwd=str(committed_repo))
    assert result["untracked"] == [
        {
            "path": "link",
            "status": "??",
            "additions": 1,
            "deletions": 0,
            "content_hash": _hash_object(committed_repo, "link"),
        }
    ]


def test_git_status_skips_counting_a_huge_untracked_file(
    committed_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    # Big untracked files are usually generated assets. Reading them on every
    # poll stalls the Git tab, so past the byte cap we report 0 rather than
    # spend the read.
    from vicoa.rpc import git_ops

    monkeypatch.setattr(git_ops, "_MAX_UNTRACKED_LINE_COUNT_BYTES", 8)
    (committed_repo / "small.txt").write_text("a\n")
    (committed_repo / "big.txt").write_text("a\nb\nc\nd\ne\n")

    result = git_ops.git_status(cwd=str(committed_repo))
    counts = {e["path"]: e["additions"] for e in result["untracked"]}
    assert counts == {"small.txt": 1, "big.txt": 0}


def test_untracked_line_count_is_cached_until_the_file_changes(
    committed_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    # Without the cache every poll re-reads every untracked file, which is what
    # makes `-uall` affordable on a repo carrying hundreds of new files.
    from vicoa.rpc import git_ops

    git_ops._untracked_stats_cache.clear()
    target = committed_repo / "notes.txt"
    target.write_text("a\nb\n")

    reads = 0
    real_read = git_ops._read_additions

    def counting_read(abs_file, st):
        nonlocal reads
        reads += 1
        return real_read(abs_file, st)

    monkeypatch.setattr(git_ops, "_read_additions", counting_read)

    assert git_ops.git_status(cwd=str(committed_repo))["untracked"][0]["additions"] == 2
    assert git_ops.git_status(cwd=str(committed_repo))["untracked"][0]["additions"] == 2
    assert reads == 1, "second poll must reuse the cached count"

    # A rewrite changes size and mtime, so the next poll recounts.
    target.write_text("a\nb\nc\n")
    assert git_ops.git_status(cwd=str(committed_repo))["untracked"][0]["additions"] == 3
    assert reads == 2


def test_untracked_stats_cache_evicts_oldest_first(
    committed_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    from vicoa.rpc import git_ops

    git_ops._untracked_stats_cache.clear()
    for n in range(4):
        (committed_repo / f"f{n}.txt").write_text("x\n")

    git_ops.git_status(cwd=str(committed_repo))
    assert len(git_ops._untracked_stats_cache) == 4

    # Shrinking the bound takes effect on the next insert, which must drop the
    # least recently used entries rather than let the cache grow unbounded.
    (committed_repo / "f4.txt").write_text("x\n")
    monkeypatch.setattr(git_ops, "_UNTRACKED_STATS_CACHE_MAX_ENTRIES", 3)
    git_ops.git_status(cwd=str(committed_repo))
    assert len(git_ops._untracked_stats_cache) == 3
    # f0/f1 were the oldest reads; f4 is the newest and must have survived.
    assert str(committed_repo / "f4.txt") in git_ops._untracked_stats_cache


def test_git_status_caps_entries_and_reports_the_true_total(
    committed_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    # A repo with a huge un-ignored directory must not push every row through
    # each poll. Past the cap the client gets a truncated list plus the real
    # count, and renders its "too many changes" state off `did_hit_limit`.
    from vicoa.rpc import git_ops

    monkeypatch.setattr(git_ops, "_STATUS_ENTRY_LIMIT", 3)
    for n in range(5):
        (committed_repo / f"f{n}.txt").write_text("x\n")

    result = git_ops.git_status(cwd=str(committed_repo))
    assert result["did_hit_limit"] is True
    assert result["status_length"] == 5
    assert [e["path"] for e in result["untracked"]] == [
        "f0.txt",
        "f1.txt",
        "f2.txt",
    ]


def test_git_status_skips_enrichment_once_capped(
    committed_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    # numstat, line counting and hash-object all scale with the entry count —
    # running them past the cap reintroduces the exact cost the cap avoids.
    from vicoa.rpc import git_ops

    monkeypatch.setattr(git_ops, "_STATUS_ENTRY_LIMIT", 1)
    (committed_repo / "seed.txt").write_text("seed\nedited\n")
    for n in range(3):
        (committed_repo / f"f{n}.txt").write_text("x\n")

    extra_calls = 0
    real_run = git_ops.subprocess.run

    def counting_run(cmd, *args, **kwargs):
        nonlocal extra_calls
        if isinstance(cmd, list) and ("hash-object" in cmd or "--numstat" in cmd):
            extra_calls += 1
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(git_ops.subprocess, "run", counting_run)
    result = git_ops.git_status(cwd=str(committed_repo))
    assert result["did_hit_limit"] is True
    assert extra_calls == 0
    entry = (result["staged"] + result["unstaged"] + result["untracked"])[0]
    assert entry["additions"] == 0
    assert entry["content_hash"] is None


def test_git_status_clean_repo_runs_no_numstat(
    committed_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    # numstat now runs only for sections that have entries, so a clean tree
    # costs one `git status` and nothing else.
    from vicoa.rpc import git_ops

    numstat_calls = 0
    real_run = git_ops.subprocess.run

    def counting_run(cmd, *args, **kwargs):
        nonlocal numstat_calls
        if isinstance(cmd, list) and "--numstat" in cmd:
            numstat_calls += 1
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(git_ops.subprocess, "run", counting_run)
    git_ops.git_status(cwd=str(committed_repo))
    assert numstat_calls == 0


def test_git_status_disables_optional_locks(
    committed_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    # Status is polled while the agent runs git in the same repo; refreshing
    # the index here would contend on `.git/index.lock` with its commit.
    from vicoa.rpc import git_ops

    seen: list[list[str]] = []
    real_run = git_ops.subprocess.run

    def recording_run(cmd, *args, **kwargs):
        if isinstance(cmd, list):
            seen.append(cmd)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(git_ops.subprocess, "run", recording_run)
    (committed_repo / "seed.txt").write_text("seed\nedited\n")
    git_ops.git_status(cwd=str(committed_repo))

    assert seen
    assert all("--no-optional-locks" in cmd for cmd in seen)


def test_git_status_deleted_file_is_listed_with_null_hash(committed_repo: Path):
    # Working-tree delete (no `git rm`). content_hash is null because there's
    # no working-tree content to hash.
    from vicoa.rpc.git_ops import git_status

    (committed_repo / "seed.txt").unlink()
    result = git_status(cwd=str(committed_repo))
    assert result["staged"] == []
    assert result["untracked"] == []
    assert result["unstaged"] == [
        {
            "path": "seed.txt",
            "status": "D",
            "additions": 0,
            "deletions": 1,
            "content_hash": None,
        }
    ]


def test_git_status_renamed_staged_file_carries_old_path(committed_repo: Path):
    # Rename detection requires the rename be staged (porcelain v2 only emits
    # rename records for staged renames).
    from vicoa.rpc.git_ops import git_status

    _git(committed_repo, "mv", "seed.txt", "renamed.txt")
    result = git_status(cwd=str(committed_repo))
    assert result["unstaged"] == []
    assert result["untracked"] == []
    assert len(result["staged"]) == 1
    entry = result["staged"][0]
    assert entry["path"] == "renamed.txt"
    assert entry["old_path"] == "seed.txt"
    assert entry["status"] == "R"


def test_git_status_same_file_both_staged_and_unstaged_appears_in_both(
    committed_repo: Path,
):
    # Stage a modification, then add another modification on top in the
    # worktree. The file shows up in BOTH staged and unstaged sections — each
    # bucket reports its own numstat slice.
    from vicoa.rpc.git_ops import git_status

    (committed_repo / "seed.txt").write_text("seed\nstaged-line\n")
    _git(committed_repo, "add", "seed.txt")
    (committed_repo / "seed.txt").write_text("seed\nstaged-line\nworktree-line\n")
    result = git_status(cwd=str(committed_repo))
    staged_paths = [e["path"] for e in result["staged"]]
    unstaged_paths = [e["path"] for e in result["unstaged"]]
    assert "seed.txt" in staged_paths
    assert "seed.txt" in unstaged_paths


# --- git_status: branch metadata ----------------------------------------------


@pytest.fixture
def repo_with_upstream(
    committed_repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """Repo with `origin/main` upstream wired up via a bare local remote."""
    remote = tmp_path_factory.mktemp("remote.git")
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    _git(committed_repo, "remote", "add", "origin", str(remote))
    _git(committed_repo, "push", "-u", "-q", "origin", "main")
    return committed_repo


def test_git_status_reports_upstream_when_tracking(repo_with_upstream: Path):
    from vicoa.rpc.git_ops import git_status

    result = git_status(cwd=str(repo_with_upstream))
    assert result["upstream"] == "origin/main"
    assert result["ahead"] == 0
    assert result["behind"] == 0
    assert "detached_head" not in result


def test_git_status_reports_ahead_after_local_commit(repo_with_upstream: Path):
    from vicoa.rpc.git_ops import git_status

    (repo_with_upstream / "ahead.txt").write_text("ahead\n")
    _git(repo_with_upstream, "add", "ahead.txt")
    _git(repo_with_upstream, "commit", "-q", "-m", "ahead")
    result = git_status(cwd=str(repo_with_upstream))
    assert result["ahead"] == 1
    assert result["behind"] == 0


def test_git_status_omits_upstream_when_branch_has_none(committed_repo: Path):
    from vicoa.rpc.git_ops import git_status

    result = git_status(cwd=str(committed_repo))
    assert "upstream" not in result
    assert result["ahead"] == 0
    assert result["behind"] == 0


def test_git_status_detached_head_uses_short_sha_for_branch(committed_repo: Path):
    from vicoa.rpc.git_ops import git_status

    # Add a second commit so we have a SHA to detach to.
    (committed_repo / "more.txt").write_text("more\n")
    _git(committed_repo, "add", "more.txt")
    _git(committed_repo, "commit", "-q", "-m", "more")
    sha = _git(committed_repo, "rev-parse", "HEAD").stdout.decode().strip()
    _git(committed_repo, "checkout", "-q", sha)
    result = git_status(cwd=str(committed_repo))
    assert result["detached_head"] is True
    assert result["branch"] == sha[:7]


def test_git_status_runs_hash_object_at_most_once_per_call(
    committed_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    # Subprocess startup dominates cost on noisy repos. Plan §6 requires
    # batching unstaged + untracked hashes through a single
    # `git hash-object --stdin-paths` call.
    from vicoa.rpc import git_ops

    for n in ("a", "b", "c", "d"):
        (committed_repo / f"{n}.txt").write_text(f"{n}\n")

    hash_calls = 0
    real_run = git_ops.subprocess.run

    def counting_run(cmd, *args, **kwargs):
        nonlocal hash_calls
        if isinstance(cmd, list) and "hash-object" in cmd:
            hash_calls += 1
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(git_ops.subprocess, "run", counting_run)
    git_ops.git_status(cwd=str(committed_repo))
    assert hash_calls <= 1, f"hash-object ran {hash_calls} times — must batch"


# --- git_diff -----------------------------------------------------------------


def test_git_diff_unstaged_modification_returns_typed_hunk(committed_repo: Path):
    from vicoa.rpc.git_ops import git_diff

    (committed_repo / "seed.txt").write_text("seed\nadded\n")
    result = git_diff(
        cwd=str(committed_repo),
        path="seed.txt",
        staged=False,
        ignore_whitespace=False,
    )
    assert result["path"] == "seed.txt"
    assert result["is_binary"] is False
    assert result["truncated"] is False
    assert len(result["hunks"]) == 1
    hunk = result["hunks"][0]
    assert hunk["old_start"] == 1
    assert hunk["new_start"] == 1
    # The added line carries a type, not a leading "+".
    types_and_content = [(ln["type"], ln["content"]) for ln in hunk["lines"]]
    assert ("add", "added") in types_and_content
    assert ("context", "seed") in types_and_content


def test_git_diff_staged_and_unstaged_return_distinct_hunks(committed_repo: Path):
    # Stage one change, then add another on top in the worktree. The two
    # diffs must surface different content, proving `staged=True/False` flips
    # the underlying invocation.
    from vicoa.rpc.git_ops import git_diff

    (committed_repo / "seed.txt").write_text("seed\nstaged-line\n")
    _git(committed_repo, "add", "seed.txt")
    (committed_repo / "seed.txt").write_text("seed\nstaged-line\nworktree-line\n")
    staged = git_diff(
        cwd=str(committed_repo),
        path="seed.txt",
        staged=True,
        ignore_whitespace=False,
    )
    unstaged = git_diff(
        cwd=str(committed_repo),
        path="seed.txt",
        staged=False,
        ignore_whitespace=False,
    )
    staged_adds = [
        ln["content"]
        for h in staged["hunks"]
        for ln in h["lines"]
        if ln["type"] == "add"
    ]
    unstaged_adds = [
        ln["content"]
        for h in unstaged["hunks"]
        for ln in h["lines"]
        if ln["type"] == "add"
    ]
    assert "staged-line" in staged_adds
    assert "worktree-line" in unstaged_adds
    assert "worktree-line" not in staged_adds
    assert "staged-line" not in unstaged_adds


def test_git_diff_ignore_whitespace_drops_whitespace_only_change(
    committed_repo: Path,
):
    from vicoa.rpc.git_ops import git_diff

    # Whitespace-only change — trailing-space variant of the same line.
    (committed_repo / "seed.txt").write_text("seed  \n")
    keep_ws = git_diff(
        cwd=str(committed_repo),
        path="seed.txt",
        staged=False,
        ignore_whitespace=False,
    )
    drop_ws = git_diff(
        cwd=str(committed_repo),
        path="seed.txt",
        staged=False,
        ignore_whitespace=True,
    )
    assert len(keep_ws["hunks"]) >= 1
    assert drop_ws["hunks"] == []


def test_git_diff_over_cap_returns_truncated_with_partial_hunks(
    committed_repo: Path,
):
    # Replace `seed.txt` with ~1.5 MB of new content — the diff will be
    # ~1.5 MB of `+` lines plus headers, comfortably over the 1 MB cap.
    from vicoa.rpc.git_ops import git_diff

    big = "abcdef\n" * 250_000  # ~1.75 MB
    (committed_repo / "seed.txt").write_text(big)
    result = git_diff(
        cwd=str(committed_repo),
        path="seed.txt",
        staged=False,
        ignore_whitespace=False,
    )
    assert result["truncated"] is True
    assert result["is_binary"] is False
    assert len(result["hunks"]) >= 1
    # All hunks that were emitted must be well-formed (no half-line crumbs).
    for h in result["hunks"]:
        for ln in h["lines"]:
            assert ln["type"] in ("add", "remove", "context")


def test_git_diff_binary_file_reports_is_binary_with_no_hunks(
    committed_repo: Path,
):
    from vicoa.rpc.git_ops import git_diff

    payload = b"\x89PNG\x00\x01\x02\x03\x04\x05" * 50
    (committed_repo / "seed.txt").write_bytes(payload)
    result = git_diff(
        cwd=str(committed_repo),
        path="seed.txt",
        staged=False,
        ignore_whitespace=False,
    )
    assert result["is_binary"] is True
    assert result["hunks"] == []
    assert result["size"] == len(payload)


def test_git_diff_untracked_file_synthesizes_all_additions(committed_repo: Path):
    # `git diff` produces no output for untracked paths. The handler must
    # synthesize a one-hunk all-additions diff so the Git tab can render it
    # the same way as a tracked-file modification.
    from vicoa.rpc.git_ops import git_diff

    (committed_repo / "new.txt").write_text("one\ntwo\nthree\n")
    result = git_diff(
        cwd=str(committed_repo),
        path="new.txt",
        staged=False,
        ignore_whitespace=False,
    )
    assert result["is_binary"] is False
    assert result["truncated"] is False
    assert len(result["hunks"]) == 1
    hunk = result["hunks"][0]
    line_types = [ln["type"] for ln in hunk["lines"]]
    assert line_types == ["add", "add", "add"]
    contents = [ln["content"] for ln in hunk["lines"]]
    assert contents == ["one", "two", "three"]


def test_git_diff_untracked_directory_returns_empty_diff(committed_repo: Path):
    # An untracked *directory* — e.g. an embedded git repo (its own `.git`, not
    # a registered submodule) — is reported by `git status` as a single path
    # with a trailing slash, and git won't descend into it. The handler must
    # return an empty diff, not crash trying to `open()` the directory.
    # Regression for IsADirectoryError in _synthesize_all_additions_diff.
    from vicoa.rpc.git_ops import git_diff

    embedded = committed_repo / "embedded"
    embedded.mkdir()
    (embedded / ".git").mkdir()  # makes git treat it as an opaque embedded repo
    (embedded / "file.txt").write_text("hi\n")

    result = git_diff(
        cwd=str(committed_repo),
        path="embedded/",  # trailing slash, exactly as `git status` reports it
        staged=False,
        ignore_whitespace=False,
    )
    assert result["hunks"] == []
    assert result["is_binary"] is False
    assert result["size"] == 0


def test_git_diff_deleted_file_returns_all_removals(committed_repo: Path):
    from vicoa.rpc.git_ops import git_diff

    (committed_repo / "seed.txt").unlink()
    result = git_diff(
        cwd=str(committed_repo),
        path="seed.txt",
        staged=False,
        ignore_whitespace=False,
    )
    assert result["is_binary"] is False
    assert len(result["hunks"]) == 1
    types = [ln["type"] for ln in result["hunks"][0]["lines"]]
    assert types == ["remove"]
    assert result["hunks"][0]["lines"][0]["content"] == "seed"


def test_git_diff_path_outside_project_returns_outside_project(
    committed_repo: Path,
):
    from vicoa.rpc.git_ops import git_diff

    result = git_diff(
        cwd=str(committed_repo),
        path="../escape",
        staged=False,
        ignore_whitespace=False,
    )
    assert result == {"error": "outside_project"}


# --- git_log ------------------------------------------------------------------


def _commit(repo: Path, name: str, content: str, message: str) -> None:
    (repo / name).write_text(content)
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", message)


def test_git_log_non_git_directory_returns_not_a_repo(tmp_path: Path):
    from vicoa.rpc.git_ops import git_log

    assert git_log(cwd=str(tmp_path)) == {"error": "not_a_repo"}


def test_git_log_empty_repo_returns_empty(git_repo: Path):
    from vicoa.rpc.git_ops import git_log

    assert git_log(cwd=str(git_repo)) == {"commits": [], "has_more": False}


def test_git_log_linear_history_newest_first_with_refs(committed_repo: Path):
    from vicoa.rpc.git_ops import git_log

    _commit(committed_repo, "a.txt", "a\n", "second")
    result = git_log(cwd=str(committed_repo))
    assert result["has_more"] is False
    subjects = [c["subject"] for c in result["commits"]]
    assert subjects == ["second", "seed"]
    head = result["commits"][0]
    assert head["parent_ids"] == [result["commits"][1]["id"]]
    assert head["author_name"] == "Test"
    assert head["author_email"] == "test@example.com"
    assert isinstance(head["timestamp"], int) and head["timestamp"] > 0
    kinds = {(r["name"], r["kind"]) for r in head["refs"]}
    assert ("main", "branch") in kinds
    assert result["current_ref"] == {"name": "main", "revision": head["id"]}


def test_git_log_has_more_and_limit(committed_repo: Path):
    from vicoa.rpc.git_ops import git_log

    for i in range(5):
        _commit(committed_repo, f"f{i}.txt", f"{i}\n", f"c{i}")
    result = git_log(cwd=str(committed_repo), limit=3)
    assert len(result["commits"]) == 3
    assert result["has_more"] is True


def test_git_log_tag_is_decorated(committed_repo: Path):
    from vicoa.rpc.git_ops import git_log

    _git(committed_repo, "tag", "v1")
    result = git_log(cwd=str(committed_repo))
    refs = result["commits"][0]["refs"]
    assert any(r["name"] == "v1" and r["kind"] == "tag" for r in refs)


# --- git_commit_files ---------------------------------------------------------


def test_git_commit_files_root_commit_lists_added_file(committed_repo: Path):
    from vicoa.rpc.git_ops import git_commit_files

    head = _git(committed_repo, "rev-parse", "HEAD").stdout.decode().strip()
    result = git_commit_files(cwd=str(committed_repo), commit_id=head)
    assert result["files"] == [
        {"path": "seed.txt", "status": "A", "additions": 1, "deletions": 0}
    ]
    assert result["stats"] == {"files": 1, "insertions": 1, "deletions": 0}


def test_git_commit_files_modification(committed_repo: Path):
    from vicoa.rpc.git_ops import git_commit_files

    (committed_repo / "seed.txt").write_text("seed\nmore\n")
    _git(committed_repo, "commit", "-q", "-am", "edit")
    head = _git(committed_repo, "rev-parse", "HEAD").stdout.decode().strip()
    result = git_commit_files(cwd=str(committed_repo), commit_id=head)
    assert result["files"] == [
        {"path": "seed.txt", "status": "M", "additions": 1, "deletions": 0}
    ]


def test_git_commit_files_rename_carries_old_path(committed_repo: Path):
    from vicoa.rpc.git_ops import git_commit_files

    _git(committed_repo, "mv", "seed.txt", "renamed.txt")
    _git(committed_repo, "commit", "-q", "-m", "rename")
    head = _git(committed_repo, "rev-parse", "HEAD").stdout.decode().strip()
    result = git_commit_files(cwd=str(committed_repo), commit_id=head)
    assert len(result["files"]) == 1
    f = result["files"][0]
    assert f["path"] == "renamed.txt"
    assert f["old_path"] == "seed.txt"
    assert f["status"] == "R"


def test_git_commit_files_rejects_non_hex_commit(committed_repo: Path):
    from vicoa.rpc.git_ops import git_commit_files

    assert git_commit_files(cwd=str(committed_repo), commit_id="--output=x") == {
        "error": "rpc_failed"
    }


# --- git_commit_diff ----------------------------------------------------------


def test_git_commit_diff_modification_returns_hunk(committed_repo: Path):
    from vicoa.rpc.git_ops import git_commit_diff

    (committed_repo / "seed.txt").write_text("seed\nmore\n")
    _git(committed_repo, "commit", "-q", "-am", "edit")
    head = _git(committed_repo, "rev-parse", "HEAD").stdout.decode().strip()
    result = git_commit_diff(cwd=str(committed_repo), commit_id=head, path="seed.txt")
    assert result["is_binary"] is False
    assert result["path"] == "seed.txt"
    kinds = [ln["type"] for h in result["hunks"] for ln in h["lines"]]
    assert "add" in kinds


def test_git_commit_diff_root_commit_all_additions(committed_repo: Path):
    from vicoa.rpc.git_ops import git_commit_diff

    head = _git(committed_repo, "rev-parse", "HEAD").stdout.decode().strip()
    result = git_commit_diff(cwd=str(committed_repo), commit_id=head, path="seed.txt")
    lines = [ln for h in result["hunks"] for ln in h["lines"]]
    assert lines and all(ln["type"] == "add" for ln in lines)


def test_git_commit_diff_rejects_non_hex(committed_repo: Path):
    from vicoa.rpc.git_ops import git_commit_diff

    result = git_commit_diff(cwd=str(committed_repo), commit_id="x;rm", path="seed.txt")
    assert result == {"error": "rpc_failed"}


# --- submodules: git_status flagging ------------------------------------------


@pytest.fixture
def repo_with_submodule(committed_repo: Path, tmp_path_factory) -> Path:
    """Parent repo with submodule `sub`, whose pin is one commit behind its HEAD.

    Mirrors the real case the Changes panel cares about: someone committed
    inside the submodule, so the parent shows a moved gitlink and `git diff` in
    the parent can only say "Subproject commit a..b".
    """
    inner = tmp_path_factory.mktemp("inner")
    subprocess.run(["git", "init", "-q", "-b", "main", str(inner)], check=True)
    _git(inner, "config", "user.email", "test@example.com")
    _git(inner, "config", "user.name", "Test")
    _git(inner, "config", "commit.gpgsign", "false")
    (inner / "lib.txt").write_text("one\n")
    _git(inner, "add", "lib.txt")
    _git(inner, "commit", "-q", "-m", "inner seed")

    # Local-path submodules are refused by default since git 2.38 (CVE-2022-39253).
    _git(
        committed_repo,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(inner),
        "sub",
    )
    _git(committed_repo, "commit", "-q", "-m", "add submodule")

    # Move the submodule's HEAD past what the parent pins. `submodule add` made
    # `sub` a fresh clone, so it inherits none of `inner`'s local config —
    # pin identity here too or the commit below needs a global git identity.
    sub = committed_repo / "sub"
    _git(sub, "config", "user.email", "test@example.com")
    _git(sub, "config", "user.name", "Test")
    _git(sub, "config", "commit.gpgsign", "false")
    (sub / "lib.txt").write_text("one\ntwo\n")
    (sub / "added.txt").write_text("new file\n")
    _git(sub, "add", "-A")
    _git(sub, "commit", "-q", "-m", "inner change")
    return committed_repo


def test_git_status_flags_submodule_entry(repo_with_submodule: Path):
    from vicoa.rpc.git_ops import git_status

    result = git_status(cwd=str(repo_with_submodule))
    subs = [e for e in result["unstaged"] if e["path"] == "sub"]
    assert len(subs) == 1
    assert subs[0]["is_submodule"] is True


def test_git_status_plain_file_is_not_flagged_as_submodule(repo_with_submodule: Path):
    from vicoa.rpc.git_ops import git_status

    (repo_with_submodule / "seed.txt").write_text("seed\nedited\n")
    result = git_status(cwd=str(repo_with_submodule))
    seed = [e for e in result["unstaged"] if e["path"] == "seed.txt"]
    assert len(seed) == 1
    assert "is_submodule" not in seed[0]


def test_git_status_submodule_does_not_null_other_content_hashes(
    repo_with_submodule: Path,
):
    """Regression: submodules are directories, so feeding them to
    `hash-object --stdin-paths` aborted the whole batch and every entry —
    not just the submodule — came back with a null hash."""
    from vicoa.rpc.git_ops import git_status

    (repo_with_submodule / "seed.txt").write_text("seed\nedited\n")
    result = git_status(cwd=str(repo_with_submodule))
    seed = next(e for e in result["unstaged"] if e["path"] == "seed.txt")
    assert seed["content_hash"] is not None


def test_git_status_untracked_dir_does_not_null_other_content_hashes(
    committed_repo: Path,
):
    """Same batch-abort regression, reached via an untracked *directory*
    (git reports embedded repos as one path with a trailing slash)."""
    from vicoa.rpc.git_ops import git_status

    nested = committed_repo / "embedded"
    nested.mkdir()
    subprocess.run(["git", "init", "-q", str(nested)], check=True)
    (nested / "x.txt").write_text("x\n")
    (committed_repo / "seed.txt").write_text("seed\nedited\n")

    result = git_status(cwd=str(committed_repo))
    seed = next(e for e in result["unstaged"] if e["path"] == "seed.txt")
    assert seed["content_hash"] is not None


def test_git_status_on_submodule_dir_returns_its_own_working_changes(
    repo_with_submodule: Path,
):
    """The Changes panel expands a submodule by pointing `git-status` at the
    submodule directory, so what it shows is the submodule's *active* work —
    HEAD vs worktree — not everything committed since the parent's pin."""
    from vicoa.rpc.git_ops import git_status

    sub = repo_with_submodule / "sub"
    (sub / "lib.txt").write_text("one\ntwo\nthree\n")  # unstaged edit
    (sub / "staged.txt").write_text("staged\n")
    _git(sub, "add", "staged.txt")
    (sub / "scratch.txt").write_text("untracked\n")

    result = git_status(cwd=str(sub))
    assert {e["path"] for e in result["unstaged"]} == {"lib.txt"}
    assert {e["path"] for e in result["staged"]} == {"staged.txt"}
    assert {e["path"] for e in result["untracked"]} == {"scratch.txt"}
    # `added.txt` was committed inside the submodule (moving the pin), so it is
    # deliberately absent — that is history, not active work.
    assert "added.txt" not in {e["path"] for e in result["unstaged"]}


# --- git_show_file: baseline for the editable diff ----------------------------


def test_git_show_file_returns_head_blob(committed_repo: Path):
    """HEAD baseline is the committed content, not the working-tree edit."""
    from vicoa.rpc.git_ops import git_show_file

    (committed_repo / "seed.txt").write_text("seed\nedited\n")  # working edit
    result = git_show_file(cwd=str(committed_repo), path="seed.txt")
    assert result["content"] == "seed\n"  # HEAD version, not the edit
    assert result["is_binary"] is False
    assert result["encoding"] == "utf-8"
    assert result["content_hash"] is not None


def test_git_show_file_index_ref_returns_staged_blob(committed_repo: Path):
    """An empty ref reads the index (`git show :<path>`) — the staged blob."""
    from vicoa.rpc.git_ops import git_show_file

    (committed_repo / "seed.txt").write_text("seed\nstaged\n")
    _git(committed_repo, "add", "seed.txt")
    (committed_repo / "seed.txt").write_text(
        "seed\nstaged\nunstaged\n"
    )  # newer worktree

    result = git_show_file(cwd=str(committed_repo), path="seed.txt", ref="")
    assert result["content"] == "seed\nstaged\n"  # index, between HEAD and worktree


def test_git_show_file_untracked_path_reports_not_in_ref(committed_repo: Path):
    """A file that doesn't exist at HEAD → empty original (all-added diff)."""
    from vicoa.rpc.git_ops import git_show_file

    (committed_repo / "new.txt").write_text("brand new\n")
    result = git_show_file(cwd=str(committed_repo), path="new.txt")
    assert result == {"not_in_ref": True}


def test_git_show_file_binary_blob_flags_binary(committed_repo: Path):
    """A NUL-containing HEAD blob is reported binary with no content."""
    from vicoa.rpc.git_ops import git_show_file

    (committed_repo / "blob.bin").write_bytes(b"\x00\x01\x02binary\x00")
    _git(committed_repo, "add", "blob.bin")
    _git(committed_repo, "commit", "-q", "-m", "add binary")

    result = git_show_file(cwd=str(committed_repo), path="blob.bin")
    assert result["is_binary"] is True
    assert result["content"] == ""
    assert result["content_hash"] is None


def test_git_show_file_non_git_directory_returns_not_a_repo(tmp_path: Path):
    from vicoa.rpc.git_ops import git_show_file

    assert git_show_file(cwd=str(tmp_path), path="x.txt") == {"error": "not_a_repo"}


def test_git_show_file_outside_project_is_rejected(committed_repo: Path):
    from vicoa.rpc.git_ops import git_show_file

    result = git_show_file(cwd=str(committed_repo), path="../escape.txt")
    assert result == {"error": "outside_project"}


# --- git_stage / git_unstage / git_commit ----------------------------------------


def test_git_stage_untracked_file_moves_it_to_staged(committed_repo: Path):
    from vicoa.rpc.git_ops import git_stage, git_status

    (committed_repo / "new.txt").write_text("hello\n")
    result = git_stage(cwd=str(committed_repo), paths=["new.txt"])
    assert result == {"ok": True}

    status = git_status(cwd=str(committed_repo))
    assert [e["path"] for e in status["staged"]] == ["new.txt"]
    assert status["untracked"] == []


def test_git_stage_stages_a_deletion(committed_repo: Path):
    from vicoa.rpc.git_ops import git_stage, git_status

    (committed_repo / "seed.txt").unlink()
    result = git_stage(cwd=str(committed_repo), paths=["seed.txt"])
    assert result == {"ok": True}

    status = git_status(cwd=str(committed_repo))
    staged = {e["path"]: e["status"] for e in status["staged"]}
    assert staged == {"seed.txt": "D"}


def test_git_stage_literal_pathspec_does_not_glob(committed_repo: Path):
    """A filename containing `*` stages exactly that file, not glob matches."""
    from vicoa.rpc.git_ops import git_stage, git_status

    (committed_repo / "a*.txt").write_text("star\n")
    (committed_repo / "ab.txt").write_text("plain\n")
    result = git_stage(cwd=str(committed_repo), paths=["a*.txt"])
    assert result == {"ok": True}

    status = git_status(cwd=str(committed_repo))
    assert [e["path"] for e in status["staged"]] == ["a*.txt"]
    assert [e["path"] for e in status["untracked"]] == ["ab.txt"]


def test_git_stage_outside_project_is_rejected(committed_repo: Path):
    from vicoa.rpc.git_ops import git_stage

    result = git_stage(cwd=str(committed_repo), paths=["../escape.txt"])
    assert result == {"error": "outside_project"}


def test_git_stage_empty_paths_is_rejected(committed_repo: Path):
    from vicoa.rpc.git_ops import git_stage

    assert git_stage(cwd=str(committed_repo), paths=[]) == {"error": "rpc_failed"}


def test_git_stage_non_git_directory_returns_not_a_repo(tmp_path: Path):
    from vicoa.rpc.git_ops import git_stage

    assert git_stage(cwd=str(tmp_path), paths=["x.txt"]) == {"error": "not_a_repo"}


def test_git_unstage_returns_file_to_unstaged(committed_repo: Path):
    from vicoa.rpc.git_ops import git_status, git_unstage

    (committed_repo / "seed.txt").write_text("seed\nmore\n")
    _git(committed_repo, "add", "seed.txt")

    result = git_unstage(cwd=str(committed_repo), paths=["seed.txt"])
    assert result == {"ok": True}

    status = git_status(cwd=str(committed_repo))
    assert status["staged"] == []
    assert [e["path"] for e in status["unstaged"]] == ["seed.txt"]


def test_git_unstage_on_unborn_branch_resets_to_empty_tree(git_repo: Path):
    """No HEAD yet (fresh repo) — unstaging an added file must still work."""
    from vicoa.rpc.git_ops import git_status, git_unstage

    (git_repo / "first.txt").write_text("first\n")
    _git(git_repo, "add", "first.txt")

    result = git_unstage(cwd=str(git_repo), paths=["first.txt"])
    assert result == {"ok": True}

    status = git_status(cwd=str(git_repo))
    assert status["staged"] == []
    assert [e["path"] for e in status["untracked"]] == ["first.txt"]


def test_git_commit_commits_only_the_staged_file(committed_repo: Path):
    from vicoa.rpc.git_ops import git_commit, git_status

    (committed_repo / "staged.txt").write_text("in\n")
    (committed_repo / "kept.txt").write_text("out\n")
    _git(committed_repo, "add", "staged.txt")

    result = git_commit(cwd=str(committed_repo), message="add staged.txt")
    assert result["ok"] is True
    assert isinstance(result["commit_id"], str) and len(result["commit_id"]) == 40

    subject = _git(committed_repo, "log", "-1", "--format=%s").stdout.decode().strip()
    assert subject == "add staged.txt"
    status = git_status(cwd=str(committed_repo))
    assert status["staged"] == []
    assert [e["path"] for e in status["untracked"]] == ["kept.txt"]


def test_git_commit_empty_message_is_rejected(committed_repo: Path):
    from vicoa.rpc.git_ops import git_commit

    result = git_commit(cwd=str(committed_repo), message="   ")
    assert result["error"] == "commit_failed"


def test_git_commit_nothing_staged_reports_gits_message(committed_repo: Path):
    from vicoa.rpc.git_ops import git_commit

    result = git_commit(cwd=str(committed_repo), message="nope")
    assert result["error"] == "commit_failed"
    assert result["message"]  # git's own explanation, surfaced to the UI


def test_git_commit_non_git_directory_returns_not_a_repo(tmp_path: Path):
    from vicoa.rpc.git_ops import git_commit

    assert git_commit(cwd=str(tmp_path), message="m") == {"error": "not_a_repo"}
