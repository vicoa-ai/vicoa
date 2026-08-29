"""Unit tests for the Claude plan-usage credential reader.

The HTTP call (``fetch_claude_usage``) is a thin best-effort aiohttp wrapper
that returns ``None`` on any error, so it isn't unit-tested here; the token
reader carries the parsing logic worth pinning down.
"""

from __future__ import annotations

import json

from integrations.headless import claude_usage_fetcher as fetcher


def test_read_token_from_credentials_file(tmp_path, monkeypatch):
    creds = tmp_path / ".credentials.json"
    creds.write_text(json.dumps({"claudeAiOauth": {"accessToken": "tok-123"}}))
    monkeypatch.setenv("CLAUDE_HOME", str(tmp_path))
    assert fetcher.read_claude_oauth_token() == "tok-123"


def test_read_token_none_when_no_oauth_block(tmp_path, monkeypatch):
    # API-key setups have no claudeAiOauth block -> no windows to show.
    creds = tmp_path / ".credentials.json"
    creds.write_text(json.dumps({"someOtherKey": {"apiKey": "sk-..."}}))
    monkeypatch.setenv("CLAUDE_HOME", str(tmp_path))
    assert fetcher.read_claude_oauth_token() is None


def test_read_token_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOME", str(tmp_path))  # empty dir, no creds file
    # Force the darwin keychain branch off so the test is platform-stable.
    monkeypatch.setattr(fetcher.sys, "platform", "linux")
    assert fetcher.read_claude_oauth_token() is None


def test_read_token_none_on_malformed_json(tmp_path, monkeypatch):
    creds = tmp_path / ".credentials.json"
    creds.write_text("{not valid json")
    monkeypatch.setenv("CLAUDE_HOME", str(tmp_path))
    monkeypatch.setattr(fetcher.sys, "platform", "linux")
    assert fetcher.read_claude_oauth_token() is None
