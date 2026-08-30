"""Daemon RPC handlers for `list-files` and `read-file`.

See `plans/todos/vicoa-app-files-tab.md` §Phase B for the full spec.
"""

from __future__ import annotations

import base64
import fnmatch
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from vicoa.file_sync import DEFAULT_EXCLUDE_PATTERNS, get_excluded_dir_names
from vicoa.rpc.paths import OutsideProject, resolve_inside_project

_EXCLUDED_DIR_NAMES = get_excluded_dir_names()
_EXCLUDED_FILE_GLOBS = tuple(p for p in DEFAULT_EXCLUDE_PATTERNS if "*" in p)

_TEXT_CAP = 1 * 1024 * 1024
_IMAGE_CAP = 5 * 1024 * 1024
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _content_hash(abs_file: Path, size: int) -> str | None:
    """sha256 of the on-disk bytes, or None when the file isn't editable.

    None for binary (NUL in the first 8 KB) and for anything larger than the
    editable text cap — the exact files whose edit affordance is disabled, so a
    None hash never gates a save. `read_file`, `stat_file`, and `write_file`'s
    conflict check all agree because they hash the same bytes the same way.
    """
    if size > _TEXT_CAP:
        return None
    try:
        with open(abs_file, "rb") as fh:
            data = fh.read(_TEXT_CAP + 1)
    except OSError:
        return None
    if len(data) > _TEXT_CAP or b"\x00" in data[:8192]:
        return None
    return _sha256(data)


def _matches_default_exclude(name: str, is_dir: bool) -> bool:
    if is_dir and name in _EXCLUDED_DIR_NAMES:
        return True
    if not is_dir and any(fnmatch.fnmatch(name, glob) for glob in _EXCLUDED_FILE_GLOBS):
        return True
    return False


def _filter_gitignored(abs_dir: Path, names: list[str]) -> set[str]:
    """Return the subset of `names` git considers ignored under `abs_dir`.

    One subprocess per call — names are batched into a single `check-ignore`
    invocation. Exit code 1 (no matches) is normal, not an error.
    """
    if not names:
        return set()
    proc = subprocess.run(
        ["git", "-C", str(abs_dir), "check-ignore", "-z", "--stdin"],
        input="\0".join(names).encode(),
        capture_output=True,
        check=False,
    )
    return {n for n in proc.stdout.decode().split("\0") if n}


def list_files(cwd: str, path: str) -> dict[str, Any]:
    """List one directory level inside `cwd`, filtering ignored + .git entries."""
    project_root = Path(os.path.expanduser(cwd))
    try:
        abs_dir = resolve_inside_project(project_root, path)
    except OutsideProject:
        return {"error": "outside_project"}

    try:
        scanner = os.scandir(abs_dir)
    except FileNotFoundError:
        return {"error": "path_not_found"}
    except NotADirectoryError:
        return {"error": "not_a_directory"}
    except PermissionError:
        return {"error": "permission_denied"}

    project_root_real = project_root.resolve()
    raw: list[os.DirEntry[str]] = []
    with scanner as it:
        for entry in it:
            if entry.name == ".git":
                continue
            if entry.is_symlink():
                target = Path(entry.path).resolve()
                if target != project_root_real and not str(target).startswith(
                    str(project_root_real) + os.sep
                ):
                    continue
            raw.append(entry)

    ignored = _filter_gitignored(abs_dir, [e.name for e in raw])

    entries: list[dict[str, Any]] = []
    for entry in raw:
        if entry.name in ignored:
            continue
        is_dir = entry.is_dir()
        if _matches_default_exclude(entry.name, is_dir):
            continue
        row: dict[str, Any] = {
            "name": entry.name,
            "type": "dir" if is_dir else "file",
        }
        if not is_dir:
            row["size"] = entry.stat().st_size
        entries.append(row)
    entries.sort(key=lambda e: (e["type"] == "file", e["name"].lower()))
    return {"entries": entries}


def read_file(cwd: str, path: str) -> dict[str, Any]:
    """Return the working-tree contents of `path` under `cwd`, capped."""
    project_root = Path(os.path.expanduser(cwd))
    try:
        abs_file = resolve_inside_project(project_root, path)
    except OutsideProject:
        return {"error": "outside_project"}

    try:
        st = abs_file.stat()
    except FileNotFoundError:
        return {"error": "path_not_found"}
    except PermissionError:
        return {"error": "permission_denied"}
    if not abs_file.is_file():
        return {"error": "not_a_file"}
    size = st.st_size
    is_image = abs_file.suffix.lower() in _IMAGE_EXTS
    if is_image:
        with open(abs_file, "rb") as fh:
            data = fh.read(_IMAGE_CAP)
        return {
            "content": base64.b64encode(data).decode("ascii"),
            "encoding": "base64",
            "is_binary": True,
            "size": size,
            "truncated": size > _IMAGE_CAP,
            "content_hash": None,
        }
    with open(abs_file, "rb") as fh:
        head = fh.read(_TEXT_CAP)
    if b"\x00" in head[:8192]:
        return {
            "content": "",
            "encoding": "utf-8",
            "is_binary": True,
            "size": size,
            "truncated": False,
            "content_hash": None,
        }
    truncated = size > _TEXT_CAP
    return {
        "content": head.decode("utf-8", errors="replace"),
        "encoding": "utf-8",
        "is_binary": False,
        "size": size,
        "truncated": truncated,
        # None when truncated: editing is disabled there, and saving a partial
        # buffer must never be allowed (it would drop the tail).
        "content_hash": None if truncated else _sha256(head),
    }


def stat_file(cwd: str, path: str) -> dict[str, Any]:
    """Cheap freshness probe for an open file — size, mtime, and content hash.

    The web panel polls this for open editable tabs to detect that the agent
    (or anything else) rewrote a file underneath the user, without re-sending
    the contents. `content_hash` matches `read_file`'s so a hash change is the
    reliable "changed on disk" signal.
    """
    project_root = Path(os.path.expanduser(cwd))
    try:
        abs_file = resolve_inside_project(project_root, path)
    except OutsideProject:
        return {"error": "outside_project"}
    try:
        st = abs_file.stat()
    except FileNotFoundError:
        return {"error": "path_not_found"}
    except PermissionError:
        return {"error": "permission_denied"}
    if not abs_file.is_file():
        return {"error": "not_a_file"}
    return {
        "size": st.st_size,
        "mtime": st.st_mtime,
        "content_hash": _content_hash(abs_file, st.st_size),
    }


def write_file(
    cwd: str,
    path: str,
    content: str,
    base_hash: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Write `content` (UTF-8) to `path` under `cwd`, atomically.

    Conflict guard: unless `force`, the on-disk content hash must equal
    `base_hash` (the hash the caller held when it opened the file). A mismatch —
    including the file being deleted or replaced by a binary/oversized blob —
    returns `{"error": "conflict", "content_hash": <current>}` rather than
    clobbering a concurrent write (e.g. the agent editing the same file). The
    caller resolves it (reload or overwrite with `force`).

    The write itself is atomic: a temp file in the same directory is written,
    chmod-ed to the original's mode, then `os.replace`d over the target, so a
    crash mid-write can never leave a half-written file.
    """
    project_root = Path(os.path.expanduser(cwd))
    try:
        abs_file = resolve_inside_project(project_root, path)
    except OutsideProject:
        return {"error": "outside_project"}

    try:
        st = abs_file.stat()
        exists = True
    except FileNotFoundError:
        st = None
        exists = False
    except PermissionError:
        return {"error": "permission_denied"}
    if exists and not abs_file.is_file():
        return {"error": "not_a_file"}

    current_hash = _content_hash(abs_file, st.st_size) if (exists and st) else None
    if not force and base_hash != current_hash:
        return {"error": "conflict", "content_hash": current_hash}

    data = content.encode("utf-8")
    parent = abs_file.parent
    try:
        fd, tmp_name = tempfile.mkstemp(dir=parent, prefix=".vicoa-tmp-", suffix=".tmp")
    except (PermissionError, FileNotFoundError):
        return {"error": "permission_denied"}
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        if exists and st is not None:
            try:
                os.chmod(tmp_name, st.st_mode & 0o777)
            except OSError:
                pass
        os.replace(tmp_name, abs_file)
    except PermissionError:
        _unlink_quiet(tmp_name)
        return {"error": "permission_denied"}
    except OSError:
        _unlink_quiet(tmp_name)
        return {"error": "write_failed"}

    new_st = abs_file.stat()
    return {
        "size": new_st.st_size,
        "mtime": new_st.st_mtime,
        "content_hash": _sha256(data),
    }


def _unlink_quiet(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
