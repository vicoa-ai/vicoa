"""HTTP surface for the built-in auth provider (self-hosted deployments).

Mounted only when `AUTH_PROVIDER` resolves to ``builtin`` — a Supabase-backed
deployment must not expose a second way to create accounts. The identity logic
lives in :mod:`shared.auth.builtin_provider`; what this module adds is the
request/response shapes and email delivery, which `shared` cannot reach.

Email is optional throughout. When no transport is configured the one-time code
is written to the server log instead of being sent, so a fresh self-hosted
instance is usable before any mail provider exists.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from shared.auth import builtin_provider as builtin
from shared.config import settings
from shared.database.models import User
from shared.database.session import get_db
from sqlalchemy.orm import Session

from .. import email_service
from .dependencies import _schedule_signup_side_effects, get_current_user

router = APIRouter(prefix="/auth/builtin", tags=["auth"])
logger = logging.getLogger(__name__)


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class EmailRequest(BaseModel):
    email: EmailStr


class CodeRequest(BaseModel):
    email: EmailStr
    code: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str


class SessionUser(BaseModel):
    id: str
    email: str
    display_name: str | None


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: SessionUser


@router.post("/sign-up", response_model=SessionResponse)
async def sign_up(
    request: SignUpRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> SessionResponse:
    """Create a local account and return a session for it."""
    try:
        user = builtin.register_user(
            db, request.email, request.password, request.display_name
        )
    except builtin.BuiltinAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # With Supabase the local row appears on first authenticated request, and
    # the signup side effects hang off that JIT create. Here the row is created
    # up front, so this is the moment.
    _schedule_signup_side_effects(background_tasks, user)

    if settings.builtin_require_email_verification:
        await _deliver_code(db, user, "verify_email")

    return _session_for(user)


@router.post("/sign-in", response_model=SessionResponse)
async def sign_in(
    request: SignInRequest, db: Session = Depends(get_db)
) -> SessionResponse:
    """Exchange an email and password for a session token."""
    try:
        user = builtin.authenticate_user(db, request.email, request.password)
    except builtin.EmailNotVerified as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except builtin.BuiltinAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    return _session_for(user)


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Replace the signed-in user's password."""
    try:
        builtin.change_password(
            db, current_user.id, request.current_password, request.new_password
        )
    except builtin.InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except builtin.BuiltinAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Password updated"}


@router.post("/request-email-verification")
async def request_email_verification(
    request: EmailRequest, db: Session = Depends(get_db)
):
    """Send (or log) a code proving control of an address."""
    user = _find_user(db, request.email)
    if user is not None:
        await _deliver_code(db, user, "verify_email")
    return _code_sent_response()


@router.post("/verify-email")
async def verify_email(request: CodeRequest, db: Session = Depends(get_db)):
    """Spend a verification code."""
    user = _find_user(db, request.email)
    if user is None:
        raise HTTPException(
            status_code=400, detail="That code is invalid or has expired"
        )
    try:
        builtin.consume_email_code(db, user.id, "verify_email", request.code)
    except builtin.InvalidEmailCode as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    builtin.mark_email_verified(db, user.id)
    return {"message": "Email verified"}


@router.post("/forgot-password")
async def forgot_password(request: EmailRequest, db: Session = Depends(get_db)):
    """Start a password reset.

    Always reports success: whether an address has an account is not something
    an unauthenticated caller gets to learn.
    """
    user = _find_user(db, request.email)
    if user is not None:
        await _deliver_code(db, user, "reset_password")
    return _code_sent_response()


@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Finish a password reset with the emailed code."""
    user = _find_user(db, request.email)
    if user is None:
        raise HTTPException(
            status_code=400, detail="That code is invalid or has expired"
        )
    try:
        builtin.consume_email_code(db, user.id, "reset_password", request.code)
        builtin.set_password(db, user.id, request.new_password)
    except builtin.InvalidEmailCode as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except builtin.BuiltinAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Password updated"}


def _session_for(user: User) -> SessionResponse:
    token, expires_at = builtin.create_session_token(
        user.id, user.email, user.display_name
    )
    return SessionResponse(
        access_token=token,
        expires_at=expires_at,
        user=SessionUser(
            id=str(user.id), email=user.email, display_name=user.display_name
        ),
    )


def _find_user(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == builtin.normalize_email(email)).first()


async def _deliver_code(db: Session, user: User, purpose: str) -> None:
    code = builtin.issue_email_code(db, user.id, purpose)
    if not email_service.email_is_configured():
        # No mail provider: the operator reads it off the log. This is what
        # keeps a first-boot instance usable without an email account.
        logger.warning(
            "No email transport configured; %s code for %s is %s",
            purpose,
            user.email,
            code,
        )
        return
    await email_service.send_auth_code_email(user.email, code, purpose)


def _code_sent_response() -> dict[str, str]:
    return {"message": "If that address has an account, a code is on its way"}
