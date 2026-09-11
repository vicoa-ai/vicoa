"""HTTP mapping for the access-control exceptions, shared by both apps.

`AccessDenied` (shared.access) → 403 and `CapabilityDenied` (shared.hooks) →
402 are raised deep in the query layer so that a forgotten try/except in a
router degrades to the *right* status rather than a 500. Installing the
handlers once per app is what makes that safe.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from shared.access import AccessDenied
from shared.hooks import CapabilityDenied


def install_access_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AccessDenied)
    async def _on_access_denied(request: Request, exc: AccessDenied) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=403,
            content={"detail": str(exc), "required_role": exc.minimum},
        )

    @app.exception_handler(CapabilityDenied)
    async def _on_capability_denied(
        request: Request, exc: CapabilityDenied
    ) -> JSONResponse:
        del request
        # 402: the action exists and the caller is allowed to ask for it —
        # it is metered. The overlay's reason carries the upgrade path.
        return JSONResponse(
            status_code=402,
            content={"detail": exc.reason, "capability": exc.capability},
        )
