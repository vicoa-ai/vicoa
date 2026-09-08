"""Regression tests for issue #33 — a large codex frame used to kill the
transport for the rest of the session.

The rule under test is "a frame codex meant to send is always delivered".
``asyncio.StreamReader.readline`` cannot honour that: it refuses any line past
its ``limit``, and *every* choice of limit is a cliff a real tool result can
run past. So framing goes through :class:`JsonlLineReader`, which has no cap on
a legal line — the same guarantee Node's ``readline`` gives the equivalent
integrations in ``paseo``, which is why codex never hit this there.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Dict, List, Tuple

import pytest

from integrations.headless.codex.spawn import spawn_codex_app_server
from integrations.headless.codex.transport import CodexTransport
from integrations.headless.jsonl_stream import JsonlLineReader, OversizedFrameError


# ---------------------------------------------------------------------------
# End to end, over a real subprocess pipe
# ---------------------------------------------------------------------------

# Emits one big notification, then behaves like ``_fake_codex.py``.
_FAKE_CODEX_BIG_FRAME = """
import json, sys

size = int(sys.argv[1])
sys.stdout.write(json.dumps({
    "jsonrpc": "2.0",
    "method": "codex/event",
    "params": {"msg": "A" * size},
}) + "\\n")
sys.stdout.flush()

while True:
    line = sys.stdin.readline()
    if not line:
        break
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    if msg.get("method") == "initialize" and msg.get("id") is not None:
        sys.stdout.write(json.dumps({
            "jsonrpc": "2.0", "id": msg["id"], "result": {"ok": True},
        }) + "\\n")
        sys.stdout.flush()
"""


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="asyncio subprocess on Windows needs ProactorEventLoop; not in scope",
)
@pytest.mark.parametrize(
    "size",
    [
        # Past asyncio's 64 KiB default — the reporter's case.
        pytest.param(200_000, id="200KiB"),
        # Past 2 MiB, i.e. past any ceiling we would plausibly have picked for
        # a StreamReader. A codex tool result really can be this big, and
        # dropping it costs a message or hangs a turn.
        pytest.param(3 * 1024 * 1024, id="3MiB"),
    ],
)
async def test_big_notification_is_delivered_whole(size: int):
    spawned = await spawn_codex_app_server(
        command=[sys.executable, "-c", _FAKE_CODEX_BIG_FRAME, str(size)],
    )
    seen: List[Tuple[str, Dict[str, Any]]] = []
    received = asyncio.Event()

    async def on_notification(method: str, params: Dict[str, Any]) -> None:
        seen.append((method, params))
        received.set()

    spawned.transport.on_notification = on_notification
    try:
        await spawned.transport.start()
        await asyncio.wait_for(received.wait(), timeout=10.0)
        assert seen[0][0] == "codex/event"
        assert seen[0][1]["msg"] == "A" * size

        # The session survives the big frame: a normal request still works.
        result = await asyncio.wait_for(
            spawned.transport.send_request("initialize", {"capabilities": {}}),
            timeout=10.0,
        )
        assert result == {"ok": True}
    finally:
        await spawned.aclose()


# ---------------------------------------------------------------------------
# JsonlLineReader
# ---------------------------------------------------------------------------


class _ByteFeed:
    """A byte stream that hands out at most ``n`` bytes per read, then EOF."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self, n: int) -> bytes:
        chunk, self._data = self._data[:n], self._data[n:]
        return chunk


def _reader(data: bytes, *, max_line_bytes: int = 1 << 30) -> JsonlLineReader:
    return JsonlLineReader(_ByteFeed(data), max_line_bytes=max_line_bytes, label="test")


async def test_reader_assembles_a_line_spanning_many_reads():
    line = b"x" * (5 * 1024 * 1024)
    reader = _reader(line + b"\n")
    assert await reader.readline() == line + b"\n"
    assert await reader.readline() == b""


async def test_reader_splits_several_lines_out_of_one_read():
    reader = _reader(b"a\nb\nc\n")
    assert [await reader.readline() for _ in range(3)] == [b"a\n", b"b\n", b"c\n"]
    assert await reader.readline() == b""


async def test_reader_returns_a_trailing_line_without_a_newline():
    reader = _reader(b"a\ntail")
    assert await reader.readline() == b"a\n"
    assert await reader.readline() == b"tail"
    assert await reader.readline() == b""


async def test_reader_drops_a_runaway_line_and_resyncs():
    """The ceiling costs exactly one frame, and the stream stays in sync."""
    runaway = b"R" * (300 * 1024)
    reader = _reader(runaway + b"\n" + b"after\n", max_line_bytes=64 * 1024)
    with pytest.raises(OversizedFrameError):
        await reader.readline()
    assert await reader.readline() == b"after\n"
    assert await reader.readline() == b""


async def test_reader_reports_eof_when_a_runaway_line_never_ends():
    reader = _reader(b"R" * (300 * 1024), max_line_bytes=64 * 1024)
    with pytest.raises(OversizedFrameError):
        await reader.readline()
    assert await reader.readline() == b""


# ---------------------------------------------------------------------------
# Transport read loop
# ---------------------------------------------------------------------------


class _NullWriter:
    def write(self, data: bytes) -> None:  # pragma: no cover - trivial
        pass

    async def drain(self) -> None:  # pragma: no cover - trivial
        pass


async def test_transport_survives_a_frame_past_the_ceiling():
    """Even the runaway guard must not take the session down."""
    ceiling = 64 * 1024
    stream = asyncio.StreamReader()
    transport = CodexTransport(
        reader=JsonlLineReader(stream, max_line_bytes=ceiling, label="codex"),
        writer=_NullWriter(),
    )

    delivered: List[str] = []
    arrived = asyncio.Event()

    async def on_notification(method: str, params: Dict[str, Any]) -> None:
        delivered.append(method)
        arrived.set()

    transport.on_notification = on_notification
    await transport.start()

    runaway = json.dumps(
        {"jsonrpc": "2.0", "method": "too/big", "params": {"msg": "A" * ceiling * 3}}
    )
    ok = json.dumps({"jsonrpc": "2.0", "method": "still/alive", "params": {}})
    stream.feed_data((runaway + "\n" + ok + "\n").encode("utf-8"))

    try:
        await asyncio.wait_for(arrived.wait(), timeout=5.0)
        assert delivered == ["still/alive"]
        assert not transport.is_closed
    finally:
        await transport.aclose()
