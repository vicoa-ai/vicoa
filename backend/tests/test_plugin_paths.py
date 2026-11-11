"""Tests for the plugin ``files`` glob matcher (protocol.plugin_paths).

The renderer mirrors this algorithm in TypeScript, so these cases double as its
specification.
"""

import pytest

from protocol.plugin_paths import expand_glob, path_matches_any, path_matches_glob

HOME = "/h"


@pytest.mark.parametrize(
    "path, pattern, expected",
    [
        # ** = zero or more whole segments
        (
            "/h/projects/a/.vicoa/dashboard.local.json",
            "~/**/.vicoa/dashboard.local.json",
            True,
        ),
        ("/h/.vicoa/dashboard.local.json", "~/**/.vicoa/dashboard.local.json", True),
        (
            "/h/a/b/c/.vicoa/dashboard.local.json",
            "~/**/.vicoa/dashboard.local.json",
            True,
        ),
        ("/h/projects/a/.vicoa/x.json", "~/**/.vicoa/dashboard.local.json", False),
        (
            "/other/.vicoa/dashboard.local.json",
            "~/**/.vicoa/dashboard.local.json",
            False,
        ),
        ("/h/a/b", "~/**", True),
        ("/h", "~/**", True),
        ("/h/a/b/c.json", "/h/**/*.json", True),
        ("/h/c.json", "/h/**/*.json", True),
        ("/h/a/b/c.txt", "/h/**/*.json", False),
        ("/h/a/x/b", "/h/a/**/b/**", True),
        ("/h/a/b/b/c", "/h/**/b/c", True),
        # * stays inside one segment
        ("/data/a.json", "/data/*.json", True),
        ("/data/sub/a.json", "/data/*.json", False),
        ("/data/.json", "/data/*.json", True),
        ("/data/.hidden.json", "/data/*.json", True),  # no dot-file rule
        ("/data/a.json", "/data/*", True),
        ("/data", "/data/*", False),
        ("/data/a/b", "/*/a/*", True),
        ("/data/abc", "/data/a*c", True),
        ("/data/ac", "/data/a*c", True),
        ("/data/ab", "/data/a*c", False),
        ("/data/aXbYc", "/data/a*b*c", True),
        ("/data/a**b", "/data/a**b", True),  # ** inside a segment is just *
        ("/data/axyb", "/data/a**b", True),
        ("/data/a/b", "/data/a**b", False),
        # ? = exactly one character, never /
        ("/data/a1.json", "/data/a?.json", True),
        ("/data/a.json", "/data/a?.json", False),
        ("/data/a12.json", "/data/a?.json", False),
        ("/data/a/b", "/data/a?b", False),
        # literal characters, including [ ]
        ("/data/[a].json", "/data/[a].json", True),
        ("/data/a.json", "/data/[a].json", False),
        ("/data/axjson", "/data/a.json", False),
        # whole path, case-sensitive
        ("/data/a.json", "/data/A.json", False),
        ("/data/a.json/x", "/data/a.json", False),
        ("/x/data/a.json", "/data/a.json", False),
        ("/data/a.json", "/data/a.json", True),
        # anchoring
        ("/h/a.json", "~/a.json", True),
        ("/h/a.json", "a.json", False),
        ("/h/a.json", "~a.json", False),
        ("/h/a.json", "**/a.json", False),
    ],
)
def test_path_matches_glob(path, pattern, expected):
    assert path_matches_glob(path, pattern, HOME) is expected


def test_home_trailing_slash_and_root_home():
    assert path_matches_glob("/h/a", "~/a", "/h/")
    assert path_matches_glob("/a", "~/a", "/")


def test_expand_glob():
    assert expand_glob("~/a", "/h") == "/h/a"
    assert expand_glob("/a", "/h") == "/a"
    assert expand_glob("a", "/h") is None
    assert expand_glob("~", "/h") is None


def test_pathological_pattern_is_fast():
    # A regex translation would backtrack exponentially here.
    segment = "a" * 200
    pattern = "/" + "*a" * 40 + "b"
    assert path_matches_glob("/" + segment, pattern, HOME) is False
    deep = "/" + "/".join(["a"] * 200)
    assert path_matches_glob(deep, "/" + "/".join(["**"] * 50) + "/b", HOME) is False


def test_path_matches_any():
    globs = ["/data/*.json", "~/**/notes.md"]
    assert path_matches_any("/h/x/notes.md", globs, HOME)
    assert path_matches_any("/data/a.json", globs, HOME)
    assert not path_matches_any("/data/a.md", globs, HOME)
    assert not path_matches_any("/data/a.json", [], HOME)
