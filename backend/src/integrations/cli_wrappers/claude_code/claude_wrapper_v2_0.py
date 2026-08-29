#!/usr/bin/env python3
"""
Claude Wrapper v2.0 — DEPRECATED legacy implementation for Claude CLI < 2.1.0.

This module is frozen. The modular wrapper in `wrapper.py` (+ siblings under
`monitoring/`, `messaging/`, etc.) is the only path under active development;
all new features and bug fixes belong there. The version dispatcher in
`__main__.py` keeps this file alive solely to support users still pinned to
Claude CLI < 2.1.0, and that audience is expected to dwindle to zero.

Guidance for future maintainers:
- Do NOT add new features here. If a behavior changes in `wrapper.py` and the
  legacy path would also benefit, copy the *minimum* defensive patch across
  and reference the modular file in the commit message.
- Do NOT refactor for clarity or share code with the modular wrapper —
  divergence is fine; the legacy file is meant to age out, not be polished.
- Bug fixes are OK when the bug is severe AND affects users on the legacy
  CLI (rare). Otherwise leave it alone.

Key features (legacy):
- Sync operations where async isn't needed
- Cancellable request_user_input for race condition handling
- Clear separation of concerns
- JSONL log monitoring
- Git diff tracking
"""

import argparse
import asyncio
import errno
import json
import os
import pty
import re
import select
import signal
import sys
import termios
import threading
import time
import tty
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Dict, Optional
from vicoa.constants import DEFAULT_API_URL
from vicoa.sdk.async_client import AsyncVicoaClient
from vicoa.sdk.client import VicoaClient
from vicoa.sdk.exceptions import AuthenticationError, APIError
from vicoa.utils import get_project_path
from integrations.cli_wrappers.claude_code.session_reset_handler import (
    SessionResetHandler,
)
from integrations.cli_wrappers.claude_code.format_utils import format_content_block


# Constants
CLAUDE_LOG_BASE = Path.home() / ".claude" / "projects"
VICOA_WRAPPER_LOG_DIR = Path.home() / ".vicoa" / "claude_wrapper"
PERMISSION_MODE_KEYWORDS = {
    "plan": ("plan",),
    "acceptEdits": (
        "accept edits",
        "auto accept",
        "accept-edits",
        "acceptedits",
        "acceptEdits",
    ),
    "default": (
        "default",
        "manual",
        "shortcuts",
        "standard",
    ),
    "bypassPermissions": (
        "bypass permissions",
        "bypass-permissions",
        "bypassPermissions",
        "bypasspermissions",
    ),
}
PERMISSION_MODE_LABELS = {
    "default": "default mode",
    "plan": "plan mode",
    "acceptEdits": "accept edits",
    "bypassPermissions": "bypass permissions",
}

# Thinking toggle detection
THINKING_TOGGLE_PATTERN = re.compile(
    r"Thinking (on|off)\s*\(tab to toggle\)", re.IGNORECASE
)
THINKING_KEYWORDS = {
    "on": ("on", "enabled", "active"),
    "off": ("off", "disabled", "inactive"),
}
THINKING_LABELS = {
    "on": "thinking on",
    "off": "thinking off",
}

# Control command pattern (JSON format) - can be embedded in text
CONTROL_JSON_PATTERN = re.compile(r'\{[^}]*"type"\s*:\s*"control"[^}]*\}')
PERMISSION_MODE_PATTERN = re.compile(
    r"([^\n\r]+?)\s*(?:\(shift\+tab to cycle\)|\?\s+for\s+shortcuts)",
    re.IGNORECASE,
)


def find_claude_cli():
    """Find Claude CLI binary (delegates to the shared resolver)."""
    from .utils.cli_finder import find_claude_cli as _find

    return _find()


class MessageProcessor:
    """Message processing implementation"""

    def __init__(self, wrapper: "ClaudeWrapper"):
        self.wrapper = wrapper
        self.last_message_id = None
        self.last_message_time = None
        self.web_ui_messages = set()  # Track messages from web UI to avoid duplicates
        self.pending_input_message_id = None  # Track if we're waiting for input
        self.last_was_tool_use = False  # Track if last assistant message used tools
        self.subtask = False

    def process_user_message_sync(self, content: str, from_web: bool) -> None:
        """Process a user message (sync version for monitor thread)"""
        if from_web:
            # Message from web UI - track it to avoid duplicate sends
            self.web_ui_messages.add(content)
        else:
            # Message from CLI - send to Vicoa if not already from web
            if content not in self.web_ui_messages:
                self.wrapper.log(
                    f"[INFO] Sending CLI message to Vicoa: {content[:50]}..."
                )
                if self.wrapper.agent_instance_id and self.wrapper.vicoa_client_sync:
                    self.wrapper.vicoa_client_sync.send_user_message(
                        agent_instance_id=self.wrapper.agent_instance_id,
                        content=content,
                    )
            else:
                # Remove from tracking set
                self.web_ui_messages.discard(content)

            # Reset idle timer and clear pending input
            self.last_message_time = time.time()
            self.pending_input_message_id = None

    def process_assistant_message_sync(
        self, content: str, tools_used: list[str]
    ) -> None:
        """Process an assistant message (sync version for monitor thread)"""
        if not self.wrapper.agent_instance_id or not self.wrapper.vicoa_client_sync:
            return

        # Use lock to ensure atomic message processing
        with self.wrapper.send_message_lock:
            # Track if this message uses tools
            self.last_was_tool_use = bool(tools_used)

            # Sanitize content - remove NUL characters and control characters that break the API
            # This handles binary content from .docx, PDFs, etc.
            sanitized_content = "".join(
                char if ord(char) >= 32 or char in "\n\r\t" else ""
                for char in content.replace("\x00", "")
            )

            # Send to Vicoa
            response = self.wrapper.vicoa_client_sync.send_message(
                content=sanitized_content,
                agent_type=self.wrapper.name,
                agent_instance_id=self.wrapper.agent_instance_id,
                requires_user_input=False,
            )

            # Track message for idle detection
            self.last_message_id = response.message_id
            self.last_message_time = time.time()

            # Clear old tracked input requests since we have a new message
            self.wrapper.requested_input_messages.clear()

            # Clear pending permission options since we have a new message
            self.wrapper.pending_permission_options.clear()

            # Process any queued user messages
            if response.queued_user_messages:
                concatenated = "\n".join(response.queued_user_messages)
                self.web_ui_messages.add(concatenated)
                self.wrapper.input_queue.append(concatenated)

    def should_request_input(self) -> Optional[str]:
        """Check if we should request input, returns message_id if yes"""
        # Don't request input if we might have a permission prompt
        if self.last_was_tool_use and self.wrapper.is_claude_idle():
            # We're in a state where a permission prompt might appear
            return None

        # Only request if:
        # 1. We have a message to request input for
        # 2. We haven't already requested input for it
        # 3. Claude is idle
        if (
            self.last_message_id
            and self.last_message_id != self.pending_input_message_id
            and self.wrapper.is_claude_idle()
        ):
            return self.last_message_id

        return None

    def mark_input_requested(self, message_id: str) -> None:
        """Mark that input has been requested for a message"""
        self.pending_input_message_id = message_id


class ClaudeWrapper:
    """Legacy Claude Code wrapper for Claude CLI versions < 2.1.0.

    This is the v2.0 implementation that supports older Claude CLI versions.
    For newer versions (>= 2.1.0), use the modular wrapper in wrapper.py.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        permission_mode: Optional[str] = None,
        dangerously_skip_permissions: bool = False,
        name: str = "Claude Code",
        idle_delay: float = 3.5,
        agent_instance_id: Optional[str] = None,
        is_resuming: bool = False,
    ):
        # Session management
        # Track if we're resuming an existing session (based on --resume flag)
        self.is_resuming = is_resuming

        # Use provided agent_instance_id, or check env var, or generate new UUID
        self.agent_instance_id = (
            agent_instance_id
            or os.environ.get("VICOA_AGENT_INSTANCE_ID")
            or str(uuid.uuid4())
        )
        print(f"Session ID: {self.agent_instance_id}")  # debug, do not delete
        self.permission_mode = permission_mode
        self.dangerously_skip_permissions = dangerously_skip_permissions
        self.name = os.environ.get("VICOA_AGENT_DISPLAY_NAME") or name
        self.idle_delay = idle_delay

        # Set up logging
        self.debug_log_file = None
        self._init_logging()

        self.log(f"[INFO] Agent Instance ID: {self.agent_instance_id}")
        if self.is_resuming:
            self.log("[INFO] Resuming existing session")

        # Vicoa SDK setup
        self.api_key = api_key or os.environ.get("VICOA_API_KEY")
        if not self.api_key:
            print(
                "ERROR: API key must be provided via --api-key or VICOA_API_KEY environment variable",
                file=sys.stderr,
            )
            sys.exit(1)

        self.base_url = base_url or os.environ.get("VICOA_BASE_URL", DEFAULT_API_URL)
        self.vicoa_client_async: Optional[AsyncVicoaClient] = None
        self.vicoa_client_sync: Optional[VicoaClient] = None

        # Terminal interaction setup
        self.child_pid = None
        self.master_fd = None
        self.original_tty_attrs = None
        self.input_queue = deque()
        self.stdin_line_buffer = ""  # Buffer to accumulate stdin input until Enter

        # Session reset handler
        self.reset_handler = SessionResetHandler(log_func=self.log)

        # Claude JSONL log monitoring
        self.claude_jsonl_path = None
        self.jsonl_monitor_thread = None
        self.running = True
        # Set once a 401 has dropped the Vicoa link, so the recovery hint is
        # printed exactly once and link threads stop respinning. Claude itself
        # keeps running — see ``_drop_vicoa_link``.
        self._vicoa_link_dropped = False
        # Heartbeat
        self.heartbeat_thread = None
        self.heartbeat_interval = 30.0  # seconds
        self.skip_existing_jsonl_entries = self.is_resuming

        # Claude status monitoring
        self.terminal_buffer = ""
        self.last_esc_interrupt_seen = None

        # Message processor
        self.message_processor = MessageProcessor(self)

        # Async task management
        self.pending_input_task = None
        self.async_loop = None
        self.requested_input_messages = (
            set()
        )  # Track messages we've already requested input for
        self.pending_permission_options = {}  # Map option text to number for permission prompts
        self.send_message_lock = (
            threading.Lock()
        )  # Lock for message sending synchronization

        # Unified toggle state for all control settings
        # Initialize the structure first
        self._toggles = {
            "permission_mode": {
                "current_slug": None,
                "last_display": None,
                "pending_target": None,
                "cycle": ["default", "acceptEdits", "plan"],
                "key_sequence": b"\x1b[Z",  # Shift+Tab
                "keywords": PERMISSION_MODE_KEYWORDS,
                "labels": PERMISSION_MODE_LABELS,
            },
            "thinking": {
                "current_slug": None,  # Unknown initially
                "last_display": None,
                "pending_target": None,
                "cycle": ["off", "on"],
                "key_sequence": b"\t",  # Tab
                "keywords": THINKING_KEYWORDS,
                "labels": THINKING_LABELS,
            },
        }
        # Now normalize the initial permission_mode value
        if permission_mode:
            self._toggles["permission_mode"]["current_slug"] = (
                self._normalize_toggle_value("permission_mode", permission_mode)
            )
        self._control_detection_buffer = ""  # Shared buffer for both settings

    def _suspend_for_ctrl_z(self):
        """Handle Ctrl+Z while in raw mode: restore TTY, stop child and self."""
        try:
            self.log("[INFO] Ctrl+Z detected: suspending (raw mode)")
            if self.original_tty_attrs:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.original_tty_attrs)
            if self.child_pid:
                try:
                    os.kill(self.child_pid, signal.SIGTSTP)
                except Exception as e:
                    self.log(f"[WARNING] Failed to SIGTSTP child: {e}")
            # Suspend this wrapper
            try:
                os.kill(os.getpid(), signal.SIGTSTP)
            except Exception as e:
                self.log(f"[WARNING] Failed to SIGTSTP self: {e}")
        except Exception as e:
            self.log(f"[ERROR] Error handling Ctrl+Z: {e}")

    def _init_logging(self):
        """Initialize debug logging"""
        try:
            VICOA_WRAPPER_LOG_DIR.mkdir(exist_ok=True, parents=True)
            log_file_path = VICOA_WRAPPER_LOG_DIR / f"{self.agent_instance_id}.log"
            self.debug_log_file = open(log_file_path, "w")
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            milliseconds = int((time.time() % 1) * 1000)
            self.log(
                f"=== Claude Wrapper V3 Debug Log - {timestamp}.{milliseconds:03d} ==="
            )
        except Exception as e:
            print(f"Failed to create debug log file: {e}", file=sys.stderr)

    def _write_all_to_master(self, data: bytes) -> None:
        """Write data to the PTY master handling partial writes."""
        if not data:
            return

        if self.master_fd is None:
            raise RuntimeError("PTY master file descriptor is not initialized")

        view = memoryview(data)
        total_written = 0

        while total_written < len(view):
            try:
                written = os.write(self.master_fd, view[total_written:])
                if written == 0:
                    time.sleep(0.01)
                    continue
                total_written += written
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    time.sleep(0.01)
                    continue
                raise

    def log(self, message: str):
        """Write to debug log file"""
        if self.debug_log_file:
            try:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                milliseconds = int((time.time() % 1) * 1000)
                self.debug_log_file.write(
                    f"[{timestamp}.{milliseconds:03d}] {message}\n"
                )
                self.debug_log_file.flush()
            except Exception:
                pass

    def init_vicoa_clients(self):
        """Initialize both sync and async Vicoa SDK clients"""
        if not self.api_key:
            raise ValueError("API key is required to initialize Vicoa clients")

        # ~24 hours of retries: 6 exponential (63s) + 1438 at 60s each = 1444 total
        self.vicoa_client_sync = VicoaClient(
            api_key=self.api_key,
            base_url=self.base_url,
            max_retries=1440,  # ~24 hours with 60s cap
            backoff_factor=1.0,
            backoff_max=60.0,
            log_func=self.log,
        )

        self.vicoa_client_async = AsyncVicoaClient(
            api_key=self.api_key,
            base_url=self.base_url,
            max_retries=1440,  # ~24 hours with 60s cap
            backoff_factor=1.0,
            backoff_max=60.0,
            log_func=self.log,
        )

    def _drop_vicoa_link(self) -> None:
        """Tear down the Vicoa remote link without killing Claude.

        A 401 means the credential is dead (revoked key / deleted account). For
        an interactive session a human is at the terminal, so destroying
        in-progress local work would be worse than losing the remote link. We
        stop the link threads (each detector returns after calling this), tell
        the user once how to recover, and leave Claude (``child_pid``) running.
        Re-auth via ``vicoa --auth`` restores the link on the next launch.
        Idempotent: repeated 401s across threads only print once.
        """
        if self._vicoa_link_dropped:
            return
        self._vicoa_link_dropped = True
        self.log(
            "[INFO] Vicoa credential expired; dropping remote link, Claude keeps running"
        )
        print(
            "Vicoa is disconnected (credential expired), run vicoa --auth",
            flush=True,
        )

    def _heartbeat_loop(self):
        """Background loop to POST heartbeat while running"""
        if not self.vicoa_client_sync:
            return
        session = self.vicoa_client_sync.session
        url = (
            self.base_url.rstrip("/")
            + f"/api/v1/agents/instances/{self.agent_instance_id}/heartbeat"
        )
        # Small stagger to avoid herd
        import random

        jitter = random.uniform(0, 2.0)
        time.sleep(jitter)
        while self.running:
            try:
                resp = session.post(url, timeout=10)
                if resp.status_code == 401:
                    # Fatal-auth: the credential is dead. Drop the link and
                    # stop pinging — don't treat it as a transient failure.
                    self._drop_vicoa_link()
                    return
                if resp.status_code == 404:
                    # 404 on our own instance heartbeat means the row is
                    # gone (e.g. the user account that owns it was deleted
                    # — the instance cascaded away, but no 401 because the
                    # heartbeat endpoint looks up the row before writing,
                    # so PR #45's FK→401 handler doesn't fire). Nothing left
                    # to heartbeat against — stop the loop cleanly instead
                    # of logging WARN every 30s forever. Claude itself
                    # keeps running (the human is at the terminal); only
                    # the Vicoa link goes silent.
                    self.log(
                        "[INFO] Vicoa instance no longer exists; stopping heartbeat"
                    )
                    return
                if resp.status_code >= 400:
                    self.log(
                        f"[WARN] Heartbeat failed {resp.status_code}: {resp.text[:120]}"
                    )
            except Exception as e:
                self.log(f"[WARN] Heartbeat error: {e}")
            # Sleep interval with small jitter
            delay = self.heartbeat_interval + random.uniform(-2.0, 2.0)
            if delay < 5:
                delay = 5
            for _ in range(int(delay * 10)):
                if not self.running:
                    break
                time.sleep(0.1)

    def get_project_log_dir(self):
        """Get the Claude project log directory for current working directory"""
        cwd = os.getcwd()
        # Convert path to Claude's format
        project_name = re.sub(r"[^a-zA-Z0-9]", "-", cwd)
        project_dir = CLAUDE_LOG_BASE / project_name
        return project_dir if project_dir.exists() else None

    def monitor_claude_jsonl(self):
        """Monitor Claude's JSONL log file for messages"""
        # Wait for log file to be created
        while self.running and not self.claude_jsonl_path:
            project_dir = self.get_project_log_dir()
            if project_dir:
                expected_filename = f"{self.agent_instance_id}.jsonl"
                expected_path = project_dir / expected_filename
                if expected_path.exists():
                    self.claude_jsonl_path = expected_path
                    self.log(f"[INFO] Found Claude JSONL log: {expected_path}")
                    break
            time.sleep(0.5)

        if not self.claude_jsonl_path:
            return

        # Monitor the file
        while self.running:
            try:
                with open(self.claude_jsonl_path, "r") as f:
                    if self.skip_existing_jsonl_entries:
                        f.seek(0, os.SEEK_END)
                        self.log(
                            "[INFO] Skipping existing Claude JSONL entries due to resume"
                        )
                        self.skip_existing_jsonl_entries = False
                    else:
                        f.seek(0)  # Start from beginning when not resuming

                    self.log(
                        f"[INFO] Monitoring JSONL file: {self.claude_jsonl_path.name}"
                    )

                    while self.running:
                        # Check for session reset
                        if self.reset_handler.is_reset_pending():
                            self.log(
                                "[INFO] Session reset pending, waiting for new JSONL file..."
                            )

                            project_dir = self.get_project_log_dir()

                            if project_dir:
                                # Look for new session file
                                new_jsonl_path = (
                                    self.reset_handler.find_reset_session_file(
                                        project_dir=project_dir,
                                        current_file=self.claude_jsonl_path,
                                        max_wait=10.0,
                                    )
                                )
                            else:
                                new_jsonl_path = None
                                self.log("[WARNING] Could not get project directory")

                            if new_jsonl_path:
                                old_path = self.claude_jsonl_path.name
                                self.claude_jsonl_path = new_jsonl_path
                                self.log(
                                    f"[INFO] ✅ Switched from {old_path} to {new_jsonl_path.name}"
                                )

                                # Reset the handler state
                                self.reset_handler.clear_reset_state()

                                # Break out of inner loop to reopen with new file
                                break
                            else:
                                # Couldn't find new file, continue with current
                                self.log(
                                    "[WARNING] Could not find new session file, continuing with current"
                                )
                                self.reset_handler.clear_reset_state()

                        # Read next line from current file
                        line = f.readline()
                        if line:
                            try:
                                data = json.loads(line.strip())
                                # Process directly with sync client
                                self.process_claude_log_entry(data)
                            except json.JSONDecodeError:
                                pass
                        else:
                            # Check if file still exists
                            if not self.claude_jsonl_path.exists():
                                self.log(
                                    "[WARNING] Current JSONL file no longer exists"
                                )
                                break
                            time.sleep(0.1)

            except Exception as e:
                self.log(f"[ERROR] Error monitoring Claude JSONL: {e}")
                # If we hit an error, wait a bit before retrying
                time.sleep(1)

    def process_claude_log_entry(self, data: Dict[str, Any]):
        """Process a log entry from Claude's JSONL (sync)"""
        try:
            msg_type = data.get("type")

            # We skip showing messages from subtasks
            is_subtask = data.get("isSidechain")
            if is_subtask and (msg_type == "assistant" or msg_type == "user"):
                return
            elif not is_subtask and (msg_type == "assistant" or msg_type == "user"):
                self.message_processor.subtask = False

            if msg_type == "user":
                # Skip meta messages (like "Caveat:" messages)
                if data.get("isMeta", False):
                    self.log("[INFO] Skipping meta message")
                    return

                # User message
                message = data.get("message", {})
                content = message.get("content", "")

                # Handle both string content and structured content blocks
                if isinstance(content, str) and content:
                    # Skip empty command output
                    if (
                        content.strip()
                        == "<local-command-stdout></local-command-stdout>"
                    ):
                        self.log("[INFO] Skipping empty command output")
                        return

                    # `<command-name>/X</command-name>` is the user's TUI
                    # slash command (e.g. typing `/model`). Drop it entirely
                    # — the user already saw the result locally, and the
                    # stdout confirmation (handled below) carries the
                    # actionable text.
                    if "<command-name>" in content:
                        self.log("[INFO] Skipping TUI slash-command echo")
                        return

                    # Non-empty TUI slash-command stdout (e.g. "Set model to
                    # Opus 4.8 (1M context)"). Visible to the user, but not
                    # a real chat message — route it as AGENT so it doesn't
                    # trip session title generation.
                    if "<local-command-stdout>" in content:
                        self.log(
                            f"[INFO] CLI command stdout in JSONL: {content[:80]}..."
                        )
                        if self.agent_instance_id and self.vicoa_client_sync:
                            try:
                                self.vicoa_client_sync.send_message(
                                    content=content,
                                    agent_type=self.name,
                                    agent_instance_id=self.agent_instance_id,
                                    requires_user_input=False,
                                )
                            except Exception as e:
                                self.log(
                                    f"[ERROR] Failed to send CLI command echo to Vicoa: {e}"
                                )
                        return

                    self.log(f"[INFO] User message in JSONL: {content[:50]}...")
                    # CLI user input arrived - cancel any pending web input request
                    self.cancel_pending_input_request()
                    self.message_processor.process_user_message_sync(
                        content, from_web=False
                    )
                elif isinstance(content, list):
                    # Handle structured content (e.g., tool results)
                    formatted_parts = []
                    for block in content:
                        if isinstance(block, dict):
                            formatted_content = format_content_block(block)
                            if formatted_content:
                                formatted_parts.append(formatted_content)

                    if formatted_parts:
                        combined_content = "\n".join(formatted_parts)
                        self.log(
                            f"[INFO] User message with blocks: {combined_content[:100]}..."
                        )
                        # Don't process tool results as user messages
                        # They're just acknowledgements of tool execution

            elif msg_type == "assistant":
                # Claude's response
                message = data.get("message", {})
                content_blocks = message.get("content", [])
                formatted_parts = []
                tools_used = []

                for block in content_blocks:
                    if isinstance(block, dict):
                        formatted_content = format_content_block(block)
                        if formatted_content:
                            formatted_parts.append(formatted_content)
                            # Track if this was a tool use
                            if block.get("type") == "tool_use":
                                tools_used.append(formatted_content)
                            if block.get("name") == "Task":
                                self.message_processor.subtask = True

                # Process message if we have content
                if formatted_parts:
                    message_content = "\n".join(formatted_parts)
                    self.message_processor.process_assistant_message_sync(
                        message_content, tools_used
                    )

            elif msg_type == "summary":
                # Session started
                summary = data.get("summary", "")
                if summary and not self.agent_instance_id and self.vicoa_client_sync:
                    # Send initial message
                    self.vicoa_client_sync.send_message(
                        content=f"Claude session started: {summary}",
                        agent_type=self.name,
                        agent_instance_id=self.agent_instance_id,
                        requires_user_input=False,
                    )

        except Exception as e:
            self.log(f"[ERROR] Error processing Claude log entry: {e}")

    def is_claude_idle(self):
        """Check if Claude is idle (hasn't shown 'esc to interrupt' for idle_delay seconds)"""
        if self.last_esc_interrupt_seen:
            time_since_esc = time.time() - self.last_esc_interrupt_seen
            return time_since_esc >= self.idle_delay
        return True

    def cancel_pending_input_request(self):
        """Cancel any pending input request task"""
        if self.pending_input_task and not self.pending_input_task.done():
            self.log("[INFO] Cancelling pending input request due to CLI input")
            self.pending_input_task.cancel()
            self.pending_input_task = None

    def _process_user_responses(self, responses: list[str]) -> bool:
        """Process user responses and queue non-control messages for Claude.

        Args:
            responses: List of user response strings from web UI

        Returns:
            True if any actual (non-control) input was queued, False if only control commands

        Note:
            Control commands (like permission mode changes) are handled but not queued.
            They won't be sent to Claude, allowing immediate subsequent requests.
        """
        has_actual_input = False

        for response in responses:
            self.log(f"[INFO] Got user response from web UI: {response[:50]}...")

            # Always track the message for deduplication
            self.message_processor.process_user_message_sync(response, from_web=True)

            # Check if this is a control command (JSON format)
            if self._handle_control_command(response):
                self.log("[INFO] Processed control command, not queuing for Claude")
                continue

            # Queue actual user input for Claude
            self.input_queue.append(response)
            has_actual_input = True

        return has_actual_input

    async def _send_waiting_message_and_get_responses(self) -> bool:
        """Send a waiting message and get user responses (fallback for 400 errors).

        Returns:
            True if actual input was received, False if only control commands
        """
        try:
            if not self.vicoa_client_async:
                return False

            response = await self.vicoa_client_async.send_message(
                content="Waiting for your input...",
                agent_type=self.name,
                agent_instance_id=self.agent_instance_id,
                requires_user_input=True,
                poll_interval=3.0,
            )
            self.log(f"[INFO] Sent waiting message with ID: {response.message_id}")

            # Process any queued responses
            return self._process_user_responses(response.queued_user_messages)

        except Exception as e:
            self.log(f"[ERROR] Failed to send waiting message: {e}")
            return False

    async def request_user_input_async(self, message_id: str):
        """Async task to request user input from web UI.

        This method long-polls for user responses and processes them. Control commands
        (like permission mode changes) are handled but don't count as "actual input",
        allowing immediate subsequent requests without blocking.

        Args:
            message_id: The message ID to request input for
        """
        has_actual_input = False

        try:
            self.log(f"[INFO] Starting request_user_input for message {message_id}")

            if not self.vicoa_client_async:
                self.log("[ERROR] Vicoa async client not initialized")
                return

            # Ensure async client session exists
            await self.vicoa_client_async._ensure_session()

            # Long-polling request for user input (blocks until user responds)
            user_responses = await self.vicoa_client_async.request_user_input(
                message_id=message_id,
                timeout_minutes=1440,  # 24 hours
                poll_interval=3.0,
            )

            # Process responses and check if we got actual input vs control commands
            has_actual_input = self._process_user_responses(user_responses)

        except asyncio.CancelledError:
            self.log(f"[INFO] request_user_input cancelled for message {message_id}")
            raise

        except AuthenticationError:
            # Fatal-auth: the credential is dead. Drop the link (prints once,
            # keeps Claude running) instead of swallowing and re-polling the
            # dead endpoint every few seconds.
            self._drop_vicoa_link()

        except Exception as e:
            self.log(f"[ERROR] Failed to request user input: {e}")

            # Fallback: If message already requires input, create a new waiting message
            if "400" in str(e) and "already requires user input" in str(e):
                self.log(
                    "[INFO] Message already requires input, creating new waiting message"
                )
                has_actual_input = await self._send_waiting_message_and_get_responses()

        finally:
            # State management for duplicate request prevention:
            # - If we got actual input: keep pending_input_message_id set (prevents duplicate requests)
            # - If only control commands: clear it (allows immediate subsequent requests)
            if (
                not has_actual_input
                and self.message_processor.pending_input_message_id == message_id
            ):
                self.message_processor.pending_input_message_id = None

            # Always clear from tracking set to allow retries if needed
            self.requested_input_messages.discard(message_id)

    def _extract_permission_prompt(
        self, clean_buffer: str
    ) -> tuple[str, list[str], dict[str, str]]:
        """Extract permission/plan mode/AskUserQuestion prompt from terminal buffer
        Returns: (question, options_list, options_map)
        """

        # Check if this is AskUserQuestion - look for the specific indicators
        is_ask_user_question = (
            "Enter to select" in clean_buffer
            and "Tab/Arrow keys to navigate" in clean_buffer
        )

        # Check if this is plan mode - look for the specific options
        is_plan_mode = "Would you like to proceed" in clean_buffer and (
            "auto-accept edits" in clean_buffer
            or "manually approve edits" in clean_buffer
        )

        # Find the question - support permission, plan mode, and AskUserQuestion prompts
        question = ""
        plan_content = ""

        if is_ask_user_question:
            # For AskUserQuestion, extract the question text
            # IMPORTANT: Focus on the LAST/MOST RECENT part of the buffer
            # The terminal buffer accumulates text, so we need to extract from the end

            # Strategy: Work backwards from the end to find the current prompt
            # 1. Find "Enter to select" (marks the end of the prompt)
            # 2. Find the last "❯ 1." or "1." before that (marks the options)
            # 3. Find the question between options and "Enter to select"

            lines = clean_buffer.split("\n")

            # Find the last occurrence of "Enter to select" - this marks the current prompt
            enter_to_select_idx = None
            for i in range(len(lines) - 1, -1, -1):
                if "Enter to select" in lines[i]:
                    enter_to_select_idx = i
                    break

            if enter_to_select_idx is None:
                self.log("[WARNING] 'Enter to select' not found in buffer")
                is_ask_user_question = False
            else:
                # Now work backwards from "Enter to select" to find options
                # Find the LAST occurrence of "1." before "Enter to select"
                first_option_idx = None
                for i in range(
                    enter_to_select_idx - 1, max(0, enter_to_select_idx - 50), -1
                ):
                    line_check = lines[i].strip().replace("❯", "").strip()
                    line_check = line_check.replace("\u2502", "").strip()
                    if re.match(r"^\s*1\.\s+\w", line_check):
                        first_option_idx = i
                        # Don't break - keep looking backwards for the earliest option

                if first_option_idx is None:
                    self.log("[WARNING] Option '1.' not found before 'Enter to select'")
                    is_ask_user_question = False
                else:
                    # Look for question between some reasonable point and first option
                    # Start searching from max 20 lines before the first option
                    search_start = max(0, first_option_idx - 20)

                    # Look for question between start and first option, working backwards so we pick the most recent line
                    for i in range(first_option_idx - 1, search_start - 1, -1):
                        line = lines[i]
                        # Extra cleaning for any remaining escape sequences
                        line_clean = line.strip()
                        line_clean = line_clean.replace(
                            "\u2502", ""
                        )  # Remove box border
                        line_clean = line_clean.replace("\u276f", "")  # Remove arrow
                        line_clean = line_clean.replace(
                            "❯", ""
                        )  # Remove selection marker
                        line_clean = line_clean.strip()

                        # Skip empty lines, navigation hints, header UI elements, and option numbers
                        if (
                            line_clean
                            and not line_clean.startswith(
                                ("1.", "2.", "3.", "4.", "5.", ">", ">>")
                            )
                            and "Enter to select" not in line_clean
                            and "Tab/Arrow keys" not in line_clean
                            and "Esc to cancel" not in line_clean
                            and "Submit" not in line_clean  # Skip header buttons
                            and "for shortcuts" not in line_clean.lower()
                            and "thinking off" not in line_clean.lower()
                            and "Try "
                            not in line_clean  # Skip suggestion lines like "Try ..."
                            and not re.match(
                                r"^[←☐✔→\s]+$", line_clean
                            )  # Skip pure UI elements
                            and not re.match(
                                r"^[←☐✔→].*[←☐✔→]$", line_clean
                            )  # Skip header lines with UI on both ends
                            and len(line_clean) > 10  # Skip very short lines
                            and "?"
                            in line_clean  # Questions should contain a question mark
                            # Check that line contains mostly printable characters (not just escape sequences)
                            and len([c for c in line_clean if c.isprintable()])
                            > len(line_clean) * 0.7
                        ):
                            # This is likely the question
                            question = line_clean
                            break
        elif is_plan_mode:
            # For plan mode, extract the question from buffer
            question = "Would you like to proceed with this plan?"

            # Simple approach: Just use the terminal buffer for plan extraction
            # Look for "Ready to code?" marker in the buffer
            plan_marker = "Ready to code?"
            plan_start = clean_buffer.rfind(plan_marker)

            if plan_start != -1:
                # Extract everything after "Ready to code?" up to the prompt
                plan_end = clean_buffer.find("Would you like to proceed", plan_start)
                if plan_end != -1:
                    plan_content = clean_buffer[
                        plan_start + len(plan_marker) : plan_end
                    ]

                    # Clean up the plan content - remove ANSI codes and box characters
                    lines = []
                    for line in plan_content.split("\n"):
                        # Remove box drawing characters and clean up
                        cleaned = re.sub(r"^[│\s]+", "", line)
                        cleaned = re.sub(r"[│\s]+$", "", cleaned)
                        cleaned = cleaned.strip()

                        # Skip empty lines and box borders
                        if cleaned and not re.match(r"^[╭─╮╰╯]+$", cleaned):
                            lines.append(cleaned)

                    plan_content = "\n".join(lines).strip()
                else:
                    plan_content = ""
            else:
                # No "Ready to code?" found - might be a very short plan or scrolled off
                plan_content = ""
        else:
            # Regular permission prompt - find the actual question
            lines = clean_buffer.split("\n")
            # Look for "Do you want" line - search from end to get most recent
            for i in range(len(lines) - 1, -1, -1):
                line_clean = lines[i].strip().replace("\u2502", "").strip()
                if "Do you want" in line_clean:
                    question = line_clean
                    break

        # Default question if not found
        if not question:
            question = "Permission required"

        # Find the options
        options_dict = {}

        if is_ask_user_question:
            # For AskUserQuestion, parse options with descriptions
            # Use the same strategy: work backwards from "Enter to select"
            lines = clean_buffer.split("\n")

            # Find the last occurrence of "Enter to select"
            enter_to_select_idx = None
            for i in range(len(lines) - 1, -1, -1):
                if "Enter to select" in lines[i]:
                    enter_to_select_idx = i
                    break

            if enter_to_select_idx is None:
                self.log(
                    "[WARNING] Could not find 'Enter to select' for options parsing"
                )
            else:
                # Find all option lines (1-5) between some reasonable range and "Enter to select"
                # Look backwards from "Enter to select" up to 30 lines
                search_start = max(0, enter_to_select_idx - 30)
                option_starts = []

                for i in range(search_start, enter_to_select_idx):
                    clean_line = lines[i].strip().replace("\u2502", "").strip()
                    clean_line = clean_line.replace(
                        "\u276f", ""
                    ).strip()  # Remove arrow
                    clean_line = clean_line.replace(
                        "❯", ""
                    ).strip()  # Remove selection marker
                    if re.match(r"^[1-5]\.\s+", clean_line):
                        option_starts.append(i)

            # Process the found options
            if option_starts:
                start_line = option_starts[0]  # First option in the range

                # Extract consecutive numbered options from this point
                current_num = 1
                current_option_key = None
                for i in range(start_line, min(start_line + 20, len(lines))):
                    raw_line = lines[i]
                    clean_line = raw_line.strip().replace("\u2502", "").strip()
                    clean_line = clean_line.replace("\u276f", "").strip()
                    clean_line = clean_line.replace("❯", "").strip()

                    pattern = rf"^{current_num}\.\s+(.+)"
                    match = re.match(pattern, clean_line)
                    if match:
                        current_option_key = str(current_num)
                        options_dict[current_option_key] = clean_line
                        current_num += 1
                    elif current_option_key and clean_line and current_num <= 6:
                        # Stop if we hit navigation hints
                        if (
                            "Enter to select" in clean_line
                            or "Tab/Arrow keys" in clean_line
                        ):
                            break
                        # Check if this is a description line (indented continuation)
                        raw_without_border = raw_line.replace("\u2502", " ")
                        raw_without_border = raw_without_border.replace("❯", " ")
                        if raw_without_border.startswith((" ", "\t")) and not re.match(
                            r"^[1-5]\.\s+", clean_line
                        ):
                            # Append description to current option
                            existing = options_dict[current_option_key].rstrip()
                            options_dict[current_option_key] = (
                                f"{existing} - {clean_line}"
                            ).strip()
                    elif (
                        "Enter to select" in clean_line
                        or "Tab/Arrow keys" in clean_line
                    ):
                        # Stop when we hit navigation hints
                        break

                self.log(f"[INFO] Found {len(options_dict)} AskUserQuestion options")
        elif is_plan_mode:
            # For plan mode, use hardcoded options since they're always the same
            options_dict = {
                "1": "1. Yes, and auto-accept edits",
                "2": "2. Yes, and manually approve edits",
                "3": "3. No, keep planning",
            }
        else:
            # Regular permission prompt - look for numbered options
            lines = clean_buffer.split("\n")

            # Look for lines that start with "1. " to find option groups
            # Then extract consecutive numbered options from that point

            # Find all lines starting with "1. "
            option_starts = []
            for i, line in enumerate(lines):
                clean_line = line.strip().replace("\u2502", "").strip()
                clean_line = clean_line.replace("\u276f", "").strip()
                if re.match(r"^1\.\s+", clean_line):
                    option_starts.append(i)

            # Process the last (most recent) option group
            if option_starts:
                start_line = option_starts[-1]

                # Extract consecutive numbered options from this point
                current_num = 1
                current_option_key = None
                for i in range(start_line, min(start_line + 10, len(lines))):
                    raw_line = lines[i]
                    clean_line = raw_line.strip().replace("\u2502", "").strip()
                    clean_line = clean_line.replace("\u276f", "").strip()

                    pattern = rf"^{current_num}\.\s+(.+)"
                    match = re.match(pattern, clean_line)
                    if match:
                        current_option_key = str(current_num)
                        options_dict[current_option_key] = clean_line
                        current_num += 1
                    elif current_option_key and clean_line:
                        raw_without_border = raw_line.replace("\u2502", " ")
                        if raw_without_border.startswith((" ", "\t")) and not re.match(
                            r"^\d\.\s+", clean_line
                        ):
                            # Append wrapped lines (terminal line wraps) to the current option
                            existing = options_dict[current_option_key].rstrip()
                            options_dict[current_option_key] = (
                                f"{existing} {clean_line}"
                            ).strip()
                    elif current_num > 1 and not clean_line:
                        # Empty line might be between options, continue
                        continue
                    elif current_num > 1:
                        # Non-empty line that's not an option, stop here
                        break

                # Log summary of what was found
                if options_dict:
                    self.log(f"[INFO] Found {len(options_dict)} permission options")
            else:
                self.log(
                    "[WARNING] No permission options found in buffer, using defaults"
                )

        # Convert to list maintaining order
        options = [options_dict[key] for key in sorted(options_dict.keys())]

        # Build options mapping
        options_map = {}
        if is_ask_user_question:
            # For AskUserQuestion, map option text to number
            # Also handle "Type something" special case
            for option in options:
                # Parse "1. Option text - description" -> {"Option text - description": "1"}
                parts = option.split(". ", 1)
                if len(parts) == 2:
                    number = parts[0].strip()
                    text = parts[1].strip()
                    options_map[text] = number

                    # Also add just the first part before " - " for easier matching
                    if " - " in text:
                        main_text = text.split(" - ")[0].strip()
                        if main_text not in options_map:
                            options_map[main_text] = number
        elif is_plan_mode:
            # For plan mode, use specific mapping
            options_map = {
                "Yes, and auto-accept edits": "1",
                "Yes, and manually approve edits": "2",
                "No, keep planning": "3",
            }
        else:
            # Regular permission mapping
            for option in options:
                # Parse "1. Yes" -> {"Yes": "1"}
                parts = option.split(". ", 1)
                if len(parts) == 2:
                    number = parts[0].strip()
                    text = parts[1].strip()
                    options_map[text] = number

        # Return plan content as part of question if available
        if plan_content:
            question = f"{question}\n\n{plan_content}"
            # Clear terminal buffer after extracting plan to avoid old plans
            self.terminal_buffer = ""

        return question, options, options_map

    def run_claude_with_pty(self):
        """Run Claude CLI in a PTY"""
        claude_path = find_claude_cli()
        self.log(f"[INFO] Found Claude CLI at: {claude_path}")

        # Build Claude command
        if self.is_resuming:
            # When resuming, use --resume with the session ID
            cmd = [claude_path, "--resume", self.agent_instance_id]
        else:
            # When starting new session, use --session-id
            cmd = [claude_path, "--session-id", self.agent_instance_id]

        # Add permission-mode flag if specified
        if self.permission_mode:
            cmd.extend(["--permission-mode", self.permission_mode])
            self.log(
                f"[INFO] Added permission-mode to Claude command: {self.permission_mode}"
            )

        # Add dangerously-skip-permissions flag if specified
        if self.dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")
            self.log("[INFO] Added dangerously-skip-permissions to Claude command")

        # Log the final command for debugging
        self.log(f"[INFO] Final Claude command: {' '.join(cmd)}")

        # Save original terminal settings
        try:
            self.original_tty_attrs = termios.tcgetattr(sys.stdin)
        except Exception:
            self.original_tty_attrs = None

        # Get terminal size
        try:
            cols, rows = os.get_terminal_size()
            self.log(f"[INFO] Terminal size: {cols}x{rows}")
        except Exception:
            cols, rows = 80, 24

        # Create PTY
        self.child_pid, self.master_fd = pty.fork()

        if self.child_pid == 0:
            # Child process - exec Claude CLI
            os.environ["CLAUDE_CODE_ENTRYPOINT"] = "jsonlog-wrapper"
            os.execvp(cmd[0], cmd)

        # Parent process - set PTY size
        if self.child_pid > 0:
            try:
                import fcntl
                import struct

                TIOCSWINSZ = 0x5414  # Linux
                if sys.platform == "darwin":
                    TIOCSWINSZ = 0x80087467  # macOS

                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(self.master_fd, TIOCSWINSZ, winsize)
            except Exception:
                pass

        # Parent process - handle I/O
        try:
            if self.original_tty_attrs:
                tty.setraw(sys.stdin)

            # Set non-blocking mode on master_fd
            import fcntl

            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            while self.running:
                # Use select to multiplex I/O
                rlist, _, _ = select.select([sys.stdin, self.master_fd], [], [], 0.01)

                # Clean ANSI escape sequences more thoroughly
                clean_buffer = self.terminal_buffer
                # Remove CSI sequences: ESC [ ... letter
                clean_buffer = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", clean_buffer)
                # Remove OSC sequences: ESC ] ... BEL/ST
                clean_buffer = re.sub(r"\x1b\].*?(\x07|\x1b\\\\)", "", clean_buffer)
                # Remove other ESC sequences: ESC followed by single char
                clean_buffer = re.sub(r"\x1b[=>\\[\\]PI]", "", clean_buffer)
                # Remove bracketed paste mode markers
                clean_buffer = re.sub(r"\x1b\[\?2004[hl]", "", clean_buffer)
                # Remove cursor visibility sequences
                clean_buffer = re.sub(r"\x1b\[\?25[hl]", "", clean_buffer)
                # Remove synchronized output sequences
                clean_buffer = re.sub(r"\x1b\[\?2026[hl]", "", clean_buffer)
                # When expecting permission prompt, check if we need to handle it
                if self.message_processor.last_was_tool_use and self.is_claude_idle():
                    # After tool use + idle, assume permission prompt is shown
                    if not hasattr(self, "_permission_assumed_time"):
                        self._permission_assumed_time = time.time()

                    # After 0.5 seconds, check if we can parse the prompt from buffer
                    elif time.time() - self._permission_assumed_time > 0.5:
                        # If we see permission/plan/AskUserQuestion prompt, extract it
                        # For AskUserQuestion: "Enter to select" and "Tab/Arrow keys"
                        # For plan mode: "Would you like to proceed" without "(esc"
                        # For permission: "Do you want" with "(esc"
                        if (
                            (
                                "Enter to select" in clean_buffer
                                and "Tab/Arrow keys to navigate" in clean_buffer
                            )
                            or (
                                "Do you want" in clean_buffer and "(esc" in clean_buffer
                            )
                            or (
                                "Would you like to proceed" in clean_buffer
                                and "No, keep planning" in clean_buffer
                            )
                        ):
                            if not hasattr(self, "_permission_handled"):
                                self._permission_handled = True

                                # Use lock to ensure atomic permission prompt handling
                                with self.send_message_lock:
                                    # Extract prompt components using the shared method
                                    question, options, options_map = (
                                        self._extract_permission_prompt(clean_buffer)
                                    )

                                    # Validate that we have a reasonable question and options
                                    has_valid_question = (
                                        question
                                        and len(question) > 10
                                        and "?" in question
                                    )
                                    has_valid_options = (
                                        len(options) >= 2
                                        and all(
                                            opt.strip() for opt in options
                                        )  # All options are non-empty
                                    )

                                    if not has_valid_question:
                                        self.log(
                                            "[WARNING] Invalid question extracted, skipping prompt"
                                        )
                                        question = "Waiting for your input..."
                                        options = []
                                    elif not has_valid_options:
                                        self.log(
                                            "[WARNING] Invalid options extracted, skipping prompt"
                                        )
                                        options = []

                                    # Build the message
                                    if options and has_valid_question:
                                        options_text = "\n".join(options)
                                        permission_msg = f"{question}\n\n[OPTIONS]\n{options_text}\n[/OPTIONS]"
                                        self.pending_permission_options = options_map
                                    else:
                                        # Fallback if parsing fails
                                        permission_msg = f"{question}\n\n[OPTIONS]\n1. Yes\n2. Yes, and don't ask again this session\n3. No\n[/OPTIONS]"
                                        self.pending_permission_options = {
                                            "Yes": "1",
                                            "Yes, and don't ask again this session": "2",
                                            "No": "3",
                                        }
                                        self.log(
                                            "[WARNING] Using default permission options (extraction failed)"
                                        )

                                    # Send to Vicoa with extracted text
                                    if (
                                        self.agent_instance_id
                                        and self.vicoa_client_sync
                                    ):
                                        response = self.vicoa_client_sync.send_message(
                                            content=permission_msg,
                                            agent_type=self.name,
                                            agent_instance_id=self.agent_instance_id,
                                            requires_user_input=False,
                                        )
                                        self.message_processor.last_message_id = (
                                            response.message_id
                                        )
                                        self.message_processor.last_message_time = (
                                            time.time()
                                        )
                                        self.message_processor.last_was_tool_use = False

                        # Fallback after 1 second if we still don't have the full prompt
                        elif time.time() - self._permission_assumed_time > 1.0:
                            if not hasattr(self, "_permission_handled"):
                                self._permission_handled = True
                                with self.send_message_lock:
                                    if (
                                        self.agent_instance_id
                                        and self.vicoa_client_sync
                                    ):
                                        response = self.vicoa_client_sync.send_message(
                                            content="Waiting for your input...",
                                            agent_type=self.name,
                                            agent_instance_id=self.agent_instance_id,
                                            requires_user_input=False,
                                        )
                                        self.message_processor.last_message_id = (
                                            response.message_id
                                        )
                                        self.message_processor.last_message_time = (
                                            time.time()
                                        )
                                        self.message_processor.last_was_tool_use = False
                elif (
                    (
                        (
                            "Enter to select" in clean_buffer
                            and "Tab/Arrow keys to navigate" in clean_buffer
                        )
                        or ("Do you want" in clean_buffer and "(esc" in clean_buffer)
                        or (
                            "Would you like to proceed" in clean_buffer
                            and "No, keep planning" in clean_buffer
                        )
                    )
                    and self.message_processor.subtask
                    and not self.pending_permission_options
                ):
                    self.message_processor.last_was_tool_use = True
                else:
                    # Clear state when conditions change
                    if hasattr(self, "_permission_assumed_time"):
                        delattr(self, "_permission_assumed_time")
                    if hasattr(self, "_permission_handled"):
                        delattr(self, "_permission_handled")

                # Handle terminal output from Claude
                if self.master_fd in rlist:
                    try:
                        data = os.read(self.master_fd, 65536)
                        if data:
                            # Write to stdout
                            os.write(sys.stdout.fileno(), data)
                            sys.stdout.flush()

                            # Check for "esc to interrupt" indicator
                            try:
                                text = data.decode("utf-8", errors="ignore")
                                self.terminal_buffer += text

                                # Keep buffer large enough for long plans
                                if len(self.terminal_buffer) > 200000:
                                    self.terminal_buffer = self.terminal_buffer[
                                        -200000:
                                    ]

                                # Check for the indicator
                                clean_text = re.sub(r"\x1b\[[0-9;]*m", "", text)

                                # Only check control settings if text contains relevant keywords
                                # This reduces unnecessary processing and prevents blinking
                                if (
                                    "shift+tab" in clean_text.lower()
                                    or "tab to toggle" in clean_text.lower()
                                    or "? for shortcut" in clean_text.lower()
                                ):
                                    self._check_control_settings_status(clean_text)

                                # Check for both "esc to interrupt" and "ctrl+b to run in background"
                                if (
                                    "esc to interrupt" in clean_text
                                    or "ctrl+b to run in background" in clean_text
                                ):
                                    self.last_esc_interrupt_seen = time.time()

                            except Exception:
                                pass
                        else:
                            # Claude process has exited - trigger cleanup
                            self.log(
                                "[INFO] Claude process exited, shutting down wrapper"
                            )
                            self.running = False
                            if self.async_loop and self.async_loop.is_running():
                                self.async_loop.call_soon_threadsafe(
                                    self.async_loop.stop
                                )
                            break
                    except BlockingIOError:
                        pass
                    except OSError:
                        # Claude process has exited - trigger cleanup
                        self.log(
                            "[INFO] Claude process exited (OSError), shutting down wrapper"
                        )
                        self.running = False
                        if self.async_loop and self.async_loop.is_running():
                            self.async_loop.call_soon_threadsafe(self.async_loop.stop)
                        break

                # Handle user input from stdin
                if sys.stdin in rlist and self.original_tty_attrs:
                    try:
                        # Read available data (larger buffer for efficiency)
                        data = os.read(sys.stdin.fileno(), 65536)
                        if data and b"\x1a" in data:
                            data = data.replace(b"\x1a", b"")
                            # Ctrl+Z: suspend child and wrapper
                            self._suspend_for_ctrl_z()
                            try:
                                if self.original_tty_attrs:
                                    tty.setraw(sys.stdin)
                            except Exception:
                                pass
                        if data:
                            # Log user input for debugging
                            try:
                                # Try to decode and log readable text
                                text_input = data.decode("utf-8", errors="replace")

                                # Process the input character by character to handle backspaces
                                for char in text_input:
                                    if char in ["\x7f", "\x08"]:  # Backspace or DEL
                                        # Remove last character from buffer if present
                                        if self.stdin_line_buffer:
                                            self.stdin_line_buffer = (
                                                self.stdin_line_buffer[:-1]
                                            )
                                    elif char not in ["\n", "\r"]:
                                        # Add regular characters to buffer
                                        self.stdin_line_buffer += char

                                # Check if Enter was pressed (newline or carriage return)
                                if "\n" in text_input or "\r" in text_input:
                                    # Log the complete line
                                    line = self.stdin_line_buffer.strip()
                                    if line:
                                        self.log(f"[STDIN] User entered: {repr(line)}")

                                        # Clean the line - remove escape sequences and get just the text
                                        # Remove various ANSI escape sequences
                                        clean_line = re.sub(
                                            r"\x1b\[[^m]*m", "", line
                                        )  # Color codes
                                        clean_line = re.sub(
                                            r"\x1b\[[0-9;]*[A-Za-z]", "", clean_line
                                        )  # Cursor movement
                                        clean_line = re.sub(
                                            r"\x1b[>=\[\]OPI]", "", clean_line
                                        )  # Various single char escapes
                                        clean_line = re.sub(
                                            r"\x1b\([AB012]", "", clean_line
                                        )  # Character set selection
                                        clean_line = re.sub(
                                            r"\x1b\].*?\x07", "", clean_line
                                        )  # OSC sequences
                                        # Remove all remaining control characters except spaces
                                        clean_line = "".join(
                                            c
                                            for c in clean_line
                                            if c.isprintable() or c.isspace()
                                        )
                                        clean_line = clean_line.strip()

                                        # Check for special commands like /clear
                                        if clean_line.startswith("/"):
                                            self.log(
                                                f"[STDIN] ⚠️ Detected slash command: {clean_line}"
                                            )

                                            # Check for session reset commands
                                            if self.reset_handler.check_for_reset_command(
                                                clean_line
                                            ):
                                                self.reset_handler.mark_reset_detected(
                                                    clean_line
                                                )

                                    # Reset buffer for next line
                                    self.stdin_line_buffer = ""
                            except Exception:
                                # If decode fails, log the raw bytes
                                self.log(
                                    f"[STDIN] User input (raw bytes): {data[:100]}"
                                )

                            # Store data in a buffer attribute if PTY is full
                            if not hasattr(self, "pending_write_buffer"):
                                self.pending_write_buffer = b""

                            # Add new data to any pending data (post-processed)
                            self.pending_write_buffer += data

                            # Try to write as much as possible
                            if self.pending_write_buffer:
                                try:
                                    bytes_written = os.write(
                                        self.master_fd, self.pending_write_buffer
                                    )
                                    # Remove written data from buffer
                                    self.pending_write_buffer = (
                                        self.pending_write_buffer[bytes_written:]
                                    )
                                except OSError as e:
                                    if e.errno in (
                                        35,
                                        11,
                                    ):  # EAGAIN/EWOULDBLOCK (35=macOS, 11=Linux)
                                        # PTY buffer full, data remains in pending_write_buffer
                                        pass
                                    else:
                                        self.log(
                                            f"[ERROR] Unexpected error writing to PTY: {e}"
                                        )
                                        raise
                    except OSError as e:
                        self.log(f"[ERROR] Error reading from stdin: {e}")
                        pass

                # Try to flush pending write buffer when PTY might be ready
                if hasattr(self, "pending_write_buffer") and self.pending_write_buffer:
                    try:
                        bytes_written = os.write(
                            self.master_fd, self.pending_write_buffer
                        )
                        self.pending_write_buffer = self.pending_write_buffer[
                            bytes_written:
                        ]
                    except OSError as e:
                        if e.errno not in (35, 11):  # Log unexpected errors
                            self.log(f"[ERROR] Unexpected error flushing buffer: {e}")
                        # PTY still full or other error, will retry next iteration
                        pass

                # Process messages from Vicoa web UI
                if self.input_queue:
                    content = self.input_queue.popleft()

                    # Defense in depth: Filter control commands before sending to Claude
                    # (Primary filtering happens in _process_user_responses, this catches edge cases)
                    if self._handle_control_command(content):
                        continue

                    # Check if this is a permission prompt response
                    if self.pending_permission_options:
                        if content in self.pending_permission_options:
                            # Convert full text to number
                            converted = self.pending_permission_options[content]
                            self.log(
                                f"[INFO] Converting permission response '{content}' to '{converted}'"
                            )
                            content = converted
                        else:
                            # Default to the highest numbered option (last option)
                            max_option = max(self.pending_permission_options.values())
                            self.log(
                                f"[INFO] Unmatched permission response '{content}' - defaulting to option {max_option}"
                            )
                            content = max_option

                        # Always clear the mapping after handling a permission response
                        self.pending_permission_options = {}
                        self.terminal_buffer = ""

                    self.log(
                        f"[INFO] Sending web UI message to Claude: {content[:50]}..."
                    )

                    # Check for session reset commands from web UI
                    if self.reset_handler.check_for_reset_command(content.strip()):
                        self.reset_handler.mark_reset_detected(content.strip())

                    # Send to Claude
                    self._write_all_to_master(content.encode())
                    time.sleep(0.25)
                    self.message_processor.last_message_time = time.time()
                    self.message_processor.pending_input_message_id = None
                    self._write_all_to_master(b"\r")

        finally:
            # Restore terminal settings
            if self.original_tty_attrs:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.original_tty_attrs)

            # Clean up child process
            if self.child_pid:
                try:
                    os.kill(self.child_pid, signal.SIGTERM)
                    os.waitpid(self.child_pid, 0)
                except Exception:
                    pass

    async def idle_monitor_loop(self):
        """Async loop to monitor idle state and request input"""
        self.log("[INFO] Started idle monitor loop")

        if not self.vicoa_client_async:
            self.log("[ERROR] Vicoa async client not initialized")
            return

        # Ensure async client session
        await self.vicoa_client_async._ensure_session()

        while self.running:
            await asyncio.sleep(0.5)  # Check every 500ms

            # Check if we should request input
            message_id = self.message_processor.should_request_input()

            if message_id:
                # Skip if we've already requested input for this message
                if message_id in self.requested_input_messages:
                    continue

                self.log(
                    f"[INFO] Claude is idle, starting request_user_input for message {message_id}"
                )

                # Track that we've requested input for this message
                self.requested_input_messages.add(message_id)

                # Mark as requested
                self.message_processor.mark_input_requested(message_id)

                # Cancel any existing task
                self.cancel_pending_input_request()

                # Start new input request task
                self.pending_input_task = asyncio.create_task(
                    self.request_user_input_async(message_id)
                )

    def _handle_control_command(self, content: str) -> bool:
        """Handle JSON control commands from the web UI.

        Expected formats:
        - Toggle: {"type": "control", "setting": "X", "value": "Y"}
        - Interrupt: {"type": "control", "setting": "interrupt"}

        Returns: True if command was recognized (even if failed), False otherwise
        """
        # Parse JSON control command
        control = self._parse_control_json(content)
        if not control:
            return False  # Not a control command

        setting = control.get("setting")
        if not setting:
            return False

        # Handle interrupt setting (special case - triggers immediate action)
        if setting == "interrupt":
            return self._handle_interrupt_action()

        # Handle toggle settings
        value = control.get("value")

        # Validate setting exists in toggles
        if setting not in self._toggles:
            self._send_feedback_message(f"Unknown setting '{setting}'")
            return True

        # Normalize and validate value
        target_slug = self._normalize_toggle_value(setting, value)
        if not target_slug:
            self._send_feedback_message(f"Invalid value '{value}' for {setting}")
            return True

        # Check if already at target
        current_slug = self._toggles[setting]["current_slug"]
        if current_slug == target_slug:
            self._send_feedback_message(
                self._format_toggle_feedback(setting, target_slug, "already")
            )
            return True

        # Log the request
        current_display = (
            self._humanize_toggle_value(setting, current_slug)
            if current_slug
            else "unknown"
        )
        self.log(
            f"[INFO] Received {setting} set request for {target_slug} (current: {current_display})"
        )

        # Set pending target and cycle
        self._toggles[setting]["pending_target"] = target_slug
        # Ensure target mode is in cycle before attempting to cycle to it
        self._ensure_mode_in_cycle(setting, target_slug)
        success = self._set_toggle(setting, target_slug)

        if not success:
            self._send_feedback_message(
                self._format_toggle_feedback(setting, target_slug, "unable")
            )
            self._toggles[setting]["pending_target"] = None

        return True

    def _handle_interrupt_action(self) -> bool:
        """Handle interrupt action from web UI.

        Clears queued messages, sends Escape key to Claude Code,
        and sends confirmation feedback to user.

        Returns: True (command was handled)
        """
        self.log("[INFO] Received interrupt request from web UI")

        # Clear all queued messages
        queue_size = len(self.input_queue)
        if queue_size > 0:
            self.input_queue.clear()
            self.log(f"[INFO] Cleared {queue_size} queued message(s)")

        # Check if Claude Code is currently running (can be interrupted)
        is_active = not self.is_claude_idle()

        if not is_active:
            self.log("[WARNING] Claude Code appears to be idle (not actively running)")
            self._send_feedback_message("Claude is already idle.")
            return True

        # Send Escape key to Claude Code PTY once
        try:
            self._write_all_to_master(b"\x1b")
            self.log("[INFO] Sent interrupt signal (Escape key) to Claude Code")
        except Exception as e:
            self.log(f"[ERROR] Failed to send interrupt signal: {e}")
            self._send_feedback_message("Failed to interrupt Claude")
            return True

        # Send confirmation feedback to web UI
        self._send_feedback_message("Interrupted · What should Claude do instead?")

        return True

    def _set_toggle(self, setting: str, target_slug: str) -> bool:
        """Cycle toggle until the detected value matches the target.

        Args:
            setting: The setting name (e.g., "permission_mode", "thinking")
            target_slug: The target canonical slug value

        Returns:
            True if successful, False otherwise
        """
        if setting not in self._toggles:
            self.log(f"[ERROR] Unknown setting '{setting}'")
            return False

        toggle = self._toggles[setting]
        cycle = toggle["cycle"]
        key_sequence = toggle["key_sequence"]
        current_slug = toggle["current_slug"] or cycle[0]

        # Find current position in cycle
        try:
            current_index = cycle.index(current_slug)
        except ValueError:
            self.log(
                f"[WARNING] Current {setting} '{current_slug}' is unknown. Assuming first in cycle."
            )
            current_index = 0

        # Find target position in cycle
        try:
            target_index = cycle.index(target_slug)
        except ValueError:
            self.log(f"[ERROR] Target {setting} '{target_slug}' is unknown.")
            return False

        # Calculate how many steps to take
        if current_index == target_index:
            return True

        steps_needed = (target_index - current_index + len(cycle)) % len(cycle)
        self.log(
            f"[INFO] Sending {steps_needed} key presses to cycle {setting} from {current_slug} to {target_slug}"
        )

        # Send key sequences
        for _ in range(steps_needed):
            self._write_all_to_master(key_sequence)
            # A small delay between key presses can improve reliability
            time.sleep(0.1)

        # Optimistically update the state. The UI will eventually be consistent.
        toggle["current_slug"] = target_slug
        display_value = self._humanize_toggle_value(setting, target_slug)
        toggle["last_display"] = display_value

        # Update self.permission_mode for backward compatibility
        if setting == "permission_mode":
            self.permission_mode = display_value

        return True

    def _parse_control_json(self, content: str) -> Optional[Dict[str, str]]:
        """Parse JSON control command from text (can be embedded).

        Supports:
        - Toggle commands: {"type": "control", "setting": "X", "value": "Y"}
        - Interrupt command: {"type": "control", "setting": "interrupt"}
        - Hybrid: "Text description. {"type": "control", ...}"

        Returns: {"setting": "X", "value": "Y"} or {"setting": "interrupt"} or None
        """
        if not content:
            return None

        # Try to find JSON anywhere in the content
        match = CONTROL_JSON_PATTERN.search(content)
        if not match:
            return None

        # Extract the JSON string
        json_str = match.group(0)

        try:
            data = json.loads(json_str)
            if not isinstance(data, dict):
                return None

            if data.get("type") != "control":
                return None

            setting = data.get("setting")
            if not setting:
                return None

            # Value is optional (e.g., interrupt doesn't need a value)
            value = data.get("value")

            if value:
                return {"setting": setting, "value": value}
            else:
                return {"setting": setting}
        except json.JSONDecodeError:
            return None

    def _normalize_toggle_value(
        self, setting: str, value: Optional[str]
    ) -> Optional[str]:
        """Normalize toggle value to canonical slug.

        Examples:
          - permission_mode: "auto accept" → "acceptEdits"
          - thinking: "enabled" → "on"
        """
        if not value:
            return None

        if setting not in self._toggles:
            return None

        keywords = self._toggles[setting]["keywords"]

        cleaned = value.lower().strip()
        cleaned = cleaned.replace("_", "-")
        collapsed = re.sub(r"[^a-z-]", "", cleaned)
        collapsed = collapsed.replace("-", "")

        for slug, keyword_list in keywords.items():
            for keyword in keyword_list:
                normalized_keyword = re.sub(r"[^a-z]", "", keyword.lower())
                if normalized_keyword and normalized_keyword in collapsed:
                    return slug

        # Fallback for permission mode specific cases
        if setting == "permission_mode":
            if "bypass" in collapsed:
                return "bypassPermissions"
            if "plan" in collapsed:
                return "plan"
            if "accept" in collapsed:
                return "acceptEdits"
            if (
                "default" in collapsed
                or "shortcut" in collapsed
                or "manual" in collapsed
            ):
                return "default"

        return None

    def _humanize_toggle_value(self, setting: str, slug: str) -> str:
        """Convert slug to human-readable display.

        Examples:
          - permission_mode, "plan" → "plan mode"
          - thinking, "on" → "thinking on"
        """
        if setting not in self._toggles:
            return slug

        labels = self._toggles[setting]["labels"]
        return labels.get(slug, slug)

    def _ensure_mode_in_cycle(self, setting: str, slug: str) -> None:
        """Ensure a mode is in the cycle, adding it if necessary.

        For permission_mode, bypassPermissions is added at the beginning
        when first detected. This allows dynamic cycle adaptation:
          - Without bypass: default → acceptEdits → plan
          - With bypass: bypassPermissions → default → acceptEdits → plan
        """
        if setting not in self._toggles:
            return

        toggle = self._toggles[setting]
        cycle = toggle["cycle"]

        # Already in cycle - nothing to do
        if slug in cycle:
            return

        # Add to cycle based on setting type
        if setting == "permission_mode" and slug == "bypassPermissions":
            # Insert at beginning for bypass permissions
            cycle.insert(0, slug)
            self.log(
                f"[INFO] Expanded permission_mode cycle to include bypassPermissions: {cycle}"
            )

    def _format_toggle_feedback(
        self, setting: str, slug: str, message_type: str = "changed"
    ) -> str:
        """Format feedback message for toggle state changes.

        Args:
            setting: The setting name (e.g., "permission_mode", "thinking")
            slug: The canonical slug value
            message_type: Type of message - "changed", "already", or "unable"

        Returns:
            Formatted feedback message with proper grammar
        """
        display_value = self._humanize_toggle_value(setting, slug)
        setting_name = setting.replace("_", " ").capitalize()

        # Special handling for thinking to avoid repetition
        if setting == "thinking":
            if message_type == "changed":
                # "Thinking turned on" instead of "Thinking changed to thinking on"
                return f"Thinking turned {slug}"
            elif message_type == "already":
                # "Thinking is already off" instead of "Thinking is already thinking off"
                return f"Thinking is already {slug}"
            else:  # "unable"
                return f"Unable to set thinking to {slug}"
        else:
            # For permission_mode and others, use the full display value
            if message_type == "changed":
                return f"{setting_name} changed to {display_value}"
            elif message_type == "already":
                return f"{setting_name} is already {display_value}"
            else:  # "unable"
                return f"Unable to set {setting.replace('_', ' ')} to {display_value}"

    def _update_toggle_state(
        self, setting: str, slug: str, consumed_upto: Optional[int] = None
    ):
        """Update toggle state and send notifications if needed.

        Args:
            setting: The setting name (e.g., "permission_mode", "thinking")
            slug: The new canonical slug value
            consumed_upto: Optional buffer position to clear up to
        """
        if setting not in self._toggles:
            return

        toggle = self._toggles[setting]
        current_slug = toggle["current_slug"]
        last_display = toggle["last_display"]
        pending_target = toggle["pending_target"]

        # No change detected - could be due to optimistic update
        if current_slug == slug:
            # If this matches a pending target, it means terminal confirmed our optimistic update
            if pending_target == slug:
                display_mode = self._humanize_toggle_value(setting, slug)
                self.log(
                    f"[INFO] Terminal confirmed {setting} change to: {display_mode}"
                )
                # Send notification for user-requested change
                self._send_feedback_message(
                    self._format_toggle_feedback(setting, slug, "changed")
                )
                toggle["pending_target"] = None
            return

        # Check if this is the initial detection (first time seeing this setting)
        is_initial_detection = last_display is None

        # Get display value
        display_mode = self._humanize_toggle_value(setting, slug)

        # Log the change
        if is_initial_detection:
            self.log(f"[INFO] Initial {setting} detected: {display_mode}")
        else:
            self.log(f"[INFO] {setting} changed to: {display_mode}")

        # Update state
        toggle["current_slug"] = slug
        toggle["last_display"] = display_mode

        # Update self.permission_mode for backward compatibility
        if setting == "permission_mode":
            self.permission_mode = display_mode

        # Ensure the mode is in the cycle (dynamically expand if needed)
        self._ensure_mode_in_cycle(setting, slug)

        # Determine if we should notify the user (check BEFORE clearing pending_target)
        should_notify = False
        if pending_target == slug:
            # Reached the target state - notify
            should_notify = True
            toggle["pending_target"] = None  # Clear after confirming we'll notify
        elif not is_initial_detection and not pending_target:
            # Manual change (no pending target) - notify
            # Don't notify for intermediate states during cycling
            should_notify = True
        elif (
            is_initial_detection
            and setting == "permission_mode"
            and slug == "bypassPermissions"
        ):
            # Initial detection of bypassPermissions - notify so frontend knows
            # This is important for --dangerously-skip-permissions to be detected
            # We only notify for bypassPermissions on startup, not other modes
            should_notify = True

        # Send notification only once per actual state change
        if should_notify:
            self._send_feedback_message(
                self._format_toggle_feedback(setting, slug, "changed")
            )

    def _send_feedback_message(self, message: str) -> None:
        """Send a status update to Vicoa about local control actions."""

        if not self.vicoa_client_sync or not self.agent_instance_id:
            self.log(
                "[WARNING] Cannot send feedback: vicoa_client_sync or agent_instance_id not initialized"
            )
            return

        try:
            response = self.vicoa_client_sync.send_message(
                content=message,
                agent_type=self.name,
                agent_instance_id=self.agent_instance_id,
                requires_user_input=False,
            )
            if response and response.queued_user_messages:
                for queued in response.queued_user_messages:
                    self.log(
                        f"[INFO] Processing queued user message after feedback: {queued[:50]}..."
                    )
                    self.message_processor.process_user_message_sync(
                        queued, from_web=True
                    )
                    self.input_queue.append(queued)
        except Exception as exc:
            self.log(f"[ERROR] ❌ Failed to send feedback message '{message}': {exc}")

    def _check_control_settings_status(self, clean_text: str) -> None:
        """Detect control setting banner changes from terminal output.

        Detects both permission mode and thinking toggle from the same terminal line.
        Note: clean_text should already have ANSI escape sequences removed by caller.
        """
        if not clean_text:
            return

        self._control_detection_buffer += clean_text.replace("\r", "\n")
        if len(self._control_detection_buffer) > 4000:
            self._control_detection_buffer = self._control_detection_buffer[-4000:]

        # Parse permission mode
        permission_entries: list[dict[str, Any]] = []
        for match in PERMISSION_MODE_PATTERN.finditer(self._control_detection_buffer):
            # Check if this match is from "? for shortcuts" or "(shift+tab to cycle)"
            matched_text = match.group(0)
            is_shortcuts_match = "? for shortcuts" in matched_text.lower()

            if is_shortcuts_match:
                raw_mode = "shortcuts"
            else:
                raw_mode = match.group(1).strip()

            if not raw_mode:
                continue

            normalized = raw_mode.replace("⏵⏵", "").replace("⏸", "").strip()
            normalized = re.sub(
                r"[\s\u2500-\u257F\u25A0-\u25FF]+", " ", normalized
            ).strip()
            normalized = normalized.strip("- ")

            if not normalized:
                continue

            has_on = normalized.lower().endswith(" on")
            trimmed = normalized[:-3].strip() if has_on else normalized
            if not trimmed:
                continue

            slug = self._normalize_toggle_value("permission_mode", trimmed)

            # Only add entries that resolve to a known permission mode
            if slug:
                permission_entries.append(
                    {
                        "raw": normalized,
                        "trimmed": trimmed,
                        "slug": slug,
                        "end": match.end(),
                        "has_on": has_on,
                        "is_shortcuts": is_shortcuts_match,  # Track the source
                    }
                )

        # Parse thinking toggle
        thinking_entries: list[dict[str, Any]] = []
        for match in THINKING_TOGGLE_PATTERN.finditer(self._control_detection_buffer):
            state = match.group(1).lower()  # "on" or "off"
            thinking_entries.append({"slug": state, "end": match.end()})

        # Track the maximum consumed position from both settings
        max_consumed_upto = 0

        # Update permission mode if detected
        if permission_entries:
            selected_entry: Optional[dict[str, Any]] = None
            pending_target = self._toggles["permission_mode"]["pending_target"]

            if pending_target:
                for entry in reversed(permission_entries):
                    if entry["slug"] == pending_target:
                        selected_entry = entry
                        break

            if not selected_entry:
                # Prefer shift+tab entries over "? for shortcuts" entries
                # When both are present (e.g., acceptEdits mode with empty input),
                # use shift+tab as it's the actual mode indicator
                non_shortcuts = [
                    e for e in permission_entries if not e.get("is_shortcuts")
                ]
                if non_shortcuts:
                    # Found shift+tab entries - use the last one
                    selected_entry = non_shortcuts[-1]
                else:
                    # Only "? for shortcuts" found - use it (default mode)
                    selected_entry = permission_entries[-1]

            slug = selected_entry["slug"]
            consumed_upto = selected_entry["end"]

            if consumed_upto is not None and consumed_upto > max_consumed_upto:
                max_consumed_upto = consumed_upto

            # Update state using unified method
            self._update_toggle_state("permission_mode", slug)

        # Update thinking toggle if detected
        if thinking_entries:
            # Use the most recent thinking entry
            selected_thinking = thinking_entries[-1]
            slug = selected_thinking["slug"]
            consumed_upto = selected_thinking.get("end")

            if consumed_upto is not None and consumed_upto > max_consumed_upto:
                max_consumed_upto = consumed_upto

            # Update state using unified method
            self._update_toggle_state("thinking", slug)

        # Clear buffer up to the maximum consumed position
        if max_consumed_upto > 0:
            self._control_detection_buffer = self._control_detection_buffer[
                max_consumed_upto:
            ]

    def run(self):
        """Run Claude with Vicoa integration (main entry point)"""
        self.log("[INFO] Starting run() method")

        try:
            # Initialize Vicoa clients (sync)
            self.log("[INFO] Initializing Vicoa clients...")
            self.init_vicoa_clients()
            self.log("[INFO] Vicoa clients initialized")

            # Register agent instance only if starting a new session
            if self.is_resuming:
                self.log(
                    f"[INFO] Resuming session with instance ID: {self.agent_instance_id}"
                )
            else:
                self.log("[INFO] Registering new agent instance...")
                if self.vicoa_client_sync:
                    from .utils.initial_session_config import (
                        build_initial_session_config,
                    )

                    initial_session_config = build_initial_session_config(
                        anthropic_model_env=os.environ.get("ANTHROPIC_MODEL"),
                        permission_mode=getattr(self, "permission_mode", None),
                        dangerously_skip_permissions=bool(
                            getattr(self, "dangerously_skip_permissions", False)
                        ),
                    )
                    registration = self.vicoa_client_sync.register_agent_instance(
                        agent_type=self.name,
                        transport="local",
                        agent_instance_id=self.agent_instance_id,
                        name=None,
                        project=get_project_path(),
                        home_dir=str(Path.home()),
                        session_config=initial_session_config,
                        source="terminal",
                    )
                    self.agent_instance_id = registration.agent_instance_id
                    self.log(
                        f"[INFO] Registered agent instance: {self.agent_instance_id}"
                    )

                # Create initial session (sync)
                self.log("[INFO] Creating initial Vicoa session...")
                if self.vicoa_client_sync:
                    response = self.vicoa_client_sync.send_message(
                        content=f"{self.name} session started, waiting for your input...",
                        agent_type=self.name,
                        agent_instance_id=self.agent_instance_id,
                        requires_user_input=False,
                    )

                    # Initialize message processor with first message
                    if hasattr(self.message_processor, "last_message_id"):
                        self.message_processor.last_message_id = response.message_id
                        self.message_processor.last_message_time = time.time()

            # Start heartbeat thread
            try:
                if not self.heartbeat_thread:
                    self.heartbeat_thread = threading.Thread(
                        target=self._heartbeat_loop, daemon=True
                    )
                    self.heartbeat_thread.start()
                    self.log("[INFO] Heartbeat loop started")
            except Exception as e:
                self.log(f"[WARN] Failed to start heartbeat loop: {e}")
        except AuthenticationError as e:
            # Log the error
            self.log(f"[ERROR] Authentication failed: {e}")

            # Print user-friendly error message
            print(
                "\nError: Authentication failed. Please check for valid Vicoa API key in ~/.vicoa/credentials.json.",
                file=sys.stderr,
            )

            # Clean up and exit
            if self.vicoa_client_sync:
                self.vicoa_client_sync.close()
            if self.debug_log_file:
                self.debug_log_file.close()
            sys.exit(1)

        except APIError as e:
            # Log the error
            self.log(f"[ERROR] API error: {e}")

            # Print user-friendly error message based on status code
            if e.status_code >= 500:
                print(
                    "\nError: Vicoa server error. Please try again later.",
                    file=sys.stderr,
                )
            elif e.status_code == 404:
                print(
                    "\nError: Vicoa endpoint not found. Please check your base URL.",
                    file=sys.stderr,
                )
            else:
                print(f"\nError: Vicoa API error: {e}", file=sys.stderr)

            # Clean up and exit
            if self.vicoa_client_sync:
                self.vicoa_client_sync.close()
            if self.debug_log_file:
                self.debug_log_file.close()
            sys.exit(1)

        except Exception as e:
            # Log the error
            self.log(f"[ERROR] Failed to initialize Vicoa connection: {e}")

            # Print user-friendly error message
            error_msg = str(e)
            if "connection" in error_msg.lower() or "refused" in error_msg.lower():
                print("\nError: Could not connect to Vicoa server.", file=sys.stderr)
                print(
                    "Please check your internet connection and try again.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"\nError: Failed to connect to Vicoa: {error_msg}",
                    file=sys.stderr,
                )

            # Clean up and exit
            if self.vicoa_client_sync:
                self.vicoa_client_sync.close()
            if self.debug_log_file:
                self.debug_log_file.close()
            sys.exit(1)

        # Start Claude in PTY (in thread)
        claude_thread = threading.Thread(target=self.run_claude_with_pty)
        claude_thread.daemon = True
        claude_thread.start()

        # Wait a moment for Claude to start
        time.sleep(1.0)

        # Start JSONL monitor thread
        self.jsonl_monitor_thread = threading.Thread(target=self.monitor_claude_jsonl)
        self.jsonl_monitor_thread.daemon = True
        self.jsonl_monitor_thread.start()

        # Run async idle monitor in event loop
        try:
            self.async_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.async_loop)
            self.async_loop.run_until_complete(self.idle_monitor_loop())
        except (KeyboardInterrupt, RuntimeError):
            # RuntimeError happens when loop.stop() is called
            pass
        finally:
            # Clean up
            self.running = False
            self.log("[INFO] Shutting down wrapper...")

            # Print exit message immediately for better UX
            if not sys.exc_info()[0]:
                print("\nEnded Vicoa Claude Session\n", file=sys.stderr)

            # Quick cleanup - cancel pending tasks
            self.cancel_pending_input_request()

            # Run cleanup in background thread with timeout
            def background_cleanup():
                import threading

                # Create a timer to force exit after 10 seconds
                def force_exit():
                    self.log("[WARNING] Cleanup timeout reached, forcing exit")
                    if self.debug_log_file:
                        self.debug_log_file.flush()
                    os._exit(0)

                timer = threading.Timer(10.0, force_exit)
                timer.daemon = True
                timer.start()

                try:
                    if self.vicoa_client_sync and self.agent_instance_id:
                        self.vicoa_client_sync.end_session(self.agent_instance_id)
                        self.log("[INFO] Session ended successfully")

                    if self.vicoa_client_sync:
                        self.vicoa_client_sync.close()

                    if self.vicoa_client_async:
                        # Close async client synchronously
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(self.vicoa_client_async.close())
                        loop.close()

                    if self.debug_log_file:
                        self.log("=== Claude Wrapper V3 Log Ended ===")
                        self.debug_log_file.flush()
                        self.debug_log_file.close()

                    # Cancel timer if cleanup completed successfully
                    timer.cancel()

                except Exception as e:
                    self.log(f"[ERROR] Background cleanup error: {e}")
                    if self.debug_log_file:
                        self.debug_log_file.flush()
                    timer.cancel()

            # Start background cleanup as non-daemon thread
            cleanup_thread = threading.Thread(target=background_cleanup)
            cleanup_thread.daemon = False
            cleanup_thread.start()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Claude wrapper V3 for Vicoa integration",
        add_help=False,  # Disable help to pass through to Claude
    )
    parser.add_argument("--api-key", help="Vicoa API key")
    parser.add_argument("--base-url", help="Vicoa base URL")
    parser.add_argument(
        "--name",
        default="Claude Code",
        help="Name of the agent (defaults to 'Claude Code')",
    )
    parser.add_argument(
        "--permission-mode",
        choices=["acceptEdits", "bypassPermissions", "default", "plan"],
        help="Permission mode to use for the session",
    )
    parser.add_argument(
        "--dangerously-skip-permissions",
        action="store_true",
        help="Bypass all permission checks. Recommended only for sandboxes with no internet access.",
    )
    parser.add_argument(
        "--idle-delay",
        type=float,
        default=3.5,
        help="Delay in seconds before considering Claude idle (default: 3.5)",
    )
    parser.add_argument(
        "--agent-instance-id",
        help="Agent instance ID to use for this session (will be used as --session-id for Claude Code)",
    )

    # Parse known args and pass the rest to Claude
    args, claude_args = parser.parse_known_args()

    # Check if --resume flag is present
    is_resuming = any(arg in ["--resume", "-r"] for arg in claude_args)

    # Check if --continue (not --resume) in claude_args - only bypass for --continue
    # We now support --resume with Vicoa integration
    if any(arg in ["--continue", "-c"] for arg in claude_args):
        print(
            "\n⚠️  Warning: --continue flag is not yet fully supported by Vicoa.",
            file=sys.stderr,
        )
        print(
            "   The flag will be passed to Claude Code, but conversation history may not appear in the Vicoa dashboard.\n",
            file=sys.stderr,
        )
        try:
            claude_path = find_claude_cli()
            # claude_args already has Vicoa flags filtered out!
            os.execvp(claude_path, [claude_path] + claude_args)
            # Never returns - process is replaced
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    # Update sys.argv to only include Claude args
    sys.argv = [sys.argv[0]] + claude_args

    wrapper = ClaudeWrapper(
        api_key=args.api_key,
        base_url=args.base_url,
        permission_mode=args.permission_mode,
        dangerously_skip_permissions=args.dangerously_skip_permissions,
        name=args.name,
        idle_delay=args.idle_delay,
        agent_instance_id=args.agent_instance_id,
        is_resuming=is_resuming,
    )

    def signal_handler(sig, frame):
        # Check if this is a repeated Ctrl+C (user really wants to exit)
        if not wrapper.running:
            # Second Ctrl+C - exit immediately
            print("\nForce exiting...", file=sys.stderr)
            os._exit(1)

        # First Ctrl+C - initiate graceful shutdown
        wrapper.running = False
        wrapper.log("[INFO] SIGINT received, initiating shutdown")

        # Stop the async event loop to trigger cleanup
        if wrapper.async_loop and wrapper.async_loop.is_running():
            wrapper.async_loop.call_soon_threadsafe(wrapper.async_loop.stop)

        if wrapper.child_pid:
            try:
                # Kill Claude process to trigger exit
                os.kill(wrapper.child_pid, signal.SIGTERM)
            except Exception:
                pass

    def handle_resize(sig, frame):
        """Handle terminal resize signal"""
        if wrapper.master_fd:
            try:
                # Get new terminal size
                cols, rows = os.get_terminal_size()
                # Update PTY size
                import fcntl
                import struct

                TIOCSWINSZ = 0x80087467 if sys.platform == "darwin" else 0x5414
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(wrapper.master_fd, TIOCSWINSZ, winsize)
            except Exception:
                pass

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)  # Handle terminal close
    signal.signal(signal.SIGHUP, signal_handler)  # Handle terminal disconnect
    signal.signal(signal.SIGWINCH, handle_resize)  # Handle terminal resize

    try:
        wrapper.run()
    except Exception as e:
        # Fatal errors still go to stderr
        print(f"Fatal error: {e}", file=sys.stderr)
        if wrapper.original_tty_attrs:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, wrapper.original_tty_attrs)
        if hasattr(wrapper, "debug_log_file") and wrapper.debug_log_file:
            wrapper.log(f"[FATAL] {e}")
            wrapper.debug_log_file.close()
        sys.exit(1)


if __name__ == "__main__":
    main()
