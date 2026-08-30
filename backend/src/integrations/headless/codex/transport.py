"""NDJSON JSON-RPC 2.0 transport for ``codex app-server``.

The transport is duplex-stream-agnostic: production composes it with the
``StreamReader`` / ``StreamWriter`` pair returned by
``asyncio.create_subprocess_exec``; tests inject paired in-memory pipes.

Scope of this slice (tracer bullet):
- request/response correlation by ``id``
- outbound notifications
- inbound notification dispatch via ``on_notification``
- per-call request timeouts (``send_request(..., timeout=...)``)
- fail every pending request when the child dies (``_read_loop`` EOF/error),
  attaching the child's captured stderr tail as the failure reason

Out of scope (later slices): inbound JSON-RPC requests (permission, AUQ)
are handled; live streaming deltas are still buffered by the session.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol


logger = logging.getLogger(__name__)


class CodexTransportClosed(RuntimeError):
    """Raised on pending requests when the codex app-server transport goes
    away — either an explicit ``aclose`` or the child process dying (EOF/error
    on the read loop). Carries the child's captured stderr tail as its reason
    when one is available, so a wedged ``turn/start`` surfaces *why* codex
    exited instead of a bare "transport closed"."""


class _Readable(Protocol):
    async def readline(self) -> bytes: ...


class _Writable(Protocol):
    def write(self, data: bytes) -> None: ...
    async def drain(self) -> None: ...


NotificationHandler = Callable[[str, Dict[str, Any]], Awaitable[None]]
RequestHandler = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]
# Fired once, with the failure reason, when the child dies on its own
# (read-loop EOF/error) — NOT on an explicit ``aclose``. Lets the session
# unblock a turn parked on its own completion future (which is not a transport
# request, so ``_fail_all_pending`` can't reach it).
CloseHandler = Callable[[str], None]


class CodexTransport:
    def __init__(
        self,
        reader: _Readable,
        writer: _Writable,
        *,
        on_notification: Optional[NotificationHandler] = None,
        on_close: Optional[CloseHandler] = None,
        stderr_tail: Optional[Callable[[], str]] = None,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self.on_notification = on_notification
        # Called on *unexpected* child death only (see ``CloseHandler``).
        self.on_close = on_close
        # Best-effort provider of the child's recent stderr, used to explain
        # *why* the transport died when we fail pending requests on EOF. Wired
        # by ``spawn_codex_app_server``; ``None`` for the in-memory test
        # transport (no subprocess, so nothing to tail).
        self._stderr_tail = stderr_tail
        self._request_handlers: Dict[str, RequestHandler] = {}
        self._inbound_tasks: set["asyncio.Task[None]"] = set()

        self._next_id = 1
        self._pending: Dict[int, "asyncio.Future[Dict[str, Any]]"] = {}
        self._read_task: Optional["asyncio.Task[None]"] = None
        self._closed = False
        # Monotonic timestamp of the last inbound frame, used by the session's
        # silence watchdog to detect a codex that went quiet mid-turn. Seeded
        # in ``start`` so a fresh transport doesn't read as idle-since-epoch.
        self._last_activity: float = 0.0

    @property
    def last_activity(self) -> float:
        """Loop-clock time (``loop.time()``) of the most recent inbound frame.

        The session's status watchdog compares this against ``loop.time()`` to
        decide whether codex has gone silent for long enough to settle the row.
        """
        return self._last_activity

    @property
    def is_closed(self) -> bool:
        return self._closed

    def register_request_handler(self, method: str, handler: RequestHandler) -> None:
        """Register a handler for inbound JSON-RPC requests.

        Codex sends us approval requests (``item/commandExecution/requestApproval``,
        ``item/fileChange/requestApproval``, ``item/tool/requestUserInput``,
        ``item/permissions/requestApproval``). Handlers are dispatched
        fire-and-forget so a long human-in-the-loop wait does NOT block
        subsequent inbound frames.
        """
        self._request_handlers[method] = handler

    async def start(self) -> None:
        if self._read_task is None:
            self._last_activity = asyncio.get_running_loop().time()
            self._read_task = asyncio.create_task(self._read_loop())

    async def aclose(self) -> None:
        """Stop the reader task and fail every pending request.

        Subprocess teardown (SIGTERM/SIGKILL fallback) lives in
        ``CodexSubprocess.aclose`` at the spawn layer; this scope is in-process
        state only.
        """
        self._closed = True
        if self._read_task is not None and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except (asyncio.CancelledError, Exception):
                pass
            self._read_task = None
        self._fail_all_pending(self._close_reason("codex transport closed"))

    def _close_reason(self, reason: str) -> str:
        """Append the child's stderr tail to ``reason`` when we have one."""
        if self._stderr_tail is None:
            return reason
        try:
            tail = self._stderr_tail()
        except Exception:
            tail = ""
        if not tail:
            return reason
        return f"{reason}\n--- codex stderr (tail) ---\n{tail}"

    def _fail_all_pending(self, reason: str) -> None:
        """Reject all in-flight requests + inbound handlers with ``reason``.

        Called both on explicit ``aclose`` and when ``_read_loop`` hits EOF /
        error (codex died on its own). Without the latter, an in-flight
        ``turn/start`` would hang until something else happened to call
        ``aclose``. ``reason`` already carries any stderr tail (see
        ``_close_reason``).
        """
        # Cancel any in-flight inbound request handlers so their futures stop
        # awaiting state we'll never deliver (e.g. permission registry).
        for task in list(self._inbound_tasks):
            if not task.done():
                task.cancel()
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(CodexTransportClosed(reason))
        self._pending.clear()

    async def send_request(
        self,
        method: str,
        params: Dict[str, Any],
        *,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Send a JSON-RPC request and await its response.

        ``timeout`` bounds the wait for a matching response. The turn/message
        flow passes explicit bounds (``turn/start`` ~90s, ``model/list`` /
        ``turn/interrupt`` ~10s) so a codex that stalls mid-handshake can't
        wedge the caller forever; streaming notifications never come through
        here, so they're unaffected. ``None`` keeps the legacy unbounded wait.
        """
        if self._closed:
            # Fail fast rather than parking a future the dead reader can never
            # resolve.
            raise CodexTransportClosed(f"codex transport closed (cannot {method})")
        msg_id = self._next_id
        self._next_id += 1
        fut: "asyncio.Future[Dict[str, Any]]" = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[msg_id] = fut
        self._write(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "method": method,
                "params": params,
            }
        )
        try:
            if timeout is None:
                return await fut
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"codex request {method!r} timed out after {timeout:.0f}s"
            ) from None
        finally:
            self._pending.pop(msg_id, None)

    def notify(self, method: str, params: Dict[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _write(self, payload: Dict[str, Any]) -> None:
        serialized = json.dumps(payload)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("codex -> %s", serialized[:500])
        self._writer.write((serialized + "\n").encode("utf-8"))

    async def _read_loop(self) -> None:
        reason = "codex app-server exited"
        try:
            while not self._closed:
                try:
                    line = await self._reader.readline()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.exception("codex transport: read failed")
                    reason = f"codex app-server read error: {exc}"
                    break
                if not line:
                    break
                self._last_activity = asyncio.get_running_loop().time()
                try:
                    msg = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    logger.warning("codex transport: invalid JSON line: %r", line)
                    continue
                # Always log inbound at DEBUG so a `--debug` run produces the
                # exact wire trace without code changes. The full payload can
                # be large; truncate to keep logs scannable.
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("codex <- %s", json.dumps(msg)[:500])
                await self._dispatch(msg)
        finally:
            # EOF or read error means codex is gone: fail everything still
            # waiting on a response so callers unblock instead of hanging until
            # some other path calls aclose(). Skip when we're already closing
            # (aclose owns the failure reason in that case).
            if not self._closed:
                self._closed = True
                full_reason = self._close_reason(reason)
                logger.warning(
                    "codex transport: %s; failing pending requests", full_reason[:500]
                )
                self._fail_all_pending(full_reason)
                # Notify the session so it can unblock a turn parked on its own
                # completion future (not reachable via _pending) and settle the
                # row. Only fires on unexpected death, never on aclose.
                cb = self.on_close
                if cb is not None:
                    try:
                        cb(full_reason)
                    except Exception:
                        logger.exception("codex transport: on_close callback raised")

    async def _dispatch(self, msg: Dict[str, Any]) -> None:
        # Response to one of our outbound requests
        if "id" in msg and ("result" in msg or "error" in msg):
            fut = self._pending.get(msg["id"])
            if fut is not None and not fut.done():
                if "error" in msg:
                    fut.set_exception(RuntimeError(f"codex error: {msg['error']}"))
                else:
                    fut.set_result(msg.get("result") or {})
            return

        method = msg.get("method")
        if method is None:
            logger.debug("codex transport: unhandled message: %r", msg)
            return

        # Inbound request (id + method): fire-and-forget so a long-blocking
        # handler (permission wait) does not stall the read loop.
        if "id" in msg:
            handler = self._request_handlers.get(method)
            msg_id = msg["id"]
            if handler is None:
                self._write(
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {
                            "code": -32601,
                            "message": f"method not handled: {method}",
                        },
                    }
                )
                return
            task = asyncio.create_task(
                self._handle_inbound_request(handler, msg_id, msg.get("params") or {})
            )
            self._inbound_tasks.add(task)
            task.add_done_callback(self._inbound_tasks.discard)
            return

        # Notification: method + params, no id
        if self.on_notification is not None:
            await self.on_notification(method, msg.get("params") or {})

    async def _handle_inbound_request(
        self,
        handler: RequestHandler,
        msg_id: Any,
        params: Dict[str, Any],
    ) -> None:
        try:
            result = await handler(params)
            self._write({"jsonrpc": "2.0", "id": msg_id, "result": result})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("codex inbound handler raised for id=%s", msg_id)
            self._write(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32603, "message": str(exc)},
                }
            )
