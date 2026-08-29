"""Claude CLI version detection utilities.

This module provides utilities for detecting the installed Claude CLI version
and determining which wrapper implementation to use.
"""

import re
import subprocess
from typing import Optional, Tuple

from .cli_finder import find_claude_cli


def get_claude_version() -> Optional[Tuple[int, int, int]]:
    """Get the installed Claude CLI version.

    Returns:
        Tuple of (major, minor, patch) version numbers, or None if detection fails

    Examples:
        >>> get_claude_version()
        (2, 1, 0)  # For Claude CLI v2.1.0
    """
    try:
        # Find Claude CLI
        claude_path = find_claude_cli()

        # Run claude --version
        result = subprocess.run(
            [claude_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            return None

        # Parse version from output
        # Expected format: "claude version 2.1.0" or similar
        version_text = result.stdout.strip()

        # Try to extract version number using regex
        # Matches patterns like "2.1.0", "v2.1.0", "version 2.1.0"
        match = re.search(r"(\d+)\.(\d+)\.(\d+)", version_text)

        if match:
            major = int(match.group(1))
            minor = int(match.group(2))
            patch = int(match.group(3))
            return (major, minor, patch)

        return None

    except Exception:
        # If anything fails (binary not found, subprocess error, etc), return None
        return None


def should_use_legacy_wrapper() -> bool:
    """Determine if the legacy wrapper should be used based on Claude CLI version.

    The legacy wrapper (v2_0.py) should be used for Claude CLI versions < 2.1.0.
    The new modular wrapper should be used for Claude CLI versions >= 2.1.0.

    Returns:
        True if legacy wrapper should be used, False for new modular wrapper

    Fallback behavior:
        - If version detection fails, defaults to new wrapper (False)
    """
    # Detect version
    version = get_claude_version()

    if version is None:
        # Default to new wrapper if detection fails
        return False

    major, minor, patch = version

    # Use legacy wrapper for versions < 2.1.0
    if major < 2:
        return True
    elif major == 2 and minor < 1:
        return True
    else:
        return False


def get_version_string() -> str:
    """Get a human-readable version string.

    Returns:
        Version string like "2.1.0" or "unknown"
    """
    version = get_claude_version()
    if version:
        return f"{version[0]}.{version[1]}.{version[2]}"
    return "unknown"
