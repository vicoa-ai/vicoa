"""Support endpoints — report an issue."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.email_service import send_support_issue_email
from shared.config import settings
from shared.database.models import User
from shared.database.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["support"])


class ReportIssueRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1500)


@router.post("/report-issue")
async def report_issue(
    request: ReportIssueRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not settings.support_email:
        # No support inbox configured (open-source / self-host default).
        raise HTTPException(status_code=503, detail="Support inbox is not configured")
    sent = await send_support_issue_email(
        to_email=settings.support_email,
        from_user_email=current_user.email,
        from_user_name=current_user.display_name or "",
        message=request.message,
    )
    if not sent:
        raise HTTPException(status_code=500, detail="Failed to send report")
    return {"status": "sent"}
