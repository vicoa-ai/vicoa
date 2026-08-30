"""Activation nudges — re-engagement touches for signups who never activated.

A signup who has not yet sent a first message ("never activated") gets a short,
**signup-anchored** drip of push + email nudges (plans/todos/activation-improvement-roadmap.md
§B "Push re-engagement"). A backend-side sweep (src/backend/activation/) computes each
touch's due time as ``users.created_at + a fixed offset`` — no per-user timezone needed:
the +24h/+72h touches land at the user's own signup wall-clock hour (awake by
construction, since they were onboarding then).

One row per delivered/attempted touch, uniquely keyed by ``(user_id, channel, step)``
so a touch is sent at most once and the sweep is safe across overlapping runs and
backend replicas — a touch is claimed with ``INSERT ... ON CONFLICT DO NOTHING``. This
table is also the frequency-cap + stop-on-activation ledger: the sweep only enrolls
users with no USER message and never re-sends a recorded touch. Status/channel are
varchar + CHECK (task_models style) so the vocabulary can grow without a migration;
timestamps are timestamptz (new-table convention).
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base

ACTIVATION_NUDGE_CHANNELS = ("push", "email")
# pending → the sweep claimed the slot and is sending; sent/failed/skipped are terminal.
ACTIVATION_NUDGE_STATUSES = ("pending", "sent", "failed", "skipped")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ActivationNudge(Base):
    """One activation re-engagement touch (push or email) for a non-activated user."""

    __tablename__ = "activation_nudges"
    __table_args__ = (
        # A given touch is recorded once per user — the dedup + claim guarantee.
        UniqueConstraint(
            "user_id", "channel", "step", name="uq_activation_nudges_user_channel_step"
        ),
        CheckConstraint(
            "channel IN ('push','email')", name="ck_activation_nudges_channel"
        ),
        CheckConstraint(
            "status IN ('pending','sent','failed','skipped')",
            name="ck_activation_nudges_status",
        ),
        Index("ix_activation_nudges_user", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )

    channel: Mapped[str] = mapped_column(String(20))
    # 1-based touch number within the channel's sequence (1, 2, 3).
    step: Mapped[int] = mapped_column(Integer)

    # The computed due instant (users.created_at + the channel/step offset). Kept so
    # analytics can see planned-vs-sent latency and the sweep can skip stale touches.
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(20), default="pending")
    detail: Mapped[str | None] = mapped_column(Text, default=None)
    # Set when the touch resolves (sent/failed/skipped); NULL while pending.
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
