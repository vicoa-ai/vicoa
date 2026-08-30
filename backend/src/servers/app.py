"""Unified server combining MCP and FastAPI functionality.

This server provides:
- MCP tools at /mcp/ endpoint (log_step, ask_question, end_session)
- REST API endpoints at /api/v1/*
- WebSocket endpoint at /ws (when enabled) for realtime + terminal streaming
- Shared JWT authentication for both interfaces
"""

import asyncio
import logging
from contextlib import asynccontextmanager
import traceback

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Scope, Receive, Send, Message
import sentry_sdk
from sqlalchemy.exc import IntegrityError, OperationalError as SAOperationalError
from shared.auth.user_fk import make_user_gone_exception_handler
from shared.config import settings
from shared.database.errors import is_db_disconnect
from shared.database.models import User
from shared.database.session import SessionLocal
from shared.telemetry import (
    VersionTelemetryMiddleware,
    drop_known_uvicorn_noise,
    version_telemetry,
)

# Import the pre-configured MCP server
from servers.mcp.server import mcp

# Import FastAPI routers
from servers.api.automations import automation_router
from servers.api.instances import instance_router
from servers.api.routers import agent_router
from servers.api.tasks import task_router
from servers.api.ws_handler import ws_router
from servers.scheduler import AutomationScheduler
from shared.pg_listener import start_hub, stop_hub


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SseWriteTimeoutMiddleware:
    """Times out writes on SSE streams so CLOSE_WAIT sockets don't block the event loop.

    When a client disconnects mid-stream the OS puts the socket into CLOSE_WAIT.
    Subsequent writes buffer in the kernel but are never ACKed, causing
    `await send(...)` to hang forever and starve the asyncio event loop.
    Wrapping send() with asyncio.wait_for aborts the stream after 10 s and
    lets the connection be cleaned up.
    """

    _WRITE_TIMEOUT = 10.0

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_sse = False

        async def send_with_timeout(message: Message) -> None:
            nonlocal is_sse
            if message["type"] == "http.response.start":
                for name, value in message.get("headers", []):
                    if (
                        name.lower() == b"content-type"
                        and b"text/event-stream" in value
                    ):
                        is_sse = True
                        break
            if (
                is_sse
                and message["type"] == "http.response.body"
                and message.get("more_body")
            ):
                try:
                    await asyncio.wait_for(send(message), timeout=self._WRITE_TIMEOUT)
                except asyncio.TimeoutError:
                    logger.info(
                        "SSE write timed out after %.1fs on %s; closing stream",
                        self._WRITE_TIMEOUT,
                        scope.get("path", "<unknown>"),
                    )
                    raise
                except asyncio.CancelledError:
                    raise
                except BaseException:
                    # Previously any non-Timeout exception bubbled up silently —
                    # uvicorn logged "ASGI callable returned without completing
                    # response" with no traceback, making SSE breakage invisible.
                    # Log + re-raise so fly logs show the actual cause.
                    logger.exception(
                        "SSE send raised on %s; stream will terminate",
                        scope.get("path", "<unknown>"),
                    )
                    raise
            else:
                await send(message)

        try:
            await self.app(scope, receive, send_with_timeout)
        except asyncio.CancelledError:
            raise
        except BaseException:
            if is_sse:
                logger.exception(
                    "SSE ASGI app raised on %s", scope.get("path", "<unknown>")
                )
            raise


# Initialize Sentry only in production. Dev/test runs (pytest on a laptop,
# local CI) would otherwise leak test-fixture exceptions like
# "RuntimeError: boom" into the prod Sentry project.
if settings.sentry_dsn and settings.environment == "production":
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        send_default_pii=True,
        environment=settings.environment,
        before_send=drop_known_uvicorn_noise,
    )
    logger.info(f"Sentry initialized for {settings.environment} environment")
else:
    logger.info(
        "Sentry disabled (env=%s, dsn_present=%s)",
        settings.environment,
        bool(settings.sentry_dsn),
    )

# Get the MCP app with streamable-http transport
mcp_app = mcp.http_app(path="/")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Combined lifespan for both MCP and FastAPI functionality."""
    # Use the MCP app's lifespan to ensure proper initialization
    async with mcp_app.lifespan(app):
        logger.info("Unified server starting up")
        logger.info("MCP endpoints available at: /mcp/")
        logger.info("REST API endpoints available at: /api/v1/*")
        await start_hub()
        # Automation sweep — dispatches scheduled agent runs over the daemon RPC.
        # No-op unless enable_websocket (only the WS-enabled server can reach a
        # daemon's rpc_router). Started after the hub, torn down before it.
        scheduler = AutomationScheduler()
        await scheduler.start()
        try:
            yield
        finally:
            logger.info("Shutting down unified server")
            await scheduler.stop()
            await stop_hub()


# Create FastAPI app with MCP's lifespan
app = FastAPI(
    title="Agent Dashboard Unified Server",
    description="Combined MCP and REST API for agent monitoring and interaction",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SseWriteTimeoutMiddleware)
# Record the CLI/daemon version of every request for the Wave B retirement
# gate (websocket-migration §4 item 6). `server` serves CLI wrappers and
# machine daemons, which send X-CLI-Version.
app.add_middleware(
    VersionTelemetryMiddleware,
    telemetry=version_telemetry,
    header_name="X-CLI-Version",
)


def _user_exists_in_db(sub: str) -> bool:
    """Return whether `users.id = sub` exists. PK lookup, sub-ms.

    Used by the IntegrityError handler below to distinguish "the auth'd
    user was deleted while their CLI kept running" (→ 401) from any other
    FK violation (→ re-raise → 500). See p0-agent-jwt-no-db-validation.
    """
    with SessionLocal() as db:
        return db.query(User.id).filter(User.id == sub).first() is not None


app.exception_handler(IntegrityError)(
    make_user_gone_exception_handler(_user_exists_in_db)
)


@app.exception_handler(SAOperationalError)
async def _on_db_disconnect(request: Request, exc: SAOperationalError):
    """Convert transient flycast disconnects to 503 + Retry-After.

    Daemon clients (CLI wrappers, machine heartbeats) retry on 503 naturally.
    This stops disconnect-class errors from polluting Sentry as 500s and
    keeps user-facing surfaces clean during flycast proxy resets.

    More-specific handlers run before the generic `Exception` handler below.
    """
    if is_db_disconnect(exc):
        inner = getattr(exc, "orig", exc)
        logger.warning(
            "DB disconnect on %s %s -> 503: %s",
            request.method,
            request.url.path,
            str(inner)[:200],
        )
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "1"},
            content={"detail": "Database temporarily unavailable, please retry."},
        )
    # Not a transient disconnect — fall through to the generic 500 handler.
    raise exc


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler that logs all unhandled exceptions."""
    # Log the error with full traceback
    logger.error(f"Unhandled exception in {request.method} {request.url.path}")
    logger.error(f"Exception: {type(exc).__name__}: {str(exc)}")
    logger.error(traceback.format_exc())

    # Re-raise HTTPExceptions to preserve their status codes
    if isinstance(exc, HTTPException):
        raise exc

    # For all other exceptions, return 500
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(agent_router, prefix="/api/v1")
# Task tracker CRUD for CLI agents (agent-facing mirror of backend/api/tasks.py).
app.include_router(task_router, prefix="/api/v1")
# Scheduled-automation CRUD for CLI agents (agent-facing mirror of
# backend/api/automations.py). Dispatch stays in this process's scheduler sweep.
app.include_router(automation_router, prefix="/api/v1")
# Read-only session list + transcript for CLI agents (agent-facing mirror of
# the backend/api/agents.py instance reads).
app.include_router(instance_router, prefix="/api/v1")
# The WebSocket endpoint and its process-local ConnectionManager are mounted
# only on the dedicated vicoa-server app (enable_websocket=true). The legacy
# server process inside vicoa-backend stays SSE/REST-only (server-app-split.md).
if settings.enable_websocket:
    app.include_router(ws_router)
    logger.info("WebSocket endpoint mounted at /ws")
app.mount("/mcp", mcp_app)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Agent Dashboard Unified Server",
        "version": "1.0.0",
        "endpoints": {
            "mcp": "/mcp/ (MCP tools via Streamable HTTP)",
            "api": "/api/v1/* (REST API endpoints)",
            "docs": "/docs (API documentation)",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "server": "unified"}


def main():
    """Run the unified server."""
    import socket

    import uvicorn

    # Log configuration for debugging
    logger.info(f"Starting unified server on port: {settings.mcp_server_port}")
    logger.info("Database URL configured.")
    logger.info(
        f"JWT public key configured: {'Yes' if settings.jwt_public_key else 'No'}"
    )

    # Dual-stack bind: one AF_INET6 socket with IPV6_V6ONLY=0 listens on BOTH
    # IPv4 (via IPv4-mapped-IPv6 addresses) and IPv6. Required so:
    #   - Fly's edge proxy (IPv4 → agents.vicoa.ai:443) reaches the process
    #   - Fly's 6PN private network (IPv6 → vicoa-server.internal:8080)
    #     reaches the process for the §2.11 backend→server bridge.
    # Cannot use uvicorn's `host="::"` because asyncio.loop.create_server
    # explicitly setsockopt(IPV6_V6ONLY=1), overriding the Linux kernel
    # default `bindv6only=0` — verified 2026-05-23 by deploying host="::"
    # and observing Fly IPv4 health checks fail with 503. Creating the
    # socket manually with V6ONLY=0 and passing it via Server.run(sockets=)
    # bypasses asyncio's defaulting.
    port = settings.mcp_server_port
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind(("::", port))

    try:
        config = uvicorn.Config(
            "servers.app:app",
            # WebSocket migration §2.10: the in-memory ConnectionManager is
            # per-process. Multiple workers would each hold a separate manager
            # and silently split broadcasts/RPC. Pin to a single worker
            # explicitly until Phase 6 (Redis) lifts the constraint.
            workers=1,
        )
        server = uvicorn.Server(config)
        server.run(sockets=[sock])
    except Exception as e:
        logger.error(f"Failed to start unified server: {e}")
        raise


if __name__ == "__main__":
    main()
