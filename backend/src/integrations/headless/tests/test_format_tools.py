"""Layer 1 tests for ``integrations.headless.format_tools.format_tool_use``.

Representative coverage — every Claude tool branch the runner forwards. Not
exhaustive (the table is long); the goal is to catch a regression that would
break the dashboard's tool-call rendering.
"""

from __future__ import annotations

from integrations.headless.format_tools import (
    format_background_task_notification,
    format_tool_use,
    subagent_label,
)


def test_bash_uses_backticked_command():
    out = format_tool_use("Bash", {"command": "git status"})
    assert out == "🔧 Using tool: Bash - `git status`"


def test_bash_without_command_falls_back():
    out = format_tool_use("Bash", {})
    assert out == "🔧 Using tool: Bash"


def test_edit_emits_diff_with_file_path():
    out = format_tool_use(
        "Edit",
        {
            "file_path": "/a/b.py",
            "old_string": "foo",
            "new_string": "bar",
            "replace_all": False,
        },
    )
    assert "🔧 Using tool: **Edit**" in out
    assert "`/a/b.py`" in out
    # Diff block should contain both - foo and + bar
    assert "- foo" in out
    assert "+ bar" in out


def test_edit_replace_all_annotated():
    out = format_tool_use(
        "Edit",
        {
            "file_path": "/a/b.py",
            "old_string": "x",
            "new_string": "y",
            "replace_all": True,
        },
    )
    assert "*Replacing all occurrences*" in out


def test_write_emits_content_as_additions_diff():
    out = format_tool_use(
        "Write",
        {"file_path": "/a/new.py", "content": "line one\nline two"},
    )
    assert "🔧 Using tool: **Write**" in out
    assert "`/a/new.py`" in out
    # New-file body rendered as an all-additions diff block.
    assert "```diff" in out
    assert "+ line one" in out
    assert "+ line two" in out


def test_write_without_content_is_header_only():
    out = format_tool_use("Write", {"file_path": "/a/empty.py"})
    assert out == "🔧 Using tool: **Write** - `/a/empty.py`"
    assert "```diff" not in out


def test_read_with_offset_and_limit():
    out = format_tool_use("Read", {"file_path": "/x.py", "offset": 10, "limit": 50})
    assert "Read - `/x.py`" in out
    assert "offset=10" in out
    assert "limit=50" in out


def test_grep_with_path_and_flags():
    out = format_tool_use(
        "Grep",
        {"pattern": "fn (.*)", "path": "src/", "-i": True, "multiline": True},
    )
    assert "Grep - `fn (.*)`" in out
    assert "`src/`" in out
    assert "case-insensitive" in out
    assert "multiline" in out


def test_ask_user_question_single_question_renders_options():
    out = format_tool_use(
        "AskUserQuestion",
        {
            "questions": [
                {
                    "question": "Pick a color",
                    "options": [
                        {"label": "Red", "description": "Bold"},
                        {"label": "Blue", "description": "Cool"},
                    ],
                }
            ]
        },
    )
    assert "**Pick a color**" in out
    assert "**Red** — Bold" in out
    assert "**Blue** — Cool" in out


def test_ask_user_question_multi_uses_headers():
    out = format_tool_use(
        "AskUserQuestion",
        {
            "questions": [
                {
                    "header": "color",
                    "question": "Pick a color",
                    "options": [{"label": "Red", "description": "Bold"}],
                },
                {
                    "header": "size",
                    "question": "Pick a size",
                    "options": [{"label": "L", "description": "Large"}],
                    "multiSelect": True,
                },
            ]
        },
    )
    assert "**[color]** Pick a color" in out
    assert "**[size]** Pick a size" in out
    assert "*(multiple selections allowed)*" in out


def test_todowrite_renders_status_icons():
    out = format_tool_use(
        "TodoWrite",
        {
            "todos": [
                {"content": "task one", "status": "completed"},
                {"content": "task two", "status": "in_progress"},
                {"content": "task three", "status": "pending"},
            ]
        },
    )
    assert "● 1. task one" in out
    assert "◐ 2. task two" in out
    assert "○ 3. task three" in out


def test_unknown_tool_picks_common_param():
    out = format_tool_use("WeirdTool", {"file_path": "/x"})
    assert out == "🔧 Using tool: WeirdTool - `/x`"


def test_unknown_tool_with_no_recognized_param():
    out = format_tool_use("WeirdTool", {"unrelated": True})
    assert out == "🔧 Using tool: WeirdTool"


# --- Agent / Task ----------------------------------------------------------


def test_agent_row_carries_the_prompt_as_its_body():
    """The assignment is the only record of what the sub-agent was asked to do
    — the child ``UserMessage`` repeating it is dropped with the other
    sub-agent tool results — so it rides the row's collapsible body."""
    out = format_tool_use(
        "Agent",
        {
            "description": "Map the auth flow",
            "subagent_type": "Explore",
            "prompt": "Find every call site of ensure_local_user.",
        },
    )
    assert out == (
        "🔧 Using tool: Agent - `Map the auth flow` (agent: Explore)\n\n"
        "Find every call site of ensure_local_user."
    )


def test_agent_row_without_a_prompt_stays_one_line():
    out = format_tool_use(
        "Agent", {"description": "Map the auth flow", "subagent_type": "Explore"}
    )
    assert out == "🔧 Using tool: Agent - `Map the auth flow` (agent: Explore)"


def test_agent_row_marks_a_background_launch():
    out = format_tool_use(
        "Agent",
        {
            "description": "Watch CI",
            "subagent_type": "Explore",
            "model": "opus",
            "run_in_background": True,
        },
    )
    assert out == (
        "🔧 Using tool: Agent - `Watch CI` (agent: Explore, model: opus, background)"
    )


def test_subagent_label_prefers_an_explicit_name():
    assert (
        subagent_label({"name": "reviewer", "subagent_type": "Explore"}) == "reviewer"
    )
    assert subagent_label({"subagent_type": "Explore"}) == "Explore"
    assert subagent_label({"name": "  ", "subagent_type": "Explore"}) == "Explore"
    assert subagent_label({}) == ""


# --- Background task notifications -----------------------------------------


def test_background_task_notification_is_a_one_line_tool_row():
    out = format_background_task_notification("Sync main", "completed")
    assert out == "🔧 Using tool: Background task - `Sync main`"


def test_background_task_notification_keeps_the_rest_as_a_body():
    out = format_background_task_notification("Watch CI\n\nexit code 0", "completed")
    assert out == "🔧 Using tool: Background task - `Watch CI`\n\nexit code 0"


def test_background_task_notification_reports_a_non_completed_status():
    out = format_background_task_notification("Watch CI", "failed")
    assert out == "🔧 Using tool: Background task - `Watch CI` (failed)"


def test_background_task_notification_without_a_summary_still_labels_itself():
    out = format_background_task_notification("   ", None)
    assert out == "🔧 Using tool: Background task - `Background task finished`"
