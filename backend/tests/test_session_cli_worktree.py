"""Unit tests for ``vicoa session update --worktree``.

The PATCH itself is covered in ``test_session_folder_patch.py``; what is
only reachable here is how the CLI turns a branch name into the fields it
sends — which checkout matches, the subfolder carried across, the "back to
main" case — and the guards that stop it (other machine, unknown branch,
a worktree whose directory is gone).
"""

from __future__ import annotations

import os
import types
from pathlib import Path

import pytest

from vicoa.commands import instance as I


def _args(**over):
    base = {
        "session_id": "s-1",
        "json": False,
        "api_key": "k",
        "base_url": None,
        "title": None,
        "task": None,
        "unlink_task": False,
        "worktree": None,
    }
    base.update(over)
    return types.SimpleNamespace(**base)


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Pin HOME so ``get_project_path`` collapses tmp paths to ``~/…``."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    return h


@pytest.fixture
def checkouts(home: Path) -> dict:
    """A main checkout plus two linked worktrees, on disk (no git needed —
    the resolver only looks at the listing and at directories)."""
    main = home / "src" / "app"
    (main / "apps" / "web").mkdir(parents=True)
    wt_root = home / "vicoa" / "workspaces" / "app-worktrees"
    feat = wt_root / "feat-x" / "app"
    (feat / "apps" / "web").mkdir(parents=True)
    bare = wt_root / "bare" / "app"
    bare.mkdir(parents=True)  # no apps/web here
    listing = {
        "main_path": str(main),
        "main_display_path": "~/src/app",
        "main_branch": "main",
        "worktrees": [
            {
                "path": str(feat),
                "display_path": "~/vicoa/workspaces/app-worktrees/feat-x/app",
                "branch": "feat-x",
                "head": "abc",
                "managed": True,
                "prunable": False,
            },
            {
                "path": str(bare),
                "display_path": "~/vicoa/workspaces/app-worktrees/bare/app",
                "branch": "",  # detached: goes by its directory name
                "head": "def",
                "managed": True,
                "prunable": False,
            },
        ],
    }
    return {"main": main, "feat": feat, "bare": bare, "listing": listing}


class TestWorktreeMove:
    def test_main_session_moves_into_the_worktree(self, checkouts):
        fields = I._worktree_move(
            {"project": "~/src/app"}, "feat-x", checkouts["listing"]
        )
        assert fields == {
            "project": "~/vicoa/workspaces/app-worktrees/feat-x/app",
            "worktree_name": "feat-x",
            "repo_root": "~/src/app",
        }

    def test_worktree_session_moves_back_to_main_with_null_name(self, checkouts):
        fields = I._worktree_move(
            {"project": "~/vicoa/workspaces/app-worktrees/feat-x/app"},
            "main",
            checkouts["listing"],
        )
        assert fields["project"] == "~/src/app"
        assert fields["worktree_name"] is None
        assert fields["repo_root"] == "~/src/app"

    def test_subfolder_is_carried_across(self, checkouts):
        fields = I._worktree_move(
            {"project": "~/src/app/apps/web"}, "feat-x", checkouts["listing"]
        )
        assert (
            fields["project"] == "~/vicoa/workspaces/app-worktrees/feat-x/app/apps/web"
        )

    def test_subfolder_missing_from_target_is_an_error(self, checkouts):
        with pytest.raises(ValueError, match="does not exist"):
            I._worktree_move(
                {"project": "~/src/app/apps/web"}, "app", checkouts["listing"]
            )

    def test_detached_worktree_goes_by_its_directory_name(self, checkouts):
        fields = I._worktree_move({"project": "~/src/app"}, "app", checkouts["listing"])
        assert fields["project"] == "~/vicoa/workspaces/app-worktrees/bare/app"
        assert fields["worktree_name"] == "app"

    def test_cwd_outside_every_checkout_lands_on_the_target_root(self, checkouts):
        """The session's own worktree was deleted: nothing to carry across."""
        fields = I._worktree_move(
            {"project": "~/vicoa/workspaces/app-worktrees/gone/app/apps/web"},
            "feat-x",
            checkouts["listing"],
        )
        assert fields["project"] == "~/vicoa/workspaces/app-worktrees/feat-x/app"

    def test_unknown_branch_lists_the_candidates(self, checkouts):
        with pytest.raises(ValueError) as exc:
            I._worktree_move({"project": "~/src/app"}, "nope", checkouts["listing"])
        assert "Worktrees: app, feat-x" in str(exc.value)
        assert "main checkout: main" in str(exc.value)

    def test_prunable_worktree_is_refused(self, checkouts):
        listing = checkouts["listing"]
        listing["worktrees"][0]["prunable"] = True
        with pytest.raises(ValueError, match="directory is gone"):
            I._worktree_move({"project": "~/src/app"}, "feat-x", listing)

    def test_branch_checked_out_twice_is_ambiguous(self, checkouts):
        listing = checkouts["listing"]
        listing["worktrees"][1]["branch"] = "feat-x"
        with pytest.raises(ValueError, match="2 places"):
            I._worktree_move({"project": "~/src/app"}, "feat-x", listing)


class TestResolveWorktreeMove:
    def _wire(self, monkeypatch, detail: dict, listing: dict, local_machine=None):
        calls: list[tuple] = []

        def fake_request(args, api_key, method, endpoint, *, params=None, json=None):
            calls.append((method, endpoint, json))
            return detail

        monkeypatch.setattr(I, "request", fake_request)
        monkeypatch.setattr(I, "_local_machine_id", lambda args: local_machine)
        monkeypatch.setattr(
            "vicoa.rpc.worktree_ops.list_worktrees", lambda cwd: listing
        )
        return calls

    def test_refuses_a_session_on_another_machine(self, monkeypatch, checkouts):
        self._wire(
            monkeypatch,
            {"project": "~/src/app", "machine_id": "m-remote"},
            checkouts["listing"],
            local_machine="m-local",
        )
        with pytest.raises(ValueError, match="another machine"):
            I._resolve_worktree_move(_args(), "k", "s-1", "feat-x")

    def test_finds_the_repo_from_the_stored_repo_root(self, monkeypatch, checkouts):
        seen: list[str] = []

        def fake_list(cwd: str) -> dict:
            seen.append(cwd)
            return checkouts["listing"]

        self._wire(
            monkeypatch,
            {
                # a worktree session: its cwd is outside the repo, repo_root
                # is what points git at the right repo
                "project": "~/vicoa/workspaces/app-worktrees/feat-x/app",
                "machine_id": "m-1",
                "instance_metadata": {
                    "worktree_name": "feat-x",
                    "repo_root": "~/src/app",
                },
            },
            checkouts["listing"],
            local_machine="m-1",
        )
        monkeypatch.setattr("vicoa.rpc.worktree_ops.list_worktrees", fake_list)
        fields = I._resolve_worktree_move(_args(), "k", "s-1", "main")
        assert seen == [os.path.expanduser("~/src/app")]
        assert fields["worktree_name"] is None

    def test_missing_folder_is_reported(self, monkeypatch, checkouts):
        self._wire(
            monkeypatch,
            {"project": "~/elsewhere/app", "machine_id": "m-1"},
            checkouts["listing"],
            local_machine="m-1",
        )
        with pytest.raises(ValueError, match="does not exist on this machine"):
            I._resolve_worktree_move(_args(), "k", "s-1", "feat-x")

    def test_non_git_folder_is_reported(self, monkeypatch, checkouts, home):
        (home / "plain").mkdir()
        self._wire(
            monkeypatch,
            {"project": "~/plain", "machine_id": "m-1"},
            {"error": "not_a_repo"},
            local_machine="m-1",
        )
        with pytest.raises(ValueError, match="not a git checkout"):
            I._resolve_worktree_move(_args(), "k", "s-1", "feat-x")


class TestCmdUpdate:
    def test_worktree_alone_is_enough_and_patches_the_three_fields(
        self, monkeypatch, checkouts, capsys
    ):
        sent: list[tuple] = []

        def fake_request(args, api_key, method, endpoint, *, params=None, json=None):
            sent.append((method, endpoint, json))
            if method == "GET":
                return {"id": "s-1", "project": "~/src/app", "machine_id": "m-1"}
            # A current server echoes the row it wrote.
            return {"agent_instance_id": "s-1", "project": json["project"]}

        monkeypatch.setattr(I, "request", fake_request)
        monkeypatch.setattr(I, "_require_session_id", lambda ref: "s-1")
        monkeypatch.setattr(I, "_local_machine_id", lambda args: "m-1")
        monkeypatch.setattr(
            "vicoa.rpc.worktree_ops.list_worktrees", lambda cwd: checkouts["listing"]
        )

        assert I._cmd_update(_args(worktree="feat-x"), "k") == 0
        method, endpoint, body = sent[-1]
        assert (method, endpoint) == ("PATCH", "/api/v1/agent-instances/s-1")
        assert body == {
            "project": "~/vicoa/workspaces/app-worktrees/feat-x/app",
            "worktree_name": "feat-x",
            "repo_root": "~/src/app",
        }
        assert "moved to worktree feat-x" in capsys.readouterr().out

    def test_server_that_ignored_the_move_is_reported(
        self, monkeypatch, checkouts, capsys
    ):
        """An older server drops unknown PATCH keys and answers 200 with the
        row as it was; the CLI must not call that a move."""

        def fake_request(args, api_key, method, endpoint, *, params=None, json=None):
            if method == "GET":
                return {"id": "s-1", "project": "~/src/app", "machine_id": "m-1"}
            return {"agent_instance_id": "s-1", "project": "~/src/app"}

        monkeypatch.setattr(I, "request", fake_request)
        monkeypatch.setattr(I, "_require_session_id", lambda ref: "s-1")
        monkeypatch.setattr(I, "_local_machine_id", lambda args: "m-1")
        monkeypatch.setattr(
            "vicoa.rpc.worktree_ops.list_worktrees", lambda cwd: checkouts["listing"]
        )

        assert I._cmd_update(_args(worktree="feat-x"), "k") == 1
        out = capsys.readouterr()
        assert "did not apply the move" in out.err
        assert "moved" not in out.out

    def test_resolver_error_is_printed_and_nothing_is_patched(
        self, monkeypatch, checkouts, capsys
    ):
        sent: list[str] = []

        def fake_request(args, api_key, method, endpoint, *, params=None, json=None):
            sent.append(method)
            return {"id": "s-1", "project": "~/src/app", "machine_id": "m-1"}

        monkeypatch.setattr(I, "request", fake_request)
        monkeypatch.setattr(I, "_require_session_id", lambda ref: "s-1")
        monkeypatch.setattr(I, "_local_machine_id", lambda args: "m-1")
        monkeypatch.setattr(
            "vicoa.rpc.worktree_ops.list_worktrees", lambda cwd: checkouts["listing"]
        )

        assert I._cmd_update(_args(worktree="nope"), "k") == 1
        assert "PATCH" not in sent
        assert "No checkout" in capsys.readouterr().err

    def test_nothing_to_update_mentions_worktree(self, capsys):
        assert I._cmd_update(_args(), "k") == 2
        assert "--worktree" in capsys.readouterr().err
