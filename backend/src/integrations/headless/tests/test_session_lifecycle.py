"""A wrapper must stop itself when its session is closed elsewhere.

Archiving/closing a session from the web or app broadcasts an ``instance-update``
frame over the session's WebSocket. Before this, the WebSocket migration had
dropped the terminate handling the old SSE path carried, so archiving marked the
row terminal but left the agent running in the background — the source of the
accumulated zombie sessions.

These tests pin the decision function. The per-wrapper wiring (setting
``running = False`` / cancelling the task) is asserted structurally so a rename
can't quietly unwire it.
"""

from __future__ import annotations

import inspect

import pytest

from integrations.headless.session_lifecycle import (
    WRAPPER_STOP_STATUSES,
    instance_update_requests_stop,
)


@pytest.mark.parametrize(
    "status", ["COMPLETED", "FAILED", "KILLED", "DISCONNECTED", "DELETED"]
)
def test_terminal_status_requests_stop(status: str):
    assert instance_update_requests_stop({"status": status}) is True


@pytest.mark.parametrize("status", ["ACTIVE", "AWAITING_INPUT", "STARTING", "REVIEWED"])
def test_live_status_does_not_request_stop(status: str):
    # The wrapper's own transitions -- including the AWAITING_INPUT it writes on
    # resume -- must never trip the stop.
    assert instance_update_requests_stop({"status": status}) is False


def test_matching_is_case_insensitive():
    assert instance_update_requests_stop({"status": "completed"}) is True


@pytest.mark.parametrize(
    "body", [{}, {"status": None}, {"status": ""}, "nonsense", None]
)
def test_malformed_bodies_do_not_request_stop(body):
    assert instance_update_requests_stop(body) is False


def test_stop_set_matches_the_backend_terminal_set():
    # Guards against drift from the backend's canonical terminal set.
    from backend.db.queries import _TERMINAL_STATUSES

    assert WRAPPER_STOP_STATUSES == {s.value for s in _TERMINAL_STATUSES}


# --------------------------------------------------------------------------
# Wiring: each wrapper must actually watch instance updates and stop
# --------------------------------------------------------------------------


def test_acp_base_watches_instance_updates_and_stops():
    from integrations.headless import acp_base

    start_src = inspect.getsource(acp_base.ACPWrapperBase._start_ws_client)
    assert "on_instance_update=" in start_src

    handler = inspect.getsource(acp_base.ACPWrapperBase._on_ws_instance_update)
    assert "instance_update_requests_stop" in handler
    assert "self.running = False" in handler


@pytest.mark.parametrize(
    "module_name",
    ["integrations.headless.claude_code", "integrations.headless.codex_native"],
)
def test_async_wrappers_watch_instance_updates_and_stop(module_name: str):
    import importlib

    src = inspect.getsource(importlib.import_module(module_name))
    assert "on_instance_update=" in src
    assert "instance_update_requests_stop" in src
    # The async stop path sets running False and cancels the main task.
    assert "self.running = False" in src
    assert ".cancel()" in src


# --------------------------------------------------------------------------
# The stop guard: a stopping wrapper must not re-open the row it was closing
# --------------------------------------------------------------------------


def _acp_wrapper():
    """A bare ACP wrapper with just the fields _set_agent_status touches."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from integrations.headless.acp_base import ACPWrapperBase

    w = ACPWrapperBase.__new__(ACPWrapperBase)
    w.log = lambda *_a, **_k: None
    w.vicoa_client = MagicMock()
    w.config = SimpleNamespace(agent_instance_id="inst-1", agent_type="opencode")
    w._stopping = False
    return w


def test_acp_status_write_suppressed_while_stopping():
    """A racing in-flight turn calling AWAITING_INPUT after the session was
    archived would otherwise re-open it."""
    w = _acp_wrapper()
    w._stopping = True

    w._set_agent_status("AWAITING_INPUT")

    w.vicoa_client.update_agent_instance_status.assert_not_called()


def test_acp_terminal_status_still_written_while_stopping():
    """The wrapper's own terminal write on shutdown must still go through."""
    w = _acp_wrapper()
    w._stopping = True

    w._set_agent_status("COMPLETED")

    w.vicoa_client.update_agent_instance_status.assert_called_once()


def test_acp_status_write_normal_when_not_stopping():
    w = _acp_wrapper()

    w._set_agent_status("AWAITING_INPUT")

    w.vicoa_client.update_agent_instance_status.assert_called_once()
