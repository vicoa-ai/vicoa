"""FastAPI backend for Agent Dashboard"""

import importlib.util
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sentry_sdk
from sqlalchemy.exc import OperationalError as SAOperationalError
from shared.config import settings
from shared.database.errors import is_db_disconnect
from shared.telemetry import (
    VersionTelemetryMiddleware,
    drop_known_uvicorn_noise,
    version_telemetry,
)
from shared.pg_listener import start_hub, stop_hub
from shared.hooks import run_app_setup, start_lifespan_hooks, stop_lifespan_hooks
from .api import (
    activity,
    agents,
    attachments,
    deepgram,
    user_agents,
    push_notifications,
    user_settings,
    teams,
    machines,
    slash_commands,
    file_mentions,
    support,
    tasks,
    automations,
    search,
)
from shared.auth import resolve_auth_provider_name
from .auth import routes as auth_routes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await start_hub()
    # Overlay background tasks (e.g. the activation-nudge drip). Empty in the
    # open-source build where the cloud overlay is absent.
    await start_lifespan_hooks()
    try:
        yield
    finally:
        await stop_lifespan_hooks()
        await stop_hub()


# Create FastAPI app
app = FastAPI(
    title="Agent Dashboard API",
    description="Backend API for monitoring and interacting with AI agents",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS - cannot use wildcard (*) with credentials
# Define localhost origins for both development and production access
localhost_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",  # Vite default
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:8081",  # Custom frontend port
    "http://127.0.0.1:8081",
]

if os.getenv("ENVIRONMENT", "development") == "development":
    # In development, use localhost origins
    allowed_origins = localhost_origins
else:
    # Production origins from configuration
    allowed_origins = (
        settings.frontend_urls + localhost_origins
    )  # Include localhost URLs in production too

# The desktop app's renderer is served from http://127.0.0.1:<port> (a dynamic
# port picked at launch), so it can't be a static allowlist entry. Loopback
# origins are the user's own machine and a remote web page cannot forge its
# Origin, so any localhost/127.0.0.1 port is safe to accept for CORS — auth is
# still the Authorization header (Supabase JWT / API key), and
# allow_credentials is False.
DESKTOP_LOCALHOST_ORIGIN_REGEX = r"^http://(127\.0\.0\.1|localhost)(:\d+)?$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=DESKTOP_LOCALHOST_ORIGIN_REGEX,
    # We authenticate via Authorization header; no cross-site cookies needed
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],  # includes Authorization
)
# Record the web/app client version of every request for the Wave A retirement
# gate (websocket-migration §4 item 6). `backend` serves vicoa-web and
# vicoa-app, which send X-Client-Version.
app.add_middleware(
    VersionTelemetryMiddleware,
    telemetry=version_telemetry,
    header_name="X-Client-Version",
)


@app.exception_handler(SAOperationalError)
async def _on_db_disconnect(request: Request, exc: SAOperationalError):
    """Convert transient flycast disconnects to 503 + Retry-After.

    Daemon clients (CLI wrappers, machine heartbeats) retry on 503 naturally.
    This stops disconnect-class errors from polluting Sentry as 500s and
    keeps user-facing surfaces clean during flycast proxy resets.
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
    raise exc


# Include routers with versioned API prefix
app.include_router(auth_routes.router, prefix=settings.api_v1_prefix)
app.include_router(activity.router, prefix=settings.api_v1_prefix)
app.include_router(agents.router, prefix=settings.api_v1_prefix)
app.include_router(attachments.router, prefix=settings.api_v1_prefix)
app.include_router(deepgram.router, prefix=settings.api_v1_prefix)
app.include_router(user_agents.router, prefix=settings.api_v1_prefix)
app.include_router(push_notifications.router, prefix=settings.api_v1_prefix)
app.include_router(user_settings.router, prefix=settings.api_v1_prefix)
app.include_router(teams.router, prefix=settings.api_v1_prefix)
app.include_router(machines.router, prefix=settings.api_v1_prefix)
app.include_router(slash_commands.router, prefix=settings.api_v1_prefix)
app.include_router(file_mentions.router, prefix=settings.api_v1_prefix)
app.include_router(support.router, prefix=settings.api_v1_prefix)
app.include_router(tasks.router, prefix=settings.api_v1_prefix)
app.include_router(automations.router, prefix=settings.api_v1_prefix)
app.include_router(search.router, prefix=settings.api_v1_prefix)

# Sign-up / sign-in endpoints only exist when this deployment *is* the identity
# provider. Mounting them against a Supabase-backed deployment would add a
# second, unmanaged way to create accounts.
if resolve_auth_provider_name() == "builtin":
    from .auth import builtin_routes

    app.include_router(builtin_routes.router, prefix=settings.api_v1_prefix)
    logger.info("Built-in auth provider: sign-in endpoints mounted")

# Load the closed cloud overlay when it
# is present, then let it mount its routers on top of the core ones. Absent in
# the open-source build, so the core runs unchanged. `find_spec` is used instead
# of a bare `try/except ImportError` so that a real ImportError raised from
# *within* the overlay still fails loudly in the cloud build rather than being
# silently swallowed.
if importlib.util.find_spec("cloud") is not None:
    import cloud  # type: ignore[import-not-found]  # noqa: F401  # pyright: ignore[reportMissingImports]  (registers billing/activation/convertkit hooks)

    logger.info("Loaded cloud overlay")
else:
    logger.info("Cloud overlay absent; running open-source core")

run_app_setup(app)


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Agent Dashboard API", "version": "1.0.0", "docs": "/docs"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=settings.api_port, reload=True)


def main():
    """Entry point for module execution"""
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=settings.api_port)


if __name__ == "__main__":
    main()
