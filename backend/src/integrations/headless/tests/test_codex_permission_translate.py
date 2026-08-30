"""Tests for codex permission_mode → `-c` flag translation (plan §3.7, §5.7).

The daemon collapses a single client-side `permission_mode` enum down to the
two or three codex `-c` overrides required to honour it. Only the knobs each
mode actually changes from codex defaults get emitted, so the user's
`~/.codex/config.toml` keeps owning fields the UI doesn't touch.

One exception: `network_access=true` is always emitted in Default mode,
because remote-coding sessions need npm/pip installs and codex's own default
is `false` (§9.3).
"""

from __future__ import annotations

import pytest

from integrations.headless.codex.permission_translate import (
    translate_permission_mode,
)


class TestTranslatePermissionMode:
    def test_default_only_emits_network_access_override(self):
        # `default` preserves the user's ~/.codex/config.toml for everything
        # the UI doesn't touch (no approval/sandbox/collab override), but
        # always flips workspace-write network_access on for remote coding.
        result = translate_permission_mode("default")
        assert result == ["-c", "sandbox_workspace_write.network_access=true"]

    def test_bypass_emits_dangerous_overrides(self):
        result = translate_permission_mode("bypassPermissions")
        assert result == [
            "-c",
            "approval_policy=never",
            "-c",
            "sandbox_mode=danger-full-access",
            "-c",
            "collaboration_mode=default",
        ]

    def test_plan_no_longer_accepted(self):
        # `plan` was removed from the Codex picker — the translator should
        # treat it as unknown so any stale caller raises loudly.
        with pytest.raises(ValueError, match="unknown codex permission_mode"):
            translate_permission_mode("plan")

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="unknown codex permission_mode"):
            translate_permission_mode("garbage")
