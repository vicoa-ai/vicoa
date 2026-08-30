"""Fetch Claude's plan usage (5-hour / weekly rate-limit windows) out-of-band.

The SDK's ``RateLimitEvent`` only fires on a status *transition*, so a session
comfortably under its limits never reports any window. To show Session/Weekly
usage the way Codex does, we read the Claude Code OAuth token the running CLI
already maintains and call Anthropic's usage endpoint for a full snapshot.

Strictly best-effort and read-only: any missing creds / non-OAuth (API-key)
setup / network error / non-200 yields ``None`` so the caller simply leaves the
limits section hidden. We do NOT refresh or write back tokens — the live Claude
session keeps ``~/.claude/.credentials.json`` fresh while it runs.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp

_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
_OAUTH_BETA_HEADER = "oauth-2025-04-20"
# macOS Keychain entry the Claude Code CLI writes when the file is absent.
_KEYCHAIN_SERVICE = "Claude Code-credentials"


def _credentials_path() -> Path:
    base = os.environ.get("CLAUDE_HOME")
    root = Path(base) if base else Path.home() / ".claude"
    return root / ".credentials.json"


def _read_credentials_raw() -> Optional[str]:
    """Return the raw credentials JSON from the file, else the macOS Keychain."""
    try:
        return _credentials_path().read_text()
    except OSError:
        pass
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", _KEYCHAIN_SERVICE, "-w"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except (OSError, subprocess.SubprocessError):
            return None
    return None


def read_claude_oauth_token() -> Optional[str]:
    """Return the Claude Code OAuth access token, or ``None`` when unavailable.

    ``None`` covers the API-key case too: a pay-as-you-go setup has no
    ``claudeAiOauth`` block (and no rate-limit windows to show).
    """
    raw = _read_credentials_raw()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    oauth = data.get("claudeAiOauth") if isinstance(data, dict) else None
    if isinstance(oauth, dict):
        token = oauth.get("accessToken")
        if isinstance(token, str) and token:
            return token
    return None


async def fetch_claude_usage(
    token: str, *, timeout: float = 10.0
) -> Optional[Dict[str, Any]]:
    """GET the OAuth usage snapshot. Returns the parsed JSON, or ``None`` on any
    error / non-200 (expired token, offline, etc.)."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "anthropic-beta": _OAUTH_BETA_HEADER,
    }
    try:
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.get(_USAGE_URL, headers=headers) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return None
