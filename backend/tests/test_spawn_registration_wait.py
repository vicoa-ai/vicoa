"""The spawn RPC holds until the child registers, and reports why it didn't.

Covers vicoa/session_markers.py (runner → daemon signal) and
MachineDaemon._wait_for_registration (the daemon side of the same contract).
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from vicoa import session_markers
from vicoa.machine_daemon import MachineDaemon
from vicoa.session_markers import (
    clear_session_registered,
    mark_session_registered,
    registered_marker_path,
)


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    return tmp_path


@pytest.fixture
def daemon() -> MachineDaemon:
    return MachineDaemon(api_key="test-key", base_url="http://localhost:0")


class _FakeProcess:
    """Just enough of Popen for the wait loop."""

    def __init__(self, exit_code: int | None = None) -> None:
        self._exit_code = exit_code
        self.terminated = False

    def poll(self) -> int | None:
        return self._exit_code

    def terminate(self) -> None:
        self.terminated = True
        self._exit_code = -15


# ----- marker -----


def test_marker_round_trip(_home: Path) -> None:
    mark_session_registered("s1")
    assert registered_marker_path("s1").exists()
    assert registered_marker_path("s1").is_relative_to(_home)
    clear_session_registered("s1")
    assert not registered_marker_path("s1").exists()
    # Idempotent.
    clear_session_registered("s1")


def test_marker_write_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_: Any, **__: Any) -> None:
        raise OSError("read-only fs")

    monkeypatch.setattr(session_markers.Path, "write_bytes", _boom)
    mark_session_registered("s1")  # must not raise


# ----- daemon wait -----


def test_wait_returns_once_the_marker_appears(daemon: MachineDaemon) -> None:
    process = _FakeProcess()
    threading.Timer(0.1, mark_session_registered, args=("s1",)).start()

    assert daemon._wait_for_registration("s1", process, timeout=2.0) is None  # type: ignore[arg-type]
    # Consumed: the marker does not linger for the next run of this id.
    assert not registered_marker_path("s1").exists()
    assert not process.terminated


def test_wait_reports_the_childs_last_stderr_line(
    daemon: MachineDaemon, _home: Path
) -> None:
    stderr = daemon._session_stderr_path("s1")
    stderr.parent.mkdir(parents=True)
    stderr.write_text("Traceback ...\nFatal error before registration: 503 busy\n")

    failure = daemon._wait_for_registration(
        "s1", _FakeProcess(exit_code=1), timeout=2.0
    )  # type: ignore[arg-type]

    assert (
        failure
        == "Couldn't start the session: Fatal error before registration: 503 busy"
    )


def test_wait_reports_generic_message_when_stderr_is_empty(
    daemon: MachineDaemon,
) -> None:
    failure = daemon._wait_for_registration(
        "s1", _FakeProcess(exit_code=2), timeout=2.0
    )  # type: ignore[arg-type]
    assert failure == (
        "Couldn't start the session. The agent exited unexpectedly, please try again."
    )


def test_wait_terminates_a_child_that_never_registers(daemon: MachineDaemon) -> None:
    process = _FakeProcess()
    failure = daemon._wait_for_registration("s1", process, timeout=0.2, interval=0.02)  # type: ignore[arg-type]
    assert failure is not None
    assert failure == (
        "Couldn't start the session. It didn't come online in time, please try again."
    )
    assert process.terminated


def test_wait_budget_fits_under_the_rpc_timeout() -> None:
    from shared.websocket.rpc import DEFAULT_TIMEOUT
    from vicoa.machine_daemon import REGISTRATION_WAIT_SECONDS
    from integrations.utils.registration import REGISTRATION_TOTAL_BUDGET_SECONDS

    # Runner budget < daemon wait (process-start slack) < server RPC timeout.
    assert REGISTRATION_TOTAL_BUDGET_SECONDS < REGISTRATION_WAIT_SECONDS
    assert REGISTRATION_WAIT_SECONDS < DEFAULT_TIMEOUT


# ----- runners never mint a row for a failure that happened before registration -----


def test_acp_startup_failure_before_registration_goes_to_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock

    from integrations.headless.acp_base import ACPWrapperBase

    wrapper = ACPWrapperBase.__new__(ACPWrapperBase)
    wrapper.vicoa_client = Mock()
    wrapper.config = SimpleNamespace(agent_instance_id="inst-1", agent_type="acp")
    wrapper.log = lambda message: None
    wrapper._registered = False

    wrapper._report_startup_failure(RuntimeError("503 busy"))

    # Posting would create the instance row; stderr is what the daemon reads.
    wrapper.vicoa_client.send_message.assert_not_called()
    assert "Fatal error before registration: 503 busy" in capsys.readouterr().err


async def test_pi_startup_failure_before_registration_goes_to_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from unittest.mock import AsyncMock

    from integrations.headless.pi_family.runner import PiFamilyRunner

    runner = PiFamilyRunner.__new__(PiFamilyRunner)
    runner.vicoa_client = AsyncMock()
    runner.session_id = "inst-1"
    runner.agent_name = "pi"
    runner._registered = False

    await runner._report_startup_failure("pi couldn't start: 503 busy")

    runner.vicoa_client.send_message.assert_not_called()
    assert "Fatal error before registration" in capsys.readouterr().err
