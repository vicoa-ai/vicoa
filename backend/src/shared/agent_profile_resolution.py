"""Resolve an automation's agent-profile reference at dispatch time (collab P1).

Sessions and automations bind to a profile differently, on purpose:

* A **session** snapshots. It is already running, so it can only ever hold the
  config it spawned with; ``agent_instances.agent_profile_id`` is provenance for
  display, never re-read for config.
* An **automation** references. It has *not* launched yet, so when it fires it
  should use the agent as it is *then* — edit the agent, and the next 3am run
  picks the change up.

The reference's one real failure mode is the profile being archived or deleted
between the last edit and the run. ``automations.session_config`` is therefore
kept NOT NULL and always holds the last-resolved config as a **fallback
snapshot**: resolution prefers the live profile and silently degrades to that
snapshot, so a run never fails for lack of a config.

Shared by ``servers/scheduler`` (which dispatches) and ``backend/api`` (which has
to show the user what a referenced automation will actually run with) so the two
can never disagree about what "resolved" means.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from protocol.agent_catalog import normalize_session_config
from shared.database.agent_profile_models import AgentProfile


@dataclass(frozen=True)
class ResolvedAgentConfig:
    """What an automation will actually spawn with."""

    session_config: dict
    system_prompt: str | None
    #: True when the live profile was used; False when we fell back to the
    #: stored snapshot (profile missing or archived). Callers use it to decide
    #: whether the snapshot on the row needs refreshing, and the API uses it to
    #: tell the user their automation has become unlinked in practice.
    from_profile: bool


def resolve_automation_config(
    db: Session,
    *,
    agent_profile_id: UUID | None,
    session_config: dict | None,
) -> ResolvedAgentConfig:
    """Prefer the referenced profile; fall back to the stored snapshot."""
    fallback = dict(session_config or {})
    if agent_profile_id is None:
        return ResolvedAgentConfig(
            session_config=fallback, system_prompt=None, from_profile=False
        )

    profile = db.get(AgentProfile, agent_profile_id)
    if profile is None or profile.is_archived:
        # Deleting a profile already NULLs the FK (ON DELETE SET NULL), so in
        # practice this is the archived case — but a row read mid-delete lands
        # here too, and either way the snapshot keeps the run alive.
        return ResolvedAgentConfig(
            session_config=fallback, system_prompt=None, from_profile=False
        )

    return ResolvedAgentConfig(
        session_config=normalize_session_config(profile.config, profile.agent),
        system_prompt=(profile.system_prompt or None),
        from_profile=True,
    )
