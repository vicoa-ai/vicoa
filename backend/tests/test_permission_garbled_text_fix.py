"""Test that permission prompts are not garbled when using cursor forward sequences.

This test validates the fix for the issue where permission questions appeared as
garbled text like "Do you want t m ke th s e it to testing.txt?" instead of
"Do you want to make this edit to testing.txt?".

The root cause was that Claude CLI uses cursor forward sequences (\x1b[NC) to
position text, and the simple ANSI cleaner was replacing these with spaces,
creating garbled output when used between individual characters.

The fix uses TerminalRenderer which properly simulates terminal cursor movements.
"""

from src.integrations.cli_wrappers.claude_code.terminal.terminal_parser import (
    TerminalRenderer,
)
from src.integrations.cli_wrappers.claude_code.detection import PermissionDetector


class TestPermissionGarbledTextFix:
    """Test cases for the garbled text fix."""

    def test_cursor_forward_between_words(self):
        """Test that cursor forward between words produces correct spacing."""
        # Claude CLI uses \x1b[1C (cursor forward 1) between words
        raw = "\x1b[1CDo\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Coverwrite\x1b[1C\x1b[1mtesting.txt?"

        renderer = TerminalRenderer()
        result = renderer.render(raw)

        # Should have proper spacing
        assert "Do you want to overwrite" in result
        assert "testing.txt?" in result
        # Should NOT have garbled text
        assert "Doyou" not in result
        assert "wantto" not in result

    def test_actual_log_buffer(self):
        """Test with actual buffer from production logs."""
        # This is the exact buffer that was producing garbled text
        raw_buffer = (
            "╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\x1b[39m\r\r\n"
            "\x1b[1CDo\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Coverwrite\x1b[1C\x1b[1mtesting.txt\x1b[22m?\r\r\n"
            "\x1b[1C\x1b[38;2;177;185;249m❯\x1b[1C\x1b[38;2;153;153;153m1.\x1b[1C\x1b[38;2;177;185;249mYes\x1b[39m\r\r\n"
            "\x1b[3C\x1b[38;2;153;153;153m2.\x1b[1C\x1b[39mYes,\x1b[1Callow\x1b[1Call\x1b[1Cedits\x1b[1Cduring\x1b[1Cthis\x1b[1Csession\x1b[1C\x1b[1m(shift+tab)\x1b[22m\r\r\n"
            "\x1b[3C\x1b[38;2;153;153;153m3.\x1b[1C\x1b[39mNo\r\r\n\r\r\n"
            "\x1b[1C\x1b[38;2;153;153;153mEsc\x1b[1Cto\x1b[1Ccancel\x1b[1C·\x1b[1CTab\x1b[1Cto\x1b[1Camend\x1b[39m"
        )

        renderer = TerminalRenderer()
        clean = renderer.render(raw_buffer)

        # Should contain the correct question text
        assert "Do you want to overwrite testing.txt?" in clean

        # Should contain all options
        assert "1. Yes" in clean
        assert "2. Yes, allow all edits during this session" in clean
        assert "3. No" in clean

        # Should NOT contain garbled fragments
        assert "m ke" not in clean
        assert "th s" not in clean
        assert "e it" not in clean

    def test_detection_works_with_rendered_buffer(self):
        """Test that permission detection works with rendered buffer."""
        raw_buffer = (
            "\x1b[1CDo\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Coverwrite\x1b[1C\x1b[1mtesting.txt\x1b[22m?\r\r\n"
            "\x1b[1C❯\x1b[1C1.\x1b[1CYes\r\r\n"
            "\x1b[3C2.\x1b[1CYes,\x1b[1Callow\x1b[1Call\x1b[1Cedits\r\r\n"
            "\x1b[3C3.\x1b[1CNo"
        )

        renderer = TerminalRenderer()
        clean = renderer.render(raw_buffer)

        detector = PermissionDetector()
        result = detector.detect_and_extract(clean)

        # Should detect the prompt
        assert result.detected
        assert result.data is not None

        # Should extract correct question
        question = result.data.get("question", "")
        assert "Do you want to overwrite testing.txt?" in question

        # Should extract options
        options = result.data.get("options", [])
        assert len(options) >= 3
        assert any("Yes" in opt for opt in options)
        assert any("No" in opt for opt in options)

    def test_terminal_renderer_vs_ansi_cleaner(self):
        """Compare TerminalRenderer vs ANSICleaner to show the difference."""
        # Test case that highlights the difference
        raw = (
            "\x1b[1CDo\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cmake\x1b[1Cthis\x1b[1Cedit?"
        )

        # TerminalRenderer properly handles cursor movements
        renderer = TerminalRenderer()
        rendered = renderer.render(raw)

        # Both should work for this case (cursor forward does insert space)
        # but verify the text is readable
        assert "Do" in rendered
        assert "you" in rendered
        assert "want" in rendered
        assert "edit?" in rendered

    def test_carriage_return_overwrite(self):
        """Test that carriage returns are handled correctly."""
        # Scenario: Claude overwrites text with carriage return
        raw = "Do you want to xxxxx?\rDo you want to make"

        renderer = TerminalRenderer()
        result = renderer.render(raw)

        # TerminalRenderer should handle \r by moving cursor to start of line
        # The second text should overwrite the first
        assert "Do you want to make" in result
        # Should not contain the overwritten "xxxxx?"
        assert "xxxxx" not in result or result.index("make") < result.index("xxxxx")

    def test_cursor_backward_overwrite(self):
        """Test that cursor backward with overwrite is handled correctly."""
        # Scenario: Cursor moves backward and overwrites text
        raw = "Do you want to xxxxx?\x1b[7Dmake this edit"

        renderer = TerminalRenderer()
        result = renderer.render(raw)

        # The cursor backward (\x1b[7D) should move cursor back 7 positions
        # Then "make this edit" overwrites "xxxxx??"
        assert "make this edit" in result
        # Original "xxxxx?" should be overwritten
        assert "want tomake this edit" in result or "want to make this edit" in result


if __name__ == "__main__":
    # Run tests
    test = TestPermissionGarbledTextFix()

    print("Running test_cursor_forward_between_words...")
    test.test_cursor_forward_between_words()
    print("✓ Passed")

    print("\nRunning test_actual_log_buffer...")
    test.test_actual_log_buffer()
    print("✓ Passed")

    print("\nRunning test_detection_works_with_rendered_buffer...")
    test.test_detection_works_with_rendered_buffer()
    print("✓ Passed")

    print("\nRunning test_terminal_renderer_vs_ansi_cleaner...")
    test.test_terminal_renderer_vs_ansi_cleaner()
    print("✓ Passed")

    print("\nRunning test_carriage_return_overwrite...")
    test.test_carriage_return_overwrite()
    print("✓ Passed")

    print("\nRunning test_cursor_backward_overwrite...")
    test.test_cursor_backward_overwrite()
    print("✓ Passed")

    print("\n✅ All tests passed!")
