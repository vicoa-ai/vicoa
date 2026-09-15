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

The socket is the primary signal (§4.1 of the plan). Every agent process holds
a session-scoped WebSocket and every daemon a machine-scoped one, and the
server pings each every 30 s — so `ConnectionManager` already knows who is
alive. This registry reads that: a connected id is leased every flush without
any tick, its effective heartbeat is "now", and its `live_state` is computed
here from the socket rather than from a timestamp. A disconnect is recorded
as a last-seen touch so the timestamp-derived state (what REST readers and
older clients still compute) decays from that moment exactly as it did when
the ticks stopped.

Clients whose socket is present are told to tick far less often
(`next_interval_seconds` in the heartbeat response); ones the server can't
see keep the 30 s cadence as the fallback signal. Dashboards still receive a
periodic full-row refresh per live session (`REFRESH_EVERY_N_FLUSHES`) — the
same frame the tick used to produce — so nothing on the client side has to
change for the ticks to go away.

Like `ConnectionManager`, this registry is process-local: the server runs as
exactly one process (websocket-migration §2.10), and a restart simply starts
the cache empty — sockets reconnect within seconds and the next tick from
each session re-verifies ownership once.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import tuple_, update
from sqlalchemy.orm import Session

from shared.config import settings
from shared.database.liveness import LiveState, compute_live_state, is_fresh
from shared.database.models import AgentInstance, Machine
from shared.database.session import SessionLocal
from shared.websocket.connection_manager import Connection, connection_manager
from shared.websocket.envelope import build_instance_update, build_machine_update

logger = logging.getLogger(__name__)

# How often touched and connected rows get their `last_heartbeat_at` lease
# renewed in the database. Must stay comfortably below
# `liveness_online_threshold_seconds` (90 s): a REST reader sees the column at
# most this much behind the truth.
LEASE_FLUSH_SECONDS = 15.0
# Dashboards get a full-row refresh of every live session/machine every this
# many flushes (30 s at the default — the cadence the client ticks used to
# produce), so a client that derives liveness from the timestamps keeps
# seeing them advance after the ticks stop.
REFRESH_EVERY_N_FLUSHES = 2
# What the heartbeat endpoints tell a client whose socket the server can see:
# tick this rarely. Kept under `liveness_stale_threshold_seconds` (300 s) so a
# client whose socket is blocked but whose REST works can never read as
# `agent_stopped` between two of its own ticks.
CONNECTED_TICK_INTERVAL_SECONDS = 120
# ...and one it can't see: the pre-existing cadence.
DEFAULT_TICK_INTERVAL_SECONDS = 30

# Rows per UPDATE statement. Each pair is two bind params; keep statements
# small enough that a huge fleet never trips the driver's parameter limit.
_FLUSH_CHUNK = 500


@dataclass(slots=True)
class _Touch:
    user_id: UUID
    seen_at: datetime


def _ts(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _latest(*values: datetime | None) -> datetime | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return max(present, key=_ts)


def _connected_pairs(index: dict[str, str]) -> list[tuple[UUID, UUID]]:
    pairs: list[tuple[UUID, UUID]] = []
    for raw_id, raw_user in index.items():
        try:
            pairs.append((UUID(raw_id), UUID(raw_user)))
        except ValueError:
            continue
    return pairs


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

    # ----- sockets -----

    def note_connected(self, conn: Connection) -> None:
        """A session/machine socket arrived: it is alive as of now."""
        now = datetime.now(timezone.utc)
        if conn.scope == "session-scoped" and conn.instance_id:
            self.touch_instance(UUID(conn.instance_id), UUID(conn.user_id), now=now)
        elif conn.scope == "machine-scoped" and conn.machine_id:
            self.touch_machine(UUID(conn.machine_id), UUID(conn.user_id), now=now)

    def note_disconnected(self, conn: Connection) -> None:
        """A socket left: last seen now, so the timestamp-derived state decays
        from this moment (through `reconnecting` to `agent_stopped`) exactly
        as it did when a client's ticks stopped."""
        self.note_connected(conn)

    def effective_instance_heartbeat(
        self, instance_id: UUID, stored: datetime | None
    ) -> datetime | None:
        """The freshest proof of life for an instance: the socket, a tick, or
        the column — whichever is most recent."""
        if connection_manager.is_session_connected(str(instance_id)):
            return datetime.now(timezone.utc)
        return _latest(stored, self.instance_last_seen(instance_id))

    def effective_machine_heartbeat(
        self, machine_id: UUID, stored: datetime | None
    ) -> datetime | None:
        if connection_manager.is_machine_connected(str(machine_id)):
            return datetime.now(timezone.utc)
        return _latest(stored, self.machine_last_seen(machine_id))

    def live_state_for(
        self, instance: AgentInstance, machine_heartbeat_at: datetime | None
    ) -> LiveState:
        """Server-computed `live_state`, with the sockets as the first input."""
        return compute_live_state(
            status=instance.status,
            instance_last_heartbeat_at=self.effective_instance_heartbeat(
                instance.id, instance.last_heartbeat_at
            ),
            machine_id=instance.machine_id,
            machine_last_heartbeat_at=(
                self.effective_machine_heartbeat(
                    instance.machine_id, machine_heartbeat_at
                )
                if instance.machine_id is not None
                else None
            ),
            started_at=instance.started_at,
        )

    def tick_interval_for_instance(self, instance_id: UUID) -> int:
        """What to tell a ticking client: rarely if its socket is visible."""
        if connection_manager.is_session_connected(str(instance_id)):
            return CONNECTED_TICK_INTERVAL_SECONDS
        return DEFAULT_TICK_INTERVAL_SECONDS

    def tick_interval_for_machine(self, machine_id: UUID) -> int:
        if connection_manager.is_machine_connected(str(machine_id)):
            return CONNECTED_TICK_INTERVAL_SECONDS
        return DEFAULT_TICK_INTERVAL_SECONDS

    def recently_seen_instances(self, user_id: UUID, *, within: float) -> set[UUID]:
        """Instances of `user_id` touched (or seen on a socket) within `within` s."""
        cutoff = datetime.now(timezone.utc).timestamp() - within
        return {
            iid
            for iid, touch in self._instances.items()
            if touch.user_id == user_id and _ts(touch.seen_at) >= cutoff
        }

    def recently_seen_machines(self, user_id: UUID, *, within: float) -> set[UUID]:
        cutoff = datetime.now(timezone.utc).timestamp() - within
        return {
            mid
            for mid, touch in self._machines.items()
            if touch.user_id == user_id and _ts(touch.seen_at) >= cutoff
        }

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
    # Every socket present is a live row, tick or no tick.
    seen_i = {iid for iid, _ in instances}
    instances += [
        pair
        for pair in _connected_pairs(connection_manager.connected_sessions())
        if pair[0] not in seen_i
    ]
    seen_m = {mid for mid, _ in machines}
    machines += [
        pair
        for pair in _connected_pairs(connection_manager.connected_machines())
        if pair[0] not in seen_m
    ]
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


def _user_room(user_id: UUID) -> list[str]:
    return [f"user:{user_id}:user-scoped"]


def refresh_dashboards(db: Session, registry: PresenceRegistry) -> int:
    """Push a fresh full-row frame for every live session and machine to each
    user who has a dashboard connected.

    This is the frame the client tick used to produce on every beat, now
    produced here from the sockets and the tick cache instead — so a client
    that derives liveness from `last_heartbeat_at` keeps seeing it advance,
    and a newer client gets `live_state` computed from the socket. One SELECT
    per table per user with a dashboard; nobody watching, nothing built.
    Returns the number of frames enqueued.
    """
    within = float(settings.liveness_online_threshold_seconds)
    frames = 0
    for raw_user in connection_manager.users_with_dashboards():
        try:
            user_id = UUID(raw_user)
        except ValueError:
            continue
        connected_i = {
            UUID(iid)
            for iid, uid in connection_manager.connected_sessions().items()
            if uid == raw_user
        }
        instance_ids = connected_i | registry.recently_seen_instances(
            user_id, within=within
        )
        connected_m = {
            UUID(mid)
            for mid, uid in connection_manager.connected_machines().items()
            if uid == raw_user
        }
        machine_ids = connected_m | registry.recently_seen_machines(
            user_id, within=within
        )

        machine_heartbeats: dict[UUID, datetime | None] = {}
        if machine_ids:
            machines = (
                db.query(Machine)
                .filter(Machine.user_id == user_id, Machine.id.in_(machine_ids))
                .all()
            )
            for machine in machines:
                db.expunge(machine)
                machine.last_heartbeat_at = registry.effective_machine_heartbeat(
                    machine.id, machine.last_heartbeat_at
                )
                machine_heartbeats[machine.id] = machine.last_heartbeat_at
                connection_manager.broadcast_update(
                    raw_user, build_machine_update(machine), _user_room(user_id)
                )
                frames += 1

        if instance_ids:
            instances = (
                db.query(AgentInstance)
                .filter(
                    AgentInstance.user_id == user_id,
                    AgentInstance.id.in_(instance_ids),
                )
                .all()
            )
            for inst in instances:
                db.expunge(inst)
                machine_hb = (
                    machine_heartbeats.get(inst.machine_id)
                    if inst.machine_id is not None
                    else None
                )
                state = registry.live_state_for(inst, machine_hb)
                inst.last_heartbeat_at = registry.effective_instance_heartbeat(
                    inst.id, inst.last_heartbeat_at
                )
                connection_manager.broadcast_update(
                    raw_user,
                    build_instance_update(inst, live_state=state.value),
                    _user_room(user_id),
                )
                frames += 1
    return frames


def _refresh_blocking(registry: PresenceRegistry) -> int:
    with SessionLocal() as db:
        return refresh_dashboards(db, registry)


def broadcast_session_connected(conn: Connection) -> None:
    """Blocking: on a session socket's arrival, show the row as live at once.

    Only when the owner has a dashboard connected — otherwise there is nobody
    to tell, and the next refresh sweep covers a dashboard that opens later —
    and only when the row was NOT already reading as live: a socket that
    reconnects inside the online window (a blip, or every socket at once
    after a deploy) changes nothing the dashboard can see, and after a deploy
    that is a herd of reads and frames for no visible change.
    """
    if conn.scope != "session-scoped" or not conn.instance_id:
        return
    if not connection_manager.has_user_scoped(conn.user_id):
        return
    try:
        instance_id, user_id = UUID(conn.instance_id), UUID(conn.user_id)
    except ValueError:
        return
    try:
        with SessionLocal() as db:
            inst = (
                db.query(AgentInstance)
                .filter(
                    AgentInstance.id == instance_id, AgentInstance.user_id == user_id
                )
                .first()
            )
            if inst is None or is_fresh(inst.last_heartbeat_at):
                return
            db.expunge(inst)
            machine_hb: datetime | None = None
            if inst.machine_id is not None:
                row = (
                    db.query(Machine.last_heartbeat_at)
                    .filter(Machine.id == inst.machine_id, Machine.user_id == user_id)
                    .first()
                )
                machine_hb = row[0] if row is not None else None
            state = presence.live_state_for(inst, machine_hb)
            inst.last_heartbeat_at = presence.effective_instance_heartbeat(
                inst.id, inst.last_heartbeat_at
            )
        connection_manager.broadcast_update(
            conn.user_id,
            build_instance_update(inst, live_state=state.value),
            _user_room(user_id),
        )
    except Exception:  # noqa: BLE001 — a missed frame is the next sweep's problem
        logger.exception("broadcast_session_connected failed for %s", conn.instance_id)


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
        flushes = 0
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
            flushes += 1
            if flushes % REFRESH_EVERY_N_FLUSHES:
                continue
            try:
                await asyncio.to_thread(_refresh_blocking, self._registry)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — retried next round
                logger.exception("presence dashboard refresh failed")


# Process-wide singleton, shared by the heartbeat endpoints and the flusher.
presence = PresenceRegistry()
