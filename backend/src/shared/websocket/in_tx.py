"""Post-commit guarantee for realtime updates (websocket-migration plan §2.7).

Realtime `update` frames must never be emitted for a transaction that rolls
back. `after_commit(db, callback)` registers a one-shot listener that fires
only when the next commit on `db` succeeds. On rollback the listener is
discarded with the session — no broadcast is sent.

Use:

    message = create_user_message(db, ...)
    payload = build_new_message_update(message)   # snapshot ORM -> primitives
    rooms = [f"user:{user_id}:session:{instance_id}", ...]
    after_commit(db, lambda: post_broadcast(str(user_id), payload, rooms))
    db.commit()                                    # listener fires here

Two rules the abstraction does not enforce — they must be respected by callers:

1.  Build the envelope (a plain dict) *before* registering the callback. The
    session's `expire_on_commit=True` (SQLAlchemy default) means any ORM
    attribute access from inside the lambda would refresh against a closed
    transaction, raising or issuing a surprise query.

2.  Register the callback *before* calling `db.commit()`. The listener is
    attached to the session and fires on the next commit; if registration
    happens after commit, the callback is bound to a later commit (or never
    fires at all when the session closes).

Design note: a per-session listener is preferred over a `with`-block /
ContextVar wrapper because FastAPI auth dependencies (`get_current_user`) read
the DB before the handler body runs, autobeginning a transaction on the
request session. A wrapper that opens its own transaction collides with that
pre-existing one; this design attaches a listener to the session SQLAlchemy
is already managing, so the broadcast fires on the same commit that persists
both the auth-dep read and the handler's writes.
"""

import logging
from collections.abc import Callable

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def after_commit(db: Session | AsyncSession, callback: Callable[[], None]) -> None:
    """Register `callback` to run after the next successful commit on `db`.

    Fires once, then detaches. If the transaction rolls back (handler raises,
    session closes without commit, explicit rollback), the listener is
    discarded without firing.

    Exceptions raised by `callback` are logged and swallowed. A broadcast
    failure must never propagate into SQLAlchemy's event dispatch — that
    would skip remaining listeners on this event and could corrupt
    later commits on the same session.
    """
    # AsyncSession proxies events through its underlying sync Session.
    target = db.sync_session if isinstance(db, AsyncSession) else db

    def _fire(session: Session) -> None:
        del session  # SQLAlchemy passes the session; we only need to fire.
        try:
            callback()
        except Exception:
            logger.exception("after_commit callback failed")

    event.listen(target, "after_commit", _fire, once=True)
