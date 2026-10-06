"""Record which agent profile a freshly spawned session was started from.

Two paths spawn a session from a profile — the web's ``spawn-session`` RPC
(``servers/api/ws_handler.py``) and the automation sweep
(``servers/scheduler/loop.py``) — and both hit the same race: the daemon mints
the instance id locally and returns it as soon as the agent process is
*launched*, but the row only appears once that agent boots and registers. So the
stamp is a bounded retry that runs detached from the spawn, and it lives here so
the two callers share one schedule rather than drifting apart.
"""

import asyncio
import logging

from servers.shared.db.queries import stamp_instance_agent_profile

logger = logging.getLogger(__name__)

# How long to wait for a spawned session to register before giving up on its
# provenance. A constant rather than a literal in the loop so a test can shorten
# it, and so the budget is visible in one place: anything here shorter than a
# cold agent start silently drops the stamp — and a dropped stamp looks to the
# user exactly like the session never ran.
STAMP_DELAYS: tuple[float, ...] = (0.5, 1.0, 2.0, 4.0, 8.0)

# Detached tasks are referenced only weakly by the event loop, so one that waits
# this long can be collected mid-flight. Same guard the local server keeps over
# its RPC tasks.
_tasks: set[asyncio.Task] = set()


async def stamp_agent_profile_when_registered(
    user_id: str, instance_id: str, agent_profile_id: str
) -> None:
    """Record the session's originating agent profile once its row exists.

    A failure is silent for the spawn — this is display-only provenance and must
    never break a launch — but it is not harmless: the stamp is what the Agents
    page reads as "Run history" and what signs the session's task comments as the
    agent, so giving up early looks to the user exactly like the agent never ran.
    See `STAMP_DELAYS`.
    """
    for delay in STAMP_DELAYS:
        try:
            if await asyncio.to_thread(
                stamp_instance_agent_profile, user_id, instance_id, agent_profile_id
            ):
                return
        except Exception:  # noqa: BLE001 — provenance must never break a spawn
            logger.exception("failed to stamp agent_profile_id on %s", instance_id)
            return
        await asyncio.sleep(delay)
    logger.warning(
        "instance %s never registered within %.0fs; agent profile provenance "
        "not recorded (its Run history will not show this session)",
        instance_id,
        sum(STAMP_DELAYS),
    )


def stamp_agent_profile_in_background(
    user_id: str, instance_id: str, agent_profile_id: str
) -> None:
    """Fire `stamp_agent_profile_when_registered` without awaiting it, holding
    the task in `_tasks` until it finishes."""
    task = asyncio.create_task(
        stamp_agent_profile_when_registered(user_id, instance_id, agent_profile_id)
    )
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
