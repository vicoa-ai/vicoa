"""Tiny scripted stand-in for ``codex app-server`` used by the subprocess
smoke test in ``test_codex_subprocess.py``.

Reads JSON-RPC NDJSON from stdin, replies to ``initialize`` with a fixed
``{"ok": true}`` result, and keeps reading until stdin EOF. Mirrors the
production shutdown path: parent closes stdin, child exits 0. Does NOT
implement the full schema — just enough to prove the transport composes
correctly with real OS pipes.

Leading underscore in the filename keeps pytest from trying to collect it
(``python_files = ["test_*.py"]`` in pyproject.toml).
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    while True:
        line = sys.stdin.readline()
        if not line:
            # EOF from parent — clean exit.
            return 0
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        msg_id = msg.get("id")
        if method == "initialize" and msg_id is not None:
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"ok": True},
            }
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            # Keep reading; production codex stays up until stdin closes.


if __name__ == "__main__":
    sys.exit(main())
