"""Database utility functions."""

import json
import re
from typing import Any, Optional


def is_valid_git_diff(diff: Optional[str]) -> bool:
    """Validate if a string is a valid git diff.

    Checks for:
    - Basic git diff format markers
    - Proper structure
    - Not just random text

    Args:
        diff: The string to validate as a git diff

    Returns:
        True if valid git diff format, False otherwise
    """
    if not diff or not isinstance(diff, str):
        return False

    # Check for essential git diff patterns
    has_diff_header = re.search(r"^diff --git", diff, re.MULTILINE) is not None
    has_index_line = (
        re.search(r"^index [a-f0-9]+\.\.[a-f0-9]+", diff, re.MULTILINE) is not None
    )
    has_file_markers = (
        re.search(r"^--- ", diff, re.MULTILINE) is not None
        and re.search(r"^\+\+\+ ", diff, re.MULTILINE) is not None
    )
    has_hunk_header = re.search(r"^@@[ \-\+,0-9]+@@", diff, re.MULTILINE) is not None

    # For new files (untracked), we might not have index lines
    has_new_file = re.search(r"^new file mode", diff, re.MULTILINE) is not None

    # A valid diff should have:
    # 1. diff --git header
    # 2. Either (index line) OR (new file mode)
    # 3. File markers (--- and +++)
    # 4. At least one hunk header (@@)

    is_valid = (
        has_diff_header
        and (has_index_line or has_new_file)
        and has_file_markers
        and has_hunk_header
    )

    # Additional check: should have some actual diff content (lines starting with +, -, or space)
    has_diff_content = re.search(r"^[ \+\-]", diff, re.MULTILINE) is not None

    return is_valid and has_diff_content


def sanitize_git_diff(diff: Optional[str]) -> Optional[str]:
    """Sanitize and validate a git diff for storage.

    Args:
        diff: The git diff string to sanitize (None means no update needed)

    Returns:
        - Original diff string if valid
        - Empty string if diff is empty (clears the git diff)
        - None if diff is invalid or not provided
    """
    if diff is None:
        return None

    # Postgres text columns cannot hold NUL. psycopg2 raises ValueError at
    # flush, the router turns that into a 400, and the *whole* transaction
    # rolls back — taking the agent's message row with it. A binary file in an
    # untracked-file diff therefore silently ate the agent's reply (U+0000 is
    # valid UTF-8, so the reader's errors="ignore" passes it straight through).
    # Strip at the storage boundary so no caller can reintroduce it.
    diff = diff.replace("\x00", "")

    # Strip excessive whitespace
    diff = diff.strip()

    # If empty after stripping, return empty string (valid case)
    if not diff:
        return ""

    # Check if it's a valid git diff
    if not is_valid_git_diff(diff):
        return None

    # Limit size to prevent abuse (1MB)
    max_size = 1024 * 1024  # 1MB
    if len(diff) > max_size:
        # Truncate and add marker
        diff = diff[: max_size - 100] + "\n\n... [TRUNCATED - DIFF TOO LARGE] ..."

    return diff


def _strip_nul(value: Any) -> Any:
    """Copy of a JSON value with U+0000 removed from every string and key."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {_strip_nul(k): _strip_nul(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_strip_nul(v) for v in value]
    return value


def json_dumps_without_nul(value: Any) -> str:
    """The engine's ``json_serializer``: ``json.dumps`` minus U+0000.

    Postgres jsonb rejects ``\\u0000``, so one NUL in a client-supplied
    string failed the whole write (a binary SKILL.md made ``/commands/sync``
    500 every time). Stripping here covers every JSON/JSONB column, from any
    caller or client version, the same way `sanitize_git_diff` does for the
    diff column.
    """
    text = json.dumps(value)
    # json.dumps writes U+0000 as the escape `\u0000`, so if that text is
    # absent there is no NUL. A hit can also be a literal backslash followed by
    # "u0000", which the slow path below leaves intact.
    if "\\u0000" not in text:
        return text
    return json.dumps(_strip_nul(value))
