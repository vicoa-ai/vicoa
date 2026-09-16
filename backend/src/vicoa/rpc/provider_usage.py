"""On-demand provider plan-usage fetch for the `fetch-provider-usage` RPC.

The web/mobile fetch an account's rate-limit windows when the user actually
looks at them (usage popover open, new-session page) instead of only seeing
whatever a wrapper stamped at its last end-of-turn. The daemon is the right
place to serve this: it runs on the machine that holds each CLI's credential,
and it answers even when no session is running yet.

One registry, three providers:

``claude``   Claude Code OAuth token (``~/.claude/.credentials.json`` or the
             macOS Keychain) → ``api.anthropic.com/api/oauth/usage``.
``codex``    ``$CODEX_HOME/auth.json`` ``tokens.access_token`` + ``account_id``
             → ``chatgpt.com/backend-api/wham/usage``.
``copilot``  ``COPILOT_TOKEN`` / ``GITHUB_TOKEN`` / ``GITHUB_PAT`` env, else
             ``gh auth token`` (on macOS ``gh`` keeps it in the Keychain, so
             ``hosts.yml`` has no ``oauth_token``), else ``hosts.yml`` →
             ``api.github.com/copilot_internal/user``.

Every fetcher returns the same shape the wrappers stamp on
``instance_metadata.usage`` — ``{limits: {windows: [{id,label,used_pct,
resets_at}]}}`` — or ``{error: <reason>}``, so the clients' usage indicator
renders any of them unchanged. Tokens are only ever read; the CLIs own their
own refresh.

The HTTP GET is synchronous ``requests`` (already a daemon dependency)
because RPC handlers run in worker threads, not an event loop.

Results — including failures — are cached per provider for a short TTL:
popover opens can come in bursts, and on macOS a failed Keychain read may pop
a GUI authorization prompt, so re-probing on every click would be hostile.

`fetch-claude-usage` (the pre-registry RPC name) routes here too so a web or
mobile build that predates `fetch-provider-usage` keeps working.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import requests

_TIMEOUT_SECONDS = 10.0
_CACHE_TTL_SECONDS = 30.0

_CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
_CLAUDE_OAUTH_BETA_HEADER = "oauth-2025-04-20"

_CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
# The endpoint is the ChatGPT web app's own; a bare python-requests UA gets a
# bot-wall HTML page instead of JSON.
_CODEX_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_COPILOT_USAGE_URL = "https://api.github.com/copilot_internal/user"
# Same editor headers the Copilot Chat extension sends; the endpoint 404s
# without them.
_COPILOT_HEADERS = {
    "Editor-Version": "vscode/1.96.2",
    "Editor-Plugin-Version": "copilot-chat/0.26.7",
    "User-Agent": "GitHubCopilotChat/0.26.7",
    "X-Github-Api-Version": "2025-04-01",
    "Accept": "application/json",
}
_COPILOT_TOKEN_ENV = ("COPILOT_TOKEN", "GITHUB_TOKEN", "GITHUB_PAT")
# `gh` is a Homebrew/apt binary the daemon's launchd/systemd PATH may lack.
_GH_FALLBACK_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin")

Fetcher = Callable[[], Dict[str, Any]]

_cache_lock = threading.Lock()
_cache: Dict[str, tuple[Dict[str, Any], float]] = {}


# ---------------------------------------------------------------------------
# Shared HTTP
# ---------------------------------------------------------------------------


def _get_json(
    url: str, headers: Dict[str, str], parse: Callable[[Any], Optional[dict]]
) -> Dict[str, Any]:
    """GET → parse → ``{limits}``; every failure mode is an ``{error}`` with a
    stable reason string the client can log (never an exception)."""
    try:
        response = requests.get(url, headers=headers, timeout=_TIMEOUT_SECONDS)
    except requests.RequestException:
        return {"error": "fetch_failed"}

    if response.status_code != 200:
        # 401/403 usually means the token expired and no live session has
        # refreshed it yet (or, for Codex, an HTML bot-wall) — surfaced as-is
        # so the client can tell, and left hidden like Claude does.
        return {"error": f"http_{response.status_code}"}

    try:
        payload = response.json()
    except ValueError:
        return {"error": "invalid_response"}

    limits = parse(payload)
    if not limits:
        return {"error": "no_windows"}
    return {"limits": limits}


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------


def _fetch_claude() -> Dict[str, Any]:
    # Lazy imports keep daemon startup unchanged; ``usage`` is pure stdlib and
    # ``claude_usage_fetcher`` only costs its own module imports here.
    from integrations.headless.claude_usage_fetcher import read_claude_oauth_token
    from integrations.headless.usage import claude_limits_from_oauth

    token = read_claude_oauth_token()
    if not token:
        # Covers API-key setups (no windows to show) and unreadable
        # credentials (missing file, denied Keychain access).
        return {"error": "no_oauth_token"}
    return _get_json(
        _CLAUDE_USAGE_URL,
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "anthropic-beta": _CLAUDE_OAUTH_BETA_HEADER,
        },
        claude_limits_from_oauth,
    )


# ---------------------------------------------------------------------------
# Codex
# ---------------------------------------------------------------------------


def _codex_auth_paths() -> list[Path]:
    paths: list[Path] = []
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        paths.append(Path(codex_home) / "auth.json")
    paths.append(Path.home() / ".config" / "codex" / "auth.json")
    paths.append(Path.home() / ".codex" / "auth.json")
    return paths


def read_codex_credentials() -> Optional[tuple[str, Optional[str]]]:
    """``(access_token, account_id)`` from the Codex CLI's ``auth.json``, or
    ``None`` when there is no ChatGPT login (API-key setups have no
    ``tokens`` block and no windows to show)."""
    for path in _codex_auth_paths():
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError, TypeError):
            continue
        tokens = data.get("tokens") if isinstance(data, dict) else None
        if not isinstance(tokens, dict):
            continue
        token = tokens.get("access_token")
        if isinstance(token, str) and token:
            account = tokens.get("account_id")
            return token, account if isinstance(account, str) and account else None
    return None


def _fetch_codex() -> Dict[str, Any]:
    from integrations.headless.usage import codex_limits_from_wham

    creds = read_codex_credentials()
    if creds is None:
        return {"error": "no_oauth_token"}
    token, account_id = creds
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": _CODEX_USER_AGENT,
    }
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    return _get_json(_CODEX_USAGE_URL, headers, codex_limits_from_wham)


# ---------------------------------------------------------------------------
# Copilot
# ---------------------------------------------------------------------------


def _gh_binary() -> Optional[str]:
    found = shutil.which("gh")
    if found:
        return found
    for directory in _GH_FALLBACK_DIRS:
        candidate = Path(directory) / "gh"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _gh_auth_token() -> Optional[str]:
    gh = _gh_binary()
    if not gh:
        return None
    try:
        result = subprocess.run(
            [gh, "auth", "token", "--hostname", "github.com"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    token = result.stdout.strip() if result.returncode == 0 else ""
    return token or None


def _gh_hosts_token() -> Optional[str]:
    """``oauth_token`` for github.com out of ``~/.config/gh/hosts.yml``.

    Only present when ``gh`` stores tokens in plain text (Linux without a
    keyring); a two-level YAML lookup is all that needs parsing, so no yaml
    dependency.
    """
    config_dir = os.environ.get("GH_CONFIG_DIR") or str(Path.home() / ".config" / "gh")
    try:
        text = (Path(config_dir) / "hosts.yml").read_text()
    except OSError:
        return None
    in_github = False
    for line in text.splitlines():
        if not line.startswith(" "):
            in_github = line.strip().rstrip(":") == "github.com"
            continue
        if not in_github:
            continue
        match = re.match(r"\s+oauth_token:\s*(\S+)", line)
        if match:
            return match.group(1).strip("'\"") or None
    return None


def read_copilot_token() -> Optional[str]:
    for name in _COPILOT_TOKEN_ENV:
        value = os.environ.get(name)
        if value:
            return value
    return _gh_auth_token() or _gh_hosts_token()


def _fetch_copilot() -> Dict[str, Any]:
    from integrations.headless.usage import copilot_limits

    token = read_copilot_token()
    if not token:
        return {"error": "no_oauth_token"}
    return _get_json(
        _COPILOT_USAGE_URL,
        {"Authorization": f"token {token}", **_COPILOT_HEADERS},
        copilot_limits,
    )


# ---------------------------------------------------------------------------
# Registry + RPC entry points
# ---------------------------------------------------------------------------

#: provider id (the catalog agent id) -> fetcher. The clients gate the usage
#: indicator on this exact key set, mirrored in web `lib/provider-usage.ts`
#: and mobile `chat_usage_indicator.dart`.
PROVIDER_USAGE_FETCHERS: Dict[str, Fetcher] = {
    "claude": _fetch_claude,
    "codex": _fetch_codex,
    "copilot": _fetch_copilot,
}


def fetch_provider_usage(provider: Any = None, **_params: Any) -> Dict[str, Any]:
    """Serve the `fetch-provider-usage` RPC: `{limits: {windows: [...]}}` or `{error}`.

    ``**_params`` absorbs any extra RPC params a newer client may send.
    """
    provider_id = str(provider or "").strip().lower()
    fetcher = PROVIDER_USAGE_FETCHERS.get(provider_id)
    if fetcher is None:
        return {"error": f"unsupported provider: {provider_id or '(none)'}"}

    with _cache_lock:
        cached = _cache.get(provider_id)
        if cached is not None and time.monotonic() - cached[1] < _CACHE_TTL_SECONDS:
            return cached[0]

    result = fetcher()

    with _cache_lock:
        _cache[provider_id] = (result, time.monotonic())
    return result


def fetch_claude_usage(**_params: Any) -> Dict[str, Any]:
    """Serve the legacy `fetch-claude-usage` RPC name (pre-registry clients)."""
    return fetch_provider_usage("claude")


def clear_cache() -> None:
    """Test hook."""
    with _cache_lock:
        _cache.clear()


__all__ = [
    "PROVIDER_USAGE_FETCHERS",
    "clear_cache",
    "fetch_claude_usage",
    "fetch_provider_usage",
    "read_codex_credentials",
    "read_copilot_token",
]
