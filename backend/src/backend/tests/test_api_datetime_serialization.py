"""Session timestamps go out as UTC with a trailing "Z", naive or aware.

Most columns behind them are naive UTC; `rate_limited_until` is timestamptz, so
its value is aware. Appending "Z" to an aware value's isoformat() would give
"+00:00Z", which neither JavaScript nor Python parses.
"""

from datetime import datetime, timedelta, timezone

from backend.models import AgentInstanceDetail, AgentInstanceResponse
from shared.database.enums import AgentStatus

NAIVE_START = datetime(2026, 8, 20, 9, 30, 0)
AWARE_RESET = datetime(2026, 8, 20, 18, 0, 45, tzinfo=timezone.utc)


def _fields(**overrides: object) -> dict[str, object]:
    return {
        "id": "a",
        "agent_type_id": "t",
        "status": AgentStatus.AWAITING_INPUT,
        "started_at": NAIVE_START,
        "ended_at": None,
        "rate_limited": True,
        "rate_limit_resets_at": AWARE_RESET,
        **overrides,
    }


def test_naive_and_aware_timestamps_serialize_the_same_way() -> None:
    out = AgentInstanceResponse.model_validate(_fields()).model_dump(mode="json")
    assert out["started_at"] == "2026-08-20T09:30:00Z"
    assert out["rate_limit_resets_at"] == "2026-08-20T18:00:45Z"


def test_an_aware_value_in_another_zone_is_converted_to_utc() -> None:
    reset = AWARE_RESET.astimezone(timezone(timedelta(hours=8)))
    out = AgentInstanceResponse.model_validate(
        _fields(rate_limit_resets_at=reset)
    ).model_dump(mode="json")
    assert out["rate_limit_resets_at"] == "2026-08-20T18:00:45Z"


def test_the_detail_response_agrees() -> None:
    detail = AgentInstanceDetail.model_validate(
        {**_fields(), "messages": [], "agent_type_name": "claude"}
    )
    out = detail.model_dump(mode="json")
    assert out["started_at"] == "2026-08-20T09:30:00Z"
    assert out["rate_limit_resets_at"] == "2026-08-20T18:00:45Z"
