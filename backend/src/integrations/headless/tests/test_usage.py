"""Unit tests for the pure usage-blob builders in ``integrations.headless.usage``."""

from __future__ import annotations

from datetime import datetime, timezone

from integrations.headless.usage import (
    UsageState,
    claude_compaction_post_tokens,
    claude_context_used_from_result,
    claude_context_used_tokens,
    claude_context_window_for_model,
    claude_context_window_from_model_usage,
    claude_limits_from_oauth,
    claude_window,
    codex_context,
    codex_limits,
    project_rate_limited_until,
)


# --- context ---------------------------------------------------------------


def test_claude_context_sums_one_requests_prompt_plus_output():
    used = claude_context_used_tokens(
        {
            "input_tokens": 100,
            "cache_creation_input_tokens": 20,
            "cache_read_input_tokens": 30,
            "output_tokens": 25,
        }
    )
    assert used == 175


def test_claude_context_tolerates_missing_cache_and_output_fields():
    assert claude_context_used_tokens({"input_tokens": 42}) == 42


def test_claude_context_none_without_input_tokens():
    assert claude_context_used_tokens(None) is None
    assert claude_context_used_tokens({}) is None
    assert claude_context_used_tokens({"output_tokens": 10}) is None


def test_claude_context_stays_bounded_across_repeated_readings():
    """The regression that motivated this path: readings must not accumulate.

    A tool-heavy turn re-sends the whole cached prefix on every round-trip, so
    summing the requests reports several times the window size. Each reading is
    a snapshot, so the last one is the answer.
    """
    round_trips = [
        {
            "input_tokens": 5_000,
            "cache_read_input_tokens": 90_000,
            "output_tokens": 500,
        },
        {
            "input_tokens": 5_200,
            "cache_read_input_tokens": 95_000,
            "output_tokens": 700,
        },
        {
            "input_tokens": 5_400,
            "cache_read_input_tokens": 99_000,
            "output_tokens": 300,
        },
    ]
    readings = [claude_context_used_tokens(rt) for rt in round_trips]
    assert readings == [95_500, 100_900, 104_700]
    assert max(readings) < 200_000  # would be ~301k if summed


def test_claude_context_from_result_uses_last_iteration_not_the_aggregate():
    usage = {
        # Flat fields are the turn's cumulative usage — must be ignored.
        "input_tokens": 15_600,
        "cache_read_input_tokens": 284_000,
        "output_tokens": 1_500,
        "iterations": [
            {"input_tokens": 5_000, "cache_read_input_tokens": 90_000},
            {"input_tokens": 5_400, "cache_read_input_tokens": 99_000},
        ],
    }
    assert claude_context_used_from_result(usage) == 104_400


def test_claude_context_from_result_none_without_iterations():
    assert claude_context_used_from_result(None) is None
    assert claude_context_used_from_result({"input_tokens": 100}) is None


def test_claude_context_window_takes_max_across_models():
    model_usage = {
        "claude-opus-4-8": {"contextWindow": 200_000},
        "claude-haiku-4-5": {"contextWindow": 100_000},
    }
    assert claude_context_window_from_model_usage(model_usage) == 200_000


def test_claude_context_window_none_for_garbage():
    assert claude_context_window_from_model_usage(None) is None
    assert claude_context_window_from_model_usage({"m": {"contextWindow": 0}}) is None


def test_claude_context_window_seed_prefers_long_context_variant():
    assert claude_context_window_for_model("claude-opus-4-8[1m]") == 1_000_000
    assert claude_context_window_for_model("claude-opus-4-8-20260115") == 200_000
    assert claude_context_window_for_model("claude-haiku-4-5") == 200_000
    assert claude_context_window_for_model(None) is None


def test_claude_context_window_seed_matches_claude_code_defaults():
    # Bare ids mirror Claude Code's default 200k window even though the API
    # serves 1M for these models; only the [1m] variant (and the 1M-only
    # Fable/Opus 5 ids) seed the large window.
    assert claude_context_window_for_model("claude-sonnet-5") == 200_000
    assert claude_context_window_for_model("claude-sonnet-5[1m]") == 1_000_000
    assert claude_context_window_for_model("claude-fable-5") == 1_000_000
    assert claude_context_window_for_model("claude-opus-5") == 1_000_000


def test_claude_compaction_post_tokens_accepts_key_variants():
    assert (
        claude_compaction_post_tokens({"compact_metadata": {"post_tokens": 12}}) == 12
    )
    assert claude_compaction_post_tokens({"compactMetadata": {"postTokens": 34}}) == 34
    assert claude_compaction_post_tokens({"compact_metadata": {}}) is None
    assert claude_compaction_post_tokens(None) is None


def test_codex_context_uses_last_breakdown_and_model_window():
    token_usage = {
        "last": {"totalTokens": 48213, "inputTokens": 40000, "outputTokens": 8213},
        "total": {"totalTokens": 120000},
        "modelContextWindow": 272000,
    }
    ctx = codex_context(token_usage)
    assert ctx == {"used_tokens": 48213, "max_tokens": 272000, "cost_usd": None}


def test_codex_context_falls_back_to_total_when_no_last():
    ctx = codex_context({"total": {"totalTokens": 99}, "modelContextWindow": 200000})
    assert ctx["used_tokens"] == 99


def test_codex_context_none_for_garbage():
    assert codex_context(None) is None
    assert codex_context({}) is None


# --- rate-limit windows ----------------------------------------------------


def test_claude_window_normalises_fraction_to_percent_and_iso_reset():
    # 2026-07-16T21:00:00Z
    epoch = int(datetime(2026, 7, 16, 21, 0, tzinfo=timezone.utc).timestamp())
    window = claude_window("five_hour", 0.634, epoch)
    assert window["id"] == "five_hour"
    assert window["label"] == "Session"
    assert window["used_pct"] == 63.4
    assert window["resets_at"] == "2026-07-16T21:00:00+00:00"


def test_claude_window_none_without_type_or_utilization():
    assert claude_window(None, 0.5, None) is None
    assert claude_window("five_hour", None, None) is None


def test_claude_window_only_session_and_weekly():
    # Per-model / overage / unknown windows are dropped — only the two
    # headline windows surface.
    assert claude_window("seven_day", 0.4, None)["label"] == "Weekly"
    assert claude_window("seven_day_opus", 0.4, None) is None
    assert claude_window("overage", 0.4, None) is None
    assert claude_window("brand_new_window", 0.1, None) is None


def test_codex_limits_maps_primary_secondary_and_credits():
    epoch = int(datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp())
    limits = codex_limits(
        {
            "primary": {"usedPercent": 63, "resetsAt": epoch},
            "secondary": {"usedPercent": 41, "resetsAt": None},
            "credits": {"hasCredits": True, "unlimited": False, "balance": "4.10"},
        }
    )
    assert limits["windows"][0] == {
        "id": "session",
        "label": "Session",
        "used_pct": 63.0,
        "resets_at": "2026-07-20T00:00:00+00:00",
    }
    assert limits["windows"][1]["id"] == "weekly"
    assert limits["windows"][1]["resets_at"] is None
    assert limits["credits"] == {"unit": "usd", "remaining": 4.10}


def test_codex_limits_omits_credits_without_balance():
    limits = codex_limits(
        {
            "primary": {"usedPercent": 10},
            "credits": {"hasCredits": False, "unlimited": False},
        }
    )
    assert "credits" not in limits
    assert len(limits["windows"]) == 1


def test_codex_limits_none_when_empty():
    assert codex_limits(None) is None
    assert codex_limits({}) is None


def test_claude_limits_from_oauth_maps_session_and_weekly():
    # utilization is already 0-100 here (unlike the SDK's 0-1 fraction), and
    # resets_at is an ISO string passed through as-is.
    limits = claude_limits_from_oauth(
        {
            "five_hour": {"utilization": 63.0, "resets_at": "2026-07-16T21:00:00Z"},
            "seven_day": {"utilization": 41.0, "resets_at": "2026-07-20T00:00:00Z"},
            "seven_day_opus": {"utilization": 12.0, "resets_at": None},
            "extra_usage": {"is_enabled": True},
        }
    )
    assert [w["id"] for w in limits["windows"]] == ["five_hour", "seven_day"]
    assert limits["windows"][0] == {
        "id": "five_hour",
        "label": "Session",
        "used_pct": 63.0,
        "resets_at": "2026-07-16T21:00:00Z",
    }
    assert limits["windows"][1]["label"] == "Weekly"
    assert "credits" not in limits


def test_claude_limits_from_oauth_none_when_empty_or_garbage():
    assert claude_limits_from_oauth(None) is None
    assert claude_limits_from_oauth({}) is None
    assert (
        claude_limits_from_oauth({"five_hour": {"resets_at": "x"}}) is None
    )  # no util


# --- UsageState ------------------------------------------------------------


def test_usage_state_context_max_is_sticky_across_updates():
    """The ring needs a max to draw a percentage; once known it must not go away."""
    state = UsageState()
    assert state.latch_context_max(200_000) is True
    assert state.set_context_usage(50_000) is True
    assert state.context == {
        "used_tokens": 50_000,
        "max_tokens": 200_000,
        "cost_usd": None,
    }
    # A later reading that carries no window size keeps the known one.
    assert state.set_context_usage(60_000) is True
    assert state.context["max_tokens"] == 200_000
    assert state.latch_context_max(None) is False
    assert state.context["max_tokens"] == 200_000


def test_usage_state_seed_never_overwrites_a_real_window_size():
    state = UsageState()
    assert state.latch_context_max(1_000_000) is True
    assert state.latch_context_max(200_000, seed=True) is False
    assert state.context_max_tokens == 1_000_000


def test_usage_state_seed_fills_the_gap_before_any_real_reading():
    state = UsageState()
    assert state.latch_context_max(200_000, seed=True) is True
    assert state.context_max_tokens == 200_000
    # ...and the authoritative value still wins later.
    assert state.latch_context_max(1_000_000) is True
    assert state.context_max_tokens == 1_000_000


def test_usage_state_latching_max_restamps_an_existing_fill():
    state = UsageState()
    state.set_context_usage(50_000)
    assert state.context["max_tokens"] is None
    state.latch_context_max(1_000_000)
    assert state.context["max_tokens"] == 1_000_000


def test_usage_state_carries_cost_forward_through_mid_turn_updates():
    """Cost only rides the end-of-turn result; mid-turn fills must not blank it."""
    state = UsageState()
    state.set_context_usage(10_000, cost_usd=0.42)
    assert state.context["cost_usd"] == 0.42
    state.set_context_usage(20_000)
    assert state.context["cost_usd"] == 0.42


def test_usage_state_accepts_zero_used_tokens_as_a_real_reading():
    state = UsageState()
    state.latch_context_max(200_000)
    assert state.set_context_usage(0) is True
    assert state.context["used_tokens"] == 0


def test_usage_state_merges_context_and_limits_without_clobbering():
    state = UsageState()
    assert state.set_context(
        {"used_tokens": 100, "max_tokens": 200000, "cost_usd": None}
    )
    assert state.upsert_window(
        {"id": "five_hour", "label": "Session", "used_pct": 60.0, "resets_at": None}
    )
    core = state.core()
    assert core["context"]["used_tokens"] == 100
    assert core["limits"]["windows"][0]["id"] == "five_hour"

    # A later context-only update must preserve the previously-seen window.
    assert state.set_context(
        {"used_tokens": 150, "max_tokens": 200000, "cost_usd": None}
    )
    core = state.core()
    assert core["context"]["used_tokens"] == 150
    assert core["limits"]["windows"][0]["id"] == "five_hour"


def test_usage_state_dedupes_no_op_updates():
    state = UsageState()
    ctx = {"used_tokens": 100, "max_tokens": 200000, "cost_usd": None}
    assert state.set_context(ctx) is True
    assert state.set_context(dict(ctx)) is False  # identical -> no change
    window = {"id": "weekly", "label": "Weekly", "used_pct": 40.0, "resets_at": None}
    assert state.upsert_window(window) is True
    assert state.upsert_window(dict(window)) is False


def test_usage_state_upserts_window_by_id():
    state = UsageState()
    state.upsert_window(
        {"id": "five_hour", "label": "Session", "used_pct": 60.0, "resets_at": None}
    )
    changed = state.upsert_window(
        {"id": "five_hour", "label": "Session", "used_pct": 72.0, "resets_at": None}
    )
    assert changed is True
    windows = state.core()["limits"]["windows"]
    assert len(windows) == 1
    assert windows[0]["used_pct"] == 72.0


def test_usage_state_set_limits_replaces_snapshot():
    state = UsageState()
    state.upsert_window(
        {"id": "session", "label": "Session", "used_pct": 10.0, "resets_at": None}
    )
    changed = state.set_limits(
        {
            "windows": [
                {
                    "id": "session",
                    "label": "Session",
                    "used_pct": 63.0,
                    "resets_at": None,
                },
                {
                    "id": "weekly",
                    "label": "Weekly",
                    "used_pct": 41.0,
                    "resets_at": None,
                },
            ],
            "credits": {"unit": "usd", "remaining": 4.10},
        }
    )
    assert changed is True
    core = state.core()
    assert [w["id"] for w in core["limits"]["windows"]] == ["session", "weekly"]
    assert core["limits"]["credits"]["remaining"] == 4.10


def test_usage_state_blob_is_timestamped_and_none_when_empty():
    assert UsageState().blob() is None
    state = UsageState()
    state.set_context({"used_tokens": 1, "max_tokens": None, "cost_usd": None})
    blob = state.blob()
    assert "updated_at" in blob
    # ISO-8601 parseable
    datetime.fromisoformat(blob["updated_at"])


# --- rate-limit projection -------------------------------------------------


def _win(pct, resets_at="2026-08-20T18:00:00+00:00", wid="five_hour"):
    return {"id": wid, "label": "Session", "used_pct": pct, "resets_at": resets_at}


def test_project_none_when_no_windows_maxed():
    usage = {"limits": {"windows": [_win(75.0), _win(99.9, wid="seven_day")]}}
    assert project_rate_limited_until(usage) is None


def test_project_one_maxed_window_returns_reset_plus_buffer():
    reset = "2026-08-20T18:00:00+00:00"
    got = project_rate_limited_until({"limits": {"windows": [_win(100.0, reset)]}})
    assert got == datetime(2026, 8, 20, 18, 0, 45, tzinfo=timezone.utc)


def test_project_takes_latest_reset_across_two_maxed_windows():
    early = _win(100.0, "2026-08-20T18:00:00+00:00", "five_hour")
    late = _win(100.0, "2026-08-25T00:00:00+00:00", "seven_day")
    got = project_rate_limited_until({"limits": {"windows": [early, late]}})
    # blocked until the LATER (binding) reset, +45s buffer
    assert got == datetime(2026, 8, 25, 0, 0, 45, tzinfo=timezone.utc)


def test_project_ignores_credits_money_exhaustion():
    usage = {
        "limits": {
            "windows": [_win(50.0)],
            "credits": {"unit": "usd", "remaining": 0.0},
        }
    }
    assert project_rate_limited_until(usage) is None


def test_project_ignores_maxed_window_without_reset():
    usage = {"limits": {"windows": [_win(100.0, resets_at=None)]}}
    assert project_rate_limited_until(usage) is None


def test_project_tolerates_z_suffixed_reset():
    got = project_rate_limited_until(
        {"limits": {"windows": [_win(100.0, "2026-08-20T18:00:00Z")]}}
    )
    assert got == datetime(2026, 8, 20, 18, 0, 45, tzinfo=timezone.utc)


def test_project_none_for_empty_or_garbage_usage():
    assert project_rate_limited_until(None) is None
    assert project_rate_limited_until({}) is None
    assert project_rate_limited_until({"limits": {"windows": []}}) is None
    assert project_rate_limited_until({"limits": "nope"}) is None
