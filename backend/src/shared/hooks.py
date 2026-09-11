"""Extension hooks that let the closed *cloud* overlay add behavior to the open
core without the core importing it.

The overlay (``src/cloud/``) registers callbacks at import time; the open core
fires them. Every registry is empty in the open-source / self-host build (the
overlay is absent), so each ``run_*`` / ``start_*`` call is a no-op there.

See ``plans/todos/oss-cut-manifest.md`` (PART A / A4).
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Protocol
from uuid import UUID

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
CAPABILITY_TEAM_SEAT = "collab.team_seat"
CAPABILITY_GRANT_WRITE = "collab.grant_write"

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
    a billing error would hand out seats for free."""
    for fn in _capability_hooks:
        try:
            reason = fn(db, user_id, capability, context)
        except CapabilityDenied:
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
