"""Tests for ANSI escape sequence cleaning."""

from integrations.cli_wrappers.claude_code.terminal.ansi_cleaner import ANSICleaner


def test_clean_text_without_ansi() -> None:
    """Test that clean text passes through unchanged."""
    text = "Hello, world!"
    assert ANSICleaner.clean_all(text) == text


def test_clean_csi_cursor_movement() -> None:
    """Test cleaning of CSI cursor movement sequences."""
    # Cursor forward - converted to spaces (Claude uses this for spacing)
    assert ANSICleaner.clean_all("text\x1b[3Cmore") == "text   more"  # 3 spaces
    assert ANSICleaner.clean_all("text\x1b[1Cmore") == "text more"  # 1 space
    # Cursor backward - removed (doesn't add spacing)
    assert ANSICleaner.clean_all("text\x1b[2Dmore") == "textmore"
    # Cursor up - removed
    assert ANSICleaner.clean_all("text\x1b[1Amore") == "textmore"
    # Cursor down - removed
    assert ANSICleaner.clean_all("text\x1b[4Bmore") == "textmore"


def test_clean_csi_editing_sequences() -> None:
    """Test cleaning of CSI text editing sequences."""
    # Insert character (@)
    assert ANSICleaner.clean_all("text\x1b[1@more") == "textmore"
    # Delete character (P)
    assert ANSICleaner.clean_all("text\x1b[2Pmore") == "textmore"
    # Erase character (X)
    assert ANSICleaner.clean_all("text\x1b[3Xmore") == "textmore"
    # Insert line (L)
    assert ANSICleaner.clean_all("text\x1b[1Lmore") == "textmore"
    # Delete line (M)
    assert ANSICleaner.clean_all("text\x1b[2Mmore") == "textmore"


def test_clean_csi_erase_sequences() -> None:
    """Test cleaning of CSI erase sequences."""
    # Erase in display (J)
    assert ANSICleaner.clean_all("text\x1b[2Jmore") == "textmore"
    # Erase in line (K)
    assert ANSICleaner.clean_all("text\x1b[Kmore") == "textmore"
    assert ANSICleaner.clean_all("text\x1b[1Kmore") == "textmore"
    assert ANSICleaner.clean_all("text\x1b[2Kmore") == "textmore"


def test_clean_csi_sgr_formatting() -> None:
    """Test cleaning of SGR (Select Graphic Rendition) sequences."""
    # Reset
    assert ANSICleaner.clean_all("text\x1b[mmore") == "textmore"
    # Bold
    assert ANSICleaner.clean_all("text\x1b[1mmore") == "textmore"
    # Color
    assert ANSICleaner.clean_all("text\x1b[31mmore") == "textmore"
    # Multiple parameters
    assert ANSICleaner.clean_all("text\x1b[1;31;40mmore") == "textmore"


def test_clean_csi_with_private_parameters() -> None:
    """Test cleaning of CSI sequences with private parameters (? prefix)."""
    # Show cursor
    assert ANSICleaner.clean_all("text\x1b[?25hmore") == "textmore"
    # Hide cursor
    assert ANSICleaner.clean_all("text\x1b[?25lmore") == "textmore"
    # Bracketed paste mode
    assert ANSICleaner.clean_all("text\x1b[?2004hmore") == "textmore"
    # Synchronized output
    assert ANSICleaner.clean_all("text\x1b[?2026hmore") == "textmore"


def test_clean_osc_sequences() -> None:
    """Test cleaning of OSC (Operating System Command) sequences."""
    # Window title (terminated with BEL)
    assert ANSICleaner.clean_all("text\x1b]0;Title\x07more") == "textmore"
    # Window title (terminated with ST)
    assert ANSICleaner.clean_all("text\x1b]0;Title\x1b\\more") == "textmore"


def test_clean_complex_mixed_sequences() -> None:
    """Test cleaning of text with multiple different ANSI sequences."""
    text = "Do you want\x1b[1m\x1b[31m to\x1b[m\x1b[K create\x1b[?25h test.txt?"
    expected = "Do you want to create test.txt?"
    assert ANSICleaner.clean_all(text) == expected


def test_clean_permission_prompt_with_cursor_artifacts() -> None:
    """Test realistic permission prompt with cursor movement artifacts."""
    # Simulates what might happen when terminal redraws corrupt the text
    text = "Do you want t\x1b[1@o create test.txt?"
    expected = "Do you want to create test.txt?"
    assert ANSICleaner.clean_all(text) == expected


def test_clean_cursor_forward_creates_spaces() -> None:
    """Test that cursor forward sequences are converted to spaces.

    Claude CLI uses cursor forward (\x1b[1C) to create visual spacing
    without actual space characters. These must be converted to spaces
    to preserve readability.
    """
    # Single character forward
    text = "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cproceed?"
    expected = "Do you want to proceed?"
    assert ANSICleaner.clean_all(text) == expected

    # Multiple characters forward
    text = "Option\x1b[3CA"
    expected = "Option   A"  # 3 spaces
    assert ANSICleaner.clean_all(text) == expected

    # Real example from Claude permission prompts
    text = "Yes,\x1b[1Cand\x1b[1Calways\x1b[1Callow\x1b[1Caccess"
    expected = "Yes, and always allow access"
    assert ANSICleaner.clean_all(text) == expected


def test_clean_all_matches_individual_cleaners() -> None:
    """Verify that clean_all produces same results as sequential cleaning."""
    text = "text\x1b[1;31m\x1b]0;Title\x07\x1b[2K\x1b[?25hmore"

    # Individual cleaning
    result1 = text
    result1 = ANSICleaner.clean_csi_sequences(result1)
    result1 = ANSICleaner.clean_osc_sequences(result1)
    result1 = ANSICleaner.clean_bracketed_paste(result1)
    result1 = ANSICleaner.clean_cursor_visibility(result1)
    result1 = ANSICleaner.clean_synchronized_output(result1)

    # Single-pass cleaning
    result2 = ANSICleaner.clean_all(text)

    assert result1 == result2 == "textmore"
