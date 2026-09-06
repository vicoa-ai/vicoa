"""Transport-level tests for the Pi-family JSONL RPC.

Driven through in-memory pipes rather than a subprocess: the transport is
stream-agnostic by design and ``spawn.py`` is the only module that knows about
processes.
"""

from __future__ import annotations

import asyncio
import base64
import json

import pytest

from integrations.headless.pi_family.transport import (
    ChunkReassembler,
    PiRpcError,
    PiTransport,
    PiTransportClosed,
)


class FakeReader:
    """Feeds pre-queued lines, then blocks (or EOFs) like a real stream."""

    def __init__(self) -> None:
        self._queue: "asyncio.Queue[bytes]" = asyncio.Queue()
        self._eof = False

    def push(self, frame) -> None:
        payload = frame if isinstance(frame, str) else json.dumps(frame)
        self._queue.put_nowait((payload + "\n").encode("utf-8"))

    def eof(self) -> None:
        self._eof = True
        self._queue.put_nowait(b"")

    async def readline(self) -> bytes:
        return await self._queue.get()


class FakeWriter:
    def __init__(self) -> None:
        self.written: list[dict] = []

    def write(self, data: bytes) -> None:
        for line in data.decode("utf-8").splitlines():
            if line.strip():
                self.written.append(json.loads(line))

    async def drain(self) -> None:
        return None


def make_transport(**kwargs):
    reader, writer = FakeReader(), FakeWriter()
    transport = PiTransport(reader, writer, agent_label="omp", **kwargs)
    return transport, reader, writer


async def test_request_correlates_by_id_and_returns_data():
    transport, reader, writer = make_transport()
    await transport.start()
    task = asyncio.create_task(transport.request("get_state", timeout=5))
    await asyncio.sleep(0)
    sent = writer.written[-1]
    assert sent["type"] == "get_state"
    reader.push(
        {
            "id": sent["id"],
            "type": "response",
            "command": "get_state",
            "success": True,
            "data": {"sessionId": "abc"},
        }
    )
    assert await task == {"sessionId": "abc"}
    await transport.aclose()


async def test_params_ride_at_the_top_level_not_in_an_envelope():
    """This protocol has no ``params`` object — a nested one would be ignored."""
    transport, _reader, writer = make_transport()
    await transport.start()
    task = asyncio.create_task(
        transport.request("set_thinking_level", {"level": "high"}, timeout=0.2)
    )
    await asyncio.sleep(0)
    assert writer.written[-1]["level"] == "high"
    assert "params" not in writer.written[-1]
    with pytest.raises(TimeoutError):
        await task
    await transport.aclose()


async def test_null_data_ack_resolves_to_empty_dict():
    """``prompt`` often acks with ``data: null``; that is success, not absence."""
    transport, reader, writer = make_transport()
    await transport.start()
    task = asyncio.create_task(transport.request("prompt", {"message": "hi"}))
    await asyncio.sleep(0)
    reader.push(
        {
            "id": writer.written[-1]["id"],
            "type": "response",
            "command": "prompt",
            "success": True,
            "data": None,
        }
    )
    assert await task == {}
    await transport.aclose()


async def test_failed_response_raises_pi_rpc_error():
    transport, reader, writer = make_transport()
    await transport.start()
    task = asyncio.create_task(transport.request("branch", {"entryId": "x"}))
    await asyncio.sleep(0)
    reader.push(
        {
            "id": writer.written[-1]["id"],
            "type": "response",
            "command": "branch",
            "success": False,
            "error": "Cannot rewind while a turn is active",
        }
    )
    with pytest.raises(PiRpcError) as excinfo:
        await task
    assert not excinfo.value.is_unknown_command
    await transport.aclose()


async def test_id_less_unknown_command_error_still_resolves_its_request():
    """omp drops the ``id`` on an unknown-command error; pi keeps it.

    Without the command-name fallback the request would park until its
    timeout, which matters because probing an optional command is routine
    across two agents with different surfaces.
    """
    transport, reader, _writer = make_transport()
    await transport.start()
    task = asyncio.create_task(transport.request("set_host_tools", {"tools": []}))
    await asyncio.sleep(0)
    reader.push(
        {
            "type": "response",
            "command": "set_host_tools",
            "success": False,
            "error": "Unknown command: set_host_tools",
        }
    )
    with pytest.raises(PiRpcError) as excinfo:
        await task
    assert excinfo.value.is_unknown_command
    await transport.aclose()


async def test_events_are_dispatched_to_the_event_handler():
    seen: list[dict] = []

    async def on_event(frame):
        seen.append(frame)

    transport, reader, _writer = make_transport(on_event=on_event)
    await transport.start()
    reader.push({"type": "agent_start"})
    reader.push({"type": "turn_start"})
    await asyncio.sleep(0.05)
    assert [frame["type"] for frame in seen] == ["agent_start", "turn_start"]
    await transport.aclose()


async def test_child_death_fails_pending_requests_with_the_stderr_tail():
    transport, reader, _writer = make_transport(
        stderr_tail=lambda: "No models available. Use /login or set an API key."
    )
    await transport.start()
    task = asyncio.create_task(transport.request("get_state"))
    await asyncio.sleep(0)
    reader.eof()
    with pytest.raises(PiTransportClosed) as excinfo:
        await task
    assert "No models available" in str(excinfo.value)


async def test_on_close_fires_only_for_unexpected_death():
    reasons: list[str] = []
    transport, reader, _writer = make_transport(on_close=reasons.append)
    await transport.start()
    reader.eof()
    await asyncio.sleep(0.05)
    assert len(reasons) == 1

    transport2, _reader2, _writer2 = make_transport(on_close=reasons.append)
    await transport2.start()
    await transport2.aclose()
    await asyncio.sleep(0.05)
    assert len(reasons) == 1  # aclose is not a death


async def test_send_is_fire_and_forget_and_carries_no_id():
    transport, _reader, writer = make_transport()
    transport.send("host_tool_result", {"id": "call-1", "result": {}})
    frame = writer.written[-1]
    assert frame["type"] == "host_tool_result"
    # The ``id`` here is the host-tool correlation id, not a request id — the
    # transport must not mint one of its own for a fire-and-forget frame.
    assert frame["id"] == "call-1"


async def test_chunked_frames_are_reassembled():
    transport, reader, _writer = make_transport()
    seen: list[dict] = []

    async def on_event(frame):
        seen.append(frame)

    transport.on_event = on_event
    await transport.start()

    original = {
        "type": "agent_end",
        "messages": [{"role": "assistant"} for _ in range(50)],
    }
    payload = json.dumps(original).encode("utf-8")
    half = len(payload) // 2
    parts = [payload[:half], payload[half:]]
    for index, part in enumerate(parts):
        reader.push(
            {
                "type": "rpc_chunk",
                "chunkId": "rpc-1",
                "index": index,
                "count": 2,
                "byteLength": len(payload),
                "data": base64.b64encode(part).decode("ascii"),
            }
        )
    await asyncio.sleep(0.05)
    assert seen == [original]
    await transport.aclose()


def test_chunk_reassembler_rejects_out_of_order_sequences():
    reassembler = ChunkReassembler()
    with pytest.raises(ValueError):
        reassembler.push(
            {
                "type": "rpc_chunk",
                "chunkId": "c",
                "index": 1,
                "count": 2,
                "byteLength": 10,
                "data": base64.b64encode(b"abcde").decode("ascii"),
            }
        )


def test_chunk_reassembler_rejects_an_interrupted_sequence():
    reassembler = ChunkReassembler()
    reassembler.push(
        {
            "type": "rpc_chunk",
            "chunkId": "c",
            "index": 0,
            "count": 2,
            "byteLength": 10,
            "data": base64.b64encode(b"abcde").decode("ascii"),
        }
    )
    with pytest.raises(ValueError):
        reassembler.push({"type": "agent_start"})


def test_chunk_reassembler_passes_whole_frames_through():
    assert ChunkReassembler().push({"type": "turn_start"}) == {"type": "turn_start"}
