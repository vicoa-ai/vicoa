"""Detect when the persisted daemon identity belongs to a different API key
than the one the CLI is currently running with — a different user signed in,
or the same user rotated their key — so the old daemon can be stopped and the
state cleared before a fresh registration takes its place.

The decision (``decide_identity_action``) is split from the side effects
(stop daemon / clear entry / stamp fingerprint) so the policy is unit-testable
without mocking the daemon lifecycle. Callers in ``machine_daemon`` execute
the verdict.
"""

from __future__ import annotations

import enum
import hashlib
import os
from pathlib import Path
from typing import Optional

import requests
from requests.exceptions import RequestException

from vicoa.machine_state import STATE_PATH, read_daemon_entry


def api_key_fingerprint(api_key: str) -> str:
    """Stable SHA256 hex of the API key.

    Matches the digest the backend already uses for API-key storage, so no
    weaker secret material leaves the process. Compared locally to detect
    that the persisted ``machine_id`` was registered under a different key
    without a backend round trip.
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def verify_machine_ownership(
    api_key: str, base_url: str, machine_id: str
) -> Optional[bool]:
    """Return ``True`` when ``api_key`` owns ``machine_id`` on the backend,
    ``False`` when it does not, ``None`` on transient network failure.

    Used exactly once per install — when a daemon_state entry carried over
    from a pre-fingerprint version has a ``machine_id`` but no
    ``api_key_fingerprint``. After the first successful run stamps the
    fingerprint we take the cheap local-only comparison path forever after.

    Heartbeat is the cheapest mutating endpoint the daemon already calls, so
    re-using it keeps the verification surface small. A 200 means the
    machine is owned by the current key; any other status means it isn't.
    """
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/api/v1/machines/{machine_id}/heartbeat",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"metadata": {"last_pid": os.getpid()}},
            timeout=5,
        )
    except RequestException:
        return None
    return response.status_code == 200


class IdentityAction(enum.Enum):
    """Verdict for the caller to execute. Keeping the decision pure-ish lets
    ``decide_identity_action`` be tested without patching subprocess kills."""

    NONE = "none"  # state matches the current key (or nothing to verify)
    RESET = "reset"  # mismatch or backend-says-not-owned: stop daemon + clear entry
    STAMP_FINGERPRINT = "stamp_fingerprint"  # legacy verified-owned: stamp fp + adopt


def decide_identity_action(
    api_key: str,
    base_url: str,
    state_path: Path = STATE_PATH,
) -> IdentityAction:
    """Decide what to do with ``base_url``'s persisted daemon entry given the
    current ``api_key``. Reads the state file and may issue one heartbeat
    ping; never kills processes or rewrites state — the caller does that.

    Branches:

    - ``stored_fp`` present + matches current → ``NONE``
    - ``stored_fp`` present + differs → ``RESET``
    - ``stored_fp`` absent + no ``machine_id`` → ``NONE`` (first run; spawn
      path handles it)
    - ``stored_fp`` absent + ``machine_id`` present (legacy upgrade path):
      heartbeat ping → 200 ⇒ ``STAMP_FINGERPRINT``; 4xx ⇒ ``RESET``; network
      failure ⇒ ``NONE`` (safe-degrade; next invocation retries)
    """
    entry = read_daemon_entry(base_url, state_path)
    stored_fp = entry.get("api_key_fingerprint")
    current_fp = api_key_fingerprint(api_key)

    if stored_fp:
        return IdentityAction.NONE if stored_fp == current_fp else IdentityAction.RESET

    machine_id = entry.get("machine_id")
    if not machine_id:
        return IdentityAction.NONE

    owned = verify_machine_ownership(api_key, base_url, machine_id)
    if owned is True:
        return IdentityAction.STAMP_FINGERPRINT
    if owned is False:
        return IdentityAction.RESET
    return IdentityAction.NONE
