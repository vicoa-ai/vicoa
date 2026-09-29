"""Grant-gated watching of shared sessions over `/ws` (collaboration §9).

Originally the relay was owner-only end to end: every room was `user:{owner}:*`
and every catch-up filtered `user_id ==`. A session shared with someone now
reaches them through a watcher room, `instance:{id}:watchers`, which a
user-scoped connection joins with a `watch_instance` frame — never at hello,
and never without the grant check here. The check is the one resolver
(`shared.access.instance_role`), so what the relay lets through is exactly what
the dashboard REST lets through.

Access is cached per connection for `ACCESS_TTL_SECONDS`, which bounds how
long a revocation the relay was not told about can keep working. Revocations
it *is* told about — the backend posts `/_internal/revalidate_watchers` after a
grant or share is removed — evict at once, and the periodic sweep
(`revalidate_watchers` from the presence flusher) catches every other path
access can end by: a team membership removed, a session moved out of a shared
project, a session deleted.

Owners never join a watcher room. Their own rooms already carry the session in
full; a watcher-room copy is the narrowed grantee view and would overwrite it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from uuid import UUID

from sqlalchemy.orm import Session

from shared import access
from shared.database.models import AgentInstance
from shared.database.session import SessionLocal
from shared.websocket.connection_manager import Connection, connection_manager

logger = logging.getLogger(__name__)

ACCESS_TTL_SECONDS = 30.0


def _uuid(raw: object) -> UUID | None:
    try:
        return UUID(str(raw))
    except (ValueError, TypeError):
        return None


def resolve_role_blocking(user_id: str, instance_id: str) -> str | None:
    """The caller's role on a session, or None when it is invisible to them."""
    uid, iid = _uuid(user_id), _uuid(instance_id)
    if uid is None or iid is None:
        return None
    with SessionLocal() as db:
        instance = db.get(AgentInstance, iid)
        if instance is None:
            return None
        return access.instance_role(db, uid, instance)


async def cached_role(conn: Connection, instance_id: str) -> str | None:
    """`resolve_role_blocking` behind the connection's short-lived cache."""
    now = time.monotonic()
    hit = conn.access_cache.get(instance_id)
    if hit is not None and now - hit[0] < ACCESS_TTL_SECONDS:
        return hit[1]
    role = await asyncio.to_thread(resolve_role_blocking, conn.user_id, instance_id)
    conn.access_cache[instance_id] = (time.monotonic(), role)
    return role


async def handle_watch_instance(conn: Connection, frame: dict) -> dict:
    """Answer a `watch_instance` frame.

    `ok: false` is the one answer for "no such session" and "not yours to
    watch" alike, so the frame is not an existence oracle. The owner gets
    `ok: true` without joining — their own rooms already carry it.
    """
    instance_id = frame.get("instance_id")
    response: dict = {
        "type": "watch_instance_response",
        "request_id": frame.get("request_id"),
        "instance_id": instance_id,
        "ok": False,
        "role": None,
    }
    if conn.scope != "user-scoped" or _uuid(instance_id) is None:
        return response
    instance_id = str(_uuid(instance_id))
    response["instance_id"] = instance_id
    role = await cached_role(conn, instance_id)
    if role is None:
        return response
    if role != "owner" and not connection_manager.watch(conn, instance_id):
        logger.warning(
            "WS %s watch limit reached; refusing %s", conn.connection_id, instance_id
        )
        return response
    response["ok"] = True
    response["role"] = role
    return response


def handle_unwatch_instance(conn: Connection, frame: dict) -> None:
    instance_id = _uuid(frame.get("instance_id"))
    if instance_id is not None:
        connection_manager.unwatch(conn, str(instance_id))


def revalidate_watchers(db: Session, user_ids: set[str] | None = None) -> int:
    """Re-check every watcher's access (or just `user_ids`') and evict the
    ones that lost it. One batched resolver call per watching user.

    Also refreshes each connection's access cache with the answer, so a
    fetch right after a role change sees the new role. Returns the number of
    evictions.
    """
    by_user: dict[str, dict[str, list[Connection]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for instance_id, conns in connection_manager.watchers().items():
        for conn in conns:
            if user_ids is None or conn.user_id in user_ids:
                by_user[conn.user_id][instance_id].append(conn)
    evicted = 0
    for raw_user, watched in by_user.items():
        uid = _uuid(raw_user)
        ids = [iid for iid in (_uuid(i) for i in watched) if iid is not None]
        if uid is None or not ids:
            continue
        instances = db.query(AgentInstance).filter(AgentInstance.id.in_(ids)).all()
        roles = access.instance_roles(db, uid, instances)
        now = time.monotonic()
        for raw_instance, conns in watched.items():
            iid = _uuid(raw_instance)
            role = roles.get(iid) if iid is not None else None
            for conn in conns:
                if role is None or role == "owner":
                    # An owner in a watcher room would get the narrowed copy
                    # over their full one; ownership never changes today, but
                    # the room is for grantees only.
                    connection_manager.revoke_watch(conn, raw_instance)
                    evicted += 1
                else:
                    conn.access_cache[raw_instance] = (now, role)
    if evicted:
        logger.info("watcher revalidation evicted %d watch(es)", evicted)
    return evicted


def revalidate_watchers_blocking(user_ids: set[str] | None = None) -> int:
    with SessionLocal() as db:
        return revalidate_watchers(db, user_ids)


def forget_cached_access(user_ids: set[str]) -> None:
    """Drop the access cache of every connection these users hold, so their
    next grant-gated read resolves afresh (a new grant should work at once,
    not after the TTL of a cached "no")."""
    for user_id in user_ids:
        for conn in connection_manager.connections_of(user_id):
            conn.access_cache.clear()
