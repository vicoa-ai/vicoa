"""Unit tests for the Claude plan-usage credential reader.

The HTTP call (``fetch_claude_usage``) is a thin best-effort aiohttp wrapper
that returns ``None`` on any error, so it isn't unit-tested here; the token
reader carries the parsing logic worth pinning down.
"""

from __future__ import annotations

import json
import subprocess
from typing import Dict, List, Optional

import pytest

from integrations.headless import claude_usage_fetcher as fetcher

_LOGIN = json.dumps({"mcpOAuth": {}, "claudeAiOauth": {"accessToken": "tok-keychain"}})
_MCP_ONLY = json.dumps({"mcpOAuth": {"some-server": {"accessToken": "mcp"}}})


class _FakeKeychain:
    """Stands in for ``security find-generic-password``.

    ``items`` maps an account name to the item's JSON; a lookup with no
    ``-a`` gets ``unscoped`` (the item the Keychain happens to list first).
    """

    def __init__(self, items: Dict[str, str], unscoped: Optional[str] = None) -> None:
        self.items = items
        self.unscoped = unscoped
        self.calls: List[List[str]] = []

    def __call__(self, command: List[str], **_kwargs: object):
        self.calls.append(command)
        if "-a" in command:
            found = self.items.get(command[command.index("-a") + 1])
        else:
            found = self.unscoped
        if found is None:
            return subprocess.CompletedProcess(command, 44, "", "not found")
        return subprocess.CompletedProcess(command, 0, found + "\n", "")


@pytest.fixture(autouse=True)
def _no_real_keychain(tmp_path, monkeypatch):
    """Keep every test off the machine's real credentials file and Keychain."""
    monkeypatch.setenv("CLAUDE_HOME", str(tmp_path))
    monkeypatch.setattr(fetcher.subprocess, "run", _FakeKeychain({}))


def _on_macos(monkeypatch, keychain: _FakeKeychain, user: str = "dev") -> None:
    monkeypatch.setattr(fetcher.sys, "platform", "darwin")
    monkeypatch.setenv("USER", user)
    monkeypatch.setattr(fetcher.subprocess, "run", keychain)


def test_read_token_from_credentials_file(tmp_path):
    creds = tmp_path / ".credentials.json"
    creds.write_text(json.dumps({"claudeAiOauth": {"accessToken": "tok-123"}}))
    assert fetcher.read_claude_oauth_token() == "tok-123"


def test_read_token_none_when_no_oauth_block(tmp_path, monkeypatch):
    # API-key setups have no claudeAiOauth block -> no windows to show.
    creds = tmp_path / ".credentials.json"
    creds.write_text(json.dumps({"someOtherKey": {"apiKey": "sk-..."}}))
    monkeypatch.setattr(fetcher.sys, "platform", "linux")
    assert fetcher.read_claude_oauth_token() is None


def test_read_token_none_when_file_missing(monkeypatch):
    # Force the darwin keychain branch off so the test is platform-stable.
    monkeypatch.setattr(fetcher.sys, "platform", "linux")
    assert fetcher.read_claude_oauth_token() is None


def test_read_token_none_on_malformed_json(tmp_path, monkeypatch):
    creds = tmp_path / ".credentials.json"
    creds.write_text("{not valid json")
    monkeypatch.setattr(fetcher.sys, "platform", "linux")
    assert fetcher.read_claude_oauth_token() is None


def test_keychain_lookup_asks_for_the_users_account(monkeypatch):
    keychain = _FakeKeychain({"dev": _LOGIN})
    _on_macos(monkeypatch, keychain)
    assert fetcher.read_claude_oauth_token() == "tok-keychain"
    # Found under the user's account, so no service-only lookup follows.
    assert keychain.calls == [
        [
            "security",
            "find-generic-password",
            "-a",
            "dev",
            "-s",
            "Claude Code-credentials",
            "-w",
        ]
    ]


def test_keychain_skips_a_first_listed_item_without_the_login(monkeypatch):
    # A service-only lookup returns an MCP-only item filed under another
    # account; the user's own item still holds the login.
    keychain = _FakeKeychain({"unknown": _MCP_ONLY, "dev": _LOGIN}, _MCP_ONLY)
    _on_macos(monkeypatch, keychain)
    assert fetcher.read_claude_oauth_token() == "tok-keychain"


def test_keychain_falls_back_to_service_only_lookup(monkeypatch):
    keychain = _FakeKeychain({"someone-else": _LOGIN}, unscoped=_LOGIN)
    _on_macos(monkeypatch, keychain)
    assert fetcher.read_claude_oauth_token() == "tok-keychain"
    assert "-a" not in keychain.calls[-1]


def test_keychain_none_when_no_item_has_the_login(monkeypatch):
    keychain = _FakeKeychain({"dev": _MCP_ONLY}, unscoped=_MCP_ONLY)
    _on_macos(monkeypatch, keychain)
    assert fetcher.read_claude_oauth_token() is None


def test_file_without_login_falls_through_to_keychain(tmp_path, monkeypatch):
    (tmp_path / ".credentials.json").write_text(_MCP_ONLY)
    _on_macos(monkeypatch, _FakeKeychain({"dev": _LOGIN}))
    assert fetcher.read_claude_oauth_token() == "tok-keychain"


def test_keychain_account_falls_back_for_unusual_user_names(monkeypatch):
    monkeypatch.setenv("USER", "dev user")
    assert fetcher._keychain_account() == "claude-code-user"


def test_keychain_account_uses_login_name_without_user_env(monkeypatch):
    pwd = pytest.importorskip("pwd")
    monkeypatch.delenv("USER", raising=False)
    expected = pwd.getpwuid(fetcher.os.getuid()).pw_name
    assert fetcher._keychain_account() == expected
