"""Who is acting — the attribution channel for generated task activity.

`task_activity` rows are written by a flush listener, not by call sites (§3.5),
and a flush listener has no request context: it can see *that* a task's status
changed but not *who* changed it. The actor therefore has to be handed to the
Session, and the Session is the right carrier because it is exactly the scope
the listener runs in — one request, one unit of work, one actor.

It is stamped in **one place per process** rather than per endpoint:
`backend.auth.dependencies.get_current_user` and `servers.api.auth`'s
`get_current_user_id` both already run for every authenticated request and both
already hold the session, so every route gets attribution with no per-route
work. A request that never authenticates (health checks, the public router)
leaves it unset, and the listener writes `actor_type = NULL` — an unattributed
line, which is honest, rather than a guess.

Per-mutation overrides exist for the one case the request actor gets wrong: the
instance-status sync runs inside a request authenticated *as the user* but the
thing that actually moved the task is the agent's session. See
`register_activity_override`.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

_SESSION_ACTOR_KEY = "vicoa_actor"
_OVERRIDE_KEY = "vicoa_activity_actor_overrides"


@dataclass(frozen=True)
class Actor:
    """A principal, as `task_activity` records it."""

    type: str  # 'user' | 'agent' | 'system'
    id: UUID | None = None
    # Set when the action came from an agent session. Carried into
    # `task_activity.details` so the task timeline can fold a session's status
    # churn into that session's card instead of listing every hop separately.
    agent_instance_id: UUID | None = None


def set_session_actor(db: Session, actor: Actor | None) -> None:
    """Attribute everything this session flushes to `actor`."""
    if actor is None:
        db.info.pop(_SESSION_ACTOR_KEY, None)
        return
    db.info[_SESSION_ACTOR_KEY] = actor


def session_actor(db: Session) -> Actor | None:
    return db.info.get(_SESSION_ACTOR_KEY)


def register_activity_override(db: Session, task_id: UUID, actor: Actor) -> None:
    """Attribute this session's *next* activity on `task_id` to `actor`.

    Consumed by the activity listener and cleared as it goes, so an override
    never leaks onto a later, unrelated change to the same task.
    """
    db.info.setdefault(_OVERRIDE_KEY, {})[task_id] = actor


def take_activity_override(db: Session, task_id: UUID) -> Actor | None:
    overrides = db.info.get(_OVERRIDE_KEY)
    if not overrides:
        return None
    return overrides.pop(task_id, None)
