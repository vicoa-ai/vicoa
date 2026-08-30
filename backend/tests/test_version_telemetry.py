"""Behavioral tests for client/CLI version telemetry (websocket-migration §4 item 6).

Every REST/WS request carries a version header — `X-Client-Version` from
vicoa-web/vicoa-app, `X-CLI-Version` from the daemon/CLI wrapper. The server
counts the version share so the Wave A/B retirement gates can fire. A request
with no header is an un-upgraded client and must be counted as old, never
dropped.
"""

from starlette.types import Message, Scope

from shared.telemetry import (
    OTHER,
    PRE_TELEMETRY,
    VersionTelemetry,
    VersionTelemetryMiddleware,
    drop_known_uvicorn_noise,
)

_ASGI_NOISE = "ASGI callable returned without completing response."


async def _noop_receive() -> Message:
    return {"type": "http.request"}


async def _noop_send(message: Message) -> None:
    return None


async def _passthrough(scope: Scope, receive: object, send: object) -> None:
    return None


def test_observe_counts_a_version() -> None:
    telemetry = VersionTelemetry()
    telemetry.observe("1.4.2")
    telemetry.observe("1.4.2")

    assert telemetry.snapshot() == {"1.4.2": 2}


def test_missing_version_is_counted_as_pre_telemetry() -> None:
    telemetry = VersionTelemetry()
    telemetry.observe(None)

    assert telemetry.snapshot() == {PRE_TELEMETRY: 1}


def test_distinct_version_buckets_are_capped() -> None:
    """The version header is attacker-controlled; the histogram must not grow
    unbounded. Versions past the cap collapse into a single OTHER bucket."""
    telemetry = VersionTelemetry()
    for i in range(VersionTelemetry.MAX_BUCKETS + 50):
        telemetry.observe(f"v{i}")

    snapshot = telemetry.snapshot()
    assert len(snapshot) == VersionTelemetry.MAX_BUCKETS + 1  # buckets + OTHER
    assert snapshot[OTHER] == 50


async def test_middleware_records_the_request_version_header() -> None:
    telemetry = VersionTelemetry()
    middleware = VersionTelemetryMiddleware(_passthrough, telemetry, "X-Client-Version")
    scope = {"type": "http", "headers": [(b"x-client-version", b"1.4.2")]}

    await middleware(scope, _noop_receive, _noop_send)

    assert telemetry.snapshot() == {"1.4.2": 1}


async def test_middleware_counts_a_headerless_request_as_pre_telemetry() -> None:
    telemetry = VersionTelemetry()
    middleware = VersionTelemetryMiddleware(_passthrough, telemetry, "X-Client-Version")

    await middleware({"type": "http", "headers": []}, _noop_receive, _noop_send)

    assert telemetry.snapshot() == {PRE_TELEMETRY: 1}


async def test_middleware_records_websocket_handshake_versions() -> None:
    telemetry = VersionTelemetry()
    middleware = VersionTelemetryMiddleware(_passthrough, telemetry, "X-CLI-Version")
    scope = {"type": "websocket", "headers": [(b"x-cli-version", b"2.0.0")]}

    await middleware(scope, _noop_receive, _noop_send)

    assert telemetry.snapshot() == {"2.0.0": 1}


async def test_middleware_ignores_non_request_scopes() -> None:
    telemetry = VersionTelemetry()
    middleware = VersionTelemetryMiddleware(_passthrough, telemetry, "X-Client-Version")

    await middleware({"type": "lifespan"}, _noop_receive, _noop_send)

    assert telemetry.snapshot() == {}


# --- drop_known_uvicorn_noise (Sentry FLASK-7) -------------------------------


def test_drops_asgi_incomplete_response_noise() -> None:
    """The benign uvicorn streaming-teardown warning is discarded (returns None)."""
    event = {"logger": "uvicorn.error", "logentry": {"message": _ASGI_NOISE}}

    assert drop_known_uvicorn_noise(event, {}) is None


def test_drops_when_message_is_in_logentry_formatted() -> None:
    """Some SDK paths populate `formatted` instead of `message`."""
    event = {"logger": "uvicorn.error", "logentry": {"formatted": _ASGI_NOISE}}

    assert drop_known_uvicorn_noise(event, {}) is None


def test_keeps_other_uvicorn_errors() -> None:
    """A real ASGI failure on the same logger must still report."""
    event = {
        "logger": "uvicorn.error",
        "logentry": {"message": "Exception in ASGI application"},
    }

    assert drop_known_uvicorn_noise(event, {}) is event


def test_keeps_matching_message_from_a_different_logger() -> None:
    """Scoped to uvicorn.error: the same words elsewhere are not dropped."""
    event = {"logger": "my.app", "logentry": {"message": _ASGI_NOISE}}

    assert drop_known_uvicorn_noise(event, {}) is event


def test_handles_event_without_logentry() -> None:
    """A logger-only event must not raise and must pass through."""
    event = {"logger": "uvicorn.error"}

    assert drop_known_uvicorn_noise(event, {}) is event
