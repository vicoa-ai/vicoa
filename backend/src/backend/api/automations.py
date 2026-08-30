"""Automations API (automation-scheduled-tasks plan §v1).

Scheduled agent runs: a saved prompt + agent/model + machine/folder that fires an
agent session automatically at a chosen time. CRUD is human-facing (Supabase JWT);
the actual dispatch happens in the `server` process (scheduler sweep, or the web's
client-side spawn for "run now"). This router only reads/writes the DB rows —
`POST /automations/{id}/run` records a manual dispatch's outcome, it does not itself
reach a daemon (rpc_router is process-local to `server`).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from shared.database.models import User
from shared.database.session import get_db

from ..auth.dependencies import get_current_user
from ..db import automation_queries
from ..db.automation_queries import (
    AutomationNotFoundError,
    InvalidScheduleError,
    MachineNotFoundError,
)
from ..models import (
    AutomationResponse,
    AutomationRunResponse,
    CreateAutomationRequest,
    RecordAutomationRunRequest,
    UpdateAutomationRequest,
)

router = APIRouter(tags=["automations"])


@router.get("/automations", response_model=list[AutomationResponse])
def list_automations_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AutomationResponse]:
    rows = automation_queries.list_automations(db, current_user.id)
    return [AutomationResponse.model_validate(r) for r in rows]


@router.post(
    "/automations",
    response_model=AutomationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_automation_endpoint(
    request: CreateAutomationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AutomationResponse:
    try:
        automation = automation_queries.create_automation(
            db,
            current_user.id,
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


@router.get("/automations/{automation_id}", response_model=AutomationResponse)
def get_automation_endpoint(
    automation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AutomationResponse:
    automation = automation_queries.get_automation(db, current_user.id, automation_id)
    if automation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found"
        )
    return AutomationResponse.model_validate(automation)


@router.patch("/automations/{automation_id}", response_model=AutomationResponse)
def update_automation_endpoint(
    automation_id: UUID,
    request: UpdateAutomationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AutomationResponse:
    fields = request.model_dump(exclude_unset=True)
    try:
        automation = automation_queries.update_automation(
            db, current_user.id, automation_id, fields
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


@router.delete("/automations/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_automation_endpoint(
    automation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not automation_queries.delete_automation(db, current_user.id, automation_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found"
        )


@router.get(
    "/automations/{automation_id}/runs",
    response_model=list[AutomationRunResponse],
)
def list_automation_runs_endpoint(
    automation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AutomationRunResponse]:
    try:
        runs = automation_queries.list_runs(db, current_user.id, automation_id)
    except AutomationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return [AutomationRunResponse.model_validate(r) for r in runs]


@router.post(
    "/automations/{automation_id}/run",
    response_model=AutomationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_automation_run_endpoint(
    automation_id: UUID,
    request: RecordAutomationRunRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AutomationRunResponse:
    """Record the outcome of a manual "run now" the web dispatched over its WS."""
    try:
        run = automation_queries.record_run(
            db,
            current_user.id,
            automation_id,
            status=request.status,
            agent_instance_id=request.agent_instance_id,
            detail=request.detail,
        )
    except AutomationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return AutomationRunResponse.model_validate(run)
