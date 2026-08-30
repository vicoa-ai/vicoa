"""`AuthProvider` with no external IdP — the self-hosted default.

Identity lives entirely in our own Postgres: `users` (already the source of
truth for everything else) plus `user_credentials` for the password. Sessions
are RS256 JWTs signed with the **existing** `JWT_PRIVATE_KEY` keypair, the same
one that signs agent API keys, so a self-hosted deployment needs no new key
material and no new crypto — only the `typ` claim distinguishes a browser
session from an API key (see :mod:`shared.auth.agent_tokens`).

Email is optional by design. Sign-up works with nothing but a password, because
requiring a mail provider before a self-hoster can log into their own instance
is a bad first five minutes. When a provider *is* configured, address
verification and password reset ride on `auth_email_codes`.

This module holds the identity logic only. The HTTP surface that drives it
lives in `backend/auth/builtin_routes.py`, which is where email delivery
belongs — `shared` must not import `backend`.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from shared.config.settings import settings

from .agent_tokens import (
    TOKEN_TYPE_CLAIM,
    USER_TOKEN_TYPE,
    create_signed_jwt,
    decode_vicoa_jwt,
)
from .base import Principal, ProviderUser, TokenVerificationError
from .passwords import hash_password, needs_rehash, verify_password

logger = logging.getLogger(__name__)

BUILTIN_ISSUER = "vicoa"
BUILTIN_AUDIENCE = "vicoa-user"

MIN_PASSWORD_LENGTH = 8
EMAIL_CODE_LENGTH = 6
EMAIL_CODE_TTL = timedelta(minutes=15)

# A hash computed against a throwaway password when the account does not exist,
# so sign-in takes the same ~50 ms whether or not the email is registered and
# cannot be used to enumerate accounts.
_DUMMY_HASH = (
    "scrypt$32768$8$1$AAAAAAAAAAAAAAAAAAAAAA==$"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
)


class BuiltinAuthError(Exception):
    """Base class for built-in-provider sign-up / sign-in failures."""


class SignupDisabled(BuiltinAuthError):
    """`BUILTIN_ALLOW_SIGNUP` is off."""


class EmailAlreadyRegistered(BuiltinAuthError):
    """That address already has an account."""


class WeakPassword(BuiltinAuthError):
    """The password is shorter than `MIN_PASSWORD_LENGTH`."""


class InvalidCredentials(BuiltinAuthError):
    """Unknown email, or wrong password."""


class EmailNotVerified(BuiltinAuthError):
    """Verification is required and this address has not been proven."""


class InvalidEmailCode(BuiltinAuthError):
    """The code is unknown, already used, or expired."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BuiltinAuthProvider:
    """Verify our own user-session JWTs; the admin plane is just Postgres."""

    name = "builtin"

    def verify_user_token(self, token: str) -> Principal:
        if not token:
            raise TokenVerificationError("Missing access token")

        claims = decode_vicoa_jwt(token)

        if claims.get(TOKEN_TYPE_CLAIM) != USER_TOKEN_TYPE:
            # An agent API key must not double as a browser session: it is
            # long-lived and can mint more keys from the user-facing API.
            raise TokenVerificationError("Token is not a user session")
        if claims.get("iss") != BUILTIN_ISSUER:
            raise TokenVerificationError("Token was not issued by this server")
        if claims.get("aud") != BUILTIN_AUDIENCE:
            raise TokenVerificationError("Token has the wrong audience")

        sub = claims.get("sub")
        try:
            user_id = UUID(str(sub))
        except (ValueError, TypeError) as exc:
            raise TokenVerificationError("Token missing valid subject") from exc

        return Principal(
            user_id=user_id,
            kind="user",
            email=claims.get("email"),
            display_name=claims.get("name"),
        )

    def fetch_user(self, user_id: UUID) -> ProviderUser | None:
        """Read the local row — with no external IdP, `users` *is* the provider."""
        from shared.database.models import User
        from shared.database.session import SessionLocal

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user is None:
                return None
            return ProviderUser(
                user_id=user.id, email=user.email, display_name=user.display_name
            )
        finally:
            db.close()

    def update_user_profile(self, user_id: UUID, display_name: str | None) -> None:
        """No-op: the caller already wrote the local row, and there is no copy."""

    def delete_user(self, user_id: UUID) -> None:
        """No-op: `user_credentials` and `auth_email_codes` cascade from `users`."""


# --- credential operations (driven by backend/auth/builtin_routes.py) --------


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_session_token(
    user_id: UUID, email: str | None = None, display_name: str | None = None
) -> tuple[str, datetime]:
    """Mint a browser session token. Returns `(token, expires_at)`."""
    now = _utc_now()
    expires_at = now + timedelta(hours=settings.builtin_session_ttl_hours)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        TOKEN_TYPE_CLAIM: USER_TOKEN_TYPE,
        "iss": BUILTIN_ISSUER,
        "aud": BUILTIN_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if email:
        payload["email"] = email
    if display_name:
        payload["name"] = display_name
    return create_signed_jwt(payload), expires_at


def register_user(
    db: Session, email: str, password: str, display_name: str | None = None
):
    """Create a local account. Raises `BuiltinAuthError` on refusal."""
    from shared.database.models import User

    if not settings.builtin_allow_signup:
        raise SignupDisabled("Sign-up is disabled on this server")

    address = normalize_email(email)
    if not address:
        raise InvalidCredentials("Email is required")
    _assert_password_strength(password)

    if db.query(User).filter(User.email == address).first():
        raise EmailAlreadyRegistered("That email already has an account")

    user = User(
        id=uuid4(),
        email=address,
        display_name=(display_name or "").strip() or None,
    )
    db.add(user)
    db.flush()
    db.add(_new_credential(user.id, password))
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str):
    """Check an email/password pair and return the `User`."""
    from shared.database.models import User
    from shared.database.auth_models import UserCredential

    address = normalize_email(email)
    row = (
        db.query(User, UserCredential)
        .join(UserCredential, UserCredential.user_id == User.id)
        .filter(User.email == address)
        .first()
    )

    if row is None:
        # Burn the same time as a real check so a wrong email and a wrong
        # password are indistinguishable from the outside.
        verify_password(password, _DUMMY_HASH)
        raise InvalidCredentials("Incorrect email or password")

    user, credential = row
    if not verify_password(password, credential.password_hash):
        raise InvalidCredentials("Incorrect email or password")

    if (
        settings.builtin_require_email_verification
        and credential.email_verified_at is None
    ):
        raise EmailNotVerified("Confirm your email address to sign in")

    if needs_rehash(credential.password_hash):
        credential.password_hash = hash_password(password)
        db.commit()

    return user


def set_password(db: Session, user_id: UUID, password: str) -> None:
    """Set or replace a user's password."""
    from shared.database.auth_models import UserCredential

    _assert_password_strength(password)
    credential = (
        db.query(UserCredential).filter(UserCredential.user_id == user_id).first()
    )
    if credential is None:
        db.add(_new_credential(user_id, password))
    else:
        credential.password_hash = hash_password(password)
    db.commit()


def change_password(
    db: Session, user_id: UUID, current_password: str, new_password: str
) -> None:
    """Replace a password, proving knowledge of the old one first."""
    from shared.database.auth_models import UserCredential

    credential = (
        db.query(UserCredential).filter(UserCredential.user_id == user_id).first()
    )
    if credential is None or not verify_password(
        current_password, credential.password_hash
    ):
        raise InvalidCredentials("Current password is incorrect")
    set_password(db, user_id, new_password)


def issue_email_code(db: Session, user_id: UUID, purpose: str) -> str:
    """Mint a single-use code and return the **plaintext** to email out.

    Any outstanding code for the same purpose is consumed first, so a resend
    invalidates the previous message rather than leaving two live codes.
    """
    from shared.database.auth_models import AuthEmailCode

    now = _utc_now()
    db.query(AuthEmailCode).filter(
        AuthEmailCode.user_id == user_id,
        AuthEmailCode.purpose == purpose,
        AuthEmailCode.consumed_at.is_(None),
    ).update({"consumed_at": now}, synchronize_session=False)

    code = "".join(secrets.choice("0123456789") for _ in range(EMAIL_CODE_LENGTH))
    db.add(
        AuthEmailCode(
            user_id=user_id,
            purpose=purpose,
            code_hash=hash_email_code(code),
            expires_at=now + EMAIL_CODE_TTL,
        )
    )
    db.commit()
    return code


def consume_email_code(db: Session, user_id: UUID, purpose: str, code: str) -> None:
    """Spend a code, or raise `InvalidEmailCode`."""
    from shared.database.auth_models import AuthEmailCode

    now = _utc_now()
    row = (
        db.query(AuthEmailCode)
        .filter(
            AuthEmailCode.user_id == user_id,
            AuthEmailCode.purpose == purpose,
            AuthEmailCode.code_hash == hash_email_code(code.strip()),
            AuthEmailCode.consumed_at.is_(None),
            AuthEmailCode.expires_at > now,
        )
        .first()
    )
    if row is None:
        raise InvalidEmailCode("That code is invalid or has expired")
    row.consumed_at = now
    db.commit()


def mark_email_verified(db: Session, user_id: UUID) -> None:
    from shared.database.auth_models import UserCredential

    credential = (
        db.query(UserCredential).filter(UserCredential.user_id == user_id).first()
    )
    if credential is not None:
        credential.email_verified_at = _utc_now()
        db.commit()


def hash_email_code(code: str) -> str:
    """Codes are stored hashed for the same reason API keys are."""
    return hashlib.sha256(code.encode()).hexdigest()


def _new_credential(user_id: UUID, password: str):
    from shared.database.auth_models import UserCredential

    return UserCredential(user_id=user_id, password_hash=hash_password(password))


def _assert_password_strength(password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise WeakPassword(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
        )
