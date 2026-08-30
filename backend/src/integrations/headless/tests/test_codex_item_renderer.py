"""Unit tests for ``integrations.headless.codex.item_renderer.render_item``.

Pure data-in / data-out. Each ``ThreadItem`` variant maps to either a vicoa
message string or ``None`` (intercepted / skipped). Item-shape details come
from the plan's \xa75 table; exact bytes can shift when the 0.131.0 schema
spike confirms field names — assertions here check structure, not strict
equality, except for the trivial cases.
"""

from __future__ import annotations

from integrations.headless.codex.item_renderer import render_item


def test_reasoning_item_uses_brain_prefix_with_summary():
    # Per Codex 0.131.0 schema, reasoning carries `summary` and `content`
    # as string arrays — NOT a single `text` field (the plan was wrong).
    # Renderer prefers summary as the short-form rationale.
    out = render_item(
        {
            "type": "reasoning",
            "summary": ["considered options A and B"],
            "content": ["full chain of thought here, possibly long"],
        }
    )
    assert out is not None
    assert out.startswith("🧠 Reasoning:\n")
    assert "considered options A and B" in out
    # Content not surfaced when summary is present (avoids spammy long
    # reasoning blobs in the chat surface).
    assert "full chain of thought" not in out


def test_reasoning_item_falls_back_to_content_when_no_summary():
    out = render_item(
        {"type": "reasoning", "content": ["raw thought 1", "raw thought 2"]}
    )
    assert out is not None
    assert "raw thought 1" in out
    assert "raw thought 2" in out


def test_reasoning_item_with_no_summary_or_content_is_dropped():
    # Empty reasoning items would render to bare "🧠 Reasoning:\n" — useless
    # noise in the chat surface. Drop them instead.
    assert render_item({"type": "reasoning"}) is None
    assert render_item({"type": "reasoning", "summary": [], "content": []}) is None


def test_command_execution_item_shows_bash_and_result():
    out = render_item(
        {
            "type": "commandExecution",
            "command": "ls -la /tmp",
            "cwd": "/Users/foo",
            "aggregatedOutput": "total 0\nfoo.txt\n",
            "exitCode": 0,
            "status": "completed",
        }
    )
    assert out is not None
    # format_tool_use("Bash", ...) prefix from format_tools.py
    assert "Using tool: Bash" in out
    assert "ls -la /tmp" in out
    # Result block per the plan §5 row
    assert "Result:" in out
    assert "exit 0" in out


def test_command_execution_item_truncates_long_output():
    long_out = "x" * 5000
    out = render_item(
        {
            "type": "commandExecution",
            "command": "yes",
            "aggregatedOutput": long_out,
            "exitCode": 0,
        }
    )
    assert out is not None
    # plan §5 caps the surfaced output at 200 chars; the source string of
    # 5000 chars must not appear verbatim in the rendered message.
    assert long_out not in out


def test_command_execution_canceled_status_shows_cancelled_note():
    """When the user picks Cancel/Decline on the permission card, codex
    emits a commandExecution item with status="canceled" and no exit code.
    We must surface that as "cancelled" — NOT as a fake (exit None) result
    which reads like the command silently ran and produced nothing."""
    out = render_item(
        {
            "type": "commandExecution",
            "command": "rm ../text.txt",
            "status": "canceled",
            "aggregatedOutput": "",
            "exitCode": None,
        }
    )
    assert out is not None
    assert "rm ../text.txt" in out
    assert "cancelled" in out.lower()
    # The "Result: (exit None)" tail must NOT appear — it's misleading.
    assert "Result:" not in out
    assert "exit None" not in out


def test_command_execution_clean_success_skips_result_line():
    """Empty stdout + exit 0 = nothing to surface. Head row only."""
    out = render_item(
        {
            "type": "commandExecution",
            "command": "true",
            "aggregatedOutput": "",
            "exitCode": 0,
            "status": "completed",
        }
    )
    assert out is not None
    assert "true" in out
    assert "Result:" not in out
    assert "exit" not in out


def test_command_execution_in_progress_skips_result_line():
    """exitCode is None during in-progress states; don't fake "(exit None)"."""
    out = render_item(
        {
            "type": "commandExecution",
            "command": "long_running",
            "aggregatedOutput": "",
            "exitCode": None,
            "status": "running",
        }
    )
    assert out is not None
    assert "Result:" not in out


def test_command_execution_nonzero_exit_shown_even_without_output():
    """When the command fails with no captured stdout, the exit code is
    still useful information — surface it."""
    out = render_item(
        {
            "type": "commandExecution",
            "command": "grep foo /nope",
            "aggregatedOutput": "",
            "exitCode": 2,
            "status": "failed",
        }
    )
    assert out is not None
    assert "Result:" in out
    assert "exit 2" in out


def test_file_change_add_renders_as_write_tool():
    out = render_item(
        {
            "type": "fileChange",
            "changes": [
                {
                    "path": "/repo/new.py",
                    "kind": {"type": "add"},
                    "diff": "print('hi')\n",
                }
            ],
        }
    )
    assert out is not None
    # Mirrors claude_code's Write tool head shape: "Write - `path`".
    assert out.startswith("🔧 Using tool: Write - `/repo/new.py`")
    assert "```diff" in out
    assert "print('hi')" in out
    # Path appears once (in the head); we don't repeat it as a **header**
    # above the diff block per UX feedback.
    assert out.count("/repo/new.py") == 1


def test_file_change_update_renders_as_edit_tool():
    out = render_item(
        {
            "type": "fileChange",
            "changes": [
                {
                    "path": "/repo/src/foo.py",
                    "kind": {"type": "update"},
                    "diff": "@@ -1 +1 @@\n-old\n+new\n",
                }
            ],
        }
    )
    assert out is not None
    assert out.startswith("🔧 Using tool: Edit - `/repo/src/foo.py`")
    assert "+new" in out
    assert out.count("/repo/src/foo.py") == 1


def test_file_change_delete_renders_as_delete_tool():
    out = render_item(
        {
            "type": "fileChange",
            "changes": [
                {
                    "path": "/repo/old.py",
                    "kind": {"type": "delete"},
                    "diff": "removed\n",
                }
            ],
        }
    )
    assert out is not None
    assert out.startswith("🔧 Using tool: Delete - `/repo/old.py`")
    assert "removed" in out
    assert out.count("/repo/old.py") == 1


def test_file_change_multi_file_falls_back_to_apply_patch():
    """Multi-file fileChange items are rare in practice (codex emits one
    change per item) but when they happen, we use ApplyPatch + glyphs +
    per-file diff headers so the diffs stay associated with their paths."""
    out = render_item(
        {
            "type": "fileChange",
            "changes": [
                {
                    "path": "/repo/a.py",
                    "kind": {"type": "add"},
                    "diff": "a\n",
                },
                {
                    "path": "/repo/b.py",
                    "kind": {"type": "delete"},
                    "diff": "b\n",
                },
            ],
        }
    )
    assert out is not None
    assert "ApplyPatch" in out
    assert "/repo/a.py" in out
    assert "/repo/b.py" in out
    assert "➕" in out
    assert "❌" in out


def test_file_change_item_with_no_changes_shows_bare_head():
    assert render_item({"type": "fileChange"}) == "🔧 Using tool: ApplyPatch"
    assert (
        render_item({"type": "fileChange", "changes": []})
        == "🔧 Using tool: ApplyPatch"
    )


def test_unknown_item_type_returns_none():
    assert render_item({"type": "futureItemKindWeDontHandleYet"}) is None
