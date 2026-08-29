"""Daemon RPC handler for `scan-files` — the `@`-mention project index.

See `plans/todos/file-mentions-live-rpc.md` §Phase 1.

This is the *whole-project* counterpart to `file_ops.list_files`, which lists
one directory level for the Files tab tree. The two are deliberately separate
methods: they answer different questions, cache differently, and — because
`list_files` filters through `git check-ignore` while this one goes through
`scan_project_files`/`pathspec` (which also serves non-git directories) — they
do not even share a definition of "ignored".

Caching model (plan §Foundational decisions #4, #5):

* Result memoized per project root, invalidated by a short TTL. NOT by
  `file_sync.get_newest_dir_mtime` — measured on the vicoa-ai monorepo, that
  probe costs 1.42 s against 0.07 s for the full scan it exists to avoid,
  because it `rglob`s into `node_modules`/`.venv` before filtering.
* A hit inside the TTL returns immediately. A stale hit returns the old list
  *and* schedules one background rescan, so the caller's next `@` gets fresh
  data without ever waiting on a scan.
* Refreshes are triggered by RPC arrival only. Nothing runs on a timer, so a
  laptop nobody is mentioning files on does zero work.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from vicoa.file_sync import scan_project_files

logger = logging.getLogger(__name__)

# How long a cached index is served without rescanning. The client refreshes in
# the background on every `@`, so this only has to be short enough that a file
# created mid-session shows up on the *next* mention, not the current one.
INDEX_TTL_SECONDS = 30.0

# Matches the desktop local server's `FILE_MENTIONS_MAX`. Bounds the worst
# observed project (245k paths, ~9 MB of JSON) to something a WebSocket frame
# can carry without stalling the connection.
DEFAULT_MAX_FILES = 20_000

# Project roots kept in memory at once. Someone bouncing between a handful of
# repos stays warm; a script walking a hundred directories can't grow the
# daemon unboundedly.
MAX_CACHED_PROJECTS = 8


@dataclass
class _Entry:
    files: list[str]
    hash: str
    # Two clocks on purpose: `monotonic` can't jump backwards over an NTP
    # correction or a laptop suspend, so it's the only safe basis for the TTL
    # comparison. It is also process-relative and therefore meaningless to a
    # client, so the wire carries the wall-clock stamp instead.
    scanned_at_monotonic: float
    scanned_at: float
    truncated: bool


_cache: "OrderedDict[str, _Entry]" = OrderedDict()
# Guards `_cache` and `_scanning`. Held only around dict access — never across
# a scan, so a slow scan of project A doesn't block a cache hit for project B.
_lock = threading.Lock()
# Roots with a scan in flight, so N concurrent `@`s cause one scan, not N.
_scanning: set[str] = set()


def _index_hash(files: list[str]) -> str:
    return hashlib.sha256("\n".join(files).encode("utf-8")).hexdigest()[:16]


def _normalize(cwd: str) -> str:
    return os.path.realpath(os.path.expanduser(cwd))


def _store(root: str, files: list[str], truncated: bool) -> _Entry:
    entry = _Entry(
        files=files,
        hash=_index_hash(files),
        scanned_at_monotonic=time.monotonic(),
        scanned_at=time.time(),
        truncated=truncated,
    )
    with _lock:
        _cache[root] = entry
        _cache.move_to_end(root)
        while len(_cache) > MAX_CACHED_PROJECTS:
            _cache.popitem(last=False)
    return entry


def _scan(root: str, max_files: int) -> _Entry:
    files = scan_project_files(root, max_files=max_files)
    # `scan_project_files` prints a warning and stops at the cap; it doesn't
    # report that it did. Inferring from the count is the only signal
    # available, and an exact-cap hit is the only false positive.
    return _store(root, files, truncated=len(files) >= max_files)


def _refresh_in_background(root: str, max_files: int) -> None:
    """Rescan `root` off the caller's thread, at most one scan at a time."""
    with _lock:
        if root in _scanning:
            return
        _scanning.add(root)

    def run() -> None:
        try:
            _scan(root, max_files)
        except Exception:
            logger.exception("background file-index refresh failed for %s", root)
        finally:
            with _lock:
                _scanning.discard(root)

    threading.Thread(target=run, name="vicoa-file-index", daemon=True).start()


def scan_files(
    cwd: str,
    known_hash: str | None = None,
    max_files: int = DEFAULT_MAX_FILES,
) -> dict[str, Any]:
    """Return the `@`-mention index for the project rooted at `cwd`.

    Unlike `list_files`/`read_file` there is no caller-supplied sub-path, so
    there is nothing to confine — `cwd` is a project root the caller already
    has a session in. Result shape mirrors the REST `/api/v1/files` body it
    replaces (`files` = folders with a trailing `/` first, then files, all
    forward-slash and relative to the root) so every existing fuzzy-matcher
    keeps working untouched.
    """
    root = _normalize(cwd)
    if not os.path.exists(root):
        return {"error": "path_not_found"}
    if not os.path.isdir(root):
        return {"error": "not_a_directory"}
    if not os.access(root, os.R_OK | os.X_OK):
        return {"error": "permission_denied"}

    with _lock:
        entry = _cache.get(root)
        if entry is not None:
            _cache.move_to_end(root)

    if entry is None:
        # Cold miss: the caller waits. Safe to block — the daemon runs RPC
        # handlers on a worker pool, so this holds up neither the WebSocket
        # receive loop nor any other call (see `spawn_ws_client.dispatch_frame`).
        entry = _scan(root, max_files)
    elif time.monotonic() - entry.scanned_at_monotonic > INDEX_TTL_SECONDS:
        # Stale: answer now from what we have, freshen for next time.
        _refresh_in_background(root, max_files)

    if known_hash is not None and known_hash == entry.hash:
        return {"unchanged": True, "hash": entry.hash}

    return {
        "files": entry.files,
        "file_count": len(entry.files),
        "hash": entry.hash,
        "truncated": entry.truncated,
        "scanned_at": entry.scanned_at,
    }


def reset_cache() -> None:
    """Drop every cached index. For tests."""
    with _lock:
        _cache.clear()
        _scanning.clear()
