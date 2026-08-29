"""WebSocket `/ws` endpoint and the internal broadcast receiver (Phase 1).

Connect flow (websocket-migration plan §4 Phase 1):

  1. read credentials from the `Sec-WebSocket-Protocol` subprotocols
  2. allowlist the browser `Origin` (§2.9)
  3. verify the token (Supabase JWT, or custom RS256 agent JWT)
  4. accept, echoing the non-credential marker subprotocol
  5. read the `hello` frame and resolve scope + room
  6. ownership-check session/machine scopes against the DB (§2.9)
  7. register the connection, send `server_info`
  8. run the outbox / receive / ping loops until disconnect, then unregister

This router is only mounted when `settings.enable_websocket` is true — i.e. on
the dedicated `vicoa-server` app, not the legacy SSE-only `server` process.
"""

import asyncio
import hmac
import logging
import time
from collections.abc import Callable
from uuid import UUID, uuid4

import sentry_sdk
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketState

from shared.auth import (
    TokenVerificationError,
    verify_agent_jwt,
    verify_user_token,
)
from shared.auth.ws import (
    WsAuthError,
    WsCredentials,
    is_origin_allowed,
    parse_ws_subprotocol_credentials,
)
from shared.config import settings
from shared.database.models import AgentInstance, Machine, User
from shared.database.session import SessionLocal
from shared.websocket.connection_manager import Connection, connection_manager
from shared.websocket.protocol import (
    ResolvedHello,
    WsProtocolError,
    resolve_hello,
    terminal_room,
)
from shared.websocket.rpc import RpcError, rpc_router
from servers.shared.db.queries import (
    FetchMessagesResult,
    fetch_session_messages,
    fetch_user_instances,
    fetch_user_machines,
    push_recent_directory_after_spawn,
)

logger = logging.getLogger(__name__)

ws_router = APIRouter()

SERVER_VERSION = "1.0.0"
PING_INTERVAL_SECONDS = 30.0
HELLO_TIMEOUT_SECONDS = 10.0

# WebSocket close codes, private-use 4000-4999 range.
_CLOSE_UNAUTHORIZED = 4401
_CLOSE_PROTOCOL = 4400
_CLOSE_FORBIDDEN = 4403
# RFC 6455 policy violation — used when the manager sheds a slow consumer
# because its outbox is full (websocket-migration §2.10 backpressure).
_CLOSE_SLOW_CONSUMER = 1008


async def _safe_close(websocket: WebSocket, *, code: int, reason: str = "") -> None:
    """Close a WebSocket, swallowing a benign double-close but still reporting a
    genuinely-unexpected close failure.

    A connection has several *uncoordinated* server-side close paths — overflow
    (1008), ping-loop missed-pong (4400), and the credential-revoke push (4401,
    fired by `/_internal/close_user` when a user is deleted). Each is scheduled
    fire-and-forget with `asyncio.create_task`, so they race: when one wins, a
    later one runs against an already-closed socket and Starlette raises
    `RuntimeError: Cannot call "send" once a close message has been sent.`. That
    is the *desired* end state, not an error — skip it via the DISCONNECTED
    guard, or swallow it if a path wins the race between the guard and close(),
    without paging Sentry (PYTHON-FLASK-2K).

    The broad `except` remains for the real failure this was written for: the
    legacy `websockets` backend used by uvicorn can raise AttributeError
    (`'WebSocketProtocol' object has no attribute 'transfer_data_task'`) when
    close() runs against a connection whose TCP died early. Letting that
    propagate leaves the WebSocketProtocol half-closed — the asyncio task
    and transport leak onto the event loop, eventually starving accept() on
    the listen socket (the 2026-06-04 vicoa-server wedge).
    """
    if websocket.application_state == WebSocketState.DISCONNECTED:
        # Another close path already won; the socket is in the desired state.
        return
    try:
        await websocket.close(code=code, reason=reason)
    except RuntimeError:
        # A concurrent close path won the race between the guard above and
        # here. Benign: the socket is already closed, which is what we wanted.
        logger.debug("WS already closed (code=%s); concurrent close path won", code)
    except Exception:
        logger.exception("WS close raised (code=%s); transport may leak", code)
        sentry_sdk.capture_exception()


def verify_ws_credentials(creds: WsCredentials) -> str:
    """Verify a parsed credential and return its user_id, or raise WsAuthError.

    The subprotocol says which kind of credential was offered, and each kind is
    checked against its own issuer — a browser session cannot be presented as an
    agent key or vice versa.
    """
    if creds.token_type == "vicoa-supabase":
        try:
            return str(verify_user_token(creds.raw_token).user_id)
        except TokenVerificationError as exc:
            raise WsAuthError(f"user token rejected: {exc}") from exc

    # vicoa-key: the Vicoa-issued RS256 agent API key.
    try:
        return str(verify_agent_jwt(creds.raw_token).user_id)
    except TokenVerificationError as exc:
        raise WsAuthError(f"agent token rejected: {exc}") from exc


def is_owned(db: Session, resolved: ResolvedHello, user_id: str) -> bool:
    """Whether the hello's session/machine row belongs to the user (§2.9).

    Without this an agent-token holder could open a session-scoped connection
    with someone else's instance_id and receive their messages.
    """
    try:
        owner = UUID(user_id)
        target = UUID(resolved.instance_id or resolved.machine_id or "")
    except (ValueError, TypeError):
        return False
    if resolved.scope == "session-scoped":
        row = (
            db.query(AgentInstance.id)
            .filter(AgentInstance.id == target, AgentInstance.user_id == owner)
            .first()
        )
    else:
        row = (
            db.query(Machine.id)
            .filter(Machine.id == target, Machine.user_id == owner)
            .first()
        )
    return row is not None


def _user_exists(db: Session, user_id: str) -> bool:
    """PK lookup, sub-ms. Only called on the ownership-check failure path —
    so it pays nothing on the happy path. Lets the WS handler distinguish
    "user gone entirely" (close 4401, daemon goes fatal-auth) from "row
    not owned by this user" (close 4403, ownership protocol failure).
    See plans/bugs/p0-agent-jwt-no-db-validation.md."""
    try:
        owner = UUID(user_id)
    except (ValueError, TypeError):
        return False
    return db.query(User.id).filter(User.id == owner).first() is not None


def _fetch_messages_blocking(
    user_id: str,
    instance_id_raw: object,
    after: dict | None,
    scope: str,
) -> FetchMessagesResult | None:
    """Ownership check + catch-up SELECT. Returns None if the connection's user
    does not own the instance — the routing key is the verified token's user.

    `scope` selects the AGENT-message policy: user-scoped (web / mobile chat)
    needs the full conversation; session-scoped (CLI wrapper) keeps USER-only
    so a daemon doesn't re-receive its own outbound on every catch-up.
    """
    try:
        instance_id = UUID(str(instance_id_raw))
        owner_id = UUID(user_id)
    except (ValueError, TypeError):
        return None
    with SessionLocal() as db:
        owned = (
            db.query(AgentInstance.id)
            .filter(
                AgentInstance.id == instance_id,
                AgentInstance.user_id == owner_id,
            )
            .first()
        )
        if owned is None:
            return None
        return fetch_session_messages(
            db,
            instance_id,
            after,
            include_agent_messages=(scope == "user-scoped"),
        )


async def handle_fetch_messages_request(conn: Connection, frame: dict) -> dict:
    """Answer a `fetch_messages_request` with a response or a resync frame.

    The catch-up SELECT runs in a worker thread so a slow query never stalls
    the shared single event loop (§2.10).
    """
    request_id = frame.get("request_id")
    instance_id = frame.get("instance_id")
    result = await asyncio.to_thread(
        _fetch_messages_blocking,
        conn.user_id,
        instance_id,
        frame.get("after"),
        conn.scope,
    )
    if result is None:
        # Return empty rows rather than an error to avoid leaking ownership
        # information over the wire. The warning below is sufficient for
        # internal observability.
        logger.warning(
            "WS %s fetch for unowned instance %s",
            conn.connection_id,
            instance_id,
        )
        return {
            "type": "fetch_messages_response",
            "request_id": request_id,
            "instance_id": instance_id,
            "rows": [],
            "has_more": False,
        }
    if result.resync_reason is not None:
        return {
            "type": "resync_required",
            "request_id": request_id,
            "entity": "messages",
            "instance_id": instance_id,
            "reason": result.resync_reason,
        }
    return {
        "type": "fetch_messages_response",
        "request_id": request_id,
        "instance_id": instance_id,
        "rows": result.rows,
        "has_more": result.has_more,
    }


def _fetch_user_entities_blocking(
    fetch_fn: Callable[[Session, UUID, str | None], list[dict]],
    user_id: str,
    updated_after: str | None,
) -> list[dict]:
    """Run a user-wide entity catch-up SELECT off the event loop.

    The connection's verified `user_id` is the only scoping — a user-scoped
    catch-up cannot reach another user's rows.
    """
    try:
        owner = UUID(user_id)
    except (ValueError, TypeError):
        return []
    with SessionLocal() as db:
        return fetch_fn(db, owner, updated_after)


async def handle_fetch_instances_request(conn: Connection, frame: dict) -> dict:
    """Answer a `fetch_instances_request` with the user's agent instances."""
    rows = await asyncio.to_thread(
        _fetch_user_entities_blocking,
        fetch_user_instances,
        conn.user_id,
        frame.get("updated_after"),
    )
    return {
        "type": "fetch_instances_response",
        "request_id": frame.get("request_id"),
        "rows": rows,
    }


async def handle_fetch_machines_request(conn: Connection, frame: dict) -> dict:
    """Answer a `fetch_machines_request` with the user's machines."""
    rows = await asyncio.to_thread(
        _fetch_user_entities_blocking,
        fetch_user_machines,
        conn.user_id,
        frame.get("updated_after"),
    )
    return {
        "type": "fetch_machines_response",
        "request_id": frame.get("request_id"),
        "rows": rows,
    }


async def handle_rpc_call(conn: Connection, frame: dict) -> None:
    """Route a client's `rpc-call` to the owning daemon and return the result.

    Runs as its own task — `rpc_router.call` awaits the daemon for up to the
    timeout, which must not block the caller connection's receive loop.
    """
    request_id = frame.get("request_id")
    machine_id = str(frame.get("machine_id"))
    method = str(frame.get("method"))
    params = frame.get("params") or {}
    try:
        result = await rpc_router.call(conn.user_id, machine_id, method, params)
        conn.enqueue({"type": "rpc-result", "request_id": request_id, "result": result})
        # Mirror the legacy HTTP spawn-session side effect: when the web/CLI
        # spawns a session through the daemon, push the directory onto the
        # machine's recent_directories so the new-session picker shows it
        # next time.
        if (
            method == "spawn-session"
            and isinstance(result, dict)
            and not result.get("error")
        ):
            directory = params.get("directory")
            if isinstance(directory, str) and directory.strip():
                try:
                    push_recent_directory_after_spawn(
                        conn.user_id, machine_id, directory.strip()
                    )
                except Exception:  # noqa: BLE001 — best-effort post-spawn update
                    logger.exception(
                        "failed to update recent_directories after spawn-session"
                    )
    except RpcError as exc:
        if exc.code == "no_handler":
            logger.warning(
                "rpc-call no_handler: user=%s machine=%s method=%s "
                "(daemon not connected for this routing key)",
                conn.user_id,
                machine_id,
                method,
            )
        conn.enqueue({"type": "rpc-error", "request_id": request_id, "code": exc.code})


async def _serve_connection(websocket: WebSocket, conn: Connection) -> None:
    """Run the receive loop, with the outbox and ping loops in the background.

    The receive loop is the driver: when the client disconnects it raises
    `WebSocketDisconnect`, which unwinds this function and cancels the
    background loops. `drain_outbox` is the sole owner of `websocket.send` —
    the ping loop enqueues onto the outbox rather than sending directly.
    """
    last_pong = time.monotonic()

    async def drain_outbox() -> None:
        while True:
            frame = await conn.outbox.get()
            await websocket.send_json(frame)

    async def ping_loop() -> None:
        while True:
            await asyncio.sleep(PING_INTERVAL_SECONDS)
            if time.monotonic() - last_pong > 2 * PING_INTERVAL_SECONDS:
                logger.info("WS %s missed pongs; closing", conn.connection_id)
                await _safe_close(websocket, code=_CLOSE_PROTOCOL)
                return
            conn.enqueue({"type": "ping"})

    background = [
        asyncio.create_task(drain_outbox()),
        asyncio.create_task(ping_loop()),
    ]
    # In-flight rpc-call tasks: tracked so they are cancelled on disconnect and
    # do not stall the receive loop while awaiting a daemon (§2.8).
    rpc_tasks: set[asyncio.Task] = set()
    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")
            if msg_type == "pong":
                last_pong = time.monotonic()
            elif msg_type == "fetch_messages_request":
                conn.enqueue(await handle_fetch_messages_request(conn, message))
            elif msg_type == "fetch_instances_request":
                conn.enqueue(await handle_fetch_instances_request(conn, message))
            elif msg_type == "fetch_machines_request":
                conn.enqueue(await handle_fetch_machines_request(conn, message))
            elif msg_type == "presence":
                # Desktop app reporting its window foreground/blur. Recorded on
                # the connection and read at push time by
                # `is_desktop_foreground` to suppress FCM phone push while the
                # user is looking at the desktop app (mirrors the desktop
                # banner's "only when unfocused" behavior, but for the phone).
                connection_manager.record_presence(
                    conn, bool(message.get("foreground"))
                )
            elif msg_type == "rpc-register":
                # Only a daemon (machine-scoped) may serve RPC handlers; the
                # routing key is its own machine (§2.8).
                method = message.get("method")
                if conn.scope == "machine-scoped" and conn.machine_id and method:
                    rpc_router.register(
                        conn.user_id, conn.machine_id, str(method), conn
                    )
                    logger.info(
                        "WS %s registered RPC handler: user=%s machine=%s method=%s",
                        conn.connection_id,
                        conn.user_id,
                        conn.machine_id,
                        method,
                    )
                else:
                    logger.warning(
                        "WS %s rejected rpc-register: scope=%s machine_id=%s method=%r",
                        conn.connection_id,
                        conn.scope,
                        conn.machine_id,
                        method,
                    )
            elif msg_type == "rpc-call":
                task = asyncio.create_task(handle_rpc_call(conn, message))
                rpc_tasks.add(task)
                task.add_done_callback(rpc_tasks.discard)
            elif msg_type == "rpc-response":
                rpc_router.resolve(
                    str(message.get("corr_id")), message.get("result") or {}
                )
            elif msg_type in ("pty-output", "pty-exit"):
                # A daemon streaming a remote terminal's output/exit. Only a
                # machine-scoped (daemon) connection may push these; relay them
                # verbatim to that machine's terminal room, where the viewing
                # client is subscribed (terminal-scoped). Cross-user isolation
                # is the `user:{uid}:…` room prefix built from the daemon's own
                # authenticated user_id.
                if conn.scope == "machine-scoped" and conn.machine_id:
                    if msg_type == "pty-output":
                        frame = {
                            "type": "pty-output",
                            "pty_id": message.get("pty_id"),
                            "data": message.get("data"),
                        }
                    else:
                        frame = {
                            "type": "pty-exit",
                            "pty_id": message.get("pty_id"),
                            "exit_code": message.get("exit_code"),
                        }
                    connection_manager.broadcast_frame(
                        [terminal_room(conn.user_id, conn.machine_id)], frame
                    )
    except WebSocketDisconnect:
        pass
    except RuntimeError as exc:
        # Starlette raises RuntimeError (not WebSocketDisconnect) from
        # `receive_json` after a server-initiated close — the ping loop or the
        # slow-consumer overflow callback closed the socket while the receive
        # loop was awaiting the next frame. Normal teardown, not an error.
        logger.info("WS %s receive after server close: %s", conn.connection_id, exc)
    except ValueError as exc:
        # `receive_json` raises ValueError on non-JSON / non-text frames. The
        # connection is unrecoverable from here (the loop has no state machine
        # to skip the bad frame), but the client otherwise sees a silent drop —
        # log so a malformed sender is debuggable from the server side.
        logger.warning("WS %s closing on malformed frame: %s", conn.connection_id, exc)
    finally:
        for task in background:
            task.cancel()
        for task in rpc_tasks:
            task.cancel()


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """The single WebSocket endpoint for web, mobile, CLI wrappers, and daemons."""
    # --- authenticate before accepting the handshake ---
    try:
        creds = parse_ws_subprotocol_credentials(
            websocket.scope.get("subprotocols", [])
        )
        # Origin allowlist applies to browser (Supabase) connections only —
        # daemons and CLI wrappers use vicoa-key and have no malicious-site
        # vector (§2.9). Daemon HTTP clients send a default `Origin` we have
        # no reason to require to be on the web allowlist.
        if creds.token_type == "vicoa-supabase" and not is_origin_allowed(
            websocket.headers.get("origin"), settings.frontend_urls
        ):
            raise WsAuthError("origin not allowlisted")
        # Off the event loop: verification can touch the database (the API-key
        # revocation check) and, on a Supabase deployment without local key
        # material, the network. Blocking here would stall every other
        # connection on this worker.
        user_id = await asyncio.to_thread(verify_ws_credentials, creds)
    except WsAuthError as exc:
        logger.info("WS handshake rejected: %s", exc)
        await _safe_close(websocket, code=_CLOSE_UNAUTHORIZED)
        return

    await websocket.accept(subprotocol=creds.echo_subprotocol)

    # --- hello handshake ---
    try:
        hello = await asyncio.wait_for(
            websocket.receive_json(), timeout=HELLO_TIMEOUT_SECONDS
        )
    except WebSocketDisconnect:
        logger.info("WS client disconnected during hello handshake")
        return
    except (TimeoutError, ValueError):
        await _safe_close(websocket, code=_CLOSE_PROTOCOL)
        return
    try:
        resolved = resolve_hello(hello, user_id=user_id, token_type=creds.token_type)
    except WsProtocolError as exc:
        logger.info("WS hello rejected: %s", exc)
        await _safe_close(websocket, code=_CLOSE_PROTOCOL)
        return

    # --- ownership check for session/machine scopes (§2.9) ---
    if resolved.scope in ("session-scoped", "machine-scoped"):
        with SessionLocal() as db:
            owned = is_owned(db, resolved, user_id)
            # When ownership fails, distinguish "user gone" from "wrong
            # owner" so the daemon's WS client can stop reconnecting on
            # 4401 (credential revoked) without misinterpreting a real
            # ownership mistake (4403) as fatal-auth. Extra PK lookup
            # only runs on the failure path — same one-time cost as
            # Phase 1b would have charged on heartbeats, but at WS
            # handshake frequency instead of every-30s heartbeat.
            user_alive = True if owned else _user_exists(db, user_id)
        if not owned:
            if user_alive:
                logger.info("WS ownership check failed for %s", resolved.scope)
                await _safe_close(websocket, code=_CLOSE_FORBIDDEN)
            else:
                logger.info(
                    "WS user gone for %s — closing with credential_revoked",
                    resolved.scope,
                )
                await _safe_close(
                    websocket,
                    code=_CLOSE_UNAUTHORIZED,
                    reason="credential_revoked",
                )
            return

    # --- register, announce, serve ---
    # The on_overflow callback (§2.10 backpressure) schedules the close on
    # the running event loop: ConnectionManager fans out synchronously and
    # cannot await `websocket.close(...)` itself. The close raises a
    # WebSocketDisconnect into the receive loop, which unwinds via the
    # existing finally and unregisters cleanly — no extra cleanup path.
    def _on_overflow() -> None:
        try:
            asyncio.create_task(
                _safe_close(
                    websocket, code=_CLOSE_SLOW_CONSUMER, reason="slow_consumer"
                )
            )
        except RuntimeError:
            # No running loop (e.g. broadcaster called from a sync context
            # outside the server's loop). Manager already logged + counted.
            pass

    # Mirrors _on_overflow for the revocation path. Triggered by
    # ConnectionManager.close_user() when `backend` POSTs
    # `/_internal/close_user` after a `delete_user_account` commit. Sends
    # 4401 so the daemon's WS client interprets it as fatal-auth (same code
    # as a handshake-time auth failure), goes through the existing CLI
    # AuthenticationError path, and stops reconnecting.
    def _on_revoked() -> None:
        try:
            asyncio.create_task(
                _safe_close(
                    websocket, code=_CLOSE_UNAUTHORIZED, reason="credential_revoked"
                )
            )
        except RuntimeError:
            pass

    conn = Connection(
        connection_id=uuid4().hex,
        user_id=user_id,
        scope=resolved.scope,
        rooms=frozenset({resolved.room}),
        machine_id=resolved.machine_id,
        on_overflow=_on_overflow,
        on_revoked=_on_revoked,
    )
    connection_manager.register(conn)
    try:
        await websocket.send_json(
            {
                "type": "server_info",
                "body": {"server_version": SERVER_VERSION, "user_id": user_id},
            }
        )
        await _serve_connection(websocket, conn)
    except WebSocketDisconnect:
        # Client dropped between accept and the server_info send — nothing to
        # serve; the finally below unregisters.
        logger.info("WS %s client disconnected before server_info", conn.connection_id)
    finally:
        connection_manager.unregister(conn)
        # Drop this daemon's RPC handlers and fail its in-flight calls (§2.8).
        # A no-op for non-daemon connections.
        rpc_router.unregister(conn)


class _InternalBroadcastBody(BaseModel):
    """Body shape for the §2.11 cross-process broadcast bridge.

    Used purely for shape validation — a malformed POST returns 422 instead
    of raising `KeyError` from a raw `body["..."]` lookup (which turns into
    an opaque 500 the bridge sender's metric can't distinguish from real
    receiver failures).
    """

    user_id: str
    payload: dict
    rooms: list[str]


@ws_router.post("/_internal/broadcast", include_in_schema=False)
async def internal_broadcast(body: _InternalBroadcastBody, request: Request) -> dict:
    """Cross-process broadcast bridge receiver (websocket-migration §2.11).

    `backend` POSTs here after a write commits so user-scoped WS clients on
    `server` get the realtime update. Token-gated: this route is reachable
    from the public internet, so the bearer token is the security boundary.
    """
    expected = settings.internal_broadcast_token
    provided = request.headers.get("authorization", "")
    if not expected or not hmac.compare_digest(provided, f"Bearer {expected}"):
        raise HTTPException(status_code=401, detail="unauthorized")

    connection_manager.broadcast_update(body.user_id, body.payload, body.rooms)
    return {"ok": True}


class _InternalCloseUserBody(BaseModel):
    """Body shape for the cross-process credential-revoke bridge.

    Same shape contract as `_InternalBroadcastBody` — Pydantic validation gives
    422 on malformed POSTs instead of opaque 500s. Carries only the user_id
    because the close target is "every WS connection owned by this user."
    """

    user_id: str


@ws_router.post("/_internal/close_user", include_in_schema=False)
async def internal_close_user(body: _InternalCloseUserBody, request: Request) -> dict:
    """Cross-process credential-revoke bridge receiver.

    `backend` POSTs here after `delete_user_account` commits so the daemon's
    WS connection (and any other live WS clients owned by that user) is closed
    with 4401 "credential_revoked" — instead of waiting for the daemon's next
    REST call to surface a 401 via PR #45's reactive bouncer. Token-gated for
    the same reason `/_internal/broadcast` is.
    """
    expected = settings.internal_broadcast_token
    provided = request.headers.get("authorization", "")
    if not expected or not hmac.compare_digest(provided, f"Bearer {expected}"):
        raise HTTPException(status_code=401, detail="unauthorized")

    closed = connection_manager.close_user(body.user_id)
    return {"ok": True, "closed": closed}
