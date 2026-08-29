"""Agent Client Protocol (ACP) JSON-RPC client.

This module implements a JSON-RPC 2.0 client for communicating with agents that
support the Agent Client Protocol (ACP), such as OpenCode.

Protocol spec: https://agentclientprotocol.com/
"""

import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from queue import Queue, Empty
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger(__name__)


class ACPError(Exception):
    """Base exception for ACP client errors."""

    pass


class ACPMethodNotFound(ACPError):
    """Raised by request handlers to reject an agent→client request.

    ``ACPClient`` translates this into the standard JSON-RPC -32601
    Method-not-found error response, which the ACP spec mandates for
    unknown methods (e.g. fs/terminal calls we never advertised).
    """

    def __init__(self, method: str):
        super().__init__(f"Method not found: {method}")
        self.method = method


@dataclass
class ACPResponse:
    """Response from ACP JSON-RPC request."""

    id: Optional[int]
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def raise_for_error(self):
        """Raise ACPError if response contains an error."""
        if self.error:
            code = self.error.get("code", -1)
            message = self.error.get("message", "Unknown error")
            data = self.error.get("data")
            error_msg = f"ACP Error {code}: {message}"
            if data:
                error_msg += f" ({data})"
            raise ACPError(error_msg)


class ACPClient:
    """JSON-RPC 2.0 client for Agent Client Protocol.

    This client manages bidirectional communication with an ACP-compatible agent
    process via stdin/stdout using newline-delimited JSON (NDJSON).

    Example:
        client = ACPClient(
            command=["opencode", "acp"],
            cwd="/path/to/project",
            on_notification=handle_notification
        )
        client.start()
        response = client.send_request("initialize", {
            "protocolVersion": "2024-11-01"
        })
        client.stop()
    """

    def __init__(
        self,
        command: List[str],
        cwd: str,
        env: Optional[Dict[str, str]] = None,
        on_notification: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_request: Optional[
            Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]]
        ] = None,
        on_error: Optional[Callable[[str], None]] = None,
        log_func: Optional[Callable[[str], None]] = None,
    ):
        """Initialize ACP client.

        Args:
            command: Command to spawn ACP agent (e.g., ["opencode", "acp"])
            cwd: Working directory for the agent process
            env: Environment variables for the agent process
            on_notification: Callback for JSON-RPC notifications (method, params)
            on_request: Callback for JSON-RPC requests from agent (method, params).
                Return value is used as the JSON-RPC response result.
            on_error: Callback for stderr output from agent
            log_func: Optional logging function
        """
        self.command = command
        self.cwd = cwd
        self.env = env or {}
        self.on_notification = on_notification
        self.on_request = on_request
        self.on_error = on_error
        self.log = log_func or (lambda msg: logger.debug(msg))

        self.process: Optional[subprocess.Popen] = None
        self.message_id = 0
        self.pending_responses: Dict[int, Queue] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._id_lock = threading.Lock()
        self._ignored_response_ids: set[int] = set()
        self._timed_out_response_ids: set[int] = set()
        self.on_late_response: Optional[Callable[[int, "ACPResponse"], None]] = None

        # Threading for reading stdout/stderr
        self.stdout_thread: Optional[threading.Thread] = None
        self.stderr_thread: Optional[threading.Thread] = None
        self.running = False

    def start(self):
        """Start the ACP agent process and begin reading output."""
        if self.process is not None:
            raise ACPError("ACP client already started")

        self.log(f"[ACP] Starting agent: {' '.join(self.command)}")
        self.log(f"[ACP] Working directory: {self.cwd}")

        full_env = os.environ.copy()
        full_env.update(self.env)

        # On Windows, npm-installed binaries are .cmd scripts that subprocess
        # cannot find without shell=True, regardless of PATH resolution.
        # CREATE_NO_WINDOW prevents cmd.exe from flashing a console window.
        # The bash installer (curl | bash) targets Git Bash/WSL where sys.platform
        # is "linux", so shell=True is only needed for native Windows (npm install).
        command = list(self.command)
        use_shell = sys.platform == "win32"
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        if sys.platform == "win32" and not shutil.which(command[0]):
            raise FileNotFoundError(
                f"Could not find '{command[0]}' on PATH. "
                f"Install it with: npm install -g opencode-ai"
            )

        # Spawn process
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.cwd,
            env=full_env,
            bufsize=0,  # Unbuffered
            shell=use_shell,
            creationflags=creation_flags,
        )

        self.running = True

        # Start reader threads
        self.stdout_thread = threading.Thread(
            target=self._read_stdout, daemon=True, name="ACP-stdout"
        )
        self.stderr_thread = threading.Thread(
            target=self._read_stderr, daemon=True, name="ACP-stderr"
        )
        self.stdout_thread.start()
        self.stderr_thread.start()

        self.log("[ACP] Agent process started")

    def stop(self):
        """Stop the ACP agent process and cleanup."""
        if not self.process:
            return

        self.log("[ACP] Stopping agent process")
        self.running = False

        try:
            # Close stdin to signal EOF
            if self.process.stdin:
                self.process.stdin.close()

            # Wait for process to exit
            self.process.wait(timeout=5)
            self.log("[ACP] Agent process stopped cleanly")
        except subprocess.TimeoutExpired:
            self.log("[ACP] Agent process did not exit, terminating")
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.log("[ACP] Killing agent process")
                self.process.kill()

        # Wait for threads to finish
        if self.stdout_thread:
            self.stdout_thread.join(timeout=1)
        if self.stderr_thread:
            self.stderr_thread.join(timeout=1)

        self.process = None

    def interrupt_process(self) -> bool:
        """Best-effort interrupt signal for the underlying ACP process."""
        if not self.process:
            return False

        try:
            # Works on POSIX and maps to CTRL_C_EVENT on some Windows setups.
            self.process.send_signal(signal.SIGINT)
            self.log("[ACP] Sent SIGINT to agent process")
            return True
        except Exception as e:
            self.log(f"[ACP] Failed to send SIGINT: {e}")
            return False

    def send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
        cancel_event: Optional[threading.Event] = None,
        cancel_grace_period: float = 0.0,
    ) -> ACPResponse:
        """Send JSON-RPC request and wait for response.

        Args:
            method: JSON-RPC method name
            params: Method parameters (optional)
            timeout: Response timeout in seconds
            cancel_event: Optional event to cancel local wait early
            cancel_grace_period: Optional grace window after cancellation is requested
                before failing locally. If <= 0, cancellation fails immediately.

        Returns:
            ACPResponse with result or error

        Raises:
            ACPError: If request fails or times out
        """
        if not self.process or not self.running:
            raise ACPError("ACP client not running")

        with self._id_lock:
            self.message_id += 1
            request_id = self.message_id

        # Create response queue
        response_queue: Queue = Queue()
        with self._pending_lock:
            self.pending_responses[request_id] = response_queue

        # Build request
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        # Send request
        self._write_message(request)
        self.log(f"[ACP] Request {request_id}: {method}")

        # Wait for response
        try:
            # Keep compatibility with previous semantics while allowing local interrupt.
            # We poll in short intervals to react quickly to cancel_event.
            waited = 0.0
            poll_interval = 0.1
            cancel_waited = 0.0
            cancel_requested = False
            while True:
                if cancel_event and cancel_event.is_set():
                    if not cancel_requested:
                        cancel_requested = True
                        self.log(
                            f"[ACP] Request {request_id} ({method}) cancellation requested"
                        )
                    if cancel_grace_period <= 0 or cancel_waited >= cancel_grace_period:
                        with self._pending_lock:
                            self._ignored_response_ids.add(request_id)
                        raise ACPError(
                            f"Request {request_id} ({method}) interrupted locally"
                        )

                if (
                    self.process
                    and hasattr(self.process, "poll")
                    and self.process.poll() is not None
                ):
                    return_code = getattr(self.process, "returncode", "unknown")
                    raise ACPError(
                        f"Request {request_id} ({method}) failed: agent process exited with code {return_code}"
                    )

                remaining = timeout - waited
                if remaining <= 0:
                    with self._pending_lock:
                        self._timed_out_response_ids.add(request_id)
                    raise ACPError(
                        f"Request {request_id} ({method}) timed out after {timeout}s"
                    )

                wait_for = min(poll_interval, remaining)
                try:
                    response = response_queue.get(timeout=wait_for)
                    self.log(
                        f"[ACP] Response {request_id}: {'error' if response.is_error else 'success'}"
                    )
                    return response
                except Empty:
                    waited += wait_for
                    if cancel_requested:
                        cancel_waited += wait_for
        finally:
            # Cleanup
            with self._pending_lock:
                self.pending_responses.pop(request_id, None)

    def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        """Send JSON-RPC notification (no response expected).

        Args:
            method: JSON-RPC method name
            params: Method parameters (optional)
        """
        if not self.process or not self.running:
            raise ACPError("ACP client not running")

        notification = {"jsonrpc": "2.0", "method": method, "params": params or {}}

        self._write_message(notification)
        self.log(f"[ACP] Notification: {method}")

    def _write_message(self, msg: Dict[str, Any]):
        """Write JSON-RPC message to agent's stdin."""
        if not self.process or not self.process.stdin:
            raise ACPError("Process stdin not available")

        try:
            # NDJSON format: one JSON object per line
            line = json.dumps(msg) + "\n"
            with self._write_lock:
                self.process.stdin.write(line.encode("utf-8"))
                self.process.stdin.flush()
        except Exception as e:
            raise ACPError(f"Failed to write message: {e}")

    def _read_stdout(self):
        """Read and process stdout from agent (responses and notifications)."""
        if not self.process or not self.process.stdout:
            return

        try:
            for line in iter(self.process.stdout.readline, b""):
                if not self.running:
                    break

                line = line.decode("utf-8").strip()
                if not line:
                    continue

                try:
                    msg = json.loads(line)
                    self._handle_message(msg)
                except json.JSONDecodeError as e:
                    self.log(f"[ACP] Invalid JSON from agent: {e}")
                    self.log(f"[ACP] Line: {line[:200]}")
        except Exception as e:
            if self.running:
                self.log(f"[ACP] Error reading stdout: {e}")

    def _read_stderr(self):
        """Read and process stderr from agent (logs, errors)."""
        if not self.process or not self.process.stderr:
            return

        try:
            for line in iter(self.process.stderr.readline, b""):
                if not self.running:
                    break

                line = line.decode("utf-8").rstrip()
                if line:
                    self.log(f"[ACP stderr] {line}")
                    if self.on_error:
                        self.on_error(line)
        except Exception as e:
            if self.running:
                self.log(f"[ACP] Error reading stderr: {e}")

    def _handle_message(self, msg: Dict[str, Any]):
        """Handle incoming JSON-RPC message from agent."""
        # Notifications/requests both include "method". Requests additionally include "id".
        if "method" in msg:
            method = msg["method"]
            params = msg.get("params", {})

            # JSON-RPC request from agent -> client (expects response)
            if "id" in msg:
                msg_id = msg["id"]
                self.log(f"[ACP] Request received: {method} (id={msg_id})")

                try:
                    result: Dict[str, Any] | None = {}
                    if self.on_request:
                        result = self.on_request(method, params)

                    self._write_message(
                        {"jsonrpc": "2.0", "id": msg_id, "result": result or {}}
                    )
                except ACPMethodNotFound as e:
                    self.log(f"[ACP] Rejecting unknown request {method}: {e}")
                    self._write_message(
                        {
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "error": {"code": -32601, "message": "Method not found"},
                        }
                    )
                except Exception as e:
                    self.log(f"[ACP] Error handling request {method}: {e}")
                    self._write_message(
                        {
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "error": {"code": -32000, "message": str(e)},
                        }
                    )
                return

            # JSON-RPC notification from agent -> client (no response)
            if method not in {"session/update", "session/message"}:
                self.log(f"[ACP] Notification received: {method}")

            if self.on_notification:
                try:
                    self.on_notification(method, params)
                except Exception as e:
                    self.log(f"[ACP] Error in notification handler: {e}")
            return

        # Response (has "id" and no "method")
        if "id" in msg:
            msg_id = msg["id"]
            response = ACPResponse(
                id=msg_id, result=msg.get("result"), error=msg.get("error")
            )

            # Deliver to waiting request
            with self._pending_lock:
                queue = self.pending_responses.get(msg_id)
                fallback_id = None

                # Some OpenCode ACP builds occasionally respond with id=0
                # even when one request is in-flight. Route it to the only
                # pending request to avoid losing the response.
                if queue is None and msg_id == 0 and len(self.pending_responses) == 1:
                    fallback_id = next(iter(self.pending_responses.keys()))
                    queue = self.pending_responses.get(fallback_id)

            if queue is not None:
                if fallback_id is not None:
                    self.log(
                        f"[ACP] Routed unexpected response id=0 to pending request {fallback_id}"
                    )
                queue.put(response)
            else:
                with self._pending_lock:
                    if msg_id in self._ignored_response_ids:
                        self._ignored_response_ids.discard(msg_id)
                        self.log(
                            f"[ACP] Ignored late response for locally cancelled request ID: {msg_id}"
                        )
                        return
                    if msg_id in self._timed_out_response_ids:
                        self._timed_out_response_ids.discard(msg_id)
                        self.log(
                            f"[ACP] Late response for timed-out request ID: {msg_id}"
                        )
                        if self.on_late_response:
                            try:
                                self.on_late_response(msg_id, response)
                            except Exception as e:
                                self.log(
                                    f"[ACP] Error in on_late_response handler: {e}"
                                )
                        return
                self.log(f"[ACP] Received response for unknown request ID: {msg_id}")
            return

        else:
            self.log(f"[ACP] Invalid message (no id or method): {msg}")

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
