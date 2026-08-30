"""Pure unit tests: a REST 401 from the agent server is a *fatal-auth* signal.

The daemon must surface an agent-server 401 as ``AuthenticationError`` so it
escapes the broad ``except RequestException`` blocks in the heartbeat/poll
loops, instead of being swallowed and retried forever (the deleted-user FK
storm, plans/bugs/p0-agent-jwt-no-db-validation.md). ``AuthenticationError``
is deliberately NOT a ``RequestException`` subclass so those broad catches
don't re-swallow it.

No DB, no real network, no state-file writes.
"""

from __future__ import annotations

import threading

import requests
import pytest

from vicoa.machine_daemon import MachineDaemon
from vicoa.sdk.exceptions import AuthenticationError


@pytest.fixture
def daemon() -> MachineDaemon:
    return MachineDaemon(api_key="test-key", base_url="http://localhost:0")


class _FakeResp:
    """Mimics the slice of ``requests.Response`` the daemon touches."""

    def __init__(self, status_code: int, json_body: dict | None = None) -> None:
        self.status_code = status_code
        self._json = json_body or {}
        self.text = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self) -> dict:
        return self._json


def test_send_heartbeat_raises_authentication_error_on_401(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """A 401 heartbeat must raise AuthenticationError, not be swallowed by the
    method's ``except RequestException`` (which is how it loops forever today)."""
    daemon.machine_id = "mac-1"
    monkeypatch.setattr(daemon.session, "post", lambda *a, **k: _FakeResp(401))

    with pytest.raises(AuthenticationError):
        daemon.send_heartbeat()


def test_poll_for_requests_raises_authentication_error_on_401(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """poll runs in the SSE/WS catch-up path; a 401 must escape its
    ``except RequestException``/``except Timeout`` instead of returning None
    (which reads as 'no requests' and loops forever)."""
    daemon.machine_id = "mac-1"
    monkeypatch.setattr(daemon.session, "post", lambda *a, **k: _FakeResp(401))

    with pytest.raises(AuthenticationError):
        daemon.poll_for_requests()


def test_report_request_status_raises_authentication_error_on_401(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """report_request_status PATCHes; a 401 must escape its ``except
    RequestException`` (and not be mistaken for the 400 missing-agent retry)."""
    daemon.machine_id = "mac-1"
    monkeypatch.setattr(daemon.session, "patch", lambda *a, **k: _FakeResp(401))

    with pytest.raises(AuthenticationError):
        daemon.report_request_status("req-1", "completed")


def test_update_instance_status_raises_authentication_error_on_401(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """The best-effort terminal-status PUT must still raise on 401 so a dead
    credential surfaces (the headless owner does this write right before exit)."""
    daemon.machine_id = "mac-1"
    monkeypatch.setattr(daemon.session, "put", lambda *a, **k: _FakeResp(401))

    with pytest.raises(AuthenticationError):
        daemon._update_instance_status("inst-1", "disconnected")


def test_register_machine_raises_authentication_error_on_401(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """register_machine runs before the daemon threads start, so its 401 must
    raise the fatal-auth type (AuthenticationError) — not a plain HTTPError —
    so ``run()``'s top-level catch recognises it."""
    monkeypatch.setattr(daemon, "_load_entry", lambda: {})
    monkeypatch.setattr(daemon, "_persist_entry", lambda updates: None)
    monkeypatch.setattr(daemon, "_detect_available_agents", lambda: {})
    monkeypatch.setattr(daemon.session, "post", lambda *a, **k: _FakeResp(401))

    with pytest.raises(AuthenticationError):
        daemon.register_machine()


class _FakeStreamCM:
    """Context manager standing in for ``session.get(..., stream=True)``."""

    def __init__(self, resp: _FakeResp) -> None:
        self._resp = resp

    def __enter__(self) -> _FakeResp:
        return self._resp

    def __exit__(self, *exc: object) -> bool:
        return False


def test_sse_connect_raises_authentication_error_on_401(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """The SSE stream GET must raise AuthenticationError on 401 so it escapes
    the SSE reconnect loop's broad ``except Exception`` (infinite backoff today)
    rather than being treated as a transient connection drop."""
    daemon.machine_id = "mac-1"
    monkeypatch.setattr(
        daemon.session, "get", lambda *a, **k: _FakeStreamCM(_FakeResp(401))
    )

    with pytest.raises(AuthenticationError):
        daemon._sse_connect_and_process()


def test_non_401_heartbeat_is_still_swallowed(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """A transient 5xx is NOT fatal-auth: heartbeat keeps swallowing it (so the
    daemon retries) rather than surfacing AuthenticationError."""
    daemon.machine_id = "mac-1"
    monkeypatch.setattr(daemon.session, "post", lambda *a, **k: _FakeResp(503))

    # Must not raise — returns quietly so the loop retries.
    assert daemon.send_heartbeat() is None


def test_non_401_poll_returns_none(daemon: MachineDaemon, monkeypatch) -> None:
    """A non-401, non-2xx poll response is still treated as 'no requests'."""
    daemon.machine_id = "mac-1"
    monkeypatch.setattr(daemon.session, "post", lambda *a, **k: _FakeResp(500))

    assert daemon.poll_for_requests() is None


# ---------------------------------------------------------------------------
# Daemon lifecycle: _fatal_auth event, background -> flag + exit
# ---------------------------------------------------------------------------


def test_rest_401_sets_fatal_auth_event(daemon: MachineDaemon, monkeypatch) -> None:
    """A 401 on any REST call sets the shared ``_fatal_auth`` event — the
    cross-thread signal a background heartbeat thread uses to tell the main
    loop to stop the stream and exit."""
    daemon.machine_id = "mac-1"
    monkeypatch.setattr(daemon.session, "post", lambda *a, **k: _FakeResp(401))

    assert not daemon._fatal_auth.is_set()
    with pytest.raises(AuthenticationError):
        daemon.send_heartbeat()
    assert daemon._fatal_auth.is_set()


def test_handle_fatal_auth_persists_flag_and_nulls_pid(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """On fatal-auth the daemon stamps ``auth_invalid_at`` and nulls
    ``daemon_pid`` (so a foreground launch won't see us as the live owner),
    while keeping machine_id/display_name/fingerprint via the merging persist."""
    captured: dict = {}
    monkeypatch.setattr(
        daemon, "_persist_entry", lambda updates: captured.update(updates)
    )

    daemon._handle_fatal_auth()

    assert captured["daemon_pid"] is None
    assert isinstance(captured["auth_invalid_at"], str)
    assert captured["auth_invalid_at"]  # non-empty ISO timestamp
    # Identity keys are NOT overwritten — the merge keeps them.
    assert "machine_id" not in captured
    assert "api_key_fingerprint" not in captured


def test_register_machine_clears_auth_invalid_at_on_success(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """A successful (re-)registration is the only heal path: it explicitly
    clears any prior ``auth_invalid_at`` stamp so a recovered credential goes
    back to normal operation."""
    captured: dict = {}
    monkeypatch.setattr(daemon, "_load_entry", lambda: {})
    monkeypatch.setattr(
        daemon, "_persist_entry", lambda updates: captured.update(updates)
    )
    monkeypatch.setattr(daemon, "_detect_available_agents", lambda: {})
    monkeypatch.setattr(
        daemon.session,
        "post",
        lambda *a, **k: _FakeResp(
            200,
            {
                "machine_id": "mac-1",
                "display_name": None,
                "hostname": "h",
                "platform": "p",
            },
        ),
    )

    daemon.register_machine()

    assert "auth_invalid_at" in captured  # explicitly cleared, not just absent
    assert captured["auth_invalid_at"] is None


def test_run_handles_fatal_auth_from_register(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """``register_machine`` runs before the daemon threads start. Its 401 must
    be caught by ``run()``'s top-level handler — flag state + clean return
    (process exit 0) — not propagate and crash the daemon."""

    def _boom() -> None:
        raise AuthenticationError("401")

    handled = {"n": 0}
    monkeypatch.setattr(daemon, "register_machine", _boom)
    monkeypatch.setattr(
        daemon, "_handle_fatal_auth", lambda: handled.__setitem__("n", handled["n"] + 1)
    )

    daemon.run()  # must return cleanly, not raise

    assert handled["n"] == 1


def test_run_does_not_flag_on_keyboard_interrupt(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """A normal Ctrl-C shutdown is not a credential failure — ``run()`` must
    not stamp ``auth_invalid_at``."""
    monkeypatch.setattr(daemon, "register_machine", lambda: None)
    monkeypatch.setattr(daemon, "send_heartbeat", lambda: None)
    monkeypatch.setattr(daemon, "_catchup_poll", lambda: None)

    def _interrupt() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(daemon, "_listen_for_spawn_requests", _interrupt)
    handled = {"n": 0}
    monkeypatch.setattr(
        daemon, "_handle_fatal_auth", lambda: handled.__setitem__("n", handled["n"] + 1)
    )

    daemon.run()

    assert handled["n"] == 0


def test_sse_listener_stops_on_fatal_auth(daemon: MachineDaemon, monkeypatch) -> None:
    """The SSE reconnect loop must break once a 401 sets ``_fatal_auth``, not
    treat it as a transient drop and back off forever. A safety counter raises
    KeyboardInterrupt on the 2nd connect so a regressed (looping) impl
    terminates the test instead of hanging."""
    daemon.machine_id = "mac-1"
    monkeypatch.setattr(daemon, "_catchup_poll", lambda: None)

    calls = {"n": 0}

    def _fake_get(*a, **k):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise KeyboardInterrupt  # safety: a non-stopping loop ends here
        return _FakeStreamCM(_FakeResp(401))

    monkeypatch.setattr(daemon.session, "get", _fake_get)

    daemon._sse_listen_for_spawn_requests()

    assert daemon._fatal_auth.is_set()
    assert calls["n"] == 1  # stopped after the first 401, did not reconnect


def test_ws_heartbeat_stops_client_on_fatal_auth(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """On the WebSocket transport the heartbeat is the authoritative stopper:
    a 401 on the heartbeat thread must stop the WS client so ``client.run()``
    returns and the listener exits — otherwise the client reconnects forever."""
    daemon.machine_id = "mac-1"
    daemon.ws_url = "wss://agents.example/ws"
    daemon._last_heartbeat_sent = 0.0  # force a heartbeat on the first tick

    created: dict = {}

    class _FakeWsClient:
        def __init__(self, **kwargs: object) -> None:
            created["client"] = self
            self._stopped = threading.Event()
            self.stop_called = 0

        def run(self) -> None:
            # Block like the real reconnect loop until stop() is called.
            self._stopped.wait()

        def stop(self) -> None:
            self.stop_called += 1
            self._stopped.set()

    monkeypatch.setattr("vicoa.machine_daemon.SpawnRequestWsClient", _FakeWsClient)

    def _hb() -> None:
        daemon._fatal_auth.set()  # mimic _raise_for_auth
        raise AuthenticationError("401")

    monkeypatch.setattr(daemon, "send_heartbeat", _hb)

    listener = threading.Thread(
        target=daemon._ws_listen_for_spawn_requests, daemon=True
    )
    listener.start()
    listener.join(timeout=3)

    assert not listener.is_alive()  # returned, did not hang reconnecting
    assert daemon._fatal_auth.is_set()
    assert created["client"].stop_called >= 1
