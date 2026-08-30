"""Translate a vicoa `permission_mode` enum into codex `-c key=value` overrides.

Both codex paths (codex_acp and codex_native) end up running the codex CLI;
this module is the single source of truth for how a UI-level permission_mode
maps to codex CLI flags. Per plan §3.7, only knobs the chosen mode actually
changes from codex defaults are emitted, so the user's ~/.codex/config.toml
keeps owning everything the UI doesn't touch.

Exception: `network_access=true` is always emitted in Default mode (§9.3) —
remote-coding sessions need npm/pip installs and codex's own default for
workspace-write is `false`.
"""

from __future__ import annotations


def translate_permission_mode(mode: str) -> list[str]:
    """Return the `-c key=value` flag pairs for a codex permission mode."""
    if mode == "default":
        return ["-c", "sandbox_workspace_write.network_access=true"]
    if mode == "bypassPermissions":
        return [
            "-c",
            "approval_policy=never",
            "-c",
            "sandbox_mode=danger-full-access",
            "-c",
            "collaboration_mode=default",
        ]
    raise ValueError(f"unknown codex permission_mode: {mode!r}")
