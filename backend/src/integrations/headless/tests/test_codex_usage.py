"""Integration test: Codex token/rate-limit notifications -> usage PATCH.

Drives ``CodexAppServerSession._handle_notification`` directly (the transport
is irrelevant to notification handling) and asserts the merged usage blob is
stamped onto ``instance_metadata.usage`` with the right cadence:

* ``account/rateLimits/updated`` flushes immediately.
* ``thread/tokenUsage/updated`` is buffered and flushed at ``turn/completed``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from _fakes import FakeAsyncVicoaClient

from integrations.headless.codex_app_server import CodexAppServerSession

INSTANCE_ID = "11111111-1111-1111-1111-111111111111"


def _make_session() -> tuple[CodexAppServerSession, FakeAsyncVicoaClient]:
    vicoa = FakeAsyncVicoaClient()
    session = CodexAppServerSession(
        vicoa_client=vicoa,
        instance_id=INSTANCE_ID,
        cwd=".",
        transport=MagicMock(),
    )
    return session, vicoa


def _usage_patches(vicoa: FakeAsyncVicoaClient) -> list[dict]:
    return [
        c["instance_metadata"]["usage"]
        for c in vicoa.patch_calls
        if c.get("instance_metadata") and "usage" in c["instance_metadata"]
    ]


@pytest.mark.asyncio
async def test_rate_limits_flush_immediately():
    session, vicoa = _make_session()
    await session._handle_notification(
        "account/rateLimits/updated",
        {
            "rateLimits": {
                "primary": {"usedPercent": 63, "resetsAt": None},
                "secondary": {"usedPercent": 41, "resetsAt": None},
                "credits": {"hasCredits": True, "unlimited": False, "balance": "4.10"},
            }
        },
    )
    patches = _usage_patches(vicoa)
    assert len(patches) == 1
    limits = patches[0]["limits"]
    assert [w["id"] for w in limits["windows"]] == ["session", "weekly"]
    assert limits["windows"][0]["used_pct"] == 63.0
    assert limits["credits"] == {"unit": "usd", "remaining": 4.10}


@pytest.mark.asyncio
async def test_token_usage_buffered_until_turn_completed():
    session, vicoa = _make_session()

    await session._handle_notification(
        "thread/tokenUsage/updated",
        {"tokenUsage": {"last": {"totalTokens": 48213}, "modelContextWindow": 272000}},
    )
    # Buffered — nothing stamped yet.
    assert _usage_patches(vicoa) == []

    await session._handle_notification(
        "turn/completed", {"turn": {"status": "completed"}}
    )
    patches = _usage_patches(vicoa)
    assert len(patches) == 1
    assert patches[0]["context"] == {
        "used_tokens": 48213,
        "max_tokens": 272000,
        "cost_usd": None,
    }


@pytest.mark.asyncio
async def test_no_op_turn_completed_does_not_patch():
    session, vicoa = _make_session()
    # A turn with no token/rate-limit notifications must not stamp usage.
    await session._handle_notification(
        "turn/completed", {"turn": {"status": "completed"}}
    )
    assert _usage_patches(vicoa) == []


@pytest.mark.asyncio
async def test_context_and_limits_merge_across_notifications():
    session, vicoa = _make_session()
    await session._handle_notification(
        "account/rateLimits/updated",
        {"rateLimits": {"primary": {"usedPercent": 10, "resetsAt": None}}},
    )
    await session._handle_notification(
        "thread/tokenUsage/updated",
        {"tokenUsage": {"last": {"totalTokens": 100}, "modelContextWindow": 200000}},
    )
    await session._handle_notification(
        "turn/completed", {"turn": {"status": "completed"}}
    )

    last = _usage_patches(vicoa)[-1]
    # Final blob carries both the limits (from the earlier event) and context.
    assert last["context"]["used_tokens"] == 100
    assert last["limits"]["windows"][0]["id"] == "session"
