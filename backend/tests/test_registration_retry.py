"""Registration is retried inside a fixed budget, and never past a refusal.

Pins the contract of integrations/utils/registration.py: a slow server gets
a few tries, a refusing server (bad key, quota) gets none, and the whole
schedule stays inside the window the daemon and the app are still waiting.
"""

from __future__ import annotations

import asyncio
import logging
import time

import pytest

from integrations.utils import registration as reg
from integrations.utils.registration import (
    RegistrationError,
    register_with_retry,
    register_with_retry_sync,
)
from vicoa.sdk.exceptions import APIError, AuthenticationError

log = logging.getLogger("test")


@pytest.fixture(autouse=True)
def _fast_schedule(monkeypatch: pytest.MonkeyPatch):
    """Compress the schedule so the suite stays quick."""
    monkeypatch.setattr(reg, "REGISTRATION_ATTEMPT_OFFSETS", (0.0, 0.05, 0.1))
    monkeypatch.setattr(reg, "_JITTER_SECONDS", 0.0)


# ----- async -----


async def test_first_success_returns_immediately() -> None:
    calls = 0

    async def attempt() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    assert await register_with_retry(attempt, log=log, label="t") == "ok"
    assert calls == 1


async def test_retries_a_stalling_server_then_succeeds() -> None:
    calls = 0

    async def attempt() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise APIError(503, "busy")
        if calls == 2:
            await asyncio.sleep(10)  # hangs — must be cut by the attempt timeout
        return "ok"

    result = await register_with_retry(
        attempt, log=log, label="t", attempt_timeout=0.05, total_budget=5.0
    )
    assert result == "ok"
    assert calls == 3


async def test_gives_up_after_the_schedule() -> None:
    async def attempt() -> str:
        raise APIError(503, "busy")

    with pytest.raises(RegistrationError, match="after 3 attempts"):
        await register_with_retry(attempt, log=log, label="t", total_budget=5.0)


async def test_budget_caps_the_schedule() -> None:
    calls = 0

    async def attempt() -> str:
        nonlocal calls
        calls += 1
        await asyncio.sleep(10)
        return "never"

    started = time.monotonic()
    with pytest.raises(RegistrationError):
        await register_with_retry(
            attempt, log=log, label="t", attempt_timeout=1.0, total_budget=0.15
        )
    # One attempt cut at the budget; the later offsets fall outside it.
    assert time.monotonic() - started < 1.0
    assert calls <= 2


@pytest.mark.parametrize(
    "exc",
    [AuthenticationError("bad key"), APIError(402, "quota"), APIError(400, "bad")],
)
async def test_refusals_are_not_retried(exc: Exception) -> None:
    calls = 0

    async def attempt() -> str:
        nonlocal calls
        calls += 1
        raise exc

    with pytest.raises(type(exc)):
        await register_with_retry(attempt, log=log, label="t")
    assert calls == 1


# ----- sync -----


def test_sync_retries_then_succeeds() -> None:
    calls = 0

    def attempt() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise APIError(502, "bad gateway")
        if calls == 2:
            time.sleep(1.0)  # overruns the attempt timeout; abandoned
        return "ok"

    assert (
        register_with_retry_sync(
            attempt, log=log, label="t", attempt_timeout=0.05, total_budget=5.0
        )
        == "ok"
    )
    assert calls == 3


def test_sync_refusal_is_not_retried() -> None:
    calls = 0

    def attempt() -> str:
        nonlocal calls
        calls += 1
        raise AuthenticationError("bad key")

    with pytest.raises(AuthenticationError):
        register_with_retry_sync(attempt, log=lambda msg: None, label="t")
    assert calls == 1


def test_sync_gives_up_after_the_schedule() -> None:
    def attempt() -> str:
        raise APIError(503, "busy")

    with pytest.raises(RegistrationError, match="after 3 attempts"):
        register_with_retry_sync(attempt, log=log, label="t", total_budget=5.0)
