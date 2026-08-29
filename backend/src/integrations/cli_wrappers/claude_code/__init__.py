"""Claude Code Wrapper - Automatic version detection and wrapper selection.

This package provides a wrapper for the Claude CLI that enables bidirectional
communication with Vicoa servers. It automatically detects the installed Claude CLI
version and selects the appropriate wrapper implementation:

- Legacy wrapper (claude_wrapper_v2_0.py): For Claude CLI versions < 2.1.0
- Modular wrapper (wrapper.py): For Claude CLI versions >= 2.1.0

Version Selection:
- Automatically detects Claude CLI version using `claude --version`
- Selects appropriate wrapper based on detected version
- Defaults to modular wrapper if version detection fails

Usage:
    # Run via module:
    python -m integrations.cli_wrappers.claude_code

    # Or via vicoa CLI:
    vicoa
"""

# Version info
__version__ = "3.0.0-auto-detect"
__legacy_version__ = "2.0.0"  # For Claude CLI < 2.1.0
__modular_version__ = "3.0.0"  # For Claude CLI >= 2.1.0
