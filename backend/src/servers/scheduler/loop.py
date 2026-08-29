"""The automation sweep loop.

A plain asyncio timer (Postgres has no wall-clock trigger and "run at 9am" is a
future time, not a row change). Every SWEEP_INTERVAL it claims due rows, advances
each row's `next_run_at` inside the claim transaction (v1's dedup guarantee), then
dispatches outside the lock and records a history row.
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from shared.config import settings
from shared.database import Automation, AgentInstance, AutomationRun
from shared.database.session import SessionLocal
from shared.scheduling import compute_next_run

from .dispatch import DispatchResult, dispatch_automation

logger = logging.getLogger(__name__)

SWEEP_INTERVAL = 30.0  # seconds; ±interval granularity is fine for daily/weekly
CLAIM_LIMIT = 50
# How long to wait for the spawned agent to self-register before recording the
# run, so `agent_instance_id` links to a real row. The spawn RPC returns as soon
# as the daemon Popen's the process, before the agent registers.
INSTANCE_LINK_WAIT = 8.0
INSTANCE_LINK_POLL = 0.5


def _claim_due_blocking() -> list[dict]:
    """Claim due rows and advance their next fire time in one short transaction.

    Uses `FOR UPDATE SKIP LOCKED` so this is safe even if two sweeps overlap, and
    advances `next_run_at` before commit so a row can't be double-claimed. Returns
    plain dicts (ORM rows expire after commit)."""
    now = datetime.now(timezone.utc)
    claimed: list[dict] = []
    with SessionLocal() as db:
        rows = (
            db.query(Automation)
            .filter(
                Automation.enabled.is_(True),
                Automation.next_run_at.isnot(None),
                Automation.next_run_at <= now,
            )
            .order_by(Automation.next_run_at.asc())
            .with_for_update(skip_locked=True)
            .limit(CLAIM_LIMIT)
            .all()
        )
        for row in rows:
            claimed.append(
                {
                    "id": row.id,
                    "user_id": row.user_id,
                    "machine_id": row.machine_id,
                    "directory": row.directory,
                    "worktree": dict(row.worktree) if row.worktree else None,
                    "session_config": dict(row.session_config or {}),
                    "prompt": row.prompt,
                    "planned_at": row.next_run_at,
                }
            )
            if row.schedule_kind == "recurring":
                row.next_run_at = compute_next_run(
                    row.frequency,
                    tz_name=row.timezone,
                    after=now,
                    anchor=row.anchor_at,
                )
                # A frequency that no longer yields a future time disables the row
                # rather than spinning.
                if row.next_run_at is None:
                    row.enabled = False
            else:  # one-time — fire once, then disable
                row.enabled = False
                row.next_run_at = None
        db.commit()
    return claimed


def _instance_exists_blocking(instance_id: UUID) -> bool:
    with SessionLocal() as db:
        return (
            db.query(AgentInstance.id).filter(AgentInstance.id == instance_id).first()
            is not None
        )


def _record_run_blocking(
    row: dict, result: DispatchResult, linked_instance_id: UUID | None
) -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        run = AutomationRun(
            automation_id=row["id"],
            user_id=row["user_id"],
            agent_instance_id=linked_instance_id,
            planned_at=row["planned_at"],
            fired_at=now,
            status=result.status,
            detail=result.detail,
        )
        db.add(run)
        db.query(Automation).filter(Automation.id == row["id"]).update(
            {"last_run_at": now, "last_run_status": result.status}
        )
        db.commit()


class AutomationScheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._closed = False

    async def start(self) -> None:
        # rpc_router (the daemon registry) is process-local to the WebSocket-
        # enabled `server` app; a sweep anywhere else can never reach a daemon.
        if not settings.enable_websocket:
            logger.info("automation scheduler disabled (enable_websocket=false)")
            return
        if self._task is not None:
            return
        self._closed = False
        self._task = asyncio.create_task(self._run())
        logger.info("automation scheduler started (sweep=%.0fs)", SWEEP_INTERVAL)

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
            logger.exception("automation scheduler shutdown error")
        self._task = None

    async def _run(self) -> None:
        while not self._closed:
            try:
                claimed = await asyncio.to_thread(_claim_due_blocking)
                if claimed:
                    logger.info("automation sweep: dispatching %d run(s)", len(claimed))
                    await asyncio.gather(
                        *(self._process_row(row) for row in claimed),
                        return_exceptions=True,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — one bad sweep must not kill the loop
                logger.exception("automation scheduler sweep failed")
            try:
                await asyncio.sleep(SWEEP_INTERVAL)
            except asyncio.CancelledError:
                raise

    async def _process_row(self, row: dict) -> None:
        result = await dispatch_automation(
            user_id=row["user_id"],
            machine_id=row["machine_id"],
            directory=row["directory"],
            worktree=row["worktree"],
            session_config=row["session_config"],
            prompt=row["prompt"],
        )
        linked = None
        if result.status == "fired" and result.agent_instance_id:
            linked = await self._await_instance(result.agent_instance_id)
        await asyncio.to_thread(_record_run_blocking, row, result, linked)

    async def _await_instance(self, instance_id: str) -> UUID | None:
        """Wait (bounded) for the spawned agent to self-register so the run row
        can link to it. Returns the id if the row appears, else None."""
        try:
            inst = UUID(instance_id)
        except (ValueError, TypeError):
            return None
        waited = 0.0
        while waited < INSTANCE_LINK_WAIT:
            if await asyncio.to_thread(_instance_exists_blocking, inst):
                return inst
            await asyncio.sleep(INSTANCE_LINK_POLL)
            waited += INSTANCE_LINK_POLL
        return None
