"""Worktree lifecycle config — shared normalization for setup/teardown commands.

A project can declare shell commands that run when one of its linked worktrees is
created (``setup``) or removed (``teardown``) — so a fresh worktree arrives with
deps installed / ``.env`` copied and a removed one is cleaned up. Modeled on
Paseo's ``worktree.setup`` / ``worktree.teardown``.

Two substrates carry this config and MUST agree on its shape, so the parser
lives here in ``protocol`` — the dependency-light package both the daemon and the
backend import (the daemon never pulls in ``shared``, which drags in the DB and
server infrastructure the user-facing CLI wheel must not ship):

* a committed ``vicoa.json`` at the repo root, read by the daemon, with the hooks
  nested under a ``"worktree"`` key;
* ``projects.worktree_config`` (JSONB), edited from the dashboard, storing just
  the inner ``{"setup": [...], "teardown": [...]}`` object.

A hook value is a single command string OR a list of command strings (run
sequentially); either normalizes to ``list[str]`` with blank / whitespace-only
entries dropped — mirroring Paseo's ``normalizeLifecycleCommands`` so behavior
matches the reference implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Committed config file locations relative to the repo root, in priority order.
# `.vicoa/config.json` (namespaced — mirrors the `~/.vicoa/` home convention and
# leaves room for other repo-level vicoa files) is preferred; a bare `vicoa.json`
# at the root is the discoverable, Paseo-style (`paseo.json`) fallback. Both hold
# the same wrapped shape (hooks under a `"worktree"` key).
COMMITTED_CONFIG_FILES: tuple[str, ...] = (".vicoa/config.json", "vicoa.json")


def normalize_lifecycle_commands(value: Any) -> list[str]:
    """Coerce a hook value (``str | list[str] | None``) to a command list.

    * a non-empty string ⇒ ``[value]``
    * a list ⇒ its string items, blank / whitespace-only ones dropped
    * anything else (``None``, dict, number, a list of non-strings) ⇒ ``[]``
    """
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item.strip()]
    return []


@dataclass(frozen=True)
class WorktreeConfig:
    """Normalized setup / teardown command lists for a project's worktrees."""

    setup: list[str] = field(default_factory=list)
    teardown: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.setup and not self.teardown

    def to_dict(self) -> dict[str, list[str]]:
        """The inner ``{"setup", "teardown"}`` shape stored in the entity JSONB."""
        return {"setup": list(self.setup), "teardown": list(self.teardown)}


def parse_worktree_config(inner: Any) -> WorktreeConfig:
    """Parse the inner ``{"setup", "teardown"}`` object (the entity JSONB shape).

    Tolerant of anything: a non-dict (or missing keys) yields an empty config,
    never an error — a malformed stored value must not break a worktree spawn.
    """
    if not isinstance(inner, dict):
        return WorktreeConfig()
    return WorktreeConfig(
        setup=normalize_lifecycle_commands(inner.get("setup")),
        teardown=normalize_lifecycle_commands(inner.get("teardown")),
    )


def parse_committed_config(file_data: Any) -> WorktreeConfig:
    """Parse a committed ``vicoa.json`` dict (hooks nested under ``"worktree"``).

    The file wraps the hooks so it can grow non-worktree keys later; the entity
    stores only the inner object. Both funnel through :func:`parse_worktree_config`
    so the two can never diverge.
    """
    if not isinstance(file_data, dict):
        return WorktreeConfig()
    return parse_worktree_config(file_data.get("worktree"))
