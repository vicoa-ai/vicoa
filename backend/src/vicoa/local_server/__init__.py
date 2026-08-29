"""Local FastAPI server embedded in the machine daemon (desktop app v1).

One app on ``127.0.0.1:<port>`` carrying the local WebSocket (``/ws``, same
frame grammar as the cloud ``servers/api/ws_handler.py``) and a small REST
subset. In local-only (logged-out) mode it impersonates the backend for one
user, persisting instances and messages in SQLite; in cloud mode it serves
only RPC (files/git/pty) while the cloud carries chat traffic.

This package must stay importable from the packaged CLI distribution: it may
only depend on ``vicoa*``, ``integrations*``, ``protocol*`` and third-party
CLI deps — never ``shared.*``, ``servers.*`` or ``backend.*`` (those are not
shipped with the CLI). Wire-shape parity with the cloud server is enforced by
unit tests instead of shared imports.
"""

from .app import create_local_app
from .store import LocalStore

__all__ = ["create_local_app", "LocalStore"]
