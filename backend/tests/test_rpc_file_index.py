"""Daemon-side `scan-files` RPC — the live `@`-mention project index.

Covers `plans/todos/file-mentions-live-rpc.md` §Phase 1. The contract these
tests pin down is what web and mobile fall back *off* the DB onto, so the
result shape (`files` = folders-then-files, forward-slash, relative) matters
as much as the caching behaviour.
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import pytest

from vicoa.rpc import file_index
from vicoa.rpc.file_index import scan_files


@pytest.fixture(autouse=True)
def _clean_index_cache():
    """The index memo is module-level; isolate every test from its neighbours."""
    file_index.reset_cache()
    yield
    file_index.reset_cache()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')\n")
    (tmp_path / "README.md").write_text("# hi\n")
    return tmp_path


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


def test_scan_returns_folders_and_files_relative_to_the_root(project: Path):
    result = scan_files(cwd=str(project))

    assert "src/" in result["files"]
    assert "src/main.py" in result["files"]
    assert "README.md" in result["files"]
    assert result["file_count"] == len(result["files"])
    assert result["truncated"] is False


def test_scanned_at_is_wall_clock_not_the_ttl_clock(project: Path):
    """`scanned_at` crosses the wire, so it must be a timestamp a client can
    interpret — `time.monotonic()` is process-relative and would read as a
    nonsense date. The TTL comparison uses the monotonic clock separately."""
    before = time.time()
    result = scan_files(cwd=str(project))
    assert before <= result["scanned_at"] <= time.time()


def test_scan_honours_gitignore(project: Path):
    (project / ".gitignore").write_text("secrets/\n")
    (project / "secrets").mkdir()
    (project / "secrets" / "key.txt").write_text("shh\n")

    files = scan_files(cwd=str(project))["files"]

    assert not any(f.startswith("secrets") for f in files)


def test_scan_expands_a_tilde_path(project: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOME", str(project.parent))
    result = scan_files(cwd=f"~/{project.name}")
    assert "README.md" in result["files"]


def test_scan_sets_truncated_when_the_cap_is_hit(project: Path):
    for i in range(20):
        (project / f"f{i}.txt").write_text("x")

    result = scan_files(cwd=str(project), max_files=5)

    assert result["truncated"] is True


# ---------------------------------------------------------------------------
# Errors — the daemon is authoritative about its own disk, so these do NOT
# fall back to the DB copy on the client.
# ---------------------------------------------------------------------------


def test_missing_root_returns_path_not_found(tmp_path: Path):
    assert scan_files(cwd=str(tmp_path / "nope")) == {"error": "path_not_found"}


def test_file_as_root_returns_not_a_directory(project: Path):
    assert scan_files(cwd=str(project / "README.md")) == {"error": "not_a_directory"}


def test_unreadable_root_returns_permission_denied(tmp_path: Path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        assert scan_files(cwd=str(locked)) == {"error": "permission_denied"}
    finally:
        locked.chmod(0o755)  # so pytest can clean up


# ---------------------------------------------------------------------------
# Caching: TTL, serve-stale-then-refresh, single-flight
# ---------------------------------------------------------------------------


def test_second_call_inside_the_ttl_does_not_rescan(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    scans = {"n": 0}
    real = file_index.scan_project_files

    def counting(*a, **k):
        scans["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(file_index, "scan_project_files", counting)

    scan_files(cwd=str(project))
    scan_files(cwd=str(project))

    assert scans["n"] == 1


def test_a_stale_entry_is_served_immediately_and_refreshed_behind_it(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    """The whole point of the design: the caller never waits on a rescan, and
    the file created after the first scan is mentionable on the *next* `@`."""
    monkeypatch.setattr(file_index, "INDEX_TTL_SECONDS", 0.0)

    first = scan_files(cwd=str(project))
    assert "late.py" not in first["files"]

    (project / "late.py").write_text("x\n")
    stale = scan_files(cwd=str(project))
    assert "late.py" not in stale["files"]  # served from cache, not rescanned

    assert _wait_for(lambda: "late.py" in scan_files(cwd=str(project))["files"])


def test_concurrent_callers_trigger_a_single_scan(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    """N tabs typing `@` at once must cost one scan, not N."""
    monkeypatch.setattr(file_index, "INDEX_TTL_SECONDS", 0.0)
    scans = {"n": 0}
    real = file_index.scan_project_files
    started = threading.Event()

    def slow(*a, **k):
        scans["n"] += 1
        started.set()
        time.sleep(0.2)
        return real(*a, **k)

    scan_files(cwd=str(project))  # prime, so the next calls take the stale path
    monkeypatch.setattr(file_index, "scan_project_files", slow)

    threads = [
        threading.Thread(target=lambda: scan_files(cwd=str(project))) for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5.0)

    assert started.wait(5.0)
    assert _wait_for(lambda: not file_index._scanning)
    assert scans["n"] == 1


def test_a_slow_scan_of_one_project_does_not_block_another(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The cache lock must never be held across a scan."""
    other = tmp_path.parent / "other-project"
    other.mkdir()
    (other / "a.txt").write_text("x")
    real = file_index.scan_project_files
    slow_root = str(project.resolve())

    def slow(path, *a, **k):
        # Exact match, not `in`: `project` is tmp_path itself, so a substring
        # test would also slow down anything created underneath it.
        if str(Path(path).resolve()) == slow_root:
            time.sleep(1.0)
        return real(path, *a, **k)

    monkeypatch.setattr(file_index, "scan_project_files", slow)

    blocker = threading.Thread(target=lambda: scan_files(cwd=str(project)))
    blocker.start()
    time.sleep(0.1)  # let it get inside the slow scan

    started = time.monotonic()
    assert "a.txt" in scan_files(cwd=str(other))["files"]
    assert time.monotonic() - started < 0.5

    blocker.join(5.0)


def test_cache_evicts_the_least_recently_used_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(file_index, "MAX_CACHED_PROJECTS", 2)
    roots = []
    for name in ("a", "b", "c"):
        root = tmp_path / name
        root.mkdir()
        (root / f"{name}.txt").write_text("x")
        roots.append(root)
        scan_files(cwd=str(root))

    assert len(file_index._cache) == 2
    assert str(roots[0].resolve()) not in file_index._cache


# ---------------------------------------------------------------------------
# known_hash round-trip
# ---------------------------------------------------------------------------


def test_matching_known_hash_returns_unchanged_without_the_payload(project: Path):
    first = scan_files(cwd=str(project))

    result = scan_files(cwd=str(project), known_hash=first["hash"])

    assert result == {"unchanged": True, "hash": first["hash"]}
    assert "files" not in result


def test_stale_known_hash_returns_the_full_index(project: Path):
    result = scan_files(cwd=str(project), known_hash="deadbeefdeadbeef")

    assert "files" in result
    assert result["hash"] != "deadbeefdeadbeef"


def test_the_hash_changes_when_a_file_is_added(
    project: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(file_index, "INDEX_TTL_SECONDS", 0.0)
    before = scan_files(cwd=str(project))["hash"]

    (project / "new.py").write_text("x\n")
    file_index.reset_cache()
    after = scan_files(cwd=str(project))["hash"]

    assert before != after


# ---------------------------------------------------------------------------
# Wiring: the daemon must route and advertise the method
# ---------------------------------------------------------------------------


def test_daemon_advertises_scan_files_and_the_file_index_capability():
    from vicoa.machine_daemon import MachineDaemon

    daemon = MachineDaemon.__new__(MachineDaemon)
    assert "scan-files" in daemon._supported_rpc_methods()
    assert "file-index" in daemon._capabilities()


def test_daemon_dispatches_scan_files_to_the_handler(project: Path):
    from vicoa.machine_daemon import MachineDaemon

    daemon = MachineDaemon.__new__(MachineDaemon)
    result = daemon._handle_rpc_request(
        {"method": "scan-files", "params": {"cwd": str(project)}}
    )

    assert "README.md" in result["files"]
