"""Pure unit tests for the daemon's background key-renewal loop.

The daemon periodically pings ``/api/v1/auth/api-keys/current/renew`` so an
opaque CLI key never lapses while the daemon is alive. A 401 (dead credential)
stops the loop and defers the fatal-auth exit to the heartbeat/main loop; any
other error is transient and just retried. Renewal never touches the token
string, so machine identity is preserved. No DB, no real network.
"""

from __future__ import annotations

import requests
import pytest

from vicoa.machine_daemon import RENEW_ENDPOINT, MachineDaemon


@pytest.fixture
def daemon() -> MachineDaemon:
    return MachineDaemon(api_key="vic_deadbeef", base_url="http://localhost:0")


class _FakeResp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def test_try_renew_posts_to_the_renew_endpoint(
    daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict = {}

    def _post(url, *a, **k):  # noqa: ANN001
        seen["url"] = url
        return _FakeResp(200)

    monkeypatch.setattr(daemon.session, "post", _post)
    daemon._try_renew()

    assert seen["url"].endswith(RENEW_ENDPOINT)
    assert not daemon._stop_renewal.is_set()  # a healthy renew keeps looping


def test_try_renew_stops_loop_on_401(
    daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(daemon.session, "post", lambda *a, **k: _FakeResp(401))

    daemon._try_renew()  # AuthenticationError is caught, not raised

    assert daemon._stop_renewal.is_set()


def test_try_renew_swallows_transient_errors(
    daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(daemon.session, "post", lambda *a, **k: _FakeResp(503))

    daemon._try_renew()  # HTTPError (RequestException) swallowed

    assert not daemon._stop_renewal.is_set()  # keeps retrying next cycle


def test_renewal_never_changes_the_token(
    daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In-place server-side renewal leaves the token string untouched — the
    whole point, so ``api_key_fingerprint`` (and machine identity) is stable."""
    monkeypatch.setattr(daemon.session, "post", lambda *a, **k: _FakeResp(200))
    before = daemon.api_key
    daemon._try_renew()
    assert daemon.api_key == before


def test_connection_error_is_transient(
    daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*a, **k):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr(daemon.session, "post", _boom)
    daemon._try_renew()  # must not raise
    assert not daemon._stop_renewal.is_set()
