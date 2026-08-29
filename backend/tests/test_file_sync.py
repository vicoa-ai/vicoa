"""Tests for vicoa.file_sync — directory scanning and gitignore exclusion.

Covers:
- DEFAULT_EXCLUDE_PATTERNS exclusions (node_modules, .venv, __pycache__, etc.)
- Root .gitignore pattern loading
- Subdirectory .gitignore loading (e.g. ios/.gitignore with **/Pods/)
- Nested gitignore stacking
- get_newest_dir_mtime and cache round-trip
- get_excluded_dir_names helper
"""

from pathlib import Path

import pytest

from vicoa.file_sync import (
    get_cache_path,
    get_excluded_dir_names,
    get_newest_dir_mtime,
    load_sync_cache,
    save_sync_cache,
    scan_project_files,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_tree(base: Path, spec: dict) -> None:
    """Recursively create files/directories from a dict spec.

    Keys ending with '/' are directories; others are files.
    Values that are dicts recurse; string values become file content.
    """
    for name, content in spec.items():
        path = base / name
        if isinstance(content, dict):
            path.mkdir(parents=True, exist_ok=True)
            make_tree(path, content)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content if isinstance(content, str) else "")


def scan(root: Path, **kwargs) -> set:
    """Return scan_project_files results as a set for easy comparison."""
    return set(scan_project_files(str(root), **kwargs))


# ---------------------------------------------------------------------------
# get_excluded_dir_names
# ---------------------------------------------------------------------------


def test_excluded_dir_names_contains_common_dirs() -> None:
    dirs = get_excluded_dir_names()
    assert "node_modules" in dirs
    assert ".venv" in dirs
    assert "__pycache__" in dirs
    assert ".git" in dirs


def test_excluded_dir_names_no_glob_patterns() -> None:
    dirs = get_excluded_dir_names()
    for d in dirs:
        assert "*" not in d, f"Glob pattern leaked into dir names: {d}"


# ---------------------------------------------------------------------------
# DEFAULT_EXCLUDE_PATTERNS — directories pruned from scan
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "excluded_dir",
    [
        "node_modules",
        ".venv",
        "__pycache__",
        ".git",
        ".next",
        "dist",
        "build",
    ],
)
def test_default_excluded_dirs_not_in_results(
    excluded_dir: str, tmp_path: Path
) -> None:
    make_tree(
        tmp_path,
        {
            "src": {"main.py": ""},
            excluded_dir: {"secret.py": ""},
        },
    )
    results = scan(tmp_path)
    assert not any(excluded_dir in r for r in results), (
        f"Files from '{excluded_dir}/' should be excluded but got: "
        + str([r for r in results if excluded_dir in r])
    )


def test_normal_files_included(tmp_path: Path) -> None:
    make_tree(tmp_path, {"src": {"main.py": "", "utils.py": ""}})
    results = scan(tmp_path)
    assert "src/main.py" in results
    assert "src/utils.py" in results


# ---------------------------------------------------------------------------
# Root .gitignore exclusion
# ---------------------------------------------------------------------------


def test_root_gitignore_excludes_matching_files(tmp_path: Path) -> None:
    make_tree(
        tmp_path,
        {
            ".gitignore": "secrets.txt\n",
            "src": {"main.py": ""},
            "secrets.txt": "",
        },
    )
    results = scan(tmp_path)
    assert "secrets.txt" not in results
    assert "src/main.py" in results


def test_root_gitignore_excludes_directories(tmp_path: Path) -> None:
    make_tree(
        tmp_path,
        {
            ".gitignore": "vendor/\n",
            "src": {"main.py": ""},
            "vendor": {"lib.py": ""},
        },
    )
    results = scan(tmp_path)
    assert not any("vendor" in r for r in results)


def test_root_gitignore_glob_pattern(tmp_path: Path) -> None:
    make_tree(
        tmp_path,
        {
            ".gitignore": "*.log\n",
            "app.log": "",
            "src": {"debug.log": "", "main.py": ""},
        },
    )
    results = scan(tmp_path)
    assert "app.log" not in results
    assert "src/debug.log" not in results
    assert "src/main.py" in results


# ---------------------------------------------------------------------------
# ios/Pods — the reported bug: subdirectory .gitignore with **/Pods/
# ---------------------------------------------------------------------------


def test_pods_excluded_via_subdirectory_gitignore(tmp_path: Path) -> None:
    """ios/.gitignore with **/Pods/ must exclude ios/Pods/ from scan."""
    make_tree(
        tmp_path,
        {
            "lib": {"main.dart": ""},
            "ios": {
                ".gitignore": "**/Pods/\n",
                "Runner": {"AppDelegate.swift": ""},
                "Pods": {
                    "Headers": {"pod1.h": ""},
                    "Manifest.lock": "",
                },
            },
        },
    )
    results = scan(tmp_path)
    assert not any("Pods" in r for r in results), (
        "ios/Pods/ should be excluded by ios/.gitignore but found: "
        + str([r for r in results if "Pods" in r])
    )
    assert "ios/Runner/AppDelegate.swift" in results
    assert "lib/main.dart" in results


def test_pods_excluded_via_simple_pattern(tmp_path: Path) -> None:
    """ios/.gitignore with plain 'Pods/' should also exclude ios/Pods/."""
    make_tree(
        tmp_path,
        {
            "lib": {"main.dart": ""},
            "ios": {
                ".gitignore": "Pods/\n",
                "Pods": {"Manifest.lock": ""},
            },
        },
    )
    results = scan(tmp_path)
    assert not any("Pods" in r for r in results)


def test_pods_excluded_via_root_gitignore_doublestar(tmp_path: Path) -> None:
    """Root .gitignore with **/Pods/ should exclude ios/Pods/."""
    make_tree(
        tmp_path,
        {
            ".gitignore": "**/Pods/\n",
            "ios": {"Pods": {"Manifest.lock": ""}, "Runner": {"AppDelegate.swift": ""}},
        },
    )
    results = scan(tmp_path)
    assert not any("Pods" in r for r in results)
    assert "ios/Runner/AppDelegate.swift" in results


# ---------------------------------------------------------------------------
# Nested gitignore stacking
# ---------------------------------------------------------------------------


def test_nested_gitignore_does_not_affect_sibling_dirs(tmp_path: Path) -> None:
    """A .gitignore in 'a/' should not exclude files in 'b/'."""
    make_tree(
        tmp_path,
        {
            "a": {".gitignore": "secret.txt\n", "secret.txt": "", "public.txt": ""},
            "b": {"secret.txt": ""},
        },
    )
    results = scan(tmp_path)
    assert "a/secret.txt" not in results
    assert "a/public.txt" in results
    assert "b/secret.txt" in results


def test_multiple_gitignore_levels_stack(tmp_path: Path) -> None:
    """Files excluded by ancestor gitignore must still be excluded in descendants."""
    make_tree(
        tmp_path,
        {
            ".gitignore": "*.log\n",
            "src": {"app.log": "", "main.py": ""},
        },
    )
    results = scan(tmp_path)
    assert "src/app.log" not in results
    assert "src/main.py" in results


def test_respect_gitignore_false_skips_gitignore(tmp_path: Path) -> None:
    """When respect_gitignore=False, .gitignore patterns are not applied."""
    make_tree(
        tmp_path,
        {
            ".gitignore": "secret.txt\n",
            "secret.txt": "",
            "public.txt": "",
        },
    )
    results = scan(tmp_path, respect_gitignore=False)
    assert "secret.txt" in results


# ---------------------------------------------------------------------------
# Cache round-trip
# ---------------------------------------------------------------------------


def test_save_and_load_cache(tmp_path: Path) -> None:
    project = str(tmp_path)
    save_sync_cache(project, newest_dir_mtime=1234567890.0, file_count=42)
    cache = load_sync_cache(project)
    assert cache["newest_dir_mtime"] == 1234567890.0
    assert cache["file_count"] == 42
    assert "last_sync_timestamp" in cache
    assert "project_path" in cache


def test_load_cache_missing_returns_empty(tmp_path: Path) -> None:
    cache = load_sync_cache(str(tmp_path / "nonexistent_project"))
    assert cache == {}


def test_load_cache_corrupt_returns_empty(tmp_path: Path) -> None:
    project = str(tmp_path)
    cache_path = get_cache_path(project)
    cache_path.write_text("not valid json")
    cache = load_sync_cache(project)
    assert cache == {}


# ---------------------------------------------------------------------------
# get_newest_dir_mtime
# ---------------------------------------------------------------------------


def test_newest_dir_mtime_nonexistent_returns_zero() -> None:
    assert get_newest_dir_mtime("/does/not/exist/at/all") == 0.0


def test_newest_dir_mtime_returns_positive(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    mtime = get_newest_dir_mtime(str(tmp_path))
    assert mtime > 0.0


def test_newest_dir_mtime_excludes_default_patterns(tmp_path: Path) -> None:
    """Excluded dirs like node_modules are skipped during mtime scan."""
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "src").mkdir()
    # Should not raise; excluded dirs are skipped silently
    mtime = get_newest_dir_mtime(str(tmp_path))
    assert mtime > 0.0


# ---------------------------------------------------------------------------
# Folder entries in results
# ---------------------------------------------------------------------------


def test_folders_included_with_trailing_slash(tmp_path: Path) -> None:
    make_tree(tmp_path, {"src": {"components": {"Button.tsx": ""}}})
    results = scan(tmp_path)
    assert "src/" in results
    assert "src/components/" in results
    assert "src/components/Button.tsx" in results


def test_empty_project_returns_empty_list(tmp_path: Path) -> None:
    results = scan(tmp_path)
    assert results == set()


# ---------------------------------------------------------------------------
# additional_excludes
# ---------------------------------------------------------------------------


def test_additional_excludes_applied(tmp_path: Path) -> None:
    make_tree(tmp_path, {"generated": {"code.py": ""}, "src": {"main.py": ""}})
    results = scan(tmp_path, additional_excludes=["generated/"])
    assert not any("generated" in r for r in results)
    assert "src/main.py" in results
