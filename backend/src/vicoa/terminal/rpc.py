"""Shared pty-* RPC handlers.

Used by BOTH the desktop local server (``vicoa/local_server/rpc.py``, over the
127.0.0.1 socket) and the cloud machine daemon (``machine_daemon.py``, for
terminals opened on this machine *from another device* through the relay).
Keeping the dispatch here means the local and remote paths can never drift.

Each handler drives a :class:`~vicoa.terminal.service.TerminalService`. Output
does not flow through these calls — ``pty-spawn`` returns ``{"pty_id": …}`` and
the bytes arrive asynchronously via the service's ``on_output``/``on_exit``
callbacks (pushed as ``pty-output``/``pty-exit`` frames by whichever transport
owns the service).
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

from vicoa.terminal.service import TerminalService

# The pty methods this module dispatches. Callers advertise these (local server
# via ``LOCAL_ONLY_RPC_METHODS``, cloud daemon via ``_supported_rpc_methods``).
PTY_RPC_METHODS: tuple[str, ...] = (
    "pty-spawn",
    "pty-write",
    "pty-resize",
    "pty-kill",
    "pty-heartbeat",
)

# Pty methods whose order at the daemon MUST match the order the client sent
# them — a keystroke byte stream, its interleaved window resizes, and the final
# kill. The client pipelines these (fire-and-forget, no per-keystroke ack) so
# typing isn't serialized at one round-trip per key; to keep that safe the WS
# layers route these to a single ordered worker instead of the parallel RPC
# pool, where two keystrokes could otherwise land on different threads and
# reorder. ``pty-spawn`` and ``pty-heartbeat`` are intentionally excluded:
# spawn is awaited one-at-a-time by the client (and may block on fork/exec,
# which must not stall other terminals' input), and heartbeat only renews a
# lease (order-independent).
PTY_ORDERED_METHODS: frozenset[str] = frozenset({"pty-write", "pty-resize", "pty-kill"})


def handle_pty_rpc(
    terminal: TerminalService, method: str, params: dict[str, Any]
) -> dict[str, Any] | None:
    """Handle a pty-* method, returning its result dict.

    Returns ``None`` (never a valid pty result) when ``method`` is not a pty
    method, so the caller can fall through to its other handlers. Errors are
    returned as ``{"error": …}`` dicts — the same convention the daemon uses —
    so the renderer sees a normal ``rpc-result``.
    """
    if method not in PTY_RPC_METHODS:
        return None
    try:
        if method == "pty-spawn":
            return _pty_spawn(terminal, params)
        if method == "pty-write":
            return _pty_write(terminal, params)
        if method == "pty-resize":
            return _pty_resize(terminal, params)
        if method == "pty-kill":
            return _pty_kill(terminal, params)
        return _pty_heartbeat(terminal, params)
    except KeyError as exc:
        return {"error": f"unknown pty_id: {exc.args[0] if exc.args else exc}"}
    except (ValueError, RuntimeError) as exc:
        return {"error": str(exc)}


def _pty_spawn(terminal: TerminalService, params: dict[str, Any]) -> dict[str, Any]:
    cwd = params.get("cwd")
    if not isinstance(cwd, str) or not cwd.strip():
        return {"error": "pty-spawn requires a cwd"}
    command_param = params.get("command")
    command: list[str] | None = None
    if isinstance(command_param, list) and command_param:
        command = [str(part) for part in command_param]
    pty_id = terminal.spawn(
        cwd=cwd,
        cols=int(params.get("cols") or 80),
        rows=int(params.get("rows") or 24),
        command=command,
        lease_secs=_lease_secs(params),
    )
    # `ordered_input` tells the client this daemon applies pty input
    # (write/resize/kill) in receive order (§ PTY_ORDERED_METHODS), so it's safe
    # to pipeline keystrokes fire-and-forget. Absent on daemons that predate the
    # ordered path — the client then keeps the awaited, one-in-flight path so
    # their parallel RPC pool can't reorder keystrokes. Present here for both the
    # local server and the cloud daemon, which share this handler.
    return {"pty_id": pty_id, "ordered_input": True}


def _lease_secs(params: dict[str, Any]) -> float | None:
    """A positive ``lease_secs`` opts the session into lease-reaping; anything
    else (absent, non-numeric, <= 0) leaves it unmanaged — the legacy path for
    clients that don't heartbeat."""
    raw = params.get("lease_secs")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw) if raw > 0 else None


def _pty_write(terminal: TerminalService, params: dict[str, Any]) -> dict[str, Any]:
    pty_id = str(params.get("pty_id") or "")
    raw = params.get("data")
    if not isinstance(raw, str):
        return {"error": "pty-write requires base64 data"}
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        return {"error": "pty-write data is not valid base64"}
    terminal.write(pty_id, data)
    return {}


def _pty_resize(terminal: TerminalService, params: dict[str, Any]) -> dict[str, Any]:
    terminal.resize(
        str(params.get("pty_id") or ""),
        cols=int(params.get("cols") or 80),
        rows=int(params.get("rows") or 24),
    )
    return {}


def _pty_kill(terminal: TerminalService, params: dict[str, Any]) -> dict[str, Any]:
    terminal.kill(str(params.get("pty_id") or ""))
    return {}


def _pty_heartbeat(terminal: TerminalService, params: dict[str, Any]) -> dict[str, Any]:
    """Renew the lease on the client's still-live ptys. ``renewed`` echoes the
    ids the daemon still has, so a client can tell when one was already reaped."""
    raw_ids = params.get("pty_ids")
    if not isinstance(raw_ids, list):
        return {"error": "pty-heartbeat requires a pty_ids list"}
    pty_ids = [x for x in raw_ids if isinstance(x, str) and x]
    renewed = terminal.renew_leases(pty_ids, lease_secs=_lease_secs(params))
    return {"renewed": renewed}
