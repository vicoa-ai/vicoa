"""Bounded, idempotent agent-instance registration for headless runners.

Registration used to be one attempt behind a hard 10 s ``wait_for``. During
the 2026-09-14 incident the server took 5-60 s per request under CPU
throttling: the runner gave up at 10 s, the request it abandoned then
*succeeded* server-side, and the runner's fatal-error report minted a second,
orphaned row (plans/todos/connection-driven-liveness-and-hibernation.md §4.3).

This module replaces that with a small retry schedule inside a fixed total
budget. Retrying is safe because registration is idempotent by instance id:
the SDK turns a 409 into a read of the existing row, and the server answers a
same-owner re-register with 200. The budget matters as much as the retry —
past ~30 s every caller has stopped waiting (the RPC route times out at 30 s,
the mobile spawn poll at ~36 s) and a late success becomes an invisible
zombie, so the schedule stays well inside that window.
"""

from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
from typing import Awaitable, Callable, TypeVar

from vicoa.sdk.exceptions import APIError, AuthenticationError
from vicoa.sdk.exceptions import TimeoutError as SdkTimeoutError

T = TypeVar("T")

# Per-attempt cap. Under a healthy server registration takes ~0.4 s; anything
# past this is the server stalling, and the next attempt is more likely to
# land on a healthy burst than waiting on this one.
REGISTRATION_ATTEMPT_TIMEOUT_SECONDS = 8.0
# When each attempt may start, measured from the first. Three tries.
REGISTRATION_ATTEMPT_OFFSETS: tuple[float, ...] = (0.0, 4.0, 10.0)
# Hard ceiling for the whole schedule. Sized against the daemon's own wait
# (`machine_daemon.REGISTRATION_WAIT_SECONDS`, which adds process-start
# slack) and the 30 s RPC timeout behind it.
REGISTRATION_TOTAL_BUDGET_SECONDS = 20.0
_JITTER_SECONDS = 1.0

# Retryable API statuses: the server said "not now", not "no".
_RETRYABLE_STATUSES = frozenset({0, 408, 425, 429, 500, 502, 503, 504})


class RegistrationError(RuntimeError):
    """Registration did not succeed within the budget (or was refused)."""


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, AuthenticationError):
        return False
    if isinstance(exc, APIError):
        return exc.status_code in _RETRYABLE_STATUSES
    if isinstance(exc, (asyncio.TimeoutError, SdkTimeoutError, TimeoutError, OSError)):
        return True
    # A transport-level failure the SDK didn't wrap (aiohttp/requests errors
    # are ``OSError`` or ``VicoaError`` subclasses in practice; anything else
    # is a bug we should not mask by retrying).
    return False


def _schedule() -> list[float]:
    return [
        offset + (random.uniform(0.0, _JITTER_SECONDS) if i else 0.0)
        for i, offset in enumerate(REGISTRATION_ATTEMPT_OFFSETS)
    ]


async def register_with_retry(
    attempt: Callable[[], Awaitable[T]],
    *,
    log: logging.Logger,
    label: str,
    attempt_timeout: float = REGISTRATION_ATTEMPT_TIMEOUT_SECONDS,
    total_budget: float = REGISTRATION_TOTAL_BUDGET_SECONDS,
) -> T:
    """Run ``attempt()`` on the retry schedule; return its first success.

    Raises ``RegistrationError`` once the budget is spent or every scheduled
    attempt has failed, and re-raises immediately on a non-retryable error
    (bad credential, quota refusal, malformed request) — those don't get
    better by waiting.
    """
    started = time.monotonic()
    last_error: BaseException | None = None
    offsets = _schedule()
    for index, offset in enumerate(offsets):
        wait = started + offset - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        remaining = total_budget - (time.monotonic() - started)
        if remaining <= 0:
            break
        try:
            return await asyncio.wait_for(
                attempt(), timeout=min(attempt_timeout, remaining)
            )
        except Exception as exc:  # noqa: BLE001 — classified below; cancellation propagates
            if not _is_retryable(exc):
                raise
            last_error = exc
            log.warning(
                "%s: registration attempt %d/%d failed (%s: %s)",
                label,
                index + 1,
                len(offsets),
                type(exc).__name__,
                str(exc)[:200] or "timed out",
            )
    elapsed = time.monotonic() - started
    raise RegistrationError(
        f"{label}: agent instance registration failed after {len(offsets)} "
        f"attempts in {elapsed:.1f}s: {type(last_error).__name__ if last_error else 'no attempt made'}"
        f"{': ' + str(last_error)[:200] if last_error and str(last_error) else ''}"
    ) from last_error


def register_with_retry_sync(
    attempt: Callable[[], T],
    *,
    log: logging.Logger | Callable[[str], None],
    label: str,
    attempt_timeout: float = REGISTRATION_ATTEMPT_TIMEOUT_SECONDS,
    total_budget: float = REGISTRATION_TOTAL_BUDGET_SECONDS,
) -> T:
    """Blocking counterpart of :func:`register_with_retry` for sync runners.

    Each attempt runs on a daemon thread and is abandoned (not cancelled —
    ``requests`` has no cancel) if it overruns ``attempt_timeout``. An
    abandoned attempt that later succeeds is harmless: the next attempt
    reads the row back through the 409/200 idempotency path.
    """
    warn = log.warning if isinstance(log, logging.Logger) else log
    started = time.monotonic()
    last_error: BaseException | None = None
    offsets = _schedule()
    for index, offset in enumerate(offsets):
        wait = started + offset - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        remaining = total_budget - (time.monotonic() - started)
        if remaining <= 0:
            break

        outcome: dict[str, object] = {}

        def _run() -> None:
            try:
                outcome["value"] = attempt()
            except Exception as exc:  # noqa: BLE001 — carried to the caller
                outcome["error"] = exc

        worker = threading.Thread(
            target=_run, name="vicoa-register-attempt", daemon=True
        )
        worker.start()
        worker.join(timeout=min(attempt_timeout, remaining))
        if worker.is_alive():
            last_error = TimeoutError("attempt timed out")
        elif "error" in outcome:
            exc = outcome["error"]
            assert isinstance(exc, BaseException)
            if not _is_retryable(exc):
                raise exc
            last_error = exc
        else:
            return outcome["value"]  # type: ignore[return-value]
        warn(
            f"{label}: registration attempt {index + 1}/{len(offsets)} failed "
            f"({type(last_error).__name__}: {str(last_error)[:200]})"
        )
    elapsed = time.monotonic() - started
    raise RegistrationError(
        f"{label}: agent instance registration failed after {len(offsets)} "
        f"attempts in {elapsed:.1f}s: "
        f"{type(last_error).__name__ if last_error else 'no attempt made'}"
        f"{': ' + str(last_error)[:200] if last_error and str(last_error) else ''}"
    ) from last_error
