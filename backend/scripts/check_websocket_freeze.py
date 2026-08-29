#!/usr/bin/env python3
"""CI enforcement of the WebSocket migration freeze rules (plan §2.7).

Two checks, both backstops — not proofs (see plan §2.7 "Lint is a backstop"):

1. db.commit() ceiling. Every `.commit()` in the production write-path dirs
   must stay at or below a checked-in per-file baseline. A new commit site in
   an un-baselined file, or a count above baseline, fails CI. The baseline
   shrinks phase-by-phase as write paths move onto `in_tx`; reaching empty is
   the "all write paths on in_tx" signal.

2. Trigger / pg_notify freeze. No new Alembic migration may introduce a
   `CREATE TRIGGER` or a `pg_notify` call. Only the migrations that already
   had them when the freeze began are grandfathered.

Exit code 0 = clean, 1 = violation.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = Path(__file__).with_name("websocket_freeze_baseline.json")

COMMIT_DIRS = ("src/backend/api", "src/servers/api")
MIGRATIONS_DIR = "src/shared/alembic/versions"

_COMMIT_RE = re.compile(r"\.commit\s*\(\s*\)")
# The existing triggers emit via `EXECUTE format('NOTIFY %I, ...')`, not the
# pg_notify() function — so the freeze must catch the bare SQL NOTIFY keyword
# too. `\bNOTIFY\b` does not match the `notify` inside `pg_notify` or an
# identifier like `notify_enabled` (the trailing `_`/`(` keeps the word intact).
_TRIGGER_RE = re.compile(r"CREATE\s+TRIGGER|pg_notify|\bNOTIFY\b", re.IGNORECASE)


def _count_commits(path: Path) -> int:
    """Count `.commit()` calls in a file, ignoring those inside line comments."""
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        for match in _COMMIT_RE.finditer(line):
            hash_pos = line.find("#")
            if hash_pos == -1 or hash_pos > match.start():
                count += 1
    return count


def check_commit_baseline(baseline: dict[str, int]) -> list[str]:
    errors: list[str] = []
    for rel_dir in COMMIT_DIRS:
        for path in sorted((REPO_ROOT / rel_dir).rglob("*.py")):
            count = _count_commits(path)
            if count == 0:
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            allowed = baseline.get(rel)
            if allowed is None:
                errors.append(
                    f"{rel}: {count} .commit() call(s) but no freeze-baseline "
                    f"entry. New production write paths must use in_tx() + "
                    f"after_commit() instead of a bare commit (plan §2.7)."
                )
            elif count > allowed:
                errors.append(
                    f"{rel}: {count} .commit() call(s) exceeds baseline of "
                    f"{allowed}. New write paths must use in_tx() (plan §2.7)."
                )
    return errors


def check_trigger_freeze(grandfathered: set[str]) -> list[str]:
    errors: list[str] = []
    for path in sorted((REPO_ROOT / MIGRATIONS_DIR).glob("*.py")):
        if path.name in grandfathered:
            continue
        if _TRIGGER_RE.search(path.read_text(encoding="utf-8")):
            errors.append(
                f"{path.relative_to(REPO_ROOT).as_posix()}: introduces a "
                f"CREATE TRIGGER or pg_notify. New realtime events must use "
                f"the ConnectionManager, not PG triggers (plan §2.7 freeze)."
            )
    return errors


def main() -> int:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    errors = check_commit_baseline(baseline["commit_baseline"])
    errors += check_trigger_freeze(set(baseline["grandfathered_trigger_migrations"]))

    if errors:
        print("WebSocket freeze check FAILED:\n")
        for error in errors:
            print(f"  - {error}")
        print(
            "\nIf a phase intentionally migrated a write path, decrement or "
            "remove its entry in websocket_freeze_baseline.json."
        )
        return 1

    print("WebSocket freeze check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
