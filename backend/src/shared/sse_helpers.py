"""Shared helpers for FastAPI SSE endpoints backed by ``pg_listener``.

Currently extracts the "signal stream" pattern — the simple loop used by SSE
endpoints that just relay each NOTIFY payload to the client (no DB cursor
catch-up, no WakeEvent dual-path).  The per-instance message streams are
intentionally NOT routed through this helper: they use ``WakeEvent`` plus a
DB cursor query plus drain-signals-separately, and forcing them through a
single abstraction obscured more than it shared.

If a third Pattern-A endpoint shows up later, keep adding to this file.  If a
second Pattern-B endpoint shows up, extract that one separately.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, Callable, Optional, Tuple

from fastapi import Request
from fastapi.responses import StreamingResponse

from shared.pg_listener import get_hub

logger = logging.getLogger(__name__)

# Headers all our SSE endpoints want. ``X-Accel-Buffering: no`` disables nginx
# proxy buffering so events reach the client immediately instead of getting
# batched into ~4 KB chunks.
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

# Idle interval at which we emit a ``heartbeat`` event so the client can
# detect a dead connection (and so intermediate proxies don't reap the TCP
# stream as idle).  Matches the existing ad-hoc timeout used in agents.py /
# routers.py.
DEFAULT_HEARTBEAT_TIMEOUT_SECONDS: float = 15.0


def format_sse(event: str, data: str) -> str:
    """Encode a single SSE event frame. ``data`` is already a string."""
    return f"event: {event}\ndata: {data}\n\n"


PayloadToEvent = Callable[[str], Tuple[str, str]]
"""(payload) -> (event_type, data_str).  Used to override the default
parse-JSON / pick-`event_type`-field behaviour for endpoints whose NOTIFY
payload isn't structured as a JSON envelope with an ``event_type`` field."""


async def signal_sse_generator(
    *,
    request: Request,
    channel: str,
    connected_event: dict,
    default_event_type: str = "message",
    payload_to_event: Optional[PayloadToEvent] = None,
    heartbeat_timeout: float = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
) -> AsyncGenerator[str, None]:
    """Generator for a Pattern A SSE stream.

    Subscribes to ``channel`` via the shared PG hub, yields ``event: connected``
    immediately, then loops: each NOTIFY becomes one SSE event; if no NOTIFY
    arrives within ``heartbeat_timeout`` seconds, yields a ``heartbeat`` event
    so the client can keep the connection alive.

    Exits cleanly when ``request.is_disconnected()`` (the client has gone
    away).  A bad payload yields an ``error`` event and ends the stream.

    Parameters
    ----------
    request : Request
        The FastAPI request — used only for ``is_disconnected()`` polling.
    channel : str
        The PG channel to LISTEN on.
    connected_event : dict
        JSON-serialisable payload for the initial ``connected`` event
        (e.g. ``{"user_id": "..."}`` or ``{"machine_id": "..."}``).
    default_event_type : str, optional
        Used when the JSON payload doesn't carry an ``event_type`` field.
        Defaults to ``"message"``; callers like the per-user instance stream
        pass ``"instance_updated"`` to match their pre-extraction behaviour.
    payload_to_event : callable, optional
        Override for the default "parse JSON, pick event_type field"
        behaviour.  Useful when the NOTIFY payload is opaque to this layer
        (e.g. spawn-request payloads, which the daemon parses, not us).
    heartbeat_timeout : float, optional
        Idle interval before emitting a ``heartbeat`` event.
    """
    try:
        async with get_hub().subscribe(channel) as (_wake_event, signal_queue):
            yield format_sse("connected", json.dumps(connected_event))

            while True:
                try:
                    payload = await asyncio.wait_for(
                        signal_queue.get(), timeout=heartbeat_timeout
                    )
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        break
                    yield format_sse(
                        "heartbeat",
                        json.dumps({"timestamp": asyncio.get_running_loop().time()}),
                    )
                    continue

                if await request.is_disconnected():
                    break

                try:
                    if payload_to_event is not None:
                        event_type, data_str = payload_to_event(payload)
                    else:
                        data = json.loads(payload)
                        event_type = data.get("event_type", default_event_type)
                        data_str = json.dumps(data)
                    yield format_sse(event_type, data_str)
                except Exception as exc:
                    yield format_sse("error", json.dumps({"error": str(exc)}))
                    break
    except asyncio.CancelledError:
        # Normal client disconnect; propagate so Starlette cleans up cleanly.
        raise
    except BaseException:
        # Any other exception here was previously swallowed — uvicorn would log
        # only "ASGI callable returned without completing response" with no
        # traceback. Surface it so the underlying fault is debuggable.
        logger.exception("signal_sse_generator crashed on channel=%s", channel)
        raise


def sse_response(generator: AsyncGenerator[str, None]) -> StreamingResponse:
    """Wrap an SSE generator in a FastAPI StreamingResponse with the standard
    SSE headers."""
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
