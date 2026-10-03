"""Automations API (automation-scheduled-tasks plan §v1).

Scheduled agent runs: a saved prompt + agent/model + machine/folder that fires an
agent session automatically at a chosen time. CRUD is human-facing (Supabase JWT);
the actual dispatch happens in the `server` process (scheduler sweep, or the web's
client-side spawn for "run now"). This router only reads/writes the DB rows —
`POST /automations/{id}/run` records a manual dispatch's outcome, it does not itself
reach a daemon (rpc_router is process-local to `server`).

Collaborators *read* an automation through the project its folder files it
under, when their standing covers that project's `automations` scope
(collaboration §10.6): `?scope=all` and `?project_id=` on the list, and GET on
one automation and its runs. Their rows are redacted like a shared session row. Edit, delete
and run-now stay the author's alone: a collaborator who can see the
automation gets 403, anyone else the 404 of a missing id.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, load_only

from shared import access, grantee_view
from shared.database.models import AgentInstance, User
from shared.database.session import get_db

from ..auth.dependencies import get_current_user
from ..db import automation_queries
from ..db.automation_queries import (
    AgentProfileNotFoundError,
    AutomationNotFoundError,
    InvalidScheduleError,
    MachineNotFoundError,
    VisibleAutomation,
)
from shared.database.project_matching import resolve_automation_project_ids

from ..db.queries import _user_principal
from ..models import (
    AutomationOrderResponse,
    AutomationResponse,
    AutomationRunResponse,
    CreateAutomationRequest,
    RecordAutomationRunRequest,
    SetAutomationOrderRequest,
    UpdateAutomationRequest,
)

router = APIRouter(tags=["automations"])


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found"
    )


def _require_author(db: Session, user_id: UUID, automation_id: UUID) -> None:
    """Writes are the author's alone. 403 for a collaborator who can see the
    automation, 404 for anyone else, so the answer never confirms that an
    automation the caller cannot see exists."""
    visible = automation_queries.get_visible_automation(db, user_id, automation_id)
    if visible is None:
        raise _not_found()
    access.require(visible.role, "owner")


def _responses_for(
    db: Session, visibles: list[VisibleAutomation]
) -> list[AutomationResponse]:
    """Serialize rows the caller can see, redacting every one they did not
    write. Every row says which project it is filed under (the web filters by
    it); authors and unresolved projects are fetched in one batch each."""
    unresolved = [v.automation for v in visibles if v.project_id is None]
    projects = resolve_automation_project_ids(db, unresolved) if unresolved else {}
    author_ids = {v.automation.user_id for v in visibles if v.role != "owner"}
    authors = (
        {u.id: u for u in db.query(User).filter(User.id.in_(author_ids))}
        if author_ids
        else {}
    )
    out: list[AutomationResponse] = []
    for visible in visibles:
        response = AutomationResponse.model_validate(visible.automation)
        response.project_id = visible.project_id or projects.get(visible.automation.id)
        if visible.role != "owner":
            _redact_for_collaborator(
                response, authors.get(visible.automation.user_id), visible
            )
        out.append(response)
    return out


def _redact_for_collaborator(
    response: AutomationResponse, author: User | None, visible: VisibleAutomation
) -> None:
    """What a collaborator may see of an automation: the same line a shared
    session row draws (`queries.redact_for_grantee`). What it does and when —
    title, prompt, schedule, agent and model — but nothing that locates the
    author's machine, and nothing to aim a spawn or RPC at."""
    response.owner = _user_principal(author)
    response.viewer_role = visible.role  # type: ignore[assignment]
    response.machine_id = None
    response.directory = grantee_view.project_label(response.directory) or ""
    mode = response.worktree.get("mode") if response.worktree else None
    response.worktree = {"mode": mode} if mode else None
    response.session_config = (
        grantee_view.display_session_config(response.session_config) or {}
    )
    # The author's own agent, or a team agent the caller may not belong to:
    # the display subset above already says which agent and model run.
    response.agent_profile_id = None


@router.get("/automations", response_model=list[AutomationResponse])
def list_automations_endpoint(
    scope: Literal["me", "all"] = Query(
        "me",
        description=(
            "me (default): your own automations, in every project, which is "
            "what the CLI and mobile read. all: those plus collaborators' "
            "automations in every project whose automations you can see "
            "(read-only, redacted)."
        ),
    ),
    project_id: UUID | None = Query(
        None,
        description=(
            "Every automation filed in that project that you can see, yours "
            "and, if your standing covers its automations, collaborators'. "
            "Overrides `scope`."
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AutomationResponse]:
    if project_id is not None:
        visibles = automation_queries.list_project_automations(
            db, current_user.id, project_id
        )
    elif scope == "all":
        visibles = automation_queries.list_visible_automations(db, current_user.id)
    else:
        visibles = [
            VisibleAutomation(a, "owner")
            for a in automation_queries.list_automations(db, current_user.id)
        ]
    return _responses_for(db, visibles)


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
            agent_profile_id=request.agent_profile_id,
            schedule_kind=request.schedule_kind,
            frequency=request.frequency,
            timezone=request.timezone,
            run_at=request.run_at,
            enabled=request.enabled,
        )
    except (MachineNotFoundError, AgentProfileNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except InvalidScheduleError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return _responses_for(db, [VisibleAutomation(automation, "owner")])[0]


# Declared before the `/automations/{automation_id}` routes on purpose: that
# path param is typed UUID, so "order" would otherwise be matched there and 422.
@router.put("/automations/order", response_model=AutomationOrderResponse)
def set_automation_order_endpoint(
    request: SetAutomationOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AutomationOrderResponse:
    """Save the caller's drag order. It is their view only, so any automation
    they can see may be ranked, a collaborator's included, and nobody else's
    list moves."""
    stored = automation_queries.set_automation_order(
        db, current_user.id, request.automation_ids
    )
    return AutomationOrderResponse(automation_ids=stored)


@router.get("/automations/{automation_id}", response_model=AutomationResponse)
def get_automation_endpoint(
    automation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AutomationResponse:
    visible = automation_queries.get_visible_automation(
        db, current_user.id, automation_id
    )
    if visible is None:
        raise _not_found()
    return _responses_for(db, [visible])[0]


@router.patch("/automations/{automation_id}", response_model=AutomationResponse)
def update_automation_endpoint(
    automation_id: UUID,
    request: UpdateAutomationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AutomationResponse:
    _require_author(db, current_user.id, automation_id)
    fields = request.model_dump(exclude_unset=True)
    try:
        automation = automation_queries.update_automation(
            db, current_user.id, automation_id, fields
        )
    except (MachineNotFoundError, AgentProfileNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except InvalidScheduleError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if automation is None:
        raise _not_found()
    return _responses_for(db, [VisibleAutomation(automation, "owner")])[0]


@router.delete("/automations/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_automation_endpoint(
    automation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _require_author(db, current_user.id, automation_id)
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
    visible = automation_queries.get_visible_automation(
        db, current_user.id, automation_id
    )
    if visible is None:
        raise _not_found()
    # The author's history either way; a collaborator gets it redacted below.
    runs = automation_queries.list_runs(db, visible.automation.user_id, automation_id)
    responses = [AutomationRunResponse.model_validate(r) for r in runs]
    if visible.role != "owner":
        _redact_runs_for_collaborator(db, current_user.id, responses)
    return responses


def _redact_runs_for_collaborator(
    db: Session, user_id: UUID, runs: list[AutomationRunResponse]
) -> None:
    """A run links its session only when the caller can open that session
    (it is usually filed in the same project, but need not be), and drops the
    failure `detail`, which carries whatever the author's daemon reported."""
    instance_ids = {r.agent_instance_id for r in runs if r.agent_instance_id}
    instances = (
        db.query(AgentInstance)
        # Only what the resolver reads; `git_diff` is unbounded.
        .options(
            load_only(
                AgentInstance.id,
                AgentInstance.user_id,
                AgentInstance.status,
                AgentInstance.project_id,
            )
        )
        .filter(AgentInstance.id.in_(instance_ids))
        .all()
        if instance_ids
        else []
    )
    openable = {
        iid
        for iid, role in access.instance_roles(db, user_id, instances).items()
        if role
    }
    for run in runs:
        run.detail = None
        if run.agent_instance_id not in openable:
            run.agent_instance_id = None


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
    _require_author(db, current_user.id, automation_id)
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
