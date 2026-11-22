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
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp

_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
_OAUTH_BETA_HEADER = "oauth-2025-04-20"
# macOS Keychain entry the Claude Code CLI writes when the file is absent.
_KEYCHAIN_SERVICE = "Claude Code-credentials"
# Claude Code files that entry under an account named after the user, and
# falls back to this name when the user name has other characters.
_KEYCHAIN_ACCOUNT_RE = re.compile(r"[A-Za-z0-9._-]+")
_KEYCHAIN_FALLBACK_ACCOUNT = "claude-code-user"


def _credentials_path() -> Path:
    base = os.environ.get("CLAUDE_HOME")
    root = Path(base) if base else Path.home() / ".claude"
    return root / ".credentials.json"


def _read_credentials_file() -> Optional[str]:
    try:
        return _credentials_path().read_text()
    except OSError:
        return None


def _keychain_account() -> str:
    """The Keychain account Claude Code reads and writes its login under:
    ``$USER``, else the login name, else a fixed fallback."""
    name = os.environ.get("USER") or ""
    if not name:
        try:
            import pwd  # POSIX only; this path only runs on macOS.

            name = pwd.getpwuid(os.getuid()).pw_name
        except (ImportError, KeyError, OSError):
            name = ""
    if not _KEYCHAIN_ACCOUNT_RE.fullmatch(name):
        return _KEYCHAIN_FALLBACK_ACCOUNT
    return name


def _read_keychain(account: Optional[str]) -> Optional[str]:
    """Raw JSON of the ``Claude Code-credentials`` Keychain item, or ``None``.

    With no ``account`` the lookup matches on service alone and returns
    whichever item with that service the Keychain lists first.
    """
    command = ["security", "find-generic-password", "-s", _KEYCHAIN_SERVICE, "-w"]
    if account:
        command[2:2] = ["-a", account]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout
    return None


def _token_from_credentials(raw: Optional[str]) -> Optional[str]:
    """``claudeAiOauth.accessToken`` out of a credentials JSON blob."""
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


def read_claude_oauth_token() -> Optional[str]:
    """Return the Claude Code OAuth access token, or ``None`` when unavailable.

    ``None`` covers the API-key case too: a pay-as-you-go setup has no
    ``claudeAiOauth`` block (and no rate-limit windows to show).

    On macOS the Keychain is asked for the item under the user's account
    first. More than one item can carry the service name (one holding only
    MCP server tokens, filed under another account, has been seen), and a
    lookup by service alone may return that one, which has no Claude login.
    The service-only lookup stays as a fallback for an item filed under an
    account name this process does not derive.
    """
    token = _token_from_credentials(_read_credentials_file())
    if token or sys.platform != "darwin":
        return token
    for account in (_keychain_account(), None):
        token = _token_from_credentials(_read_keychain(account))
        if token:
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
