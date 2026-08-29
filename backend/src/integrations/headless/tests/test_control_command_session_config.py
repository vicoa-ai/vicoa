"""Headless Claude wrapper must PATCH session_config when the user
changes permission_mode mid-session via a JSON control message.

Bug: feedback message "Permission mode changed to X" fires (because
`set_permission_mode` on the SDK succeeded), but the row's session_config
stays on the previous value — so the mobile gear sheet keeps showing the
old permission until the next register. This affects daemon-spawned
headless sessions specifically (TUI sessions go through
input_request_manager which already PATCHes at JSON-parse time; headless
has its own _handle_control_command in claude_code.py).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from _fakes import FakeAsyncVicoaClient


pytestmark = pytest.mark.asyncio


def _control(setting: str, value: str) -> str:
    return json.dumps({"type": "control", "setting": setting, "value": value})


async def test_permission_mode_change_patches_session_config(make_runner) -> None:
    """The user clicks "Accept Edits" in the mobile pill. JSON arrives via SSE,
    headless wrapper calls set_permission_mode AND patches session_config."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    runner.session_id = "test-instance"
    # claude_client.set_permission_mode is async; mock so the SDK call
    # succeeds without spinning up a real ClaudeSDKClient.
    runner.claude_client = AsyncMock()
    runner.claude_client.set_permission_mode = AsyncMock(return_value=None)

    handled = await runner._handle_control_command(
        _control("permission_mode", "acceptEdits")
    )
    assert handled is True

    # SDK was told about the change.
    runner.claude_client.set_permission_mode.assert_awaited_once_with("acceptEdits")
    # AND the row was patched — this is the regression fix.
    assert fake.patch_calls == [
        {
            "agent_instance_id": "test-instance",
            "name": None,
            "session_config": {"permission_mode": "acceptEdits"},
            "instance_metadata": None,
        }
    ]


async def test_invalid_permission_mode_skips_patch(make_runner) -> None:
    """Rejected at the validator step — must NOT patch a bogus slug."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    runner.session_id = "test-instance"
    runner.claude_client = AsyncMock()
    runner.claude_client.set_permission_mode = AsyncMock(return_value=None)

    await runner._handle_control_command(_control("permission_mode", "nope"))
    runner.claude_client.set_permission_mode.assert_not_awaited()
    assert fake.patch_calls == []


async def test_sdk_failure_skips_patch(make_runner) -> None:
    """If set_permission_mode raises for a non-auto mode, the row hasn't
    actually changed — don't lie via the patch, and don't reconnect (only
    ``auto`` has a live model gate worth retrying atomically)."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    runner.session_id = "test-instance"
    runner.claude_client = AsyncMock()
    runner.claude_client.set_permission_mode = AsyncMock(
        side_effect=RuntimeError("SDK boom")
    )
    runner._reconnect_claude_client = AsyncMock(return_value=True)

    await runner._handle_control_command(_control("permission_mode", "plan"))
    assert fake.patch_calls == []
    runner._reconnect_claude_client.assert_not_awaited()
    assert runner.permission_mode is None


async def test_auto_recovers_on_live_client_without_reconnect(make_runner) -> None:
    """The CLI rejects the first live set_permission_mode('auto') because the
    live client's model drifted from self.model. Re-assert the model on the
    SAME client and retry — no reconnect — so the status/feedback flow (the
    'vibing' indicator) behaves like any live permission toggle."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    runner.session_id = "test-instance"
    runner.permission_mode = "default"
    runner.model = "claude-opus-4-8"
    runner.claude_client = AsyncMock()
    # First call (live attempt) rejected; second (after the model re-assert)
    # succeeds.
    runner.claude_client.set_permission_mode = AsyncMock(
        side_effect=[RuntimeError("auto mode unavailable for this model"), None]
    )
    runner._reconnect_claude_client = AsyncMock(return_value=True)

    await runner._handle_control_command(_control("permission_mode", "auto"))

    # Model was re-asserted on the live client, and NO reconnect happened.
    runner.claude_client.set_model.assert_awaited_once_with("claude-opus-4-8")
    assert runner.claude_client.set_permission_mode.await_count == 2
    runner._reconnect_claude_client.assert_not_awaited()
    assert runner.permission_mode == "auto"
    assert fake.patch_calls == [
        {
            "agent_instance_id": "test-instance",
            "name": None,
            "session_config": {"permission_mode": "auto"},
            "instance_metadata": None,
        }
    ]


async def test_auto_falls_back_to_reconnect_when_live_reassert_fails(
    make_runner,
) -> None:
    """If the live model re-assert still can't apply auto, fall back to a full
    reconnect and, when it succeeds, PATCH + cache the mode as the live path
    would."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    runner.session_id = "test-instance"
    runner.permission_mode = "default"
    runner.model = "claude-opus-4-8"
    runner.claude_client = AsyncMock()
    # Every live set_permission_mode is rejected (initial + post-re-assert).
    runner.claude_client.set_permission_mode = AsyncMock(
        side_effect=RuntimeError("auto mode unavailable for this model")
    )
    runner._reconnect_claude_client = AsyncMock(return_value=True)

    await runner._handle_control_command(_control("permission_mode", "auto"))

    runner._reconnect_claude_client.assert_awaited_once()
    assert runner.permission_mode == "auto"
    assert fake.patch_calls == [
        {
            "agent_instance_id": "test-instance",
            "name": None,
            "session_config": {"permission_mode": "auto"},
            "instance_metadata": None,
        }
    ]


async def test_auto_reconnect_failure_rolls_back(make_runner) -> None:
    """If both the live re-assert and the reconnect fallback fail, don't PATCH
    and restore the previous mode — the change never took effect."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    runner.session_id = "test-instance"
    runner.permission_mode = "default"
    runner.model = "claude-opus-4-8"
    runner.claude_client = AsyncMock()
    runner.claude_client.set_permission_mode = AsyncMock(
        side_effect=RuntimeError("auto mode unavailable for this model")
    )
    runner._reconnect_claude_client = AsyncMock(return_value=False)

    await runner._handle_control_command(_control("permission_mode", "auto"))

    runner._reconnect_claude_client.assert_awaited_once()
    assert runner.permission_mode == "default"
    assert fake.patch_calls == []
