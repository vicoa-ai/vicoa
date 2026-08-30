"""DB queries for scheduled automations (automation-scheduled-tasks plan §v1).

All queries are user-scoped. `next_run_at` is computed here (not in the router)
from the schedule fields so create/update and the server-side scheduler agree on
one clock. History rows (`automation_runs`) are written by `record_run` — from the
manual "run now" path — and by the server scheduler directly.
"""

# `timezone` is aliased because create/update take a `timezone: str` parameter
# that would otherwise shadow datetime.timezone.
from datetime import datetime, timezone as dt_timezone
from uuid import UUID

from sqlalchemy.orm import Session

from shared.database import AgentInstance, Automation, AutomationRun, Machine
from shared.scheduling import compute_next_run, is_valid_frequency

# Schedule-DEFINING fields that, when changed, force a `next_run_at` recompute
# (and re-anchor interval schedules). `enabled` is deliberately excluded —
# pause/resume must preserve the fire time.
_SCHEDULE_FIELDS = {
    "schedule_kind",
    "frequency",
    "timezone",
    "run_at",
}


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=dt_timezone.utc)


class MachineNotFoundError(Exception):
    """Raised when the referenced machine doesn't exist or isn't the user's."""


class InvalidScheduleError(Exception):
    """Raised when the schedule fields are inconsistent (400)."""


class AutomationNotFoundError(Exception):
    """Raised when recording a run against a missing/foreign automation (404)."""


def _get_machine(db: Session, user_id: UUID, machine_id: UUID) -> Machine | None:
    return (
        db.query(Machine)
        .filter(Machine.id == machine_id, Machine.user_id == user_id)
        .first()
    )


def _resolve_next_run_at(
    *,
    schedule_kind: str,
    frequency: dict | None,
    timezone_name: str,
    run_at: datetime | None,
    anchor: datetime | None,
) -> datetime | None:
    """Validate the schedule and compute the next absolute UTC fire time.

    Independent of `enabled`: a paused automation keeps its `next_run_at` so it
    resumes cleanly (the sweep gates on `enabled` separately). Pausing/resuming
    therefore does NOT recompute — only a change to a schedule-defining field
    does — which is what lets a one-time automation (whose only record of *when*
    is `next_run_at`) survive a pause/resume round-trip."""
    if schedule_kind not in ("once", "recurring"):
        raise InvalidScheduleError("schedule_kind must be 'once' or 'recurring'")
    if schedule_kind == "once":
        if run_at is None:
            raise InvalidScheduleError("run_at is required for a one-time schedule")
        return _as_utc(run_at)
    # recurring
    if not is_valid_frequency(frequency):
        raise InvalidScheduleError("a valid `frequency` is required for recurring")
    return compute_next_run(frequency, tz_name=timezone_name, anchor=anchor)


def list_automations(db: Session, user_id: UUID) -> list[Automation]:
    return (
        db.query(Automation)
        .filter(Automation.user_id == user_id)
        .order_by(Automation.created_at.desc())
        .all()
    )


def get_automation(
    db: Session, user_id: UUID, automation_id: UUID
) -> Automation | None:
    return (
        db.query(Automation)
        .filter(Automation.id == automation_id, Automation.user_id == user_id)
        .first()
    )


def create_automation(
    db: Session,
    user_id: UUID,
    *,
    title: str,
    prompt: str,
    machine_id: UUID,
    directory: str,
    worktree: dict | None = None,
    session_config: dict,
    schedule_kind: str,
    frequency: dict | None = None,
    timezone: str = "UTC",
    run_at: datetime | None = None,
    enabled: bool = True,
) -> Automation:
    if _get_machine(db, user_id, machine_id) is None:
        raise MachineNotFoundError("Machine not found")

    # Anchor interval schedules ("every N …") to creation time.
    anchor_at = datetime.now(dt_timezone.utc)
    next_run_at = _resolve_next_run_at(
        schedule_kind=schedule_kind,
        frequency=frequency,
        timezone_name=timezone,
        run_at=run_at,
        anchor=anchor_at,
    )

    automation = Automation(
        user_id=user_id,
        title=title,
        prompt=prompt,
        machine_id=machine_id,
        directory=directory,
        worktree=worktree,
        session_config=session_config,
        schedule_kind=schedule_kind,
        frequency=frequency,
        timezone=timezone,
        anchor_at=anchor_at,
        next_run_at=next_run_at,
        enabled=enabled,
    )
    db.add(automation)
    db.commit()
    return automation


def update_automation(
    db: Session, user_id: UUID, automation_id: UUID, fields: dict
) -> Automation | None:
    """Apply the explicitly-sent PATCH fields; recompute next_run_at only when a
    schedule-DEFINING field changes. `run_at` is transient (one-time only) — it
    feeds the recompute but isn't a stored column. Toggling `enabled` alone
    (pause/resume) deliberately does NOT recompute, so a one-time automation
    keeps its stored fire time across a pause."""
    automation = get_automation(db, user_id, automation_id)
    if automation is None:
        return None

    if "machine_id" in fields:
        machine_id = fields.pop("machine_id")
        if _get_machine(db, user_id, machine_id) is None:
            raise MachineNotFoundError("Machine not found")
        automation.machine_id = machine_id

    # Decide whether to recompute BEFORE popping run_at, so a PATCH that sends
    # only run_at still triggers it.
    schedule_touched = bool(_SCHEDULE_FIELDS & set(fields))
    run_at = fields.pop("run_at", None)

    for key in (
        "title",
        "prompt",
        "directory",
        "worktree",
        "session_config",
        "schedule_kind",
        "frequency",
        "timezone",
        "enabled",
    ):
        if key in fields:
            setattr(automation, key, fields[key])

    if schedule_touched:
        # Re-anchor interval schedules to the edit so "every N" counts from now.
        automation.anchor_at = datetime.now(dt_timezone.utc)
        automation.next_run_at = _resolve_next_run_at(
            schedule_kind=automation.schedule_kind,
            frequency=automation.frequency,
            timezone_name=automation.timezone,
            run_at=run_at,
            anchor=automation.anchor_at,
        )

    db.commit()
    return automation


def delete_automation(db: Session, user_id: UUID, automation_id: UUID) -> bool:
    automation = get_automation(db, user_id, automation_id)
    if automation is None:
        return False
    db.delete(automation)
    db.commit()
    return True


def list_runs(
    db: Session, user_id: UUID, automation_id: UUID, limit: int = 50
) -> list[AutomationRun]:
    if get_automation(db, user_id, automation_id) is None:
        raise AutomationNotFoundError("Automation not found")
    return (
        db.query(AutomationRun)
        .filter(
            AutomationRun.automation_id == automation_id,
            AutomationRun.user_id == user_id,
        )
        .order_by(AutomationRun.fired_at.desc())
        .limit(limit)
        .all()
    )


def record_run(
    db: Session,
    user_id: UUID,
    automation_id: UUID,
    *,
    status: str,
    agent_instance_id: UUID | None = None,
    detail: str | None = None,
    planned_at: datetime | None = None,
) -> AutomationRun:
    """Record a manual ("run now") dispatch outcome and stamp last-run status.

    The scheduler writes its own runs directly (it lives in the `server` process);
    this path serves the web's client-side spawn, which reports what it observed."""
    if get_automation(db, user_id, automation_id) is None:
        raise AutomationNotFoundError("Automation not found")

    # The spawn RPC returns before the agent self-registers, so the reported
    # instance may not have an agent_instances row yet. Link only if it exists
    # (the FK would otherwise reject the insert); a missing link is fine.
    linked_instance_id = agent_instance_id
    if linked_instance_id is not None:
        exists = (
            db.query(AgentInstance.id)
            .filter(
                AgentInstance.id == linked_instance_id,
                AgentInstance.user_id == user_id,
            )
            .first()
        )
        if exists is None:
            linked_instance_id = None

    now = datetime.now(dt_timezone.utc)
    run = AutomationRun(
        automation_id=automation_id,
        user_id=user_id,
        agent_instance_id=linked_instance_id,
        planned_at=planned_at,
        fired_at=now,
        status=status,
        detail=detail,
    )
    db.add(run)
    db.query(Automation).filter(Automation.id == automation_id).update(
        {"last_run_at": now, "last_run_status": status}
    )
    db.commit()
    return run
