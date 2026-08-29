"""Regression test for: TUI `⏵⏵ bypass permissions on` not detected.

User reported that Shift+Tab into bypassPermissions (and the UI sheet's
"Skip permissions (Yolo)" option) didn't work even though every other
mode did. Root cause: bypassPermissions is sticky — Claude's status line
drops the `(shift+tab to cycle)` hint once you're in bypass mode, and
the label has no `mode` word ("⏵⏵ bypass permissions on"). The
PERMISSION_MODE_PATTERN and the fallback both miss it.

Fix: a focused keyword match for "bypass permissions?" emits a
bypassPermissions entry whenever the buffer contains it. set_toggle's
send-one-observe loop now confirms the bypass target as soon as Claude
redraws the status line.
"""

from __future__ import annotations

import pytest

from integrations.cli_wrappers.claude_code.state.toggle_manager import (
    ToggleManager,
)


@pytest.fixture
def manager() -> ToggleManager:
    return ToggleManager(write_to_pty_func=lambda _b: None, log_func=lambda _msg: None)


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Bypass display Claude actually emits — sticky mode has no cycle
        # hint and no "mode" word, just the label + "on".
        ("⏵⏵ bypass permissions on", "bypassPermissions"),
        ("⏵⏵ bypass permissions on\n", "bypassPermissions"),
        # Even bare "bypass" should be enough — narrow enough that the
        # control_detection_buffer's status-line context won't false-match
        # on user chat content.
        ("⏵⏵ bypass permission on", "bypassPermissions"),
        # Existing modes still go through the regular paths.
        ("default mode on", "default"),
        ("plan mode on", "plan"),
    ],
)
def test_parse_slug_from_output_detects_bypass(
    manager: ToggleManager, raw: str, expected: str
) -> None:
    assert manager._parse_slug_from_output("permission_mode", raw) == expected
