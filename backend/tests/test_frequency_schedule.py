"""Unit tests for structured-frequency next-run computation.

Focus on the interval + daily-window additions ("every N minutes" and
sub-daily schedules confined to a time-of-day span), plus regression coverage
for the pre-existing hourly/daily shapes.
"""

from datetime import datetime, timezone

from shared.scheduling.frequency import compute_next_run, is_valid_frequency


def _utc(y: int, mo: int, d: int, h: int, mi: int) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


# --- is_valid_frequency ----------------------------------------------------


def test_minutely_is_valid() -> None:
    assert is_valid_frequency({"kind": "custom", "unit": "minutely", "interval": 15})
    # A window is optional and never invalidates the shape.
    assert is_valid_frequency(
        {
            "kind": "custom",
            "unit": "minutely",
            "interval": 15,
            "window": {"start": "09:00", "end": "12:00"},
        }
    )


def test_unknown_unit_is_invalid() -> None:
    assert not is_valid_frequency({"kind": "custom", "unit": "secondly"})


# --- minutely (un-windowed, anchor-phased) ---------------------------------


def test_minutely_every_15_from_midnight_anchor() -> None:
    freq = {"kind": "custom", "unit": "minutely", "interval": 15}
    nxt = compute_next_run(
        freq,
        tz_name="UTC",
        after=_utc(2026, 8, 9, 10, 7),
        anchor=_utc(2026, 8, 9, 0, 0),
    )
    assert nxt == _utc(2026, 8, 9, 10, 15)


def test_minutely_interval_is_floored_to_five() -> None:
    # interval 2 is below the 5-minute floor and must be clamped up.
    freq = {"kind": "custom", "unit": "minutely", "interval": 2}
    nxt = compute_next_run(
        freq,
        tz_name="UTC",
        after=_utc(2026, 8, 9, 10, 7),
        anchor=_utc(2026, 8, 9, 0, 0),
    )
    assert nxt == _utc(2026, 8, 9, 10, 10)


# --- minutely (windowed) ---------------------------------------------------

_WINDOWED = {
    "kind": "custom",
    "unit": "minutely",
    "interval": 15,
    "window": {"start": "09:00", "end": "12:00"},
}


def test_windowed_before_window_returns_start() -> None:
    nxt = compute_next_run(_WINDOWED, tz_name="UTC", after=_utc(2026, 8, 9, 8, 30))
    assert nxt == _utc(2026, 8, 9, 9, 0)


def test_windowed_mid_window_returns_next_slot() -> None:
    nxt = compute_next_run(_WINDOWED, tz_name="UTC", after=_utc(2026, 8, 9, 10, 7))
    assert nxt == _utc(2026, 8, 9, 10, 15)


def test_windowed_last_slot_is_inclusive_of_end() -> None:
    nxt = compute_next_run(_WINDOWED, tz_name="UTC", after=_utc(2026, 8, 9, 11, 50))
    assert nxt == _utc(2026, 8, 9, 12, 0)


def test_windowed_at_end_jumps_to_next_day_start() -> None:
    # Firing exactly at the inclusive end → next occurrence is tomorrow's start.
    nxt = compute_next_run(_WINDOWED, tz_name="UTC", after=_utc(2026, 8, 9, 12, 0))
    assert nxt == _utc(2026, 8, 10, 9, 0)


def test_windowed_after_window_jumps_to_next_day_start() -> None:
    nxt = compute_next_run(_WINDOWED, tz_name="UTC", after=_utc(2026, 8, 9, 15, 0))
    assert nxt == _utc(2026, 8, 10, 9, 0)


def test_windowed_respects_local_timezone() -> None:
    # 09:00–12:00 window is local; in America/New_York (UTC-4 in August) the
    # first slot at 09:00 local is 13:00 UTC.
    nxt = compute_next_run(
        _WINDOWED, tz_name="America/New_York", after=_utc(2026, 8, 9, 6, 0)
    )
    assert nxt == _utc(2026, 8, 9, 13, 0)


def test_degenerate_window_falls_back_to_all_day() -> None:
    # end <= start is unsupported → behaves as an un-windowed every-15 schedule.
    freq = {
        "kind": "custom",
        "unit": "minutely",
        "interval": 15,
        "window": {"start": "12:00", "end": "09:00"},
    }
    nxt = compute_next_run(
        freq,
        tz_name="UTC",
        after=_utc(2026, 8, 9, 15, 7),
        anchor=_utc(2026, 8, 9, 0, 0),
    )
    assert nxt == _utc(2026, 8, 9, 15, 15)


# --- hourly windowed -------------------------------------------------------


def test_hourly_windowed_every_two_hours() -> None:
    freq = {
        "kind": "custom",
        "unit": "hourly",
        "interval": 2,
        "window": {"start": "09:00", "end": "17:00"},
    }
    # Mid-window at 10:30 → next 2-hour slot from 09:00 is 11:00.
    nxt = compute_next_run(freq, tz_name="UTC", after=_utc(2026, 8, 9, 10, 30))
    assert nxt == _utc(2026, 8, 9, 11, 0)
    # After the window → tomorrow's start.
    nxt2 = compute_next_run(freq, tz_name="UTC", after=_utc(2026, 8, 9, 18, 0))
    assert nxt2 == _utc(2026, 8, 10, 9, 0)


# --- regression: pre-existing shapes unchanged -----------------------------


def test_preset_hourly_unchanged() -> None:
    freq = {"kind": "hourly", "minute": 30}
    nxt = compute_next_run(
        freq,
        tz_name="UTC",
        after=_utc(2026, 8, 9, 10, 45),
        anchor=_utc(2026, 8, 9, 0, 0),
    )
    assert nxt == _utc(2026, 8, 9, 11, 30)


def test_custom_hourly_unwindowed_unchanged() -> None:
    freq = {"kind": "custom", "unit": "hourly", "interval": 3, "minute": 0}
    nxt = compute_next_run(
        freq,
        tz_name="UTC",
        after=_utc(2026, 8, 9, 10, 0),
        anchor=_utc(2026, 8, 9, 0, 0),
    )
    # 00:00, 03:00, 06:00, 09:00, 12:00 → after 10:00 the next is 12:00.
    assert nxt == _utc(2026, 8, 9, 12, 0)


def test_daily_unchanged() -> None:
    freq = {"kind": "daily", "time": "09:00"}
    nxt = compute_next_run(freq, tz_name="UTC", after=_utc(2026, 8, 9, 10, 0))
    assert nxt == _utc(2026, 8, 10, 9, 0)
