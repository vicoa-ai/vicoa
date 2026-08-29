"""Automations REST API for the agent-facing server.

The human dashboard (``backend`` process, Supabase JWT) owns the automation
CRUD so far (``backend/api/automations.py``). This module exposes the same CRUD
to CLI agents, which authenticate against *this* server with their RS256
API-key JWT (``get_current_user_id``). The business logic is reused verbatim
from ``backend.db.automation_queries`` — the same servers→backend reuse
precedent as ``tasks.py`` importing ``backend.db.task_queries`` — so the
agent-facing and human-facing automation surfaces can never drift.

Automations are user-scoped: an agent acting for a user sees and mutates that
user's whole set of scheduled runs, exactly as the user's web session would.
Dispatch (the actual firing) is NOT here — it lives in the ``server`` process's
scheduler sweep; this router only reads/writes the DB rows. Kept in its own file
to avoid bloating ``routers.py``.
"""

# NB: no ``from __future__ import annotations`` — it would stringify the
# ``-> None`` on the 204 DELETE, which FastAPI then resolves to ``NoneType``
# (truthy) and rejects as "204 must not have a response body".

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from shared.database.session import get_db

# Reused human-facing query layer + DTOs. See module docstring for why this
# servers→backend import is deliberate rather than a duplicate implementation.
from backend.db import automation_queries
from backend.db.automation_queries import (
    AutomationNotFoundError,
    InvalidScheduleError,
    MachineNotFoundError,
)
from backend.models import (
    AutomationResponse,
    AutomationRunResponse,
    CreateAutomationRequest,
    UpdateAutomationRequest,
)

from .auth import get_current_user_id

automation_router = APIRouter(tags=["automations"])


def _user_uuid(user_id: str) -> UUID:
    """Coerce the token's ``sub`` (a string) to the UUID the queries expect."""
    try:
        return UUID(user_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject is not a valid user id",
        ) from exc


@automation_router.get("/automations", response_model=list[AutomationResponse])
def list_automations_endpoint(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> list[AutomationResponse]:
    rows = automation_queries.list_automations(db, _user_uuid(user_id))
    return [AutomationResponse.model_validate(r) for r in rows]


@automation_router.post(
    "/automations",
    response_model=AutomationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_automation_endpoint(
    request: CreateAutomationRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> AutomationResponse:
    try:
        automation = automation_queries.create_automation(
            db,
            _user_uuid(user_id),
            title=request.title,
            prompt=request.prompt,
            machine_id=request.machine_id,
            directory=request.directory,
            worktree=request.worktree,
            session_config=request.session_config,
            schedule_kind=request.schedule_kind,
            frequency=request.frequency,
            timezone=request.timezone,
            run_at=request.run_at,
            enabled=request.enabled,
        )
    except MachineNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except InvalidScheduleError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return AutomationResponse.model_validate(automation)


@automation_router.get(
    "/automations/{automation_id}", response_model=AutomationResponse
)
def get_automation_endpoint(
    automation_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> AutomationResponse:
    automation = automation_queries.get_automation(
        db, _user_uuid(user_id), automation_id
    )
    if automation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found"
        )
    return AutomationResponse.model_validate(automation)


@automation_router.patch(
    "/automations/{automation_id}", response_model=AutomationResponse
)
def update_automation_endpoint(
    automation_id: UUID,
    request: UpdateAutomationRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> AutomationResponse:
    fields = request.model_dump(exclude_unset=True)
    try:
        automation = automation_queries.update_automation(
            db, _user_uuid(user_id), automation_id, fields
        )
    except MachineNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except InvalidScheduleError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if automation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found"
        )
    return AutomationResponse.model_validate(automation)


@automation_router.delete(
    "/automations/{automation_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_automation_endpoint(
    automation_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> None:
    if not automation_queries.delete_automation(db, _user_uuid(user_id), automation_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found"
        )


@automation_router.get(
    "/automations/{automation_id}/runs",
    response_model=list[AutomationRunResponse],
)
def list_automation_runs_endpoint(
    automation_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> list[AutomationRunResponse]:
    try:
        runs = automation_queries.list_runs(db, _user_uuid(user_id), automation_id)
    except AutomationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return [AutomationRunResponse.model_validate(r) for r in runs]
