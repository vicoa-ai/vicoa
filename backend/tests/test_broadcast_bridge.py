"""Unit tests for the backend->server `_internal/broadcast` bridge caller.

`post_broadcast` is the caller side of the cross-process broadcast bridge
(websocket-migration plan §2.11, Phase 3 Slice 1). A backend write commits,
then an `after_commit` callback POSTs the realtime update to the `server`
process's `ConnectionManager`. The POST is fire-and-forget: a failure is
logged and metered, never raised, because the DB write already succeeded.
"""

import logging
from unittest.mock import patch

import httpx
import pytest

from backend.broadcast_bridge import post_broadcast
from shared.config import settings

_BRIDGE_URL = "http://vicoa-server.internal:8080/_internal/broadcast"


@pytest.fixture
def configured_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "internal_broadcast_url", _BRIDGE_URL)
    monkeypatch.setattr(settings, "internal_broadcast_token", "secret-token")


def test_post_broadcast_posts_payload_with_bearer_token(
    configured_bridge: None,
) -> None:
    with patch("backend.broadcast_bridge.httpx.post") as mock_post:
        post_broadcast("user-1", {"entity": "messages"}, ["user:user-1:user-scoped"])

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == _BRIDGE_URL
    assert kwargs["json"] == {
        "user_id": "user-1",
        "payload": {"entity": "messages"},
        "rooms": ["user:user-1:user-scoped"],
    }
    assert kwargs["headers"]["Authorization"] == "Bearer secret-token"


def test_post_broadcast_swallows_connection_error(
    configured_bridge: None, caplog: pytest.LogCaptureFixture
) -> None:
    with patch(
        "backend.broadcast_bridge.httpx.post",
        side_effect=httpx.ConnectError("connection refused"),
    ):
        with caplog.at_level(logging.WARNING):
            # The DB write already succeeded — a bridge failure must not raise.
            post_broadcast("user-1", {"entity": "messages"}, ["r"])

    assert "broadcast_bridge_failure" in caplog.text


def test_post_broadcast_is_noop_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "internal_broadcast_url", "")
    monkeypatch.setattr(settings, "internal_broadcast_token", "")

    with patch("backend.broadcast_bridge.httpx.post") as mock_post:
        post_broadcast("user-1", {"entity": "messages"}, ["r"])

    mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# post_close_user — credential-revoke side of the bridge
# ---------------------------------------------------------------------------


from backend.broadcast_bridge import post_close_user  # noqa: E402


def test_post_close_user_posts_to_close_endpoint_with_bearer(
    configured_bridge: None,
) -> None:
    """Hits `/_internal/close_user` (not `/broadcast`) with the same token."""
    with patch("backend.broadcast_bridge.httpx.post") as mock_post:
        post_close_user("user-1")

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "http://vicoa-server.internal:8080/_internal/close_user"
    assert kwargs["json"] == {"user_id": "user-1"}
    assert kwargs["headers"]["Authorization"] == "Bearer secret-token"


def test_post_close_user_swallows_connection_error(
    configured_bridge: None, caplog: pytest.LogCaptureFixture
) -> None:
    """The DB delete already committed — a bridge failure only delays WS
    teardown; it must not raise back into delete_user_account."""
    with patch(
        "backend.broadcast_bridge.httpx.post",
        side_effect=httpx.ConnectError("connection refused"),
    ):
        with caplog.at_level(logging.WARNING):
            post_close_user("user-1")

    assert "close_user_bridge_failure" in caplog.text


def test_post_close_user_is_noop_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "internal_broadcast_url", "")
    monkeypatch.setattr(settings, "internal_broadcast_token", "")

    with patch("backend.broadcast_bridge.httpx.post") as mock_post:
        post_close_user("user-1")

    mock_post.assert_not_called()
