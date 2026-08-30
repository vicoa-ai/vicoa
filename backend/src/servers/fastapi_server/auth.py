"""Authentication dependencies for FastAPI server.

Kept as an alias of :mod:`servers.api.auth`: this module used to carry its own
copy of the RS256 decode, which is exactly the duplication that let a revoked
API key keep working on one code path and not the other.
"""

from servers.api.auth import (  # noqa: F401
    get_current_principal,
    get_current_user_id,
    security,
)

__all__ = ["get_current_principal", "get_current_user_id", "security"]
