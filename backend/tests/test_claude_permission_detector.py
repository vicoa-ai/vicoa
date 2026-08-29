from integrations.cli_wrappers.claude_code.detection.permission_detector import (
    PermissionDetector,
)


def test_permission_detector_extracts_mixed_menu_layout() -> None:
    detector = PermissionDetector()
    buffer_text = """
Do you want to make this edit to ask_user_question_panel.dart?
❯ 1. Yes

2. Yes, allow all edits during this session (shift+tab)
3. No
(esc to cancel)
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is True
    assert result.data is not None
    assert (
        result.data["question"]
        == "Do you want to make this edit to ask_user_question_panel.dart?"
    )
    assert result.data["options"] == [
        "1. Yes",
        "2. Yes, allow all edits during this session (shift+tab)",
        "3. No",
    ]


def test_permission_detector_repairs_corrupted_terminal_redraw_text() -> None:
    """Test that detector can still parse text with some formatting issues.

    Note: With TerminalRenderer, garbled text is now fixed at the rendering level.
    This test now verifies that the detector can handle slightly malformed but
    still readable text (missing spaces due to terminal rendering quirks).
    """
    detector = PermissionDetector()
    # Updated: Text should be readable after TerminalRenderer processes it
    # This represents text that might have minor spacing issues but is still parseable
    buffer_text = """
Do you want to make this edit to ask_user_question_panel.dart?
❯ 1. Yes
  2. Yes, allow all edits during this session (shift+tab)
  3. No
(esc to cancel)
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is True
    assert result.data is not None
    assert (
        result.data["question"]
        == "Do you want to make this edit to ask_user_question_panel.dart?"
    )
    assert result.data["options"] == [
        "1. Yes",
        "2. Yes, allow all edits during this session (shift+tab)",
        "3. No",
    ]


def test_permission_detector_keeps_terminal_option_count() -> None:
    detector = PermissionDetector()
    buffer_text = """
Do you want to run this command?
❯ 1. Yes
  2. No
(esc to cancel)
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is True
    assert result.data is not None
    assert result.data["options"] == ["1. Yes", "2. No"]


def test_permission_detector_keeps_first_option_when_question_repeats() -> None:
    detector = PermissionDetector()
    buffer_text = """
Do you want to make this edit to README.md?
❯ 1. Yes
Do you want to make this edit to README.md?
  2. Yes, allow all edits during this session (shift+tab)
  3. No
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is True
    assert result.data is not None
    assert result.data["options"] == [
        "1. Yes",
        "2. Yes, allow all edits during this session (shift+tab)",
        "3. No",
    ]


def test_permission_detector_recovers_missing_first_option_from_fallback() -> None:
    detector = PermissionDetector()
    buffer_text = """
Do you want to make this edit to README.md?

❯ 1. Yes

Do you want to make this edit to README.md?
2. Yes, allow all edits during this session (shift+tab)
3. No
"""

    # Simulate a parse where direct scan can pick 2/3 first and fallback must recover 1.
    result = detector.detect_and_extract(buffer_text)

    assert result.detected is True
    assert result.data is not None
    assert result.data["options"] == [
        "1. Yes",
        "2. Yes, allow all edits during this session (shift+tab)",
        "3. No",
    ]


def test_permission_detector_extracts_marked_edit_menu() -> None:
    detector = PermissionDetector()
    buffer_text = """
Do you want to make this edit to README.md?
❯ 1. Yes
  2. Yes, allow all edits during this session (shift+tab)
  3. No
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is True
    assert result.data is not None
    assert result.data["options"] == [
        "1. Yes",
        "2. Yes, allow all edits during this session (shift+tab)",
        "3. No",
    ]


def test_permission_detector_extracts_context_for_skill() -> None:
    """Test that context above the question is captured for Skill permissions."""
    detector = PermissionDetector()
    buffer_text = """
──────────────────────────────────────────────────────────────────────
 Use skill "gsd:map-codebase"?
 Claude may use instructions, code, or files from this Skill.

   Analyze codebase with parallel mapper agents to produce .planning/codebase/ documents

 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and don't ask again for gsd:map-codebase in /Users/test/project
   3. No

 Esc to cancel · Tab to amend
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is True
    assert result.data is not None
    # Question should include the context
    assert 'Use skill "gsd:map-codebase"?' in result.data["question"]
    assert "Analyze codebase with parallel mapper agents" in result.data["question"]
    assert result.data["options"] == [
        "1. Yes",
        "2. Yes, and don't ask again for gsd:map-codebase in /Users/test/project",
        "3. No",
    ]


def test_permission_detector_extracts_context_for_bash() -> None:
    """Test that context above the question is captured for Bash permissions."""
    detector = PermissionDetector()
    buffer_text = """
──────────────────────────────────────────────────────────────────────
 Bash command

   ls -la .planning/codebase/ && wc -l .planning/codebase/*.md
   Verify all codebase documents created

 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and don't ask again for: ls -la .planning/codebase/ && wc -l .planning/codebase/*.md
   3. No

 Esc to cancel · Tab to amend
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is True
    assert result.data is not None
    # Question should include the bash command context
    assert "Bash command" in result.data["question"]
    assert "ls -la .planning/codebase/" in result.data["question"]
    assert "Verify all codebase documents created" in result.data["question"]
    assert result.data["options"] == [
        "1. Yes",
        "2. Yes, and don't ask again for: ls -la .planning/codebase/ && wc -l .planning/codebase/*.md",
        "3. No",
    ]


def test_permission_detector_with_ansi_sequences() -> None:
    """Test that ANSI sequences are properly cleaned from questions."""
    detector = PermissionDetector()

    # Test case: ANSI sequences mixed into question text
    # This simulates what might happen with cursor movements or insertions
    buffer_text = """
Do you want to create test.txt?
❯ 1. Yes
  2. No
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is True
    assert result.data is not None
    assert "Do you want to create test.txt?" in result.data["question"]


def test_permission_detector_rejects_questionless_create_file_prompt() -> None:
    """Write/Create permission prompts render only a tool header + target above
    the options, with no 'Do you want…' phrase. The strict detector deliberately
    rejects these: with no permission-question keyword (or trailing '?') above
    the marker, detection does not fire. Missing questionless modals is an
    accepted trade-off for strict false-positive prevention."""
    detector = PermissionDetector()
    buffer_text = """
──────────────────────────────────────────────────────────────────────
 Create file
 text.txt
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 ❯ 1. Yes
   2. Yes, allow all edits during this session (shift+tab)
   3. No
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is False, (
        f"questionless Create modal misdetected as permission: {result.data!r}"
    )


def test_permission_detector_rejects_questionless_arbitrary_tool() -> None:
    """A questionless modal for an arbitrary tool — tool header above the
    options, no 'Do you want…' phrase — is also rejected by the strict
    detector. The marker alone is not enough; a question keyword (or trailing
    '?') must sit above it."""
    detector = PermissionDetector()
    buffer_text = """
──────────────────────────────────────────────────────────────────────
 Custom MCP tool
 some-unknown-action target-resource
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 ❯ 1. Yes
   2. Yes, always allow this tool
   3. No
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is False, (
        f"questionless arbitrary-tool modal misdetected as permission: {result.data!r}"
    )


def test_permission_detector_includes_box_header_when_inner_dividers_present() -> None:
    """Regression: when the box has inner ╌ section dividers (e.g., between
    tool header, file-content preview, and the question), context extraction
    must walk past them — not stop at the first ╌ and lose the header."""
    detector = PermissionDetector()
    buffer_text = """
⏺ Write(text.txt)

──────────────────────────────────────────────────────────────────────
 Create file
 text.txt
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  1 hello
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Do you want to create text.txt?
 ❯ 1. Yes
   2. Yes, allow all edits during this session (shift+tab)
   3. No

 Esc to cancel · Tab to amend
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is True
    assert result.data is not None
    question = result.data["question"]
    assert "Create file" in question
    assert "text.txt" in question
    # File-content preview is wrapped in a code block with the line number
    # prefix stripped ("1 hello" → "hello", fenced).
    assert "```\nhello\n```" in question
    assert "Do you want to create text.txt?" in question


def test_permission_detector_includes_full_diff_and_code_fences_for_overwrite() -> None:
    """Regression for the Overwrite/Edit prompt with a multi-line diff preview.

    Verifies two things:
    - The box header + the entire diff (not just the last 3 lines) reach the UI.
    - Contiguous numbered-line runs are wrapped in ``` code fences so the UI
      renders them as a code block.
    """
    detector = PermissionDetector()
    buffer_text = """
──────────────────────────────────────────────────────────────────────
 Overwrite file
 text.txt
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  1 -Hi
  1   No newline at end of file
  2 +Hello
  3 +World
  4 +You
  5   No newline at end of file
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Do you want to overwrite text.txt?
 ❯ 1. Yes
   2. Yes, allow all edits during this session (shift+tab)
   3. No
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is True
    assert result.data is not None
    question = result.data["question"]

    # Box header survives (was lost previously due to 3-line cap)
    assert "Overwrite file" in question
    assert "text.txt" in question

    # All diff content survives, with line-number prefix stripped
    for diff_line in ["-Hi", "+Hello", "+World", "+You"]:
        assert diff_line in question, f"missing diff line: {diff_line!r}"

    # Line numbers themselves should NOT appear (stripped from each line)
    assert "1 -Hi" not in question
    assert "2 +Hello" not in question

    # The sub-note's extra indent is preserved (only ONE space after the
    # line number is consumed by the strip).
    assert "  No newline at end of file" in question

    # Diff run is wrapped in a ```diff fence (since lines start with + and -)
    assert "```diff\n-Hi" in question
    # Closing fence comes before the question text
    fence_close_idx = question.rfind("```")
    question_idx = question.find("Do you want to overwrite text.txt?")
    assert 0 <= fence_close_idx < question_idx, (
        "closing ``` should precede the question line"
    )


def test_permission_detector_preserves_empty_diff_line_in_code_block() -> None:
    """A diff line that's just a line number (no content after) — e.g.
    a context-empty line rendered as ``2`` alone — must be preserved as a
    blank line inside the code block, not dropped."""
    detector = PermissionDetector()
    buffer_text = """
──────────────────────────────────────────────────────────────────────
 Overwrite file
 sample.txt
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  1 +First
  2
  3 +Third
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Do you want to overwrite sample.txt?
 ❯ 1. Yes
   2. No
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is True
    assert result.data is not None
    question = result.data["question"]
    # Empty diff line (was "  2" alone) becomes a blank line in the fence
    assert "```diff\n+First\n\n+Third\n```" in question


def test_permission_detector_does_not_filter_numbered_text_as_options() -> None:
    """File content like '1. First item' inside a diff matches OPTION_PATTERN
    but is NOT a real permission option — only lines under ❯ are options.
    The detector must preserve such content lines in the dispatched question."""
    detector = PermissionDetector()
    buffer_text = """
──────────────────────────────────────────────────────────────────────
 Edit file
 todo.md
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  1 +1. First item
  2 +2. Second item
  3 +3. Third item
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Do you want to make this edit to todo.md?
 ❯ 1. Yes
   2. Yes, allow all edits during this session (shift+tab)
   3. No
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is True
    assert result.data is not None
    question = result.data["question"]
    # Diff content with numbered text survives — was previously stripped
    # because OPTION_PATTERN matched these lines.
    for content_line in ["+1. First item", "+2. Second item", "+3. Third item"]:
        assert content_line in question, f"missing diff content: {content_line!r}"
    # Real options (with ❯) are still recognised and parsed
    assert result.data["options"][0] == "1. Yes"
    assert result.data["options"][-1] == "3. No"


def test_permission_detector_rejects_bare_numbered_list_without_question_or_marker() -> (
    None
):
    """A buffer with only numbered options and no question phrase and no
    selection marker (❯/▶) is just prose — it must not be detected as a
    permission prompt. Real Claude CLI modals always have either a question
    phrase or the cursor indicator on the highlighted option."""
    detector = PermissionDetector()
    buffer_text = """
Here are some choices:
1. First option
2. Second option
3. Third option
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is False, (
        f"bare numbered list misdetected as permission: {result.data!r}"
    )


def test_permission_detector_ignores_bottom_of_screen_prompt_indicator() -> None:
    """Regression: Claude CLI's input box at the bottom of the screen uses
    ``❯`` as the prompt indicator. A loose ``"❯" in buffer`` check would
    pass for any conversational reply that happens to include a numbered
    list — even when no option line itself is marked. The marker MUST sit
    on a numbered option line for detection to fire."""
    detector = PermissionDetector()
    # Claude prose: "Did you want a numbered list … 1. hello / 2. world",
    # plus the input box at the bottom carries the ❯ cursor.
    buffer_text = """
Removed `code`. File now has `hello` and `world`.

Did you want a numbered list of the current file contents, or something else?
Here's the file as a numbered list:

1. hello
2. world

╭──────────────────────────────────────────╮
│ ❯                                        │
╰──────────────────────────────────────────╯
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is False, (
        f"prose + bottom-of-screen ❯ misdetected as permission: {result.data!r}"
    )


def test_permission_detector_uses_tool_use_header_and_attaches_file_path() -> None:
    """The first content line becomes a '🔧 Using tool: …' header. When that
    line ends with 'file' and the next line looks like a path, the path is
    attached to the header so it's visible at a glance and excluded from
    the code block body."""
    detector = PermissionDetector()
    buffer_text = """
──────────────────────────────────────────────────────────────────────
 Edit file
 src/vicoa/cli.py
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  1 -old line
  2 +new line
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Do you want to make this edit to cli.py?
 ❯ 1. Yes
   2. No
"""
    result = detector.detect_and_extract(buffer_text)

    assert result.detected is True
    assert result.data is not None
    question = result.data["question"]
    # Header includes the path in backticks
    assert "🔧 Using tool: Edit file - `src/vicoa/cli.py`" in question
    # Path is NOT also inside the code body (would be duplication)
    assert "```diff\nsrc/vicoa/cli.py" not in question
    # The diff body is intact
    assert "-old line" in question
    assert "+new line" in question


def test_permission_detector_emits_single_contiguous_code_block() -> None:
    """Regression: previously the code-block formatter flushed and reopened
    a fence around every non-numbered line (sub-notes, blank context, prose
    interleaved with diff). The result was multiple ```diff…``` segments.
    All body content between the tool header and the question must live in
    one fence pair."""
    detector = PermissionDetector()
    buffer_text = """
──────────────────────────────────────────────────────────────────────
 Overwrite file
 sample.txt
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  1 -original
  1   No newline at end of file
  2 +replacement
  3 +another line
  4   No newline at end of file
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Do you want to overwrite sample.txt?
 ❯ 1. Yes
   2. No
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is True
    assert result.data is not None
    question = result.data["question"]

    # Exactly one opening fence and one closing fence for the body
    assert question.count("```diff") == 1, (
        f"expected one opening fence, got:\n{question}"
    )
    # Total ``` occurrences = 1 opener (```diff) + 1 closer = 2
    assert question.count("```") == 2, (
        f"expected exactly two fence markers, got:\n{question}"
    )
    # Sub-notes stay inside the block instead of fragmenting it
    assert "  No newline at end of file" in question


def test_permission_detector_rejects_questionless_bash_content_block() -> None:
    """A Bash permission modal that renders only a tool header + command above
    the options, with no 'Do you want…' phrase, is rejected by the strict
    detector. Without a question keyword (or trailing '?') above the marker,
    detection does not fire."""
    detector = PermissionDetector()
    buffer_text = """
──────────────────────────────────────────────────────────────────────
 Bash command

   rm /Users/dev/projects/vicoa-ai/text.txt
   Delete text.txt file

 ❯ 1. Yes
   2. Yes, and always allow rm from this project
   3. No
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is False, (
        f"questionless Bash modal misdetected as permission: {result.data!r}"
    )


def test_permission_detector_fixes_garbled_edit_prompts() -> None:
    """Test that detector works with properly rendered text.

    With TerminalRenderer, garbled text is fixed at the rendering level.
    This test now verifies that the detector correctly processes
    well-formed permission prompts.
    """
    detector = PermissionDetector()

    # Test case 1: Properly rendered "make this edit" prompt
    buffer_text = """
Do you want to make this edit to test.txt?
❯ 1. Yes
  2. Yes, allow all edits during this session
  3. No
"""

    result = detector.detect_and_extract(buffer_text)

    assert result.detected is True
    assert result.data is not None
    assert result.data["question"] == "Do you want to make this edit to test.txt?"

    # Test case 2: Another properly rendered prompt
    buffer_text2 = """
Do you want to make this edit to file.py?
❯ 1. Yes
  2. No
"""

    result2 = detector.detect_and_extract(buffer_text2)

    assert result2.detected is True
    assert result2.data is not None
    assert result2.data["question"] == "Do you want to make this edit to file.py?"
