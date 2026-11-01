"""Plan limits — one declaration per metered resource, one place to check it.

The split is the same one `shared.hooks` draws everywhere else: **the open core
counts, the closed overlay prices.** The core declares which resources exist and
how to count them (they are core tables, so only the core *can* count them); the
overlay answers with the numbers for this user's plan, via the single
`hooks.plan_limits` hook. No hook registered — the open-source / self-hosted
build — means every resource is unlimited.

Adding a resource later is two lines and no migration:

    register_resource(LimitedResource(key="projects", ..., count=_count_projects))
    ...
    limits.check_limit(db, user_id, "projects")   # at the creation site

Clients never learn a number from their own source: `GET /limits` reports
`used` / `limit` per resource from *this* module, so changing a plan is a
server-side change and an App Store release is never in the loop.

Enforcement notes
-----------------
* The check is ``used + requested > limit``, which makes the rule **additive
  only**. A user already over a limit (a free account that had three machines
  before the limit existed) keeps everything they have and is refused only the
  *next* one. There is deliberately no retroactive sweep.
* A denial raises `hooks.CapabilityDenied`, which both FastAPI apps already map
  to ``402 {detail, capability}`` (`shared.access_handlers`), so a new resource
  needs no router-level error handling.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError as SAOperationalError
from sqlalchemy.orm import Session

from . import hooks
from .database.automation_models import Automation
from .database.models import Machine

logger = logging.getLogger(__name__)

# Resource keys. Also the keys the overlay's plan mapping uses and the keys
# `GET /limits` reports, so they are a wire contract — rename with a migration
# of the overlay's plan table, not casually.
RESOURCE_MACHINES = "machines"
RESOURCE_AUTOMATIONS = "automations"

# Period vocabulary for `LimitedResource.period`. Everything metered today is
# a standing count; a resource that *resets* would add its own word here, and
# the per-period storage to go with it (there is none in the core right now —
# a count of rows the user owns needs nowhere to keep a tally).
PERIOD_TOTAL = "total"  # a standing count of things that exist right now


def capability_for(key: str) -> str:
    """The capability name a denial of ``key`` carries, e.g. `limit.machines`.

    Namespaced so a client can tell a limit denial from the collaboration seat
    denials (`collab.*`) that share the 402 status.
    """
    return f"limit.{key}"


@dataclass(frozen=True)
class LimitedResource:
    """One metered resource.

    ``count`` returns the user's current usage in the same unit as the limit.
    Everything metered today is a count of rows the user owns, so counting is
    a ``COUNT(*)`` and nothing has to be recorded as it happens.
    """

    key: str
    label: str  # heading case, for a usage list ("Machines")
    noun: str  # singular, for a sentence ("machine") — pluralised at use
    unit: str  # "count" today — presentation only; widen with the resource
    period: str  # PERIOD_TOTAL
    count: Callable[[Session, UUID], int]


_REGISTRY: dict[str, LimitedResource] = {}


def register_resource(resource: LimitedResource) -> LimitedResource:
    """Register (or replace) a metered resource. Idempotent by key so a module
    re-imported under a different name in tests cannot double-register."""
    _REGISTRY[resource.key] = resource
    return resource


def resources() -> Sequence[LimitedResource]:
    """Every registered resource, in registration order."""
    return tuple(_REGISTRY.values())


def get_resource(key: str) -> LimitedResource:
    try:
        return _REGISTRY[key]
    except KeyError:  # pragma: no cover - programming error, not runtime state
        raise KeyError(f"Unknown limited resource {key!r}") from None


@dataclass(frozen=True)
class LimitStatus:
    """What a client needs to render one row of a paywall / usage list."""

    key: str
    label: str
    unit: str
    period: str
    used: int
    limit: int | None  # None = unlimited

    @property
    def unlimited(self) -> bool:
        return self.limit is None

    @property
    def remaining(self) -> int | None:
        if self.limit is None:
            return None
        return max(self.limit - self.used, 0)


# ---------------------------------------------------------------------------
# Counting
# ---------------------------------------------------------------------------


def _count_machines(db: Session, user_id: UUID) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(Machine).where(Machine.user_id == user_id)
        ).scalar_one()
    )


def _count_automations(db: Session, user_id: UUID) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(Automation)
            .where(Automation.user_id == user_id)
        ).scalar_one()
    )


# ---------------------------------------------------------------------------
# Reading the plan + enforcing
# ---------------------------------------------------------------------------


def _limits_for(db: Session, user_id: UUID) -> dict[str, int | None]:
    return hooks.plan_limits(db, user_id)


def _denial_reason(resource: LimitedResource, limit: int) -> str:
    """The sentence a 402 carries. Deliberately states the plan's number and
    the resource, and nothing about *which* plan or what it costs — prices are
    the overlay's business and the open build has none."""
    # Say what is already using the allowance, not just how big it is: a user
    # who reads "your plan includes 1 machine" on their second computer still
    # has to work out that the first one is holding the slot.
    if limit == 1:
        return (
            f"Your plan includes 1 {resource.noun}, and one is already "
            f"connected. Upgrade to add more."
        )
    return (
        f"You're using all {limit} {resource.noun}s your plan includes. "
        f"Upgrade to add more."
    )


def check_limit(db: Session, user_id: UUID, key: str, *, requested: int = 1) -> None:
    """Raise `hooks.CapabilityDenied` if adding ``requested`` would exceed the
    user's cap for ``key``. No registered hook ⇒ unlimited ⇒ returns.

    Fails **closed**: a hook that blows up denies the action, because failing
    open on a billing read hands the resource out for free. The one exception is
    a transient database error, which is re-raised unchanged so `backend.main`
    turns it into ``503 + Retry-After`` — a 402 is a claim about someone's
    subscription, and a dropped connection is no evidence about that.
    """
    if requested <= 0:
        return
    resource = get_resource(key)
    try:
        limits = _limits_for(db, user_id)
    except SAOperationalError:
        logger.warning(
            "plan-limits hook hit a database error for %s; surfacing as 503", key
        )
        raise
    except hooks.CapabilityDenied:
        raise
    except Exception:
        logger.exception("plan-limits hook failed for %s", key)
        raise hooks.CapabilityDenied(
            capability_for(key), "Could not verify your plan. Please try again."
        )

    limit = limits.get(key)
    if limit is None:
        return
    used = resource.count(db, user_id)
    if used + requested > limit:
        raise hooks.CapabilityDenied(
            capability_for(key), _denial_reason(resource, limit)
        )


def _status(
    db: Session, user_id: UUID, resource: LimitedResource, limits: dict[str, int | None]
) -> LimitStatus:
    return LimitStatus(
        key=resource.key,
        label=resource.label,
        unit=resource.unit,
        period=resource.period,
        used=resource.count(db, user_id),
        limit=limits.get(resource.key),
    )


def describe_limit(db: Session, user_id: UUID, key: str) -> LimitStatus:
    """One resource's usage + cap. Used where a caller has just touched a single
    meter and wants it back — counting every other resource to answer that would
    be a needless COUNT(*) per table on a hot path."""
    return _status(db, user_id, get_resource(key), _limits_for(db, user_id))


def describe_limits(db: Session, user_id: UUID) -> list[LimitStatus]:
    """Usage + cap for every registered resource — what `GET /limits` returns.

    Reads the caps through the same `hooks.plan_limits` call `check_limit` uses,
    so what a client shows and what it will actually be allowed to do are the
    same answer. Exceptions propagate (see `hooks.plan_limits`).
    """
    limits = _limits_for(db, user_id)
    return [_status(db, user_id, resource, limits) for resource in resources()]


# ---------------------------------------------------------------------------
# The resources the core meters today
# ---------------------------------------------------------------------------

register_resource(
    LimitedResource(
        key=RESOURCE_MACHINES,
        label="Machines",
        noun="machine",
        unit="count",
        period=PERIOD_TOTAL,
        count=_count_machines,
    )
)

register_resource(
    LimitedResource(
        key=RESOURCE_AUTOMATIONS,
        label="Automations",
        noun="automation",
        unit="count",
        period=PERIOD_TOTAL,
        count=_count_automations,
    )
)
