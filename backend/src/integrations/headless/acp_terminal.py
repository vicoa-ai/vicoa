"""ACP client-side terminal support.

The five agent→client ``terminal/*`` methods, implemented over
:mod:`subprocess`. Advertising ``clientCapabilities.terminal`` moves the
agent's shell commands into processes Vicoa owns: they die with the session
instead of outliving it, their output is bounded, and a stuck command can be
killed from our side rather than only from the agent's.

Lifetime is the agent's to manage — it calls ``terminal/release`` when done —
but :py:meth:`TerminalManager.close_all` is the backstop for a session that
ends mid-command.

Threading: ``wait_for_exit`` blocks its caller by design, so every method here
must be safe to call from several threads at once. The ACP client answers each
inbound request on its own thread precisely so this can block.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from typing import Any, Dict, List, Optional


#: Fallback cap when the agent names no ``outputByteLimit``. Bounded on purpose:
#: the buffer is held in memory for the life of the terminal, and an agent that
#: runs a chatty build without a limit would otherwise grow it without end.
DEFAULT_OUTPUT_BYTE_LIMIT = 1_000_000

#: Seconds to wait for a SIGTERM to land before escalating to SIGKILL.
TERMINATE_GRACE_SECONDS = 2.0


class TerminalNotFound(KeyError):
    """The agent named a terminal that was never created or already released."""


class _Terminal:
    """One running command and its bounded output buffer."""

    def __init__(
        self,
        terminal_id: str,
        process: subprocess.Popen,
        output_byte_limit: Optional[int],
    ) -> None:
        self.id = terminal_id
        self.process = process
        self.output_byte_limit = output_byte_limit
        self._lock = threading.Lock()
        self._output = bytearray()
        self._truncated = False
        self._exit: Optional[Dict[str, Any]] = None
        self._exited = threading.Event()
        self._readers: List[threading.Thread] = []

    # -- output ---------------------------------------------------------

    def append(self, chunk: bytes) -> None:
        with self._lock:
            self._output.extend(chunk)
            limit = self.output_byte_limit
            if limit and len(self._output) > limit:
                # Drop from the front: the tail is what a caller reading a
                # build log actually wants, and it is what the ACP spec asks
                # for alongside the truncated flag.
                del self._output[: len(self._output) - limit]
                self._truncated = True

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            payload: Dict[str, Any] = {
                "output": self._output.decode("utf-8", errors="replace"),
                "truncated": self._truncated,
            }
            if self._exit is not None:
                payload["exitStatus"] = self._exit
            return payload

    # -- lifecycle ------------------------------------------------------

    def start_readers(self) -> None:
        for stream in (self.process.stdout, self.process.stderr):
            if stream is None:
                continue
            thread = threading.Thread(
                target=self._pump, args=(stream,), daemon=True, name=f"term-{self.id}"
            )
            thread.start()
            self._readers.append(thread)
        threading.Thread(
            target=self._await_exit, daemon=True, name=f"term-wait-{self.id}"
        ).start()

    def _pump(self, stream: Any) -> None:
        try:
            for chunk in iter(lambda: stream.read(4096), b""):
                if not chunk:
                    break
                self.append(chunk)
        except Exception:
            # A closed pipe during teardown is normal; the exit status is the
            # signal that matters and it is recorded separately.
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def _await_exit(self) -> None:
        code = self.process.wait()
        with self._lock:
            # POSIX reports a signal death as a negative return code.
            if code is not None and code < 0:
                self._exit = {"exitCode": None, "signal": signal.Signals(-code).name}
            else:
                self._exit = {"exitCode": code, "signal": None}
        self._exited.set()

    def wait_for_exit(self) -> Dict[str, Any]:
        self._exited.wait()
        with self._lock:
            return dict(self._exit or {"exitCode": None, "signal": None})

    def has_exited(self) -> bool:
        return self._exited.is_set()

    def _signal(self, sig: int, *, fallback: Any) -> None:
        """Signal the whole process group, falling back to the leader.

        The group is what matters: the command is usually a shell that forked
        children, and signalling only the leader leaves `npm run dev`'s server
        running after the session that started it is gone. ``killpg`` is POSIX;
        on Windows (and if the group is already reaped) we fall back to
        Popen's own method.
        """
        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(self.process.pid), sig)
                return
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            fallback()
        except Exception:
            pass

    def terminate(self) -> None:
        """SIGTERM, then SIGKILL if it does not land. Safe to call twice."""
        if self._exited.is_set():
            return
        self._signal(signal.SIGTERM, fallback=self.process.terminate)
        if self._exited.wait(TERMINATE_GRACE_SECONDS):
            return
        self._signal(signal.SIGKILL, fallback=self.process.kill)


class TerminalManager:
    """The ``terminal/*`` half of the ACP client interface."""

    def __init__(self, *, default_cwd: str, log: Any = None) -> None:
        self._default_cwd = default_cwd
        self._log = log or (lambda _msg: None)
        self._terminals: Dict[str, _Terminal] = {}
        self._lock = threading.Lock()
        self._next_id = 0

    def _allocate_id(self) -> str:
        with self._lock:
            self._next_id += 1
            return f"term-{self._next_id}"

    def _get(self, terminal_id: str) -> _Terminal:
        with self._lock:
            terminal = self._terminals.get(terminal_id)
        if terminal is None:
            raise TerminalNotFound(f"Unknown terminalId: {terminal_id}")
        return terminal

    # -- ACP methods ----------------------------------------------------

    def create(self, params: Dict[str, Any]) -> Dict[str, Any]:
        command = str(params.get("command") or "").strip()
        if not command:
            raise ValueError("terminal/create requires a command")
        args = [str(a) for a in (params.get("args") or [])]

        # ACP passes env as an array of {name, value}; absent means inherit.
        env: Optional[Dict[str, str]] = None
        env_entries = params.get("env")
        if isinstance(env_entries, list):
            env = dict(os.environ)
            for entry in env_entries:
                if isinstance(entry, dict) and entry.get("name"):
                    env[str(entry["name"])] = str(entry.get("value") or "")

        limit = params.get("outputByteLimit")
        output_byte_limit = (
            int(limit)
            if isinstance(limit, int) and limit > 0
            else DEFAULT_OUTPUT_BYTE_LIMIT
        )

        process = subprocess.Popen(
            [command, *args],
            cwd=str(params.get("cwd") or self._default_cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # Its own process group, so _signal() can reach the whole tree a
            # shell command spawns rather than only the leader — and so a
            # Ctrl-C in the terminal Vicoa itself runs in does not travel down
            # into the agent's commands.
            start_new_session=True,
        )

        terminal_id = self._allocate_id()
        terminal = _Terminal(terminal_id, process, output_byte_limit)
        terminal.start_readers()
        with self._lock:
            self._terminals[terminal_id] = terminal
        self._log(f"[ACP] terminal {terminal_id} started: {command} {' '.join(args)}")
        return {"terminalId": terminal_id}

    def output(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self._get(str(params.get("terminalId") or "")).snapshot()

    def wait_for_exit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self._get(str(params.get("terminalId") or "")).wait_for_exit()

    def kill(self, params: Dict[str, Any]) -> Dict[str, Any]:
        # Kill leaves the terminal readable: the agent still wants the output
        # of the command it just stopped. Only release removes it.
        self._get(str(params.get("terminalId") or "")).terminate()
        return {}

    def release(self, params: Dict[str, Any]) -> Dict[str, Any]:
        terminal_id = str(params.get("terminalId") or "")
        terminal = self._get(terminal_id)
        terminal.terminate()
        with self._lock:
            self._terminals.pop(terminal_id, None)
        return {}

    # -- teardown -------------------------------------------------------

    def close_all(self) -> None:
        """Stop every terminal still running. Backstop for session shutdown."""
        with self._lock:
            terminals = list(self._terminals.values())
            self._terminals.clear()
        for terminal in terminals:
            terminal.terminate()
