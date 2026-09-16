"""GitHub pull-request state for the sidebar's per-branch git icon.

One `gh pr list` per *repository* — never one call per PR or per session. The
result is keyed by head branch so the caller joins it locally against the
worktree list it already holds. That batching is the whole reason this can
ignore GitHub's rate limit: the quota is per *account*, shared with the `gh`
calls the agent itself runs inside every live session, so a per-PR poll would
starve the actual work long before it ran out of quota on its own.

Nothing here is persisted. A daemon that is offline renders no icon rather than
a stale one, which is why there is no cache to invalidate and no "as of" caveat
to show.

`gh` is used rather than a token of our own: it is already authenticated on any
machine where the user pushes code, it handles GitHub Enterprise hosts for free,
and it means Vicoa never stores a GitHub credential. `gh pr list` needs only the
`repo` scope, which every `gh auth login` grants — so there is no scope
diagnostic to surface either.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

# `gh` occasionally hangs on a stalled network rather than failing: this RPC is
# called on window focus, so a hung call would wedge the sidebar's git view.
_GH_TIMEOUT_SECONDS = 20

# The most recently updated PRs across all states. A branch whose PR merged
# long enough ago to fall off this list no longer has a worktree to label.
_GH_PR_LIMIT = 100

# Fetched in one shot. `headRefName` is the join key; `statusCheckRollup` is
# collapsed to a single word below rather than shipped as its raw check list.
_GH_PR_FIELDS = "number,title,state,headRefName,url,isDraft,mergedAt,statusCheckRollup"

# Any of these means the check suite has a definite red. ACTION_REQUIRED counts:
# it blocks the merge exactly like a failure does.
_CHECK_FAILURE_CONCLUSIONS = {
    "FAILURE",
    "TIMED_OUT",
    "ACTION_REQUIRED",
    "STARTUP_FAILURE",
}
_CHECK_FAILURE_STATES = {"FAILURE", "ERROR"}


def _gh(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a fixed `gh` command in `repo`.

    Every argument is supplied by this module — the RPC surface takes only a
    `cwd`. `gh` runs with the user's full GitHub credential, so an RPC that
    forwarded caller-supplied argv would hand any client the ability to delete
    their repositories.
    """
    env = dict(os.environ)
    # A daemon has no terminal: without these `gh`/git can block forever on an
    # auth or update prompt instead of returning an error we can classify.
    env["GH_NO_UPDATE_NOTIFIER"] = "1"
    env["GH_PROMPT_DISABLED"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["gh", *args],
        cwd=str(repo),
        capture_output=True,
        check=False,
        text=True,
        env=env,
        timeout=_GH_TIMEOUT_SECONDS,
    )


def _is_git_repo(abs_dir: Path) -> bool:
    proc = subprocess.run(
        [
            "git",
            "--no-optional-locks",
            "-C",
            str(abs_dir),
            "rev-parse",
            "--is-inside-work-tree",
        ],
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0 and proc.stdout.strip() == b"true"


def _classify_gh_error(stderr: str) -> str:
    """Map `gh` stderr onto the error codes the client can act on.

    The distinction that matters to the UI is *whose problem it is*. An
    unauthenticated or GitHub-less repo is a permanent "this user does not use
    this feature" — hide it silently. A rate limit or outage is transient and
    also not the user's fault, so it likewise must not nag; it is kept separate
    only so it is legible in logs.
    """
    lowered = stderr.lower()
    if "gh auth login" in lowered or "not logged in" in lowered:
        return "gh_unauthenticated"
    if "none of the git remotes" in lowered or "no git remotes found" in lowered:
        return "no_remote"
    if "could not resolve to a repository" in lowered or "not found" in lowered:
        return "no_remote"
    if "rate limit" in lowered or "was submitted too quickly" in lowered:
        return "gh_unavailable"
    return "gh_unavailable"


def _rollup_checks(rollup: Any) -> str:
    """Collapse `statusCheckRollup` into `pass` / `fail` / `pending` / `none`.

    Done daemon-side so a PR with fifty check runs costs the client one word
    instead of fifty objects it would only reduce to the same word anyway.
    """
    if not isinstance(rollup, list) or not rollup:
        return "none"

    pending = False
    for entry in rollup:
        if not isinstance(entry, dict):
            continue
        # CheckRun: in flight until `status` reaches COMPLETED, then judged on
        # `conclusion`. StatusContext (the legacy commit-status API): a single
        # `state` that is its own verdict.
        status = str(entry.get("status") or "").upper()
        conclusion = str(entry.get("conclusion") or "").upper()
        state = str(entry.get("state") or "").upper()

        if conclusion in _CHECK_FAILURE_CONCLUSIONS or state in _CHECK_FAILURE_STATES:
            return "fail"
        if state in ("PENDING", "EXPECTED"):
            pending = True
        elif status and status != "COMPLETED":
            pending = True
        elif not status and not state and not conclusion:
            pending = True

    return "pending" if pending else "pass"


def _derive_state(raw_state: str, is_draft: bool) -> str:
    """`open` / `draft` / `merged` / `closed`.

    `gh` reports draft as a flag orthogonal to OPEN, but for the icon it is a
    distinct state — a draft PR is not yet a claim that the work is ready.
    """
    state = (raw_state or "").upper()
    if state == "MERGED":
        return "merged"
    if state == "CLOSED":
        return "closed"
    return "draft" if is_draft else "open"


def github_pr_list(cwd: str) -> dict[str, Any]:
    """PR state for every branch of the repo containing `cwd`, keyed by branch.

    Returns `{"prs": {branch: {number, title, state, url, checks}}}` where
    `state` is `open|draft|merged|closed` and `checks` is
    `pass|fail|pending|none`.

    On failure returns `{"error": code}` with one of `not_a_repo`, `gh_missing`,
    `gh_unauthenticated`, `no_remote`, `gh_unavailable`. Every one of them means
    the client hides the icon decoration entirely — none is worth interrupting
    the user over, since not using GitHub is a perfectly ordinary state.

    When a branch has several PRs (a reopened branch, or a merged PR followed by
    a new one) the most recently updated wins: `gh pr list` returns newest-first
    and the first write per branch is kept.
    """
    abs_dir = Path(os.path.expanduser(cwd)).resolve()
    if not _is_git_repo(abs_dir):
        return {"error": "not_a_repo"}

    try:
        proc = _gh(
            abs_dir,
            "pr",
            "list",
            "--state",
            "all",
            "--limit",
            str(_GH_PR_LIMIT),
            "--json",
            _GH_PR_FIELDS,
        )
    except FileNotFoundError:
        # `gh` is not installed. Expected on plenty of machines; not an error
        # the user should ever see.
        return {"error": "gh_missing"}
    except subprocess.TimeoutExpired:
        return {"error": "gh_unavailable"}

    if proc.returncode != 0:
        return {"error": _classify_gh_error(proc.stderr or "")}

    try:
        records = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return {"error": "gh_unavailable"}
    if not isinstance(records, list):
        return {"error": "gh_unavailable"}

    prs: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        branch = record.get("headRefName")
        number = record.get("number")
        if not isinstance(branch, str) or not branch or not isinstance(number, int):
            continue
        # Newest-first ordering makes the first entry per branch the live one.
        if branch in prs:
            continue
        prs[branch] = {
            "number": number,
            "title": str(record.get("title") or ""),
            "state": _derive_state(
                str(record.get("state") or ""), bool(record.get("isDraft"))
            ),
            "url": str(record.get("url") or ""),
            "checks": _rollup_checks(record.get("statusCheckRollup")),
        }

    return {"prs": prs}
