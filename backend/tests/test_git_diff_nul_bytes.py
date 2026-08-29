"""A NUL byte in a git diff must not destroy the agent's message.

Postgres text columns cannot hold ``\\x00``. psycopg2 raises ``ValueError`` at
flush, the agent router turns that into a 400, and the whole transaction rolls
back — including the ``messages`` row the diff was riding with.

The CLI wrappers no longer attach a git diff to outbound messages (clients
fetch diffs on demand via the machine-daemon git RPCs), but the server still
accepts and stores ``git_diff`` for older wrappers in the field and any SDK
caller. ``sanitize_git_diff`` is that storage boundary: it strips the NUL so
the message survives instead of taking the whole transaction down with it.
"""

from __future__ import annotations

from shared.database.utils import sanitize_git_diff

_NUL = "\x00"


def _valid_diff_with(payload: str) -> str:
    """A well-formed new-file diff whose body contains ``payload``."""
    return (
        "diff --git a/blob.bin b/blob.bin\n"
        "new file mode 100644\n"
        "index 0000000..0000000\n"
        "--- /dev/null\n"
        "+++ b/blob.bin\n"
        "@@ -0,0 +1 @@\n"
        f"+{payload}\n"
    )


# --------------------------------------------------------------------------
# Storage boundary — protects every wrapper and every client
# --------------------------------------------------------------------------


def test_sanitizer_strips_nul_bytes():
    out = sanitize_git_diff(_valid_diff_with(f"bin{_NUL}data"))

    assert out is not None, "a diff with NUL must still be stored, not dropped"
    assert _NUL not in out


def test_sanitizer_keeps_the_surrounding_content():
    """Strip the NUL, don't discard the diff — the diff is still useful."""
    out = sanitize_git_diff(_valid_diff_with(f"before{_NUL}after"))

    assert out is not None
    assert "beforeafter" in out
    assert "diff --git a/blob.bin b/blob.bin" in out


def test_sanitizer_still_rejects_a_non_diff():
    """The NUL strip must not accidentally make garbage look valid."""
    assert sanitize_git_diff(f"not a diff{_NUL}") is None


def test_sanitizer_still_passes_a_clean_diff_through():
    clean = _valid_diff_with("hello")

    assert sanitize_git_diff(clean) == clean.strip()
