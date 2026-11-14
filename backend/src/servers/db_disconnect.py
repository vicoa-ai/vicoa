"""Exception handler for a transient database disconnect on the agent-facing server.

Lives in its own module, like `shared/auth/user_fk.py`, so a test can drive it
without importing `servers.app` (which needs the JWT keys at import time). The
wiring is in `servers/app.py`.
"""

from __future__ import annotations

import logging

from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError as SAOperationalError
from starlette.requests import HTTPConnection
from starlette.websockets import WebSocket

from servers.api.ws_handler import close_for_db_disconnect
from shared.database.errors import is_db_disconnect

logger = logging.getLogger(__name__)


async def on_db_disconnect(
    conn: HTTPConnection, exc: SAOperationalError
) -> JSONResponse | None:
    """Turn a transient flycast disconnect into an answer the client retries.

    HTTP: 503 + Retry-After. Daemon clients (CLI wrappers, machine heartbeats)
    retry on 503 naturally, and disconnect-class errors stop polluting Sentry
    as 500s during flycast proxy resets.

    WebSocket: Starlette hands this handler the `WebSocket` (it has no
    `.method`) and awaits whatever the handler returns as an ASGI response, so a
    JSON response is wrong here. Close with "try again later" instead and
    return None.

    Anything that is not a transient disconnect is re-raised, so the generic
    500 handler (HTTP) or the server's own error report (WebSocket) still sees
    it.
    """
    if not is_db_disconnect(exc):
        raise exc

    inner = getattr(exc, "orig", exc)
    if isinstance(conn, WebSocket):
        logger.warning(
            "DB disconnect on WS %s -> close 1013: %s", conn.url.path, str(inner)[:200]
        )
        await close_for_db_disconnect(conn)
        return None

    logger.warning(
        "DB disconnect on %s %s -> 503: %s",
        conn.scope.get("method"),
        conn.url.path,
        str(inner)[:200],
    )
    return JSONResponse(
        status_code=503,
        headers={"Retry-After": "1"},
        content={"detail": "Database temporarily unavailable, please retry."},
    )
