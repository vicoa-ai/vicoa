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
    assert len(persisted) == 1
    assert persisted[0]["daemon_pid"] is None
    assert persisted[0]["machine_limit_at"]
    # The credential is fine — only the plan is full.
    assert "auth_invalid_at" not in persisted[0]


def test_the_servers_sentence_is_stamped_for_other_surfaces(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """The CLI and the desktop both explain this from the state file, not from
    the daemon's stdout — a spawned daemon's output goes to DEVNULL and
    nobody watches the desktop's child process."""
    persisted: list[dict] = []
    monkeypatch.setattr(daemon, "_persist_entry", persisted.append)

    with pytest.raises(MachineLimitReached):
        daemon._raise_for_machine_limit(
            _FakeResp(
                402,
                {
                    "detail": "Your plan includes 1 machine.",
                    "capability": "limit.machines",
                },
            )
        )
    daemon._handle_machine_limit()

    assert daemon.machine_limit_detail == "Your plan includes 1 machine."
    assert persisted[0]["machine_limit_detail"] == "Your plan includes 1 machine."


def test_a_successful_register_clears_the_stamp(
    daemon: MachineDaemon, monkeypatch
) -> None:
    """Freeing a machine elsewhere, or upgrading, heals it on the next launch
    without the user having to find and clear anything by hand."""
    monkeypatch.setattr(
        "vicoa.machine_daemon.migrate_legacy_flat_state", lambda base_url: None
    )
    monkeypatch.setattr(daemon, "_load_entry", lambda: {"machine_id": "m-1"})
    persisted: list[dict] = []
    monkeypatch.setattr(daemon, "_persist_entry", persisted.append)
    monkeypatch.setattr(
        daemon.session,
        "post",
        lambda *a, **k: _FakeResp(
            200,
            {
                "machine_id": "m-1",
                "display_name": None,
                "hostname": "h",
                "platform": "p",
            },
        ),
    )

    daemon.register_machine()

    stamped = [e for e in persisted if "machine_limit_at" in e]
    assert stamped and stamped[-1]["machine_limit_at"] is None
    assert stamped[-1]["machine_limit_detail"] is None


class TestSpawnGate:
    """`ensure_background_daemon_running` must not re-spawn into the same
    refusal. A CLI-spawned daemon runs with stdout at DEVNULL, so a retry loop
    here would be both silent to the user and a stream of 402s at the server.
    """

    def _state(self, tmp_path, entry: dict):
        """Written through the real writer so the test cannot drift from the
        on-disk schema."""
        from vicoa.machine_state import write_daemon_entry

        path = tmp_path / "daemon_state.json"
        write_daemon_entry("https://api.example.com", entry, path)
        return path

    def test_a_stamped_limit_stops_the_spawn(self, tmp_path, monkeypatch) -> None:
        from vicoa import machine_daemon as md

        state = self._state(tmp_path, {"machine_limit_at": "2026-11-01T00:00:00+00:00"})
        monkeypatch.setattr(md, "migrate_legacy_flat_state", lambda *a, **k: None)
        monkeypatch.setattr(md, "_reset_state_on_identity_change", lambda *a, **k: None)

        result = md.ensure_background_daemon_running(
            api_key="k", base_url="https://api.example.com", state_path=state
        )
        assert result is md.DaemonStartResult.MACHINE_LIMIT

    def test_no_stamp_spawns_as_usual(self, tmp_path, monkeypatch) -> None:
        from vicoa import machine_daemon as md

        state = self._state(tmp_path, {})
        monkeypatch.setattr(md, "migrate_legacy_flat_state", lambda *a, **k: None)
        monkeypatch.setattr(md, "_reset_state_on_identity_change", lambda *a, **k: None)
        monkeypatch.setattr(md, "find_running_daemon_pid", lambda *a, **k: None)
        monkeypatch.setattr(md, "build_daemon_command", lambda **k: ["true"])

        result = md.ensure_background_daemon_running(
            api_key="k", base_url="https://api.example.com", state_path=state
        )
        assert result is not md.DaemonStartResult.MACHINE_LIMIT
