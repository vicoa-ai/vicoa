"""Async input request management for Claude Code Wrapper.

Receives user messages via SSE subscription to the servers
``/api/v1/agents/instances/{id}/stream`` endpoint instead of polling.

Two concurrent async tasks run in the same event loop:
- ``sse_listener_loop``: subscribes to SSE and delivers user messages instantly.
- ``idle_monitor_loop``: detects when Claude is idle and calls
  ``PATCH /messages/{id}/request-input`` to mark the last message as needing
  input (sets ``requires_user_input=True``, transitions status to
  ``AWAITING_INPUT``, fires push notifications to web/app).
"""

import asyncio
import base64
import json
import os
import threading
import time
from typing import Any, Callable, Optional, Set, TYPE_CHECKING
from urllib.parse import urljoin

import aiohttp

from vicoa.attachments import (
    attachment_note,
    attachments_dir,
    extract_attachment_refs,
    save_attachment,
    unavailable_note,
)
from vicoa.sdk.exceptions import AuthenticationError
from vicoa.session_ws_client import SessionMessagesWsClient
from vicoa.utils import derive_ws_url

if TYPE_CHECKING:
    from vicoa.sdk.async_client import AsyncVicoaClient
    from .processor import MessageProcessor
    from .queue_manager import MessageQueue
    from ..state.session_state import SessionState
    from ..state.toggle_manager import ToggleManager
    from ..terminal.pty_manager import PTYManager
from ..config import CONTROL_JSON_PATTERN


class InputRequestManager:
    """Manages user input delivery from Vicoa web/app UI to the CLI wrapper.

    Connects to the servers SSE endpoint and receives ``user_message`` events
    in real-time, replacing the previous 1.5 s control poller and 3 s
    long-poll input-request loop.
    """

    # Upper bound on how long we wait for Claude TUI's slash-command
    # confirmation echo ("Set model to" / "Set effort level to") after
    # writing a /model or /effort to the PTY. The wait unblocks the next
    # control command — without it, two slash commands dispatched
    # back-to-back (model + effort in one mobile confirm) race Claude's
    # input parser and the second is sometimes dropped. On timeout we
    # log + proceed; the optimistic PATCH still runs and JSONLMonitor
    # self-heals if Claude actually rejected the slug.
    SLASH_COMMAND_ECHO_TIMEOUT_S: float = 3.0
    SLASH_COMMAND_ECHO_POLL_INTERVAL_S: float = 0.05

    def __init__(
        self,
        agent_instance_id: str,
        agent_name: str,
        vicoa_client_async: Optional["AsyncVicoaClient"],
        vicoa_client_sync,  # VicoaClient
        message_processor: "MessageProcessor",
        message_queue: "MessageQueue",
        session_state: "SessionState",
        toggle_manager: "ToggleManager",
        pty_manager: "PTYManager",
        log_func: Callable[[str], None],
        on_ask_user_question_submitted: Optional[Callable[[], None]] = None,
    ):
        """Initialize input request manager.

        Args:
            agent_instance_id: Agent instance ID
            agent_name: Agent display name
            vicoa_client_async: Async Vicoa client for long-polling
            vicoa_client_sync: Sync Vicoa client for feedback messages
            message_processor: Message processor instance
            message_queue: Message queue for queuing responses to CLI
            session_state: Session state manager
            toggle_manager: Toggle manager for control settings
            pty_manager: PTY manager for sending interrupts
            log_func: Logging function
        """
        self.agent_instance_id = agent_instance_id
        self.agent_name = agent_name
        self.vicoa_client_async = vicoa_client_async
        self.vicoa_client_sync = vicoa_client_sync
        self.message_processor = message_processor
        self.message_queue = message_queue
        self.session_state = session_state
        self.toggle_manager = toggle_manager
        self.pty_manager = pty_manager
        self.log = log_func

        # State
        self.on_ask_user_question_submitted = on_ask_user_question_submitted

        # State
        self.running = True
        self.async_loop: Optional[asyncio.AbstractEventLoop] = None
        self.async_thread: Optional[threading.Thread] = None
        self.requested_input_messages: Set[str] = set()
        self._status_is_awaiting_input: bool = False

        # WebSocket transport (websocket-migration §4 Phase 3). Default path
        # for any session with an async client; URL is derived from the REST
        # base_url unless ``VICOA_WS_URL`` is set to override.
        self.ws_client: Optional[SessionMessagesWsClient] = None
        self.ws_thread: Optional[threading.Thread] = None

        # SSE observability — track when we last received any event from the
        # stream (including server heartbeats). Used for diagnosis when the
        # stream silently stalls.
        self.last_sse_event_time: float = time.time()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the message transport and idle monitor in a background thread.

        User messages arrive over the Phase 3 WebSocket client whenever an
        async client is available; the URL is derived from the REST base_url
        unless ``VICOA_WS_URL`` is set to override. The SSE listener remains
        as a fallback only when no async client was constructed.
        """
        ws_url: Optional[str] = None
        if self.vicoa_client_async is not None:
            ws_url = os.getenv("VICOA_WS_URL") or derive_ws_url(
                self.vicoa_client_async.base_url
            )
        use_ws = ws_url is not None

        async def run_both():
            await asyncio.gather(
                self.sse_listener_loop(),
                self.idle_monitor_loop(),
            )

        def run_async_loop():
            try:
                self.async_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.async_loop)
                if use_ws:
                    assert ws_url is not None
                    self._start_ws_client(ws_url)
                    self.async_loop.run_until_complete(self.idle_monitor_loop())
                else:
                    self.async_loop.run_until_complete(run_both())
            except (KeyboardInterrupt, RuntimeError):
                pass
            except Exception as e:
                self.log(f"[ERROR] Error in async loop: {e}")

        self.async_thread = threading.Thread(target=run_async_loop, daemon=True)
        self.async_thread.start()

    def stop(self) -> None:
        """Stop the message transport and idle monitor."""
        self.running = False
        if self.ws_client is not None:
            self.ws_client.stop()
        if self.async_loop and self.async_loop.is_running():
            self.async_loop.call_soon_threadsafe(self.async_loop.stop)

    # ------------------------------------------------------------------
    # WebSocket transport (websocket-migration §4 Phase 3)
    # ------------------------------------------------------------------

    def _start_ws_client(self, ws_url: str) -> None:
        """Run the session WebSocket client on its own thread.

        The client owns its full-jitter reconnect loop (§2.10). Its
        ``on_user_message`` callback marshals each message onto the asyncio
        loop, so message handling stays single-threaded with the idle
        monitor — exactly as the SSE listener dispatched from that loop.
        """
        # Imported lazily to avoid a package-load import cycle.
        from .. import __version__

        self.ws_client = SessionMessagesWsClient(
            ws_url=ws_url,
            api_key=self.vicoa_client_async.api_key,  # type: ignore[union-attr]
            instance_id=self.agent_instance_id,
            on_user_message=self._on_ws_user_message,
            cli_version=__version__,
        )
        self.ws_thread = threading.Thread(target=self._ws_thread_target, daemon=True)
        self.ws_thread.start()
        self.log("[INFO] Session WebSocket client started")

    def _ws_thread_target(self) -> None:
        """Thread target that absorbs a fatal-auth AuthenticationError.

        ``ws_client.run()`` re-raises on a 4401 ``credential_revoked`` close
        (server-side push when the JWT's user no longer exists). PR #45's
        wrapper-side ``_drop_vicoa_link`` handlers cover REST call sites but
        NOT this thread's run(). Without a wrap, the thread dies with an
        unhandled exception and Python prints the traceback to stderr —
        which the TUI shares, bleeding a multi-line stack trace into the
        user's session. Catch it here, log a clean one-liner, and let the
        thread exit silently. Claude itself keeps running; only the Vicoa
        link goes quiet.
        """
        client = self.ws_client
        if client is None:
            return  # Defensive: thread started before ws_client was assigned.
        try:
            client.run()
        except AuthenticationError as exc:
            self.log(f"[INFO] Vicoa session link closed: {exc}")

    def _on_ws_user_message(self, body: dict) -> None:
        """WS-thread callback: hand a user message to the asyncio loop.

        Marshalling via ``call_soon_threadsafe`` keeps message handling on the
        loop thread, so it never races the idle monitor over MessageProcessor
        state — the same single-threaded model the SSE path had.

        Attachments are downloaded on a short-lived side thread (the WS reader
        must keep servicing pings) and appended to the content as
        ``[Attached …: <path>]`` lines BEFORE queuing — the PTY can only carry
        text, and Claude Code's Read tool (vision-capable for images) picks the
        paths up from the prompt. A slow download can therefore deliver this
        message after a later text-only one (accepted ordering tradeoff).
        """
        content = body.get("content", "")
        attachments = extract_attachment_refs(body.get("message_metadata"))
        if not content and not attachments:
            return
        if attachments:
            threading.Thread(
                target=self._resolve_attachments_then_queue,
                args=(content, attachments),
                daemon=True,
            ).start()
            return
        loop = self.async_loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._handle_user_message, content)

    def _resolve_attachments_then_queue(self, content: str, attachments) -> None:
        """Download image attachments to local files and queue the augmented text."""
        notes = []
        for ref in attachments:
            try:
                data, mime_type = self.vicoa_client_sync.download_attachment(ref.id)
                local = save_attachment(
                    attachments_dir(self.agent_instance_id), ref, data, mime_type
                )
                notes.append(attachment_note(local))
            except Exception as e:
                self.log(f"[ERROR] Failed to download attachment {ref.id}: {e}")
                notes.append(unavailable_note(ref))
        augmented = "\n".join(part for part in [content, *notes] if part)
        loop = self.async_loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._handle_user_message, augmented)

    # ------------------------------------------------------------------
    # SSE listener
    # ------------------------------------------------------------------

    async def sse_listener_loop(self) -> None:
        """Connect to the servers SSE endpoint and process user_message events.

        Reconnects with exponential back-off (1 s → 2 s → 4 s … capped at 60 s)
        so transient network blips are handled transparently.
        """
        if not self.vicoa_client_async:
            self.log(
                "[ERROR] Vicoa async client not initialized; SSE listener will not start"
            )
            return

        await self.vicoa_client_async._ensure_session()

        base_url = self.vicoa_client_async.base_url
        stream_url = urljoin(
            base_url.rstrip("/") + "/",
            f"api/v1/agents/instances/{self.agent_instance_id}/stream",
        )
        headers = {
            "Authorization": f"Bearer {self.vicoa_client_async.api_key}",
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }

        backoff = 1.0
        max_backoff = 60.0

        while self.running:
            try:
                self.log(f"[INFO] SSE connecting to {stream_url}")
                ssl_ctx = self.vicoa_client_async.session.connector._ssl  # type: ignore[union-attr]

                # sock_read=30 means "no bytes for 30s → tear down". Server
                # sends heartbeat events every ~15s, so 30s = ~2 missed
                # heartbeats. Was 60s previously — too lenient; a partially
                # degraded server that keeps the TCP socket open but stops
                # sending data would never trip a reconnect.
                timeout = aiohttp.ClientTimeout(total=None, sock_read=30)
                async with aiohttp.ClientSession(
                    headers=headers,
                    timeout=timeout,
                ) as sse_session:
                    async with sse_session.get(stream_url, ssl=ssl_ctx) as resp:
                        if resp.status != 200:
                            body = await resp.text()
                            self.log(
                                f"[WARNING] SSE endpoint returned {resp.status}: {body}"
                            )
                            await asyncio.sleep(backoff)
                            backoff = min(backoff * 2, max_backoff)
                            continue

                        self.log("[INFO] SSE stream connected")
                        backoff = 1.0  # reset on success

                        await self._read_sse_stream(resp)

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.running:
                    self.log(
                        f"[WARNING] SSE connection error: {e}; reconnecting in {backoff:.0f}s"
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)

    async def _read_sse_stream(self, resp: aiohttp.ClientResponse) -> None:
        """Parse the SSE byte stream and dispatch events."""
        event_name = "message"
        data_lines: list[str] = []

        async for raw_line in resp.content:
            if not self.running:
                break

            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")

            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
            elif line == "":
                # Blank line = end of event
                if data_lines:
                    raw_data = "\n".join(data_lines)
                    self._dispatch_event(event_name, raw_data)
                event_name = "message"
                data_lines = []

    def _dispatch_event(self, event_name: str, raw_data: str) -> None:
        """Handle a fully-parsed SSE event."""
        # Update activity timestamp on every event (including heartbeats) so
        # post-mortems can tell when the stream actually went silent.
        self.last_sse_event_time = time.time()

        if event_name == "heartbeat":
            return

        if event_name == "connected":
            self.log("[INFO] Stream acknowledged by server")
            return

        if event_name == "error":
            self.log(f"[WARNING] Server sent error event: {raw_data}")
            return

        if event_name == "user_message":
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                self.log(
                    f"[WARNING] Could not parse user_message payload: {raw_data[:200]}"
                )
                return

            self._handle_user_message(data.get("content", ""))

    def _handle_user_message(self, content: str) -> None:
        """Process one user-message content string from web/app.

        Shared by the SSE listener and the Phase 3 WebSocket client; runs on
        the asyncio loop thread for both.
        """
        if not content:
            return

        # Control commands from the web/app must always execute regardless of
        # deduplication — they are never "echoes" of TUI input.
        if self._handle_control_command(content):
            self.message_processor.pending_input_message_id = None
            self.message_processor.last_message_id = None
            self.requested_input_messages.clear()
            return

        # If this message was originated from the TUI, the JSONL monitor
        # already tracked it in the deduplicator before forwarding it to the
        # backend. Drop the echo so we don't send the message to Claude twice.
        if self.message_processor.deduplicator.is_duplicate(content):
            self.log(f"[DEBUG] Echo suppressed (TUI origin): {content[:80]!r}")
            # Still clear the pending-input state — the user did reply.
            self.message_processor.pending_input_message_id = None
            self.message_processor.last_message_id = None
            self.requested_input_messages.clear()
            return

        # Message originated from web/app UI — track it and forward to Claude.
        self.message_processor.process_user_message_sync(content, from_web=True)

        # Clear pending input state — user replied; allows idle monitor to re-arm
        self.message_processor.pending_input_message_id = None
        self.message_processor.last_message_id = None
        self.requested_input_messages.clear()

        # injection_tracker.mark_injected is called from _process_queued_message
        # (post permission-option rewrite, pre-PTY write) so the tracked
        # content matches what Claude will actually transcribe to JSONL.
        self.message_queue.append(content)

    # ------------------------------------------------------------------
    # Idle monitor: signals web/app that Claude is waiting for input
    # ------------------------------------------------------------------

    async def idle_monitor_loop(self) -> None:
        """Detect when Claude is idle and call PATCH /messages/{id}/request-input.

        Runs every 500 ms. When ``should_request_input`` returns a message_id,
        calls the PATCH endpoint to mark the message as requiring user input.
        This triggers the ``AWAITING_INPUT`` status transition and push
        notifications on web/app — SSE then delivers the user's reply.
        """
        if not self.vicoa_client_async:
            self.log(
                "[ERROR] Vicoa async client not initialized; idle monitor will not start"
            )
            return

        await self.vicoa_client_async._ensure_session()
        self.log("[INFO] Idle monitor started")

        while self.running:
            await asyncio.sleep(0.5)

            try:
                is_idle = self.session_state.is_claude_idle()

                # When Claude transitions from idle → busy, reset the flag so we
                # set AWAITING_INPUT again the next time it goes idle.
                if not is_idle and self._status_is_awaiting_input:
                    self._status_is_awaiting_input = False

                # When Claude is idle and we haven't marked it yet, set the status —
                # but only if the backend still considers the session ACTIVE.
                # The user may have reviewed/closed the session from web/app.
                # When Claude is idle and we haven't marked it yet, set the status —
                # but only if the backend still considers the session ACTIVE.
                # The user may have reviewed/closed the session from web/app.
                # _status_is_awaiting_input gates the API call for the whole idle period
                # and resets when Claude goes busy again, so the check runs once per cycle.
                if is_idle and not self._status_is_awaiting_input:
                    try:
                        instance = await self.vicoa_client_async.get_agent_instance(
                            self.agent_instance_id
                        )
                        current_status = instance.get("status")
                    except Exception as fetch_err:
                        self.log(
                            f"[WARNING] Failed to fetch instance status: {fetch_err}"
                        )
                        current_status = None

                    if current_status == "ACTIVE":
                        self._status_is_awaiting_input = True
                        try:
                            await self.vicoa_client_async.update_agent_instance_status(
                                self.agent_instance_id, "AWAITING_INPUT"
                            )
                        except Exception as status_err:
                            self.log(
                                f"[WARNING] Failed to set status to AWAITING_INPUT: {status_err}"
                            )
                    else:
                        # Gate further attempts for this idle period to avoid log spam.
                        # The flag resets when Claude goes busy again.
                        self._status_is_awaiting_input = True

                message_id = self.message_processor.should_request_input(
                    lambda: is_idle
                )
                if not message_id:
                    continue

                if message_id in self.requested_input_messages:
                    continue

                self.log(
                    f"[INFO] Claude idle — requesting input for message {message_id}"
                )
                self.requested_input_messages.add(message_id)
                self.message_processor.mark_input_requested(message_id)

                try:
                    await self.vicoa_client_async._make_request(
                        "PATCH", f"/api/v1/messages/{message_id}/request-input"
                    )
                except Exception as patch_err:
                    err_str = str(patch_err)
                    if "already requires user input" in err_str:
                        pass  # benign race — message already marked
                    elif isinstance(
                        patch_err, (aiohttp.ClientError, asyncio.TimeoutError)
                    ):
                        # Transient network error — keep the deduplication entry so
                        # we don't re-fire the request-input call on reconnect.
                        self.log(
                            f"[WARNING] Network error requesting input for {message_id}: {patch_err}"
                        )
                    else:
                        # Definitive server error — roll back so we can retry.
                        self.log(
                            f"[WARNING] Failed to request input for {message_id}: {patch_err}"
                        )
                        self.requested_input_messages.discard(message_id)
                        self.message_processor.pending_input_message_id = None

            except Exception as e:
                self.log(f"[ERROR] Idle monitor error: {e}")

    # ------------------------------------------------------------------
    # Control command handling (unchanged from previous implementation)
    # ------------------------------------------------------------------

    def request_input_now(self, message_id: str) -> None:
        """No-op: SSE stream delivers messages immediately without explicit requests."""

    def cancel_pending_input_request(self) -> None:
        """No-op: there is no long-poll task to cancel."""

    def _handle_control_command(self, content: str) -> bool:
        """Handle JSON control commands from the web UI.

        Returns True if the content was a control command (consumed), False otherwise.
        """
        try:
            control = self._parse_control_json(content)
            if not control:
                return False

            setting = control.get("setting", "").strip()
            if not setting:
                return False

            # Handle interrupt
            if setting == "interrupt":
                return self._handle_interrupt_action()

            if setting == "ask_user_question":
                return self._handle_ask_user_question_action(
                    str(control.get("value") or "")
                )

            # Persist-only metadata/control messages from UI.
            # They should be stored by backend but never forwarded to Claude
            # or treated as toggle commands.
            if setting == "persist_only":
                return True

            # Handle toggle settings
            value = (control.get("value") or "").strip()
            if not value:
                self._send_feedback_message(f"Missing value for setting '{setting}'")
                return True

            # Slash-command settings (model + effort): Claude accepts inline
            # args like `/model claude-sonnet-4-6` or `/effort high`. PTY-type
            # the command directly + optimistically PATCH session_config.
            # JSONLMonitor's message.model on the next assistant reply
            # self-heals if Claude rejects the slug ("Model 'X' not found"
            # → no message.model with X arrives → PATCH walks back).
            #
            # Wait for Claude's confirmation echo before returning so the
            # next slash command (model + effort can arrive in one mobile
            # confirm) doesn't race the still-rendering input area.
            # ``_wait_for_pty_echo`` is bounded — on timeout the PATCH still
            # fires and JSONLMonitor handles the rejected case.
            #
            # Always send `agent` alongside the changed field so a row whose
            # session_config column was NULL gets a complete identity on
            # first PATCH. Mobile's SessionConfig.fromJson defaults missing
            # agent to "claude" — harmless here since it matches, but the
            # symmetric defense protects against future agent confusion.
            if setting == "model":
                buf_size_before = self._terminal_buffer_size()
                self.pty_manager.write_to_pty(f"/model {value}\r".encode("utf-8"))
                self._wait_for_pty_echo("Set model to", after_size=buf_size_before)
                if self.vicoa_client_sync:
                    try:
                        self.vicoa_client_sync.patch_agent_instance(
                            self.agent_instance_id,
                            session_config={"agent": "claude", "model": value},
                        )
                        self.log(
                            f"[DEBUG] PATCH session_config {{'model': '{value}'}} after /model"
                        )
                    except Exception as e:
                        self.log(f"[WARNING] Failed to PATCH session_config: {e}")
                return True
            if setting == "effort":
                buf_size_before = self._terminal_buffer_size()
                self.pty_manager.write_to_pty(f"/effort {value}\r".encode("utf-8"))
                self._wait_for_pty_echo(
                    "Set effort level to", after_size=buf_size_before
                )
                if self.vicoa_client_sync:
                    try:
                        self.vicoa_client_sync.patch_agent_instance(
                            self.agent_instance_id,
                            session_config={
                                "agent": "claude",
                                "thinking_effort": value,
                            },
                        )
                        self.log(
                            f"[DEBUG] PATCH session_config {{'thinking_effort': '{value}'}} after /effort"
                        )
                    except Exception as e:
                        self.log(f"[WARNING] Failed to PATCH session_config: {e}")
                return True

            # Delegate to toggle manager — this drives the PTY observe loop
            # and returns True only when Claude's status line confirms the
            # target mode is actually active.
            success = self.toggle_manager.handle_toggle_request(setting, value)

            # PATCH session_config ONLY after the toggle is confirmed.
            # set_toggle's observe loop returns False when Claude won't reach
            # the target (most notably: requesting bypassPermissions on a
            # session that wasn't started with --dangerously-skip-permissions
            # — the bypass slug isn't in Claude's actual cycle so the loop
            # exhausts its cap). PATCHing optimistically at parse time used
            # to make the row claim a mode the session couldn't actually run
            # as; the mobile gear sheet then displayed a lie. Wait for the
            # toggle_manager to confirm before persisting.
            if success and setting == "permission_mode" and self.vicoa_client_sync:
                target_slug = self.toggle_manager.normalize_value(setting, value)
                if target_slug:
                    try:
                        self.vicoa_client_sync.patch_agent_instance(
                            self.agent_instance_id,
                            session_config={"permission_mode": target_slug},
                        )
                        self.log(
                            f"[DEBUG] PATCH session_config {{'permission_mode': '{target_slug}'}} after UI-driven toggle"
                        )
                    except Exception as e:
                        self.log(f"[WARNING] Failed to PATCH session_config: {e}")

            # Only send feedback on failure
            # Success feedback will come from terminal detection when change is confirmed
            if not success:
                target_slug = self.toggle_manager.normalize_value(setting, value)
                display_value = (
                    self.toggle_manager.humanize_value(setting, target_slug)
                    if target_slug
                    else value
                )
                self._send_feedback_message(
                    f"Failed to set {setting.replace('_', ' ')} to {display_value}"
                )

            return True

        except json.JSONDecodeError:
            return False
        except Exception as e:
            self.log(f"[ERROR] Error handling control command: {e}")
            return False

    def _parse_control_json(self, content: str) -> Optional[dict]:
        """Parse JSON control command from text (can be embedded).

        Supports both formats for backwards compatibility:
        - {"type": "control", "setting": "X", "value": "Y"}
        - {"type": "control", "action": "interrupt"}
        """
        if not content:
            return None

        match = CONTROL_JSON_PATTERN.search(content)
        if not match:
            return None

        json_str = match.group(0)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict) or data.get("type") != "control":
            return None

        # Support both "setting" (new format) and "action" (old format)
        setting = data.get("setting") or data.get("action")
        if not setting:
            return None

        value = data.get("value")
        if value is not None:
            return {"setting": str(setting), "value": str(value)}
        return {"setting": str(setting)}

    def _handle_ask_user_question_action(self, value: str) -> bool:
        """Handle AskUserQuestion submit/cancel control commands."""
        command = value.strip()
        if not command:
            self._send_feedback_message("Missing AskUserQuestion command")
            return True

        if command == "cancel":
            try:
                self.pty_manager.write_to_pty(b"\x1b")
            except Exception as e:
                self.log(f"[ERROR] Failed to cancel AskUserQuestion: {e}")
                self._send_feedback_message("Failed to cancel AskUserQuestion")
            return True

        if not command.startswith("submit:"):
            self._send_feedback_message("Invalid AskUserQuestion command")
            return True

        encoded = command[len("submit:") :].strip()
        payload = self._decode_ask_user_question_payload(encoded)
        if not payload:
            self._send_feedback_message("Invalid AskUserQuestion answers payload")
            return True

        answers = payload.get("answers")
        if not isinstance(answers, list):
            self._send_feedback_message("AskUserQuestion payload missing answers")
            return True

        try:
            self.message_processor.suppress_cli_user_echo_until = time.time() + 10.0
            self.log(f"[DEBUG] Submitting AskUserQuestion answers count={len(answers)}")
            self._submit_ask_user_question_answers(answers)
            # Clear suppress window so a subsequent AskUserQuestion call is detected.
            if self.on_ask_user_question_submitted:
                self.on_ask_user_question_submitted()
        except Exception as e:
            self.log(f"[ERROR] Failed to submit AskUserQuestion answers: {e}")
            self._send_feedback_message("Failed to submit AskUserQuestion answers")

        return True

    def _decode_ask_user_question_payload(
        self, encoded: str
    ) -> Optional[dict[str, Any]]:
        if not encoded:
            return None
        try:
            padding = "=" * (-len(encoded) % 4)
            raw = base64.urlsafe_b64decode(encoded + padding)
            payload = json.loads(raw.decode("utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            return None
        return None

    def _submit_ask_user_question_answers(self, answers: list[Any]) -> None:
        """Send key sequence to terminal to answer AskUserQuestion and submit."""
        auto_advanced_from_prev = False
        for index, answer in enumerate(answers):
            if index > 0 and not auto_advanced_from_prev:
                self.log(
                    f"[DEBUG] AskUserQuestion move to next tab index={index}: sending Tab"
                )
                self._write_pty_key(b"\t")
                time.sleep(0.5)
            elif index > 0 and auto_advanced_from_prev:
                self.log(
                    f"[DEBUG] AskUserQuestion next tab already active after text confirm index={index}"
                )
                # Give the UI time to finish the tab transition before pressing keys
                # on the new tab (right-arrow transition takes ~100-200ms to render).
                time.sleep(0.2)

            auto_advanced_from_prev = False

            if isinstance(answer, dict):
                mode = str(answer.get("mode") or "option").strip()
                if mode == "text":
                    option_count_raw = answer.get("option_count")
                    option_count = self._parse_int_value(option_count_raw, default=4)
                    self.log(
                        f"[DEBUG] AskUserQuestion answer[{index}] mode=text option_count={option_count}"
                    )
                    self._answer_question_with_text(
                        str(answer.get("text") or ""),
                        option_count=option_count,
                    )
                    # In AskUserQuestion, Enter on text answer moves to the next tab.
                    auto_advanced_from_prev = True
                else:
                    option_index = answer.get("option_index")
                    question_multi_select = bool(answer.get("question_multi_select"))
                    option_count_raw = answer.get("option_count")
                    option_count = self._parse_int_value(option_count_raw, default=4)
                    parsed_option_index = self._parse_int_value(option_index, default=0)
                    parsed_option_indexes: list[int] = []
                    raw_indexes = answer.get("option_indexes")
                    if isinstance(raw_indexes, list):
                        for raw_idx in raw_indexes:
                            parsed = self._parse_int_value(raw_idx, default=-1)
                            if parsed < 0:
                                continue
                            parsed_option_indexes.append(parsed)
                    # Fall back to option_index only when option_indexes was absent from
                    # the payload (None), not when it was explicitly sent as [].
                    # An explicit [] means the user skipped this question intentionally.
                    if (
                        not question_multi_select
                        and not parsed_option_indexes
                        and raw_indexes is None
                        and parsed_option_index >= 0
                    ):
                        parsed_option_indexes = [parsed_option_index]
                    # de-duplicate while preserving order
                    deduped_indexes: list[int] = []
                    for idx_value in parsed_option_indexes:
                        if idx_value not in deduped_indexes:
                            deduped_indexes.append(idx_value)
                    if not deduped_indexes:
                        time.sleep(0.5)
                        # User skipped this question (no options selected).
                        # Don't send any key — right arrow on an untouched multi-select tab
                        # navigates within the option list (leaving option 1 implicitly active)
                        # rather than advancing to the next tab. The Tab key sent between
                        # iterations (or the final submit-tab step) handles advancement cleanly.
                        self.log(
                            f"[DEBUG] AskUserQuestion answer[{index}]: no options selected, skipping question"
                        )
                        auto_advanced_from_prev = False
                    elif question_multi_select:
                        # Select each requested option then submit this question to advance.
                        for option_idx in deduped_indexes:
                            self._answer_question_with_option(option_idx, True)
                        self._submit_multi_select_question()
                        # We explicitly moved to the next tab.
                        auto_advanced_from_prev = True
                        self.log(
                            f"[DEBUG] AskUserQuestion multi-select advanced to next tab index={index}"
                        )
                    else:
                        option_number = max(1, min(parsed_option_index + 1, 6))
                        self.log(
                            f"[DEBUG] AskUserQuestion answer[{index}]: sending key '{option_number}' (single-select option {option_number})"
                        )
                        self._answer_question_with_option(parsed_option_index, False)
                        # Single-select auto-advances after numeric key.
                        auto_advanced_from_prev = True
            else:
                self.log(
                    f"[DEBUG] AskUserQuestion answer[{index}]: no options, selecting first option"
                )
                self._answer_question_with_option(0, False)
                auto_advanced_from_prev = True

        # Move to Submit tab and confirm submission.
        if auto_advanced_from_prev:
            self.log(
                "[DEBUG] AskUserQuestion submit tab already active after final text answer"
            )
        else:
            self.log("[DEBUG] AskUserQuestion move to submit tab: sending Tab")
            self._write_pty_key(b"\t")
        time.sleep(0.5)
        self.log("[DEBUG] AskUserQuestion confirm submit: sending Enter")
        self._write_pty_key(b"\r")

    def _parse_int_value(self, value: object, default: int) -> int:
        """Parse loose JSON-like payload values into ints for terminal actions."""
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return default
        return default

    def _answer_question_with_option(
        self, option_index: int, multi_select: bool
    ) -> None:
        option_number = max(1, min(option_index + 1, 6))
        self.log(
            f"[DEBUG] AskUserQuestion answer[{option_index}]: sending key '{option_number}' (option {option_number})"
        )
        self._write_pty_key(str(option_number).encode("ascii"))
        if multi_select:
            self.log(
                f"[DEBUG] AskUserQuestion answer[{option_index}]: sending Space to toggle option {option_number}"
            )

            # Number key only moves the cursor (❯) to the option; Space toggles the checkbox.
            self._write_pty_key(b" ")

    def _submit_multi_select_question(self) -> None:
        # Right arrow advances from the current question tab to the next tab (or Submit).
        self._write_pty_key(b"\x1b[C")

    def _answer_question_with_text(self, text: str, option_count: int) -> None:
        option_count = max(0, min(option_count, 20))
        for _ in range(option_count):
            self._write_pty_key(b"\x1b[B")
        time.sleep(0.08)
        if text:
            self._write_pty_key(text.encode("utf-8"), delay=0.02)
        self._write_pty_key(b"\r")
        # Give the UI a beat to register and auto-advance.
        time.sleep(0.08)

    def _write_pty_key(self, data: bytes, delay: float = 0.08) -> None:
        self.pty_manager.write_to_pty(data)
        time.sleep(delay)

    def _terminal_buffer_size(self) -> int:
        """Current size of the shared terminal buffer, or 0 if unavailable.

        Used as the "from here" cursor for ``_wait_for_pty_echo`` so a
        stale echo from a previous toggle doesn't satisfy the next wait.
        """
        buf = getattr(self.session_state, "terminal_buffer", None)
        if buf is None:
            return 0
        try:
            return buf.size()
        except Exception:
            return 0

    def _wait_for_pty_echo(
        self,
        pattern: str,
        *,
        after_size: int,
        timeout: Optional[float] = None,
    ) -> bool:
        """Poll ``terminal_buffer`` for ``pattern`` arriving after ``after_size``.

        Replaces the fixed ``time.sleep(0.5)`` that used to follow each
        slash-command write. The TUI's input-echo → command-dispatch →
        confirmation render cycle is variable (~150 ms on a snappy
        session, ~700 ms+ when Claude is mid-turn). A blind sleep at the
        median lets the next ``/command`` race into the input area
        mid-render and get eaten — the bug the user observed when the
        mobile gear pill sent ``model`` and ``effort`` in one confirm.

        Polling with the buffer-size watermark guarantees we only return
        on a *fresh* echo. ``timeout`` defaults to
        ``SLASH_COMMAND_ECHO_TIMEOUT_S``; on expiry we return False so
        the caller logs + proceeds with the PATCH. Reading
        ``TerminalBuffer`` from this thread is safe — the main loop's
        appends are GIL-atomic and we only ever read.
        """
        if timeout is None:
            timeout = self.SLASH_COMMAND_ECHO_TIMEOUT_S
        buf = getattr(self.session_state, "terminal_buffer", None)
        if buf is None:
            time.sleep(min(0.5, timeout))
            return False

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                size_now = buf.size()
            except Exception:
                size_now = after_size
            new_bytes = size_now - after_size
            if new_bytes > 0:
                # +200 grace for partial overlap when the pattern straddles
                # the watermark boundary (cosmetic; not load-bearing).
                tail = buf.get_last_n_chars(new_bytes + 200)
                if pattern in tail:
                    return True
            time.sleep(self.SLASH_COMMAND_ECHO_POLL_INTERVAL_S)

        self.log(
            f"[WARNING] No {pattern!r} echo within "
            f"{timeout:.1f}s — proceeding optimistically"
        )
        return False

    def _handle_interrupt_action(self) -> bool:
        """Handle interrupt action from web UI.

        Clears queued messages, sends Escape key to Claude Code,
        and sends confirmation feedback to user.

        Returns: True (command was handled)
        """
        # Clear all queued messages
        if len(self.message_queue) > 0:
            self.message_queue.clear()

        # Always send the escape key - if Claude is idle it won't hurt,
        # if Claude is busy it will interrupt. The user clicked "Stop" so
        # we should respect that regardless of our detection state.
        try:
            self.pty_manager.write_to_pty(b"\x1b")
        except Exception as e:
            self.log(f"[ERROR] Failed to send interrupt signal: {e}")
            self._send_feedback_message("Failed to interrupt Claude")
            return True

        # Cancel any pending input request since we're interrupting
        self.cancel_pending_input_request()

        # Clear the pending input message ID to allow new input requests
        self.message_processor.pending_input_message_id = None

        # Clear last_was_tool_use to allow input requests after interrupt
        self.message_processor.last_was_tool_use = False

        # Send confirmation feedback to web UI (this will set last_message_id and last_message_time)
        self._send_feedback_message("Interrupted · What should Claude do instead?")

        # Important: The feedback message above will get a message_id in response.
        # We need to immediately check for any follow-up user messages that might
        # have been queued while we were processing the interrupt.
        # The response from _send_feedback_message already processes queued messages,
        # so we don't need to do anything extra here.

        return True

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
                agent_type=self.agent_name,
                agent_instance_id=self.agent_instance_id,
                requires_user_input=False,
            )

            if response and hasattr(response, "message_id"):
                self.message_processor.last_message_id = response.message_id
                self.message_processor.last_message_time = time.time()

            # Queued messages delivered via SSE — no need to process inline here
        except Exception as e:
            self.log(f"[ERROR] Failed to send feedback message: {e}")
