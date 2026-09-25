"""`#` references API — the composer's Vicoa-entity picker.

Two endpoints, both owner-scoped:

* ``GET /references`` fills the panel (an empty ``q`` is legal and means
  "what's live and recent").
* ``GET /references/{kind}/{id}`` expands one pick into the text block the
  client appends to the outgoing message.

Linking a referenced task to the session is *not* here: that is the existing
``PATCH /agent-instances/{id}`` with ``task_id``, which already does the access
check and moves the task to in_progress. A `#` reference to a task is the same
late link the tasks plan calls §8b, triggered from the composer.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from shared.database.models import User
from shared.database.session import get_db

from ..auth.dependencies import get_current_user
from ..db import reference_queries
from ..models import (
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
