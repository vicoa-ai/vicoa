"""`_safe_close` must treat a benign double-close as a no-op, not a Sentry error.

When a user is deleted, ``POST /_internal/close_user`` fires a 4401
"credential_revoked" close on every WS connection owned by that user
(``ws_handler._on_revoked``). That close is one of several *uncoordinated*
server-side close paths — overflow (1008), ping-loop missed-pong (4400), and the
new revoke (4401) — each scheduled fire-and-forget with ``asyncio.create_task``.
When another path closes the socket first, the queued ``_safe_close`` runs
against an already-``DISCONNECTED`` socket and Starlette raises
``RuntimeError: Cannot call "send" once a close message has been sent.``
(Sentry PYTHON-FLASK-2K, first seen 2026-06-20). That is the *desired* end state
— the socket is already closed — so it must not be reported to Sentry.

The genuinely-unexpected close failure ``_safe_close`` was originally written for
— the legacy ``websockets`` ``AttributeError`` on a dead TCP transport (the
2026-06-04 vicoa-server wedge, where the transport really did leak) — must still
reach Sentry.
"""

from typing import cast

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from servers.api import ws_handler
from servers.api.ws_handler import _safe_close


class _FakeWebSocket:
    """Minimal stand-in for a Starlette ``WebSocket``: just the two attributes
    ``_safe_close`` touches — ``application_state`` and an awaitable ``close``."""

    def __init__(
        self,
        application_state: WebSocketState,
        close_exc: BaseException | None = None,
    ) -> None:
        self.application_state = application_state
        self._close_exc = close_exc
        self.close_calls: list[tuple[int, str]] = []

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.close_calls.append((code, reason))
        if self._close_exc is not None:
            raise self._close_exc


async def test_safe_close_skips_close_when_already_disconnected(monkeypatch) -> None:
    """A connection a peer/another path already closed is ``DISCONNECTED``.
    ``_safe_close`` must not even attempt a second close frame, and must not
    report anything to Sentry — the socket is already in the desired state."""
    captured: list[bool] = []
    monkeypatch.setattr(
        ws_handler.sentry_sdk,
        "capture_exception",
        lambda *_a, **_k: captured.append(True),
    )
    ws = _FakeWebSocket(
        application_state=WebSocketState.DISCONNECTED,
        close_exc=RuntimeError(
            'Cannot call "send" once a close message has been sent.'
        ),
    )

    await _safe_close(cast(WebSocket, ws), code=4401, reason="credential_revoked")

    assert ws.close_calls == []  # no second close attempted
    assert captured == []  # nothing reported to Sentry


async def test_safe_close_swallows_already_sent_close_runtimeerror(monkeypatch) -> None:
    """State reads CONNECTED, but a concurrent close path wins the race between
    the check and our ``close()`` call. Starlette then raises the benign
    "already sent" ``RuntimeError`` — swallow it without a Sentry capture."""
    captured: list[bool] = []
    monkeypatch.setattr(
        ws_handler.sentry_sdk,
        "capture_exception",
        lambda *_a, **_k: captured.append(True),
    )
    ws = _FakeWebSocket(
        application_state=WebSocketState.CONNECTED,
        close_exc=RuntimeError(
            'Cannot call "send" once a close message has been sent.'
        ),
    )

    await _safe_close(cast(WebSocket, ws), code=4401, reason="credential_revoked")

    assert ws.close_calls == [(4401, "credential_revoked")]
    assert captured == []  # benign race — not a Sentry error


async def test_safe_close_reports_unexpected_close_failure_to_sentry(
    monkeypatch,
) -> None:
    """The original failure mode: the legacy ``websockets`` ``AttributeError`` on
    a dead transport (the 2026-06-04 wedge). This genuinely leaks the transport
    and must still be captured to Sentry."""
    captured: list[bool] = []
    monkeypatch.setattr(
        ws_handler.sentry_sdk,
        "capture_exception",
        lambda *_a, **_k: captured.append(True),
    )
    ws = _FakeWebSocket(
        application_state=WebSocketState.CONNECTED,
        close_exc=AttributeError(
            "'WebSocketProtocol' object has no attribute 'transfer_data_task'"
        ),
    )

    await _safe_close(cast(WebSocket, ws), code=4400)

    assert ws.close_calls == [(4400, "")]
    assert captured == [True]  # genuine leak — still reported
