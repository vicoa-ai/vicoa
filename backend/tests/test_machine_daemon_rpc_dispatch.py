"""`_handle_rpc_request` routes new methods to `vicoa.rpc.file_ops`.

Covers `plans/todos/vicoa-app-files-tab.md` §Phase B Wire-up. The dispatcher
itself stays sync to match `spawn-session`; the file-op handlers are fast
enough to run inline.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from vicoa.machine_daemon import MachineDaemon


@pytest.fixture
def daemon() -> MachineDaemon:
    return MachineDaemon(api_key="test-key", base_url="http://localhost:0")


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(tmp_path)],
        check=True,
    )
    return tmp_path


def test_list_files_dispatched_to_handler(daemon: MachineDaemon, git_repo: Path):
    (git_repo / "readme.md").write_text("hi")
    frame = {
        "method": "list-files",
        "params": {"cwd": str(git_repo), "path": ""},
    }
    result = daemon._handle_rpc_request(frame)
    assert result == {"entries": [{"name": "readme.md", "type": "file", "size": 2}]}


def test_read_file_dispatched_to_handler(daemon: MachineDaemon, git_repo: Path):
    (git_repo / "hello.txt").write_text("hi")
    frame = {
        "method": "read-file",
        "params": {"cwd": str(git_repo), "path": "hello.txt"},
    }
    result = daemon._handle_rpc_request(frame)
    assert result["content"] == "hi"
    assert result["size"] == 2
    assert result["is_binary"] is False


def test_git_status_dispatched_to_handler(daemon: MachineDaemon, git_repo: Path):
    # Empty git repo dispatch sanity check — handler returns the branch field
    # without error.
    frame = {"method": "git-status", "params": {"cwd": str(git_repo)}}
    result = daemon._handle_rpc_request(frame)
    assert "branch" in result
    assert result["staged"] == []
    assert result["unstaged"] == []
    assert result["untracked"] == []


def test_git_diff_dispatched_to_handler(daemon: MachineDaemon, git_repo: Path):
    # Commit a file, then diff a worktree modification through the RPC path.
    subprocess.run(
        ["git", "-C", str(git_repo), "config", "user.email", "t@e.com"],
        check=True,
    )
    subprocess.run(["git", "-C", str(git_repo), "config", "user.name", "T"], check=True)
    (git_repo / "x.txt").write_text("a\n")
    subprocess.run(["git", "-C", str(git_repo), "add", "x.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(git_repo), "commit", "-q", "-m", "init"], check=True
    )
    (git_repo / "x.txt").write_text("a\nb\n")
    frame = {
        "method": "git-diff",
        "params": {
            "cwd": str(git_repo),
            "path": "x.txt",
            "staged": False,
            "ignore_whitespace": False,
        },
    }
    result = daemon._handle_rpc_request(frame)
    assert result["path"] == "x.txt"
    assert result["is_binary"] is False
    assert len(result["hunks"]) >= 1


def test_unknown_method_returns_error_dict(daemon: MachineDaemon):
    result = daemon._handle_rpc_request({"method": "no-such-method"})
    assert "error" in result
    assert "no-such-method" in result["error"]


@pytest.fixture
def committed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "src" / "app"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    for k, v in (
        ("user.email", "t@e.com"),
        ("user.name", "T"),
        ("commit.gpgsign", "false"),
    ):
        subprocess.run(["git", "-C", str(repo), "config", k, v], check=True)
    (repo / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "-C", str(repo), "add", "seed.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True)
    return repo


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    return h


def test_git_worktree_list_dispatched_to_handler(
    daemon: MachineDaemon, committed_repo: Path, home: Path
):
    frame = {"method": "git-worktree-list", "params": {"cwd": str(committed_repo)}}
    result = daemon._handle_rpc_request(frame)
    assert "worktrees" in result


def test_git_worktree_remove_dispatched_to_handler(
    daemon: MachineDaemon, committed_repo: Path, home: Path
):
    from vicoa.rpc.worktree_ops import create_worktree

    created = create_worktree(str(committed_repo))
    frame = {
        "method": "git-worktree-remove",
        "params": {
            "cwd": str(committed_repo),
            "worktree_path": created["path"],
            "force": False,
        },
    }
    result = daemon._handle_rpc_request(frame)
    assert result == {"ok": True}


def test_worktree_methods_are_advertised(daemon: MachineDaemon):
    # The server routes a method to this daemon only if it advertises it on
    # connect, so dispatch support is useless unless the method is announced.
    advertised = daemon._supported_rpc_methods()
    assert "git-worktree-list" in advertised
    assert "git-worktree-remove" in advertised


def _head(repo: Path) -> str:
    return (
        subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
        )
        .stdout.decode()
        .strip()
    )


def test_git_log_dispatched_to_handler(daemon: MachineDaemon, committed_repo: Path):
    frame = {"method": "git-log", "params": {"cwd": str(committed_repo)}}
    result = daemon._handle_rpc_request(frame)
    assert "commits" in result
    assert result["commits"][0]["subject"] == "seed"


def test_git_commit_files_dispatched_to_handler(
    daemon: MachineDaemon, committed_repo: Path
):
    frame = {
        "method": "git-commit-files",
        "params": {"cwd": str(committed_repo), "commit_id": _head(committed_repo)},
    }
    result = daemon._handle_rpc_request(frame)
    assert result["files"] == [
        {"path": "seed.txt", "status": "A", "additions": 1, "deletions": 0}
    ]


def test_git_commit_diff_dispatched_to_handler(
    daemon: MachineDaemon, committed_repo: Path
):
    frame = {
        "method": "git-commit-diff",
        "params": {
            "cwd": str(committed_repo),
            "commit_id": _head(committed_repo),
            "path": "seed.txt",
        },
    }
    result = daemon._handle_rpc_request(frame)
    assert result["path"] == "seed.txt"
    assert result["is_binary"] is False


def test_commit_history_methods_are_advertised(daemon: MachineDaemon):
    advertised = daemon._supported_rpc_methods()
    assert "git-log" in advertised
    assert "git-commit-files" in advertised
    assert "git-commit-diff" in advertised


# --------------------------------------------------------------------------
# Remote terminal (pty-* over the cloud relay)
# --------------------------------------------------------------------------
def test_pty_methods_are_advertised(daemon: MachineDaemon):
    advertised = daemon._supported_rpc_methods()
    for method in ("pty-spawn", "pty-write", "pty-resize", "pty-kill"):
        assert method in advertised


def test_terminal_capability_is_advertised(daemon: MachineDaemon):
    # The client feature-detects on this to offer the terminal for a remote
    # machine instead of failing `no_handler`.
    assert "terminal" in daemon._capabilities()


@pytest.mark.skipif(sys.platform.startswith("win"), reason="PTY sessions are Unix-only")
def test_pty_spawn_dispatched_to_terminal_service(
    daemon: MachineDaemon, tmp_path: Path
):
    # A remote pty-spawn builds the terminal service lazily and returns a live
    # pty_id; output would stream via push_frame (no ws client here → dropped).
    frame = {
        "method": "pty-spawn",
        "params": {
            "cwd": str(tmp_path),
            "cols": 80,
            "rows": 24,
            "command": ["/bin/cat"],
        },
    }
    result = daemon._handle_rpc_request(frame)
    pty_id = result["pty_id"]
    try:
        assert pty_id
        assert daemon._terminal_service is not None
        assert pty_id in daemon._terminal_service.live_session_ids()
        kill = daemon._handle_rpc_request(
            {"method": "pty-kill", "params": {"pty_id": pty_id}}
        )
        assert kill == {}
    finally:
        daemon._shutdown_terminals()
