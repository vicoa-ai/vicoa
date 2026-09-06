"""Compose a :class:`PiTransport` over a real ``pi`` / ``omp`` subprocess.

Production composition root, mirroring ``codex/spawn.py``: the transport is
stream-agnostic, and this is the only module that knows about
``asyncio.subprocess`` so the transport tests stay decoupled from process
management.

The stderr drain does double duty. An unread stderr PIPE eventually fills its
OS buffer and blocks the child the moment it writes past it, so it must be
consumed; and the tail is what explains an unexpected exit. That second job is
load-bearing for this agent family in particular — both CLIs exit 1 *before
emitting a single frame* when no model is configured::

    No models available. Use /login or set an API key environment variable.

Without the tail that surfaces as a bare "process exited with code 1".
"""

from __future__ import annotations

import asyncio
import collections
import logging
import os
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

from integrations.headless.pi_family.transport import PiTransport


logger = logging.getLogger(__name__)


_STDERR_TAIL_MAX_LINES = 200

#: Buffer ceiling for one physical JSONL line, handed to the child's
#: ``StreamReader``.
#:
#: **Load-bearing.** ``asyncio``'s default is 64 KiB, and a ``StreamReader``
#: whose ``readline`` overruns it raises ``LimitOverrunError`` *and leaves the
#: data in the buffer*, so the read loop cannot recover — the transport simply
#: dies. This is not hypothetical: it was hit on the very first live bring-up,
#: where omp's ``get_available_models`` response (dozens of models with full
#: capability blocks) is comfortably over 64 KiB.
#:
#: The protocol's own ceiling for a physical line is 1 MiB
#: (``MAX_RPC_FRAME_BYTES``); anything larger is split into ``rpc_chunk``
#: frames, which are smaller still. 2 MiB therefore covers every legal frame
#: with room to spare, and a line past it is a protocol violation rather than
#: something to tolerate.
STREAM_READER_LIMIT = 2 * 1024 * 1024
#: Char budget for the surfaced tail — enough for a stack trace without
#: dumping the whole rolling buffer into a chat error.
_STDERR_TAIL_MAX_CHARS = 4000


@dataclass
class PiSubprocess:
    """Owns a spawned Pi-family process and the transport wired to its stdio."""

    process: asyncio.subprocess.Process
    transport: PiTransport
    stderr_task: Optional["asyncio.Task[None]"] = None
    stderr_lines: Deque[str] = field(default_factory=collections.deque)

    def stderr_tail(self) -> str:
        return _format_stderr_tail(self.stderr_lines)

    async def aclose(self) -> None:
        """Tear down the transport, then the subprocess.

        Ladder: close the transport (fails pending futures) -> close stdin so
        the child sees EOF (both CLIs exit on it) -> brief wait -> SIGTERM ->
        SIGKILL. Cooperative ``abort`` of a running turn happens one layer up,
        in the session, before this is ever called.
        """
        await self.transport.aclose()
        if self.stderr_task is not None and not self.stderr_task.done():
            self.stderr_task.cancel()
        if self.process.stdin is not None and not self.process.stdin.is_closing():
            try:
                self.process.stdin.close()
            except (BrokenPipeError, OSError):
                pass
        if self.process.returncode is not None:
            return
        try:
            await asyncio.wait_for(self.process.wait(), timeout=2.0)
            return
        except asyncio.TimeoutError:
            pass
        logger.info("pi_family: child did not exit on EOF; sending SIGTERM")
        try:
            self.process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(self.process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("pi_family: child did not exit after SIGTERM; SIGKILL")
            try:
                self.process.kill()
            except ProcessLookupError:
                return
            await self.process.wait()


async def spawn_pi_agent(
    *,
    command: List[str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    agent_label: str = "agent",
) -> PiSubprocess:
    """Spawn a Pi-family CLI in RPC mode and wire a transport to its stdio.

    The transport's read loop is deliberately NOT started here — the caller
    registers its event handler first, so no frame can arrive before there is
    somewhere to put it. (omp emits ``ready``, ``extension_ui_request`` and
    ``available_commands_update`` unprompted, immediately.)
    """
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        # See STREAM_READER_LIMIT — the default 64 KiB is far below this
        # protocol's frame size and kills the transport unrecoverably.
        limit=STREAM_READER_LIMIT,
        # Own process group so a stop can reach the whole tree (both CLIs
        # spawn helpers — LSP servers, PTY bash, subagents).
        start_new_session=os.name != "nt",
    )
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("subprocess pipes did not materialize")

    stderr_lines: Deque[str] = collections.deque(maxlen=_STDERR_TAIL_MAX_LINES)
    stderr_task: Optional["asyncio.Task[None]"] = None
    if process.stderr is not None:
        stderr_task = asyncio.create_task(_drain_stderr(process.stderr, stderr_lines))

    transport = PiTransport(
        reader=process.stdout,
        writer=process.stdin,
        stderr_tail=lambda: _format_stderr_tail(stderr_lines),
        agent_label=agent_label,
    )
    return PiSubprocess(
        process=process,
        transport=transport,
        stderr_task=stderr_task,
        stderr_lines=stderr_lines,
    )


async def _drain_stderr(stream: asyncio.StreamReader, buffer: "Deque[str]") -> None:
    """Read the child's stderr into ``buffer`` until EOF.

    Decodes leniently — this is human log text, not a wire protocol, so a
    stray non-UTF8 byte must not kill the drain and re-introduce the
    pipe-fill hang.
    """
    while True:
        try:
            line = await stream.readline()
        except asyncio.CancelledError:
            raise
        except Exception:
            return
        if not line:
            return
        buffer.append(line.decode("utf-8", "replace").rstrip("\n"))


def _format_stderr_tail(buffer: "Deque[str]") -> str:
    if not buffer:
        return ""
    return "\n".join(buffer)[-_STDERR_TAIL_MAX_CHARS:]


__all__ = ["STREAM_READER_LIMIT", "PiSubprocess", "spawn_pi_agent"]
