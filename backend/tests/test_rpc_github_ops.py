"""Daemon-side GitHub PR lookup — rollup collapsing, state derivation, errors.

`gh` is stubbed rather than invoked: these tests pin the translation from its
JSON into the shape the sidebar consumes, which is where the real complexity is.
The one thing never stubbed is the argv, because "the RPC takes only a cwd" is a
security property, not a style choice.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from vicoa.rpc import github_ops


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """An initialized git repo — enough for the `_is_git_repo` guard."""
    path = tmp_path / "my-app"
    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    return path


def _stub_gh(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stdout: str = "[]",
    stderr: str = "",
    returncode: int = 0,
    raises: BaseException | None = None,
) -> list[list[str]]:
    """Replace the `gh` subprocess, returning the argv list it was called with.

    Only `gh` is intercepted — the `git rev-parse` guard is left to run for real
    against the temp repo, so these tests still exercise the not-a-repo path
    rather than trusting a stub to model it.
    """
    calls: list[list[str]] = []
    real_run = subprocess.run

    def fake_run(*args: Any, **kwargs: Any) -> Any:
        argv = list(args[0])
        if argv[0] != "gh":
            return real_run(*args, **kwargs)
        calls.append(argv)
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(
            argv, returncode, stdout=stdout, stderr=stderr
        )

    monkeypatch.setattr(github_ops.subprocess, "run", fake_run)
    return calls


def _pr(**overrides: Any) -> dict[str, Any]:
    base = {
        "number": 7,
        "title": "Add a thing",
        "state": "OPEN",
        "headRefName": "feat/thing",
        "url": "https://github.com/o/r/pull/7",
        "isDraft": False,
        "mergedAt": None,
        "statusCheckRollup": [],
    }
    base.update(overrides)
    return base


def test_rejects_non_git_directory(tmp_path: Path) -> None:
    assert github_ops.github_pr_list(str(tmp_path)) == {"error": "not_a_repo"}


def test_argv_is_fixed_and_carries_no_caller_input(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cwd must never reach `gh`'s argv.

    `gh` runs with the user's full GitHub credential. If any part of the RPC's
    input became an argument, a client could turn this into arbitrary `gh`.
    """
    calls = _stub_gh(monkeypatch)
    github_ops.github_pr_list(str(repo))

    assert calls == [
        [
            "gh",
            "pr",
            "list",
            "--state",
            "all",
            "--limit",
            str(github_ops._GH_PR_LIMIT),
            "--json",
            github_ops._GH_PR_FIELDS,
        ]
    ]
    assert str(repo) not in " ".join(calls[0])


def test_keys_by_head_branch(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_gh(monkeypatch, stdout=json.dumps([_pr()]))
    result = github_ops.github_pr_list(str(repo))
    assert result == {
        "prs": {
            "feat/thing": {
                "number": 7,
                "title": "Add a thing",
                "state": "open",
                "url": "https://github.com/o/r/pull/7",
                "checks": "none",
            }
        }
    }


@pytest.mark.parametrize(
    ("state", "is_draft", "expected"),
    [
        ("OPEN", False, "open"),
        ("OPEN", True, "draft"),
        ("MERGED", False, "merged"),
        ("CLOSED", False, "closed"),
        # A draft that was closed is closed: the terminal state wins over the
        # draft flag, which gh leaves set.
        ("CLOSED", True, "closed"),
    ],
)
def test_derives_state(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    is_draft: bool,
    expected: str,
) -> None:
    _stub_gh(monkeypatch, stdout=json.dumps([_pr(state=state, isDraft=is_draft)]))
    result = github_ops.github_pr_list(str(repo))
    assert result["prs"]["feat/thing"]["state"] == expected


@pytest.mark.parametrize(
    ("rollup", "expected"),
    [
        ([], "none"),
        (None, "none"),
        # All green.
        ([{"status": "COMPLETED", "conclusion": "SUCCESS"}], "pass"),
        # A skipped or neutral run is not a failure.
        (
            [
                {"status": "COMPLETED", "conclusion": "SUCCESS"},
                {"status": "COMPLETED", "conclusion": "SKIPPED"},
                {"status": "COMPLETED", "conclusion": "NEUTRAL"},
            ],
            "pass",
        ),
        # Still running.
        (
            [
                {"status": "COMPLETED", "conclusion": "SUCCESS"},
                {"status": "IN_PROGRESS", "conclusion": None},
            ],
            "pending",
        ),
        ([{"status": "QUEUED", "conclusion": None}], "pending"),
        # A definite red beats a pending sibling: the suite cannot recover.
        (
            [
                {"status": "IN_PROGRESS", "conclusion": None},
                {"status": "COMPLETED", "conclusion": "FAILURE"},
            ],
            "fail",
        ),
        ([{"status": "COMPLETED", "conclusion": "TIMED_OUT"}], "fail"),
        # ACTION_REQUIRED blocks the merge exactly as a failure does.
        ([{"status": "COMPLETED", "conclusion": "ACTION_REQUIRED"}], "fail"),
        # Legacy commit statuses carry `state` instead of status/conclusion.
        ([{"__typename": "StatusContext", "state": "SUCCESS"}], "pass"),
        ([{"__typename": "StatusContext", "state": "PENDING"}], "pending"),
        ([{"__typename": "StatusContext", "state": "ERROR"}], "fail"),
        ([{"__typename": "StatusContext", "state": "FAILURE"}], "fail"),
    ],
)
def test_collapses_check_rollup(
    repo: Path, monkeypatch: pytest.MonkeyPatch, rollup: Any, expected: str
) -> None:
    _stub_gh(monkeypatch, stdout=json.dumps([_pr(statusCheckRollup=rollup)]))
    result = github_ops.github_pr_list(str(repo))
    assert result["prs"]["feat/thing"]["checks"] == expected


def test_first_pr_per_branch_wins(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A reopened branch keeps its newest PR.

    `gh pr list` returns newest-first, so the stale merged PR further down the
    list must not overwrite the live one.
    """
    _stub_gh(
        monkeypatch,
        stdout=json.dumps(
            [
                _pr(number=9, state="OPEN"),
                _pr(number=4, state="MERGED"),
            ]
        ),
    )
    result = github_ops.github_pr_list(str(repo))
    assert result["prs"]["feat/thing"]["number"] == 9
    assert result["prs"]["feat/thing"]["state"] == "open"


def test_skips_malformed_records(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One unusable record must not cost the whole repo its decoration."""
    _stub_gh(
        monkeypatch,
        stdout=json.dumps(
            ["not-an-object", _pr(headRefName=""), _pr(number=None), _pr()]
        ),
    )
    result = github_ops.github_pr_list(str(repo))
    assert list(result["prs"]) == ["feat/thing"]


def test_missing_gh_binary(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_gh(monkeypatch, raises=FileNotFoundError())
    assert github_ops.github_pr_list(str(repo)) == {"error": "gh_missing"}


def test_timeout(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_gh(monkeypatch, raises=subprocess.TimeoutExpired(cmd="gh", timeout=20))
    assert github_ops.github_pr_list(str(repo)) == {"error": "gh_unavailable"}


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        (
            "To get started with GitHub CLI, please run: gh auth login",
            "gh_unauthenticated",
        ),
        ("You are not logged into any GitHub hosts.", "gh_unauthenticated"),
        (
            "none of the git remotes configured for this repository point to a "
            "known GitHub host",
            "no_remote",
        ),
        ("HTTP 403: API rate limit exceeded", "gh_unavailable"),
        ("something nobody predicted", "gh_unavailable"),
    ],
)
def test_classifies_gh_failures(
    repo: Path, monkeypatch: pytest.MonkeyPatch, stderr: str, expected: str
) -> None:
    _stub_gh(monkeypatch, returncode=1, stderr=stderr)
    assert github_ops.github_pr_list(str(repo)) == {"error": expected}


def test_unparseable_output(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_gh(monkeypatch, stdout="not json at all")
    assert github_ops.github_pr_list(str(repo)) == {"error": "gh_unavailable"}
