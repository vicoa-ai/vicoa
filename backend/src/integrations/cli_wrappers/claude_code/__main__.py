"""Entry point for running Claude Code wrapper as a module.

This allows the wrapper to be executed with:
    python -m integrations.cli_wrappers.claude_code

This entry point automatically detects the installed Claude CLI version and
uses the appropriate wrapper implementation.

Version Selection:
- Claude CLI < 2.1.0: Uses legacy wrapper (claude_wrapper_v2_0.py)
- Claude CLI >= 2.1.0: Uses new modular wrapper (wrapper.py)
- Detection is automatic based on `claude --version` output
"""

import sys
from .utils.version_detector import should_use_legacy_wrapper


def main():
    """Main entry point for the wrapper.

    Detects the appropriate wrapper based on Claude CLI version and
    delegates to that wrapper's main() function.
    """
    # from .utils.version_detector import get_version_string
    # detected_version = get_version_string()
    # wrapper_type = "legacy (v2.0)" if use_legacy else "modular (new)"

    # print(f"[Vicoa] Detected Claude CLI version: {detected_version}")
    # print(f"[Vicoa] Using {wrapper_type} wrapper")

    # Detect version and determine which wrapper to use
    use_legacy = should_use_legacy_wrapper()

    # Call the appropriate wrapper's main() function
    if use_legacy:
        from .claude_wrapper_v2_0 import main as legacy_main

        return legacy_main()
    else:
        from .wrapper import main as modular_main

        return modular_main()


if __name__ == "__main__":
    sys.exit(main())
