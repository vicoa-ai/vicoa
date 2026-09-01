"""Daemon-local worktree trust — per-(repo, machine), path-keyed, persisted.

A committed ``vicoa.json`` is untrusted until the user approves it, so a cloned
repo can't auto-run shell on the first worktree spawn. Trust lives in the daemon
state file and is keyed by the source repo's canonical path.
"""

from __future__ import annotations

from pathlib import Path

from vicoa.rpc import worktree_trust as wt


def test_untrusted_by_default(tmp_path: Path) -> None:
    state = tmp_path / "daemon_state.json"
    assert wt.is_repo_trusted(str(tmp_path / "repo"), state_path=state) is False


def test_grant_then_trusted(tmp_path: Path) -> None:
    state = tmp_path / "daemon_state.json"
    repo = tmp_path / "repo"
    repo.mkdir()
    wt.grant_repo_trust(str(repo), state_path=state)
    assert wt.is_repo_trusted(str(repo), state_path=state) is True


def test_trust_is_path_scoped(tmp_path: Path) -> None:
    state = tmp_path / "daemon_state.json"
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    wt.grant_repo_trust(str(tmp_path / "a"), state_path=state)
    assert wt.is_repo_trusted(str(tmp_path / "a"), state_path=state) is True
    assert wt.is_repo_trusted(str(tmp_path / "b"), state_path=state) is False


def test_grant_canonicalizes_path(tmp_path: Path) -> None:
    state = tmp_path / "daemon_state.json"
    repo = tmp_path / "repo"
    repo.mkdir()
    wt.grant_repo_trust(str(repo), state_path=state)
    # A non-canonical spelling of the same path still reads as trusted.
    assert wt.is_repo_trusted(f"{repo}/", state_path=state) is True
    assert wt.is_repo_trusted(str(repo / "sub" / ".."), state_path=state) is True


def test_grant_preserves_other_state(tmp_path: Path) -> None:
    import json

    state = tmp_path / "daemon_state.json"
    state.write_text(json.dumps({"daemons": {"https://x": {"machine_id": "m1"}}}))
    wt.grant_repo_trust(str(tmp_path / "repo"), state_path=state)
    data = json.loads(state.read_text())
    # Trust is additive — the existing daemons section survives.
    assert data["daemons"] == {"https://x": {"machine_id": "m1"}}
    assert wt._TRUST_KEY in data


def test_empty_repo_is_never_trusted(tmp_path: Path) -> None:
    state = tmp_path / "daemon_state.json"
    assert wt.is_repo_trusted("", state_path=state) is False
    wt.grant_repo_trust("", state_path=state)  # no-op
    assert not state.exists()
