"""Daemon-local trust for worktree lifecycle commands.

A committed ``vicoa.json`` can carry arbitrary shell in ``worktree.setup`` /
``worktree.teardown``; a repo you cloned could ship a malicious one. Auto-running
it the moment a worktree session spawns is the hazard, so the daemon records a
one-time, per-(repo, machine) trust decision before those commands ever run.

Trust is keyed by the **source repo's absolute path** (the checkout that provided
the commands) and persisted in ``~/.vicoa/daemon_state.json`` next to the rest of
the daemon's local state — the machine, not the account, is the trust boundary,
and a decision never syncs to another device. Setup asks for the grant via the
web confirm (RPC ``worktree-trust-grant``); teardown, which runs unattended, only
fires when the repo is *already* trusted.
"""

from __future__ import annotations

import os
from pathlib import Path

from vicoa.machine_state import read_state_file, save_state_file

# Top-level (not per-base-url) map: ``{abs_repo_path: True}``. Trust is a property
# of the checkout on disk, independent of which backend the daemon talks to.
_TRUST_KEY = "worktree_trust"


def _state_path() -> Path:
    """The daemon state file, resolved at call time so a redirected HOME (tests)
    is honored — matching ``worktree_paths.workspaces_root``, not the import-time
    ``machine_state.STATE_PATH`` constant."""
    return Path.home() / ".vicoa" / "daemon_state.json"


def _canonical(repo_dir: str) -> str:
    return str(Path(os.path.expanduser(repo_dir)).resolve())


def is_repo_trusted(repo_dir: str, state_path: Path | None = None) -> bool:
    """Whether the user has approved running this repo's lifecycle commands."""
    if not repo_dir:
        return False
    trust = read_state_file(state_path or _state_path()).get(_TRUST_KEY)
    if not isinstance(trust, dict):
        return False
    return bool(trust.get(_canonical(repo_dir)))


def grant_repo_trust(repo_dir: str, state_path: Path | None = None) -> None:
    """Persist a trust grant for ``repo_dir`` (idempotent)."""
    if not repo_dir:
        return
    path = state_path or _state_path()
    state = read_state_file(path)
    trust = state.get(_TRUST_KEY)
    if not isinstance(trust, dict):
        trust = {}
    trust[_canonical(repo_dir)] = True
    state[_TRUST_KEY] = trust
    save_state_file(state, path)
