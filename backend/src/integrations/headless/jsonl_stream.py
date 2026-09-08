"""Line framing for the JSONL-over-stdio agent transports.

Both the codex ``app-server`` transport and the Pi-family transport read
newline-delimited JSON off a subprocess pipe, so the framing lives here rather
than in either one.

Why not ``asyncio.StreamReader.readline``: it refuses any line longer than the
reader's ``limit`` (64 KiB by default) — issue #33, where a single large codex
notification took down the session. Raising that limit only moves the cliff,
and a frame dropped at the cliff is *silent* to the user: a lost notification
is a missing message, a lost response is a turn that hangs until it times out.
Node's ``readline`` — what the same integrations use in ``paseo`` — has no
line-length cap at all, which is why codex never hit this there. So we do the
framing ourselves and match that: no cap on a legal frame.
"""

from __future__ import annotations

import logging
from typing import Protocol


logger = logging.getLogger(__name__)


#: How much we ask the OS pipe for per read. Only a syscall-batching knob.
_READ_CHUNK_BYTES = 64 * 1024

#: Read-ahead window handed to a child's ``StreamReader`` via
#: ``create_subprocess_exec(..., limit=...)``.
#:
#: Since framing no longer goes through ``StreamReader.readline``, this is pure
#: flow control — how far the child may run ahead of us before asyncio pauses
#: reading its pipe — **not** a ceiling on a frame. Kept explicit (rather than
#: left at asyncio's 64 KiB) so a big frame arrives in a few reads instead of
#: dozens, and so anything that reverts to ``readline`` doesn't silently
#: reintroduce issue #33.
STREAM_READ_AHEAD_BYTES = 2 * 1024 * 1024

#: Ceiling on a single physical line for codex. Codex publishes no frame size
#: limit, so this is a runaway guard, not a protocol rule: it exists only to
#: bound memory if the child goes berserk. Deliberately far above anything
#: codex has been observed to send, because dropping a frame it *meant* to send
#: is the failure this module exists to prevent.
CODEX_MAX_LINE_BYTES = 64 * 1024 * 1024

#: Ceiling on a single physical line for the Pi family. This one *is* a
#: protocol rule: pi/omp cap a physical frame at 1 MiB
#: (``MAX_RPC_FRAME_BYTES``) and split anything larger into ``rpc_chunk``
#: envelopes, so a longer line is a spec violation rather than a big message.
PI_MAX_LINE_BYTES = 2 * 1024 * 1024


class OversizedFrameError(ValueError):
    """A single line ran past the reader's ceiling and was dropped.

    Subclasses ``ValueError`` so a read loop that already handles
    ``StreamReader.readline``'s overrun handles this too. The reader resyncs
    itself at the next newline, so a caller should log and keep reading.
    """


class _ByteStream(Protocol):
    async def read(self, n: int) -> bytes: ...


class JsonlLineReader:
    """Split a byte stream into LF-terminated lines, with no cap on a legal one.

    Returns each line *including* its trailing newline (matching
    ``StreamReader.readline``), a final unterminated line at EOF, and ``b""``
    once the stream is exhausted.

    A line past ``max_line_bytes`` raises :class:`OversizedFrameError` and puts
    the reader into discard mode: the rest of that line is consumed and thrown
    away, so the *next* call resumes cleanly at the following frame. The stream
    never desyncs and memory stays bounded.
    """

    def __init__(
        self,
        stream: _ByteStream,
        *,
        max_line_bytes: int,
        label: str = "agent",
    ) -> None:
        self._stream = stream
        self._max_line_bytes = max_line_bytes
        self._label = label
        self._buf = bytearray()
        # Where the next newline scan starts. Without it, re-scanning the whole
        # buffer on every chunk makes assembling a large frame quadratic.
        self._scanned = 0
        self._eof = False
        self._discarding = False

    async def readline(self) -> bytes:
        while True:
            newline = self._buf.find(b"\n", self._scanned)
            if newline != -1:
                line = bytes(self._buf[: newline + 1])
                del self._buf[: newline + 1]
                self._scanned = 0
                return line
            self._scanned = len(self._buf)
            if self._eof:
                if not self._buf:
                    return b""
                line = bytes(self._buf)
                self._buf.clear()
                self._scanned = 0
                return line
            chunk = await self._stream.read(_READ_CHUNK_BYTES)
            if not chunk:
                self._eof = True
                continue
            self._buf += chunk
            if self._discarding:
                self._drop_through_newline()
                continue
            if len(self._buf) > self._max_line_bytes:
                dropped = len(self._buf)
                self._buf.clear()
                self._scanned = 0
                self._discarding = True
                raise OversizedFrameError(
                    f"{self._label}: frame exceeded {self._max_line_bytes} bytes "
                    f"({dropped} buffered so far); dropping it"
                )

    def _drop_through_newline(self) -> None:
        """Throw away buffered bytes belonging to a frame already refused."""
        newline = self._buf.find(b"\n")
        if newline == -1:
            self._buf.clear()
        else:
            del self._buf[: newline + 1]
            self._discarding = False
        self._scanned = 0


__all__ = [
    "CODEX_MAX_LINE_BYTES",
    "JsonlLineReader",
    "OversizedFrameError",
    "PI_MAX_LINE_BYTES",
    "STREAM_READ_AHEAD_BYTES",
]
