"""Bring-up handshake for the Pi-family RPC transport.

Two agents, two handshakes:

* **omp** emits an unsolicited ``ready`` frame before anything else, then
  answers ``negotiate_protocol`` with the agreed version. v2 is worth having:
  it is what enables ``rpc_chunk`` reassembly for frames over 1 MiB (a long
  ``agent_end`` transcript overflows that easily).
* **pi** has no ``ready`` frame and no ``negotiate_protocol`` command at all —
  responses come straight back.

Both fail *before* the handshake when the machine has no model configured, so
the wait for ``ready`` is also the place a mis-set-up install is detected.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from integrations.headless.pi_family.spec import PiFamilySpec
from integrations.headless.pi_family.transport import (
    PiRpcError,
    PiTransport,
    PiTransportClosed,
)


logger = logging.getLogger(__name__)

#: How long to wait for omp's unsolicited ``ready`` frame. Generous because a
#: cold start loads extensions, skills and model catalogs; bounded because a
#: hang here is indistinguishable to the user from a dead session.
READY_TIMEOUT_SECONDS = 60.0
NEGOTIATE_TIMEOUT_SECONDS = 30.0


class PiStartupError(RuntimeError):
    """The agent never reached a usable RPC state.

    Raised with a message already fit for the chat surface — the runner posts
    it verbatim through the shared startup-failure path.
    """


@dataclass
class HandshakeResult:
    """What bring-up learned about the connected agent."""

    #: Negotiated protocol version (1 when nothing was negotiated).
    protocol_version: int = 1
    #: Byte ceilings advertised in ``ready``; ``None`` when there was no frame.
    max_frame_bytes: Optional[int] = None
    max_reassembled_frame_bytes: Optional[int] = None
    ready_frame: Optional[Dict[str, Any]] = None


class ReadyGate:
    """One-shot latch for the ``ready`` frame.

    Lives outside the session because the event handler has to be registered
    on the transport *before* the read loop starts (omp's ``ready`` is the very
    first frame), which is earlier than the session can meaningfully exist.
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self.frame: Optional[Dict[str, Any]] = None

    def offer(self, frame: Dict[str, Any]) -> bool:
        """Consume ``frame`` if it is the ready frame. Returns True if it was."""
        if frame.get("type") != "ready":
            return False
        self.frame = frame
        self._event.set()
        return True

    async def wait(self, timeout: float) -> Dict[str, Any]:
        await asyncio.wait_for(self._event.wait(), timeout)
        assert self.frame is not None
        return self.frame


def is_missing_credentials(stderr_tail: str) -> bool:
    """Whether a startup failure looks like "no provider configured".

    Both CLIs are BYO-key/OAuth across many providers and neither starts
    without one, exiting 1 with ``No models available. Use /login or set an
    API key environment variable.`` — the same class of failure OpenCode has.
    Worth naming specifically because the generic message ("exited with code
    1") sends people looking for a Vicoa bug.
    """
    lowered = (stderr_tail or "").lower()
    return "no models available" in lowered or (
        "api key" in lowered and "login" in lowered
    )


def startup_failure_message(
    display_name: str, *, stderr_tail: str, reason: str = ""
) -> str:
    """Human-readable explanation for a failed bring-up.

    Same shape and tone as ``acp_base._startup_failure_message`` — the
    credentials case is worded conditionally on purpose, because an agent that
    works in your terminal can still fail when the *daemon* spawns it (launchd
    gives it a reduced environment in which the agent can't find its auth).
    """
    if is_missing_credentials(stderr_tail):
        return (
            f"{display_name} couldn't start: no model is configured. Run "
            f"`{display_name.lower().replace(' ', '')}` on this machine and "
            f"sign in (or set the provider's API key env var), then retry. If "
            f"it works when you run it directly, the daemon may not see the "
            f"same environment — let us know at hi@vicoa.ai."
        )
    detail = reason or "it exited before completing the RPC handshake"
    tail = f"\n\n```\n{stderr_tail.strip()}\n```" if stderr_tail.strip() else ""
    return (
        f"{display_name} couldn't start: {detail}.{tail}\n\n"
        f"If this looks like a Vicoa bug, please report it to hi@vicoa.ai."
    )


async def perform_handshake(
    transport: PiTransport,
    spec: PiFamilySpec,
    ready_gate: ReadyGate,
    *,
    stderr_tail: Optional[Any] = None,
) -> HandshakeResult:
    """Wait for ``ready`` (when expected) and negotiate the protocol version.

    Raises :class:`PiStartupError` with a chat-ready message when the agent
    dies or never announces itself.
    """
    result = HandshakeResult()

    def tail() -> str:
        if stderr_tail is None:
            return ""
        try:
            return stderr_tail()
        except Exception:
            return ""

    if spec.expects_ready_frame:
        try:
            frame = await ready_gate.wait(READY_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            raise PiStartupError(
                startup_failure_message(
                    spec.display_name,
                    stderr_tail=tail(),
                    reason=(
                        f"it did not announce itself within "
                        f"{READY_TIMEOUT_SECONDS:.0f}s"
                    ),
                )
            ) from None
        if transport.is_closed:
            raise PiStartupError(
                startup_failure_message(spec.display_name, stderr_tail=tail())
            )
        result.ready_frame = frame
        result.max_frame_bytes = frame.get("maxFrameBytes")
        result.max_reassembled_frame_bytes = frame.get("maxReassembledFrameBytes")
        logger.info(
            "pi_family: %s ready (protocol %s, supported=%s)",
            spec.catalog_id,
            frame.get("protocolVersion"),
            frame.get("supportedProtocolVersions"),
        )
    elif transport.is_closed:
        raise PiStartupError(
            startup_failure_message(spec.display_name, stderr_tail=tail())
        )

    wanted = spec.negotiate_protocol_version
    if wanted is not None:
        supported = (result.ready_frame or {}).get("supportedProtocolVersions")
        if isinstance(supported, list) and supported and wanted not in supported:
            # An older build that doesn't know our version: stay on v1 rather
            # than negotiating a version it will reject. v1 only costs us
            # chunked frames, which the agent then avoids emitting.
            logger.info(
                "pi_family: %s does not support protocol v%s (%s); staying on v1",
                spec.catalog_id,
                wanted,
                supported,
            )
            return result
        try:
            data = await asyncio.wait_for(
                transport.request(
                    "negotiate_protocol",
                    {"protocolVersion": wanted},
                    timeout=NEGOTIATE_TIMEOUT_SECONDS,
                ),
                timeout=NEGOTIATE_TIMEOUT_SECONDS,
            )
            agreed = data.get("protocolVersion")
            if isinstance(agreed, int):
                result.protocol_version = agreed
        except PiTransportClosed as exc:
            raise PiStartupError(
                startup_failure_message(
                    spec.display_name, stderr_tail=tail(), reason=str(exc)
                )
            ) from exc
        except (PiRpcError, asyncio.TimeoutError, TimeoutError) as exc:
            # Negotiation is an optimisation; v1 is a working protocol. Log and
            # continue rather than failing a session over it.
            logger.warning(
                "pi_family: negotiate_protocol failed (%s); staying on v1", exc
            )
    return result


__all__ = [
    "HandshakeResult",
    "NEGOTIATE_TIMEOUT_SECONDS",
    "PiStartupError",
    "READY_TIMEOUT_SECONDS",
    "ReadyGate",
    "is_missing_credentials",
    "perform_handshake",
    "startup_failure_message",
]
