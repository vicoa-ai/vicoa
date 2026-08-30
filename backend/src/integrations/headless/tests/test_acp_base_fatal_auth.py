"""Headless ACP wrapper: a Vicoa 401 must end the session, not be swallowed.

A headless agent whose Vicoa link is dead (revoked key / deleted account) is an
invisible orphan — it keeps running with no way to reach the user. The REST
helpers swallow every exception today, so an ``AuthenticationError`` raised by
the SDK on a 401 never reaches the owner. These tests pin that the REST sites
re-raise it and the owner (``run()``) exits cleanly with cleanup.

Rule (plans/todos/cli-401-fatal-auth-handling.md): no human present -> exit.
"""

from __future__ import annotations

import types

import pytest

from integrations.headless.acp_base import ACPWrapperBase
from vicoa.sdk.exceptions import AuthenticationError


class _Stub(ACPWrapperBase):
    def create_session(self) -> None:  # ACPWrapperBase is abstract
        pass


class _AuthRaisingClient:
    def update_agent_instance_status(self, *a, **k):
        raise AuthenticationError("401")

    def send_message(self, *a, **k):
        raise AuthenticationError("401")


def _make_stub(vicoa_client: object) -> _Stub:
    stub = _Stub.__new__(_Stub)
    stub.log = lambda *a, **k: None  # type: ignore[method-assign]
    stub.vicoa_client = vicoa_client
    stub._stopping = False
    stub.config = types.SimpleNamespace(agent_instance_id="inst-1", agent_type="codex")
    return stub


def test_set_agent_status_reraises_authentication_error() -> None:
    """The best-effort status update must let a 401 through so it reaches the
    owner — not log a warning and continue as if nothing happened."""
    stub = _make_stub(_AuthRaisingClient())

    with pytest.raises(AuthenticationError):
        stub._set_agent_status("AWAITING_INPUT")


def test_forward_agent_text_reraises_authentication_error() -> None:
    """Forwarding assistant output must also surface a 401 rather than logging
    an error and continuing — it's the other live REST write in a turn."""
    stub = _make_stub(_AuthRaisingClient())

    with pytest.raises(AuthenticationError):
        stub._forward_agent_text("hello from the agent")


def test_event_loop_reraises_authentication_error(monkeypatch) -> None:
    """The drain loop's broad ``except Exception`` must let a 401 through —
    otherwise it logs the error and keeps spinning forever, and the owner never
    learns the link is dead. A sleep stub raises KeyboardInterrupt so a
    regressed (looping) impl ends the test instead of hanging."""
    stub = _Stub.__new__(_Stub)
    stub.log = lambda *a, **k: None  # type: ignore[method-assign]
    stub.running = True
    # Queue entries are (content, attachments, message_id) — a bare string used
    # to unpack by accident when the tuple was 2-wide.
    stub.message_queue = [("hi", (), None)]
    # Idle: the drain's in-flight guard must fall through to the dispatch (which
    # calls _set_agent_status and raises the 401), not hold the message back.
    stub._prompt_in_flight = False
    stub._assistant_chunk_buffer = []  # falsy -> skip the flush branch

    def _raise(*a, **k):
        raise AuthenticationError("401")

    stub._set_agent_status = _raise  # type: ignore[method-assign]

    def _sleep(_seconds):
        raise KeyboardInterrupt  # safety: a non-stopping loop ends here

    monkeypatch.setattr("integrations.headless.acp_base.time.sleep", _sleep)

    with pytest.raises(AuthenticationError):
        stub._run_event_loop()


def test_run_ends_session_cleanly_on_authentication_error() -> None:
    """The headless owner catches a 401 from the event loop and exits non-zero
    with a terminal status via _cleanup (best-effort) and a clean message —
    not the generic FATAL-error/traceback path."""
    stub = _Stub.__new__(_Stub)
    logs: list[str] = []
    stub.log = lambda msg: logs.append(msg)  # type: ignore[method-assign]
    stub._install_signal_handlers = lambda: None  # type: ignore[method-assign]
    stub._setup = lambda: None  # type: ignore[method-assign]

    def _loop() -> None:
        raise AuthenticationError("401")

    stub._run_event_loop = _loop  # type: ignore[method-assign]

    cleanup: dict = {"called": 0, "status": "UNSET"}

    def _cleanup(final_status=None) -> None:
        cleanup["called"] += 1
        cleanup["status"] = final_status

    stub._cleanup = _cleanup  # type: ignore[method-assign]

    rc = stub.run()

    assert rc == 1
    assert cleanup["called"] == 1
    assert cleanup["status"] == "KILLED"  # best-effort terminal status
    assert any("credential" in m.lower() for m in logs)
    assert not any("Fatal error" in m for m in logs)
