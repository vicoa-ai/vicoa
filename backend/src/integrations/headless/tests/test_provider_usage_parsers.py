"""Unit tests for the out-of-band provider usage parsers in
``integrations.headless.usage`` (Codex ``wham/usage``, Copilot
``copilot_internal/user``), driven by captured, redacted responses.

``*_free*.json`` are real captures from 2026-09-14 (ids/emails redacted); the
paid-plan fixtures are the same shapes with the fields a paid account fills.
"""

from __future__ import annotations

import json
from pathlib import Path

from integrations.headless.usage import codex_limits_from_wham, copilot_limits

_FIXTURES = Path(__file__).parent / "fixtures" / "provider_usage"


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text())


# --- Codex -----------------------------------------------------------------


def test_codex_free_plan_has_one_monthly_window_and_no_credits():
    limits = codex_limits_from_wham(_load("codex_wham_usage_free.json"))
    assert limits is not None
    assert limits["plan"] == "free"
    assert "credits" not in limits  # balance is null on a free plan
    assert limits["windows"] == [
        {
            "id": "session",
            # 2592000s = 30 days: the primary window is NOT a 5h session here.
            "label": "Monthly",
            "used_pct": 0.0,
            "resets_at": "2026-10-11T09:05:19+00:00",
        }
    ]


def test_codex_plus_plan_maps_both_windows_and_credits():
    limits = codex_limits_from_wham(_load("codex_wham_usage_plus.json"))
    assert limits is not None
    assert limits["plan"] == "plus"
    assert [w["id"] for w in limits["windows"]] == ["session", "weekly"]
    session, weekly = limits["windows"]
    assert session["label"] == "Session" and session["used_pct"] == 63.4
    assert session["resets_at"] == "2026-09-10T00:26:40+00:00"
    assert weekly["label"] == "Weekly" and weekly["used_pct"] == 41.0
    assert limits["credits"] == {"unit": "usd", "remaining": 12.5}


def test_codex_window_label_falls_back_when_length_is_odd():
    payload = {
        "rate_limit": {
            "primary_window": {"used_percent": 5, "limit_window_seconds": 99999},
            "secondary_window": {"used_percent": 6},  # no length at all
        }
    }
    limits = codex_limits_from_wham(payload)
    assert limits is not None
    assert [w["label"] for w in limits["windows"]] == ["Session", "Weekly"]


def test_codex_none_when_nothing_usable():
    assert codex_limits_from_wham(None) is None
    assert codex_limits_from_wham({}) is None
    assert codex_limits_from_wham({"rate_limit": {"primary_window": None}}) is None
    # An HTML bot-wall parsed as a string, or a list, is not a snapshot.
    assert codex_limits_from_wham("<html>") is None  # type: ignore[arg-type]


# --- Copilot ---------------------------------------------------------------


def test_copilot_free_limited_skips_the_zero_entitlement_premium_quota():
    """The captured free_limited account has ``premium_interactions`` with
    entitlement 0 / has_quota false — rendering that as "100% used" would be
    a lie. Chat (200/month) is the one real bar."""
    limits = copilot_limits(_load("copilot_user_free_limited.json"))
    assert limits is not None
    assert limits["plan"] == "individual"
    assert limits["windows"] == [
        {
            "id": "chat",
            "label": "Chat",
            "used_pct": 0.0,
            "resets_at": "2026-10-01T00:00:00.000Z",
            "entitlement": 200,
            "remaining": 200,
        }
    ]


def test_copilot_pro_renders_premium_requests_and_skips_unlimited():
    limits = copilot_limits(_load("copilot_user_pro.json"))
    assert limits is not None
    assert limits["plan"] == "individual_pro"
    assert limits["windows"] == [
        {
            "id": "premium",
            "label": "Premium requests",
            "used_pct": 62.5,
            # Bare quota_reset_date → UTC midnight.
            "resets_at": "2026-10-01T00:00:00+00:00",
            "entitlement": 300,
            "remaining": 112,
        }
    ]


def test_copilot_used_pct_is_clamped_and_none_without_snapshots():
    payload = {
        "quota_snapshots": {
            "premium_interactions": {
                "percent_remaining": -3.0,  # overage: more than 100% used
                "has_quota": True,
                "entitlement": 50,
                "remaining": 0,
            }
        }
    }
    limits = copilot_limits(payload)
    assert limits is not None
    assert limits["windows"][0]["used_pct"] == 100.0
    assert limits["windows"][0]["resets_at"] is None
    assert copilot_limits({"copilot_plan": "individual"}) is None
    assert copilot_limits(None) is None
