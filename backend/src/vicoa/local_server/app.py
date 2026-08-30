"""The local FastAPI app: WebSocket + REST subset on ``127.0.0.1``.

Frame grammar and REST shapes mirror the cloud servers exactly (see
``servers/api/ws_handler.py`` and ``servers/api/routers.py`` /
``backend/api/agents.py``); parity is the whole point — the web renderer and
the headless SDK run unchanged against this app in local-only mode.

Auth is a per-launch nonce:

* WebSocket — offered subprotocols must carry ``vicoa-local.<nonce>`` (the
  renderer) or ``vicoa-key.<nonce>`` (the headless child's session WS client,
  which received the nonce as its ``VICOA_API_KEY``); bad credential closes
  4401. A present ``Origin`` header must equal the allowed origin.
* REST — ``Authorization: Bearer <nonce>`` on everything except ``/healthz``.

Nonce comparisons are constant-time (``hmac.compare_digest``).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hmac
import logging
import platform as platform_module
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable
from urllib.parse import urlsplit

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

from protocol.agent_catalog import AGENT_CATALOG_ETAG, AGENT_CATALOG_JSON

from .envelopes import build_machine_update_body
from .rpc import LocalRpcDispatcher
from .store import (
    InstanceConflictError,
    InstanceNotFoundError,
    LocalStore,
    StoredInstance,
    StoredMessage,
    utc_now_iso,
)
from integrations.cli_wrappers.claude_code.command_sync import scan_agent_commands
from vicoa.file_sync import scan_project_files
from vicoa.terminal.rpc import PTY_ORDERED_METHODS
from vicoa.terminal.service import TerminalService

logger = logging.getLogger(__name__)

SERVER_VERSION = "1.0.0"
# Sane cap on the @-mention scan so a huge working tree can't return a
# multi-megabyte JSON body over the local socket (the cloud CLI syncs up to
# 100k; the renderer only needs enough to fuzzy-match against).
FILE_MENTIONS_MAX = 20_000
PING_INTERVAL_SECONDS = 30.0
HELLO_TIMEOUT_SECONDS = 10.0
OUTBOX_MAX_FRAMES = 4096

_CLOSE_UNAUTHORIZED = 4401
_CLOSE_PROTOCOL = 4400
_CLOSE_FORBIDDEN = 4403
_CLOSE_SLOW_CONSUMER = 1008

_MARKER_SUBPROTOCOL = "vicoa-ws"
_LOCAL_PREFIX = "vicoa-local."
_KEY_PREFIX = "vicoa-key."

# localhost / 127.0.0.1 / [::1] all address this same machine. The Electron
# renderer may load from any of these spellings depending on how the shell
# resolved the loopback host, so an exact-string Origin match would reject a
# perfectly-local connection (e.g. window on `localhost`, allowed origin on
# `127.0.0.1`). Treat all loopback spellings at the same scheme+port as one.
_LOOPBACK_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1"})


def _loopback_origin_variants(origin: str) -> list[str]:
    """Every loopback spelling of ``origin`` at its scheme+port. A non-loopback
    origin is returned unchanged (as a single-element list)."""
    try:
        parts = urlsplit(origin)
    except ValueError:
        return [origin]
    if parts.hostname not in _LOOPBACK_HOSTNAMES:
        return [origin]
    port = f":{parts.port}" if parts.port is not None else ""
    return [
        f"{parts.scheme}://{'[::1]' if host == '::1' else host}{port}"
        for host in _LOOPBACK_HOSTNAMES
    ]


# Stable pseudo user id for the single local user (server_info parity — the
# cloud frame carries the authenticated user's id).
LOCAL_USER_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "vicoa-local-user"))

LOCAL_MACHINE_ID = "local"

# Stable synthetic subscription id for the local free-plan billing stub
# (billing/subscription parity — the cloud returns the row's UUID).
LOCAL_SUBSCRIPTION_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "vicoa-local-subscription"))

# Mirrors shared.config settings.free_plan_agent_limit (default 10); local-only
# mode has no real subscription, so it always reports the free tier.
LOCAL_FREE_AGENT_LIMIT = 10


class CloudAuthStatus:
    """Cloud-auth state shared between the daemon thread and ``/healthz``.

    The runner creates one per credentialed desktop launch and hands ``set``
    to the daemon as its ``on_cloud_status`` callback; the local server
    thread reads ``value`` when serving ``/healthz`` so the tray can
    distinguish starting / connected / auth_failed. Values: ``"connecting"``
    (initial), ``"connected"`` (registration succeeded), ``"auth_failed"``
    (fatal auth — see ``MachineDaemon._handle_fatal_auth``).
    """

    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTH_FAILED = "auth_failed"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value = self.CONNECTING

    def set(self, value: str) -> None:
        with self._lock:
            self._value = value

    @property
    def value(self) -> str:
        with self._lock:
            return self._value


# ----------------------------------------------------------------------
# Connection registry / broadcast hub
# ----------------------------------------------------------------------
# eq=False keeps identity semantics (and hashability) for the registry set.
@dataclass(eq=False)
class _LocalConnection:
    connection_id: str
    scope: str
    instance_id: str | None
    outbox: asyncio.Queue = field(
        default_factory=lambda: asyncio.Queue(maxsize=OUTBOX_MAX_FRAMES)
    )
    on_overflow: Callable[[], None] | None = None

    def enqueue(self, frame: dict) -> None:
        try:
            self.outbox.put_nowait(frame)
        except asyncio.QueueFull:
            logger.warning(
                "local WS %s outbox full; shedding slow consumer",
                self.connection_id,
            )
            if self.on_overflow is not None:
                self.on_overflow()


class LocalBroadcastHub:
    """Fans frames out to every connected local socket.

    ``broadcast_threadsafe`` is callable from any thread (store listeners run
    on FastAPI's threadpool; terminal callbacks on PTY reader threads) — it
    hops onto the server's event loop via ``call_soon_threadsafe``.
    """

    def __init__(self) -> None:
        self._connections: set[_LocalConnection] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def register(self, conn: _LocalConnection) -> None:
        self._connections.add(conn)

    def unregister(self, conn: _LocalConnection) -> None:
        self._connections.discard(conn)

    def _broadcast_on_loop(self, frame: dict) -> None:
        for conn in list(self._connections):
            conn.enqueue(frame)

    def broadcast_threadsafe(self, frame: dict) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            logger.debug("local WS broadcast dropped (server loop not running)")
            return
        loop.call_soon_threadsafe(self._broadcast_on_loop, frame)


# ----------------------------------------------------------------------
# App factory
# ----------------------------------------------------------------------
def create_local_app(
    *,
    daemon: Any,
    store: LocalStore,
    nonce: str,
    allowed_origin: str,
    local_only: bool,
    terminal: TerminalService,
    cloud_status: CloudAuthStatus | None = None,
) -> FastAPI:
    """Build the local server app.

    ``daemon`` is the ``MachineDaemon`` handle (typed loosely to keep this
    module import-light); the app uses its ``_handle_rpc_request`` /
    ``_supported_rpc_methods`` / ``_detect_available_agents`` / ``machine_id``.
    ``cloud_status`` is the shared cloud-auth status object in credentialed
    mode (None in local-only mode, where ``/healthz`` reports ``cloud: null``).
    """
    hub = LocalBroadcastHub()
    # A single dedicated worker for order-sensitive pty input
    # (write/resize/kill). The renderer pipelines these fire-and-forget, so —
    # unlike the parallel default thread pool `asyncio.to_thread` uses — they
    # must apply in receive order or two fast keystrokes could reorder. Local
    # RTT is ~0, but reordering is about concurrency, not latency, so this
    # guard is needed here too. Everything else stays on the default pool.
    pty_input_executor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="vicoa-local-pty-input"
    )

    @asynccontextmanager
    async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Capture the server loop so store/terminal threads can broadcast
        # onto it; tear the PTY sessions down with the server.
        hub.set_loop(asyncio.get_running_loop())
        try:
            yield
        finally:
            await asyncio.to_thread(terminal.shutdown)
            pty_input_executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(
        title="vicoa-local", docs_url=None, redoc_url=None, lifespan=_lifespan
    )
    # Accept the allowed origin under any loopback spelling (localhost /
    # 127.0.0.1 / [::1]) — same machine, so the exact host the renderer sends
    # must not gate REST or the WS handshake below.
    allowed_origins = _loopback_origin_variants(allowed_origin)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    dispatcher = LocalRpcDispatcher(
        daemon_dispatch=daemon._handle_rpc_request,
        daemon_methods=daemon._supported_rpc_methods(),
        terminal=terminal,
    )
    server_started_at = utc_now_iso()
    hostname = platform_module.node()[:255]
    # Read only in local-only mode — both consumers (`GET /api/v1/machines`,
    # `fetch_machines_request`) return empty in cloud mode, and local-only is
    # currently disabled in the runner. The `scan-agents` RPC deliberately
    # does NOT invalidate this: it re-detects from scratch, so its own answer
    # is never stale, and plumbing an invalidation hook through the dispatcher
    # for an unreachable path isn't worth the seam. If local-only is ever
    # re-enabled, scan-agents must `available_agents_cache.pop("agents", None)` or
    # this synthetic machine body will keep serving the boot-time probe.
    available_agents_cache: dict[str, dict[str, bool]] = {}

    store.add_listener(
        lambda payload: hub.broadcast_threadsafe({"type": "update", "payload": payload})
    )
    terminal.bind(
        on_output=lambda pty_id, data: hub.broadcast_threadsafe(
            {
                "type": "pty-output",
                "pty_id": pty_id,
                "data": base64.b64encode(data).decode("ascii"),
            }
        ),
        on_exit=lambda pty_id, exit_code: hub.broadcast_threadsafe(
            {"type": "pty-exit", "pty_id": pty_id, "exit_code": exit_code}
        ),
    )

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------
    def _nonce_matches(candidate: str) -> bool:
        return hmac.compare_digest(candidate, nonce)

    def require_nonce(request: Request) -> None:
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer ") or not _nonce_matches(header[7:]):
            raise HTTPException(status_code=401, detail="unauthorized")

    def _parse_ws_credentials(
        offered: list[str],
    ) -> tuple[bool, str | None, str | None]:
        """(authorized, echo_subprotocol, kind) from the offered subprotocols.

        ``kind`` is ``"local"`` for the ``vicoa-local.`` subprotocol (the
        Electron renderer — a browser context) or ``"key"`` for ``vicoa-key.``
        (the headless agent / SDK — a trusted local process holding the nonce).
        """
        candidates = [p.strip() for p in offered if p.strip()]
        echo = _MARKER_SUBPROTOCOL if _MARKER_SUBPROTOCOL in candidates else None
        for candidate in candidates:
            for prefix, kind in ((_LOCAL_PREFIX, "local"), (_KEY_PREFIX, "key")):
                if candidate.startswith(prefix) and _nonce_matches(
                    candidate[len(prefix) :]
                ):
                    return True, echo, kind
        return False, echo, None

    async def _safe_close(websocket: WebSocket, *, code: int) -> None:
        if websocket.application_state == WebSocketState.DISCONNECTED:
            return
        try:
            await websocket.close(code=code)
        except RuntimeError:
            logger.debug("local WS already closed (code=%s)", code)
        except Exception:
            logger.exception("local WS close raised (code=%s)", code)

    # ------------------------------------------------------------------
    # Synthetic machine (local-only mode)
    # ------------------------------------------------------------------
    def _available_agents() -> dict[str, bool]:
        cached = available_agents_cache.get("agents")
        if cached is None:
            try:
                cached = daemon._detect_available_agents()
            except Exception:
                logger.exception("local server: agent detection failed")
                cached = {}
            available_agents_cache["agents"] = cached
        return cached

    def _machine_metadata() -> dict:
        return {
            "available_agents": _available_agents(),
            "capabilities": daemon._capabilities(),
            "local_only": True,
        }

    def _synthetic_machine_body() -> dict:
        return build_machine_update_body(
            machine_id=LOCAL_MACHINE_ID,
            display_name=hostname,
            hostname=hostname,
            platform=platform_module.platform()[:255],
            home_dir=str(Path.home()),
            last_heartbeat_at=utc_now_iso(),
            machine_metadata=_machine_metadata(),
            created_at=server_started_at,
            updated_at=utc_now_iso(),
        )

    # ------------------------------------------------------------------
    # REST response shaping (mirrors backend/servers response models)
    # ------------------------------------------------------------------
    def _message_response(msg: StoredMessage, *, renderer: bool) -> dict:
        body = {
            "id": msg.id,
            "content": msg.content,
            "sender_type": msg.sender_type,
            "created_at": msg.created_at,
            "requires_user_input": msg.requires_user_input,
            "message_metadata": msg.message_metadata,
        }
        if renderer:
            # backend.models.MessageResponse carries sender identity fields.
            body.update(
                {
                    "sender_user_id": msg.sender_user_id,
                    "sender_user_email": None,
                    "sender_user_display_name": None,
                }
            )
        return body

    def _register_response(inst: StoredInstance) -> dict:
        return {
            "agent_instance_id": inst.id,
            "agent_type_id": inst.user_agent_id,
            "agent_type_name": inst.agent_type_name,
            "status": inst.status,
            "name": inst.name,
            "instance_metadata": inst.instance_metadata,
            "project": inst.project,
            "home_dir": inst.home_dir,
            "machine_id": inst.machine_id,
            "session_config": inst.session_config,
        }

    def _from_metadata(inst: StoredInstance, key: str) -> str | None:
        """Promote a metadata key to a top-level field.

        Mirrors AgentInstanceResponse's model_validator on the cloud backend —
        this server hand-builds its dicts, so the promotion is explicit here.
        """
        if isinstance(inst.instance_metadata, dict):
            value = inst.instance_metadata.get(key)
            if value is not None:
                return str(value)
        return None

    def _instance_list_item(
        inst: StoredInstance, latest: StoredMessage | None, chat_length: int
    ) -> dict:
        return {
            "id": inst.id,
            "agent_type_id": inst.user_agent_id,
            "agent_type_name": inst.agent_type_name,
            "name": inst.name,
            "status": inst.status,
            "started_at": inst.started_at,
            "ended_at": inst.ended_at,
            "latest_message": latest.content if latest else None,
            "latest_message_at": latest.created_at if latest else None,
            "chat_length": chat_length,
            "last_heartbeat_at": inst.last_heartbeat_at,
            "instance_metadata": inst.instance_metadata,
            "session_config": inst.session_config,
            "project": inst.project,
            "home_dir": inst.home_dir,
            "machine_id": inst.machine_id,
            "pinned_at": inst.pinned_at,
            "source": _from_metadata(inst, "source"),
            "worktree_name": _from_metadata(inst, "worktree_name"),
        }

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    @app.get("/healthz")
    def healthz() -> dict:
        machine_id = LOCAL_MACHINE_ID if local_only else daemon.machine_id
        if local_only:
            cloud = None
        elif cloud_status is not None:
            cloud = cloud_status.value
        else:
            # Credentialed mode without a wired status object (shouldn't
            # happen via the runner) — report the pre-registration state.
            cloud = CloudAuthStatus.CONNECTING
        return {
            "status": "ok",
            "mode": "local-only" if local_only else "cloud",
            "machine_id": machine_id,
            "cloud": cloud,
        }

    # ------------------------------------------------------------------
    # Renderer REST subset
    # ------------------------------------------------------------------
    @app.get("/api/v1/agent-instances")
    def list_agent_instances(
        request: Request, limit: int = 50, offset: int = 0
    ) -> dict:
        require_nonce(request)
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        rows, total = store.list_instances(limit=limit, offset=offset)
        items = [
            _instance_list_item(inst, latest, count) for inst, latest, count in rows
        ]
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(items) < total,
        }

    @app.get("/api/v1/agent-instances/{instance_id}")
    def get_agent_instance(
        request: Request,
        instance_id: str,
        message_limit: int = 50,
        before_message_id: str | None = None,
    ) -> dict:
        require_nonce(request)
        inst = store.get_instance(instance_id)
        if inst is None or inst.status == "DELETED":
            raise HTTPException(status_code=404, detail="Agent instance not found")
        messages = store.get_instance_messages(
            instance_id,
            message_limit=message_limit,
            before_message_id=before_message_id,
        )
        return {
            "id": inst.id,
            "agent_type_id": inst.user_agent_id,
            "agent_type_name": inst.agent_type_name,
            "name": inst.name,
            "status": inst.status,
            "started_at": inst.started_at,
            "ended_at": inst.ended_at,
            "git_diff": inst.git_diff,
            "messages": [_message_response(msg, renderer=True) for msg in messages],
            "last_read_message_id": inst.last_read_message_id,
            "last_heartbeat_at": inst.last_heartbeat_at,
            "access_level": "WRITE",
            "is_owner": True,
            "instance_metadata": inst.instance_metadata,
            "session_config": inst.session_config,
            "project": inst.project,
            "home_dir": inst.home_dir,
            "machine_id": inst.machine_id,
            "worktree_name": _from_metadata(inst, "worktree_name"),
        }

    @app.post("/api/v1/agent-instances/{instance_id}/messages")
    def post_instance_message(request: Request, instance_id: str, body: dict) -> dict:
        require_nonce(request)
        content = body.get("content")
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(status_code=400, detail="content is required")
        try:
            # mark_as_read=False (cloud parity): the message stays pending so
            # the headless agent's /messages/pending poll delivers it.
            message = store.add_user_message(
                agent_instance_id=instance_id,
                content=content,
                mark_as_read=False,
                sender_user_id=LOCAL_USER_ID,
            )
        except InstanceNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail="Agent instance not found"
            ) from exc
        return _message_response(message, renderer=True)

    @app.get("/api/v1/machines")
    def list_machines(request: Request) -> dict:
        require_nonce(request)
        if not local_only:
            # Logged-in desktop uses the cloud machine list; the local socket
            # only carries RPC there.
            return {"machines": []}
        return {
            "machines": [
                {
                    "machine_id": LOCAL_MACHINE_ID,
                    "display_name": hostname,
                    "hostname": hostname,
                    "platform": platform_module.platform()[:255],
                    "home_dir": str(Path.home()),
                    "last_heartbeat_at": utc_now_iso(),
                    "metadata": _machine_metadata(),
                    "recent_directories": store.recent_directories(),
                }
            ]
        }

    # ------------------------------------------------------------------
    # Chat-input helpers: @-mention files + slash commands + new-session
    # catalog (renderer). Shapes mirror the cloud backend routes exactly
    # (backend.api.file_mentions / slash_commands / agents / machines) so the
    # renderer parses them unchanged; sources are computed live off this
    # machine instead of read from the synced DB tables.
    # ------------------------------------------------------------------
    @app.get("/api/v1/files")
    def get_file_mentions(request: Request, project_path: str | None = None) -> dict:
        """@-mention file list for ``project_path`` (FileMentionsResponse shape).

        The cloud endpoint returns whatever the CLI synced — the output of
        ``scan_project_files`` (folders + files as forward-slash paths relative
        to the project, honouring nested .gitignore and the default excludes).
        Here we run that same scan live against the on-disk project, so the
        shape and ignore rules match exactly. Missing / non-directory paths
        scan to an empty list rather than erroring.
        """
        require_nonce(request)
        if not project_path:
            return {"project_path": "", "files": [], "file_count": 0}
        files = scan_project_files(project_path, max_files=FILE_MENTIONS_MAX)
        return {
            "project_path": project_path,
            "files": files,
            "file_count": len(files),
        }

    def _slash_commands_body(agent_type: str) -> dict:
        """SlashCommandsResponse for ``agent_type`` (backend.api.slash_commands).

        The cloud endpoint returns whatever the CLI synced into the
        ``slash_commands`` table; here the same scanner runs live
        (``scan_agent_commands`` — Claude's and Codex's command/skill dirs).
        Agents without a local source return an empty command list (still a
        valid, non-404 response).
        """
        try:
            scanned = scan_agent_commands(agent_type)
        except Exception:  # noqa: BLE001 - scan is best-effort; never 500
            logger.exception("local server: slash-command scan failed")
            scanned = {}
        commands = [
            {"name": name, **{k: str(v) for k, v in details.items()}}
            for name, details in scanned.items()
        ]
        return {"agent_type": agent_type, "commands": commands}

    @app.get("/api/v1/commands/{agent_type}")
    def get_commands_for_agent(request: Request, agent_type: str) -> dict:
        require_nonce(request)
        return _slash_commands_body(agent_type)

    @app.get("/api/v1/commands")
    def list_slash_commands(
        request: Request, agent_type: str | None = None
    ) -> list[dict]:
        require_nonce(request)
        # Mirror the cloud list endpoint (one entry per agent type that has
        # commands). An agent without a local source scans empty, matching
        # "no synced record".
        body = _slash_commands_body(agent_type or "claude")
        return [body] if body["commands"] else []

    @app.get("/api/v1/agent-catalog")
    def get_agent_catalog(
        request: Request, if_none_match: str | None = Header(default=None)
    ) -> Response:
        """Static agent / model / permission catalog (new-session picker).

        Byte-identical to the cloud route (backend.api.agents): both serve
        ``protocol.agent_catalog``. ETag + conditional GET are honoured so the
        renderer's 304 short-circuit works locally too.
        """
        require_nonce(request)
        if if_none_match == AGENT_CATALOG_ETAG:
            return Response(status_code=304)
        return Response(
            content=AGENT_CATALOG_JSON,
            media_type="application/json",
            headers={
                "ETag": AGENT_CATALOG_ETAG,
                "Cache-Control": "private, max-age=3600",
            },
        )

    @app.get("/api/v1/machines/{machine_id}/agent-models")
    def get_machine_agent_models(request: Request, machine_id: str) -> dict:
        """Cached per-agent ACP model lists for a machine.

        There is no local ACP model cache, so this is always the empty
        ``{"agent_models": {}}`` shape (matches
        backend.api.machines MachineAgentModelsResponse). The renderer falls
        back to the catalog's default models, which is the correct behaviour
        until an ACP agent has actually run here.
        """
        require_nonce(request)
        return {"agent_models": {}}

    # ------------------------------------------------------------------
    # Auth + billing stubs (renderer parity in local-only mode)
    # These endpoints back cloud-only concerns (Supabase identity sync, Stripe
    # billing) that have no meaning without a login. The renderer still calls
    # them on dashboard load, so we answer 200 with the shape it expects
    # instead of 404ing (which surfaced "Failed to sync user" and console
    # noise). Registered unconditionally so cloud mode also never 500s.
    # ------------------------------------------------------------------
    @app.post("/api/v1/auth/sync-user")
    def sync_user(request: Request, body: dict | None = None) -> dict:
        """Reconcile the renderer's Supabase user (mirrors backend ``sync_user``).

        Local-only mode has a single synthetic user (:data:`LOCAL_USER_ID`) and
        no Supabase identity to validate, so the ``{id, email, display_name}``
        body is accepted and ignored — the per-launch nonce is the credential.
        Returns the backend's exact success body so the renderer's ``syncUser``
        resolves instead of raising "Failed to sync user".
        """
        require_nonce(request)
        return {"message": "User synced successfully"}

    @app.get("/api/v1/billing/subscription")
    def get_billing_subscription(request: Request) -> dict:
        """Free-plan subscription (mirrors backend ``SubscriptionResponse``).

        There is no billing in local-only mode; return a valid free-tier row so
        the renderer's ``getBillingSubscription`` parses a real
        ``BillingSubscription`` (it already ``.catch()``es failures, but 404
        noise is worse). ``provider: null`` marks it as un-monetized.
        """
        require_nonce(request)
        return {
            "id": LOCAL_SUBSCRIPTION_ID,
            "plan_type": "free",
            "agent_limit": LOCAL_FREE_AGENT_LIMIT,
            "current_period_end": None,
            "cancel_at_period_end": False,
            "provider": None,
        }

    # ------------------------------------------------------------------
    # SDK REST subset (headless agent → local server)
    # ------------------------------------------------------------------
    @app.post("/api/v1/agent-instances", status_code=201)
    def register_agent_instance(request: Request, body: dict) -> dict:
        require_nonce(request)
        agent_type = body.get("agent_type")
        if not isinstance(agent_type, str) or not agent_type.strip():
            raise HTTPException(status_code=400, detail="agent_type is required")
        session_config = body.get("session_config")
        try:
            inst = store.register_instance(
                agent_type=agent_type,
                agent_instance_id=body.get("agent_instance_id") or None,
                name=body.get("name") or None,
                project=body.get("project") or None,
                home_dir=body.get("home_dir") or None,
                transport=body.get("transport") or None,
                source=body.get("source") or None,
                worktree_name=body.get("worktree_name") or None,
                machine_id=body.get("machine_id") or LOCAL_MACHINE_ID,
                session_config=session_config
                if isinstance(session_config, dict)
                else None,
            )
        except InstanceConflictError as exc:
            raise HTTPException(
                status_code=409, detail="Agent instance already exists"
            ) from exc
        return _register_response(inst)

    @app.put("/api/v1/agent-instances/{instance_id}/status")
    def put_instance_status(request: Request, instance_id: str, body: dict) -> dict:
        require_nonce(request)
        if "status" not in body:
            raise HTTPException(status_code=400, detail="Status field is required")
        try:
            inst = store.update_instance_status(instance_id, str(body["status"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except InstanceNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail="Agent instance not found"
            ) from exc
        return {"success": True, "instance_id": inst.id, "status": inst.status}

    @app.patch("/api/v1/agent-instances/{instance_id}")
    def patch_agent_instance(request: Request, instance_id: str, body: dict) -> dict:
        require_nonce(request)
        session_config = body.get("session_config")
        try:
            inst = store.patch_instance(
                instance_id,
                name=body.get("name") if isinstance(body.get("name"), str) else None,
                session_config_merge=session_config
                if isinstance(session_config, dict)
                else None,
            )
        except InstanceNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail="Agent instance not found"
            ) from exc
        return _register_response(inst)

    @app.delete("/api/v1/agent-instances/{instance_id}")
    def delete_agent_instance(request: Request, instance_id: str) -> dict:
        """Delete a session (mirrors backend ``delete_agent_instance``).

        Soft-deletes the instance and wipes its messages via the store, which
        broadcasts an ``instance-update`` (DELETED) so live renderers drop the
        row; the renderer also refetches afterwards, so the sidebar clears
        either way. Returns the backend's exact body/status (200 +
        ``{"message": ...}``) and 404s an unknown id.

        Note: the daemon's ``spawn-session`` launches a detached, thread-
        monitored ``Popen`` with no instance-id → process registry, so there is
        no tracked child to force-kill here. An orphaned headless child is
        harmless: its later message posts land on the ``DELETED`` row and stay
        hidden (see ``LocalStore.delete_instance``).
        """
        require_nonce(request)
        try:
            store.delete_instance(instance_id)
        except InstanceNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail="Agent instance not found"
            ) from exc
        return {"message": "Agent instance deleted successfully"}

    @app.post("/api/v1/messages/agent")
    def post_agent_message(request: Request, body: dict) -> dict:
        require_nonce(request)
        agent_instance_id = body.get("agent_instance_id")
        content = body.get("content")
        if not isinstance(agent_instance_id, str) or not agent_instance_id:
            raise HTTPException(status_code=400, detail="agent_instance_id is required")
        if not isinstance(content, str):
            raise HTTPException(status_code=400, detail="content is required")
        metadata = body.get("message_metadata")
        try:
            message, instance, queued = store.add_agent_message(
                agent_instance_id=agent_instance_id,
                content=content,
                agent_type=body.get("agent_type") or None,
                requires_user_input=bool(body.get("requires_user_input")),
                message_metadata=metadata if isinstance(metadata, dict) else None,
                git_diff=_maybe_decode_base64(body.get("git_diff")),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "success": True,
            "agent_instance_id": instance.id,
            "message_id": message.id,
            "queued_user_messages": [
                _message_response(msg, renderer=False) for msg in queued
            ],
        }

    @app.post("/api/v1/messages/user")
    def post_user_message(request: Request, body: dict) -> dict:
        require_nonce(request)
        agent_instance_id = body.get("agent_instance_id")
        content = body.get("content")
        if not isinstance(agent_instance_id, str) or not isinstance(content, str):
            raise HTTPException(
                status_code=400, detail="agent_instance_id and content are required"
            )
        mark_as_read = bool(body.get("mark_as_read", True))
        try:
            message = store.add_user_message(
                agent_instance_id=agent_instance_id,
                content=content,
                mark_as_read=mark_as_read,
                sender_user_id=LOCAL_USER_ID,
            )
        except InstanceNotFoundError as exc:
            raise HTTPException(
                status_code=400, detail="Agent instance not found"
            ) from exc
        return {
            "success": True,
            "message_id": message.id,
            "marked_as_read": mark_as_read,
        }

    @app.get("/api/v1/messages/pending")
    def get_pending_messages(
        request: Request,
        agent_instance_id: str,
        last_read_message_id: str | None = None,
    ) -> dict:
        require_nonce(request)
        try:
            messages, status = store.pending_messages(
                agent_instance_id, last_read_message_id or None
            )
        except InstanceNotFoundError as exc:
            raise HTTPException(
                status_code=400, detail="Agent instance not found"
            ) from exc
        return {
            "agent_instance_id": agent_instance_id,
            "messages": [_message_response(msg, renderer=False) for msg in messages],
            "status": status,
        }

    @app.patch("/api/v1/messages/{message_id}/request-input")
    def request_user_input(request: Request, message_id: str) -> dict:
        require_nonce(request)
        try:
            instance_id, queued, status = store.mark_message_requires_input(message_id)
        except InstanceNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail="Agent message not found or access denied"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "success": True,
            "message_id": message_id,
            "agent_instance_id": instance_id,
            "messages": [_message_response(msg, renderer=False) for msg in queued],
            "status": status,
        }

    @app.post("/api/v1/sessions/end")
    def end_session(request: Request, body: dict) -> dict:
        require_nonce(request)
        agent_instance_id = body.get("agent_instance_id")
        if not isinstance(agent_instance_id, str) or not agent_instance_id:
            raise HTTPException(status_code=400, detail="agent_instance_id is required")
        try:
            inst = store.end_session(agent_instance_id)
        except InstanceNotFoundError as exc:
            raise HTTPException(
                status_code=400, detail="Agent instance not found"
            ) from exc
        return {
            "success": True,
            "agent_instance_id": inst.id,
            "final_status": inst.status,
        }

    @app.post("/api/v1/commands/sync")
    def sync_commands(request: Request, body: dict) -> dict:
        require_nonce(request)
        # Accepted and dropped: slash-command sync has no local consumer yet,
        # but the headless child calls it at startup and 404 noise is worse.
        commands = body.get("commands")
        count = len(commands) if isinstance(commands, dict) else 0
        return {"success": True, "synced_count": count}

    @app.post("/api/v1/files/sync")
    def sync_files(request: Request, body: dict) -> dict:
        require_nonce(request)
        files = body.get("files")
        count = len(files) if isinstance(files, list) else 0
        return {"success": True, "synced_count": count}

    @app.get("/api/v1/attachments/{attachment_id}")
    def download_attachment(request: Request, attachment_id: str) -> dict:
        require_nonce(request)
        raise HTTPException(
            status_code=404, detail="Attachments are not stored in local-only mode"
        )

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        offered = list(websocket.scope.get("subprotocols", []))
        authorized, echo, kind = _parse_ws_credentials(offered)
        if not authorized:
            logger.info("local WS handshake rejected: bad or missing nonce")
            await _safe_close(websocket, code=_CLOSE_UNAUTHORIZED)
            return
        # Enforce the Origin allowlist ONLY for the renderer (`vicoa-local.`),
        # which runs in a browser context and sends a truthful, unspoofable
        # Origin. The headless agent / SDK connect with `vicoa-key.` from a
        # non-browser process: websocket-client stamps a loopback Origin
        # (http://127.0.0.1:<port>) that a remote page cannot forge, and the
        # per-launch nonce is the real credential — so those connections are
        # Origin-exempt (mirrors the cloud server, where daemons send no Origin).
        if kind == "local":
            origin = websocket.headers.get("origin")
            if origin is not None and origin not in allowed_origins:
                logger.info("local WS rejected: origin %r not allowed", origin)
                await _safe_close(websocket, code=_CLOSE_FORBIDDEN)
                return

        await websocket.accept(subprotocol=echo)

        try:
            hello = await asyncio.wait_for(
                websocket.receive_json(), timeout=HELLO_TIMEOUT_SECONDS
            )
        except WebSocketDisconnect:
            logger.info("local WS client disconnected during hello handshake")
            return
        except (TimeoutError, ValueError):
            await _safe_close(websocket, code=_CLOSE_PROTOCOL)
            return

        scope = hello.get("scope") if isinstance(hello, dict) else None
        if (
            not isinstance(hello, dict)
            or hello.get("type") != "hello"
            or scope not in ("user-scoped", "session-scoped", "machine-scoped")
        ):
            logger.info("local WS hello rejected: %r", hello)
            await _safe_close(websocket, code=_CLOSE_PROTOCOL)
            return
        instance_id = hello.get("instance_id")
        if scope == "session-scoped" and not instance_id:
            await _safe_close(websocket, code=_CLOSE_PROTOCOL)
            return

        conn = _LocalConnection(
            connection_id=uuid.uuid4().hex,
            scope=str(scope),
            instance_id=str(instance_id) if instance_id else None,
        )

        def _on_overflow() -> None:
            try:
                asyncio.get_running_loop().create_task(
                    _safe_close(websocket, code=_CLOSE_SLOW_CONSUMER)
                )
            except RuntimeError:
                logger.debug("local WS overflow close skipped (no running loop)")

        conn.on_overflow = _on_overflow
        hub.register(conn)
        try:
            await websocket.send_json(
                {
                    "type": "server_info",
                    "body": {
                        "server_version": SERVER_VERSION,
                        "user_id": LOCAL_USER_ID,
                    },
                }
            )
            await _serve_connection(websocket, conn)
        except WebSocketDisconnect:
            logger.info(
                "local WS %s client disconnected before server_info",
                conn.connection_id,
            )
        finally:
            hub.unregister(conn)

    async def _serve_connection(websocket: WebSocket, conn: _LocalConnection) -> None:
        last_pong = time.monotonic()

        async def drain_outbox() -> None:
            while True:
                frame = await conn.outbox.get()
                await websocket.send_json(frame)

        async def ping_loop() -> None:
            while True:
                await asyncio.sleep(PING_INTERVAL_SECONDS)
                if time.monotonic() - last_pong > 2 * PING_INTERVAL_SECONDS:
                    logger.info("local WS %s missed pongs; closing", conn.connection_id)
                    await _safe_close(websocket, code=_CLOSE_PROTOCOL)
                    return
                conn.enqueue({"type": "ping"})

        background = [
            asyncio.create_task(drain_outbox()),
            asyncio.create_task(ping_loop()),
        ]
        rpc_tasks: set[asyncio.Task] = set()
        try:
            while True:
                message = await websocket.receive_json()
                msg_type = message.get("type")
                if msg_type == "pong":
                    last_pong = time.monotonic()
                elif msg_type == "ping":
                    conn.enqueue({"type": "pong"})
                elif msg_type == "fetch_messages_request":
                    conn.enqueue(await _handle_fetch_messages(conn, message))
                elif msg_type == "fetch_instances_request":
                    rows = await asyncio.to_thread(
                        store.fetch_instances, message.get("updated_after")
                    )
                    conn.enqueue(
                        {
                            "type": "fetch_instances_response",
                            "request_id": message.get("request_id"),
                            "rows": rows,
                        }
                    )
                elif msg_type == "fetch_machines_request":
                    conn.enqueue(
                        {
                            "type": "fetch_machines_response",
                            "request_id": message.get("request_id"),
                            "rows": [_synthetic_machine_body()] if local_only else [],
                        }
                    )
                elif msg_type == "rpc-call":
                    task = asyncio.create_task(_handle_rpc_call(conn, message))
                    rpc_tasks.add(task)
                    task.add_done_callback(rpc_tasks.discard)
                else:
                    logger.debug(
                        "local WS %s ignoring frame type %r",
                        conn.connection_id,
                        msg_type,
                    )
        except WebSocketDisconnect:
            pass
        except RuntimeError as exc:
            logger.info(
                "local WS %s receive after server close: %s",
                conn.connection_id,
                exc,
            )
        except ValueError as exc:
            logger.warning(
                "local WS %s closing on malformed frame: %s",
                conn.connection_id,
                exc,
            )
        finally:
            for task in background:
                task.cancel()
            for task in rpc_tasks:
                task.cancel()

    async def _handle_fetch_messages(conn: _LocalConnection, frame: dict) -> dict:
        request_id = frame.get("request_id")
        instance_id = frame.get("instance_id")
        if not isinstance(instance_id, str) or not instance_id:
            return {
                "type": "fetch_messages_response",
                "request_id": request_id,
                "instance_id": instance_id,
                "rows": [],
                "has_more": False,
            }
        rows, has_more, resync_reason = await asyncio.to_thread(
            store.fetch_messages,
            instance_id,
            frame.get("after"),
            include_agent_messages=(conn.scope == "user-scoped"),
        )
        if resync_reason is not None:
            return {
                "type": "resync_required",
                "request_id": request_id,
                "entity": "messages",
                "instance_id": instance_id,
                "reason": resync_reason,
            }
        return {
            "type": "fetch_messages_response",
            "request_id": request_id,
            "instance_id": instance_id,
            "rows": rows,
            "has_more": has_more,
        }

    async def _handle_rpc_call(conn: _LocalConnection, frame: dict) -> None:
        request_id = frame.get("request_id")
        method = str(frame.get("method"))
        params = frame.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        # machine_id is accepted but not routed on: this server fronts exactly
        # one machine (single-machine locality per the desktop v1 contract).
        #
        # Order-sensitive pty input runs on the single `pty_input_executor` so
        # pipelined keystrokes apply in receive order; `_handle_rpc_call` tasks
        # are created in receive order and reach their executor submit before
        # their first await, so a single worker preserves that order. Other
        # RPCs keep the default pool's concurrency via `asyncio.to_thread`.
        if method in PTY_ORDERED_METHODS:
            result = await asyncio.get_running_loop().run_in_executor(
                pty_input_executor, dispatcher.dispatch, method, params
            )
        else:
            result = await asyncio.to_thread(dispatcher.dispatch, method, params)
        conn.enqueue({"type": "rpc-result", "request_id": request_id, "result": result})
        # Cloud parity (ws_handler.handle_rpc_call): a successful spawn pushes
        # its directory onto the machine's recent list for the session picker.
        if (
            method == "spawn-session"
            and isinstance(result, dict)
            and not result.get("error")
        ):
            directory = params.get("directory")
            if isinstance(directory, str) and directory.strip():
                try:
                    await asyncio.to_thread(
                        store.push_recent_directory, directory.strip()
                    )
                except Exception:
                    logger.exception(
                        "local server: recent-directory update failed after spawn"
                    )

    return app


def _maybe_decode_base64(value: object) -> str | None:
    """Decode base64 strings if they look like base64 (cloud parity)."""
    if not isinstance(value, str) or value == "":
        return None
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return value
    try:
        return decoded.decode("utf-8")
    except UnicodeDecodeError:
        return decoded.decode("utf-8", errors="replace")
