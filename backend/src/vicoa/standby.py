"""Standby ("prewarm") launch protocol for headless agent sessions.

A cold session start pays for the interpreter, the imports and the agent's own
engine bring-up before the agent can look at the prompt. None of that depends
on what the user types, so the daemon can launch the session while they are
still typing: ``vicoa headless --standby`` brings the engine up and then waits
for ONE JSON line on stdin before it does anything the user can see.

* ``{"prompt": "..."}`` (or ``{"prompt": null}``) adopts: register, attach and
  run, with that prompt as the first message.
* ``{"discard": true}``, end of file, garbage, or no line within
  ``STANDBY_TTL_SECONDS``: exit without ever registering, so no session row is
  created and nothing is left to clean up.

stdin is a pipe owned by the daemon that launched the standby. If the daemon
dies the pipe closes, the standby reads end of file and exits: an orphan cannot
outlive the only process that could adopt it. Once the line is read, fd 0 is
pointed at /dev/null so nothing later in the session (or a child it starts)
touches the pipe.

The go line may arrive before the engine is up; it waits in the pipe, so a
half-warm standby is still adopted rather than thrown away.

A runner opts in with a module-level ``SUPPORTS_ENGINE_STANDBY = True`` and
calls :func:`read_go` once its engine is up. ``vicoa headless`` refuses
``--standby`` for any other agent.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from typing import Any, Optional

#: Set by ``vicoa headless --standby`` for the runner it starts.
STANDBY_ENV = "VICOA_STANDBY"
STANDBY_TTL_ENV = "VICOA_STANDBY_TTL"
#: Backstop only: the daemon discards an unused standby long before this.
DEFAULT_STANDBY_TTL_SECONDS = 15 * 60.0


def standby_ttl_seconds() -> float:
    try:
        return float(os.environ.get(STANDBY_TTL_ENV, DEFAULT_STANDBY_TTL_SECONDS))
    except ValueError:
        return DEFAULT_STANDBY_TTL_SECONDS


def parse_go_line(line: str) -> Optional[dict[str, Any]]:
    """The go payload for one stdin line, or None to discard."""
    if not line.strip():
        return None
    try:
        payload = json.loads(line)
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("discard"):
        return None
    prompt = payload.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        return None
    return {"prompt": prompt}


def _detach_stdin() -> None:
    """Point fd 0 at /dev/null once the go line is in."""
    try:
        devnull = os.open(os.devnull, os.O_RDONLY)
        try:
            os.dup2(devnull, 0)
        finally:
            os.close(devnull)
    except OSError:
        pass


def _read_line_blocking(timeout: float) -> Optional[str]:
    """One line from stdin, or None on end of file, error or timeout."""
    result: list[Optional[str]] = [None]
    done = threading.Event()

    def read() -> None:
        try:
            line = sys.stdin.readline()
            result[0] = line if line else None
        except Exception:  # noqa: BLE001 - a closed/invalid stdin is a discard
            result[0] = None
        finally:
            done.set()

    # Daemon thread: on timeout the process exits with the read still pending.
    threading.Thread(target=read, name="vicoa-standby-go", daemon=True).start()
    if not done.wait(timeout):
        return None
    return result[0]


def read_go(timeout: Optional[float] = None) -> Optional[dict[str, Any]]:
    """Block for the go line. Returns ``{"prompt": str | None}`` or None to discard."""
    line = _read_line_blocking(standby_ttl_seconds() if timeout is None else timeout)
    payload = parse_go_line(line) if line is not None else None
    _detach_stdin()
    return payload


async def read_go_async(timeout: Optional[float] = None) -> Optional[dict[str, Any]]:
    return await asyncio.to_thread(read_go, timeout)


def standby_requested() -> bool:
    return os.environ.get(STANDBY_ENV) == "1"
