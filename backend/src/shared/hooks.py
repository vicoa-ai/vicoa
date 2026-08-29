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
