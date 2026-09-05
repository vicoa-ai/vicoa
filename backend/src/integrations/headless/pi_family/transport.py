"""NDJSON RPC transport for the Pi-family CLIs.

The wire is strict JSONL over stdio, LF-delimited, with three frame classes::

    us  -> agent   {"type": "<command>", "id": "req_1", ...params}
    agent -> us    {"id": "req_1", "type": "response", "command": "<command>",
                    "success": true, "data": {...}}
    agent -> us    {"type": "<event>", ...}          # everything else

Deliberately *not* built on ``codex/transport.py``: that is LSP-style
JSON-RPC 2.0 (``jsonrpc``/``method``/``params``, integer ids, inbound requests)
and the envelopes do not meet. The structural shape here — request
correlation, stderr tail folded into failures, fail-pending on child death —
is the same idea, ported rather than shared.

Two behaviours are easy to get wrong and are handled explicitly:

* **Chunked frames.** Once protocol v2 is negotiated, omp splits any logical
  frame over 1 MiB into ``rpc_chunk`` envelopes (256 KiB of base64 each,
  strictly sequential, up to a 64 MiB reassembled ceiling) — see
  ``modes/rpc/rpc-frame.ts`` in the shipped package. A reader that treats each
  JSONL line as a whole frame silently drops big ``agent_end`` / ``get_messages``
  payloads.
* **Error responses can lose their id.** omp answers an unrecognised command
  with ``{"type":"response","command":"...","success":false,"error":"Unknown
  command: ..."}`` and **no ``id``** (pi keeps the id). Correlating strictly on
  ``id`` leaves such a request parked until its timeout, which matters because
  probing an optional command is a normal thing to do across two agents with
  different surfaces. So an id-less response falls back to the oldest pending
  request for the same ``command``.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol


logger = logging.getLogger(__name__)


#: Ceiling on a single reassembled logical frame, mirroring the agent's own
#: ``MAX_RPC_REASSEMBLED_BYTES``. A stream that claims more than this is
#: malformed, and buffering it would be an unbounded memory sink.
MAX_REASSEMBLED_BYTES = 64 * 1024 * 1024


class PiTransportClosed(RuntimeError):
    """Raised on pending requests when the agent transport goes away.

    Either an explicit ``aclose`` or the child dying on its own (EOF / read
    error). Carries the child's captured stderr tail when one is available, so
    a wedged ``prompt`` says *why* the CLI exited instead of "transport
    closed" — which matters a lot here, since both CLIs exit 1 before the
    first frame when no model is configured.
    """


class _Readable(Protocol):
    async def readline(self) -> bytes: ...


class _Writable(Protocol):
    def write(self, data: bytes) -> None: ...
    async def drain(self) -> None: ...


EventHandler = Callable[[Dict[str, Any]], Awaitable[None]]
#: Fired once with the failure reason when the child dies on its own — NOT on
#: an explicit ``aclose``. Lets the session unblock a turn parked on its own
#: completion future, which is not a transport request and so is out of reach
#: of ``_fail_all_pending``.
CloseHandler = Callable[[str], None]


class ChunkReassembler:
    """Reassemble protocol-v2 ``rpc_chunk`` sequences into logical frames.

    Mirrors the encoder's invariants (``modes/rpc/rpc-frame.ts``): a sequence
    starts at index 0, arrives strictly in order, shares one ``chunkId`` /
    ``count`` / ``byteLength``, and the concatenated payload must match the
    declared length exactly. Any violation raises — the stream is corrupt at
    that point and guessing would hand the mapper a half-frame.
    """

    def __init__(self) -> None:
        self._chunk_id: Optional[str] = None
        self._count = 0
        self._byte_length = 0
        self._next_index = 0
        self._parts: List[bytes] = []
        self._received = 0

    @property
    def in_progress(self) -> bool:
        return self._chunk_id is not None

    def reset(self) -> None:
        self.__init__()  # type: ignore[misc]

    def push(self, frame: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Feed one parsed JSONL frame.

        Returns the frame itself when it is a whole frame, the reassembled
        frame when this chunk completes a sequence, or ``None`` while a
        sequence is still filling.
        """
        if frame.get("type") != "rpc_chunk":
            if self.in_progress:
                self.reset()
                raise ValueError("rpc chunk sequence interrupted")
            return frame

        chunk_id = frame.get("chunkId")
        index = frame.get("index")
        count = frame.get("count")
        byte_length = frame.get("byteLength")
        if (
            not isinstance(chunk_id, str)
            or not chunk_id
            or not isinstance(index, int)
            or not isinstance(count, int)
            or not isinstance(byte_length, int)
            or index < 0
            or count < 2
            or index >= count
            or byte_length <= 0
            or byte_length > MAX_REASSEMBLED_BYTES
        ):
            self.reset()
            raise ValueError("invalid rpc chunk metadata")

        try:
            payload = base64.b64decode(frame.get("data") or "", validate=True)
        except (binascii.Error, ValueError) as exc:
            self.reset()
            raise ValueError("invalid rpc chunk data") from exc

        if not self.in_progress:
            if index != 0:
                raise ValueError("rpc chunk sequence must start at index 0")
            self._chunk_id = chunk_id
            self._count = count
            self._byte_length = byte_length
            self._next_index = 0
            self._parts = []
            self._received = 0

        if (
            self._chunk_id != chunk_id
            or self._count != count
            or self._byte_length != byte_length
            or self._next_index != index
        ):
            self.reset()
            raise ValueError("rpc chunk sequence mismatch")

        self._parts.append(payload)
        self._received += len(payload)
        self._next_index += 1
        if self._received > self._byte_length:
            self.reset()
            raise ValueError("rpc chunk sequence exceeds declared length")
        if self._next_index < self._count:
            return None
        if self._received != self._byte_length:
            self.reset()
            raise ValueError("rpc chunk sequence length mismatch")

        joined = b"".join(self._parts)
        self.reset()
        decoded = json.loads(joined.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("rpc frame must be an object")
        return decoded


class _Pending:
    """One in-flight request: its future plus the command it was sent as."""

    __slots__ = ("command", "future")

    def __init__(self, command: str, future: "asyncio.Future[Dict[str, Any]]") -> None:
        self.command = command
        self.future = future


class PiTransport:
    """Duplex JSONL RPC over an agent's stdio.

    Stream-agnostic: production composes it with the ``StreamReader`` /
    ``StreamWriter`` pair from ``asyncio.create_subprocess_exec`` (see
    ``spawn.py``); tests inject in-memory pipes.
    """

    def __init__(
        self,
        reader: _Readable,
        writer: _Writable,
        *,
        on_event: Optional[EventHandler] = None,
        on_close: Optional[CloseHandler] = None,
        stderr_tail: Optional[Callable[[], str]] = None,
        agent_label: str = "agent",
    ) -> None:
        self._reader = reader
        self._writer = writer
        self.on_event = on_event
        self.on_close = on_close
        self._stderr_tail = stderr_tail
        self._label = agent_label

        self._next_id = 1
        self._pending: "Dict[str, _Pending]" = {}
        self._read_task: Optional["asyncio.Task[None]"] = None
        self._closed = False
        self._reassembler = ChunkReassembler()
        #: Loop-clock time of the most recent inbound frame. The session's
        #: silence watchdog compares it against ``loop.time()``; seeded in
        #: ``start`` so a fresh transport doesn't read as idle-since-epoch.
        self._last_activity: float = 0.0

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def last_activity(self) -> float:
        return self._last_activity

    @property
    def is_closed(self) -> bool:
        return self._closed

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._read_task is None:
            self._last_activity = asyncio.get_running_loop().time()
            self._read_task = asyncio.create_task(self._read_loop())

    async def aclose(self) -> None:
        """Stop the reader and fail every pending request.

        Subprocess teardown lives in ``spawn.PiSubprocess.aclose``; this scope
        is in-process state only.
        """
        self._closed = True
        if self._read_task is not None and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except (asyncio.CancelledError, Exception):
                pass
            self._read_task = None
        self._fail_all_pending(self._close_reason(f"{self._label} transport closed"))

    def _close_reason(self, reason: str) -> str:
        if self._stderr_tail is None:
            return reason
        try:
            tail = self._stderr_tail()
        except Exception:
            tail = ""
        if not tail:
            return reason
        return f"{reason}\n--- {self._label} stderr (tail) ---\n{tail}"

    def _fail_all_pending(self, reason: str) -> None:
        for entry in list(self._pending.values()):
            if not entry.future.done():
                entry.future.set_exception(PiTransportClosed(reason))
        self._pending.clear()

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def request(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[float] = 30.0,
    ) -> Dict[str, Any]:
        """Send a command and await its response ``data``.

        Params ride at the *top level* of the frame next to ``type`` and
        ``id`` — this protocol has no ``params`` envelope. ``timeout=None``
        waits forever, which is what LLM-backed commands (``compact``,
        ``handoff``) need; everything else passes a bound so a stalled agent
        can't wedge the caller.

        Raises :class:`PiRpcError` when the agent answers ``success: false``.
        """
        if self._closed:
            raise PiTransportClosed(
                f"{self._label} transport closed (cannot {command})"
            )
        request_id = f"req_{self._next_id}"
        self._next_id += 1
        future: "asyncio.Future[Dict[str, Any]]" = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[request_id] = _Pending(command, future)
        frame: Dict[str, Any] = {"type": command, "id": request_id}
        if params:
            frame.update(params)
        self._write(frame)
        try:
            if timeout is None:
                return await future
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"{self._label} request {command!r} timed out after {timeout:.0f}s"
            ) from None
        finally:
            self._pending.pop(request_id, None)

    def send(self, command: str, params: Optional[Dict[str, Any]] = None) -> None:
        """Fire-and-forget frame (``steer``, ``host_tool_result``, …).

        These carry no ``id`` because nothing correlates a response to them.
        """
        frame: Dict[str, Any] = {"type": command}
        if params:
            frame.update(params)
        self._write(frame)

    def _write(self, payload: Dict[str, Any]) -> None:
        serialized = json.dumps(payload)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("%s -> %s", self._label, serialized[:500])
        try:
            self._writer.write((serialized + "\n").encode("utf-8"))
        except (BrokenPipeError, OSError) as exc:
            # The child is gone; the read loop will notice and fail pending
            # requests with a reason. Don't raise from a fire-and-forget send.
            logger.warning("%s transport: write failed: %s", self._label, exc)

    # ------------------------------------------------------------------
    # Receiving
    # ------------------------------------------------------------------

    async def _read_loop(self) -> None:
        reason = f"{self._label} exited"
        try:
            while not self._closed:
                try:
                    line = await self._reader.readline()
                except asyncio.CancelledError:
                    raise
                except ValueError as exc:
                    # ``StreamReader.readline`` overran its buffer limit and
                    # left the data in place, so retrying would spin forever.
                    # Fatal, but say what it actually is — see
                    # ``spawn.STREAM_READER_LIMIT``.
                    logger.error(
                        "%s transport: frame exceeded the read buffer: %s",
                        self._label,
                        exc,
                    )
                    reason = (
                        f"{self._label} sent a frame larger than the read "
                        f"buffer ({exc})"
                    )
                    break
                except Exception as exc:
                    logger.exception("%s transport: read failed", self._label)
                    reason = f"{self._label} read error: {exc}"
                    break
                if not line:
                    break
                self._last_activity = asyncio.get_running_loop().time()
                # Strict JSONL: LF is the only delimiter, but tolerate a CR
                # from a Windows-side writer. Never split on anything else —
                # U+2028/U+2029 are legal inside JSON strings.
                text = line.decode("utf-8", "replace").rstrip("\n").rstrip("\r")
                if not text.strip():
                    continue
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    logger.warning(
                        "%s transport: invalid JSON line: %r", self._label, text[:200]
                    )
                    continue
                if not isinstance(parsed, dict):
                    logger.warning(
                        "%s transport: non-object frame dropped", self._label
                    )
                    continue
                try:
                    frame = self._reassembler.push(parsed)
                except ValueError as exc:
                    logger.warning("%s transport: %s", self._label, exc)
                    continue
                if frame is None:
                    continue  # mid-chunk
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("%s <- %s", self._label, json.dumps(frame)[:500])
                await self._dispatch(frame)
        finally:
            if not self._closed:
                self._closed = True
                full_reason = self._close_reason(reason)
                logger.warning(
                    "%s transport: %s; failing pending requests",
                    self._label,
                    full_reason[:500],
                )
                self._fail_all_pending(full_reason)
                callback = self.on_close
                if callback is not None:
                    try:
                        callback(full_reason)
                    except Exception:
                        logger.exception(
                            "%s transport: on_close callback raised", self._label
                        )

    async def _dispatch(self, frame: Dict[str, Any]) -> None:
        if frame.get("type") == "response":
            self._resolve_response(frame)
            return
        handler = self.on_event
        if handler is not None:
            try:
                await handler(frame)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "%s transport: event handler raised for type=%s",
                    self._label,
                    frame.get("type"),
                )

    def _resolve_response(self, frame: Dict[str, Any]) -> None:
        entry = self._take_pending(frame)
        if entry is None:
            logger.debug(
                "%s transport: unmatched response command=%s id=%s",
                self._label,
                frame.get("command"),
                frame.get("id"),
            )
            return
        if entry.future.done():
            return
        if frame.get("success") is False:
            entry.future.set_exception(
                PiRpcError(
                    str(frame.get("command") or entry.command),
                    str(frame.get("error") or "unknown error"),
                    code=frame.get("code"),
                )
            )
            return
        data = frame.get("data")
        # A successful ack can legitimately be `data: null` (`prompt` often is),
        # so normalise to {} rather than treating it as missing.
        entry.future.set_result(data if isinstance(data, dict) else {})

    def _take_pending(self, frame: Dict[str, Any]) -> Optional[_Pending]:
        request_id = frame.get("id")
        if isinstance(request_id, str):
            entry = self._pending.pop(request_id, None)
            if entry is not None:
                return entry
        # No id (omp's "Unknown command" error path) or an id we don't know:
        # fall back to the oldest pending request for the same command, which
        # is unambiguous because we only ever have one of each in flight.
        command = frame.get("command")
        if not isinstance(command, str):
            return None
        for key, entry in self._pending.items():
            if entry.command == command:
                del self._pending[key]
                return entry
        return None


class PiRpcError(RuntimeError):
    """The agent answered a command with ``success: false``."""

    def __init__(self, command: str, message: str, *, code: Any = None) -> None:
        super().__init__(f"{command}: {message}")
        self.command = command
        self.message = message
        self.code = code

    @property
    def is_unknown_command(self) -> bool:
        """Whether this is the "this build has no such command" answer.

        Used to degrade gracefully across the two agents (and across omp
        versions) instead of treating a missing optional command as a failure.
        """
        return "unknown command" in self.message.lower()


__all__ = [
    "ChunkReassembler",
    "MAX_REASSEMBLED_BYTES",
    "PiRpcError",
    "PiTransport",
    "PiTransportClosed",
]
