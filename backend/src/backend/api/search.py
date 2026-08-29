"""Workspace search API — powers the web dashboard's cmd+K palette.

One endpoint fans out to per-entity queries (sessions, tasks, automations)
in backend.db.search_queries and returns grouped, ranked results.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from shared.database.models import User
from shared.database.session import get_db

from ..auth.dependencies import get_current_user
from ..db import search_queries
from ..models import (
    SearchAutomationResult,
    SearchSessionResult,
    SearchTaskResult,
    WorkspaceSearchResponse,
)

router = APIRouter(tags=["search"])

# Automations are a short list per user; a lower cap keeps the palette's
# third group from crowding out sessions and tasks.
AUTOMATION_LIMIT = 10

# Backstop, not the primary defense (that's the trigram index plus the
# recency-bounded short-pattern path in search_queries): a pattern whose
# trigrams are all extremely common can still fetch a large candidate set.
# Aborting the HTTP request does NOT cancel the Postgres query, so without a
# cap a slow scan keeps holding a pooled connection to completion — bound it
# and surface a retryable 503 instead.
SEARCH_STATEMENT_TIMEOUT_MS = 3000

# SQLSTATE for "canceling statement due to statement timeout".
_STATEMENT_TIMEOUT_PGCODE = "57014"


def is_statement_timeout(exc: OperationalError) -> bool:
    return getattr(exc.orig, "pgcode", None) == _STATEMENT_TIMEOUT_PGCODE


@router.get("/search", response_model=WorkspaceSearchResponse)
def search_workspace(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceSearchResponse:
    term = q.strip()
    if not term:
        return WorkspaceSearchResponse(query=q, sessions=[], tasks=[], automations=[])

    # SET LOCAL is transaction-scoped (the Session autobegins on first
    # execute), so the pooled connection comes back clean either way.
    db.execute(text(f"SET LOCAL statement_timeout = {SEARCH_STATEMENT_TIMEOUT_MS}"))
    db.execute(text("SET LOCAL transaction_read_only = on"))
    try:
        sessions = search_queries.search_sessions(db, current_user.id, term, limit)
        tasks = search_queries.search_tasks(db, current_user.id, term, limit)
        automations = search_queries.search_automations(
            db, current_user.id, term, min(limit, AUTOMATION_LIMIT)
        )
    except OperationalError as exc:
        if is_statement_timeout(exc):
            raise HTTPException(
                status_code=503,
                detail="Search timed out — refine your query and try again.",
            ) from exc
        raise
    return WorkspaceSearchResponse(
        query=term,
        sessions=[SearchSessionResult.model_validate(row) for row in sessions],
        tasks=[SearchTaskResult.model_validate(row) for row in tasks],
        automations=[SearchAutomationResult.model_validate(row) for row in automations],
    )
