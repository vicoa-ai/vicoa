"""Vicoa constants and default configuration values.

Both defaults are env-overridable so a self-hosted install can point the CLI and
daemon at its own deployment without passing ``--base-url`` to every command:

    export VICOA_API_URL=https://vicoa.example.com     # agent-facing API + /ws
    export VICOA_AUTH_URL=https://vicoa.example.com    # browser login handoff
"""

import os

# Default API endpoint — the agent-facing `vicoa-server` app's canonical
# hostname (websocket-migration §2.1). Serves both agent REST and `/ws` on
# port 443. The legacy `api.vicoa.ai:8443` is kept reachable by the same app
# for daemons already deployed in the wild and is not used for new installs.
DEFAULT_API_URL = os.environ.get("VICOA_API_URL") or "https://agents.vicoa.ai"

# Default frontend URL for authentication
DEFAULT_AUTH_URL = os.environ.get("VICOA_AUTH_URL") or "https://vicoa.ai"
