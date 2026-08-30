"""Helpers for classifying database-layer errors.

The primary use case is detecting transient psycopg2 disconnects (caused by
Fly's flycast TCP proxy resetting backhauls). These should surface as 503
with `Retry-After` so daemon clients retry naturally, instead of as 500s
that pollute Sentry and look like real outages.
"""

from __future__ import annotations

from psycopg2 import OperationalError as Psycopg2OperationalError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import OperationalError as SAOperationalError

# Substrings we treat as transient transport-layer disconnects.
# Kept narrow on purpose: we don't want to swallow real connection-refused
# or authentication errors.
_DISCONNECT_SUBSTRINGS: tuple[str, ...] = (
    "server closed the connection",
    "connection reset",
    "could not receive data",
    "no connection to the server",
    "terminating connection due to administrator command",
    "ssl connection has been closed",
)


def is_db_disconnect(exc: BaseException) -> bool:
    """True if `exc` is a transient psycopg2 transport-layer disconnect.

    Matches both SQLAlchemy's wrapped form (OperationalError with
    `connection_invalidated`) and the underlying psycopg2 OperationalError
    by message-substring. Safe to call on any exception.
    """
    if isinstance(exc, DBAPIError) and getattr(exc, "connection_invalidated", False):
        return True

    inner = getattr(exc, "orig", exc)
    if isinstance(inner, Psycopg2OperationalError):
        msg = str(inner).lower()
        return any(s in msg for s in _DISCONNECT_SUBSTRINGS)

    if isinstance(exc, SAOperationalError):
        msg = str(exc).lower()
        return any(s in msg for s in _DISCONNECT_SUBSTRINGS)

    return False
