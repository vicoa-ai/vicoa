"""Structured-frequency next-run computation for automations.

Replaces the earlier raw-cron model: a `frequency` dict fully describes a
recurring schedule, and next-run is computed in Python so we can express
intervals cron can't ("every N days / weeks / months"). Shared by the `backend`
API (compute on create/update) and the `server` scheduler (advance after a run).

Weekday convention is **0=Sunday … 6=Saturday** (JS `getDay`), matching the web.

Frequency shapes (the `recurring` detail; `once` stores no frequency and uses an
absolute `run_at`):

    {"kind": "hourly",   "minute": 0}                      # every hour at :MM
    {"kind": "daily",    "time": "09:00"}
    {"kind": "weekdays", "time": "09:00"}                  # Mon–Fri
    {"kind": "weekly",   "weekdays": [1,3,5], "time": "09:00"}
    {"kind": "custom", "unit": "minutely", "interval": 15}
    {"kind": "custom", "unit": "hourly",  "minute": 30}
    {"kind": "custom", "unit": "daily",   "interval": 2, "time": "09:00"}
    {"kind": "custom", "unit": "weekly",  "interval": 2, "weekdays": [1], "time": "09:00"}
    {"kind": "custom", "unit": "monthly", "interval": 1, "monthdays": [1,15], "time": "09:00"}

Sub-daily interval schedules (custom `minutely`, and `hourly` in either form) may
carry an optional daily `window` — they then fire only within a time-of-day span,
realigned to the window's start each day:

    {"kind": "custom", "unit": "minutely", "interval": 15,
     "window": {"start": "09:00", "end": "12:00"}}         # 9:00, 9:15 … 12:00, then next day
    {"kind": "custom", "unit": "hourly", "interval": 2,
     "window": {"start": "09:00", "end": "17:00"}}         # 9:00, 11:00 … 17:00, then next day
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Bound the day-by-day search so a mis-specified schedule can't loop forever.
_SEARCH_HORIZON_DAYS = 800

# Floor on "every N minutes" — each fire spawns a full agent session, so guard
# against runaway schedules even if the API is called outside the UI (which
# enforces the same minimum). Mirrors MIN_MINUTELY_INTERVAL in the web lib.
_MIN_MINUTELY_INTERVAL = 5


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _safe_zone(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return ZoneInfo("UTC")


def _dow_sun0(d: datetime) -> int:
    """Day-of-week with 0=Sunday (Python's date.weekday() is Mon=0)."""
    return (d.weekday() + 1) % 7


def _parse_hm(time_str: str | None) -> tuple[int, int]:
    try:
        h, m = (time_str or "09:00").split(":")
        return max(0, min(23, int(h))), max(0, min(59, int(m)))
    except (ValueError, AttributeError):
        return 9, 0


def _coerce_int(value: object, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return default


def is_valid_frequency(frequency: dict | None) -> bool:
    """Whether `frequency` is a recognized recurring shape."""
    if not isinstance(frequency, dict):
        return False
    kind = frequency.get("kind")
    if kind in ("hourly", "daily", "weekdays"):
        return True
    if kind == "weekly":
        return bool(frequency.get("weekdays"))
    if kind == "custom":
        unit = frequency.get("unit")
        if unit == "minutely":
            return True
        if unit == "hourly":
            return True
        if unit == "daily":
            return True
        if unit == "weekly":
            return bool(frequency.get("weekdays"))
        if unit == "monthly":
            return bool(frequency.get("monthdays"))
    return False


def _parse_window(window: object) -> tuple[int, int] | None:
    """Parse a daily ``{"start","end"}`` span into (start, end) minutes-since-local-
    midnight, or None when absent/degenerate (→ treat as all-day).

    Overnight windows (end <= start, e.g. 22:00–02:00) are not supported and
    collapse to all-day; the UI blocks them so this only guards direct API calls."""
    if not isinstance(window, dict):
        return None
    start = window.get("start")
    end = window.get("end")
    if not isinstance(start, str) or not isinstance(end, str):
        return None
    sh, sm = _parse_hm(start)
    eh, em = _parse_hm(end)
    start_min = sh * 60 + sm
    end_min = eh * 60 + em
    if end_min <= start_min:
        return None
    return start_min, end_min


def _anchored_interval_next(
    step: timedelta, now_local: datetime, base_local: datetime
) -> datetime:
    """Next ``base + k*step`` strictly after now (continuous across days).

    floor((now - base) / step) gives the k with base + k*step <= now, so the next
    slot strictly after now is base + (k+1)*step (holds for any sign of the gap)."""
    n = (now_local - base_local) // step
    return _as_utc(base_local + (n + 1) * step)


def _windowed_interval_next(
    step: timedelta, window: tuple[int, int], now_local: datetime
) -> datetime | None:
    """Next occurrence of an every-`step` schedule confined to a daily window.

    `window` is (start, end) minutes-since-midnight, end inclusive. Occurrences
    each day are start, start+step, … up to and including end; past end the
    schedule resumes at the next day's start (interval realigns per day)."""
    start_min, end_min = window
    # The answer is at most tomorrow's start; bound the search anyway (DST days).
    for i in range(3):
        midnight = (now_local + timedelta(days=i)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        start = midnight + timedelta(minutes=start_min)
        end = midnight + timedelta(minutes=end_min)
        if now_local < start:
            candidate = start
        else:
            n = (now_local - start) // step
            candidate = start + (n + 1) * step
        if candidate <= end:
            return _as_utc(candidate)
    return None


def _day_active(frequency: dict, d: datetime, anchor_date: datetime) -> bool:
    """Whether calendar day `d` (a tz-local date) fires under `frequency`."""
    kind = frequency.get("kind")
    dow = _dow_sun0(d)

    if kind == "daily":
        return True
    if kind == "weekdays":
        return dow in (1, 2, 3, 4, 5)  # Mon–Fri
    if kind == "weekly":
        return dow in set(frequency.get("weekdays") or [])

    if kind == "custom":
        unit = frequency.get("unit")
        interval = _coerce_int(frequency.get("interval"), 1, 1, 999)
        if unit == "daily":
            delta = (d.date() - anchor_date.date()).days
            return delta >= 0 and delta % interval == 0
        if unit == "weekly":
            if dow not in set(frequency.get("weekdays") or []):
                return False
            # Phase by the Sunday of each week relative to the anchor's Sunday.
            d_sun = d.date() - timedelta(days=_dow_sun0(d))
            a_sun = anchor_date.date() - timedelta(days=_dow_sun0(anchor_date))
            weeks = (d_sun - a_sun).days // 7
            return weeks >= 0 and weeks % interval == 0
        if unit == "monthly":
            if d.day not in set(frequency.get("monthdays") or []):
                return False
            months = (d.year * 12 + d.month) - (
                anchor_date.year * 12 + anchor_date.month
            )
            return months >= 0 and months % interval == 0
    return False


def compute_next_run(
    frequency: dict | None,
    *,
    tz_name: str | None,
    after: datetime | None = None,
    anchor: datetime | None = None,
) -> datetime | None:
    """Next fire time as an aware UTC instant, or None if the schedule yields none.

    `after` defaults to now; `anchor` (defaults to now) is the phase reference for
    interval schedules ("every N …"). Missed occurrences collapse to the next
    future one (v1 drops misses)."""
    if not is_valid_frequency(frequency):
        return None
    assert frequency is not None
    tz = _safe_zone(tz_name)
    now_local = (_as_utc(after) if after else datetime.now(timezone.utc)).astimezone(tz)
    anchor_local = (
        _as_utc(anchor) if anchor else datetime.now(timezone.utc)
    ).astimezone(tz)

    kind = frequency.get("kind")
    unit = frequency.get("unit") if kind == "custom" else None

    # Sub-daily interval schedules: hourly (preset or custom) and custom minutely,
    # each optionally confined to a daily [start,end] window. These are minute-
    # based, not day-based.
    is_hourly = kind == "hourly" or unit == "hourly"
    is_minutely = unit == "minutely"
    if is_hourly or is_minutely:
        if is_minutely:
            interval = _coerce_int(
                frequency.get("interval"), 15, _MIN_MINUTELY_INTERVAL, 1439
            )
            step = timedelta(minutes=interval)
            base = anchor_local.replace(second=0, microsecond=0)
        else:
            interval = _coerce_int(frequency.get("interval"), 1, 1, 168)
            minute = _coerce_int(frequency.get("minute"), 0, 0, 59)
            step = timedelta(hours=interval)
            base = anchor_local.replace(minute=minute, second=0, microsecond=0)
        # `window` is a custom-only field; presets never carry one.
        window = _parse_window(frequency.get("window")) if kind == "custom" else None
        if window is not None:
            return _windowed_interval_next(step, window, now_local)
        return _anchored_interval_next(step, now_local, base)

    hh, mm = _parse_hm(frequency.get("time"))
    for i in range(_SEARCH_HORIZON_DAYS):
        day = now_local + timedelta(days=i)
        if not _day_active(frequency, day, anchor_local):
            continue
        candidate = day.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if candidate > now_local:
            return _as_utc(candidate)
    return None
