"""On-demand Claude plan-usage fetch for the `fetch-claude-usage` RPC.

The web fetches the account's Session/Weekly rate-limit windows when the user
actually looks at them (usage popover open, new-session page) instead of only
seeing whatever a wrapper stamped at its last end-of-turn. The daemon is the
right place to serve this: it runs on the machine that holds the Claude Code
OAuth credential, and it answers even when no session is running yet.

Reuses the headless wrapper's credential discovery and window mapping so the
two paths can't drift; the HTTP GET itself is done synchronously with
``requests`` (already a daemon dependency) because RPC handlers run in worker
threads, not an event loop.

Results — including failures — are cached for a short TTL: popover opens can
come in bursts, and on macOS a failed Keychain read may pop a GUI
authorization prompt, so re-probing on every click would be hostile.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

import requests

_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
_OAUTH_BETA_HEADER = "oauth-2025-04-20"
_TIMEOUT_SECONDS = 10.0
_CACHE_TTL_SECONDS = 30.0

_cache_lock = threading.Lock()
_cached_result: Optional[Dict[str, Any]] = None
_cached_at: float = 0.0


def _fetch_snapshot() -> Dict[str, Any]:
    # Lazy imports keep daemon startup unchanged; ``usage`` is pure stdlib and
    # ``claude_usage_fetcher`` only costs its own module imports here.
    from integrations.headless.claude_usage_fetcher import read_claude_oauth_token
    from integrations.headless.usage import claude_limits_from_oauth

    token = read_claude_oauth_token()
    if not token:
        # Covers API-key setups (no windows to show) and unreadable
        # credentials (missing file, denied Keychain access).
        return {"error": "no_oauth_token"}

    try:
        response = requests.get(
            _USAGE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "anthropic-beta": _OAUTH_BETA_HEADER,
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return {"error": "fetch_failed"}

    if response.status_code != 200:
        # 401 here usually means the token expired and no live Claude session
        # has refreshed it yet — surfaced as-is so the client can tell.
        return {"error": f"http_{response.status_code}"}

    try:
        payload = response.json()
    except ValueError:
        return {"error": "invalid_response"}

    limits = claude_limits_from_oauth(payload)
    if not limits:
        return {"error": "no_windows"}
    return {"limits": limits}


def fetch_claude_usage(**_params: Any) -> Dict[str, Any]:
    """Serve the `fetch-claude-usage` RPC: `{limits: {windows: [...]}}` or `{error}`."""
    global _cached_result, _cached_at
    with _cache_lock:
        if (
            _cached_result is not None
            and time.monotonic() - _cached_at < _CACHE_TTL_SECONDS
        ):
            return _cached_result

    result = _fetch_snapshot()

    with _cache_lock:
        _cached_result = result
        _cached_at = time.monotonic()
    return result
