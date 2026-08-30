"""Caller side of the backend->server `_internal/broadcast` bridge (§2.11).

A backend write commits, then an `after_commit` callback calls `post_broadcast`
to deliver the realtime `update` to the `server` process's `ConnectionManager`
(the WS connections live there, not in `backend`). The POST is fire-and-forget:
the DB write already succeeded, so a bridge failure only degrades realtime
delivery — it is logged and metered, never raised.
"""

import logging

import httpx

from shared.config import settings

logger = logging.getLogger(__name__)

_BRIDGE_TIMEOUT_SECONDS = 2.0


def post_broadcast(user_id: str, payload: dict, rooms: list[str]) -> None:
    """POST a realtime `update` to the server process's broadcast receiver."""
    if not settings.internal_broadcast_url or not settings.internal_broadcast_token:
        # Without this warning the no-op is silent and a missing env var
        # masquerades as "realtime works but no live updates land" — hours
        # of head-scratching. Cheap, low-frequency, only fires on misconfig.
        logger.warning(
            "broadcast_bridge_skip user=%s reason=missing_config url_set=%s token_set=%s",
            user_id,
            bool(settings.internal_broadcast_url),
            bool(settings.internal_broadcast_token),
        )
        return
    try:
        response = httpx.post(
            settings.internal_broadcast_url,
            json={"user_id": user_id, "payload": payload, "rooms": rooms},
            headers={"Authorization": f"Bearer {settings.internal_broadcast_token}"},
            timeout=_BRIDGE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        # `broadcast_bridge_failure` is the stable marker an alert keys on.
        logger.warning("broadcast_bridge_failure user=%s err=%s", user_id, exc)


def post_close_user(user_id: str) -> None:
    """POST a credential-revoke signal to the server process so every live WS
    connection owned by `user_id` is closed with 4401 "credential_revoked".

    Called from `delete_user_account` after the cascade commit so a deleted
    user's daemon drops the link within milliseconds — without waiting for
    its next REST call to bounce off Phase 1's FK handler. Fire-and-forget:
    the DB delete already succeeded, so a bridge failure only degrades the
    teardown latency, never raises. Reuses the broadcast bridge's URL and
    token; the path differs (`/_internal/close_user` instead of
    `/_internal/broadcast`).
    """
    if not settings.internal_broadcast_url or not settings.internal_broadcast_token:
        logger.warning(
            "close_user_bridge_skip user=%s reason=missing_config url_set=%s token_set=%s",
            user_id,
            bool(settings.internal_broadcast_url),
            bool(settings.internal_broadcast_token),
        )
        return
    url = settings.internal_broadcast_url.replace(
        "/_internal/broadcast", "/_internal/close_user"
    )
    try:
        response = httpx.post(
            url,
            json={"user_id": user_id},
            headers={"Authorization": f"Bearer {settings.internal_broadcast_token}"},
            timeout=_BRIDGE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        # `close_user_bridge_failure` is the stable marker an alert keys on.
        logger.warning("close_user_bridge_failure user=%s err=%s", user_id, exc)
