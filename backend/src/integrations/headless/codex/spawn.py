"""Compose a ``CodexTransport`` over a real ``codex app-server`` subprocess.

Production composition root. The transport itself is duplex-stream-agnostic;
this module is the only place that knows about ``asyncio.subprocess`` so
unit tests against the in-memory fake transport stay decoupled.

Subprocess hardening still to come in later slices:
* crash-loop detector (plan “Risks”)
"""

from __future__ import annotations

import asyncio
import collections
import logging
import shutil
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

from integrations.headless.codex.transport import CodexTransport


logger = logging.getLogger(__name__)


# Keep the last N stderr lines from the codex child so we can explain an
# unexpected exit. Bounded so a chatty codex can't grow this without limit;
# the transport tail-trims further to a char budget when it surfaces them.
_STDERR_TAIL_MAX_LINES = 200


@dataclass
class CodexSubprocess:
    """Owns a spawned codex process and the transport wired to its stdio."""

    process: asyncio.subprocess.Process
    transport: CodexTransport
    # Background task draining the child's stderr into ``stderr_lines``. Kept
    # so ``aclose`` can cancel it; ``None`` only in the degenerate no-stderr
    # spawn.
    stderr_task: Optional["asyncio.Task[None]"] = None
    stderr_lines: Deque[str] = field(default_factory=lambda: collections.deque())

    async def aclose(self) -> None:
        """Tear down the transport, then the subprocess.

        Shutdown ladder:
          1. aclose transport (fails pending response futures)
          2. close child stdin so the child can detect EOF and exit cleanly
          3. wait briefly for natural exit (well-behaved codex case)
          4. SIGTERM as escalation, then SIGKILL after 5s

        Cooperative ``turn/interrupt`` (plan \xa712) lands in a later slice;
        it runs ahead of step 2 to give codex a chance to interrupt a
        running turn before we shut down its input stream.
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
        logger.info("codex subprocess did not exit on EOF; sending SIGTERM")
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning(
                "codex subprocess did not exit after SIGTERM; sending SIGKILL"
            )
            self.process.kill()
            await self.process.wait()


async def spawn_codex_app_server(
    *,
    command: Optional[List[str]] = None,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> CodexSubprocess:
    """Spawn a codex app-server (or a test stand-in) and wire a transport.

    ``command`` defaults to ``[which("codex"), "app-server"]``. Callers pass
    an explicit command in tests (and in unusual deployments where ``codex``
    isn't on the daemon's PATH). The transport's read loop is NOT started
    here — call ``transport.start()`` after the caller has registered
    notification + request handlers.
    """
    if command is None:
        binary = shutil.which("codex")
        if not binary:
            raise RuntimeError(
                "`codex` not found on PATH; install it from https://github.com/openai/codex"
            )
        command = [binary, "app-server"]
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("subprocess pipes did not materialize")

    # Drain the child's stderr into a bounded rolling buffer. This does double
    # duty: (1) an *unread* stderr PIPE eventually fills its OS buffer and
    # blocks codex the moment it writes past it, so we must consume it; (2) the
    # tail explains an unexpected exit when the transport fails pending
    # requests. Codex's own file logging still captures the full stream.
    stderr_lines: Deque[str] = collections.deque(maxlen=_STDERR_TAIL_MAX_LINES)
    stderr_task: Optional["asyncio.Task[None]"] = None
    if process.stderr is not None:
        stderr_task = asyncio.create_task(_drain_stderr(process.stderr, stderr_lines))

    transport = CodexTransport(
        reader=process.stdout,
        writer=process.stdin,
        stderr_tail=lambda: _format_stderr_tail(stderr_lines),
    )
    return CodexSubprocess(
        process=process,
        transport=transport,
        stderr_task=stderr_task,
        stderr_lines=stderr_lines,
    )


async def _drain_stderr(stream: asyncio.StreamReader, buffer: "Deque[str]") -> None:
    """Continuously read the child's stderr into ``buffer`` until EOF.

    Runs for the life of the subprocess. Decodes leniently — codex stderr is
    human log text, not a wire protocol, so a stray non-UTF8 byte must not kill
    the drain (which would re-introduce the pipe-fill hang).
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


# Char budget for the surfaced tail — enough to carry a Rust panic / traceback
# without dumping the whole rolling buffer into a chat error.
_STDERR_TAIL_MAX_CHARS = 4000


def _format_stderr_tail(buffer: "Deque[str]") -> str:
    if not buffer:
        return ""
    return "\n".join(buffer)[-_STDERR_TAIL_MAX_CHARS:]


__all__ = [
    "CodexSubprocess",
    "spawn_codex_app_server",
]
