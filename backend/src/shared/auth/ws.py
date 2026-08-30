"""Parse WebSocket credentials from offered subprotocols (websocket-migration §2.9).

Tokens are carried via `Sec-WebSocket-Protocol`, not query params (query strings
leak into proxy logs / Sentry / browser history). Two credential subprotocols
are accepted:

    vicoa-key.<rs256-jwt>      # CLI / daemon
    vicoa-supabase.<jwt>       # web / mobile

Per the WebSocket spec, a server that receives any offered subprotocol must echo
back exactly one offered value. The server must never echo the credential-bearing
value, so the client also offers a non-credential marker (`vicoa-ws`); this
parser reports it back as `echo_subprotocol` for the endpoint to echo on accept.

Written fresh for `/ws`; the relay server is not in use and is not modified.
"""

import re
from dataclasses import dataclass
from typing import Literal

# The desktop app's Electron renderer connects to `/ws` from
# http://127.0.0.1:<port> (a dynamic loopback port), so it can't be a static
# allowlist entry. A remote page cannot forge a loopback Origin, and the token
# is still required, so any localhost/127.0.0.1 port is accepted.
_LOCALHOST_ORIGIN_RE = re.compile(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$")

API_KEY_PREFIX = "vicoa-key."
SUPABASE_PREFIX = "vicoa-supabase."
MARKER_SUBPROTOCOL = "vicoa-ws"

TokenType = Literal["vicoa-key", "vicoa-supabase"]


class WsAuthError(Exception):
    """Raised when offered subprotocols carry no usable credential."""


@dataclass(slots=True)
class WsCredentials:
    """Credentials parsed from the offered WebSocket subprotocols."""

    token_type: TokenType
    raw_token: str
    echo_subprotocol: str | None


def parse_ws_subprotocol_credentials(offered: list[str]) -> WsCredentials:
    """Extract the credential and echo marker from offered subprotocols."""
    candidates = [p.strip() for p in offered if p.strip()]
    echo = MARKER_SUBPROTOCOL if MARKER_SUBPROTOCOL in candidates else None

    for candidate in candidates:
        if candidate.startswith(API_KEY_PREFIX):
            return WsCredentials("vicoa-key", _token(candidate, API_KEY_PREFIX), echo)
        if candidate.startswith(SUPABASE_PREFIX):
            return WsCredentials(
                "vicoa-supabase", _token(candidate, SUPABASE_PREFIX), echo
            )

    raise WsAuthError("No credential-bearing subprotocol offered")


def _token(candidate: str, prefix: str) -> str:
    token = candidate[len(prefix) :]
    if not token:
        raise WsAuthError(f"{prefix!r} subprotocol carries an empty token")
    return token


def is_origin_allowed(origin: str | None, allowed_origins: list[str]) -> bool:
    """Whether a WebSocket handshake's `Origin` is acceptable (§2.9).

    Browsers do not enforce same-origin for WebSocket, so a malicious site
    holding a token could open `/ws` — `Origin` must therefore be allowlisted
    for browser connections. Native apps and daemons send no `Origin` header
    and have no malicious-site vector, so an absent `Origin` is exempt.
    """
    if origin is None:
        return True
    if origin in allowed_origins:
        return True
    # Desktop app (Electron renderer on a dynamic loopback port) — see
    # _LOCALHOST_ORIGIN_RE above.
    return bool(_LOCALHOST_ORIGIN_RE.match(origin))
