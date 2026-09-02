"""Tracer-bullet test for the native ``codex app-server`` session.

Exercises the spine of the final architecture end-to-end:

    user message -> turn/start -> item/completed(agentMessage) -> vicoa write

against a real ``CodexTransport`` driven by paired in-memory pipes. Everything
else (permission flow, plan mode, slash commands, thread resume, more
item.type variants, cancel) plugs into this skeleton in later slices.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import defaultdict
from typing import Any, Dict, List

from _fakes import FakeAsyncVicoaClient

from integrations.headless.codex.transport import CodexTransport
from integrations.headless.codex_app_server import CodexAppServerSession


# ---------------------------------------------------------------------------
# In-memory codex stdio pipe
# ---------------------------------------------------------------------------


class FakeCodexPipe:
    """One direction of an in-memory codex stdio pipe.

    Satisfies the read/write surface the transport expects AND exposes
    test-side helpers (``feed_message`` / ``read_message``) so a scripted
    handler can drive the protocol without re-implementing framing.
    """

    def __init__(self) -> None:
        self._buf = b""
        self._q: "asyncio.Queue[bytes]" = asyncio.Queue()
        self._closed = False
        self.requests_by_method: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.notifications_by_method: Dict[str, List[Dict[str, Any]]] = defaultdict(
            list
        )

    # ---- Transport read/write surface ----
    async def readline(self) -> bytes:
        while b"\n" not in self._buf:
            chunk = await self._q.get()
            if not chunk:
                # Sentinel for EOF
                return self._buf
            self._buf += chunk
        line, _, self._buf = self._buf.partition(b"\n")
        return line + b"\n"

    def write(self, data: bytes) -> None:
        self._q.put_nowait(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self._closed = True
        self._q.put_nowait(b"")

    # ---- Test-side helpers ----
    async def read_message(self) -> Dict[str, Any]:
        line = await self.readline()
        if not line:
            raise EOFError("pipe closed")
        msg = json.loads(line.decode("utf-8"))
        method = msg.get("method")
        if method is not None:
            if "id" in msg:
                self.requests_by_method[method].append(msg)
            else:
                self.notifications_by_method[method].append(msg)
        return msg

    def feed_message(self, obj: Dict[str, Any]) -> None:
        line = (json.dumps(obj) + "\n").encode("utf-8")
        self._q.put_nowait(line)


async def scripted_handshake_replies(
    session_to_codex: FakeCodexPipe,
    codex_to_session: FakeCodexPipe,
    *,
    agent_text: str,
    thread_id: str = "thread-1",
    turn_id: str = "turn-1",
) -> None:
    """Drive a happy-path turn against a real ``CodexTransport``.

    Reads JSON-RPC frames off ``session_to_codex`` (what the SUT wrote),
    pattern-matches by method, and feeds scripted replies / notifications
    onto ``codex_to_session``. Returns after dispatching ``turn/completed``.
    """
    while True:
        msg = await session_to_codex.read_message()
        method = msg.get("method")
        msg_id = msg.get("id")

        if method == "initialize":
            codex_to_session.feed_message(
                {"jsonrpc": "2.0", "id": msg_id, "result": {}}
            )
        elif method == "initialized":
            # notification, no reply
            pass
        elif method == "thread/start":
            codex_to_session.feed_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"thread": {"id": thread_id}},
                }
            )
        elif method == "turn/start":
            codex_to_session.feed_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"turn": {"id": turn_id, "status": "completed"}},
                }
            )
            codex_to_session.feed_message(
                {
                    "jsonrpc": "2.0",
                    "method": "turn/started",
                    "params": {"threadId": thread_id, "turnId": turn_id},
                }
            )
            codex_to_session.feed_message(
                {
                    "jsonrpc": "2.0",
                    "method": "item/completed",
                    "params": {
                        "threadId": thread_id,
                        "turnId": turn_id,
                        "item": {"type": "agentMessage", "text": agent_text},
                    },
                }
            )
            codex_to_session.feed_message(
                {
                    "jsonrpc": "2.0",
                    "method": "turn/completed",
                    "params": {
                        "threadId": thread_id,
                        "turn": {"id": turn_id, "status": "completed"},
                    },
                }
            )
            return
        else:
            raise AssertionError(f"unhandled SUT method on session->codex: {method!r}")


# ---------------------------------------------------------------------------
# Tracer-bullet test
# ---------------------------------------------------------------------------


async def test_turn_yields_agent_message_row():
    """One user message produces one AGENT row in vicoa, status returns to
    ``awaiting_input``, and ``turn/start`` carried the user's text through."""
    session_to_codex = FakeCodexPipe()
    codex_to_session = FakeCodexPipe()
    transport = CodexTransport(reader=codex_to_session, writer=session_to_codex)
    vicoa_client = FakeAsyncVicoaClient()
    instance_id = "inst-1"

    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id=instance_id,
        cwd="/tmp/codex-tracer-cwd",
        transport=transport,
    )

    script_task = asyncio.create_task(
        scripted_handshake_replies(
            session_to_codex,
            codex_to_session,
            agent_text="hi back",
        )
    )

    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        await asyncio.wait_for(session.on_user_message("hello"), timeout=2.0)
        await asyncio.wait_for(script_task, timeout=2.0)
    finally:
        if not script_task.done():
            script_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script_task
        await session.aclose()

    # turn/start carried the user's text and the resolved thread id
    turn_starts = session_to_codex.requests_by_method["turn/start"]
    assert len(turn_starts) == 1, "expected exactly one turn/start"
    params = turn_starts[0]["params"]
    # Codex 0.131.0+ ContentItem variants: text / image / localImage / skill /
    # mention. (Plan said "input_text" — wrong; live codex rejects -32600.)
    assert params["input"] == [{"type": "text", "text": "hello"}]
    assert params["threadId"] == "thread-1"

    # One AGENT row written to vicoa with the scripted agentMessage text
    assert len(vicoa_client.sent_messages) == 1
    sent = vicoa_client.sent_messages[0]
    assert sent["content"] == "hi back"
    assert sent["agent_instance_id"] == instance_id

    # Session returned to awaiting_input after turn/completed
    assert session.status == "AWAITING_INPUT"


async def test_turn_with_image_attachments_sends_local_image_items(
    tmp_path, monkeypatch
):
    """Image attachments are downloaded to local files and passed to codex as
    ``localImage`` input items; failed downloads degrade to a text note."""
    import integrations.headless.codex_app_server as codex_app_server_module
    from vicoa.attachments import AttachmentRef

    monkeypatch.setattr(
        codex_app_server_module, "attachments_dir", lambda _instance_id: tmp_path
    )

    session_to_codex = FakeCodexPipe()
    codex_to_session = FakeCodexPipe()
    transport = CodexTransport(reader=codex_to_session, writer=session_to_codex)
    vicoa_client = FakeAsyncVicoaClient()
    vicoa_client.attachments = {"att-ok": (b"png-bytes", "image/png")}

    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-img",
        cwd="/tmp/codex-tracer-cwd",
        transport=transport,
    )

    script_task = asyncio.create_task(
        scripted_handshake_replies(
            session_to_codex,
            codex_to_session,
            agent_text="looked at it",
        )
    )

    refs = (
        AttachmentRef("att-ok", "image/png", "shot.png"),
        AttachmentRef("att-missing", "image/jpeg", "lost.jpg"),
    )
    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        await asyncio.wait_for(
            session.deliver_user_message("what is this", refs), timeout=2.0
        )
        await asyncio.wait_for(script_task, timeout=2.0)
    finally:
        if not script_task.done():
            script_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script_task
        await session.aclose()

    params = session_to_codex.requests_by_method["turn/start"][0]["params"]
    text_item, image_item = params["input"]
    assert text_item["type"] == "text"
    assert "what is this" in text_item["text"]
    assert "lost.jpg" in text_item["text"]  # unavailable note for failed download
    assert image_item == {"type": "localImage", "path": str(tmp_path / "att-ok.png")}
    assert (tmp_path / "att-ok.png").read_bytes() == b"png-bytes"
    assert session.active_turn_id is None


# ---------------------------------------------------------------------------
# Slice 3: thread resume
# ---------------------------------------------------------------------------


async def _drive_bringup(
    s2c: FakeCodexPipe,
    c2s: FakeCodexPipe,
    *,
    expect_resume: bool,
    resume_outcome: str = "ok",
    resume_thread_id: str = "existing-thread-id",
    start_thread_id: str = "fresh-thread-id",
) -> None:
    """Drive the initialize / initialized / (resume | start) handshake.

    ``resume_outcome`` controls the simulated codex behavior on
    ``thread/resume``: ``"ok"`` (resume succeeds), ``"not_found"`` (resume
    errors and the session must fall back to ``thread/start``). The helper
    only runs to the end of bring-up — turn drivers are separate.
    """
    msg = await s2c.read_message()
    assert msg["method"] == "initialize"
    c2s.feed_message({"jsonrpc": "2.0", "id": msg["id"], "result": {}})

    msg = await s2c.read_message()
    assert msg["method"] == "initialized"

    if expect_resume:
        msg = await s2c.read_message()
        assert msg["method"] == "thread/resume"
        if resume_outcome == "ok":
            c2s.feed_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": {"thread": {"id": resume_thread_id}},
                }
            )
            return
        # Simulated codex rejects the resume (file missing, schema drift, …).
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "id": msg["id"],
                "error": {"code": -32602, "message": "thread not_found"},
            }
        )

    msg = await s2c.read_message()
    assert msg["method"] == "thread/start"
    c2s.feed_message(
        {
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {"thread": {"id": start_thread_id}},
        }
    )


async def test_start_with_thread_id_calls_resume_and_keeps_id():
    s2c = FakeCodexPipe()
    c2s = FakeCodexPipe()
    transport = CodexTransport(reader=c2s, writer=s2c)
    vicoa_client = FakeAsyncVicoaClient()
    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-1",
        cwd="/tmp/codex-resume-cwd",
        transport=transport,
        thread_id="existing-thread-id",
    )

    script = asyncio.create_task(_drive_bringup(s2c, c2s, expect_resume=True))
    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        await asyncio.wait_for(script, timeout=2.0)
    finally:
        if not script.done():
            script.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script
        await session.aclose()

    assert "thread/resume" in s2c.requests_by_method
    assert "thread/start" not in s2c.requests_by_method
    assert session.thread_id == "existing-thread-id"
    assert session.status == "AWAITING_INPUT"


async def test_start_with_thread_id_falls_back_when_resume_errors():
    s2c = FakeCodexPipe()
    c2s = FakeCodexPipe()
    transport = CodexTransport(reader=c2s, writer=s2c)
    vicoa_client = FakeAsyncVicoaClient()
    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-1",
        cwd="/tmp/codex-resume-cwd",
        transport=transport,
        thread_id="stale-thread-id",
    )

    script = asyncio.create_task(
        _drive_bringup(
            s2c,
            c2s,
            expect_resume=True,
            resume_outcome="not_found",
            start_thread_id="fresh-thread-id",
        )
    )
    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        await asyncio.wait_for(script, timeout=2.0)
    finally:
        if not script.done():
            script.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script
        await session.aclose()

    assert "thread/resume" in s2c.requests_by_method
    assert "thread/start" in s2c.requests_by_method
    # Stale id is replaced with the fresh one — callers (daemon) read this
    # back to persist into instance_metadata.codex_thread_id.
    assert session.thread_id == "fresh-thread-id"
    assert session.status == "AWAITING_INPUT"


# ---------------------------------------------------------------------------
# Slice 4: permission flow for item/commandExecution/requestApproval
# ---------------------------------------------------------------------------


async def _wait_until(predicate, *, timeout: float = 2.0) -> None:
    """Poll-await a synchronous predicate. Used to detect that the wrapper
    has posted the permission prompt to vicoa before the test delivers the
    reply. Polling beats hooks here because the FakeAsyncVicoaClient's
    permission_reply path expects a runner attribute shape that's
    claude-specific; this keeps the codex test self-contained."""
    elapsed = 0.0
    step = 0.01
    while elapsed < timeout:
        if predicate():
            return
        await asyncio.sleep(step)
        elapsed += step
    raise AssertionError("predicate never became true within timeout")


async def _drive_permission_turn(
    s2c: FakeCodexPipe,
    c2s: FakeCodexPipe,
    *,
    agent_text: str = "ok",
    thread_id: str = "thread-1",
    turn_id: str = "turn-1",
    approval_request_id: int = 1001,
) -> None:
    """Drive bring-up + one turn that triggers an inbound approval request.

    Synchronizes with the SUT: writes turn/start response, emits the
    requestApproval frame, *waits* for the SUT's JSON-RPC reply on s2c
    (recorded in ``requests_by_method`` keyed by method=None won't work —
    responses don't have method, they have id. So we read messages directly
    until we see one whose id matches the approval_request_id).
    """
    await _drive_bringup(s2c, c2s, expect_resume=False)

    msg = await s2c.read_message()
    assert msg["method"] == "turn/start"
    c2s.feed_message(
        {
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {"turn": {"id": turn_id, "status": "completed"}},
        }
    )
    c2s.feed_message(
        {
            "jsonrpc": "2.0",
            "method": "turn/started",
            "params": {"threadId": thread_id, "turnId": turn_id},
        }
    )
    # Inbound request: codex asks us for approval on a shell command.
    c2s.feed_message(
        {
            "jsonrpc": "2.0",
            "id": approval_request_id,
            "method": "item/commandExecution/requestApproval",
            "params": {
                "command": "ls /tmp",
                "cwd": "/tmp",
                "reason": "inspect tmpdir before write",
            },
        }
    )
    # Wait for the SUT's reply to the approval request. Drain any unrelated
    # frames (none expected in this slice) until we see the matching id.
    while True:
        reply = await s2c.read_message()
        if reply.get("id") == approval_request_id:
            break
    # Sanity: the reply must be a result, not an error.
    assert "result" in reply
    # Now emit the remaining turn lifecycle.
    c2s.feed_message(
        {
            "jsonrpc": "2.0",
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "item": {"type": "agentMessage", "text": agent_text},
            },
        }
    )
    c2s.feed_message(
        {
            "jsonrpc": "2.0",
            "method": "turn/completed",
            "params": {
                "threadId": thread_id,
                "turn": {"id": turn_id, "status": "completed"},
            },
        }
    )


async def test_command_approval_routes_user_reply_back_as_decision():
    s2c = FakeCodexPipe()
    c2s = FakeCodexPipe()
    transport = CodexTransport(reader=c2s, writer=s2c)
    vicoa_client = FakeAsyncVicoaClient()
    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-1",
        cwd="/tmp/codex-perm-cwd",
        transport=transport,
    )

    script = asyncio.create_task(_drive_permission_turn(s2c, c2s, agent_text="done"))
    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        turn = asyncio.create_task(session.deliver_user_message("hello"))
        # Wait for the permission prompt to land in vicoa.
        await _wait_until(
            lambda: any(
                "[OPTIONS]" in (m.get("content") or "")
                for m in vicoa_client.sent_messages
            )
        )
        # User picks Accept. Route it through the same WS-new-message path.
        await session.deliver_user_message("Accept")
        await asyncio.wait_for(turn, timeout=2.0)
        await asyncio.wait_for(script, timeout=2.0)
    finally:
        if not script.done():
            script.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script
        await session.aclose()

    # The permission prompt was POSTed with requires_user_input=True
    prompt_calls = [
        m for m in vicoa_client.sent_messages if "[OPTIONS]" in (m.get("content") or "")
    ]
    assert len(prompt_calls) == 1
    assert prompt_calls[0]["requires_user_input"] is True
    assert "ls /tmp" in prompt_calls[0]["content"]

    # The approval reply written back to codex carried decision="accept".
    # Decode the message we wrote to s2c with id=1001 directly from the pipe's
    # captured frames — `requests_by_method` only tracks frames with a method,
    # but responses don't have one, so check the queue-buffered raw side.
    # The script already asserted the response existed and was a result; the
    # downstream item/completed -> vicoa write is what we check next.
    agent_replies = [
        m for m in vicoa_client.sent_messages if m.get("content") == "done"
    ]
    assert len(agent_replies) == 1, (
        "agentMessage item after approved command should produce one vicoa row"
    )

    assert session.status == "AWAITING_INPUT"
    assert session.active_turn_id is None


async def test_command_approval_decline_sends_decline_decision():
    """Cycle-twin of the accept test: the user replies 'Decline' and the
    JSON-RPC reply to codex carries decision='decline'."""
    s2c = FakeCodexPipe()
    c2s = FakeCodexPipe()
    transport = CodexTransport(reader=c2s, writer=s2c)
    vicoa_client = FakeAsyncVicoaClient()
    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-1",
        cwd="/tmp/codex-perm-cwd",
        transport=transport,
    )

    # Capture the response frame as it flows by inspecting the raw write
    # callback. Instead of poking at internals, observe the c2s/s2c log
    # directly: extend FakeCodexPipe in-test by sniffing the queue.
    captured_responses: List[Dict[str, Any]] = []

    # Wrap _drive_permission_turn to capture the response.
    async def driver():
        await _drive_bringup(s2c, c2s, expect_resume=False)
        msg = await s2c.read_message()
        assert msg["method"] == "turn/start"
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {"turn": {"id": "turn-1", "status": "completed"}},
            }
        )
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "id": 1001,
                "method": "item/commandExecution/requestApproval",
                "params": {"command": "rm -rf /etc", "cwd": "/", "reason": "scary"},
            }
        )
        while True:
            r = await s2c.read_message()
            if r.get("id") == 1001:
                captured_responses.append(r)
                break
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1", "status": "completed"},
                },
            }
        )

    script = asyncio.create_task(driver())
    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        turn = asyncio.create_task(session.deliver_user_message("look around"))
        await _wait_until(
            lambda: any(
                "[OPTIONS]" in (m.get("content") or "")
                for m in vicoa_client.sent_messages
            )
        )
        await session.deliver_user_message("Decline")
        await asyncio.wait_for(turn, timeout=2.0)
        await asyncio.wait_for(script, timeout=2.0)
    finally:
        if not script.done():
            script.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script
        await session.aclose()

    assert captured_responses, "codex must observe a JSON-RPC reply to id=1001"
    assert captured_responses[0]["result"] == {"decision": "decline"}


# ---------------------------------------------------------------------------
# Slice 6: cancel / turn/interrupt
# ---------------------------------------------------------------------------


async def _drive_interrupt_turn(
    s2c: FakeCodexPipe,
    c2s: FakeCodexPipe,
    *,
    thread_id: str = "thread-1",
    turn_id: str = "turn-1",
) -> None:
    """Drive bring-up + turn/start, then *wait* for turn/interrupt before
    closing the turn out. Mirrors codex's actual behaviour: an interrupted
    turn still terminates with a ``turn/completed`` notification."""
    await _drive_bringup(s2c, c2s, expect_resume=False, start_thread_id=thread_id)
    msg = await s2c.read_message()
    assert msg["method"] == "turn/start"
    c2s.feed_message(
        {
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {"turn": {"id": turn_id, "status": "completed"}},
        }
    )
    # Wait for the SUT-initiated interrupt.
    msg = await s2c.read_message()
    assert msg["method"] == "turn/interrupt"
    assert msg["params"]["threadId"] == thread_id
    assert msg["params"]["turnId"] == turn_id
    c2s.feed_message({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
    c2s.feed_message(
        {
            "jsonrpc": "2.0",
            "method": "turn/completed",
            "params": {
                "threadId": thread_id,
                "turn": {"id": turn_id, "status": "completed"},
            },
        }
    )


async def test_interrupt_sends_turn_interrupt_and_unblocks_turn():
    s2c = FakeCodexPipe()
    c2s = FakeCodexPipe()
    transport = CodexTransport(reader=c2s, writer=s2c)
    vicoa_client = FakeAsyncVicoaClient()
    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-1",
        cwd="/tmp/codex-interrupt-cwd",
        transport=transport,
    )

    script = asyncio.create_task(_drive_interrupt_turn(s2c, c2s))
    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        turn = asyncio.create_task(session.on_user_message("write a poem"))
        # Wait for the turn to be in-flight (turn/start response observed).
        await _wait_until(lambda: session.active_turn_id is not None)
        await session.interrupt()
        await asyncio.wait_for(turn, timeout=2.0)
        await asyncio.wait_for(script, timeout=2.0)
    finally:
        if not script.done():
            script.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script
        await session.aclose()

    assert "turn/interrupt" in s2c.requests_by_method
    assert session.status == "AWAITING_INPUT"
    assert session.active_turn_id is None


async def test_interrupt_during_pending_permission_cancels_decision():
    """Interrupting while a permission prompt is open must let the handler
    reply ``decision=cancel`` so codex stops waiting on the human."""
    s2c = FakeCodexPipe()
    c2s = FakeCodexPipe()
    transport = CodexTransport(reader=c2s, writer=s2c)
    vicoa_client = FakeAsyncVicoaClient()
    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-1",
        cwd="/tmp/codex-interrupt-perm-cwd",
        transport=transport,
    )

    captured_responses: List[Dict[str, Any]] = []

    async def driver():
        await _drive_bringup(s2c, c2s, expect_resume=False, start_thread_id="thread-1")
        msg = await s2c.read_message()
        assert msg["method"] == "turn/start"
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {"turn": {"id": "turn-1", "status": "completed"}},
            }
        )
        # Inbound approval request the test never answers via user reply.
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "id": 9001,
                "method": "item/commandExecution/requestApproval",
                "params": {"command": "ls", "cwd": "/", "reason": "list"},
            }
        )
        # Two things will land on s2c: the approval response (cancelled)
        # AND turn/interrupt. Both must arrive; order doesn't matter.
        seen_interrupt = False
        while not (seen_interrupt and captured_responses):
            msg = await s2c.read_message()
            if msg.get("method") == "turn/interrupt":
                c2s.feed_message({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
                seen_interrupt = True
            elif msg.get("id") == 9001:
                captured_responses.append(msg)
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1", "status": "completed"},
                },
            }
        )

    script = asyncio.create_task(driver())
    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        turn = asyncio.create_task(session.on_user_message("do stuff"))
        await _wait_until(
            lambda: any(
                "[OPTIONS]" in (m.get("content") or "")
                for m in vicoa_client.sent_messages
            )
        )
        await session.interrupt()
        await asyncio.wait_for(turn, timeout=2.0)
        await asyncio.wait_for(script, timeout=2.0)
    finally:
        if not script.done():
            script.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script
        await session.aclose()

    assert captured_responses, "permission handler must reply on interrupt"
    assert captured_responses[0]["result"] == {"decision": "cancel"}
    assert session.status == "AWAITING_INPUT"


# ---------------------------------------------------------------------------
# Slice 7: file-change approval + AUQ stub + permissions stub
# ---------------------------------------------------------------------------


async def test_file_change_approval_routes_user_reply():
    """User picks Accept on a file-change approval; codex sees decision=accept."""
    s2c = FakeCodexPipe()
    c2s = FakeCodexPipe()
    transport = CodexTransport(reader=c2s, writer=s2c)
    vicoa_client = FakeAsyncVicoaClient()
    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-1",
        cwd="/tmp/codex-fc-cwd",
        transport=transport,
    )

    captured_responses: List[Dict[str, Any]] = []

    async def driver():
        await _drive_bringup(s2c, c2s, expect_resume=False, start_thread_id="thread-1")
        msg = await s2c.read_message()
        assert msg["method"] == "turn/start"
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {"turn": {"id": "turn-1", "status": "completed"}},
            }
        )
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "id": 2001,
                "method": "item/fileChange/requestApproval",
                "params": {
                    "files": [
                        {
                            "path": "src/foo.py",
                            "diff": "@@ -1 +1 @@\n-x\n+y\n",
                        }
                    ],
                    "reason": "rename x->y",
                },
            }
        )
        while True:
            r = await s2c.read_message()
            if r.get("id") == 2001:
                captured_responses.append(r)
                break
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1", "status": "completed"},
                },
            }
        )

    script = asyncio.create_task(driver())
    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        turn = asyncio.create_task(session.deliver_user_message("apply that fix"))
        await _wait_until(
            lambda: any(
                "[OPTIONS]" in (m.get("content") or "")
                for m in vicoa_client.sent_messages
            )
        )
        # The prompt must surface the diff so the user knows what they approve.
        prompts = [
            m
            for m in vicoa_client.sent_messages
            if "[OPTIONS]" in (m.get("content") or "")
        ]
        assert "src/foo.py" in prompts[0]["content"]
        await session.deliver_user_message("Accept")
        await asyncio.wait_for(turn, timeout=2.0)
        await asyncio.wait_for(script, timeout=2.0)
    finally:
        if not script.done():
            script.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script
        await session.aclose()

    assert captured_responses and captured_responses[0]["result"] == {
        "decision": "accept"
    }


async def test_user_input_request_routes_to_dashboard_and_replies_to_codex():
    """End-to-end ``item/tool/requestUserInput`` flow:

    1. codex emits the request with one option-type question
    2. session POSTs the prompt to vicoa with ``ask_user_question`` metadata
    3. user picks option index 0 via the dashboard's control reply
    4. session replies to codex with ``{answers: {<question.id>: {answers:
       [label]}}}`` — keyed by codex's question.id (NOT the vicoa question
       text), value is the selected label.
    """
    import base64
    import json as _json

    s2c = FakeCodexPipe()
    c2s = FakeCodexPipe()
    transport = CodexTransport(reader=c2s, writer=s2c)
    vicoa_client = FakeAsyncVicoaClient()
    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-1",
        cwd="/tmp/codex-auq-cwd",
        transport=transport,
    )

    captured_responses: List[Dict[str, Any]] = []
    codex_question = {
        "id": "what_help",
        "header": "Focus",
        "question": "What do you want me to do next?",
        "isOther": False,
        "isSecret": False,
        "options": [
            {"label": "Plan work", "description": "Define approach first."},
            {"label": "Inspect code", "description": "Explore the repo."},
        ],
    }

    async def driver():
        await _drive_bringup(s2c, c2s, expect_resume=False, start_thread_id="thread-1")
        msg = await s2c.read_message()
        assert msg["method"] == "turn/start"
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {"turn": {"id": "turn-1", "status": "completed"}},
            }
        )
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "id": 3001,
                "method": "item/tool/requestUserInput",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "itemId": "call_xyz",
                    "questions": [codex_question],
                },
            }
        )
        while True:
            r = await s2c.read_message()
            if r.get("id") == 3001:
                captured_responses.append(r)
                break
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1", "status": "completed"},
                },
            }
        )

    script = asyncio.create_task(driver())
    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        turn = asyncio.create_task(session.on_user_message("help me"))

        # Wait for the AUQ prompt to land in vicoa.
        await _wait_until(
            lambda: any(
                isinstance(m.get("message_metadata"), dict)
                and "ask_user_question" in (m.get("message_metadata") or {})
                for m in vicoa_client.sent_messages
            )
        )
        prompt = next(
            m
            for m in vicoa_client.sent_messages
            if isinstance(m.get("message_metadata"), dict)
            and "ask_user_question" in (m.get("message_metadata") or {})
        )
        auq_payload = prompt["message_metadata"]["ask_user_question"]
        assert prompt["requires_user_input"] is True
        assert prompt["poll_for_reply"] is False
        assert auq_payload["questions"][0]["question"] == (
            "What do you want me to do next?"
        )
        assert auq_payload["questions"][0]["header"] == "Focus"
        assert auq_payload["questions"][0]["options"] == codex_question["options"]
        request_id = auq_payload["request_id"]

        # Simulate the dashboard's control reply: user picks option index 0.
        reply_payload = {
            "answers": [{"mode": "option", "option_index": 0}],
            "display_answers": [{"label": "Plan work"}],
            "request_id": request_id,
            "message_id": None,
        }
        encoded = (
            base64.urlsafe_b64encode(_json.dumps(reply_payload).encode("utf-8"))
            .decode("ascii")
            .rstrip("=")
        )
        control_reply = _json.dumps(
            {
                "type": "control",
                "setting": "ask_user_question",
                "value": f"submit:{encoded}",
            }
        )
        # Route through the same path WS new-messages take.
        assert await session.maybe_route_auq_reply(control_reply)

        await asyncio.wait_for(turn, timeout=2.0)
        await asyncio.wait_for(script, timeout=2.0)
    finally:
        if not script.done():
            script.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script
        await session.aclose()

    assert captured_responses, "AUQ handler must reply to codex"
    # Codex shape: {answers: {<question.id>: {answers: [labels]}}}
    assert captured_responses[0]["result"] == {
        "answers": {"what_help": {"answers": ["Plan work"]}}
    }


async def test_user_input_request_no_questions_replies_empty():
    """Defensive: an empty questions array is a no-op cancel."""
    s2c = FakeCodexPipe()
    c2s = FakeCodexPipe()
    transport = CodexTransport(reader=c2s, writer=s2c)
    vicoa_client = FakeAsyncVicoaClient()
    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-1",
        cwd="/tmp/codex-auq-empty-cwd",
        transport=transport,
    )

    captured_responses: List[Dict[str, Any]] = []

    async def driver():
        await _drive_bringup(s2c, c2s, expect_resume=False, start_thread_id="thread-1")
        msg = await s2c.read_message()
        assert msg["method"] == "turn/start"
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {"turn": {"id": "turn-1", "status": "completed"}},
            }
        )
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "id": 3002,
                "method": "item/tool/requestUserInput",
                "params": {"questions": []},
            }
        )
        while True:
            r = await s2c.read_message()
            if r.get("id") == 3002:
                captured_responses.append(r)
                break
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1", "status": "completed"},
                },
            }
        )

    script = asyncio.create_task(driver())
    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        await asyncio.wait_for(session.on_user_message("hi"), timeout=2.0)
        await asyncio.wait_for(script, timeout=2.0)
    finally:
        if not script.done():
            script.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script
        await session.aclose()

    assert captured_responses[0]["result"] == {"answers": {}}


async def test_permissions_request_auto_stubs_empty_grant():
    """v1 stub: ``item/permissions/requestApproval`` auto-replies empty
    grant scoped to the current turn (plan \xa76 v1 stub)."""
    s2c = FakeCodexPipe()
    c2s = FakeCodexPipe()
    transport = CodexTransport(reader=c2s, writer=s2c)
    vicoa_client = FakeAsyncVicoaClient()
    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-1",
        cwd="/tmp/codex-perm2-cwd",
        transport=transport,
    )

    captured_responses: List[Dict[str, Any]] = []

    async def driver():
        await _drive_bringup(s2c, c2s, expect_resume=False, start_thread_id="thread-1")
        msg = await s2c.read_message()
        assert msg["method"] == "turn/start"
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {"turn": {"id": "turn-1", "status": "completed"}},
            }
        )
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "id": 4001,
                "method": "item/permissions/requestApproval",
                "params": {
                    "requested": {"fs": ["/tmp/extra"], "network": ["example.com"]}
                },
            }
        )
        while True:
            r = await s2c.read_message()
            if r.get("id") == 4001:
                captured_responses.append(r)
                break
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1", "status": "completed"},
                },
            }
        )

    script = asyncio.create_task(driver())
    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        await asyncio.wait_for(
            session.on_user_message("expand permissions"), timeout=2.0
        )
        await asyncio.wait_for(script, timeout=2.0)
    finally:
        if not script.done():
            script.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script
        await session.aclose()

    assert captured_responses, "permissions-request stub must respond"
    assert captured_responses[0]["result"] == {"permissions": {}, "scope": "turn"}


# ---------------------------------------------------------------------------
# Failure surfacing: codex emits `error` + turn.status="failed"
# ---------------------------------------------------------------------------


async def test_failed_turn_surfaces_error_to_vicoa():
    """When codex rejects the request (e.g. model not allowed on the user's
    auth tier), the failure must reach vicoa as a message — otherwise the
    user types and sees nothing forever."""
    s2c = FakeCodexPipe()
    c2s = FakeCodexPipe()
    transport = CodexTransport(reader=c2s, writer=s2c)
    vicoa_client = FakeAsyncVicoaClient()
    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-1",
        cwd="/tmp/codex-fail-cwd",
        transport=transport,
    )

    async def driver():
        await _drive_bringup(s2c, c2s, expect_resume=False, start_thread_id="thread-1")
        msg = await s2c.read_message()
        assert msg["method"] == "turn/start"
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {"turn": {"id": "turn-1", "status": "inProgress"}},
            }
        )
        # Real wire shape captured from a live ChatGPT-auth + gpt-5-codex
        # rejection: the .message field carries a JSON-encoded OpenAI 400
        # body. Renderer should unwrap inner .error.message for readability.
        upstream_message = (
            '{"type":"error","status":400,"error":{"type":"invalid_request_error",'
            '"message":"The \'gpt-5-codex\' model is not supported when using '
            'Codex with a ChatGPT account."}}'
        )
        c2s.feed_message(
            {
                "jsonrpc": "2.0",
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {
                        "id": "turn-1",
                        "status": "failed",
                        "error": {
                            "message": upstream_message,
                            "codexErrorInfo": "other",
                        },
                    },
                },
            }
        )

    script = asyncio.create_task(driver())
    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        await asyncio.wait_for(session.on_user_message("hello"), timeout=2.0)
        await asyncio.wait_for(script, timeout=2.0)
    finally:
        if not script.done():
            script.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script
        await session.aclose()

    # The failure was written to vicoa with a human-readable message —
    # the unwrapped inner error.message, not the JSON-encoded blob.
    assert len(vicoa_client.sent_messages) == 1
    surfaced = vicoa_client.sent_messages[0]["content"]
    assert "Codex turn failed" in surfaced
    assert "gpt-5-codex" in surfaced
    assert "ChatGPT account" in surfaced
    # The JSON envelope must NOT leak into the chat surface.
    assert '"type":"error"' not in surfaced
    assert '"status":400' not in surfaced


async def test_turn_start_bypass_mode_sets_overrides():
    s2c = FakeCodexPipe()
    c2s = FakeCodexPipe()
    transport = CodexTransport(reader=c2s, writer=s2c)
    vicoa_client = FakeAsyncVicoaClient()
    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-1",
        cwd="/tmp/codex-yolo-cwd",
        transport=transport,
        permission_mode="bypassPermissions",
    )

    script_task = asyncio.create_task(
        scripted_handshake_replies(
            s2c, c2s, agent_text="ok", thread_id="thread-1", turn_id="turn-1"
        )
    )
    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        await asyncio.wait_for(session.on_user_message("hi"), timeout=2.0)
        await asyncio.wait_for(script_task, timeout=2.0)
    finally:
        if not script_task.done():
            script_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script_task
        await session.aclose()

    params = s2c.requests_by_method["turn/start"][0]["params"]
    assert params["approvalPolicy"] == "never"
    assert params["sandboxPolicy"] == {"type": "dangerFullAccess"}
    assert params["collaborationMode"]["mode"] == "default"


async def test_turn_start_default_mode_sends_no_overrides():
    """permission_mode='default' (or None) must NOT send approvalPolicy /
    sandboxPolicy / collaborationMode — codex inherits from its own
    ~/.codex/config.toml and any thread-level defaults."""
    s2c = FakeCodexPipe()
    c2s = FakeCodexPipe()
    transport = CodexTransport(reader=c2s, writer=s2c)
    vicoa_client = FakeAsyncVicoaClient()
    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-1",
        cwd="/tmp/codex-default-cwd",
        transport=transport,
        permission_mode="default",
    )

    script_task = asyncio.create_task(
        scripted_handshake_replies(
            s2c, c2s, agent_text="ok", thread_id="thread-1", turn_id="turn-1"
        )
    )
    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        await asyncio.wait_for(session.on_user_message("hi"), timeout=2.0)
        await asyncio.wait_for(script_task, timeout=2.0)
    finally:
        if not script_task.done():
            script_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script_task
        await session.aclose()

    params = s2c.requests_by_method["turn/start"][0]["params"]
    assert "approvalPolicy" not in params
    assert "sandboxPolicy" not in params
    assert "collaborationMode" not in params


async def test_turn_start_passes_model_and_effort_when_set():
    """Session forwards --model / --reasoning-effort overrides on turn/start."""
    s2c = FakeCodexPipe()
    c2s = FakeCodexPipe()
    transport = CodexTransport(reader=c2s, writer=s2c)
    vicoa_client = FakeAsyncVicoaClient()
    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-1",
        cwd="/tmp/codex-model-cwd",
        transport=transport,
        model="gpt-5",
        effort="medium",
    )

    script_task = asyncio.create_task(
        scripted_handshake_replies(
            s2c, c2s, agent_text="ok", thread_id="thread-1", turn_id="turn-1"
        )
    )
    try:
        await asyncio.wait_for(session.start(), timeout=2.0)
        await asyncio.wait_for(session.on_user_message("hi"), timeout=2.0)
        await asyncio.wait_for(script_task, timeout=2.0)
    finally:
        if not script_task.done():
            script_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script_task
        await session.aclose()

    turn_start_params = s2c.requests_by_method["turn/start"][0]["params"]
    assert turn_start_params["model"] == "gpt-5"
    assert turn_start_params["effort"] == "medium"


# ---------------------------------------------------------------------------
# Live model discovery (codex `model/list`)
# ---------------------------------------------------------------------------


async def test_discover_and_report_models_patches_available_models():
    """`model/list` results are cached and PATCHed onto session_config as
    ``available_models`` + ``current_model`` for the mid-session gear."""
    session_to_codex = FakeCodexPipe()
    codex_to_session = FakeCodexPipe()
    transport = CodexTransport(reader=codex_to_session, writer=session_to_codex)
    vicoa_client = FakeAsyncVicoaClient()

    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-models",
        cwd="/tmp/codex-cwd",
        transport=transport,
    )

    async def script_model_list() -> None:
        msg = await session_to_codex.read_message()
        assert msg["method"] == "model/list"
        assert msg["params"].get("includeHidden") is False
        codex_to_session.feed_message(
            {
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {
                    "data": [
                        {
                            "id": "gpt-5.6-terra",
                            "displayName": "GPT-5.6-Terra",
                            "isDefault": True,
                        },
                        {"id": "gpt-5.6-luna", "displayName": "GPT-5.6-Luna"},
                        {"id": "gpt-5.5", "displayName": "GPT-5.5"},
                    ],
                    "nextCursor": None,
                },
            }
        )

    await transport.start()
    script_task = asyncio.create_task(script_model_list())
    try:
        await asyncio.wait_for(session.discover_and_report_models(), timeout=2.0)
        await asyncio.wait_for(script_task, timeout=2.0)
    finally:
        if not script_task.done():
            script_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script_task
        await session.aclose()

    assert session.available_models == [
        {"id": "gpt-5.6-terra", "label": "GPT-5.6-Terra"},
        {"id": "gpt-5.6-luna", "label": "GPT-5.6-Luna"},
        {"id": "gpt-5.5", "label": "GPT-5.5"},
    ]
    assert session.discovered_default_model == "gpt-5.6-terra"

    assert len(vicoa_client.patch_calls) == 1
    sc = vicoa_client.patch_calls[0]["session_config"]
    assert sc["available_models"] == session.available_models
    # No explicit spawn pick -> current_model reflects codex's own default.
    assert sc["current_model"] == "gpt-5.6-terra"


async def test_discover_models_degrades_when_model_list_unsupported():
    """Older codex without ``model/list``: the JSON-RPC error is swallowed,
    ``available_models`` stays empty, and no session_config PATCH is emitted."""
    session_to_codex = FakeCodexPipe()
    codex_to_session = FakeCodexPipe()
    transport = CodexTransport(reader=codex_to_session, writer=session_to_codex)
    vicoa_client = FakeAsyncVicoaClient()

    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-old",
        cwd="/tmp/codex-cwd",
        transport=transport,
    )

    async def script_error() -> None:
        msg = await session_to_codex.read_message()
        assert msg["method"] == "model/list"
        codex_to_session.feed_message(
            {
                "jsonrpc": "2.0",
                "id": msg["id"],
                "error": {"code": -32601, "message": "method not handled: model/list"},
            }
        )

    await transport.start()
    script_task = asyncio.create_task(script_error())
    try:
        await asyncio.wait_for(session.discover_and_report_models(), timeout=2.0)
        await asyncio.wait_for(script_task, timeout=2.0)
    finally:
        if not script_task.done():
            script_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await script_task
        await session.aclose()

    assert session.available_models == []
    assert vicoa_client.patch_calls == []


# ---------------------------------------------------------------------------
# Interrupt with nothing to interrupt.
#
# Codex normally drives AWAITING_INPUT off ``turn/completed``. A Stop pressed
# with no active turn (a stale ACTIVE row, or the click landing between
# ``turn/start`` being sent and its response arriving) used to return
# silently, so the dashboard stayed on "active" with no way to clear it.
# ---------------------------------------------------------------------------


async def test_interrupt_without_active_turn_settles_awaiting_input():
    session_to_codex = FakeCodexPipe()
    codex_to_session = FakeCodexPipe()
    transport = CodexTransport(reader=codex_to_session, writer=session_to_codex)
    vicoa_client = FakeAsyncVicoaClient()

    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-interrupt-idle",
        cwd="/tmp/codex-interrupt-cwd",
        transport=transport,
    )
    session.thread_id = "thread-1"
    session.active_turn_id = None

    await asyncio.wait_for(session.interrupt(), timeout=2.0)

    assert vicoa_client.status_calls, "expected a status write"
    assert vicoa_client.status_calls[-1]["status"] == "AWAITING_INPUT"
    # No turn to interrupt, so nothing should have gone out on the wire.
    assert not session_to_codex.requests_by_method["turn/interrupt"]


# ---------------------------------------------------------------------------
# Reasoning items surface as a collapsed "thinking" card: the rendered text
# still rides in ``content`` (so pre-card clients degrade to inline text) but
# ``message_metadata.thinking`` marks the row so clients wrap it collapsed.
# ---------------------------------------------------------------------------


def _idle_session() -> tuple[CodexAppServerSession, FakeAsyncVicoaClient]:
    """A session wired to a fake vicoa client, with no turn started — enough
    to exercise ``_handle_item`` directly."""
    session_to_codex = FakeCodexPipe()
    codex_to_session = FakeCodexPipe()
    transport = CodexTransport(reader=codex_to_session, writer=session_to_codex)
    vicoa_client = FakeAsyncVicoaClient()
    session = CodexAppServerSession(
        vicoa_client=vicoa_client,
        instance_id="inst-thinking",
        cwd="/tmp/codex-thinking-cwd",
        transport=transport,
    )
    return session, vicoa_client


async def test_reasoning_item_is_tagged_as_thinking():
    session, vicoa_client = _idle_session()

    await session._handle_item({"type": "reasoning", "summary": ["considered A and B"]})

    assert len(vicoa_client.sent_messages) == 1
    sent = vicoa_client.sent_messages[0]
    assert sent["message_metadata"] == {"thinking": {"source": "codex"}}
    # Rendered text still rides in content for pre-card clients.
    assert "considered A and B" in sent["content"]


async def test_agent_message_item_is_not_tagged_as_thinking():
    session, vicoa_client = _idle_session()

    await session._handle_item({"type": "agentMessage", "text": "hello there"})

    assert len(vicoa_client.sent_messages) == 1
    assert vicoa_client.sent_messages[0]["message_metadata"] is None


async def test_empty_reasoning_item_is_dropped():
    session, vicoa_client = _idle_session()

    await session._handle_item({"type": "reasoning", "summary": [], "content": []})

    assert vicoa_client.sent_messages == []
