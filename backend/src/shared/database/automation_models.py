"""Automations — user-scheduled agent runs (plans/todos/automation-scheduled-tasks.md).

An `Automation` is a saved prompt + agent/model + machine/folder that fires an
agent session automatically at a chosen time (once, or on a recurring cron
schedule). A server-side sweep loop (src/servers/scheduler/) claims due rows and
dispatches them via the existing `spawn-session` WebSocket RPC; each dispatch
writes an `AutomationRun` history row.

Schedule is stored as a 5-field cron expression + IANA timezone (recurring) or an
absolute UTC `next_run_at` (one-time). Status/kind are varchar + CHECK (task_models
style) rather than native PG enums so the vocabulary can grow without a migration;
timestamps are timestamptz (new-table convention).
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base

AUTOMATION_SCHEDULE_KINDS = ("once", "recurring")
AUTOMATION_RUN_STATUSES = ("fired", "missed_offline", "failed", "skipped")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Automation(Base):
    __tablename__ = "automations"
    __table_args__ = (
        CheckConstraint(
            "schedule_kind IN ('once','recurring')",
            name="ck_automations_schedule_kind",
        ),
        Index("ix_automations_user", "user_id"),
        # The sweep's hot path: enabled rows ordered by when they're next due.
        Index("ix_automations_next_run", "next_run_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )

    title: Mapped[str] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text)

    # NOT NULL + CASCADE: an automation always targets one machine; if that
    # machine is removed the automation goes with it (no orphan rows that could
    # never dispatch). machine_id is the machines PK (uuid); its string form is
    # the rpc_router routing key (str(machine.id), matching MachineSummary).
    machine_id: Mapped[UUID] = mapped_column(
        ForeignKey("machines.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
    )
    directory: Mapped[str] = mapped_column(Text)
    # Optional worktree spec {"mode": "none"|"new"|"existing", "path"?: str}.
    # NULL/none → run in `directory`; new → fresh worktree per run; existing →
    # run in `path`. Applied to the spawn params at dispatch time.
    worktree: Mapped[dict | None] = mapped_column(JSONB, default=None)

    # User-visible spawn config (agent / model / effort / permission-mode),
    # mirroring the web SessionConfig / toSpawnMetadata shape. The scheduler
    # rebuilds spawn metadata from this + `prompt` at dispatch time.
    session_config: Mapped[dict] = mapped_column(JSONB)

    schedule_kind: Mapped[str] = mapped_column(String(20))
    # Structured recurring schedule (see shared/scheduling/frequency.py for the
    # shape); NULL for one-time. Replaces the earlier raw cron so "every N days /
    # weeks / months" is expressible.
    frequency: Mapped[dict | None] = mapped_column(JSONB, default=None)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    # Phase reference for interval schedules ("every N …"); set when the schedule
    # is created or its frequency changes.
    anchor_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    # Absolute UTC instant of the next fire. Held independently of `enabled` (a
    # paused row keeps it so it resumes cleanly); the sweep gates on `enabled`
    # separately. NULL only once a one-time run has fired (its terminal state).
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_run_status: Mapped[str | None] = mapped_column(String(20), default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class AutomationRun(Base):
    """One dispatch of an automation — persisted from day one (v1 UI shows only
    last-run status; full history is v2)."""

    __tablename__ = "automation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('fired','missed_offline','failed','skipped')",
            name="ck_automation_runs_status",
        ),
        Index("ix_automation_runs_automation", "automation_id", "planned_at"),
        Index("ix_automation_runs_user", "user_id"),
        # Reverse lookup by spawned session. Feeds the rate-limit sweep's
        # anti-join (exclude automation-spawned sessions from
        # `?rate_limited_only=true`) so it probes by index instead of
        # seq-scanning this table as it grows one row per dispatch; also spares
        # the ON DELETE SET NULL FK a table scan on every agent_instance delete.
        Index("ix_automation_runs_agent_instance", "agent_instance_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    automation_id: Mapped[UUID] = mapped_column(
        ForeignKey("automations.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    # The spawned session. SET NULL so deleting the session leaves the history
    # row intact. Linked only when the agent has self-registered by record time
    # (the spawn RPC returns before registration; v1 does a short bounded wait).
    agent_instance_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        default=None,
    )

    # The scheduled occurrence this run satisfies (NULL for ad-hoc "run now").
    planned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    status: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
