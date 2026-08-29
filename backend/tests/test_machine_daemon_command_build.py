"""Tests for MachineDaemon._build_headless_command flag plumbing.

Per plan §5.5: the daemon forwards new metadata (model, thinking_effort,
reasoning_effort, widened permission_mode) into the headless agent command
line. Tests verify the *command vector* the daemon would Popen, so we never
need to actually launch a subprocess.

We assert non-frozen behavior — the frozen (`sys.frozen`) path is the
PyInstaller bundle and is exercised by the same helpers but with a different
top-level command shape.
"""

from __future__ import annotations

from typing import Any

import pytest

from vicoa.machine_daemon import MachineDaemon


@pytest.fixture
def daemon() -> MachineDaemon:
    return MachineDaemon(api_key="test-key", base_url="http://localhost:0")


def _pair_following(cmd: list[str], flag: str) -> str | None:
    """Return the value placed after `flag` in a flat argv list, or None."""
    try:
        idx = cmd.index(flag)
    except ValueError:
        return None
    return cmd[idx + 1] if idx + 1 < len(cmd) else None


class TestClaudeCommandFlags:
    """`--model` and `--thinking-effort` flow through when metadata sets them."""

    def _build(self, daemon: MachineDaemon, **metadata: Any) -> list[str]:
        return daemon._build_headless_command(
            directory="/tmp/x",
            agent="claude",
            session_id="sess-1",
            metadata=metadata or None,
        )

    def test_model_flag_emitted_when_present(self, daemon: MachineDaemon):
        cmd = self._build(daemon, model="claude-sonnet-4-6")
        assert _pair_following(cmd, "--model") == "claude-sonnet-4-6"

    def test_model_flag_absent_when_metadata_missing(self, daemon: MachineDaemon):
        cmd = self._build(daemon)
        assert "--model" not in cmd

    def test_thinking_effort_flag_emitted_when_present(self, daemon: MachineDaemon):
        cmd = self._build(daemon, thinking_effort="high")
        assert _pair_following(cmd, "--thinking-effort") == "high"

    def test_thinking_effort_off_passes_through(self, daemon: MachineDaemon):
        # `off` is a real catalog value (mapped to ThinkingConfigDisabled in
        # the headless wrapper). It must NOT be silently dropped here.
        cmd = self._build(daemon, thinking_effort="off")
        assert _pair_following(cmd, "--thinking-effort") == "off"

    def test_thinking_effort_absent_when_metadata_missing(self, daemon: MachineDaemon):
        cmd = self._build(daemon)
        assert "--thinking-effort" not in cmd

    def test_dual_write_enable_thinking_preserved(self, daemon: MachineDaemon):
        # Plan §3.6 / §5.5: clients dual-write enable_thinking for old daemons,
        # thinking_effort for new daemons. The daemon emits BOTH; claude_code.py
        # picks thinking_effort when both are present. So a new client sending
        # both should produce both flags here.
        cmd = self._build(daemon, thinking_effort="high", enable_thinking=True)
        assert "--thinking-effort" in cmd
        assert "--enable-thinking" in cmd

    def test_permission_mode_default_when_metadata_silent(self, daemon: MachineDaemon):
        # Daemon hardcoded fallback for Claude when metadata doesn't carry
        # permission_mode. Used to be "acceptEdits" — flipped to "default"
        # so mobile-spawned sessions don't surprise users with auto-accept.
        cmd = self._build(daemon)
        assert _pair_following(cmd, "--permission-mode") == "default"

    def test_permission_mode_metadata_wins_over_default(self, daemon: MachineDaemon):
        cmd = self._build(daemon, permission_mode="plan")
        assert _pair_following(cmd, "--permission-mode") == "plan"


class TestCodexCommandFlags:
    """`--model`, `--reasoning-effort`, widened `--permission-mode` for codex.

    The daemon forwards these to whichever codex wrapper is on the path
    (codex_acp or codex_native — selected by VICOA_USE_NATIVE_CODEX). Both
    wrappers are responsible for the translation to codex CLI flags; this
    test only verifies that the daemon's command line carries the metadata
    forward in a well-defined shape.
    """

    def _build(self, daemon: MachineDaemon, **metadata: Any) -> list[str]:
        return daemon._build_headless_command(
            directory="/tmp/x",
            agent="codex",
            session_id="sess-1",
            metadata=metadata or None,
        )

    def test_model_flag_emitted_when_present(self, daemon: MachineDaemon):
        cmd = self._build(daemon, model="gpt-5-codex")
        assert _pair_following(cmd, "--model") == "gpt-5-codex"

    def test_reasoning_effort_flag_emitted_when_present(self, daemon: MachineDaemon):
        cmd = self._build(daemon, reasoning_effort="high")
        assert _pair_following(cmd, "--reasoning-effort") == "high"

    def test_permission_mode_flag_emitted_when_present(self, daemon: MachineDaemon):
        # `default` is the new codex-specific value the widened extractor
        # accepts. The daemon forwards the canonical token; the wrapper
        # handles the `-c` translation.
        cmd = self._build(daemon, permission_mode="default")
        assert _pair_following(cmd, "--permission-mode") == "default"

    def test_no_extra_flags_when_metadata_minimal(self, daemon: MachineDaemon):
        cmd = self._build(daemon)
        assert "--model" not in cmd
        assert "--reasoning-effort" not in cmd
        assert "--permission-mode" not in cmd
