"""Constructed-fixture suite for the `fetch_messages_request` catch-up query.

`fetch_session_messages` is the server-side catch-up SELECT behind the
`fetch_messages_request` WS frame (websocket-migration §4 Phase 3, §2.6). Its
failure mode is silent message loss, so it gets a dedicated suite with
hand-controlled `created_at` values rather than relying on wiring tests.

These tests hit a real database, so they are marked `integration`.
"""

from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from servers.api.ws_handler import handle_fetch_messages_request
from servers.shared.db.queries import create_user_message, fetch_session_messages
from shared.database.enums import SenderType
from shared.database.models import AgentInstance, Message, User, UserAgent
from shared.database.session import SessionLocal
from shared.websocket import Connection

pytestmark = pytest.mark.integration

BASE = datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc)

# A message-spec is (content, created_at, sender_type, message_id).
MessageSpec = tuple[str, datetime, SenderType, UUID]


@pytest.fixture
def session_instance() -> Iterator[tuple[UUID, UUID]]:
    """A persisted agent instance with no messages; yields (user_id, instance_id)."""
    user_id, agent_id, instance_id = uuid4(), uuid4(), uuid4()
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.add(UserAgent(id=agent_id, user_id=user_id, name=f"agent-{agent_id}"))
        db.add(AgentInstance(id=instance_id, user_agent_id=agent_id, user_id=user_id))
        db.commit()
    try:
        yield user_id, instance_id
    finally:
        with SessionLocal() as db:
            db.query(Message).filter(Message.agent_instance_id == instance_id).delete()
            db.query(AgentInstance).filter(AgentInstance.id == instance_id).delete()
            db.query(UserAgent).filter(UserAgent.id == agent_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()


@pytest.fixture
def add_messages() -> Callable[[UUID, list[tuple]], list[UUID]]:
    """Insert messages with controlled created_at; returns their ids in order."""

    def _add(instance_id: UUID, specs: list[tuple]) -> list[UUID]:
        ids: list[UUID] = []
        with SessionLocal() as db:
            for spec in specs:
                content, created_at = spec[0], spec[1]
                sender = spec[2] if len(spec) > 2 else SenderType.USER
                msg_id = spec[3] if len(spec) > 3 else uuid4()
                db.add(
                    Message(
                        id=msg_id,
                        agent_instance_id=instance_id,
                        sender_type=sender,
                        content=content,
                        created_at=created_at,
                        requires_user_input=False,
                    )
                )
                ids.append(msg_id)
            db.commit()
        return ids

    return _add


def test_watermark_fetch_returns_user_messages_after_the_watermark(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
) -> None:
    _user_id, instance_id = session_instance
    add_messages(
        instance_id,
        [
            ("m1", BASE + timedelta(minutes=1)),
            ("m2", BASE + timedelta(minutes=2)),
            ("m3", BASE + timedelta(minutes=3)),
        ],
    )

    with SessionLocal() as db:
        result = fetch_session_messages(
            db, instance_id, after={"created_at": BASE.isoformat(), "id": None}
        )

    assert [row["content"] for row in result.rows] == ["m1", "m2", "m3"]
    assert result.has_more is False
    assert result.resync_reason is None


def test_reconnect_refetches_both_messages_of_an_identical_timestamp_pair(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
) -> None:
    # Two messages share a created_at; the client received one and
    # disconnected before the other. A created_at-only watermark must
    # re-fetch both so the missed one is recovered (§2.6).
    _user_id, instance_id = session_instance
    shared_ts = BASE + timedelta(minutes=5)
    add_messages(
        instance_id,
        [("first", shared_ts), ("second", shared_ts)],
    )

    with SessionLocal() as db:
        result = fetch_session_messages(
            db,
            instance_id,
            after={"created_at": shared_ts.isoformat(), "id": None},
        )

    assert sorted(row["content"] for row in result.rows) == ["first", "second"]


def test_commit_order_inversion_is_recovered_by_the_safety_window(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
) -> None:
    # `inverted` was created before `newest` but committed after it, so a
    # client streaming live updates advanced its watermark to `newest` and
    # never saw `inverted`. The `>= watermark - safety_window` re-fetch
    # recovers it (§2.6 watermark-vs-cursor).
    _user_id, instance_id = session_instance
    newest = BASE + timedelta(minutes=10)
    inverted = newest - timedelta(seconds=5)
    add_messages(instance_id, [("newest", newest), ("inverted", inverted)])

    with SessionLocal() as db:
        result = fetch_session_messages(
            db,
            instance_id,
            after={"created_at": newest.isoformat(), "id": None},
        )

    assert {row["content"] for row in result.rows} == {"newest", "inverted"}


def test_pagination_cursor_returns_only_messages_strictly_after_it(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
) -> None:
    # When `after` carries an `id`, it is a pagination cursor (continuing a
    # has_more response), not a reconnect watermark: strict (created_at, id) >,
    # no safety-window re-fetch (§2.6 watermark-vs-cursor).
    _user_id, instance_id = session_instance
    ids = add_messages(
        instance_id,
        [
            ("m1", BASE + timedelta(minutes=1)),
            ("m2", BASE + timedelta(minutes=2)),
            ("m3", BASE + timedelta(minutes=3)),
            ("m4", BASE + timedelta(minutes=4)),
        ],
    )

    with SessionLocal() as db:
        result = fetch_session_messages(
            db,
            instance_id,
            after={
                "created_at": (BASE + timedelta(minutes=2)).isoformat(),
                "id": str(ids[1]),
            },
        )

    assert [row["content"] for row in result.rows] == ["m3", "m4"]


def test_pagination_cursor_for_a_missing_message_requests_resync(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
) -> None:
    # The client's pagination cursor names a message that does not exist for
    # this instance — its catch-up state cannot be served, so the server
    # tells it to drop local state and re-fetch (§2.6 resync escape hatch).
    _user_id, instance_id = session_instance
    add_messages(instance_id, [("m1", BASE + timedelta(minutes=1))])

    with SessionLocal() as db:
        result = fetch_session_messages(
            db,
            instance_id,
            after={"created_at": BASE.isoformat(), "id": str(uuid4())},
        )

    assert result.resync_reason == "missing_history"
    assert result.rows == []
    assert result.has_more is False


def test_tail_fetch_with_no_watermark_returns_all_user_messages(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
) -> None:
    # A resync re-fetch carries no watermark: the client dropped local state
    # and wants the tail of history (§2.6 resync escape hatch).
    _user_id, instance_id = session_instance
    add_messages(
        instance_id,
        [
            ("a", BASE + timedelta(minutes=1)),
            ("b", BASE + timedelta(minutes=2)),
            ("c", BASE + timedelta(minutes=3)),
        ],
    )

    with SessionLocal() as db:
        result = fetch_session_messages(db, instance_id, after=None)

    assert [row["content"] for row in result.rows] == ["a", "b", "c"]
    assert result.resync_reason is None


def test_session_scoped_no_watermark_resumes_from_instance_last_read(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
) -> None:
    # `vicoa --resume` (and any wrapper cold start) opens a fresh WS with
    # no in-memory watermark. Returning the full user-message tail would
    # re-inject every historical user message into the PTY, freezing Claude.
    # `instance.last_read_message_id` is advanced server-side every time the
    # wrapper produces an agent reply, so it is the authoritative cursor for
    # "wrapper has already processed up to here" — fall back to it on
    # cold-start catch-up.
    _user_id, instance_id = session_instance
    ids = add_messages(
        instance_id,
        [
            ("u1", BASE + timedelta(minutes=1)),
            ("u2", BASE + timedelta(minutes=2)),
            ("u3", BASE + timedelta(minutes=3)),
        ],
    )

    with SessionLocal() as db:
        instance = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        instance.last_read_message_id = ids[1]  # wrapper processed up to u2
        db.commit()

        result = fetch_session_messages(db, instance_id, after=None)

    assert [row["content"] for row in result.rows] == ["u3"]
    assert result.resync_reason is None


def test_session_scoped_no_watermark_returns_nothing_when_caught_up(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
) -> None:
    # Normal `vicoa` start: `_setup()` sends a session-start agent message
    # before the WS connects, which advances `last_read_message_id` to that
    # agent message's id. The WS catch-up that follows must return zero
    # rows — otherwise old user messages would flow into the PTY behind the
    # first agent send.
    _user_id, instance_id = session_instance
    ids = add_messages(
        instance_id,
        [
            ("u1", BASE + timedelta(minutes=1), SenderType.USER),
            ("session-start", BASE + timedelta(minutes=2), SenderType.AGENT),
        ],
    )

    with SessionLocal() as db:
        instance = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        instance.last_read_message_id = ids[1]
        db.commit()

        result = fetch_session_messages(db, instance_id, after=None)

    assert result.rows == []


@pytest.mark.parametrize("mark_as_read,recovered", [(True, False), (False, True)])
def test_initial_prompt_is_recoverable_only_when_it_does_not_mark_itself_read(
    session_instance: tuple[UUID, UUID],
    mark_as_read: bool,
    recovered: bool,
) -> None:
    # A wrapper POSTs its initial prompt and then waits for the row to come
    # back over the WS. When the subscription is not attached yet the live
    # broadcast is missed, leaving the cold-start catch-up (`after=None`) as
    # the only delivery leg — including the 10s reconcile backstop, which
    # replays the same query.
    #
    # `mark_as_read=True` points `last_read_message_id` at the row just
    # created, and this fallback selects strictly `created_at > cursor`, so
    # the prompt excludes *itself*: both legs miss it and the session hangs
    # (c0d25529-…, 6h+ idle). Leaving the cursor alone makes catch-up recover
    # it. Pins the reason `mark_as_read=False` is load-bearing at the three
    # wrapper POST sites (see test_initial_prompt_catch_up.py).
    user_id, instance_id = session_instance

    with SessionLocal() as db:
        create_user_message(
            db,
            agent_instance_id=str(instance_id),
            content="the initial prompt",
            user_id=str(user_id),
            mark_as_read=mark_as_read,
        )
        db.commit()

        result = fetch_session_messages(db, instance_id, after=None)

    assert [row["content"] for row in result.rows] == (
        ["the initial prompt"] if recovered else []
    )


def test_unread_prompt_recovery_does_not_replay_processed_history(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
) -> None:
    # The flip side of the test above: not marking the prompt read must not
    # widen the catch-up back over turns the wrapper already ran. On a
    # `--resume` the cursor still sits on the last processed message, so the
    # fallback returns the prompt and nothing older.
    user_id, instance_id = session_instance
    ids = add_messages(
        instance_id,
        [
            ("u1", BASE + timedelta(minutes=1), SenderType.USER),
            ("agent-reply", BASE + timedelta(minutes=2), SenderType.AGENT),
        ],
    )

    with SessionLocal() as db:
        instance = db.query(AgentInstance).filter(AgentInstance.id == instance_id).one()
        instance.last_read_message_id = ids[1]  # wrapper replied to u1
        create_user_message(
            db,
            agent_instance_id=str(instance_id),
            content="resume prompt",
            user_id=str(user_id),
            mark_as_read=False,
        )
        db.commit()

        result = fetch_session_messages(db, instance_id, after=None)

    assert [row["content"] for row in result.rows] == ["resume prompt"]


def test_pagination_through_a_single_timestamp_neither_skips_nor_loops(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
) -> None:
    # Five messages share one created_at — more than fits in a page. The
    # (created_at, id) pagination cursor must walk all of them exactly once.
    _user_id, instance_id = session_instance
    shared_ts = BASE + timedelta(minutes=7)
    add_messages(instance_id, [(f"m{i}", shared_ts) for i in range(5)])

    seen: list[str] = []
    after: dict | None = {"created_at": shared_ts.isoformat(), "id": None}
    for _ in range(10):  # bound: a loop would otherwise never terminate
        with SessionLocal() as db:
            result = fetch_session_messages(db, instance_id, after=after, page_limit=2)
        seen.extend(row["content"] for row in result.rows)
        if not result.has_more:
            break
        last = result.rows[-1]
        after = {"created_at": last["created_at"], "id": last["id"]}

    assert sorted(seen) == ["m0", "m1", "m2", "m3", "m4"]  # no skip
    assert len(seen) == len(set(seen))  # no loop / no duplicate


def _session_conn(user_id: UUID, instance_id: UUID) -> Connection:
    return Connection(
        connection_id=uuid4().hex,
        user_id=str(user_id),
        scope="session-scoped",
        rooms=frozenset({f"user:{user_id}:session:{instance_id}"}),
    )


def _user_scoped_conn(user_id: UUID) -> Connection:
    return Connection(
        connection_id=uuid4().hex,
        user_id=str(user_id),
        scope="user-scoped",
        rooms=frozenset({f"user:{user_id}:user-scoped"}),
    )


def test_user_scoped_catch_up_returns_user_and_agent_messages(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
) -> None:
    # vicoa-web / vicoa-app chat pages connect user-scoped and need the full
    # conversation on reconnect. Without `include_agent_messages`, any AGENT
    # message written during the WS disconnect window is silently lost from
    # the catch-up path (live broadcast carries both, but a connected client
    # that missed the live frame has only this fetch to recover it).
    _user_id, instance_id = session_instance
    add_messages(
        instance_id,
        [
            ("u1", BASE + timedelta(minutes=1), SenderType.USER),
            ("a1", BASE + timedelta(minutes=2), SenderType.AGENT),
            ("u2", BASE + timedelta(minutes=3), SenderType.USER),
            ("a2", BASE + timedelta(minutes=4), SenderType.AGENT),
        ],
    )

    with SessionLocal() as db:
        result = fetch_session_messages(
            db,
            instance_id,
            after={"created_at": BASE.isoformat(), "id": None},
            include_agent_messages=True,
        )

    assert [row["content"] for row in result.rows] == ["u1", "a1", "u2", "a2"]


def test_session_scoped_catch_up_stays_user_only(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
) -> None:
    # The CLI wrapper is session-scoped and *produces* the AGENT side of the
    # conversation; sending those rows back on every catch-up would waste
    # bandwidth and memory for no consumer benefit. Locks the legacy
    # USER-only behavior for this scope so a future "make defaults uniform"
    # refactor cannot quietly regress wrapper traffic.
    _user_id, instance_id = session_instance
    add_messages(
        instance_id,
        [
            ("u1", BASE + timedelta(minutes=1), SenderType.USER),
            ("a1", BASE + timedelta(minutes=2), SenderType.AGENT),
            ("u2", BASE + timedelta(minutes=3), SenderType.USER),
        ],
    )

    with SessionLocal() as db:
        result = fetch_session_messages(
            db,
            instance_id,
            after={"created_at": BASE.isoformat(), "id": None},
        )

    assert [row["content"] for row in result.rows] == ["u1", "u2"]


async def test_handler_routes_by_scope_for_agent_messages(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
) -> None:
    # End-to-end: user-scoped handler gets both senders; session-scoped gets
    # USER only. Guards the wiring between `Connection.scope` and the query
    # — the previous version dropped AGENT rows on all callers.
    user_id, instance_id = session_instance
    add_messages(
        instance_id,
        [
            ("u1", BASE + timedelta(minutes=1), SenderType.USER),
            ("a1", BASE + timedelta(minutes=2), SenderType.AGENT),
        ],
    )

    frame = {
        "type": "fetch_messages_request",
        "request_id": "f1",
        "instance_id": str(instance_id),
        "after": {"created_at": BASE.isoformat(), "id": None},
    }

    user_response = await handle_fetch_messages_request(
        _user_scoped_conn(user_id), frame
    )
    session_response = await handle_fetch_messages_request(
        _session_conn(user_id, instance_id), frame
    )

    assert [row["content"] for row in user_response["rows"]] == ["u1", "a1"]
    assert [row["content"] for row in session_response["rows"]] == ["u1"]


async def test_handler_answers_fetch_request_for_an_owned_instance(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
) -> None:
    user_id, instance_id = session_instance
    add_messages(instance_id, [("hi", BASE + timedelta(minutes=1))])

    response = await handle_fetch_messages_request(
        _session_conn(user_id, instance_id),
        {
            "type": "fetch_messages_request",
            "request_id": "f1",
            "instance_id": str(instance_id),
            "after": {"created_at": BASE.isoformat(), "id": None},
        },
    )

    assert response["type"] == "fetch_messages_response"
    assert response["request_id"] == "f1"
    assert response["instance_id"] == str(instance_id)
    assert [row["content"] for row in response["rows"]] == ["hi"]
    assert response["has_more"] is False


async def test_handler_does_not_serve_an_instance_the_connection_lacks(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
) -> None:
    # A connection authenticated as another user must not read this
    # instance's messages — the routing key is the verified token's user.
    _owner_id, instance_id = session_instance
    add_messages(instance_id, [("secret", BASE + timedelta(minutes=1))])
    intruder = _session_conn(uuid4(), instance_id)

    response = await handle_fetch_messages_request(
        intruder,
        {
            "type": "fetch_messages_request",
            "request_id": "f2",
            "instance_id": str(instance_id),
            "after": {"created_at": BASE.isoformat(), "id": None},
        },
    )

    assert response["type"] == "fetch_messages_response"
    assert response["rows"] == []


async def test_handler_emits_resync_required_when_the_cursor_is_missing(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
) -> None:
    user_id, instance_id = session_instance
    add_messages(instance_id, [("m1", BASE + timedelta(minutes=1))])

    response = await handle_fetch_messages_request(
        _session_conn(user_id, instance_id),
        {
            "type": "fetch_messages_request",
            "request_id": "f3",
            "instance_id": str(instance_id),
            "after": {"created_at": BASE.isoformat(), "id": str(uuid4())},
        },
    )

    assert response["type"] == "resync_required"
    assert response["request_id"] == "f3"
    assert response["entity"] == "messages"
    assert response["reason"] == "missing_history"


def test_ws_round_trip_answers_a_fetch_messages_request(
    session_instance: tuple[UUID, UUID],
    add_messages: Callable[[UUID, list[tuple]], list[UUID]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # End-to-end over a real socket: the receive loop must dispatch a
    # fetch_messages_request frame and send the response back out.
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from servers.api import ws_handler
    from shared.auth.tokens import TokenClaims

    user_id, instance_id = session_instance
    add_messages(instance_id, [("ping", BASE + timedelta(minutes=1))])
    monkeypatch.setattr(
        ws_handler,
        "verify_user_token",
        lambda _token: TokenClaims(user_id=user_id),
    )

    app = FastAPI()
    app.include_router(ws_handler.ws_router)
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws", subprotocols=["vicoa-ws", "vicoa-supabase.h.p.s"]
        ) as ws:
            ws.send_json(
                {
                    "type": "hello",
                    "scope": "session-scoped",
                    "instance_id": str(instance_id),
                }
            )
            assert ws.receive_json()["type"] == "server_info"
            ws.send_json(
                {
                    "type": "fetch_messages_request",
                    "request_id": "rt1",
                    "instance_id": str(instance_id),
                    "after": {"created_at": BASE.isoformat(), "id": None},
                }
            )
            response = ws.receive_json()

    assert response["type"] == "fetch_messages_response"
    assert response["request_id"] == "rt1"
    assert [row["content"] for row in response["rows"]] == ["ping"]
