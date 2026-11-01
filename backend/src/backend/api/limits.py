"""Plan limits — what the caller has used, and what their plan allows.

One endpoint so no client ever carries a plan number of its own. A cap changes
server-side and every surface (web, desktop, mobile) follows on the next read;
nothing here needs an App Store release to reprice.

The numbers come from the closed overlay through `shared.limits`. With no
overlay — the open-source / self-hosted build — every resource reports
`limit: null` (unlimited), which is what a client must render as "no limit",
never as zero.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared import limits as plan_limits
from shared.database.models import User
from shared.database.session import get_db

from ..auth.dependencies import get_current_user
from ..models import LimitStatusResponse, LimitsResponse

router = APIRouter(tags=["limits"])
logger = logging.getLogger(__name__)


def _to_response(status: plan_limits.LimitStatus) -> LimitStatusResponse:
    return LimitStatusResponse(
        key=status.key,
        label=status.label,
        unit=status.unit,
        period=status.period,
        used=status.used,
        limit=status.limit,
        remaining=status.remaining,
        unlimited=status.unlimited,
    )


@router.get("/limits", response_model=LimitsResponse)
def get_limits_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LimitsResponse:
    """Usage and cap for every metered resource.

    Read through the same call the enforcement path uses, so what this returns
    and what the next write will actually be allowed to do cannot disagree.
    """
    return LimitsResponse(
        limits=[
            _to_response(s) for s in plan_limits.describe_limits(db, current_user.id)
        ]
    )
