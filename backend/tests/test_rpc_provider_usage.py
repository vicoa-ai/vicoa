"""`vicoa.rpc.provider_usage`: the provider registry behind the
`fetch-provider-usage` RPC, the legacy `fetch-claude-usage` alias, credential
discovery for Codex/Copilot, and the per-provider TTL cache.

The HTTP GET is mocked at `requests.get`; the parsers have their own fixture
tests under integrations/headless/tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from vicoa.rpc import provider_usage


@pytest.fixture(autouse=True)
def _fresh_cache():
    provider_usage.clear_cache()
    yield
    provider_usage.clear_cache()


def _response(status: int, payload: Any) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    if isinstance(payload, str):
        resp.json.side_effect = ValueError("not json")
    else:
        resp.json.return_value = payload
    return resp


# --- registry + alias --------------------------------------------------------


def test_registry_covers_the_three_providers_the_clients_gate_on():
    assert set(provider_usage.PROVIDER_USAGE_FETCHERS) == {"claude", "codex", "copilot"}


def test_unknown_provider_is_an_error_not_an_exception():
    assert provider_usage.fetch_provider_usage("gemini") == {
        "error": "unsupported provider: gemini"
    }
    assert provider_usage.fetch_provider_usage() == {
        "error": "unsupported provider: (none)"
    }


def test_legacy_fetch_claude_usage_routes_to_the_registry(monkeypatch):
    monkeypatch.setitem(
        provider_usage.PROVIDER_USAGE_FETCHERS,
        "claude",
        lambda: {"limits": {"windows": [{"id": "five_hour"}]}},
    )
    assert provider_usage.fetch_claude_usage() == {
        "limits": {"windows": [{"id": "five_hour"}]}
    }
    # Extra params from a newer client are absorbed, not fatal.
    assert provider_usage.fetch_claude_usage(foo=1)["limits"]


def test_cache_is_per_provider_and_covers_failures(monkeypatch):
    calls: list[str] = []

    def fetcher_for(name: str):
        def _fetch() -> dict[str, Any]:
            calls.append(name)
            return {"error": "no_oauth_token"}

        return _fetch

    monkeypatch.setitem(
        provider_usage.PROVIDER_USAGE_FETCHERS, "codex", fetcher_for("codex")
    )
    monkeypatch.setitem(
        provider_usage.PROVIDER_USAGE_FETCHERS, "copilot", fetcher_for("copilot")
    )
    provider_usage.fetch_provider_usage("codex")
    provider_usage.fetch_provider_usage("codex")  # cached, incl. the failure
    provider_usage.fetch_provider_usage("copilot")
    assert calls == ["codex", "copilot"]

    # Expire the TTL and the next call refetches.
    monkeypatch.setattr(provider_usage, "_CACHE_TTL_SECONDS", 0.0)
    provider_usage.fetch_provider_usage("codex")
    assert calls == ["codex", "copilot", "codex"]


# --- Codex -------------------------------------------------------------------


def test_codex_credentials_prefer_codex_home_then_config_then_dotcodex(
    tmp_path: Path, monkeypatch
):
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "auth.json").write_text(
        json.dumps({"tokens": {"access_token": "dot", "account_id": "acct-dot"}})
    )
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    assert provider_usage.read_codex_credentials() == ("dot", "acct-dot")

    codex_home = tmp_path / "ch"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        json.dumps({"tokens": {"access_token": "ch"}})
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    assert provider_usage.read_codex_credentials() == ("ch", None)


def test_codex_credentials_none_for_api_key_setups(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "auth.json").write_text(
        json.dumps({"auth_mode": "apikey", "OPENAI_API_KEY": "sk-..."})
    )
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    assert provider_usage.read_codex_credentials() is None
    assert provider_usage.fetch_provider_usage("codex") == {"error": "no_oauth_token"}


def test_codex_fetch_sends_account_header_and_maps_windows(monkeypatch):
    monkeypatch.setattr(
        provider_usage, "read_codex_credentials", lambda: ("tok", "acct-1")
    )
    seen: dict[str, Any] = {}

    def fake_get(url, headers=None, timeout=None):
        seen.update(url=url, headers=headers)
        return _response(
            200,
            {
                "plan_type": "plus",
                "rate_limit": {
                    "primary_window": {
                        "used_percent": 12,
                        "limit_window_seconds": 18000,
                        "reset_at": 1789000000,
                    },
                    "secondary_window": None,
                },
                "credits": {"balance": None},
            },
        )

    monkeypatch.setattr(requests, "get", fake_get)
    result = provider_usage.fetch_provider_usage("codex")
    assert seen["url"] == provider_usage._CODEX_USAGE_URL
    assert seen["headers"]["Authorization"] == "Bearer tok"
    assert seen["headers"]["ChatGPT-Account-Id"] == "acct-1"
    assert "Mozilla" in seen["headers"]["User-Agent"]
    assert result == {
        "limits": {
            "plan": "plus",
            "windows": [
                {
                    "id": "session",
                    "label": "Session",
                    "used_pct": 12.0,
                    "resets_at": "2026-09-10T00:26:40+00:00",
                }
            ],
        }
    }


@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    [
        (401, {}, "http_401"),
        (403, "<html>bot wall</html>", "http_403"),
        (200, "<html>bot wall</html>", "invalid_response"),
        (200, {"rate_limit": {}}, "no_windows"),
    ],
)
def test_codex_fetch_failure_reasons(monkeypatch, status, payload, expected):
    monkeypatch.setattr(provider_usage, "read_codex_credentials", lambda: ("tok", None))
    monkeypatch.setattr(requests, "get", lambda *a, **k: _response(status, payload))
    assert provider_usage.fetch_provider_usage("codex") == {"error": expected}


def test_network_error_is_fetch_failed(monkeypatch):
    monkeypatch.setattr(provider_usage, "read_codex_credentials", lambda: ("tok", None))

    def boom(*_a, **_k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", boom)
    assert provider_usage.fetch_provider_usage("codex") == {"error": "fetch_failed"}


# --- Copilot -----------------------------------------------------------------


def test_copilot_token_env_beats_gh(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env-tok")
    monkeypatch.setattr(provider_usage, "_gh_auth_token", lambda: "gh-tok")
    assert provider_usage.read_copilot_token() == "env-tok"


def test_copilot_token_falls_back_to_gh_then_hosts_yml(tmp_path: Path, monkeypatch):
    for name in provider_usage._COPILOT_TOKEN_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(provider_usage, "_gh_auth_token", lambda: "gh-tok")
    assert provider_usage.read_copilot_token() == "gh-tok"

    # No `gh` (or it stores the token in the Keychain and refuses): read the
    # plain-text hosts.yml a Linux install writes.
    monkeypatch.setattr(provider_usage, "_gh_auth_token", lambda: None)
    (tmp_path / "hosts.yml").write_text(
        "github.com:\n"
        "    git_protocol: ssh\n"
        "    users:\n"
        "        someone:\n"
        "            oauth_token: gho_fromfile\n"
        "    user: someone\n"
        "    oauth_token: gho_fromfile\n"
        "ghe.example.com:\n"
        "    oauth_token: gho_other\n"
    )
    monkeypatch.setenv("GH_CONFIG_DIR", str(tmp_path))
    assert provider_usage.read_copilot_token() == "gho_fromfile"

    (tmp_path / "hosts.yml").write_text("github.com:\n    user: someone\n")
    assert provider_usage.read_copilot_token() is None
    assert provider_usage.fetch_provider_usage("copilot") == {"error": "no_oauth_token"}


def test_copilot_fetch_sends_editor_headers_and_maps_premium_window(monkeypatch):
    monkeypatch.setattr(provider_usage, "read_copilot_token", lambda: "gho_x")
    seen: dict[str, Any] = {}

    def fake_get(url, headers=None, timeout=None):
        seen.update(url=url, headers=headers)
        return _response(
            200,
            {
                "copilot_plan": "individual_pro",
                "quota_reset_date_utc": "2026-10-01T00:00:00.000Z",
                "quota_snapshots": {
                    "premium_interactions": {
                        "percent_remaining": 40.0,
                        "has_quota": True,
                        "unlimited": False,
                        "entitlement": 300,
                        "remaining": 120,
                    },
                    "chat": {"unlimited": True, "entitlement": 0},
                },
            },
        )

    monkeypatch.setattr(requests, "get", fake_get)
    result = provider_usage.fetch_provider_usage("copilot")
    assert seen["url"] == provider_usage._COPILOT_USAGE_URL
    assert seen["headers"]["Authorization"] == "token gho_x"
    assert seen["headers"]["Editor-Version"].startswith("vscode/")
    assert seen["headers"]["X-Github-Api-Version"] == "2025-04-01"
    assert result == {
        "limits": {
            "plan": "individual_pro",
            "windows": [
                {
                    "id": "premium",
                    "label": "Premium requests",
                    "used_pct": 60.0,
                    "resets_at": "2026-10-01T00:00:00.000Z",
                    "entitlement": 300,
                    "remaining": 120,
                }
            ],
        }
    }
