"""Client/CLI version telemetry (websocket-migration plan §4 Phase 0 item 6).

The WebSocket migration retires SSE endpoints behind version-share gates:
Wave A needs the new web/app build at ≥95%, Wave B needs the SSE-protocol
daemon share <1%. To measure that, every request is tagged with a version
header and counted here.

Attribution is by Fly process, not header inspection: `backend` serves
vicoa-web / vicoa-app (so its requests carry `X-Client-Version`) and `server`
serves the CLI wrappers and machine daemons (`X-CLI-Version`). Each process
mounts `VersionTelemetryMiddleware` with the header name for its own channel.

A request with no version header is an un-upgraded client: it is counted under
the `PRE_TELEMETRY` bucket, never dropped — otherwise the retirement gates
would read optimistically while old clients are still live.
"""

from collections import defaultdict

from sentry_sdk.types import Event, Hint
from starlette.types import ASGIApp, Receive, Scope, Send

PRE_TELEMETRY = "pre-telemetry"
OTHER = "other"

# uvicorn logs this at ERROR on logger "uvicorn.error" once per streaming
# response (an SSE generator or an MCP EventSourceResponse) that returns without
# emitting its terminal body frame while uvicorn has not yet flagged the socket
# as disconnected — the benign teardown of a text/event-stream when a client
# reconnect loop or a graceful shutdown cancels the generator before its final
# frame. uvicorn emits it *after* the ASGI app returns, so the event has no
# request scope: no transaction, no culprit, 0 users. It is harmless but very
# loud (Sentry FLASK-7 logged 15k+ of these, all on the streaming server). The
# string lives only in uvicorn's HTTP protocol impls — despite the breadcrumbs,
# it is never a WebSocket error.
_ASGI_INCOMPLETE_RESPONSE = "ASGI callable returned without completing response"


def drop_known_uvicorn_noise(event: Event, hint: Hint) -> Event | None:
    """Sentry ``before_send`` hook: discard the benign ASGI-incomplete-response
    uvicorn warning (FLASK-7) by returning ``None``; pass everything else through.

    Scoped to the exact ``uvicorn.error`` message so real failures — including
    uvicorn's *other* ASGI errors such as "Exception in ASGI application" — still
    report. The fly log line is untouched, so a genuine incomplete response on a
    real endpoint stays visible in logs even though it no longer pages Sentry.
    """
    if event.get("logger") == "uvicorn.error":
        logentry = event.get("logentry") or {}
        message = (
            logentry.get("formatted")
            or logentry.get("message")
            or event.get("message")
            or ""
        )
        if isinstance(message, str) and _ASGI_INCOMPLETE_RESPONSE in message:
            return None
    return event


class VersionTelemetry:
    """In-memory histogram of observed client/CLI versions for one process."""

    # The version header is attacker-controlled, so the histogram is bounded:
    # once this many distinct versions are tracked, further new values collapse
    # into the OTHER bucket. Real deployments have a handful of live versions,
    # so this never trips in normal operation.
    MAX_BUCKETS = 100

    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)

    def observe(self, version: str | None) -> None:
        """Count one request; a missing version falls in the PRE_TELEMETRY bucket."""
        key = version or PRE_TELEMETRY
        if key not in self._counts and len(self._counts) >= self.MAX_BUCKETS:
            key = OTHER
        self._counts[key] += 1

    def snapshot(self) -> dict[str, int]:
        """A copy of the version → request-count histogram."""
        return dict(self._counts)


class VersionTelemetryMiddleware:
    """ASGI middleware that records the version header of every request."""

    def __init__(
        self, app: ASGIApp, telemetry: VersionTelemetry, header_name: str
    ) -> None:
        self.app = app
        self._telemetry = telemetry
        self._header = header_name.lower().encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            version: str | None = None
            for name, value in scope.get("headers", []):
                if name == self._header:
                    version = value.decode("latin-1").strip() or None
                    break
            self._telemetry.observe(version)
        await self.app(scope, receive, send)


# Process-wide singleton. `backend` and `server` are separate processes, so
# each gets its own per-process histogram — which is exactly the design (a
# future read endpoint imports this instance to expose the snapshot).
version_telemetry = VersionTelemetry()
