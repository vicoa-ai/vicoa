"""Local credentials for the built-in auth provider (self-hosted deployments).

With `AUTH_PROVIDER=supabase` (the hosted deployment) these tables stay empty —
identity lives in Supabase and `users` is only a mirror. With
`AUTH_PROVIDER=builtin` they *are* the identity store, which is what lets a
self-hosted Vicoa run with no external SaaS at all.

Split out of `users` rather than added to it so that the two provider modes
share one `users` table: the mirror keeps exactly the columns the product needs,
and password material only exists for accounts that actually have a password.

Timestamps are timestamptz (new-table convention); `purpose` is varchar + CHECK
(task_models style) so a new code flow does not need a migration.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base

# verify_email → prove the address on sign-up; reset_password → the forgot-password
# flow. Both are single-use and short-lived.
EMAIL_CODE_PURPOSES = ("verify_email", "reset_password")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserCredential(Base):
    """A password for a locally-managed account. One row per user, at most."""

    __tablename__ = "user_credentials"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
        primary_key=True,
    )
    # Self-describing hash ("scrypt$n$r$p$salt$hash") so cost parameters can be
    # raised later without invalidating existing rows — see shared.auth.passwords.
    password_hash: Mapped[str] = mapped_column(String(255))
    # Null until the address is proven. Only enforced when
    # BUILTIN_REQUIRE_EMAIL_VERIFICATION is on, so a deployment with no mail
    # provider is not locked out of its own instance.
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class AuthEmailCode(Base):
    """A single-use code emailed to prove an address or reset a password.

    Stored as a hash for the same reason API keys are: a database read must not
    hand over a working credential.
    """

    __tablename__ = "auth_email_codes"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('verify_email', 'reset_password')",
            name="ck_auth_email_codes_purpose",
        ),
        Index("ix_auth_email_codes_user_purpose", "user_id", "purpose"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
    )
    purpose: Mapped[str] = mapped_column(String(32))
    code_hash: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
