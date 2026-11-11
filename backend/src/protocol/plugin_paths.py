"""Glob matching for the local files a plugin declares in ``files``.

A manifest lists the files its pages may read (``plugin-data-read``) as globs
such as ``~/**/.vicoa/dashboard.local.json``. The daemon checks every requested
path against them here; the renderer mirrors the same algorithm in TypeScript
(``apps/web/lib/plugins``) to decide up front whether to ask at all, so keep the
two in step and keep this simple.

The algorithm:

1. ``pattern`` must start with ``~/`` or ``/``. A leading ``~`` is replaced by
   ``home`` (with any trailing ``/`` removed from ``home``). Anything else never
   matches.
2. Both the expanded pattern and ``path`` are split on ``/``. The empty string
   before the leading ``/`` is a segment too, so ``/a/b`` is ``["", "a", "b"]``.
3. Segments are matched left to right over the whole path (no partial
   matches):

   - a pattern segment that is exactly ``**`` matches zero or more whole path
     segments;
   - any other pattern segment matches exactly one path segment, where ``*``
     matches any run of characters (including none) and ``?`` matches exactly
     one character. Every other character, ``[`` and ``]`` included, matches
     itself. ``*`` matches a leading ``.`` too (no dot-file special case).

Matching is case-sensitive. ``path`` is expected to be absolute and normalized
(no ``.``/``..``/empty segments); callers normalize before matching.
"""

from __future__ import annotations


def _segment_matches(segment: str, pattern: str) -> bool:
    """Whether one path segment matches one pattern segment (``*`` and ``?``).

    The usual greedy wildcard walk with a single backtrack point: linear-ish,
    and unlike a regex it cannot blow up on patterns like ``*a*a*a*a*b``.
    """
    s = p = 0
    star = -1
    mark = 0
    while s < len(segment):
        if (
            p < len(pattern)
            and pattern[p] != "*"
            and (pattern[p] == "?" or pattern[p] == segment[s])
        ):
            s += 1
            p += 1
        elif p < len(pattern) and pattern[p] == "*":
            star = p
            mark = s
            p += 1
        elif star != -1:
            p = star + 1
            mark += 1
            s = mark
        else:
            return False
    while p < len(pattern) and pattern[p] == "*":
        p += 1
    return p == len(pattern)


def expand_glob(pattern: str, home: str) -> str | None:
    """``pattern`` with a leading ``~`` replaced by ``home``; ``None`` if it is
    neither ``~/``- nor ``/``-anchored."""
    if pattern.startswith("~/"):
        return home.rstrip("/") + pattern[1:]
    if pattern.startswith("/"):
        return pattern
    return None


def path_matches_glob(path: str, pattern: str, home: str) -> bool:
    """Whether the absolute, normalized ``path`` matches ``pattern``.

    See the module docstring for the exact rules.
    """
    expanded = expand_glob(pattern, home)
    if expanded is None:
        return False
    pat = expanded.split("/")
    segs = path.split("/")
    n, m = len(pat), len(segs)
    # rest[j] is True when pat[i:] matches segs[j:], computed for i from the end.
    rest = [False] * m + [True]
    for i in range(n - 1, -1, -1):
        cur = [False] * (m + 1)
        if pat[i] == "**":
            cur[m] = rest[m]
            for j in range(m - 1, -1, -1):
                cur[j] = rest[j] or cur[j + 1]
        else:
            for j in range(m - 1, -1, -1):
                cur[j] = rest[j + 1] and _segment_matches(segs[j], pat[i])
        rest = cur
    return rest[0]


def path_matches_any(path: str, patterns: list[str], home: str) -> bool:
    return any(path_matches_glob(path, pattern, home) for pattern in patterns)
