#!/usr/bin/env python3
"""Flip the debug-mode backend in vicoa_api_config.dart between the hosted
backend and a local dev stack — the same edit as commenting/uncommenting the
two `return` lines by hand, scripted so a fresh worktree can start on local.

  scripts/backend_toggle.py local   # debug builds -> http://localhost:8000 + ws://localhost:8080/ws
  scripts/backend_toggle.py prod    # debug builds -> production (the committed state)

Only the `if (kDebugMode)` blocks change; release builds always use production.
Hot-restart (R) after flipping — no full `flutter run` needed.
"""
import re
import sys
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "lib/custom_code/actions/vicoa_api_config.dart"
LOCAL = ["return 'http://$host:8000';", "return 'ws://$host:8080/ws';"]
PROD = ["return 'https://api.vicoa.ai';", "return 'wss://agents.vicoa.ai/ws';"]
INDENT = "    "  # the debug-block lines; the release `return`s sit at two spaces


def flip(text: str, on: list[str], off: list[str]) -> str:
    for line in on:
        text = re.sub(rf"^{INDENT}// {re.escape(line)}$", f"{INDENT}{line}", text, flags=re.M)
    for line in off:
        text = re.sub(rf"^{INDENT}{re.escape(line)}$", f"{INDENT}// {line}", text, flags=re.M)
    for line in on:
        if f"\n{INDENT}{line}\n" not in text:
            sys.exit(f"backend_toggle: expected line not found in {FILE.name}: {line}")
    return text


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) == 2 else ""
    if mode not in ("local", "prod"):
        sys.exit(__doc__)
    src = FILE.read_text()
    out = flip(src, LOCAL, PROD) if mode == "local" else flip(src, PROD, LOCAL)
    if out == src:
        print(f"backend_toggle: debug backend already {mode}")
        return
    FILE.write_text(out)
    print(f"backend_toggle: debug backend -> {mode} ({FILE.relative_to(Path.cwd()) if FILE.is_relative_to(Path.cwd()) else FILE})")


if __name__ == "__main__":
    main()
