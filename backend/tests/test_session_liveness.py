"""Derived session liveness (shared/database/liveness.py).

Pure unit tests — liveness is computed from timestamps, so no DB is needed.

The case that motivates the whole module is
``test_idle_headless_session_reads_live``: headless wrappers historically never
heartbeated, so an idle session awaiting user input drifted stale and would
have rendered as offline — on exactly the sessions a user is most likely to be
looking at. See plans/todos/session-liveness-and-resume.md.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from shared.config.settings import settings
from shared.database.enums import AgentStatus
from shared.database.liveness import (
    LiveState,
    compute_live_state,
    is_fresh,
    is_reachable,
    machine_is_online,
)

NOW = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
MACHINE = uuid4()


def ago(seconds: float) -> datetime:
    return NOW - timedelta(seconds=seconds)


def state(
    *,
    status: AgentStatus = AgentStatus.ACTIVE,
    instance_hb: datetime | None = None,
    machine_id: object | None = MACHINE,
    machine_hb: datetime | None = None,
    started_at: datetime | None = None,
) -> LiveState:
    return compute_live_state(
        status=status,
        instance_last_heartbeat_at=instance_hb,
        machine_id=machine_id,
        machine_last_heartbeat_at=machine_hb,
        # Default well past the startup grace so cases opt into it explicitly.
        started_at=started_at if started_at is not None else ago(9999),
        now=NOW,
    )


# --------------------------------------------------------------------------
# The core matrix
# --------------------------------------------------------------------------


def test_fresh_agent_and_machine_is_live():
    assert state(instance_hb=ago(10), machine_hb=ago(10)) is LiveState.LIVE


def test_idle_headless_session_reads_live():
    """A session idling below the online threshold must NOT read as offline.

    Regression guard for the false-offline bug: without a headless heartbeat
    this session's timestamp would keep aging until it flipped to stopped,
    while the agent sat there perfectly healthy awaiting input.
    """
    assert (
        state(
            status=AgentStatus.AWAITING_INPUT,
            instance_hb=ago(settings.liveness_online_threshold_seconds - 30),
            machine_hb=ago(10),
        )
        is LiveState.LIVE
    )


def test_briefly_quiet_agent_is_reconnecting_not_dead():
    """Between the two thresholds we say "reconnecting", so a network blip
    doesn't present as a dead session the user needs to act on."""
    assert (
        state(
            instance_hb=ago(settings.liveness_online_threshold_seconds + 30),
            machine_hb=ago(10),
        )
        is LiveState.RECONNECTING
    )


def test_long_silent_agent_on_live_machine_is_stopped():
    assert (
        state(
            instance_hb=ago(settings.liveness_stale_threshold_seconds + 60),
            machine_hb=ago(10),
        )
        is LiveState.AGENT_STOPPED
    )


def test_agent_that_never_beat_is_stopped_not_live():
    """The zombie shape: status says ACTIVE, nothing ever heartbeated."""
    assert state(instance_hb=None, machine_hb=ago(10)) is LiveState.AGENT_STOPPED


# --------------------------------------------------------------------------
# Startup grace — a session exists before its agent process does
# --------------------------------------------------------------------------


def test_just_spawned_session_is_not_reported_stopped():
    """Without the grace a session is born ``agent_stopped``, which would block
    the composer on a brand-new session."""
    assert (
        state(
            status=AgentStatus.STARTING,
            instance_hb=None,
            machine_hb=ago(5),
            started_at=ago(3),
        )
        is LiveState.LIVE
    )


def test_grace_covers_the_window_before_the_first_beat():
    assert (
        state(
            instance_hb=None,
            machine_hb=ago(5),
            started_at=ago(settings.liveness_startup_grace_seconds - 30),
        )
        is LiveState.LIVE
    )


def test_hung_spawn_stuck_in_starting_is_not_excused_forever():
    """Stuck-in-STARTING is a documented zombie shape, so the grace is bounded
    by started_at rather than by the status alone."""
    assert (
        state(
            status=AgentStatus.STARTING,
            instance_hb=None,
            machine_hb=ago(5),
            started_at=ago(settings.liveness_startup_grace_seconds + 60),
        )
        is LiveState.AGENT_STOPPED
    )


def test_grace_does_not_reapply_once_a_session_has_beaten():
    """started_at is recent but a beat already landed and went stale — the
    grace must not resurrect it."""
    assert (
        state(instance_hb=ago(600), machine_hb=ago(5), started_at=ago(5))
        is LiveState.AGENT_STOPPED
    )


def test_says_nothing_about_a_session_closed_on_purpose():
    """A closed/archived session has no agent by design and keeps its own UI
    copy. Liveness exists for the opposite case — a session that still claims
    to be usable while its agent is gone — so it must not speak here."""
    assert (
        state(status=AgentStatus.COMPLETED, instance_hb=None, machine_id=None)
        is LiveState.UNKNOWN
    )


def test_offline_machine_wins_over_agent_silence():
    """A cold laptop explains the silence and is the more actionable message,
    so it must not be reported as a resumable stopped agent."""
    assert (
        state(
            instance_hb=ago(600),
            machine_hb=ago(600),
        )
        is LiveState.MACHINE_OFFLINE
    )


# --------------------------------------------------------------------------
# Legacy rows must never render as errors
# --------------------------------------------------------------------------


def test_legacy_row_without_machine_is_unknown():
    """Pre-machine_id sessions are the bulk of the backlog. They must land in
    `unknown`, or the whole of a user's history turns red on deploy."""
    assert state(instance_hb=None, machine_id=None) is LiveState.UNKNOWN


def test_fresh_agent_heartbeat_beats_missing_machine_linkage():
    """A beating agent is direct proof of life; absent linkage mustn't discard it."""
    assert state(instance_hb=ago(5), machine_id=None) is LiveState.LIVE


# --------------------------------------------------------------------------
# Terminal status interaction
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.KILLED],
)
def test_terminal_status_with_dead_heartbeat_is_stopped(status: AgentStatus):
    assert state(status=status, instance_hb=None, machine_hb=ago(10)) is (
        LiveState.AGENT_STOPPED
    )


def test_archived_but_still_beating_session_is_live():
    """Archiving writes COMPLETED while the agent may still be running. If it's
    still beating, report the truth rather than the label."""
    assert (
        state(status=AgentStatus.COMPLETED, instance_hb=ago(5), machine_hb=ago(5))
        is LiveState.LIVE
    )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def test_is_fresh_handles_naive_datetimes_as_utc():
    """Timestamps come back naive from some drivers; treating them as local
    time would silently shift liveness by the UTC offset."""
    naive = NOW.replace(tzinfo=None) - timedelta(seconds=5)
    assert is_fresh(naive, now=NOW) is True


def test_is_fresh_is_false_for_none():
    assert is_fresh(None, now=NOW) is False


def test_machine_is_online_respects_threshold():
    assert machine_is_online(ago(10), now=NOW) is True
    assert (
        machine_is_online(ago(settings.liveness_online_threshold_seconds + 1), now=NOW)
        is False
    )


@pytest.mark.parametrize(
    "live_state,expected",
    [
        (LiveState.LIVE, True),
        (LiveState.RECONNECTING, True),
        (LiveState.AGENT_STOPPED, False),
        (LiveState.MACHINE_OFFLINE, False),
        (LiveState.UNKNOWN, False),
    ],
)
def test_is_reachable(live_state: LiveState, expected: bool):
    assert is_reachable(live_state) is expected


def test_live_state_compares_equal_to_its_wire_string():
    """It rides on JSON API responses and is matched against string literals in
    the clients, so the enum must be str-valued."""
    assert LiveState.AGENT_STOPPED == "agent_stopped"
    assert LiveState.LIVE == "live"
    assert {s.value for s in LiveState} == {
        "live",
        "reconnecting",
        "agent_stopped",
        "machine_offline",
        "unknown",
    }
