"""A 402 on `/machines/register` is a plan answer, not a crash.

Registration hard-failing is not a cosmetic problem: `run()` calls
`register_machine()` first, and on the desktop a raised `HTTPError` there takes
the whole setup flow down with a traceback. A plan-capacity refusal has to wind
the daemon down with a message the user can act on, and — unlike a 401 — must
leave the credential alone, because signing in again fixes nothing.

Pure unit tests: no DB, no real network, no state-file writes.
"""

from __future__ import annotations

import pytest
import requests

from vicoa.machine_daemon import MachineDaemon
from vicoa.sdk.exceptions import MachineLimitReached


@pytest.fixture
def daemon(monkeypatch) -> MachineDaemon:
    d = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    # Never touch the real ~/.vicoa state file.
    monkeypatch.setattr(d, "_persist_entry", lambda updates: None)
    return d


class _FakeResp:
    """Mimics the slice of ``requests.Response`` the daemon touches."""

    def __init__(self, status_code: int, json_body: dict | None = None) -> None:
        self.status_code = status_code
        self._json = json_body
        self.text = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self) -> dict:
        if self._json is None:
            raise ValueError("not json")
        return self._json


def test_402_for_machines_raises_a_typed_error(daemon: MachineDaemon) -> None:
    response = _FakeResp(
        402,
        {"detail": "Your plan includes 1 machines.", "capability": "limit.machines"},
    )
    with pytest.raises(MachineLimitReached) as exc:
        daemon._raise_for_machine_limit(response)
    assert exc.value.detail == "Your plan includes 1 machines."
    assert daemon.machine_limit_reached is True


def test_the_detail_survives_for_the_user_to_read(daemon: MachineDaemon) -> None:
    """The server's sentence is the only upgrade copy the daemon has; a generic
    fallback here would hide which limit was hit."""
    with pytest.raises(MachineLimitReached) as exc:
        daemon._raise_for_machine_limit(
            _FakeResp(402, {"detail": "Custom reason", "capability": "limit.machines"})
        )
    assert "Custom reason" in str(exc.value)


def test_a_402_for_another_capability_is_left_alone(daemon: MachineDaemon) -> None:
    """Only the machines capability is about this host's right to exist. Any
    other 402 falls through to raise_for_status rather than silently killing
    the daemon."""
    daemon._raise_for_machine_limit(
        _FakeResp(402, {"detail": "seats", "capability": "collab.team_seat"})
    )
    assert daemon.machine_limit_reached is False


def test_a_402_with_an_unreadable_body_still_stops_registration(
    daemon: MachineDaemon,
) -> None:
    """A proxy-generated 402 has no JSON. Treat it as the machine limit — it is
    the only 402 this endpoint can produce — with generic copy."""
    with pytest.raises(MachineLimitReached):
        daemon._raise_for_machine_limit(_FakeResp(402, None))


@pytest.mark.parametrize("status", [200, 401, 403, 500])
def test_other_statuses_pass_through(daemon: MachineDaemon, status: int) -> None:
    daemon._raise_for_machine_limit(_FakeResp(status, {}))
    assert daemon.machine_limit_reached is False


def test_register_machine_surfaces_the_limit_instead_of_http_error(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """End to end through `register_machine`: the caller sees
    MachineLimitReached, never requests.HTTPError."""
    monkeypatch.setattr(
        "vicoa.machine_daemon.migrate_legacy_flat_state", lambda base_url: None
    )
    monkeypatch.setattr(daemon, "_load_entry", lambda: {"machine_id": "m-1"})
    monkeypatch.setattr(
        daemon.session,
        "post",
        lambda *a, **k: _FakeResp(
            402, {"detail": "no room", "capability": "limit.machines"}
        ),
    )
    with pytest.raises(MachineLimitReached):
        daemon.register_machine()


def test_the_credential_is_not_faulted(daemon: MachineDaemon) -> None:
    """The key is fine — only the plan is full. Stamping fatal-auth would send
    the user through a pointless re-login that cannot fix it."""
    with pytest.raises(MachineLimitReached):
        daemon._raise_for_machine_limit(
            _FakeResp(402, {"capability": "limit.machines"})
        )
    assert daemon.fatal_auth is False


def test_handle_machine_limit_reports_status_without_auth_stamp(
    daemon: MachineDaemon, monkeypatch
) -> None:
    persisted: list[dict] = []
    statuses: list[str] = []
    monkeypatch.setattr(daemon, "_persist_entry", persisted.append)
    daemon.on_cloud_status = statuses.append

    daemon._handle_machine_limit()

    assert statuses == ["machine_limit"]
    assert persisted == [{"daemon_pid": None}]
    assert all("auth_invalid_at" not in entry for entry in persisted)
