"""Process-local liveness registry for the `vicoa-server` process.

Every session process POSTs `/agents/instances/{id}/heartbeat` every 30 s and
every daemon POSTs `/machines/{id}/heartbeat` on the same cadence. Until
2026-09 each tick was two database transactions (an UPDATE plus a NOTIFY) and
a full-row broadcast — O(sessions × time) work that grew with every session
ever left open, and that tipped a 1-vCPU machine into CPU throttling (see
plans/todos/connection-driven-liveness-and-hibernation.md §1).

A tick is now an in-memory *touch*. The `last_heartbeat_at` columns — which
REST readers and older clients still derive liveness from — are renewed by one
batched UPDATE per `LEASE_FLUSH_SECONDS` covering everything touched since the
previous flush: a lease, not a tick. The flush interval is well inside the
90 s online threshold (`settings.liveness_online_threshold_seconds`), so a
reader of the column never sees a live session as stale.

Ownership is verified against the database once per (instance, user) per
process lifetime and cached here, so a steady-state tick never reaches the
database. The flush is still scoped by (id, user_id) pairs, so a cache bug can
never turn into a cross-user write.

Like `ConnectionManager`, this registry is process-local: the server runs as
exactly one process (websocket-migration §2.10), and a restart simply starts
the cache empty — the next tick from each session re-verifies once.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import tuple_, update
from sqlalchemy.orm import Session

from shared.database.models import AgentInstance, Machine
from shared.database.session import SessionLocal

logger = logging.getLogger(__name__)

# How often touched rows get their `last_heartbeat_at` lease renewed in the
# database. Must stay comfortably below `liveness_online_threshold_seconds`
# (90 s): a REST reader sees the column at most this much behind the truth.
LEASE_FLUSH_SECONDS = 15.0

# Rows per UPDATE statement. Each pair is two bind params; keep statements
# small enough that a huge fleet never trips the driver's parameter limit.
_FLUSH_CHUNK = 500


@dataclass(slots=True)
class _Touch:
    user_id: UUID
    seen_at: datetime


class PresenceRegistry:
    """In-memory record of who ticked, keyed by row id.

    Single-threaded by construction: every mutating method is called either
    on a request worker thread or from the flush task, and each is a handful
    of dict operations under the GIL with no interleaving await — the same
    argument `ConnectionManager` makes for its own sync methods.
    """

    def __init__(self) -> None:
        self._instances: dict[UUID, _Touch] = {}
        self._machines: dict[UUID, _Touch] = {}
        self._dirty_instances: set[UUID] = set()
        self._dirty_machines: set[UUID] = set()

    # ----- instances -----

    def instance_is_known(self, instance_id: UUID, user_id: UUID) -> bool:
        """Whether a prior tick already verified `user_id` owns `instance_id`."""
        touch = self._instances.get(instance_id)
        return touch is not None and touch.user_id == user_id

    def touch_instance(
        self, instance_id: UUID, user_id: UUID, *, now: datetime | None = None
    ) -> datetime:
        """Record a tick and return the time it was recorded at."""
        seen_at = now or datetime.now(timezone.utc)
        self._instances[instance_id] = _Touch(user_id=user_id, seen_at=seen_at)
        self._dirty_instances.add(instance_id)
        return seen_at

    def instance_last_seen(self, instance_id: UUID) -> datetime | None:
        touch = self._instances.get(instance_id)
        return touch.seen_at if touch is not None else None

    # ----- machines -----

    def machine_is_known(self, machine_id: UUID, user_id: UUID) -> bool:
        touch = self._machines.get(machine_id)
        return touch is not None and touch.user_id == user_id

    def touch_machine(
        self, machine_id: UUID, user_id: UUID, *, now: datetime | None = None
    ) -> datetime:
        seen_at = now or datetime.now(timezone.utc)
        self._machines[machine_id] = _Touch(user_id=user_id, seen_at=seen_at)
        self._dirty_machines.add(machine_id)
        return seen_at

    def machine_last_seen(self, machine_id: UUID) -> datetime | None:
        touch = self._machines.get(machine_id)
        return touch.seen_at if touch is not None else None

    # ----- lease flush -----

    def drain_dirty(self) -> tuple[list[tuple[UUID, UUID]], list[tuple[UUID, UUID]]]:
        """Take every (id, user_id) touched since the last drain.

        The caller owns the returned pairs; on a failed flush hand them back
        via `requeue` so the next flush retries them.
        """
        instances = [
            (iid, self._instances[iid].user_id)
            for iid in self._dirty_instances
            if iid in self._instances
        ]
        machines = [
            (mid, self._machines[mid].user_id)
            for mid in self._dirty_machines
            if mid in self._machines
        ]
        self._dirty_instances.clear()
        self._dirty_machines.clear()
        return instances, machines

    def requeue(
        self,
        instances: list[tuple[UUID, UUID]],
        machines: list[tuple[UUID, UUID]],
    ) -> None:
        self._dirty_instances.update(iid for iid, _ in instances)
        self._dirty_machines.update(mid for mid, _ in machines)

    def clear(self) -> None:
        """Forget everything. Tests only."""
        self._instances.clear()
        self._machines.clear()
        self._dirty_instances.clear()
        self._dirty_machines.clear()


def flush_leases(
    db: Session,
    registry: PresenceRegistry,
    *,
    now: datetime | None = None,
) -> tuple[int, int]:
    """Renew `last_heartbeat_at` for every row touched since the last flush.

    One UPDATE per chunk, scoped by (id, user_id) pairs. `updated_at` is bumped
    too — that is what today's per-tick write did, and the WS catch-up
    watermark relies on it to re-send live rows after a client reconnects.
    Returns the (instances, machines) row counts. Commits on success; on any
    failure rolls back and requeues the pairs so nothing is lost.
    """
    now = now or datetime.now(timezone.utc)
    instances, machines = registry.drain_dirty()
    if not instances and not machines:
        return 0, 0
    updated_instances = updated_machines = 0
    try:
        for start in range(0, len(instances), _FLUSH_CHUNK):
            chunk = instances[start : start + _FLUSH_CHUNK]
            result = db.execute(
                update(AgentInstance)
                .where(tuple_(AgentInstance.id, AgentInstance.user_id).in_(chunk))
                .values(last_heartbeat_at=now, updated_at=now)
            )
            updated_instances += result.rowcount or 0
        for start in range(0, len(machines), _FLUSH_CHUNK):
            chunk = machines[start : start + _FLUSH_CHUNK]
            result = db.execute(
                update(Machine)
                .where(tuple_(Machine.id, Machine.user_id).in_(chunk))
                .values(last_heartbeat_at=now, updated_at=now)
            )
            updated_machines += result.rowcount or 0
        db.commit()
    except Exception:
        db.rollback()
        registry.requeue(instances, machines)
        raise
    return updated_instances, updated_machines


def _flush_blocking(registry: PresenceRegistry) -> tuple[int, int]:
    with SessionLocal() as db:
        return flush_leases(db, registry)


class LeaseFlusher:
    """Background task: flush the registry every `LEASE_FLUSH_SECONDS`.

    Same start/stop shape as `AutomationScheduler`. The flush runs in a worker
    thread so a slow UPDATE never stalls the event loop, and one failed flush
    is logged and retried on the next tick rather than killing the loop.
    """

    def __init__(
        self, registry: PresenceRegistry, *, interval: float = LEASE_FLUSH_SECONDS
    ) -> None:
        self._registry = registry
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._closed = False

    async def start(self) -> None:
        if self._task is not None:
            return
        self._closed = False
        self._task = asyncio.create_task(self._run())
        logger.info("presence lease flusher started (every %.0fs)", self._interval)

    async def stop(self) -> None:
        self._closed = True
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 — never let shutdown raise
            logger.exception("presence lease flusher shutdown error")
        self._task = None
        # Final flush so a deploy doesn't lose up to one interval of leases —
        # the next process would otherwise see every live row as one flush
        # older than it is.
        try:
            await asyncio.to_thread(_flush_blocking, self._registry)
        except Exception:  # noqa: BLE001 — best effort at shutdown
            logger.exception("presence lease final flush failed")

    async def _run(self) -> None:
        while not self._closed:
            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                raise
            try:
                await asyncio.to_thread(_flush_blocking, self._registry)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — retried next interval
                logger.exception("presence lease flush failed")


# Process-wide singleton, shared by the heartbeat endpoints and the flusher.
presence = PresenceRegistry()
