"""DB queries for scheduled automations (automation-scheduled-tasks plan §v1).

All queries are user-scoped. `next_run_at` is computed here (not in the router)
from the schedule fields so create/update and the server-side scheduler agree on
one clock. History rows (`automation_runs`) are written by `record_run` — from the
manual "run now" path — and by the server scheduler directly.

Everything that writes, and `list_automations` / `get_automation`, is the
author's alone — the servers router (CLI, agent tools) reuses exactly those.
The dashboard additionally *reads* collaborators' automations through the
project their folder files them under (`list_project_automations`,
`get_visible_automation`; collaboration §10.6), and a project share link
carrying `automations` reads them all (`automations_filed_in`).
"""

# `timezone` is aliased because create/update take a `timezone: str` parameter
# that would otherwise shadow datetime.timezone.
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from uuid import UUID

from sqlalchemy import Select, exists, select
from sqlalchemy.orm import Session

from shared import access
from shared.access import Role
from shared.agent_profile_resolution import usable_profile_filter
from shared.database import AgentInstance, Automation, AutomationRun, Machine
from shared.database.agent_profile_models import AgentProfile
from shared.database.project_matching import resolve_automation_project_ids
from shared.database.task_models import Project, ProjectDirectory
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


class AgentProfileNotFoundError(Exception):
    """The referenced agent isn't one the automation's owner may run."""


def _require_usable_profile(db: Session, user_id: UUID, profile_id: UUID) -> None:
    """An automation may only reference an agent its owner can run — their
    own, or one of their teams' (§3.6). The dispatcher re-checks at every run
    (a membership can end); this is the up-front refusal."""
    found = db.execute(
        select(AgentProfile.id).where(
            AgentProfile.id == profile_id, usable_profile_filter(user_id)
        )
    ).first()
    if found is None:
        raise AgentProfileNotFoundError("Agent not found")


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


@dataclass(frozen=True)
class VisibleAutomation:
    """An automation and the caller's standing on it. `project_id` is the
    project it is filed under when the lookup already knows it (None = not
    resolved yet, or filed nowhere); the router resolves the rest in one batch."""

    automation: Automation
    role: Role
    project_id: UUID | None = None


def _filed_in(
    db: Session, project_ids: Select[tuple[UUID]] | list[UUID]
) -> list[tuple[Automation, UUID]]:
    """Every automation filed under one of `project_ids`, whoever wrote it,
    newest first, with the project it is filed under. Candidates are narrowed
    in SQL to authors with a folder linked to one of the projects on the
    automation's machine; the exact folder → project answer (a deeper link may
    claim it for another project) is `resolve_automation_project_ids`."""
    wanted = (
        set(project_ids)
        if isinstance(project_ids, list)
        else {row[0] for row in db.execute(project_ids).all()}
    )
    if not wanted:
        return []
    candidates = (
        db.query(Automation)
        .filter(
            exists().where(
                ProjectDirectory.user_id == Automation.user_id,
                ProjectDirectory.machine_id == Automation.machine_id,
                ProjectDirectory.project_id.in_(wanted),
            )
        )
        .order_by(Automation.created_at.desc())
        .all()
    )
    resolved = resolve_automation_project_ids(db, candidates)
    return [
        (a, project_id)
        for a in candidates
        if (project_id := resolved.get(a.id)) is not None and project_id in wanted
    ]


def list_project_automations(
    db: Session, user_id: UUID, project_id: UUID
) -> list[VisibleAutomation]:
    """The automations filed in one project that `user_id` can see: their own,
    and — when their standing covers the project's `automations` scope —
    everyone else's, read-only (`access.foreign_automation_role`). A project
    the caller cannot see yields only their own rows, which is none: their
    automations cannot be filed under a project they lost."""
    foreign_role = access.foreign_automation_role(
        access.project_access(db, user_id, project_id)
    )
    out: list[VisibleAutomation] = []
    for automation, pid in _filed_in(db, [project_id]):
        if automation.user_id == user_id:
            out.append(VisibleAutomation(automation, "owner", pid))
        elif foreign_role is not None:
            out.append(VisibleAutomation(automation, foreign_role, pid))
    return out


def list_visible_automations(db: Session, user_id: UUID) -> list[VisibleAutomation]:
    """Everything `user_id` can see: all their own automations (filed anywhere
    or nowhere), then collaborators' ones in every project whose standing
    covers its `automations` scope, read-only. The dashboard groups them by
    project."""
    own = [VisibleAutomation(a, "owner") for a in list_automations(db, user_id)]
    projects = access.visible_project_select(
        user_id, scope="all", grant_scope="automations"
    )
    foreign = [(a, pid) for a, pid in _filed_in(db, projects) if a.user_id != user_id]
    if not foreign:
        return own
    standings = access.project_accesses(
        db,
        user_id,
        db.query(Project).filter(Project.id.in_({pid for _, pid in foreign})).all(),
    )
    for automation, pid in foreign:
        role = access.foreign_automation_role(standings.get(pid))
        if role is not None:
            own.append(VisibleAutomation(automation, role, pid))
    return own


def automations_filed_in(db: Session, project_id: UUID) -> list[Automation]:
    """Every automation filed in the project, for a share link that carries
    them. The caller (the link) has already been resolved; no user lens."""
    return [automation for automation, _ in _filed_in(db, [project_id])]


def get_visible_automation(
    db: Session, user_id: UUID, automation_id: UUID
) -> VisibleAutomation | None:
    """The automation with the caller's standing on it, or None when it is
    invisible to them (which the router answers with the same 404 as a missing
    id). The author is `owner`; anyone else resolves through the project the
    automation's folder files it under."""
    automation = db.get(Automation, automation_id)
    if automation is None:
        return None
    if automation.user_id == user_id:
        return VisibleAutomation(automation, "owner")
    project_id = resolve_automation_project_ids(db, [automation]).get(automation.id)
    if project_id is None:
        return None
    role = access.foreign_automation_role(
        access.project_access(db, user_id, project_id)
    )
    if role is None:
        return None
    return VisibleAutomation(automation, role, project_id)


def automation_for_instance(db: Session, instance_id: UUID) -> Automation | None:
    """The automation whose run started this session, if one did. Runs link
    their session only once it has registered (see `record_run`), so a run
    that fired but never linked leaves its session looking hand-started."""
    return (
        db.query(Automation)
        .join(AutomationRun, AutomationRun.automation_id == Automation.id)
        .filter(
            AutomationRun.agent_instance_id == instance_id,
            # A run is its author's, and so is the session it started.
            AutomationRun.user_id == Automation.user_id,
        )
        .order_by(AutomationRun.fired_at.asc())
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
    agent_profile_id: UUID | None = None,
    schedule_kind: str,
    frequency: dict | None = None,
    timezone: str = "UTC",
    run_at: datetime | None = None,
    enabled: bool = True,
) -> Automation:
    if _get_machine(db, user_id, machine_id) is None:
        raise MachineNotFoundError("Machine not found")
    if agent_profile_id is not None:
        _require_usable_profile(db, user_id, agent_profile_id)

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
        agent_profile_id=agent_profile_id,
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
    if fields.get("agent_profile_id") is not None:
        _require_usable_profile(db, user_id, fields["agent_profile_id"])

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
        "agent_profile_id",
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
