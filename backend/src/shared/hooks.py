"""Extension hooks that let the closed *cloud* overlay add behavior to the open
core without the core importing it.

The overlay (``src/cloud/``) registers callbacks at import time; the open core
fires them. Every registry is empty in the open-source / self-host build (the
overlay is absent), so each ``run_*`` / ``start_*`` call is a no-op there.

See ``plans/todos/oss-cut-manifest.md`` (PART A / A4).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Awaitable, Callable, Protocol
from uuid import UUID

from sqlalchemy.exc import OperationalError as SAOperationalError

logger = logging.getLogger(__name__)

# --- user creation (welcome email, etc.) --------------------------------------
# The overlay registers on-signup side effects (e.g. the branded welcome email)
# here so the open core's signup path carries no Vicoa email copy.
UserCreatedHook = Callable[[str, str], Awaitable[None]]
_user_created_hooks: list[UserCreatedHook] = []


def register_user_created_hook(fn: UserCreatedHook) -> UserCreatedHook:
    _user_created_hooks.append(fn)
    return fn


async def run_user_created_hooks(to_email: str, user_name: str) -> None:
    """Run overlay on-user-created side effects (best-effort, off the request
    path). No-op in the open build where the overlay is absent. Each hook is
    isolated — one raising is logged and does not stop the others."""
    for fn in _user_created_hooks:
        try:
            await fn(to_email, user_name)
        except Exception:
            logger.exception(
                "on_user_created hook %r failed", getattr(fn, "__name__", fn)
            )


# --- account deletion teardown ------------------------------------------------
# Billing registers Stripe-cancel + billing-row deletes here so that
# ``backend.db.queries.delete_user_account`` (open core) stays billing-agnostic.
UserDeleteHook = Callable[[Any, UUID], None]
_user_delete_hooks: list[UserDeleteHook] = []


def register_user_delete_hook(fn: UserDeleteHook) -> UserDeleteHook:
    _user_delete_hooks.append(fn)
    return fn


def run_user_delete_hooks(db: Any, user_id: UUID) -> None:
    """Run overlay teardown for a user, before the user row is deleted.

    Called inside ``delete_user_account``'s transaction. Exceptions propagate so
    a failed teardown rolls the whole deletion back — matching the pre-carve
    behavior where the billing-row deletes were part of that transaction.
    """
    for fn in _user_delete_hooks:
        fn(db, user_id)


# --- capabilities (seat gating) -----------------------------------------------
# The collaboration mechanics (grants, teams, sharing) all ship in the open
# core; only seat *gating* and seat *billing* live in the overlay
# (collaboration plan §6). The core declares the capabilities it checks and
# asks the registry before the metered action; the overlay registers a hook
# that reads the subscription and answers with a denial reason. An empty
# registry — the open / self-hosted build — allows everything, so self-hosting
# is unmetered exactly like the cloud-absent path everywhere else.
#
# Capabilities the core checks today:
#   collab.team_seat   — adding a member to a team (context: team_id, seats)
#   collab.grant_write — an editor/admin project grant to someone outside the
#                        owner's teams (context: project_id, role, principal_type)
#   collab.team_own    — becoming a team's owner: creating a team, or being
#                        handed one (context: action, team_id). The owner edits
#                        everything the team owns, so a plan may require more
#                        than Free for it.
#
# The seat capabilities carry `seats` (how many people the payer pays for after
# the action), `new_seat` (whether the action adds one) and, so a hook can tell
# *who* rather than just how many, `seat_keys` (everyone after the action) and
# `new_keys` (the ones it adds), as "user:<id>" / "email:<address>" strings.
CAPABILITY_TEAM_SEAT = "collab.team_seat"
CAPABILITY_GRANT_WRITE = "collab.grant_write"
CAPABILITY_TEAM_OWN = "collab.team_own"

# Returns a human-readable denial reason, or None to allow.
CapabilityHook = Callable[[Any, UUID, str, dict[str, Any]], str | None]
_capability_hooks: list[CapabilityHook] = []


class CapabilityDenied(Exception):
    """A registered hook refused ``capability`` for this user.

    The API layer turns it into ``402 Payment Required`` carrying the reason
    and the capability name, so a client can show the upgrade path.
    """

    def __init__(self, capability: str, reason: str) -> None:
        super().__init__(reason)
        self.capability = capability
        self.reason = reason


def register_capability_hook(fn: CapabilityHook) -> CapabilityHook:
    _capability_hooks.append(fn)
    return fn


def check_capability(
    db: Any, user_id: UUID, capability: str, context: dict[str, Any]
) -> None:
    """Raise ``CapabilityDenied`` if any registered hook denies. Empty registry
    ⇒ allow. A hook that *raises* is treated as a denial too — failing open on
    a billing error would hand out seats for free.

    The one exception is a transient database error. Re-raising it still denies
    the action (the request aborts), but it aborts as ``503 + Retry-After`` via
    ``backend.main``'s handler instead of telling a *paying* customer to
    upgrade — a 402 is a statement about their subscription, and a flycast
    blip is not evidence about their subscription.
    """
    for fn in _capability_hooks:
        try:
            reason = fn(db, user_id, capability, context)
        except CapabilityDenied:
            raise
        except SAOperationalError:
            logger.warning(
                "capability hook %r hit a database error for %s; surfacing as 503",
                getattr(fn, "__name__", fn),
                capability,
            )
            raise
        except Exception:
            logger.exception(
                "capability hook %r failed for %s",
                getattr(fn, "__name__", fn),
                capability,
            )
            raise CapabilityDenied(capability, "Capability check failed")
        if reason:
            raise CapabilityDenied(capability, reason)


# --- plan limits (metered resources) ------------------------------------------
# The numeric half of the same seam. `shared.limits` declares WHICH resources
# exist and knows how to COUNT them (they are core tables); the overlay supplies
# only the NUMBERS, because a plan's shape is a pricing decision and pricing is
# not in the open build. An empty registry ⇒ no limits at all, so self-hosting
# is unmetered exactly like `check_capability` above.
#
# Deliberately ONE hook for both enforcement and display: `check_limit` and the
# `GET /limits` endpoint read the same answer through the same call, so the
# paywall a client renders can never disagree with the 402 it will get.
#
# A mapping value of `None` means "unlimited"; a key the hook omits is also
# unlimited. Resource keys are the ones in `shared.limits` (e.g. "machines").
PlanLimitsHook = Callable[[Any, UUID], Mapping[str, int | None]]
_plan_limits_hooks: list[PlanLimitsHook] = []


def register_plan_limits_hook(fn: PlanLimitsHook) -> PlanLimitsHook:
    _plan_limits_hooks.append(fn)
    return fn


def plan_limits(db: Any, user_id: UUID) -> dict[str, int | None]:
    """The user's per-resource caps, merged across hooks. `{}` when none are
    registered (the open / self-hosted build) — which every caller must read as
    *unlimited*, never as *zero*.

    Merge rule when more than one hook answers for the same resource: **the most
    permissive answer wins** (unlimited beats any number; a larger number beats a
    smaller one). A second hook exists to *grant* — a promo, a grandfathered
    account, a comped team — never to restrict; restricting is the base plan's
    job, and one hook is the only shape the overlay actually ships.

    Exceptions propagate. `check_limit` converts them into a denial so an
    enforcement path fails closed; the display endpoint lets them surface as a
    5xx, because rendering "unlimited" off a failed billing read is worse than
    rendering an error.
    """
    merged: dict[str, int | None] = {}
    for fn in _plan_limits_hooks:
        answer = fn(db, user_id)
        if not answer:
            continue
        for key, limit in answer.items():
            if key not in merged:
                merged[key] = limit
                continue
            current = merged[key]
            if current is None or limit is None:
                merged[key] = None  # unlimited wins
            else:
                merged[key] = max(current, limit)
    return merged


# --- FastAPI app setup (extra routers) ----------------------------------------
AppSetupHook = Callable[[Any], None]
_app_setup_hooks: list[AppSetupHook] = []


def register_app_setup(fn: AppSetupHook) -> AppSetupHook:
    _app_setup_hooks.append(fn)
    return fn


def run_app_setup(app: Any) -> None:
    """Let the overlay mount its routers after the core routers are mounted."""
    for fn in _app_setup_hooks:
        fn(app)


# --- lifespan (background tasks) ----------------------------------------------
class LifespanHook(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...


_lifespan_hooks: list[LifespanHook] = []


def register_lifespan_hook(hook: LifespanHook) -> LifespanHook:
    _lifespan_hooks.append(hook)
    return hook


async def start_lifespan_hooks() -> None:
    for hook in _lifespan_hooks:
        await hook.start()


async def stop_lifespan_hooks() -> None:
    for hook in reversed(_lifespan_hooks):
        await hook.stop()
