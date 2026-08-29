"""Confinement table for `vicoa.rpc.paths.resolve_inside_project`.

The helper rejects any path that escapes the project root via `..`, absolute
paths, or symlinks pointing outside. Grown one cycle at a time to match the
TDD discipline in `~/.claude/skills/tdd/SKILL.md`. Covers
`plans/todos/vicoa-app-files-tab.md` §Phase B `paths.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vicoa.rpc.paths import OutsideProject, resolve_inside_project


def test_simple_subdir_resolves_under_root(tmp_path: Path):
    (tmp_path / "subdir").mkdir()
    result = resolve_inside_project(tmp_path, "subdir")
    assert result == (tmp_path / "subdir").resolve()


def test_empty_rel_returns_project_root(tmp_path: Path):
    result = resolve_inside_project(tmp_path, "")
    assert result == tmp_path.resolve()


def test_dotdot_traversal_rejected(tmp_path: Path):
    with pytest.raises(OutsideProject):
        resolve_inside_project(tmp_path, "../escape")


def test_absolute_path_rejected(tmp_path: Path):
    # `Path("/foo") / "/etc/passwd"` discards "/foo" — the absolute input wins.
    # Confinement must catch that the resolved target sits outside the root.
    with pytest.raises(OutsideProject):
        resolve_inside_project(tmp_path, "/etc/passwd")


def test_symlink_pointing_inside_is_followed(tmp_path: Path):
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    result = resolve_inside_project(tmp_path, "link")
    assert result == (tmp_path / "real").resolve()


def test_symlink_pointing_outside_is_rejected(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}_sibling"
    outside.mkdir()
    try:
        (tmp_path / "escape").symlink_to(outside)
        with pytest.raises(OutsideProject):
            resolve_inside_project(tmp_path, "escape")
    finally:
        outside.rmdir()


def test_prefix_overlap_sibling_rejected(tmp_path: Path):
    # Naive `startswith(str(root))` without the os.sep boundary lets a sibling
    # whose name begins with the root's name slip through. Pin the boundary.
    root = tmp_path / "proj"
    root.mkdir()
    evil = tmp_path / "proj-evil"
    evil.mkdir()
    (evil / "secret").write_text("nope")
    (root / "link").symlink_to(evil / "secret")
    with pytest.raises(OutsideProject):
        resolve_inside_project(root, "link")
