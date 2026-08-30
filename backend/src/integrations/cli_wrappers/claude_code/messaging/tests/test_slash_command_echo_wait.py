"""TUI: wait for Claude's slash-command echo before unblocking the next command.

Regression: back-to-back ``model`` + ``effort`` (one mobile gear-pill
confirm) sometimes dropped the second slash command. The wrapper used a
blind ``time.sleep(0.5)`` between PTY writes — borderline against the
TUI's input-echo → command-dispatch → confirmation render cycle, which
can take ~700ms on a slow turn. If the second ``/effort X\\r`` arrived
mid-render, Claude's parser mangled or ignored it.

Fix: snapshot the terminal buffer size before writing, then poll for the
confirmation echo ("Set model to" / "Set effort level to") before
returning. Bounded by ``SLASH_COMMAND_ECHO_TIMEOUT_S``; on timeout we
log + proceed (optimistic PATCH + JSONLMonitor self-heal still cover the
rejected-slug case).
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from integrations.cli_wrappers.claude_code.messaging.input_request_manager import (
    InputRequestManager,
)
from integrations.cli_wrappers.claude_code.terminal.buffer import TerminalBuffer


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
        self.calls.append({"session_config": session_config})
        return {}


def _make_manager(
    client: Optional[_FakeClient] = None,
    *,
    echo_timeout: float = 1.0,
) -> tuple[InputRequestManager, TerminalBuffer]:
    mgr = InputRequestManager.__new__(InputRequestManager)
    mgr.agent_instance_id = INSTANCE_ID
    mgr.vicoa_client_sync = client
    mgr.log = lambda _msg: None  # noqa: E731

    toggle = MagicMock()
    toggle.normalize_value = lambda setting, value: value
    toggle.humanize_value = lambda setting, slug: slug or ""
    toggle.handle_toggle_request = lambda setting, value: True
    toggle.get_all_settings = lambda: ["permission_mode", "thinking"]
    mgr.toggle_manager = toggle

    mgr.message_processor = MagicMock()
    mgr.message_queue = MagicMock()

    # Real terminal_buffer wired through session_state so the polling
    # helper can observe writes from a background thread.
    buf = TerminalBuffer()
    mgr.session_state = MagicMock()
    mgr.session_state.terminal_buffer = buf
    mgr.pty_manager = MagicMock()

    # Shorter timeout keeps the suite fast.
    mgr.SLASH_COMMAND_ECHO_TIMEOUT_S = echo_timeout
    return mgr, buf


def _control_msg(setting: str, value: str) -> str:
    return json.dumps({"type": "control", "setting": setting, "value": value})


def _schedule_echo(buf: TerminalBuffer, text: str, *, after: float) -> threading.Timer:
    timer = threading.Timer(after, lambda: buf.append(text))
    timer.daemon = True
    timer.start()
    return timer


# ---------------------------------------------------------------------------
# /model
# ---------------------------------------------------------------------------


def test_model_change_returns_when_echo_lands() -> None:
    """Once 'Set model to' appears in the buffer the helper returns —
    the next control command can proceed immediately."""
    client = _FakeClient()
    mgr, buf = _make_manager(client)
    _schedule_echo(
        buf,
        "⎿ Set model to Sonnet 4.6 …",
        after=0.15,
    )

    start = time.time()
    consumed = mgr._handle_control_command(_control_msg("model", "claude-sonnet-4-6"))
    elapsed = time.time() - start

    assert consumed is True
    assert elapsed < 0.5, f"should return ~once echo lands, took {elapsed:.2f}s"
    assert client.calls and client.calls[-1]["session_config"] == {
        "agent": "claude",
        "model": "claude-sonnet-4-6",
    }


def test_model_change_ignores_stale_echo_in_buffer() -> None:
    """A 'Set model to' echo from a previous toggle is already in the
    buffer. The helper must snapshot the buffer size before writing so
    the new write actually triggers a wait — otherwise we'd return
    immediately and race the next slash command into Claude's input
    mid-render."""
    client = _FakeClient()
    mgr, buf = _make_manager(client, echo_timeout=0.25)
    buf.append("⎿ Set model to Opus 4.7 …\n")
    # No fresh echo scheduled — the call must hit the timeout.

    start = time.time()
    mgr._handle_control_command(_control_msg("model", "claude-haiku-4-5"))
    elapsed = time.time() - start

    assert elapsed >= 0.25, (
        "snapshot bug: helper returned on stale echo instead of waiting "
        f"for the new one (took {elapsed:.2f}s)"
    )


def test_model_change_proceeds_after_timeout() -> None:
    """No echo within the timeout: log + proceed. PATCH still fires;
    JSONLMonitor self-heals if Claude actually rejected the slug."""
    client = _FakeClient()
    mgr, _ = _make_manager(client, echo_timeout=0.2)

    consumed = mgr._handle_control_command(_control_msg("model", "claude-sonnet-4-6"))

    assert consumed is True
    assert client.calls, "PATCH must still fire on timeout — JSONLMonitor self-heals"


# ---------------------------------------------------------------------------
# /effort
# ---------------------------------------------------------------------------


def test_effort_change_returns_when_echo_lands() -> None:
    client = _FakeClient()
    mgr, buf = _make_manager(client)
    _schedule_echo(
        buf,
        "⎿ Set effort level to high …",
        after=0.15,
    )

    start = time.time()
    consumed = mgr._handle_control_command(_control_msg("effort", "high"))
    elapsed = time.time() - start

    assert consumed is True
    assert elapsed < 0.5
    assert client.calls and client.calls[-1]["session_config"] == {
        "agent": "claude",
        "thinking_effort": "high",
    }


# ---------------------------------------------------------------------------
# Back-to-back simulates the real failure: model + effort in one confirm.
# Each PTY write triggers a delayed echo, so the second command must wait
# until the first one's confirmation lands before being issued.
# ---------------------------------------------------------------------------


def test_back_to_back_model_then_effort_waits_serially() -> None:
    """The full repro: mobile sends model AND effort in one batch. With
    only ``time.sleep(0.5)`` between the writes, Claude's render of the
    first command sometimes overruns the second arrival and the
    ``/effort`` write is eaten."""
    client = _FakeClient()
    mgr, buf = _make_manager(client)

    pty_writes: List[bytes] = []

    def _on_write(data: bytes) -> None:
        pty_writes.append(data)
        # Append the matching echo ~250ms after each write.
        if data.startswith(b"/model"):
            _schedule_echo(buf, "⎿ Set model to Sonnet 4.6 …\n", after=0.25)
        elif data.startswith(b"/effort"):
            _schedule_echo(buf, "⎿ Set effort level to high …\n", after=0.25)

    mgr.pty_manager.write_to_pty = _on_write

    mgr._handle_control_command(_control_msg("model", "claude-sonnet-4-6"))
    second_write_time = time.time()
    mgr._handle_control_command(_control_msg("effort", "high"))
    second_done = time.time()

    # Both writes reached the PTY.
    assert any(w.startswith(b"/model") for w in pty_writes)
    assert any(w.startswith(b"/effort") for w in pty_writes)
    # Both PATCHes fired.
    settings_keys = {
        next(iter((call["session_config"] or {"k": None}).keys() - {"agent"}))
        for call in client.calls
    }
    assert "model" in settings_keys
    assert "thinking_effort" in settings_keys
    # The /effort handler returned promptly once its own echo landed
    # (~250ms), not after a 3s timeout.
    assert second_done - second_write_time < 0.6
