"""Claude CLI binary discovery utilities."""

from pathlib import Path

from vicoa.utils import find_npm_cli


def find_claude_cli() -> str:
    """Find the Claude Code CLI binary across common install locations.

    Delegates to ``vicoa.utils.find_npm_cli`` for the shared npm/nvm/
    Volta/snap/brew search, with ``~/.claude/local/claude`` added as a
    Claude-specific override (the path used by Claude Code's native
    installer, not in any standard npm-global / system bin dir).

    The user's own install wins; the copy Vicoa installed itself
    (`vicoa.agent_install`) is the fallback.

    Raises ``FileNotFoundError`` when nothing matches — preserves the
    legacy contract callers rely on.
    """
    cli = find_npm_cli(
        "claude",
        extra_locations=[Path.home() / ".claude" / "local" / "claude"],
    )
    if cli:
        return cli
    from vicoa.agent_install import managed_cli_path

    managed = managed_cli_path("claude")
    if managed:
        return managed
    raise FileNotFoundError(
        "Claude Code not found. Install: https://code.claude.com/docs"
    )
