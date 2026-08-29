"""Tests for PGNotificationHub."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from shared.pg_listener import (
    CoalescingQueue,
    PGNotificationHub,
    WakeEvent,
    _NOTIFY_PAYLOAD_WARN_BYTES,
    _WAKE_EVENTS,
)


@pytest_asyncio.fixture
async def hub():
    """Provide a hub and tear it down cleanly — `stop()` cancels any pending
    `_reconnect_task` that tests like the disconnect-duration ones leave
    behind when they trigger `_on_termination()`. Without this, the event
    loop closes with a pending task and pytest emits noisy
    `Task was destroyed but it is pending!` warnings."""
    h = PGNotificationHub(dsn="postgresql://test/test")
    try:
        yield h
    finally:
        await h.stop()


@pytest.fixture
def mock_conn():
    conn = MagicMock()
    conn.is_closed.return_value = False
    conn.add_listener = AsyncMock()
    conn.remove_listener = AsyncMock()
    conn.add_termination_listener = MagicMock()
    conn.close = AsyncMock()
    return conn


# ---------------------------------------------------------------------------
# WakeEvent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wake_event_set_and_clear():
    w = WakeEvent()
    assert not w.is_set()
    w.set()
    assert w.is_set()

    task = asyncio.create_task(w.wait_and_clear())
    await asyncio.sleep(0)
    await task
    assert not w.is_set()


@pytest.mark.asyncio
async def test_wake_event_multiple_sets_collapse():
    w = WakeEvent()
    for _ in range(100):
        w.set()
    assert w.is_set()
    await w.wait_and_clear()
    assert not w.is_set()


# ---------------------------------------------------------------------------
# CoalescingQueue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coalescing_queue_latest_wins():
    q = CoalescingQueue()
    import json

    q.put_nowait(json.dumps({"event_type": "status_update", "status": "ACTIVE"}))
    q.put_nowait(json.dumps({"event_type": "status_update", "status": "COMPLETED"}))
    payload = await q.get()
    data = json.loads(payload)
    assert data["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_coalescing_queue_different_types_preserved():
    q = CoalescingQueue()
    import json

    q.put_nowait(json.dumps({"event_type": "status_update", "status": "ACTIVE"}))
    q.put_nowait(json.dumps({"event_type": "git_diff_update"}))
    items = q.drain_nowait()
    assert len(items) == 2


@pytest.mark.asyncio
async def test_coalescing_queue_drain_nowait_clears():
    q = CoalescingQueue()
    import json

    q.put_nowait(json.dumps({"event_type": "status_update"}))
    items = q.drain_nowait()
    assert len(items) == 1
    assert len(q) == 0


# ---------------------------------------------------------------------------
# subscribe / listen lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscribe_first_subscriber_calls_add_listener(hub, mock_conn):
    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        async with hub.subscribe("chan_a"):
            mock_conn.add_listener.assert_called_once_with(
                "chan_a", hub._callbacks["chan_a"]
            )


@pytest.mark.asyncio
async def test_subscribe_second_subscriber_does_not_call_add_listener_again(
    hub, mock_conn
):
    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        async with hub.subscribe("chan_a"):
            async with hub.subscribe("chan_a"):
                assert mock_conn.add_listener.call_count == 1


@pytest.mark.asyncio
async def test_last_subscriber_calls_remove_listener(hub, mock_conn):
    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        async with hub.subscribe("chan_a"):
            pass
        mock_conn.remove_listener.assert_called_once_with(
            "chan_a", mock_conn.add_listener.call_args[0][1]
        )


@pytest.mark.asyncio
async def test_non_last_subscriber_does_not_call_remove_listener(hub, mock_conn):
    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        async with hub.subscribe("chan_a"):
            async with hub.subscribe("chan_a"):
                pass
            # Second exited — first still active, should NOT remove yet
            mock_conn.remove_listener.assert_not_called()


# ---------------------------------------------------------------------------
# callback routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wake_events_set_wake_flag(hub, mock_conn):
    import json

    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        async with hub.subscribe("chan_a") as (wake, _signals):
            callback = hub._callbacks["chan_a"]
            for event_type in _WAKE_EVENTS:
                payload = json.dumps({"event_type": event_type, "id": "abc"})
                callback(None, None, "chan_a", payload)
            assert wake.is_set()


@pytest.mark.asyncio
async def test_signal_events_go_to_coalescing_queue(hub, mock_conn):
    import json

    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        async with hub.subscribe("chan_a") as (wake, signals):
            callback = hub._callbacks["chan_a"]
            payload = json.dumps({"event_type": "git_diff_update"})
            callback(None, None, "chan_a", payload)
            assert not wake.is_set()
            assert len(signals) == 1


@pytest.mark.asyncio
async def test_signal_events_do_not_set_wake(hub, mock_conn):
    import json

    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        async with hub.subscribe("chan_a") as (wake, _signals):
            callback = hub._callbacks["chan_a"]
            for event_type in ("git_diff_update", "agent_heartbeat"):
                callback(
                    None,
                    None,
                    "chan_a",
                    json.dumps({"event_type": event_type}),
                )
            assert not wake.is_set()


@pytest.mark.asyncio
async def test_status_update_dual_routes_to_wake_and_queue(hub, mock_conn):
    import json

    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        async with hub.subscribe("chan_a") as (wake, signals):
            callback = hub._callbacks["chan_a"]
            payload = json.dumps({"event_type": "status_update", "status": "ACTIVE"})
            callback(None, None, "chan_a", payload)
            assert wake.is_set()
            assert len(signals) == 1


# ---------------------------------------------------------------------------
# reconnect behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconnect_relistens_all_active_channels(hub, mock_conn):
    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        async with hub.subscribe("chan_a"):
            async with hub.subscribe("chan_b"):
                hub._conn = None
                hub._callbacks.clear()
                await hub._ensure_connection_locked()

                listened = [c[0][0] for c in mock_conn.add_listener.call_args_list]
                assert "chan_a" in listened
                assert "chan_b" in listened


@pytest.mark.asyncio
async def test_reconnect_count_increments_on_each_reconnect(hub, mock_conn):
    assert hub.reconnect_count == 0
    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        await hub._ensure_connection_locked()
        assert hub.reconnect_count == 1

        hub._conn = None
        hub._callbacks.clear()
        await hub._ensure_connection_locked()
        assert hub.reconnect_count == 2


@pytest.mark.asyncio
async def test_reconnect_count_does_not_increment_when_already_connected(
    hub, mock_conn
):
    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        await hub._ensure_connection_locked()
        first_count = hub.reconnect_count
        await hub._ensure_connection_locked()
        assert hub.reconnect_count == first_count


# ---------------------------------------------------------------------------
# oversized-payload warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oversized_notify_payload_logs_warning(hub, mock_conn, caplog):
    """PG aborts the triggering write if a NOTIFY payload exceeds 8000 bytes,
    so warn as we approach the cliff."""
    import json
    import logging

    caplog.set_level(logging.WARNING, logger="shared.pg_listener")

    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        async with hub.subscribe("chan_a"):
            callback = hub._callbacks["chan_a"]
            padding = "x" * (_NOTIFY_PAYLOAD_WARN_BYTES + 100)
            payload = json.dumps({"event_type": "instance_updated", "blob": padding})
            callback(None, None, "chan_a", payload)

    assert any(
        "large NOTIFY payload" in record.message and "chan_a" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_normal_sized_notify_payload_does_not_warn(hub, mock_conn, caplog):
    import json
    import logging

    caplog.set_level(logging.WARNING, logger="shared.pg_listener")

    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        async with hub.subscribe("chan_a"):
            callback = hub._callbacks["chan_a"]
            payload = json.dumps({"event_type": "instance_updated", "id": "abc"})
            callback(None, None, "chan_a", payload)

    assert not any("large NOTIFY payload" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# disconnect-duration observability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initial_connect_does_not_count_as_disconnect(hub, mock_conn):
    """First-ever connect is not a `reconnect`. Counters stay zero."""
    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        await hub._ensure_connection_locked()
    assert hub.disconnect_count == 0
    assert hub.total_disconnect_seconds == 0.0


@pytest.mark.asyncio
async def test_termination_then_reconnect_records_disconnect_duration(hub, mock_conn):
    """A real disconnect window (termination → reconnect) increments
    `disconnect_count` and adds to `total_disconnect_seconds`."""
    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        await hub._ensure_connection_locked()
        assert hub.disconnect_count == 0

        # Simulate connection death.
        hub._on_termination(mock_conn)
        assert hub._disconnected_at is not None

        # Force the next reconnect to look like time passed.
        hub._disconnected_at -= 0.05

        # Pretend the old connection is closed so reconnect creates a new one.
        hub._conn = None
        await hub._ensure_connection_locked()

    assert hub.disconnect_count == 1
    assert hub.total_disconnect_seconds >= 0.05
    assert hub._disconnected_at is None


@pytest.mark.asyncio
async def test_long_disconnect_logs_warning(hub, mock_conn, caplog):
    """Disconnects over the warn threshold emit a WARNING with the duration
    so an outage is visible in logs even without a metrics stack."""
    import logging

    caplog.set_level(logging.WARNING, logger="shared.pg_listener")

    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        await hub._ensure_connection_locked()
        hub._on_termination(mock_conn)
        # Pretend we've been down for 10 s.
        hub._disconnected_at -= 10.0
        hub._conn = None
        await hub._ensure_connection_locked()

    assert any(
        "reconnected after" in r.message
        and "NOTIFYs during this window were dropped" in r.message
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_short_disconnect_does_not_log_warning(hub, mock_conn, caplog):
    """A sub-threshold blip is INFO, not WARNING — keeps the signal-to-noise
    on the warn level meaningful."""
    import logging

    caplog.set_level(logging.WARNING, logger="shared.pg_listener")

    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        await hub._ensure_connection_locked()
        hub._on_termination(mock_conn)
        # Sub-threshold "blip" of ~10 ms.
        hub._disconnected_at -= 0.01
        hub._conn = None
        await hub._ensure_connection_locked()

    assert not any(
        "NOTIFYs during this window were dropped" in r.message for r in caplog.records
    )


# ---------------------------------------------------------------------------
# fan-out across subscribers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fanout_two_subscribers_both_receive_in_order(hub, mock_conn):
    """Two concurrent subscribers on the same channel both receive every
    NOTIFY, in the order they were emitted. This is the guarantee that the
    SSE list and message streams depend on."""
    import json

    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        async with hub.subscribe("chan_x") as (_w1, q1):
            async with hub.subscribe("chan_x") as (_w2, q2):
                callback = hub._callbacks["chan_x"]
                # Distinct ids so the CoalescingQueue keeps them separate.
                payloads = [
                    json.dumps({"event_type": "instance_updated", "id": f"id-{i}"})
                    for i in range(3)
                ]
                for p in payloads:
                    callback(None, None, "chan_x", p)

                # Both subscribers should now have all three queued, FIFO.
                received1 = q1.drain_nowait()
                received2 = q2.drain_nowait()

    assert received1 == payloads
    assert received2 == payloads


@pytest.mark.asyncio
async def test_fanout_late_subscriber_does_not_receive_earlier_notifies(hub, mock_conn):
    """A subscriber that joined after a NOTIFY does not retroactively see it.
    This documents the no-replay guarantee — clients must re-fetch on
    subscribe if they need pre-subscription state."""
    import json

    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        async with hub.subscribe("chan_y") as (_w1, q1):
            callback = hub._callbacks["chan_y"]
            callback(
                None,
                None,
                "chan_y",
                json.dumps({"event_type": "instance_updated", "id": "early"}),
            )
            # New subscriber joins.
            async with hub.subscribe("chan_y") as (_w2, q2):
                # Only the late subscriber should miss the early event.
                callback(
                    None,
                    None,
                    "chan_y",
                    json.dumps({"event_type": "instance_updated", "id": "late"}),
                )

                received1 = q1.drain_nowait()
                received2 = q2.drain_nowait()

    early = [json.loads(p)["id"] for p in received1]
    late = [json.loads(p)["id"] for p in received2]
    assert early == ["early", "late"]
    assert late == ["late"]


@pytest.mark.asyncio
async def test_fanout_unsubscribe_does_not_affect_other_subscribers(hub, mock_conn):
    """When one subscriber exits, the other must still receive events on the
    same channel. Regression for: the cleanup path accidentally tearing
    down the channel while a sibling is still listening."""
    import json

    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        async with hub.subscribe("chan_z") as (_w_keep, q_keep):
            async with hub.subscribe("chan_z") as (_w_drop, _q_drop):
                pass  # second subscriber exits here

            # First subscriber is still alive — should still get NOTIFYs.
            callback = hub._callbacks["chan_z"]
            callback(
                None,
                None,
                "chan_z",
                json.dumps({"event_type": "instance_updated", "id": "post-exit"}),
            )
            received = q_keep.drain_nowait()

    assert len(received) == 1
    assert json.loads(received[0])["id"] == "post-exit"


# ---------------------------------------------------------------------------
# orphan self-healing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscribe_self_heals_orphaned_channel(hub, mock_conn):
    """An orphaned channel has subscribers in `_subscribers` but no asyncpg
    callback in `_callbacks` — every NOTIFY is silently dropped. A new
    subscribe() must register the missing listener instead of trusting the
    "first subscriber" proxy. Regression for the mass-orphaning bug observed
    in production where 41% of channels lost their callback after a reconnect
    that hit a failure mid-loop."""
    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        # Establish a connection but inject a leaked subscriber pair directly
        # into _subscribers, simulating a prior subscribe whose cleanup never
        # ran. _callbacks deliberately stays empty for this channel.
        await hub._ensure_connection_locked()
        stale_pair = (WakeEvent(), CoalescingQueue())
        hub._subscribers["orphaned_chan"] = {stale_pair}
        assert "orphaned_chan" not in hub._callbacks

        # A fresh subscriber on the orphaned channel must trigger LISTEN.
        async with hub.subscribe("orphaned_chan"):
            assert "orphaned_chan" in hub._callbacks
            mock_conn.add_listener.assert_called_once_with(
                "orphaned_chan", hub._callbacks["orphaned_chan"]
            )


@pytest.mark.asyncio
async def test_subscribe_self_heal_logs_warning(hub, mock_conn, caplog):
    """Self-heal events should be visible in production logs as WARNING so a
    sustained rate after the fix points at a remaining leak source."""
    import logging

    caplog.set_level(logging.WARNING, logger="shared.pg_listener")

    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        await hub._ensure_connection_locked()
        hub._subscribers["orphaned_chan"] = {(WakeEvent(), CoalescingQueue())}

        async with hub.subscribe("orphaned_chan"):
            pass

    assert any(
        "self-healing orphaned channel" in r.message and "orphaned_chan" in r.message
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_subscribe_first_time_does_not_log_self_heal(hub, mock_conn, caplog):
    """A normal first-subscribe path is INFO/silent — only a true self-heal
    (existing subscribers + missing callback) should trip the WARNING."""
    import logging

    caplog.set_level(logging.WARNING, logger="shared.pg_listener")

    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        async with hub.subscribe("fresh_chan"):
            pass

    assert not any("self-healing orphaned channel" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# reconnect resilience to per-channel failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconnect_continues_past_single_channel_failure(hub, mock_conn):
    """One bad channel during re-LISTEN must not abandon every channel
    iterated after it. Regression for the early-return bug where a single
    add_listener failure left every subsequent channel without a callback."""
    with patch("asyncpg.connect", new=AsyncMock(return_value=mock_conn)):
        async with hub.subscribe("chan_a"):
            async with hub.subscribe("chan_b"):
                async with hub.subscribe("chan_c"):
                    # Force the reconnect: drop conn + callbacks, then make
                    # the middle channel's add_listener fail. The first call
                    # below is the new connect's own attempts.
                    hub._conn = None
                    hub._callbacks.clear()
                    mock_conn.add_listener.reset_mock()

                    async def add_listener_with_failure(channel, _cb):
                        if channel == "chan_b":
                            raise RuntimeError("simulated PG error")

                    mock_conn.add_listener.side_effect = add_listener_with_failure
                    await hub._ensure_connection_locked()

                    # chan_a and chan_c must still be registered despite
                    # chan_b failing. Order of iteration is dict-insertion
                    # order, so chan_c comes after the failure.
                    listened = [c[0][0] for c in mock_conn.add_listener.call_args_list]
                    assert "chan_a" in listened
                    assert "chan_c" in listened
