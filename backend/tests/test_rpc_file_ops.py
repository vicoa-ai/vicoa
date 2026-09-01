"""Daemon-side file-op RPC handlers — listing + reading.

Covers `plans/todos/vicoa-app-files-tab.md` §Phase B file_ops.py. Each test
exercises one slice of the contract; the suite as a whole is the golden table
the Flutter Files tab consumes.
"""

from __future__ import annotations

import base64
import hashlib
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """An initialized empty git repo at `tmp_path`."""
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(tmp_path)],
        check=True,
    )
    return tmp_path


def test_list_files_empty_repo_returns_no_entries(git_repo: Path):
    from vicoa.rpc.file_ops import list_files

    result = list_files(cwd=str(git_repo), path="")
    assert result == {"entries": []}


def test_list_files_tracked_file_appears_with_size(git_repo: Path):
    from vicoa.rpc.file_ops import list_files

    (git_repo / "readme.md").write_text("hello\n")
    result = list_files(cwd=str(git_repo), path="")
    assert result == {"entries": [{"name": "readme.md", "type": "file", "size": 6}]}


def test_list_files_sorts_dirs_first_then_case_insensitive_alpha(git_repo: Path):
    from vicoa.rpc.file_ops import list_files

    (git_repo / "Zoo").mkdir()
    (git_repo / "alpha").mkdir()
    (git_repo / "Beta.txt").write_text("b")
    (git_repo / "apple.txt").write_text("a")
    result = list_files(cwd=str(git_repo), path="")
    names = [e["name"] for e in result["entries"]]
    assert names == ["alpha", "Zoo", "apple.txt", "Beta.txt"]


def test_list_files_hides_gitignored_keeps_untracked(git_repo: Path):
    from vicoa.rpc.file_ops import list_files

    (git_repo / ".gitignore").write_text("secret.env\n")
    (git_repo / "secret.env").write_text("KEY=hunter2")
    (git_repo / "new_file.py").write_text("# untracked but not ignored")
    result = list_files(cwd=str(git_repo), path="")
    names = [e["name"] for e in result["entries"]]
    assert ".gitignore" in names
    assert "new_file.py" in names
    assert "secret.env" not in names


def test_list_files_default_exclude_hides_cache_dir(git_repo: Path):
    # `__pycache__/` is in DEFAULT_EXCLUDE_PATTERNS — must be hidden even when
    # the project's .gitignore forgot to add it. Belt-and-suspenders.
    from vicoa.rpc.file_ops import list_files

    (git_repo / "__pycache__").mkdir()
    (git_repo / "__pycache__" / "x.cpython-312.pyc").write_bytes(b"\x00")
    (git_repo / "main.py").write_text("print('hi')")
    result = list_files(cwd=str(git_repo), path="")
    names = [e["name"] for e in result["entries"]]
    assert "main.py" in names
    assert "__pycache__" not in names


def test_list_files_subdir_listed_relative_to_cwd(git_repo: Path):
    from vicoa.rpc.file_ops import list_files

    (git_repo / "src").mkdir()
    (git_repo / "src" / "main.py").write_text("hi")
    result = list_files(cwd=str(git_repo), path="src")
    names = [e["name"] for e in result["entries"]]
    assert names == ["main.py"]


def test_list_files_traversal_returns_outside_project_error(git_repo: Path):
    from vicoa.rpc.file_ops import list_files

    result = list_files(cwd=str(git_repo), path="../escape")
    assert result == {"error": "outside_project"}


def test_list_files_missing_path_returns_path_not_found(git_repo: Path):
    from vicoa.rpc.file_ops import list_files

    result = list_files(cwd=str(git_repo), path="does/not/exist")
    assert result == {"error": "path_not_found"}


def test_list_files_file_path_returns_not_a_directory(git_repo: Path):
    from vicoa.rpc.file_ops import list_files

    (git_repo / "readme.md").write_text("hi")
    result = list_files(cwd=str(git_repo), path="readme.md")
    assert result == {"error": "not_a_directory"}


def test_list_files_skips_symlink_pointing_outside_project(
    git_repo: Path, tmp_path_factory: pytest.TempPathFactory
):
    # Symlinks must be followed only if their realpath stays inside the project
    # root. Outside-pointing symlinks are silently dropped — not an error.
    from vicoa.rpc.file_ops import list_files

    outside = tmp_path_factory.mktemp("outside_proj")
    (outside / "secret").write_text("nope")
    (git_repo / "ok.txt").write_text("inside")
    (git_repo / "escape").symlink_to(outside / "secret")
    result = list_files(cwd=str(git_repo), path="")
    names = [e["name"] for e in result["entries"]]
    assert "ok.txt" in names
    assert "escape" not in names


def test_list_files_keeps_symlink_pointing_inside_project(git_repo: Path):
    from vicoa.rpc.file_ops import list_files

    (git_repo / "real.txt").write_text("hi")
    (git_repo / "alias").symlink_to(git_repo / "real.txt")
    result = list_files(cwd=str(git_repo), path="")
    names = [e["name"] for e in result["entries"]]
    assert "alias" in names


def test_list_files_runs_check_ignore_once_per_call(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
):
    # Subprocess startup is the dominant cost; batching all entries through
    # one stdin call is required by the plan. Easy to regress to per-entry.
    from vicoa.rpc import file_ops

    for n in ("a", "b", "c", "d", "e"):
        (git_repo / f"{n}.txt").write_text(n)

    call_count = 0
    real_run = file_ops.subprocess.run

    def counting_run(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr(file_ops.subprocess, "run", counting_run)
    file_ops.list_files(cwd=str(git_repo), path="")
    assert call_count == 1


# --- read_file -----------------------------------------------------------------


def test_read_file_small_text_returns_full_content(git_repo: Path):
    from vicoa.rpc.file_ops import read_file

    (git_repo / "hi.txt").write_text("hello\n")
    result = read_file(cwd=str(git_repo), path="hi.txt")
    assert result == {
        "content": "hello\n",
        "encoding": "utf-8",
        "is_binary": False,
        "size": 6,
        "truncated": False,
        "content_hash": hashlib.sha256(b"hello\n").hexdigest(),
    }


def test_read_file_text_over_cap_returns_head_with_truncated_flag(git_repo: Path):
    from vicoa.rpc.file_ops import read_file

    big = "a" * (1 * 1024 * 1024 + 1024)  # 1 MB + 1 KB
    (git_repo / "big.log").write_text(big)
    result = read_file(cwd=str(git_repo), path="big.log")
    assert result["truncated"] is True
    assert result["size"] == len(big)
    assert result["encoding"] == "utf-8"
    assert result["is_binary"] is False
    assert len(result["content"]) == 1 * 1024 * 1024


def test_read_file_binary_non_image_returns_placeholder(git_repo: Path):
    # Null byte in the first 8 KB → binary. Not an image extension → no base64
    # payload, just a placeholder so the viewer can render its "binary file" card.
    from vicoa.rpc.file_ops import read_file

    payload = b"ELF\x00\x01\x02\x03binary data here"
    (git_repo / "blob.bin").write_bytes(payload)
    result = read_file(cwd=str(git_repo), path="blob.bin")
    assert result == {
        "content": "",
        "encoding": "utf-8",
        "is_binary": True,
        "size": len(payload),
        "truncated": False,
        "content_hash": None,
    }


def test_read_file_small_image_returns_base64(git_repo: Path):
    import base64

    from vicoa.rpc.file_ops import read_file

    # 1×1 transparent PNG.
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
        b"\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc"
        b"\x00\x01\x00\x00\x05\x00\x01\x0d\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    (git_repo / "pixel.png").write_bytes(png)
    result = read_file(cwd=str(git_repo), path="pixel.png")
    assert result == {
        "content": base64.b64encode(png).decode("ascii"),
        "encoding": "base64",
        "is_binary": True,
        "size": len(png),
        "truncated": False,
        "content_hash": None,
    }


def test_read_file_image_over_cap_returns_empty_truncated(git_repo: Path):
    # Mobile users hitting the 5 MB cap should see "open on desktop". Empty
    # content avoids shipping a partial PNG that the decoder would garble.
    from vicoa.rpc.file_ops import read_file

    payload = b"\x89PNG" + b"\x00" * (5 * 1024 * 1024 + 100)
    (git_repo / "huge.png").write_bytes(payload)
    result = read_file(cwd=str(git_repo), path="huge.png")
    assert result["truncated"] is True
    assert result["is_binary"] is True
    assert result["size"] == len(payload)
    # Allow either the full base64 or empty — plan §2 #11 specifies head-only
    # truncation. The minimum contract: callers can detect truncation and skip
    # rendering, not strict on what's in `content`.
    if result["content"]:
        assert len(base64.b64decode(result["content"])) == 5 * 1024 * 1024


def test_read_file_missing_returns_path_not_found(git_repo: Path):
    from vicoa.rpc.file_ops import read_file

    result = read_file(cwd=str(git_repo), path="missing.txt")
    assert result == {"error": "path_not_found"}


def test_read_file_dir_path_returns_not_a_file(git_repo: Path):
    from vicoa.rpc.file_ops import read_file

    (git_repo / "src").mkdir()
    result = read_file(cwd=str(git_repo), path="src")
    assert result == {"error": "not_a_file"}


def test_read_file_traversal_returns_outside_project(git_repo: Path):
    from vicoa.rpc.file_ops import read_file

    result = read_file(cwd=str(git_repo), path="../escape")
    assert result == {"error": "outside_project"}


# --- stat_file -----------------------------------------------------------------


def test_stat_file_hash_matches_read_file(git_repo: Path):
    # The poll's freshness signal is only reliable if `stat_file` hashes the
    # exact same bytes as `read_file` did at open time.
    from vicoa.rpc.file_ops import read_file, stat_file

    (git_repo / "note.txt").write_text("content here\n")
    read = read_file(cwd=str(git_repo), path="note.txt")
    stat = stat_file(cwd=str(git_repo), path="note.txt")
    assert stat["content_hash"] == read["content_hash"]
    assert stat["content_hash"] == hashlib.sha256(b"content here\n").hexdigest()
    assert stat["size"] == 13
    assert isinstance(stat["mtime"], float)


def test_stat_file_missing_returns_path_not_found(git_repo: Path):
    from vicoa.rpc.file_ops import stat_file

    assert stat_file(cwd=str(git_repo), path="gone.txt") == {"error": "path_not_found"}


def test_stat_file_directory_returns_not_a_file(git_repo: Path):
    from vicoa.rpc.file_ops import stat_file

    (git_repo / "src").mkdir()
    assert stat_file(cwd=str(git_repo), path="src") == {"error": "not_a_file"}


def test_stat_file_traversal_returns_outside_project(git_repo: Path):
    from vicoa.rpc.file_ops import stat_file

    assert stat_file(cwd=str(git_repo), path="../escape") == {
        "error": "outside_project"
    }


# --- write_file ----------------------------------------------------------------


def test_write_file_overwrites_and_returns_new_hash(git_repo: Path):
    from vicoa.rpc.file_ops import read_file, write_file

    (git_repo / "note.txt").write_text("old\n")
    base = read_file(cwd=str(git_repo), path="note.txt")["content_hash"]
    result = write_file(
        cwd=str(git_repo), path="note.txt", content="new content\n", base_hash=base
    )
    assert (git_repo / "note.txt").read_text() == "new content\n"
    assert result["content_hash"] == hashlib.sha256(b"new content\n").hexdigest()
    assert result["size"] == len("new content\n")
    # The returned hash is a valid new base for the next save.
    assert (
        read_file(cwd=str(git_repo), path="note.txt")["content_hash"]
        == (result["content_hash"])
    )


def test_write_file_conflict_when_base_hash_stale_leaves_file_untouched(git_repo: Path):
    from vicoa.rpc.file_ops import stat_file, write_file

    (git_repo / "note.txt").write_text("agent's newer content\n")
    result = write_file(
        cwd=str(git_repo),
        path="note.txt",
        content="my clobbering edit\n",
        base_hash="0" * 64,  # what we thought was on disk — now stale
    )
    assert result["error"] == "conflict"
    assert (
        result["content_hash"]
        == stat_file(cwd=str(git_repo), path="note.txt")["content_hash"]
    )
    # The concurrent write survived — we did NOT clobber it.
    assert (git_repo / "note.txt").read_text() == "agent's newer content\n"


def test_write_file_force_overwrites_ignoring_base_hash(git_repo: Path):
    from vicoa.rpc.file_ops import write_file

    (git_repo / "note.txt").write_text("agent's newer content\n")
    result = write_file(
        cwd=str(git_repo),
        path="note.txt",
        content="forced\n",
        base_hash="0" * 64,
        force=True,
    )
    assert "error" not in result
    assert (git_repo / "note.txt").read_text() == "forced\n"


def test_write_file_preserves_file_mode(git_repo: Path):
    import os

    from vicoa.rpc.file_ops import read_file, write_file

    p = git_repo / "script.sh"
    p.write_text("#!/bin/sh\necho old\n")
    os.chmod(p, 0o750)
    base = read_file(cwd=str(git_repo), path="script.sh")["content_hash"]
    write_file(
        cwd=str(git_repo),
        path="script.sh",
        content="#!/bin/sh\necho new\n",
        base_hash=base,
    )
    assert (p.stat().st_mode & 0o777) == 0o750


def test_write_file_leaves_no_temp_files(git_repo: Path):
    from vicoa.rpc.file_ops import read_file, write_file

    (git_repo / "note.txt").write_text("old\n")
    base = read_file(cwd=str(git_repo), path="note.txt")["content_hash"]
    write_file(cwd=str(git_repo), path="note.txt", content="new\n", base_hash=base)
    leftovers = [p.name for p in git_repo.iterdir() if p.name.startswith(".vicoa-tmp-")]
    assert leftovers == []


def test_write_file_directory_target_returns_not_a_file(git_repo: Path):
    from vicoa.rpc.file_ops import write_file

    (git_repo / "src").mkdir()
    result = write_file(cwd=str(git_repo), path="src", content="x", force=True)
    assert result == {"error": "not_a_file"}


def test_write_file_traversal_returns_outside_project(git_repo: Path):
    from vicoa.rpc.file_ops import write_file

    result = write_file(cwd=str(git_repo), path="../escape", content="x", force=True)
    assert result == {"error": "outside_project"}


def test_write_file_creates_missing_parent_dir(git_repo: Path):
    from vicoa.rpc.file_ops import read_file, write_file

    # No `.vicoa/` dir yet — a new namespaced config still writes cleanly.
    assert not (git_repo / ".vicoa").exists()
    result = write_file(
        cwd=str(git_repo),
        path=".vicoa/config.json",
        content="{}\n",
        base_hash=None,
    )
    assert "error" not in result
    assert (git_repo / ".vicoa" / "config.json").read_text() == "{}\n"
    assert read_file(cwd=str(git_repo), path=".vicoa/config.json")["content"] == "{}\n"
