"""TUI: session_config PATCH for a UI-driven permission_mode change.

Plan: plans/done/session-config-storage.md TUI follow-up.

Semantics (Option 1 / "PATCH only after confirmed"): the wrapper
delegates to toggle_manager.handle_toggle_request to actually flip
Claude's permission mode. PATCH session_config ONLY when that
returns True, so the row never claims a mode the session can't
actually run as (e.g., user clicks Yolo on a session that wasn't
started with --dangerously-skip-permissions — set_toggle's
send-one-observe loop exhausts its cap and returns False; we must
not lie via the patch).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from integrations.cli_wrappers.claude_code.messaging.input_request_manager import (
    InputRequestManager,
)


INSTANCE_ID = "00000000-0000-0000-0000-000000000001"


class _FakeClient:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def patch_agent_instance(
        self,
        agent_instance_id: str,
        *,
        name: Optional[str] = None,
        session_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.calls.append(
            {
                "agent_instance_id": agent_instance_id,
                "session_config": session_config,
            }
        )
        return {}


def _make_manager(
    client: Optional[_FakeClient] = None,
    *,
    toggle_succeeds: bool = True,
    normalize_returns: Optional[str] = "__as_input__",
) -> InputRequestManager:
    """Build an InputRequestManager via __new__ with just enough state to
    exercise _handle_control_command.

    `normalize_returns`: sentinel `"__as_input__"` means normalize_value
    echoes whatever value was passed; pass None to simulate a rejected
    value; pass any other string to force-return that string.
    """
    mgr = InputRequestManager.__new__(InputRequestManager)
    mgr.agent_instance_id = INSTANCE_ID
    mgr.vicoa_client_sync = client
    mgr.log = lambda _msg: None  # noqa: E731

    toggle = MagicMock()

    def _normalize(setting: str, value: str) -> Optional[str]:
        if normalize_returns == "__as_input__":
            return value
        return normalize_returns

    toggle.normalize_value = _normalize
    toggle.humanize_value = lambda setting, slug: slug or ""
    toggle.handle_toggle_request = lambda setting, value: toggle_succeeds
    toggle.get_all_settings = lambda: ["permission_mode", "thinking"]
    mgr.toggle_manager = toggle

    # Deps unused on the happy/sad paths but required by other branches.
    mgr.message_processor = MagicMock()
    mgr.message_queue = MagicMock()
    mgr.session_state = MagicMock()
    mgr.pty_manager = MagicMock()
    return mgr


def _control_msg(setting: str, value: str) -> str:
    return json.dumps({"type": "control", "setting": setting, "value": value})


def test_permission_mode_patches_only_when_toggle_succeeds() -> None:
    """Happy path — toggle_manager flips the mode; PATCH then fires with
    the confirmed slug so session_config reflects what's actually running."""
    client = _FakeClient()
    mgr = _make_manager(client, toggle_succeeds=True)
    consumed = mgr._handle_control_command(
        _control_msg("permission_mode", "acceptEdits")
    )
    assert consumed is True
    assert client.calls == [
        {
            "agent_instance_id": INSTANCE_ID,
            "session_config": {"permission_mode": "acceptEdits"},
        }
    ]


def test_permission_mode_failure_does_not_patch() -> None:
    """User clicks Yolo on a session that wasn't started with
    --dangerously-skip-permissions: set_toggle's observe loop exhausts
    its cap and returns False. session_config must stay on the old value;
    a failure-feedback message is the only user-visible artifact."""
    client = _FakeClient()
    mgr = _make_manager(client, toggle_succeeds=False)
    consumed = mgr._handle_control_command(
        _control_msg("permission_mode", "bypassPermissions")
    )
    assert consumed is True
    assert client.calls == [], (
        "Wrapper must not PATCH session_config when set_toggle failed — "
        "otherwise the mobile gear shows a mode the session can't run as."
    )


def test_other_settings_do_not_patch() -> None:
    """Only permission_mode is in session_config today. A thinking-toggle
    control must not produce a session_config PATCH even on success."""
    client = _FakeClient()
    mgr = _make_manager(client, toggle_succeeds=True)
    mgr._handle_control_command(_control_msg("thinking", "low"))
    assert client.calls == []


def test_unknown_permission_value_does_not_patch() -> None:
    """If normalize_value rejects the value the toggle_manager
    short-circuits to False; no PATCH."""
    client = _FakeClient()
    mgr = _make_manager(client, toggle_succeeds=False, normalize_returns=None)
    mgr._handle_control_command(_control_msg("permission_mode", "wat"))
    assert client.calls == []


def test_patch_failure_does_not_break_flow() -> None:
    """If the PATCH itself raises (network blip), the control flow must
    still mark the command as consumed; the JSONLMonitor's later
    permission-mode event PATCH provides eventual consistency."""

    class _ExplodingClient:
        def patch_agent_instance(self, *_a, **_kw):
            raise RuntimeError("boom")

    mgr = _make_manager(_ExplodingClient(), toggle_succeeds=True)  # type: ignore[arg-type]
    consumed = mgr._handle_control_command(_control_msg("permission_mode", "plan"))
    assert consumed is True
