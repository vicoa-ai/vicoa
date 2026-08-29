"""Derived session liveness.

``agent_instances.status`` is *self-reported* — an agent writes it, and nothing
ever writes it back on the agent's behalf. If a daemon is SIGKILL'd or a laptop
sleeps, nobody runs the exit monitor and the row stays ``ACTIVE`` forever. So
status alone cannot answer "is this session actually reachable right now".

Liveness is therefore *derived* at read time from two independent heartbeats,
never stored:

- ``machines.last_heartbeat_at``      — the daemon, every 30s. Is the laptop up?
- ``agent_instances.last_heartbeat_at`` — the agent process, every 30s. Is the
  agent up?

Deriving rather than storing is deliberate: a persisted ``online`` bool would
rot into stuck ``true`` values exactly the way the current status column has
(see plans/todos/stale-instance-reaper.md).

The two levels are distinct because they imply different remedies — a cold
laptop needs turning on, whereas a stopped agent on a live machine can be
resumed in place.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from shared.config.settings import settings

from .enums import AgentStatus


class LiveState(str, Enum):
    """What the user needs to know about a session, and what they can do."""

    LIVE = "live"
    """Agent is heartbeating. Normal operation."""

    RECONNECTING = "reconnecting"
    """Missed a few beats but within the stale window — likely a blip."""

    AGENT_STOPPED = "agent_stopped"
    """Machine is reachable but the agent is gone. Resumable."""

    MACHINE_OFFLINE = "machine_offline"
    """Host is unreachable; nothing on it can be resumed until it returns."""

    UNKNOWN = "unknown"
    """No machine linkage (legacy TUI rows). Render neutral, never as an error.

    Without this bucket every pre-``machine_id`` session in the backlog would
    render as offline on deploy.
    """


def _age_seconds(ts: Optional[datetime], now: datetime) -> Optional[float]:
    """Seconds since ``ts``. Tolerates naive datetimes stored as UTC."""
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds()


def is_fresh(
    ts: Optional[datetime],
    now: Optional[datetime] = None,
    threshold_seconds: Optional[int] = None,
) -> bool:
    """Whether ``ts`` is recent enough to count as a live heartbeat."""
    now = now or datetime.now(timezone.utc)
    threshold = (
        threshold_seconds
        if threshold_seconds is not None
        else settings.liveness_online_threshold_seconds
    )
    age = _age_seconds(ts, now)
    return age is not None and age < threshold


def machine_is_online(
    machine_last_heartbeat_at: Optional[datetime],
    now: Optional[datetime] = None,
) -> bool:
    """Whether the host daemon has beaten recently enough to accept work."""
    return is_fresh(machine_last_heartbeat_at, now)


def is_starting_up(
    status: AgentStatus,
    instance_last_heartbeat_at: Optional[datetime],
    started_at: Optional[datetime],
    now: datetime,
) -> bool:
    """Whether the session is still coming up and simply hasn't beaten yet.

    Without this, a session is born ``agent_stopped``: the row exists before the
    agent process does, so there is no heartbeat for the first few seconds and
    silence would be misread as death — blocking the composer on a brand-new
    session.

    Only applies while no heartbeat has ever landed. Once a session has beaten
    once, later silence is real and the grace must not resurrect it.

    Bounded by ``started_at`` rather than by the ``STARTING`` status, because a
    spawn that hung leaves the row stuck in ``STARTING`` forever — one of the
    documented zombie shapes. Past the grace window, silence is death no matter
    what the status claims.
    """
    if instance_last_heartbeat_at is not None:
        return False
    age = _age_seconds(started_at, now)
    if age is None:
        # No started_at to judge by — fall back to the explicit status.
        return status == AgentStatus.STARTING
    return age < settings.liveness_startup_grace_seconds


def compute_live_state(
    *,
    status: AgentStatus,
    instance_last_heartbeat_at: Optional[datetime],
    machine_id: Optional[object],
    machine_last_heartbeat_at: Optional[datetime],
    started_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> LiveState:
    """Derive a session's live state.

    Ordering matters:

    1. A session still starting up hasn't had time to heartbeat, so silence is
       expected rather than damning.
    2. A fresh *agent* heartbeat is direct proof the agent is alive, so it wins
       outright — including for rows with no machine linkage, whose liveness we
       would otherwise throw away.
    3. An unreachable host explains the silence and is the more actionable
       message ("turn your laptop on" beats "the agent stopped"), so it is
       checked before we blame the agent — and it also means resume can't work.

    Note this deliberately does NOT special-case terminal statuses. A closed or
    archived session has no agent by design, and the UI already explains itself
    from ``status``. Liveness exists to catch the opposite case — a session that
    still *claims* to be usable while its agent is gone.
    """
    now = now or datetime.now(timezone.utc)
    age = _age_seconds(instance_last_heartbeat_at, now)

    if is_starting_up(status, instance_last_heartbeat_at, started_at, now):
        return LiveState.LIVE

    if age is not None and age < settings.liveness_online_threshold_seconds:
        return LiveState.LIVE

    # Agent isn't beating. Is the host even up to be asked?
    if machine_id is not None and not machine_is_online(machine_last_heartbeat_at, now):
        return LiveState.MACHINE_OFFLINE

    if machine_id is None:
        # Legacy TUI-registered row, still non-terminal: no linkage, so silence
        # is unexplained rather than damning. Neutral, never shown as an error.
        return LiveState.UNKNOWN

    # Host is up but the agent is quiet: a blip, or genuinely gone.
    if age is not None and age < settings.liveness_stale_threshold_seconds:
        return LiveState.RECONNECTING
    return LiveState.AGENT_STOPPED


def is_reachable(live_state: LiveState) -> bool:
    """Whether a message sent right now has a live agent to receive it."""
    return live_state in (LiveState.LIVE, LiveState.RECONNECTING)
