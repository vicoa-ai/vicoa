"""Daemon RPC handlers for git: status/diff/log reads, plus the `git-write`
staging trio (`git-stage`/`git-unstage`/`git-commit`) behind the Changes tab.

See `plans/todos/vicoa-app-git-tab.md` §Phase B for the read-side spec.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from vicoa.rpc.file_ops import _TEXT_CAP, _sha256
from vicoa.rpc.paths import OutsideProject, resolve_inside_project

_UNTRACKED_LINE_COUNT_CAP = 100_000
_DIFF_CAP = 1 * 1024 * 1024

# Cap on total entries in one `git_status` response. A repo with a large
# un-ignored directory (a build output nobody gitignored, a fresh vendor drop)
# would otherwise push tens of thousands of rows through every poll of the Git
# tab. Past the cap we return a truncated list plus `did_hit_limit`, and skip
# every per-entry enrichment — those are the costs the cap exists to avoid.
_STATUS_ENTRY_LIMIT = 10_000

# Untracked files have no blob in the index for `git diff` to compare against,
# so their additions count has to come from reading the file. Large ones are
# usually generated assets; skip them rather than stall the poll.
_MAX_UNTRACKED_LINE_COUNT_BYTES = 2 * 1024 * 1024

# The cache must hold at least one full scan's untracked set. A smaller cache
# is worse than none: a scan wider than the cache evicts every entry before the
# next poll revisits it, so every poll re-reads every untracked file. 2x leaves
# headroom for a second repo (a worktree, a submodule) sharing the cache.
_UNTRACKED_STATS_CACHE_MAX_ENTRIES = 2 * _STATUS_ENTRY_LIMIT

_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")

_HEX_RE = re.compile(r"^[0-9a-fA-F]{4,40}$")
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's canonical empty tree
_GIT_LOG_MAX = 200
_LOG_FORMAT = "%H%x1f%h%x1f%P%x1f%an%x1f%ae%x1f%at%x1f%D%x1f%s%x1f%b"


def _git(
    repo: Path, *args: str, stdin: bytes | None = None
) -> subprocess.CompletedProcess[bytes]:
    """Run a read-only git command in `repo` and capture its output.

    `--no-optional-locks` is the point of the helper: every handler here is
    polled by the Git tab while an agent runs its own git commands in the same
    repo, and `status`/`diff` would otherwise refresh the index and contend on
    `.git/index.lock` with the agent's commit.
    """
    return subprocess.run(
        ["git", "--no-optional-locks", "-C", str(repo), *args],
        input=stdin,
        capture_output=True,
        check=False,
    )


def _is_git_repo(abs_dir: Path) -> bool:
    proc = _git(abs_dir, "rev-parse", "--is-inside-work-tree")
    return proc.returncode == 0 and proc.stdout.strip() == b"true"


def _split_porcelain_records(blob: bytes) -> list[bytes]:
    """Split `-z` porcelain output into one record per file/header.

    Tricky bit: rename records (`2 ...`) embed the original path after a NUL,
    so a single record spans two NUL-delimited segments. Everything else is
    one segment per record.
    """
    if not blob:
        return []
    parts = blob.split(b"\x00")
    # Trailing empty segment after the final NUL.
    if parts and parts[-1] == b"":
        parts.pop()

    records: list[bytes] = []
    i = 0
    while i < len(parts):
        seg = parts[i]
        if seg.startswith(b"2 "):
            # Rename — next segment is origPath.
            if i + 1 < len(parts):
                records.append(seg + b"\x00" + parts[i + 1])
                i += 2
                continue
        records.append(seg)
        i += 1
    return records


def _parse_branch_headers(records: list[bytes]) -> dict[str, Any]:
    info: dict[str, Any] = {
        "branch": "",
        "ahead": 0,
        "behind": 0,
        "detached_head": False,
    }
    oid = ""
    for rec in records:
        if not rec.startswith(b"# branch."):
            continue
        text = rec.decode("utf-8", errors="replace")[2:]  # strip "# "
        key, _, value = text.partition(" ")
        if key == "branch.head":
            if value == "(detached)":
                info["detached_head"] = True
            else:
                info["branch"] = value
        elif key == "branch.oid":
            oid = value
        elif key == "branch.upstream":
            info["upstream"] = value
        elif key == "branch.ab":
            parts = value.split()
            if len(parts) == 2:
                info["ahead"] = int(parts[0])
                info["behind"] = abs(int(parts[1]))
    if info["detached_head"] and oid:
        # Detached HEAD: branch.head reports "(detached)", so we surface the
        # short SHA from branch.oid as the displayed branch label instead.
        info["branch"] = oid[:7]
    return info


def _parse_numstat(blob: bytes) -> dict[str, tuple[int, int]]:
    """Return {path: (additions, deletions)} from `git diff --numstat -z`.

    Numstat is NUL-terminated per record. For renames, numstat emits a record
    like `A\\tD\\t\\0<origPath>\\0<newPath>\\0` — three tokens. For ordinary
    files, two tokens: `A\\tD\\t<path>\\0` becomes parts `["A\\tD\\t", path]`.
    """
    out: dict[str, tuple[int, int]] = {}
    if not blob:
        return out
    parts = blob.split(b"\x00")
    if parts and parts[-1] == b"":
        parts.pop()
    i = 0
    while i < len(parts):
        head = parts[i].decode("utf-8", errors="replace")
        # head is "<adds>\t<dels>\t<path?>" — if path is empty it's a rename
        # and the next two segments are origPath, newPath.
        bits = head.split("\t")
        if len(bits) < 2:
            i += 1
            continue
        adds_s, dels_s = bits[0], bits[1]
        # Binary files emit "-" / "-" — treat as 0/0.
        adds = int(adds_s) if adds_s.isdigit() else 0
        dels = int(dels_s) if dels_s.isdigit() else 0
        tail = bits[2] if len(bits) >= 3 else ""
        if tail:
            out[tail] = (adds, dels)
            i += 1
        else:
            # Rename: origPath, newPath are the next two segments.
            if i + 2 < len(parts):
                new_path = parts[i + 2].decode("utf-8", errors="replace")
                out[new_path] = (adds, dels)
                i += 3
            else:
                i += 1
    return out


def _batch_hash_object(repo: Path, rel_paths: list[str]) -> dict[str, str]:
    """Hash multiple working-tree paths in a single subprocess.

    Newline-separated input. Paths containing newlines are not supported —
    git's working tree allows them but they're vanishingly rare and the
    plan trades that edge case for the one-subprocess perf budget.
    """
    if not rel_paths:
        return {}
    proc = _git(
        repo,
        "hash-object",
        "--stdin-paths",
        stdin=("\n".join(rel_paths) + "\n").encode(),
    )
    if proc.returncode != 0:
        return {}
    hashes = proc.stdout.decode().splitlines()
    return dict(zip(rel_paths, hashes))


# path -> (size, mtime_ns, ctime_ns, additions). Guarded by the lock because the
# daemon serves RPCs from its websocket thread while tests drive it directly.
_untracked_stats_lock = threading.Lock()
_untracked_stats_cache: OrderedDict[str, tuple[int, int, int, int]] = OrderedDict()


def _read_additions(abs_file: Path, st: os.stat_result) -> int:
    """Line count for one untracked file, or 0 when it isn't countable text."""
    if stat.S_ISLNK(st.st_mode):
        # git stores a symlink's target path as its content — one line. Reading
        # through the link would count the target's lines instead, or fail
        # outright when it points at a directory.
        return 1
    if not stat.S_ISREG(st.st_mode) or st.st_size > _MAX_UNTRACKED_LINE_COUNT_BYTES:
        return 0
    try:
        data = abs_file.read_bytes()
    except OSError:
        return 0
    if not data:
        return 0
    if b"\x00" in data[:8192]:
        # Binary — same NUL heuristic `_synthesize_all_additions_diff` uses, so
        # a file counted as 0 here is the same one that renders as `is_binary`.
        return 0
    count = data.count(b"\n")
    if not data.endswith(b"\n"):
        # No trailing newline means the final partial line still counts, which
        # is what numstat reports for the equivalent tracked file.
        count += 1
    return min(count, _UNTRACKED_LINE_COUNT_CAP)


def _count_untracked_additions(abs_file: Path) -> int:
    """`_read_additions` memoized on the file's (size, mtime, ctime).

    This read happens for every untracked file on every status poll, so without
    the cache a repo carrying a few hundred new files re-reads all of them
    several times a minute.
    """
    key = str(abs_file)
    try:
        st = os.lstat(abs_file)
    except OSError:
        return 0
    stamp = (st.st_size, st.st_mtime_ns, st.st_ctime_ns)

    with _untracked_stats_lock:
        cached = _untracked_stats_cache.get(key)
        if cached is not None and cached[:3] == stamp:
            # Re-insert so eviction below is LRU rather than FIFO: a repo being
            # actively polled keeps its entries even while a scan of a second
            # repo streams through the same cache.
            _untracked_stats_cache.move_to_end(key)
            return cached[3]

    additions = _read_additions(abs_file, st)

    with _untracked_stats_lock:
        _untracked_stats_cache.pop(key, None)
        _untracked_stats_cache[key] = (*stamp, additions)
        while len(_untracked_stats_cache) > _UNTRACKED_STATS_CACHE_MAX_ENTRIES:
            _untracked_stats_cache.popitem(last=False)
    return additions


def git_status(cwd: str) -> dict[str, Any]:
    """Working-tree status relative to HEAD; see plan §RPC for shape."""
    abs_dir = Path(os.path.expanduser(cwd)).resolve()
    if not _is_git_repo(abs_dir):
        return {"error": "not_a_repo"}

    proc = _git(
        abs_dir,
        "status",
        "--porcelain=v2",
        "--branch",
        "-z",
        # Without this, git collapses a newly created directory into a single
        # `? dir/` record, so the Git tab shows one unopenable row instead of
        # the files inside it. Directories carrying their own `.git` (embedded
        # repos) stay collapsed either way — git will not descend into them,
        # which is why `git_diff` still needs its directory guard.
        "--untracked-files=all",
    )
    if proc.returncode != 0:
        return {"error": "not_a_repo"}

    records = _split_porcelain_records(proc.stdout)
    branch_info = _parse_branch_headers(records)

    staged: list[dict[str, Any]] = []
    unstaged: list[dict[str, Any]] = []
    untracked: list[dict[str, Any]] = []

    # Pass 1: parse porcelain into intermediate structs. Every per-entry cost —
    # numstat, untracked line counts, hash-object — is deferred to pass 2 so the
    # entry cap can skip all of it, and so a clean tree runs zero extra git.
    staged_stat_targets: list[dict[str, Any]] = []
    unstaged_stat_targets: list[dict[str, Any]] = []
    untracked_count_targets: list[dict[str, Any]] = []
    paths_to_hash: list[str] = []
    pending_hash: list[dict[str, Any]] = []

    for rec in records:
        if rec.startswith(b"# "):
            continue
        if rec.startswith(b"? "):
            path = rec[2:].decode("utf-8", errors="replace")
            entry: dict[str, Any] = {
                "path": path,
                "status": "??",
                "additions": 0,
                "deletions": 0,
                "content_hash": None,
            }
            # A trailing slash means git collapsed an untracked *directory*.
            # Under `-uall` that only happens for an embedded repo, which git
            # won't descend into. `hash-object` can't hash a directory, and it
            # aborts the whole batch when it hits one; there is likewise no
            # single file to count lines from.
            if not path.endswith("/"):
                untracked_count_targets.append(entry)
                pending_hash.append(entry)
                paths_to_hash.append(path)
            untracked.append(entry)
            continue
        if rec.startswith(b"! "):
            # ignored — not emitted unless --ignored is set
            continue
        if rec.startswith(b"u "):
            # unmerged — surface under unstaged with status "U"; no hash.
            text = rec.decode("utf-8", errors="replace")
            bits = text.split(" ", 10)
            if len(bits) >= 11:
                path = bits[10]
                unstaged.append(
                    {
                        "path": path,
                        "status": "U",
                        "additions": 0,
                        "deletions": 0,
                        "content_hash": None,
                    }
                )
            continue
        if rec.startswith(b"1 "):
            text = rec.decode("utf-8", errors="replace")
            bits = text.split(" ", 8)
            # ["1", XY, sub, mH, mI, mW, hH, hI, path]
            if len(bits) < 9:
                continue
            xy = bits[1]
            # `sub` is "N..." for an ordinary path, "S<c><m><u>" for a submodule.
            is_submodule = bits[2].startswith("S")
            hI = bits[7]
            path = bits[8]
            x, y = xy[0], xy[1]
            if x != ".":
                entry = {
                    "path": path,
                    "status": x,
                    "additions": 0,
                    "deletions": 0,
                    "content_hash": hI if x != "D" else None,
                }
                if is_submodule:
                    entry["is_submodule"] = True
                staged_stat_targets.append(entry)
                staged.append(entry)
            if y != ".":
                entry = {
                    "path": path,
                    "status": y,
                    "additions": 0,
                    "deletions": 0,
                    "content_hash": None,
                }
                unstaged_stat_targets.append(entry)
                if is_submodule:
                    entry["is_submodule"] = True
                # Submodules are directories: `hash-object` aborts on them, and
                # a non-zero exit throws away the whole batch, so every entry
                # would come back with a null hash. Keep them out of it.
                if y != "D" and not is_submodule:
                    pending_hash.append(entry)
                    paths_to_hash.append(path)
                unstaged.append(entry)
            continue
        if rec.startswith(b"2 "):
            text = rec.decode("utf-8", errors="replace")
            # `2 XY sub mH mI mW hH hI X<score> path\0origPath`
            head, _, orig_path = text.partition("\x00")
            bits = head.split(" ", 9)
            if len(bits) < 10:
                continue
            xy = bits[1]
            is_submodule = bits[2].startswith("S")
            hI = bits[7]
            new_path = bits[9]
            x, y = xy[0], xy[1]
            if x != ".":
                entry = {
                    "path": new_path,
                    "old_path": orig_path,
                    "status": x,
                    "additions": 0,
                    "deletions": 0,
                    "content_hash": hI if x != "D" else None,
                }
                if is_submodule:
                    entry["is_submodule"] = True
                staged_stat_targets.append(entry)
                staged.append(entry)
            if y != ".":
                entry = {
                    "path": new_path,
                    "status": y,
                    "additions": 0,
                    "deletions": 0,
                    "content_hash": None,
                }
                unstaged_stat_targets.append(entry)
                if is_submodule:
                    entry["is_submodule"] = True
                # See the `1 ` branch: submodule paths poison the hash batch.
                if y != "D" and not is_submodule:
                    pending_hash.append(entry)
                    paths_to_hash.append(new_path)
                unstaged.append(entry)

    # Stable, alphabetical-within-section ordering.
    staged.sort(key=lambda e: e["path"])
    unstaged.sort(key=lambda e: e["path"])
    untracked.sort(key=lambda e: e["path"])

    status_length = len(staged) + len(unstaged) + len(untracked)
    did_hit_limit = status_length > _STATUS_ENTRY_LIMIT

    if did_hit_limit:
        # Truncate in section order and skip pass 2 entirely. Rows come back
        # with zero counts and null hashes; the client renders its "too many
        # changes" state off `did_hit_limit` rather than trusting them.
        budget = _STATUS_ENTRY_LIMIT
        staged = staged[:budget]
        budget -= len(staged)
        unstaged = unstaged[:budget]
        budget -= len(unstaged)
        untracked = untracked[:budget]
    else:
        # Pass 2: per-entry enrichment, each step skipped when its section is
        # empty. Numstat is two calls by design — staged is index vs HEAD,
        # unstaged is worktree vs index.
        if staged_stat_targets:
            numstat = _parse_numstat(
                _git(abs_dir, "diff", "--cached", "--numstat", "-z").stdout
            )
            for entry in staged_stat_targets:
                entry["additions"], entry["deletions"] = numstat.get(
                    entry["path"], (0, 0)
                )
        if unstaged_stat_targets:
            numstat = _parse_numstat(_git(abs_dir, "diff", "--numstat", "-z").stdout)
            for entry in unstaged_stat_targets:
                entry["additions"], entry["deletions"] = numstat.get(
                    entry["path"], (0, 0)
                )
        for entry in untracked_count_targets:
            entry["additions"] = _count_untracked_additions(abs_dir / entry["path"])
        # One batched hash-object call for everything that needed one.
        hashes = _batch_hash_object(abs_dir, paths_to_hash)
        for entry in pending_hash:
            entry["content_hash"] = hashes.get(entry["path"])

    result: dict[str, Any] = {
        "branch": branch_info["branch"],
        "ahead": branch_info["ahead"],
        "behind": branch_info["behind"],
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
    }
    if "upstream" in branch_info:
        result["upstream"] = branch_info["upstream"]
    if branch_info["detached_head"]:
        result["detached_head"] = True
    if did_hit_limit:
        result["did_hit_limit"] = True
        result["status_length"] = status_length
    return result


def _parse_unified_diff(text: str) -> list[dict[str, Any]]:
    """Parse unified-diff text into typed hunks. Skips file headers."""
    hunks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        if line.startswith(
            (
                "diff --git",
                "index ",
                "--- ",
                "+++ ",
                "new file",
                "deleted file",
                "similarity",
                "rename ",
                "old mode",
                "new mode",
            )
        ):
            continue
        m = _HUNK_HEADER_RE.match(line)
        if m:
            old_start = int(m.group(1))
            old_count = int(m.group(2)) if m.group(2) else 1
            new_start = int(m.group(3))
            new_count = int(m.group(4)) if m.group(4) else 1
            current = {
                "header": line,
                "old_start": old_start,
                "old_count": old_count,
                "new_start": new_start,
                "new_count": new_count,
                "lines": [],
            }
            hunks.append(current)
            continue
        if current is None:
            continue
        if not line:
            # Empty line inside a hunk = context line with empty content.
            current["lines"].append({"type": "context", "content": ""})
            continue
        marker, content = line[0], line[1:]
        if marker == "+":
            current["lines"].append({"type": "add", "content": content})
        elif marker == "-":
            current["lines"].append({"type": "remove", "content": content})
        elif marker == " ":
            current["lines"].append({"type": "context", "content": content})
        elif marker == "\\":
            # "\ No newline at end of file" — drop, the renderer doesn't show it.
            continue
    return hunks


def _is_tracked(repo: Path, path: str) -> bool:
    proc = _git(repo, "ls-files", "--error-unmatch", "--", path)
    return proc.returncode == 0


def _synthesize_all_additions_diff(abs_file: Path, path: str) -> dict[str, Any]:
    """Read an untracked file head-slice and emit a one-hunk all-additions diff."""
    size = abs_file.stat().st_size
    with open(abs_file, "rb") as fh:
        head = fh.read(_DIFF_CAP)
    truncated = size > _DIFF_CAP
    if b"\x00" in head[:8192]:
        return {
            "path": path,
            "hunks": [],
            "is_binary": True,
            "truncated": False,
            "size": size,
        }
    text = head.decode("utf-8", errors="replace")
    # Preserve trailing-newline semantics: `"a\nb\n"`.splitlines() = ["a", "b"]
    lines = text.splitlines()
    if not lines:
        return {
            "path": path,
            "hunks": [],
            "is_binary": False,
            "truncated": truncated,
            "size": size,
        }
    hunk = {
        "header": f"@@ -0,0 +1,{len(lines)} @@",
        "old_start": 0,
        "old_count": 0,
        "new_start": 1,
        "new_count": len(lines),
        "lines": [{"type": "add", "content": ln} for ln in lines],
    }
    return {
        "path": path,
        "hunks": [hunk],
        "is_binary": False,
        "truncated": truncated,
        "size": size,
    }


def git_diff(
    cwd: str,
    path: str,
    staged: bool = False,
    ignore_whitespace: bool = False,
) -> dict[str, Any]:
    """Return a typed diff for `path` in `cwd`; see plan §RPC for shape."""
    project_root = Path(os.path.expanduser(cwd))
    try:
        abs_file = resolve_inside_project(project_root, path)
    except OutsideProject:
        return {"error": "outside_project"}

    repo_root = project_root.resolve()

    # Untracked files: `git diff` emits nothing. Synthesize a fake all-additions
    # diff so the client can render it the same as a tracked modification.
    if not staged and abs_file.exists() and not _is_tracked(repo_root, path):
        if not abs_file.is_file():
            # Untracked *directories* — most often an embedded git repo (its own
            # `.git`, not a registered submodule) — are reported by `git status`
            # as a single path with a trailing slash, and git won't descend into
            # them (even with -uall). There's no single-file diff to synthesize,
            # so return an empty diff instead of crashing on `open()` of a
            # non-regular path (regression: IsADirectoryError).
            return {
                "path": path,
                "hunks": [],
                "is_binary": False,
                "truncated": False,
                "size": 0,
            }
        return _synthesize_all_additions_diff(abs_file, path)

    argv = ["diff", "--no-color", "--no-ext-diff", "--no-prefix"]
    if staged:
        argv.append("--cached")
    if ignore_whitespace:
        argv.append("-w")
    argv.extend(["--", path])

    proc = _git(repo_root, *argv)
    if proc.returncode not in (
        0,
        1,
    ):  # git diff returns 1 if there were differences in some modes
        # Anything else (128 etc.) likely means bad path or repo issue.
        if not abs_file.exists():
            return {"error": "path_not_found"}
        return {"error": "not_a_repo"}

    size = abs_file.stat().st_size if abs_file.exists() else 0
    return _finalize_diff(proc.stdout, path, size)


def _finalize_diff(raw: bytes, path: str, size: int) -> dict[str, Any]:
    """Shared tail for diff outputs: binary detection, cap-truncation, parse.

    Used by both `git_diff` (working tree) and `git_commit_diff` (a commit).
    """
    # Binary detection: "Binary files ... differ".
    if b"\nBinary files " in b"\n" + raw:
        return {
            "path": path,
            "hunks": [],
            "is_binary": True,
            "truncated": False,
            "size": size,
        }

    truncated = False
    if len(raw) > _DIFF_CAP:
        truncated = True
        # Head-slice; drop trailing partial hunk by cutting at the last
        # full line boundary so the parser never sees half a line.
        sliced = raw[:_DIFF_CAP]
        last_nl = sliced.rfind(b"\n")
        if last_nl >= 0:
            sliced = sliced[: last_nl + 1]
        raw = sliced

    text = raw.decode("utf-8", errors="replace")
    hunks = _parse_unified_diff(text)
    if truncated and hunks:
        # The final hunk may be only partially populated; trim it so the
        # client doesn't render a fake "added/removed N lines" hunk.
        last = hunks[-1]
        if len(last["lines"]) < (last["old_count"] + last["new_count"]):
            # Re-slice to the last completed hunk if possible.
            if len(hunks) > 1:
                hunks = hunks[:-1]

    return {
        "path": path,
        "hunks": hunks,
        "is_binary": False,
        "truncated": truncated,
        "size": size,
    }


def git_show_file(cwd: str, path: str, ref: str = "HEAD") -> dict[str, Any]:
    """Return the contents of `path` at git revision `ref` (default HEAD).

    The baseline ("original") side of the editable diff view: the working-tree
    file (`read_file`) is the modified side, and this is what the client diffs
    it against. `ref` is a revision like `"HEAD"`, or `""` for the staged/index
    blob (`git show :<path>`). The result mirrors `read_file`'s shape so the
    client reuses one type. A path absent at `ref` — a newly-added/untracked
    file, or an unborn HEAD in a fresh repo — returns `{"not_in_ref": True}`,
    which the client renders as an empty original (an all-added diff).
    """
    project_root = Path(os.path.expanduser(cwd))
    try:
        resolve_inside_project(project_root, path)
    except OutsideProject:
        return {"error": "outside_project"}

    repo_root = project_root.resolve()
    if not _is_git_repo(repo_root):
        return {"error": "not_a_repo"}

    proc = _git(repo_root, "show", f"{ref}:{path}")
    if proc.returncode != 0:
        return {"not_in_ref": True}

    data = proc.stdout
    size = len(data)
    if b"\x00" in data[:8192]:
        return {
            "content": "",
            "encoding": "utf-8",
            "is_binary": True,
            "size": size,
            "truncated": False,
            "content_hash": None,
        }
    truncated = size > _TEXT_CAP
    head = data[:_TEXT_CAP] if truncated else data
    return {
        "content": head.decode("utf-8", errors="replace"),
        "encoding": "utf-8",
        "is_binary": False,
        "size": size,
        "truncated": truncated,
        # None when truncated: the client keeps it read-only, same as read_file.
        "content_hash": None if truncated else _sha256(data),
    }


def _parse_decorations(deco: str) -> list[dict[str, str]]:
    """Parse `%D` from `--decorate=full` into [{name, kind}] refs.

    Kinds: `head` (the `HEAD` pointer), `branch` (refs/heads/*),
    `remote` (refs/remotes/*), `tag` (refs/tags/*). Other namespaces ignored.
    """
    refs: list[dict[str, str]] = []
    deco = deco.strip()
    if not deco:
        return refs
    for raw in deco.split(", "):
        token = raw.strip()
        if not token:
            continue
        if token.startswith("HEAD -> "):
            refs.append({"name": "HEAD", "kind": "head"})
            token = token[len("HEAD -> ") :]
        elif token == "HEAD":
            refs.append({"name": "HEAD", "kind": "head"})
            continue
        if token.startswith("tag: refs/tags/"):
            refs.append({"name": token[len("tag: refs/tags/") :], "kind": "tag"})
        elif token.startswith("refs/tags/"):
            refs.append({"name": token[len("refs/tags/") :], "kind": "tag"})
        elif token.startswith("refs/remotes/"):
            refs.append({"name": token[len("refs/remotes/") :], "kind": "remote"})
        elif token.startswith("refs/heads/"):
            refs.append({"name": token[len("refs/heads/") :], "kind": "branch"})
    return refs


def _rev_parse(abs_dir: Path, *args: str) -> str | None:
    """`git rev-parse <args>` → stripped stdout, or None on failure/empty."""
    proc = _git(abs_dir, "rev-parse", *args)
    if proc.returncode != 0:
        return None
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    return out or None


def git_log(cwd: str, limit: int = 50) -> dict[str, Any]:
    """Commit history (newest first, topo order) with ref decorations.

    Returns `{commits, has_more, current_ref?, upstream_ref?}`. Fetches
    `limit + 1` to compute `has_more`. `current_ref`/`upstream_ref` feed the
    web client's lane-graph coloring.
    """
    abs_dir = Path(os.path.expanduser(cwd)).resolve()
    if not _is_git_repo(abs_dir):
        return {"error": "not_a_repo"}
    try:
        limit = max(1, min(int(limit), _GIT_LOG_MAX))
    except (TypeError, ValueError):
        limit = 50

    proc = _git(
        abs_dir,
        "log",
        f"--format={_LOG_FORMAT}",
        "-z",
        "--topo-order",
        "--decorate=full",
        f"-n{limit + 1}",
    )
    if proc.returncode != 0:
        # Most common cause: a repo with no commits yet.
        return {"commits": [], "has_more": False}

    commits: list[dict[str, Any]] = []
    # `-z` NUL-separates commits; fields inside a commit are US (0x1f)-separated.
    chunks = proc.stdout.split(b"\x00")
    if chunks and chunks[-1] == b"":
        chunks.pop()
    for chunk in chunks:
        fields = chunk.decode("utf-8", errors="replace").split("\x1f")
        if len(fields) < 9:
            continue
        h, short, parents, an, ae, at, deco, subject, body = fields[:9]
        commits.append(
            {
                "id": h,
                "short_id": short,
                "parent_ids": parents.split() if parents else [],
                "author_name": an,
                "author_email": ae,
                "timestamp": int(at) if at.isdigit() else 0,
                "refs": _parse_decorations(deco),
                "subject": subject,
                "body": body.rstrip("\n"),
            }
        )

    has_more = len(commits) > limit
    if has_more:
        commits = commits[:limit]

    result: dict[str, Any] = {"commits": commits, "has_more": has_more}

    cur_name = _git(abs_dir, "symbolic-ref", "--quiet", "--short", "HEAD")
    if cur_name.returncode == 0:
        name = cur_name.stdout.decode("utf-8", errors="replace").strip()
        rev = _rev_parse(abs_dir, "HEAD")
        if name and rev:
            result["current_ref"] = {"name": name, "revision": rev}
        up_name = _rev_parse(
            abs_dir, "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
        )
        if up_name:
            up_rev = _rev_parse(abs_dir, "@{upstream}")
            if up_rev:
                result["upstream_ref"] = {"name": up_name, "revision": up_rev}
    return result


def _parse_name_status(blob: bytes) -> list[dict[str, Any]]:
    """Parse `git diff-tree --name-status -z` records into ordered metas.

    Rename/copy (`R`/`C`) records span three NUL segments: status, oldPath,
    newPath. Everything else is two: status, path.
    """
    out: list[dict[str, Any]] = []
    parts = blob.split(b"\x00")
    if parts and parts[-1] == b"":
        parts.pop()
    i = 0
    while i < len(parts):
        code = parts[i].decode("utf-8", errors="replace")
        if not code:
            i += 1
            continue
        letter = code[0]
        if letter in ("R", "C") and i + 2 < len(parts):
            out.append(
                {
                    "path": parts[i + 2].decode("utf-8", errors="replace"),
                    "old_path": parts[i + 1].decode("utf-8", errors="replace"),
                    "status": letter,
                }
            )
            i += 3
        elif i + 1 < len(parts):
            out.append(
                {
                    "path": parts[i + 1].decode("utf-8", errors="replace"),
                    "status": letter,
                }
            )
            i += 2
        else:
            i += 1
    return out


def git_commit_files(cwd: str, commit_id: str) -> dict[str, Any]:
    """Files changed by `commit_id` (first-parent for merges, --root for root)."""
    abs_dir = Path(os.path.expanduser(cwd)).resolve()
    if not _is_git_repo(abs_dir):
        return {"error": "not_a_repo"}
    if not _HEX_RE.match(commit_id):
        return {"error": "rpc_failed"}

    base_args = [
        "diff-tree",
        "-r",
        "-M",
        "-C",
        "--root",
        "--first-parent",
        "--no-commit-id",
    ]
    ns = _git(abs_dir, *base_args, "--name-status", "-z", commit_id)
    if ns.returncode != 0:
        return {"error": "rpc_failed"}
    numstat = _parse_numstat(
        _git(abs_dir, *base_args, "--numstat", "-z", commit_id).stdout
    )

    files: list[dict[str, Any]] = []
    insertions = deletions = 0
    for meta in _parse_name_status(ns.stdout):
        adds, dels = numstat.get(meta["path"], (0, 0))
        insertions += adds
        deletions += dels
        entry: dict[str, Any] = {
            "path": meta["path"],
            "status": meta["status"],
            "additions": adds,
            "deletions": dels,
        }
        if "old_path" in meta:
            entry["old_path"] = meta["old_path"]
        files.append(entry)

    return {
        "files": files,
        "stats": {
            "files": len(files),
            "insertions": insertions,
            "deletions": deletions,
        },
    }


def git_commit_diff(cwd: str, commit_id: str, path: str) -> dict[str, Any]:
    """Diff of a single `path` introduced by `commit_id` (vs its first parent).

    Same shape as `git_diff`. The root commit diffs against the empty tree.
    """
    if not _HEX_RE.match(commit_id):
        return {"error": "rpc_failed"}
    project_root = Path(os.path.expanduser(cwd))
    try:
        resolve_inside_project(project_root, path)
    except OutsideProject:
        return {"error": "outside_project"}
    repo_root = project_root.resolve()
    if not _is_git_repo(repo_root):
        return {"error": "not_a_repo"}

    has_parent = (
        _git(repo_root, "rev-parse", "--verify", "--quiet", f"{commit_id}^").returncode
        == 0
    )
    base = f"{commit_id}^" if has_parent else _EMPTY_TREE
    proc = _git(
        repo_root,
        "diff",
        "--no-color",
        "--no-ext-diff",
        "--no-prefix",
        base,
        commit_id,
        "--",
        path,
    )
    if proc.returncode not in (0, 1):
        return {"error": "rpc_failed"}
    return _finalize_diff(proc.stdout, path, len(proc.stdout))


def _validate_write_paths(repo_root: Path, paths: Any) -> list[str] | dict[str, Any]:
    """Shared validation for stage/unstage: a non-empty list of confined paths.

    Returns the paths as literal pathspecs (`:(literal)…`) so a filename
    containing `*`/`?`/`[` stages exactly that file instead of globbing.
    """
    if not isinstance(paths, list) or not paths:
        return {"error": "rpc_failed"}
    for p in paths:
        if not isinstance(p, str) or not p:
            return {"error": "rpc_failed"}
        try:
            # Deleted files still validate: resolve() doesn't require existence.
            resolve_inside_project(repo_root, p)
        except OutsideProject:
            return {"error": "outside_project"}
    return [f":(literal){p}" for p in paths]


def git_stage(cwd: str, paths: list[str]) -> dict[str, Any]:
    """`git add` the given repo-relative paths (stages deletions too)."""
    repo_root = Path(os.path.expanduser(cwd)).resolve()
    if not _is_git_repo(repo_root):
        return {"error": "not_a_repo"}
    specs = _validate_write_paths(repo_root, paths)
    if isinstance(specs, dict):
        return specs
    proc = _git(repo_root, "add", "--", *specs)
    if proc.returncode != 0:
        return {
            "error": "stage_failed",
            "message": proc.stderr.decode("utf-8", errors="replace").strip()[:2000],
        }
    return {"ok": True}


def git_unstage(cwd: str, paths: list[str]) -> dict[str, Any]:
    """Reset the index entries for `paths` back to HEAD (the empty tree on an
    unborn branch, where `git reset HEAD` has nothing to resolve)."""
    repo_root = Path(os.path.expanduser(cwd)).resolve()
    if not _is_git_repo(repo_root):
        return {"error": "not_a_repo"}
    specs = _validate_write_paths(repo_root, paths)
    if isinstance(specs, dict):
        return specs
    base = (
        "HEAD" if _rev_parse(repo_root, "--verify", "--quiet", "HEAD") else _EMPTY_TREE
    )
    proc = _git(repo_root, "reset", "-q", base, "--", *specs)
    if proc.returncode != 0:
        return {
            "error": "unstage_failed",
            "message": proc.stderr.decode("utf-8", errors="replace").strip()[:2000],
        }
    return {"ok": True}


def git_commit(cwd: str, message: str) -> dict[str, Any]:
    """Commit whatever is staged. Failures (nothing staged, missing identity,
    a hook rejecting) come back as `commit_failed` with git's own message so
    the client can show something actionable."""
    repo_root = Path(os.path.expanduser(cwd)).resolve()
    if not _is_git_repo(repo_root):
        return {"error": "not_a_repo"}
    if not isinstance(message, str) or not message.strip():
        return {"error": "commit_failed", "message": "Commit message is empty"}
    proc = _git(repo_root, "commit", "-m", message)
    if proc.returncode != 0:
        detail = (
            proc.stderr.decode("utf-8", errors="replace").strip()
            or proc.stdout.decode("utf-8", errors="replace").strip()
        )
        return {"error": "commit_failed", "message": detail[:2000]}
    commit_id = _rev_parse(repo_root, "HEAD")
    return {"ok": True, "commit_id": commit_id}
