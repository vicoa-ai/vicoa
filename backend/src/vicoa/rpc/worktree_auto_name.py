"""Names the server generates for a new worktree from the spawn's prompt.

The daemon side of `protocol.worktree_naming`. The server pushes a
`worktree-name` frame while `git worktree add` runs; the receive loop drops it
into an `AutoNameInbox`, and once the checkout exists `spawn_session_rpc`
waits there until the spawn's naming budget runs out. A name that arrives in
time renames the worktree before the agent starts in it: nothing has run in
the folder yet, so the name is still picked at creation and branch, folder and
session title all agree. A late one is dropped and the random name stays.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# How long after the spawn request arrives the daemon will still take a name.
# The checkout counts against it, so it is also the most a new worktree
# session's start can slow down: about this much on a tiny repo, less on a big
# one (vicoa's ~0.5s checkout leaves ~0.5s), nothing once a checkout outlasts
# it. Sized to the naming call (p50 ~0.55s, p90 ~1.05s, 2026-11-01); measuring
# from the checkout instead let a tiny repo's name miss most of the time.
AUTO_NAME_BUDGET_SECONDS = 1.0

# A frame no spawn claims (it arrived after its spawn gave up) is dropped after
# this long.
_UNCLAIMED_TTL_SECONDS = 60.0

_MAX_BRANCH_WORDS = 5
_MAX_BRANCH_CHARS = 48
_MAX_TITLE_CHARS = 120


@dataclass(frozen=True)
class AutoNames:
    """A cleaned-up naming answer; either part may be missing."""

    branch: str | None
    title: str | None


def branch_slug(raw: object) -> str | None:
    """A model's branch suggestion as a kebab-case slug, or None.

    Lowercase ASCII words and digits only: the slug is also the worktree's
    middle folder, so a `/` (which git allows) would nest a directory. Capped
    at a few words; None when nothing usable is left or it has no letter.
    """
    if not isinstance(raw, str):
        return None
    words = re.findall(r"[a-z0-9]+", raw.lower())[:_MAX_BRANCH_WORDS]
    while len(words) > 1 and len("-".join(words)) > _MAX_BRANCH_CHARS:
        words.pop()
    slug = "-".join(words)
    if not slug or len(slug) > _MAX_BRANCH_CHARS or not re.search(r"[a-z]", slug):
        return None
    return slug


def session_title(raw: object) -> str | None:
    """A model's title on one line, trimmed; None when empty."""
    if not isinstance(raw, str):
        return None
    title = " ".join(raw.split())[:_MAX_TITLE_CHARS].strip()
    return title or None


class AutoNameInbox:
    """Hands `worktree-name` frames from the receive loop to waiting spawns.

    Thread-safe: `deliver` runs on the WebSocket receive loop, `wait` on an RPC
    worker. A frame may arrive before its spawn starts waiting, so it is kept
    until claimed or stale.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._cond = threading.Condition()
        self._names: dict[str, tuple[float, AutoNames]] = {}

    def deliver(self, frame: dict[str, Any]) -> None:
        token = frame.get("token")
        if not isinstance(token, str) or not token:
            return
        names = AutoNames(
            branch=branch_slug(frame.get("branch")),
            title=session_title(frame.get("title")),
        )
        with self._cond:
            now = self._clock()
            for stale in [
                t
                for t, (at, _) in self._names.items()
                if now - at > _UNCLAIMED_TTL_SECONDS
            ]:
                del self._names[stale]
            self._names[token] = (now, names)
            self._cond.notify_all()

    def wait(self, token: str, timeout: float) -> AutoNames | None:
        """The names for `token`, waiting up to `timeout` seconds; None if
        they did not arrive in time."""
        deadline = self._clock() + timeout
        with self._cond:
            while token not in self._names:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    return None
                self._cond.wait(remaining)
            return self._names.pop(token)[1]
