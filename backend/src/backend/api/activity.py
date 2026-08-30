"""Aggregated profile activity for the desktop Settings -> Profile page.

Daily counts of the user's own (user-sent) messages plus all-time session and
message totals. `daily` (user messages per UTC day) drives the heatmap/streak;
`total_user_messages` is the "Messages" tile, `total_messages` (user + agent)
is the "Total messages" tile. Everything is scoped to the user's own sessions.

Lives in the `backend` app (backend.main), which serves api.vicoa.ai — the host
the web/desktop REST client targets. The aggregation itself is in
backend.db.get_user_activity.
"""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from shared.database.session import get_db

from ..auth.dependencies import get_current_user_id
from ..db import get_user_activity
from ..models import ActivityResponse

router = APIRouter(tags=["activity"])


@router.get("/activity", response_model=ActivityResponse)
def get_activity(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    since: str | None = None,
    db: Session = Depends(get_db),
) -> ActivityResponse:
    """Return the user's daily activity + totals.

    `since` (a UTC `YYYY-MM-DD` day) limits `daily` to that day onward so the
    client can sync incrementally; totals stay all-time.
    """
    since_dt: datetime | None = None
    if since is not None:
        try:
            # Naive midnight — matches the naive-UTC created_at column.
            since_dt = datetime.strptime(since, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="`since` must be a YYYY-MM-DD date",
            )

    activity = get_user_activity(db, user_id, since_dt)
    return ActivityResponse(**activity, as_of=datetime.now(timezone.utc).isoformat())
