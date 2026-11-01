"""The daemon's side of naming a new worktree from its prompt.

`AutoNameInbox` hands the server's `worktree-name` frame from the receive loop
to the spawn waiting for it; `branch_slug` / `session_title` make whatever the
model wrote safe to use as a branch + folder name and a one-line title.
"""

from __future__ import annotations

import threading

import pytest

from vicoa.rpc.worktree_auto_name import (
    AutoNameInbox,
    AutoNames,
    branch_slug,
    session_title,
)


@pytest.mark.parametrize(
    ("raw", "slug"),
    [
        ("fix-safari-logout", "fix-safari-logout"),
        ("Fix Safari Logout", "fix-safari-logout"),
        ("bug/fix-drag-sort", "bug-fix-drag-sort"),
        ("  review_pr_212  ", "review-pr-212"),
        (
            "auto-generate-worktree-branch-name-now",
            "auto-generate-worktree-branch-name",
        ),
        ("修复 drag sort", "drag-sort"),
    ],
)
def test_branch_slug_makes_a_git_and_folder_safe_kebab_name(raw: str, slug: str):
    assert branch_slug(raw) == slug


@pytest.mark.parametrize("raw", [None, 42, "", "---", "修复拖拽", "212"])
def test_branch_slug_rejects_nothing_usable(raw: object):
    assert branch_slug(raw) is None


def test_branch_slug_stays_within_the_length_cap():
    slug = branch_slug("supercalifragilistic expialidocious antidisestablishment x")
    assert slug is not None and len(slug) <= 48


def test_session_title_is_one_trimmed_line():
    assert session_title("  修复首页\n拖拽排序  ") == "修复首页 拖拽排序"
    assert session_title("   ") is None
    assert session_title(None) is None


def test_a_delivered_frame_is_cleaned_and_claimed_once():
    inbox = AutoNameInbox()
    inbox.deliver({"token": "t1", "branch": "Fix Login", "title": " Fix login "})

    assert inbox.wait("t1", timeout=0) == AutoNames(
        branch="fix-login", title="Fix login"
    )
    assert inbox.wait("t1", timeout=0) is None


def test_a_failed_naming_frame_still_ends_the_wait():
    inbox = AutoNameInbox()
    inbox.deliver({"token": "t1"})

    assert inbox.wait("t1", timeout=5) == AutoNames(branch=None, title=None)


def test_wait_times_out_without_a_frame():
    assert AutoNameInbox().wait("missing", timeout=0.01) is None


def test_wait_wakes_when_the_frame_arrives_later():
    inbox = AutoNameInbox()
    timer = threading.Timer(
        0.05, inbox.deliver, args=({"token": "t1", "branch": "x-y"},)
    )
    timer.start()
    try:
        assert inbox.wait("t1", timeout=5) == AutoNames(branch="x-y", title=None)
    finally:
        timer.cancel()


def test_unclaimed_frames_expire():
    now = [0.0]
    inbox = AutoNameInbox(clock=lambda: now[0])
    inbox.deliver({"token": "old", "branch": "a-b"})
    now[0] = 61.0
    inbox.deliver({"token": "new", "branch": "c-d"})

    assert inbox.wait("old", timeout=0) is None
    assert inbox.wait("new", timeout=0) == AutoNames(branch="c-d", title=None)


def test_frames_without_a_token_are_ignored():
    inbox = AutoNameInbox()
    inbox.deliver({"branch": "a-b"})
    inbox.deliver({"token": "", "branch": "a-b"})

    assert inbox.wait("", timeout=0) is None
