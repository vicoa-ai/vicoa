"""Smoke-test the PyInstaller-built vicoa binary's frozen-mode imports.

Runs each subcommand that dispatches through `run_python_module` with a fake
key and short timeout. We do not care about exit codes — the test passes as
long as no Python traceback appears on stdout/stderr. Catches the class of
bug where a transitive dependency upgrade breaks the bundled binary's import
graph (e.g. fastmcp/pydantic mismatch, missing copy_metadata).

Usage: python scripts/smoke_test_binary.py path/to/vicoa[.exe]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# (label, args, timeout_seconds)
# Each entry exercises a distinct frozen-mode import path; fake credentials
# are fine because we only need the imports to succeed before any auth
# happens. Network attempts are aborted by the timeout.
SUBCOMMAND_TESTS: list[tuple[str, list[str], int]] = [
    ("--version", ["--version"], 5),
    ("--help", ["--help"], 5),
    (
        "mcp",
        [
            "mcp",
            "--api-key",
            "smoke-test",
            "--permission-tool",
            "--disable-tools",
            "--agent-instance-id",
            "smoke-test",
        ],
        5,
    ),
    (
        "headless",
        [
            "headless",
            "--api-key",
            "smoke-test",
            "--base-url",
            "http://127.0.0.1:1",
            "--prompt",
            "smoke",
        ],
        5,
    ),
]

FAILURE_MARKERS = ("Traceback", "Failed to execute script")


def run_one(binary: Path, label: str, args: list[str], timeout: int) -> str | None:
    """Return None on pass, or a captured-output snippet on fail."""
    try:
        result = subprocess.run(
            [str(binary), *args],
            input=b"",
            capture_output=True,
            timeout=timeout,
        )
        output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        output = (stdout + stderr).decode("utf-8", errors="replace")

    if any(marker in output for marker in FAILURE_MARKERS):
        return output[-2000:]
    return None


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: smoke_test_binary.py path/to/vicoa", file=sys.stderr)
        return 2

    binary = Path(sys.argv[1]).resolve()
    if not binary.exists():
        print(f"binary not found: {binary}", file=sys.stderr)
        return 2

    failures: list[str] = []
    for label, args, timeout in SUBCOMMAND_TESTS:
        snippet = run_one(binary, label, args, timeout)
        if snippet is None:
            print(f"PASS  vicoa {label}")
        else:
            print(f"FAIL  vicoa {label}")
            print("---")
            print(snippet)
            print("---")
            failures.append(label)

    if failures:
        print(f"\n{len(failures)} smoke test(s) failed: {', '.join(failures)}")
        return 1
    print("\nAll smoke tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
