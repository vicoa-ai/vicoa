"""Helpers for locating/installing the codex-acp adapter binary."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple


def _codex_auth_json_path() -> Path:
    """Return the platform-appropriate path to codex's auth.json."""
    if os.name == "nt":
        # Windows: %USERPROFILE%\.codex\auth.json
        base = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    else:
        base = os.path.expanduser("~")
    return Path(base) / ".codex" / "auth.json"


def read_codex_auth_openai_key() -> Optional[str]:
    """Read OPENAI_API_KEY from ~/.codex/auth.json if present and non-null."""
    try:
        auth_file = _codex_auth_json_path()
        if not auth_file.exists():
            return None
        with auth_file.open() as f:
            data = json.load(f)
        value = data.get("OPENAI_API_KEY")
        return str(value) if value else None
    except Exception:
        return None


def _env_binary_path() -> Optional[Path]:
    raw = os.environ.get("VICOA_CODEX_ACP_PATH")
    if not raw:
        return None
    path = Path(os.path.expanduser(raw))
    return path if path.exists() else None


def resolve_codex_acp_binary() -> Optional[Path]:
    """Locate the ``codex-acp`` binary across env / PATH / install dirs.

    Order: ``VICOA_CODEX_ACP_PATH`` env override first; then the shared
    npm-CLI resolver (covers system PATH, nvm, NPM_CONFIG_PREFIX, Volta,
    snap, brew, and well-known per-user dirs).
    """
    env_path = _env_binary_path()
    if env_path:
        return env_path
    from vicoa.utils import find_npm_cli

    resolved = find_npm_cli("codex-acp")
    return Path(resolved) if resolved else None


def ensure_codex_acp_available(
    *,
    auto_install: bool = True,
    install_timeout_seconds: int = 300,
) -> Tuple[Optional[Path], Optional[str]]:
    """Resolve codex-acp binary path, optionally auto-installing via npm."""
    resolved = resolve_codex_acp_binary()
    if resolved:
        return resolved, None

    if auto_install:
        npm = shutil.which("npm")
        if npm:
            try:
                result = subprocess.run(
                    [npm, "install", "-g", "@zed-industries/codex-acp"],
                    capture_output=True,
                    text=True,
                    timeout=install_timeout_seconds,
                    check=False,
                )
                if result.returncode == 0:
                    resolved = resolve_codex_acp_binary()
                    if resolved:
                        return resolved, None
            except Exception:
                # Fall through to final guidance message.
                pass

    return (None, "Codex ACP adapter ('codex-acp') is not installed or not on PATH.\n")
