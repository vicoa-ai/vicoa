"""Server-side automation scheduler (automation-scheduled-tasks plan §v1).

A plain asyncio sweep in the `server` process claims due `automations` rows and
dispatches them via the existing `spawn-session` WebSocket RPC. It must live here
(not in the `backend` process) because `rpc_router` — the registry of connected
daemons — is process-local to the `server` app.
"""

from .loop import AutomationScheduler

__all__ = ["AutomationScheduler"]
