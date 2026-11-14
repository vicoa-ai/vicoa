"""`#` references API — the composer's Vicoa-entity picker.

Three endpoints, all owner-scoped:

* ``GET /references`` fills the panel (an empty ``q`` is legal and means
  "what's live and recent").
* ``GET /references/{kind}/{id}`` expands one pick into the text block the
  client appends to the outgoing message.
* ``POST /agent-instances/{id}/references`` runs after the send: each task
  the message referenced notes, in its activity, that this session named it.

A reference does not file the session under the task. That is
``PATCH /agent-instances/{id}`` with ``task_id`` (the §8b late link), which
also moves the task to in_progress, and the composer no longer calls it for a
`#`: naming a task in a message is not starting work on it. Starting a session
from the task (its chip, ``?taskId=``, ``--task``) still does.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from shared.database.models import User
from shared.database.session import get_db

from ..auth.dependencies import get_current_user
from ..db import reference_queries
from ..models import (
    RecordReferencesRequest,
    RecordReferencesResponse,
    ReferenceCandidate,
    ReferenceCandidatesResponse,
    ReferenceDetail,
    ReferenceKindLiteral,
)

router = APIRouter(tags=["references"])


@router.get("/references", response_model=ReferenceCandidatesResponse)
def list_references_endpoint(
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=reference_queries.GROUP_LIMIT, ge=1, le=25),
    # The session doing the referencing. Dropped from the results — offering a
    # session a reference to itself is never what "#" means.
    exclude_session_id: UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReferenceCandidatesResponse:
    items = reference_queries.list_reference_candidates(
        db,
        current_user.id,
        query=q,
        limit=limit,
        exclude_session_id=exclude_session_id,
    )
    return ReferenceCandidatesResponse(
        query=q,
        items=[ReferenceCandidate.model_validate(item) for item in items],
    )


@router.get("/references/{kind}/{ref_id}", response_model=ReferenceDetail)
def get_reference_endpoint(
    kind: ReferenceKindLiteral,
    ref_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReferenceDetail:
    detail = reference_queries.get_reference(db, current_user.id, kind, ref_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found"
        )
    return ReferenceDetail.model_validate(detail)


@router.post(
    "/agent-instances/{instance_id}/references",
    response_model=RecordReferencesResponse,
)
def record_references_endpoint(
    instance_id: UUID,
    request: RecordReferencesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecordReferencesResponse:
    """Record the tasks a message sent in this session referenced.

    Fire-and-forget from the composer: a task it can't record is skipped, not
    an error. 404 for a session the caller can't see, 403 for one they can
    only read.
    """
    recorded = reference_queries.record_task_references(
        db, current_user.id, instance_id, request.task_ids
    )
    if recorded is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent instance not found"
        )
    return RecordReferencesResponse(recorded_task_ids=recorded)
