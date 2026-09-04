"""Base class for ACP (Agent Client Protocol) integrations.

This provides a generic framework for integrating any ACP-compatible agent
with Vicoa using the JSON-RPC protocol over stdin/stdout.

Use this for agents that:
- Support ACP protocol (https://agentclientprotocol.com/)
- Don't have native plugin systems
- Need external wrapper for Vicoa integration

For agents with plugin systems (like OpenCode), prefer native plugins instead.
"""

import base64
import logging
import difflib
import json
import os
import re
import signal
import sys
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from pathlib import Path
from typing import Any, Dict, Optional

from integrations.headless.control_command import is_control_envelope
from integrations.headless.acp_client import (
    ACPClient,
    ACPError,
    ACPMethodNotFound,
    ACPResponse,
)
from integrations.headless.thinking import build_thinking_metadata
from integrations.headless.session_lifecycle import (
    WRAPPER_STOP_STATUSES,
    instance_update_requests_stop,
)
from integrations.utils.heartbeat import SessionHeartbeat
from vicoa.attachments import (
    AttachmentRef,
    attachment_note,
    attachments_dir,
    extract_attachment_refs,
    is_image_mime,
    save_attachment,
    unavailable_note,
)
from vicoa.sdk.client import VicoaClient
from vicoa.sdk.exceptions import AuthenticationError
from vicoa.session_ws_client import SessionMessagesWsClient
from vicoa.utils import derive_ws_url


logger = logging.getLogger(__name__)
FILE_DUMP_BLOCK_PATTERN = re.compile(
    r"<path>.*?</path>\s*<type>\s*file\s*</type>\s*<content>.*?</content>",
    re.IGNORECASE | re.DOTALL,
)
CONTROL_JSON_PATTERN = re.compile(r'\{[^}]*"type"\s*:\s*"control"[^}]*\}')


class ACPWrapperConfig(ABC):
    """Base configuration for ACP wrappers.

    Subclasses should define agent-specific settings.
    """

    # Vicoa integration (required)
    api_key: str
    base_url: str
    agent_instance_id: str

    # Agent settings (required)
    project_path: str
    agent_type: str  # e.g., "opencode", "cursor", "windsurf"
    agent_command: str  # e.g., "opencode", "cursor"

    # Optional
    name: str
    # Reattaching to an existing Vicoa instance row (skip registration). This
    # says nothing about the *agent's* conversation — see acp_session_id for
    # that. The two were conflated behind one --resume flag, which meant
    # "resuming" reattached the row and silently handed the agent a blank
    # conversation while the UI still showed the old transcript.
    is_resuming: bool
    initial_prompt: Optional[str]

    # Optional tuning / spec capabilities (subclasses may override; class-level
    # defaults keep older configs that don't call super().__init__ working).
    initialize_timeout_seconds: float = 60.0
    # The agent's own prior session id, replayed via ``session/load`` so the
    # conversation actually continues. None means start a fresh agent session
    # even when ``is_resuming`` is True (e.g. the agent can't reload).
    acp_session_id: Optional[str] = None
    # Requested ACP session mode at spawn (validated against the agent's
    # advertised availableModes; silently skipped when unsupported).
    permission_mode: Optional[str] = None
    # Preferred authMethods id for the authenticate-on-auth-required retry.
    auth_method_id: Optional[str] = None
    # Catalog id persisted in session_config PATCHes ("cursor", "gemini", …).
    # Falls back to agent_type.lower() when unset.
    catalog_agent_id: Optional[str] = None

    @abstractmethod
    def get_acp_command(self) -> list[str]:
        """Return the command to start ACP mode.

        Example: ["opencode", "acp"]
        """
        pass

    @abstractmethod
    def get_acp_env(self) -> dict[str, str]:
        """Return environment variables for ACP process.

        Example: {"ANTHROPIC_API_KEY": "sk-ant-..."}
        """
        pass


class ACPWrapperBase(ABC):
    """Base class for ACP agent wrappers.

    This provides common functionality for integrating ACP-compatible agents
    with Vicoa, including:
    - ACP client lifecycle management
    - Vicoa backend communication
    - Event forwarding
    - Message queue handling
    - Session management

    Subclasses must implement:
    - create_session(): How to create a coding session
    - send_prompt(): How to send user messages (default implementation provided)

    Subclasses may override:
    - handle_notification(): Agent-specific notification handling
    - _prompt_timeout_seconds: Timeout for session/prompt requests
    - _prompt_cancel_grace_period_seconds: Grace period after cancellation
    - _hard_interrupt_fallback_delay_seconds: Delay before SIGINT fallback
    - _select_default_permission_option(): Which option to default to
    - _parse_permission_reply(): How to parse user permission responses
    """

    _permission_wait_poll_interval_seconds: float = 1.0
    _permission_wait_timeout_minutes: int = 15
    _prompt_timeout_seconds: float = 3600.0
    _prompt_cancel_grace_period_seconds: float = 10.0
    _hard_interrupt_fallback_delay_seconds: float = 0.0
    _permission_cancelled_option_id: str = "__vicoa_cancelled__"

    def __init__(self, config: ACPWrapperConfig):
        """Initialize ACP wrapper.

        Args:
            config: Wrapper configuration
        """
        self.config = config
        self.running = True

        # Setup logging
        self.debug_log_file: Optional[Any] = None
        self._init_logging()

        # Initialize Vicoa client
        self.vicoa_client: Optional[VicoaClient] = None
        self._init_vicoa_client()

        # ACP client (will be started in run())
        self.acp: Optional[ACPClient] = None

        # Session heartbeat (started in _setup once the instance id is final)
        self._heartbeat: Optional[SessionHeartbeat] = None

        # Prompt concurrency state
        self._prompt_state_lock = threading.Lock()
        self._prompt_in_flight = False
        self._queued_prompts: list[tuple[str, tuple[AttachmentRef, ...]]] = []
        self._prompt_cancel_event = threading.Event()
        self._interrupt_active = False
        self._permission_request_active = False

        # Session state
        # False until _setup() finishes. Lets run()'s fatal-error handler tell a
        # startup failure (agent never came up — most often the agent CLI isn't
        # logged in on this machine) apart from a mid-session crash, so it can
        # post the reason to the session instead of dying into a bare FAILED row
        # that the UI can only describe as "not accepting input".
        self._startup_complete = False
        # Set when the session is closed from another client. Guards against a
        # racing in-flight turn re-opening the row after we were told to stop.
        self._stopping = False
        # True only while ``session/load`` streams the prior conversation back
        # at us; see _handle_session_update for why that must not be forwarded.
        self._replaying_session = False
        self.session_id: Optional[str] = None
        self.last_message_id: Optional[str] = None
        # ACP v1 handshake state (filled by _initialize_acp_session).
        self.agent_capabilities: Dict[str, Any] = {}
        self.auth_methods: list[Dict[str, Any]] = []
        self.negotiated_protocol_version: Optional[Any] = None
        # ACP session state (filled by create_session / session updates).
        self.available_modes: list[Dict[str, Any]] = []
        self.current_mode_id: Optional[str] = None
        self.available_models: list[Dict[str, Any]] = []
        self.current_model_id: Optional[str] = None
        self.session_config_options: list[Dict[str, Any]] = []
        self.available_commands: list[Dict[str, Any]] = []
        self._awaiting_input_requested_for_message_id: Optional[str] = None
        self._awaiting_after_next_agent_output: bool = False
        self._suspend_vicoa_polling: bool = False

        # Message queue for user input from Vicoa. The third slot carries the
        # originating message id (when known) so the drain loop can mark the
        # row consumed — see ``_mark_message_consumed``.
        self.message_queue: list[
            tuple[str, tuple[AttachmentRef, ...], Optional[str]]
        ] = []
        # Ids of queued user messages the user cancelled from the UI before the
        # agent picked them up. The cancel lands as a ``message-update`` WS event
        # AFTER the row was already queued here, so it can only be honored at
        # drain time — ``_drain_and_dispatch_queue`` drops any id in this set.
        # Mirrors claude_code's ``_cancelled_message_ids`` (codex_native has the
        # same set); without it a cancel only updates the DB/UI and the agent
        # still runs the message. Every id added here is removed at the next
        # drain, so it can't grow unbounded (a cancel is only broadcast while the
        # row is still queued, i.e. still sitting in ``message_queue``).
        self._cancelled_message_ids: set[str] = set()
        # Whether the agent advertised ACP image prompt support at initialize;
        # when false, attachments degrade to local-file path notes.
        self._supports_image_prompts: bool = False

        # Session-scoped /ws subscriber. Replaces the legacy SSE listener —
        # WS handles the catch-up handshake natively (no separate
        # ``get_pending_messages`` drain) and exposes ``wait_until_ready``
        # so the initial prompt can be POSTed only after the subscription
        # is registered server-side, eliminating the catch-up race and the
        # self-echo dedup the SSE path needed (websocket-migration §4).
        self._ws_client: Optional[SessionMessagesWsClient] = None
        self._ws_thread: Optional[threading.Thread] = None

        # Buffer streamed ACP chunks to avoid fragmented UI messages.
        # Set by an interrupt: agents keep streaming for a beat after
        # ``session/cancel`` lands, and forwarding that tail re-opened the row
        # as ACTIVE (every non-requires_user_input POST does) *after* the
        # interrupt had settled it on AWAITING_INPUT — leaving the session
        # showing "active" with nothing running. Cleared by
        # ``_prepare_for_new_prompt``.
        self._drop_stream_output_until_next_prompt: bool = False
        # Per-turn "did the agent actually do anything?" tracking. A turn that
        # ends with a normal stopReason (no JSON-RPC error) yet streamed zero
        # assistant text, ran zero tools, and raised no session/error is almost
        # always a swallowed provider failure: some ACP agents report a failed
        # turn as ``stopReason: end_turn`` with no output and no error channel
        # (observed with Kimi — an unsupported ``thinking`` option for the
        # chosen model 400s upstream, and kimi-code surfaces nothing over ACP),
        # so the session just goes quiet and the user thinks the agent ignored
        # them. We flag real activity here and, when a turn produced none,
        # ``_report_empty_turn`` tells the user instead of swallowing it too.
        self._turn_produced_output: bool = False
        # Agent stderr captured during the current turn (bounded). Included in
        # the empty-turn notice when present — failure modes that DO print the
        # real cause to stderr (e.g. auth errors) then reach the user verbatim.
        self._turn_stderr: deque[str] = deque(maxlen=20)
        self._assistant_chunk_buffer: str = ""
        # Model reasoning streamed on the ACP ``agent_thought_chunk`` channel.
        # Accumulated separately from narration and flushed as its own collapsed
        # "thinking" card (metadata-tagged) ahead of the answer — see
        # ``_flush_thought_buffer``.
        self._thought_chunk_buffer: str = ""
        self._assistant_chunk_first_update_at: float = 0.0
        self._assistant_chunk_last_update_at: float = 0.0
        self._assistant_chunk_flush_after_seconds: float = 1.0
        self._assistant_chunk_force_flush_after_seconds: float = 4.0
        # By default, hide tool intermediate output and only show final assistant responses.
        self._show_tool_updates: bool = str(
            os.environ.get("VICOA_ACP_SHOW_TOOL_UPDATES", "")
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._last_tool_change_signature: Optional[str] = None
        self._tool_output_max_lines: int = int(
            os.environ.get("VICOA_ACP_TOOL_OUTPUT_MAX_LINES", "80")
        )
        self._tool_output_max_chars: int = int(
            os.environ.get("VICOA_ACP_TOOL_OUTPUT_MAX_CHARS", "4000")
        )
        self._tool_output_preview_lines: int = int(
            os.environ.get("VICOA_ACP_TOOL_OUTPUT_PREVIEW_LINES", "24")
        )
        self._tool_output_preview_chars: int = int(
            os.environ.get("VICOA_ACP_TOOL_OUTPUT_PREVIEW_CHARS", "1400")
        )

    def _install_signal_handlers(self) -> None:
        """Make SIGTERM unwind through ``run()``'s try/finally like SIGINT.

        ``vicoa stop sessions`` sends SIGTERM. The default SIGTERM action
        terminates the process immediately — the ``finally`` block below
        never runs, so ``_cleanup()`` never executes and the backend
        instance is left stuck in a non-terminal status (the bug: status
        updates worked for headless claude but not codex/opencode).

        Converting SIGTERM into ``KeyboardInterrupt`` — the exact exception
        SIGINT already raises — routes it into the existing
        ``except KeyboardInterrupt`` arm, which sets ``final_status=KILLED``
        and runs ``_cleanup()``. The event loop's ``except Exception`` does
        NOT swallow it (KeyboardInterrupt is a BaseException), so it
        propagates correctly.
        """

        def _raise_keyboard_interrupt(signum: int, frame: object) -> None:
            raise KeyboardInterrupt()

        try:
            signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
        except (ValueError, OSError):
            # signal.signal only works in the main thread (ValueError
            # otherwise). The wrapper normally runs as its process's main
            # thread, so this is best-effort defensive coding.
            self.log("[WARNING] Could not install SIGTERM handler")

    def run(self) -> int:
        """Main entry point - run the wrapper.

        Returns:
            Exit code (0 for success, 1 for error)
        """
        self._install_signal_handlers()
        final_status = "COMPLETED"
        try:
            self._setup()
            self._run_event_loop()
            return 0
        except AuthenticationError:
            # Vicoa credential died mid-session (revoked key / deleted account).
            # A headless agent with a dead link is an invisible orphan — end it.
            # _cleanup() does the best-effort terminal status + stops the WS.
            self.log("[INFO] Vicoa credential expired; ending headless session")
            final_status = "KILLED"
            return 1
        except KeyboardInterrupt:
            self.log("[INFO] Interrupted (SIGINT/SIGTERM)")
            final_status = "KILLED"
            return 0
        except Exception as e:
            self.log(f"[ERROR] Fatal error: {e}")
            import traceback

            self.log(traceback.format_exc())
            # A crash before startup finished means the agent never came up (a
            # bad binary, or the agent answering session/new with -32000
            # "Authentication required" — which can mean it isn't logged in on
            # this machine, OR that it IS logged in but the daemon's reduced
            # spawn env hid its creds). Post the reason so the user sees
            # something actionable instead of a silent FAILED session that the
            # UI can only render as "not accepting input".
            if not self._startup_complete:
                self._report_startup_failure(e)
            final_status = "FAILED"
            return 1
        finally:
            self._cleanup(final_status=final_status)

    def _report_startup_failure(self, error: Exception) -> None:
        """Post a user-visible reason when the agent never finished starting.

        Best-effort and must never raise: it runs from run()'s fatal-error
        handler, which still has to reach ``_cleanup`` to write the terminal
        status. A failure to POST here just means the row stays FAILED with no
        note — no worse than before.
        """
        if not (self.vicoa_client and self.config.agent_instance_id):
            return
        try:
            self._send_feedback_message(self._startup_failure_message(error))
        except Exception as exc:
            self.log(f"[WARNING] Could not report startup failure: {exc}")

    def _startup_failure_message(self, error: Exception) -> str:
        """Human-readable explanation for a failed spawn.

        The auth-required case is worded conditionally on purpose. An agent that
        works when you run its CLI directly can still answer ``session/new`` with
        -32000 when the *daemon* spawns it, because the daemon's environment
        (launched by launchd / the desktop app, not a login shell) is reduced and
        the agent can't find whatever its auth needs. Telling such a user to "log
        in again" is a wrong goose chase, so we name both possibilities.
        Everything else falls back to the raw error, still far better than a
        status-only FAILED row.
        """
        agent = self.config.agent_type
        if self._is_auth_required_error(error):
            return (
                f"{agent} couldn't start: it needs authentication. If you're "
                f"not signed in, log in with the {agent} on this machine and "
                f"retry. If it works when you run it directly, please let us "
                f"know the issue at hi@vicoa.ai."
            )
        return (
            f"{agent} couldn't start: {error}. "
            f"If this looks like a Vicoa bug, please report it to hi@vicoa.ai."
        )

    def build_session_config(self) -> Optional[dict]:
        """Spawn-time user-visible config for the chat-header pill.

        Default is None — wrappers that have meaningful values override this
        to return a dict (omitting None-valued keys). Returning None means
        the activate-existing branch on the backend preserves whatever value
        was pre-staged on the row.
        """
        return None

    def _setup(self) -> None:
        """Setup before main loop."""
        self.log(f"[INFO] Setting up {self.config.agent_type} wrapper...")

        # Register with Vicoa if starting new session
        if not self.config.is_resuming and self.vicoa_client:
            try:
                from vicoa.utils import get_project_path

                registration = self.vicoa_client.register_agent_instance(
                    agent_type=self.config.agent_type,
                    transport="local",
                    agent_instance_id=self.config.agent_instance_id,
                    project=get_project_path(),
                    home_dir=str(Path.home()),
                    session_config=self.build_session_config(),
                    source="app",
                )

                self.config.agent_instance_id = registration.agent_instance_id
                self.log(
                    f"[INFO] Registered agent instance: {self.config.agent_instance_id}"
                )

            except Exception as e:
                # A swallowed failure here used to leave the process running
                # as an invisible zombie: the daemon's spawn RPC had already
                # returned success with this instance id, so the caller polls
                # for a row that will now never exist, times out, and shows
                # "instance didn't start" — while this process keeps running
                # unregistered, burning the user's agent usage with no way to
                # see or stop it. Re-raise so `run()`'s outer handler exits
                # the process immediately instead (matches codex_native.py's
                # already-fatal handling of the same failure).
                self.log(f"[ERROR] Failed to register with Vicoa: {e}")
                raise
        elif self.vicoa_client:
            # Resuming skips registration (the row exists; re-registering it
            # returns 409), but the row still has to be reopened — otherwise an
            # archived session stays COMPLETED and nothing visibly happens when
            # the user hits Resume. AWAITING_INPUT rather than ACTIVE: the agent
            # is idle waiting for the user, and ACTIVE renders a working spinner
            # for an agent that isn't doing anything.
            try:
                self.vicoa_client.update_agent_instance_status(
                    self.config.agent_instance_id, "AWAITING_INPUT"
                )
                self.log(
                    f"[INFO] Reopened agent instance: {self.config.agent_instance_id}"
                )
            except Exception as e:
                self.log(f"[WARNING] Failed to reopen instance on resume: {e}")

        # Start the session heartbeat once the instance id is settled
        # (registration can hand back a different one). Without this an idle
        # headless session looks dead to the liveness indicator — see
        # integrations/utils/heartbeat.py.
        self._start_heartbeat()

        # Start ACP client
        self._start_acp_client()

        # Initialize ACP session
        self._initialize_acp_session()

        # Restore the prior conversation, or start a new one.
        self._establish_session()

        # Bring up the WS subscriber BEFORE POSTing the initial prompt so the
        # broadcast loops back to us via the live ``new-message`` channel and
        # not the (already-consumed) catch-up SELECT. Mirrors
        # ``codex_native.run()`` — see ``claude_code.initialize()`` for the
        # rationale.
        if self.vicoa_client and self.config.agent_instance_id:
            self._start_ws_client()

        # POST initial prompt as a user message and let the WS echo deliver it
        # back into ``message_queue`` — the single path also used for every
        # subsequent turn. There is NO direct ``message_queue.append``; the
        # codex_native pattern relies on the live broadcast (after
        # ``wait_until_ready`` confirms catch-up completed, so the
        # subscription is registered), with the WS client's ``CatchUpBuffer``
        # deduping by message id so a later catch-up can't double-deliver.
        initial_prompt: Optional[str] = getattr(self.config, "initial_prompt", None)
        if initial_prompt and initial_prompt.strip() and self.config.agent_instance_id:
            if self._ws_client is not None:
                ready = self._ws_client.wait_until_ready(10.0)
                if not ready:
                    self.log(
                        "[WARNING] WS catch-up not ready after 10s; "
                        "POSTing initial prompt anyway"
                    )
            if self.vicoa_client:
                try:
                    # ``mark_as_read=False`` is load-bearing — see the long
                    # comment on the same POST in ``claude_code.initialize``.
                    # The default (True) points the server's
                    # ``last_read_message_id`` at this row, and the catch-up
                    # cursor fallback then excludes the prompt from its own
                    # recovery, hanging the session forever when the
                    # ``ready`` wait above timed out.
                    self.vicoa_client.send_user_message(
                        agent_instance_id=self.config.agent_instance_id,
                        content=initial_prompt,
                        mark_as_read=False,
                    )
                except Exception as e:
                    self.log(
                        f"[WARNING] Failed to store initial prompt as user message: {e}"
                    )

        # The agent is up and the session is live; anything that fails after
        # this is a mid-session crash, not a spawn failure — see run().
        self._startup_complete = True

    def _start_heartbeat(self) -> None:
        """Begin periodic session heartbeats (best effort)."""
        if not self.vicoa_client or not self.config.agent_instance_id:
            return
        try:
            self._heartbeat = SessionHeartbeat(
                agent_instance_id=self.config.agent_instance_id,
                base_url=self.config.base_url,
                http_session=self.vicoa_client.session,
                log_func=self.log,
            )
            self._heartbeat.start()
        except Exception as exc:
            self.log(f"[WARNING] Failed to start session heartbeat: {exc}")

    def _start_acp_client(self) -> None:
        """Start ACP client and connect to agent."""
        command = self.config.get_acp_command()
        env = self.config.get_acp_env()

        self.log(f"[ACP] Starting agent: {' '.join(command)}")
        self.log(f"[ACP] Project path: {self.config.project_path}")

        self.acp = ACPClient(
            command=command,
            cwd=self.config.project_path,
            env=env,
            on_notification=self._handle_acp_notification,
            on_request=self._handle_acp_request,
            on_error=self._handle_acp_error,
            log_func=self.log,
        )

        self.acp.on_late_response = self._handle_late_acp_response
        self.acp.start()
        self.log("[ACP] Agent process started")

    def _initialize_acp_session(self) -> None:
        """Initialize the ACP protocol session (ACP v1 handshake).

        Sends a spec-compliant ``initialize`` first — integer
        ``protocolVersion: 1``, ``clientCapabilities`` with explicit
        fs/terminal flags (all false: agents then use their own internal
        tools and we only see ``tool_call`` updates), and ``clientInfo`` —
        and retains the agent's advertised ``agentCapabilities`` and
        ``authMethods`` for later gating (session/load support, the
        authenticate-on-auth-required retry in :py:meth:`create_session`).

        Legacy payload shapes are retried for old agent builds that predate
        the v1 schema (older OpenCode accepted ``capabilities.supports`` and
        date-style versions).
        """
        acp = self.acp
        if not acp:
            raise ACPError("ACP client not started")

        self.log("[ACP] Initializing protocol session")
        init_timeout = float(
            getattr(self.config, "initialize_timeout_seconds", 60.0) or 60.0
        )

        init_payloads: list[Dict[str, Any]] = [
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False},
                    "terminal": False,
                },
                "clientInfo": {"name": "vicoa", "title": "Vicoa", "version": "1.0.0"},
            },
            {
                # Legacy pre-v1 shape (older OpenCode builds).
                "protocolVersion": 1,
                "capabilities": {"supports": ["streaming", "tools", "permissions"]},
                "clientInfo": {"name": "vicoa", "version": "1.0.0"},
            },
            {
                # Backward-compatible fallback for agents that accept date-style versions.
                "protocolVersion": "2024-11-01",
                "capabilities": {"supports": ["streaming", "tools", "permissions"]},
                "clientInfo": {"name": "vicoa", "version": "1.0.0"},
            },
        ]

        last_error: ACPError | None = None
        for payload in init_payloads:
            try:
                response = acp.send_request("initialize", payload, timeout=init_timeout)
                response.raise_for_error()
                result = response.result or {}
                self.negotiated_protocol_version = result.get("protocolVersion")
                self.agent_capabilities = result.get("agentCapabilities") or {}
                self.auth_methods = result.get("authMethods") or []
                self._supports_image_prompts = self._read_image_capability(
                    self.agent_capabilities
                )
                if self.negotiated_protocol_version not in (
                    None,
                    payload["protocolVersion"],
                ):
                    # Spec says close-and-inform on unsupported version; in
                    # practice agents downgrade gracefully, so log and keep
                    # going best-effort rather than killing the session.
                    self.log(
                        "[ACP] Agent negotiated protocolVersion="
                        f"{self.negotiated_protocol_version!r}; continuing best-effort"
                    )
                self.log(
                    "[ACP] Protocol initialized successfully "
                    f"(image prompts: {self._supports_image_prompts})"
                )
                return
            except ACPError as e:
                last_error = e
                self.log(
                    f"[WARNING] ACP initialize attempt failed (protocolVersion={payload['protocolVersion']}): {e}"
                )

        self.log(f"[ERROR] Failed to initialize ACP: {last_error}")
        raise last_error if last_error else ACPError("Failed to initialize ACP")

    @staticmethod
    def _read_image_capability(agent_capabilities: Any) -> bool:
        """Whether the agent advertises image prompt support
        (``agentCapabilities.promptCapabilities.image`` per the ACP spec)."""
        if not isinstance(agent_capabilities, dict):
            return False
        prompt_caps = agent_capabilities.get("promptCapabilities")
        return isinstance(prompt_caps, dict) and prompt_caps.get("image") is True

    @staticmethod
    def _read_load_session_capability(agent_capabilities: Any) -> bool:
        """Whether the agent can reload a prior session.

        Resume is gated on this rather than attempted blindly: an agent that
        can't reload would answer ``session/load`` with an error, and falling
        back to ``session/new`` there would hand the user a blank agent while
        the UI still shows the old transcript. Silent context loss is worse
        than no resume at all.

        Accepts both shapes. The flat ``loadSession`` bool is the original
        spec; newer agents (OpenCode 1.18 advertises both) also expose a nested
        ``sessionCapabilities`` block. Reading only the flat flag would make
        resume switch itself off silently the day an agent drops the legacy
        key — a failure that looks like "resume just stopped working".
        """
        if not isinstance(agent_capabilities, dict):
            return False
        if agent_capabilities.get("loadSession") is True:
            return True
        session_caps = agent_capabilities.get("sessionCapabilities")
        # Presence of the key is the signal; the spec carries options inside it.
        return isinstance(session_caps, dict) and "resume" in session_caps

    @property
    def supports_session_load(self) -> bool:
        return self._read_load_session_capability(self.agent_capabilities)

    def extra_session_params(self) -> Dict[str, Any]:
        """Agent-specific additions to the ``session/new`` params.

        Override in subclasses (e.g. a model hint). The generic params are
        the spec-required ``cwd`` + ``mcpServers``.
        """
        return {}

    def _persist_acp_session_id(self) -> None:
        """Record the ACP session id so this session can be resumed later.

        The id lives only in this process's memory otherwise, so the
        conversation becomes unresumable the moment the wrapper exits — even
        for agents that advertise ``loadSession``.

        ``instance_metadata`` is shallow-merged server-side, so sibling keys
        survive. Best-effort: losing the id costs a future resume, it must
        never break the session coming up now.
        """
        if not (self.vicoa_client and self.config.agent_instance_id):
            return
        if not self.session_id:
            return
        try:
            self.vicoa_client.patch_agent_instance(
                self.config.agent_instance_id,
                instance_metadata={"acp_session_id": self.session_id},
            )
        except Exception as exc:
            self.log(f"[WARNING] Failed to persist ACP session id: {exc}")

    def _establish_session(self) -> None:
        """Restore the prior conversation when possible, else start a new one.

        Split out of ``_setup`` so the branch is directly testable — it decides
        whether a resumed session actually carries its history, which is the
        difference between resume working and quietly not working.

        Never aborts bring-up: an agent that can't reload, a deleted session
        file, or a schema change all degrade to a fresh session. The user's
        transcript stays visible either way, so failing here would strand a
        session that could still be used.
        """
        acp_session_id = getattr(self.config, "acp_session_id", None)
        if acp_session_id:
            loaded = False
            try:
                loaded = self.load_session(acp_session_id)
            except Exception as exc:
                self.log(f"[WARNING] session/load raised, starting fresh: {exc}")
            if loaded:
                return
            self.log(
                "[ACP] Could not restore the prior conversation; "
                "continuing with a new agent session"
            )

        self.create_session()

    def load_session(self, acp_session_id: str) -> bool:
        """Reload a prior conversation via ``session/load``.

        Returns True when the agent restored it. False means the caller should
        fall back to ``session/new`` — but only in cases where no context was
        expected to survive, since the transcript stays visible either way.
        """
        acp = self.acp
        if not acp:
            raise ACPError("ACP client not started")

        if not self.supports_session_load:
            self.log(
                f"[ACP] {self.config.agent_type} does not advertise loadSession; "
                "starting a fresh session"
            )
            return False

        params: Dict[str, Any] = {
            "sessionId": acp_session_id,
            "cwd": self.config.project_path,
            "mcpServers": [],
        }
        params.update(self.extra_session_params())

        self.log(f"[ACP] Loading session (session/load): {acp_session_id}")
        # Set before the request: the replay notifications arrive on the reader
        # thread while this call is still in flight. Cleared in `finally` so a
        # failed load can't leave the wrapper permanently deaf to updates.
        self._replaying_session = True
        try:
            try:
                response = acp.send_request("session/load", params)
                response.raise_for_error()
            except ACPError as exc:
                if self._is_auth_required_error(exc):
                    self._authenticate()
                    try:
                        response = acp.send_request("session/load", params)
                        response.raise_for_error()
                    except ACPError as retry_exc:
                        self.log(
                            f"[WARNING] session/load failed after auth: {retry_exc}"
                        )
                        return False
                else:
                    # Agent upgrade changed its session-file schema, the user
                    # deleted it, or the id is unknown. Mirrors codex's
                    # thread/resume fallback.
                    self.log(f"[WARNING] session/load failed: {exc}")
                    return False
        finally:
            self._replaying_session = False

        result = response.result or {}
        # Spec allows an empty result; the session id we asked for stays valid.
        self.session_id = str(result.get("sessionId") or acp_session_id)
        self.log(f"[ACP] Session loaded: {self.session_id}")

        self._persist_acp_session_id()
        self._apply_session_state(result)
        self._apply_initial_mode()
        self._report_live_session_state()
        return True

    def create_session(self) -> None:
        """Create the agent session via spec-compliant ``session/new``.

        Generic ACP v1 implementation: sends ``cwd`` + ``mcpServers`` (plus
        subclass extras), retries once through ``authenticate`` when the
        agent answers auth-required (-32000), and retains the returned
        session state (``modes``, ``configOptions``) for mode switching and
        model selection. Subclasses with non-standard session setup (e.g.
        OpenCode's mode param) override this.
        """
        acp = self.acp
        if not acp:
            raise ACPError("ACP client not started")

        params: Dict[str, Any] = {
            "cwd": self.config.project_path,
            "mcpServers": [],
        }
        params.update(self.extra_session_params())

        self.log("[ACP] Creating session (session/new)")
        try:
            response = acp.send_request("session/new", params)
            response.raise_for_error()
        except ACPError as e:
            if not self._is_auth_required_error(e):
                raise
            self._authenticate()
            response = acp.send_request("session/new", params)
            response.raise_for_error()

        result = response.result or {}
        session_id = result.get("sessionId")
        if not session_id:
            raise ACPError("session/new response missing sessionId")
        self.session_id = str(session_id)
        self.log(f"[ACP] Session created: {self.session_id}")

        self._persist_acp_session_id()
        self._apply_session_state(result)
        self._apply_initial_mode()
        self._report_live_session_state()

    @staticmethod
    def _is_auth_required_error(error: Exception) -> bool:
        """Spec error code -32000 = Authentication required."""
        text = str(error)
        return "-32000" in text or "authentication required" in text.lower()

    def _authenticate(self) -> None:
        """Run the ACP ``authenticate`` flow with an advertised auth method."""
        acp = self.acp
        if not acp:
            raise ACPError("ACP client not started")
        method_id = getattr(self.config, "auth_method_id", None)
        if not method_id and self.auth_methods:
            method_id = str(self.auth_methods[0].get("id") or "")
        if not method_id:
            raise ACPError(
                "Agent requires authentication but advertised no auth methods. "
                "Log in with the agent CLI on this machine first."
            )
        self.log(f"[ACP] Authenticating with method {method_id!r}")
        response = acp.send_request("authenticate", {"methodId": method_id})
        response.raise_for_error()

    def _apply_session_state(self, result: Dict[str, Any]) -> None:
        """Retain modes/models/configOptions from session/new|load responses."""
        modes = result.get("modes")
        if isinstance(modes, dict):
            self.available_modes = [
                m for m in (modes.get("availableModes") or []) if isinstance(m, dict)
            ]
            current = modes.get("currentModeId")
            self.current_mode_id = str(current) if current else None
        # Dedicated models block (gemini/kimi use this; cursor/copilot expose
        # models via a configOption instead — see _live_available_models).
        models = result.get("models")
        if isinstance(models, dict):
            self.available_models = [
                m for m in (models.get("availableModels") or []) if isinstance(m, dict)
            ]
            current_model = models.get("currentModelId")
            if current_model:
                self.current_model_id = str(current_model)
        config_options = result.get("configOptions")
        if isinstance(config_options, list):
            self.session_config_options = [
                o for o in config_options if isinstance(o, dict)
            ]
            model_value = self._current_model_config_value()
            if model_value:
                self.current_model_id = model_value

    def _current_model_config_value(self) -> Optional[str]:
        """currentValue of the model config option, if the agent exposes one."""
        option = next(
            (
                o
                for o in self.session_config_options
                if str(o.get("category") or "") == "model"
            ),
            None,
        )
        if option and option.get("currentValue") is not None:
            return str(option.get("currentValue"))
        return None

    def _live_available_models(self) -> list[Dict[str, str]]:
        """Normalize the agent's available models to ``[{id,label}]``.

        Prefers the dedicated ``models.availableModels`` block; falls back to
        the ``model`` configOption's ``options`` list.
        """
        if self.available_models:
            return [
                {
                    "id": str(m.get("modelId")),
                    "label": str(m.get("name") or m.get("modelId")),
                }
                for m in self.available_models
                if m.get("modelId")
            ]
        option = next(
            (
                o
                for o in self.session_config_options
                if str(o.get("category") or "") == "model"
            ),
            None,
        )
        if option:
            out: list[Dict[str, str]] = []
            for o in option.get("options") or []:
                if isinstance(o, dict) and o.get("value") is not None:
                    out.append(
                        {
                            "id": str(o.get("value")),
                            "label": str(o.get("name") or o.get("value")),
                        }
                    )
            return out
        return []

    def _live_session_state_config(self) -> Dict[str, Any]:
        """session_config additions describing the agent's live ACP pickers.

        Lets the mobile gear render the agent's REAL modes/models (sourced
        from the session/new payload) rather than catalog guesses — the
        catalog can't know account-gated or version-specific values.
        """
        out: Dict[str, Any] = {}
        modes = [
            {"id": str(m.get("id")), "label": str(m.get("name") or m.get("id"))}
            for m in self.available_modes
            if m.get("id")
        ]
        if modes:
            out["available_modes"] = modes
        if self.current_mode_id:
            out["current_mode"] = self.current_mode_id
        models = self._live_available_models()
        if models:
            out["available_models"] = models
        if self.current_model_id:
            out["current_model"] = self.current_model_id
        return out

    def _report_live_session_state(self) -> None:
        """PATCH the agent's live modes/models onto session_config for the UI."""
        extras = self._live_session_state_config()
        if extras:
            self._patch_session_config(extras)

    def _apply_initial_mode(self) -> None:
        """Apply the spawn-time requested session mode, when supported."""
        requested = getattr(self.config, "permission_mode", None)
        if not requested or requested == self.current_mode_id:
            return
        if not self._set_session_mode(requested, announce=False):
            self.log(
                f"[ACP] Requested initial mode {requested!r} not applied "
                f"(available: {[m.get('id') for m in self.available_modes]})"
            )

    @staticmethod
    def _resolve_model_option_value(
        requested: str, option: Dict[str, Any]
    ) -> Optional[str]:
        """Map a catalog model id onto the agent's real config-option value.

        Cursor (and likely other ACP agents) advertise variant-suffixed values
        like ``composer-2.5[fast=true]`` while our catalog carries the friendly
        ``composer-2.5``. Match the exact value first, then the part before
        ``[`` (the variant suffix), then the display name. When the agent
        doesn't enumerate its options we can't validate, so pass the requested
        value through unchanged (best-effort, the old behavior).
        """
        choices = [o for o in (option.get("options") or []) if isinstance(o, dict)]
        req = requested.strip()
        if not choices:
            return req
        for o in choices:  # exact value
            if str(o.get("value")) == req:
                return str(o.get("value"))
        for o in choices:  # value carrying a variant suffix: "composer-2.5[...]"
            value = str(o.get("value"))
            if value.split("[", 1)[0] == req:
                return value
        req_lower = req.lower()
        for o in choices:  # friendly display name
            if str(o.get("name") or "").strip().lower() == req_lower:
                return str(o.get("value"))
        return None

    def _apply_initial_model(self, model: str) -> None:
        """Best-effort spawn-time model application via the model config option.

        ACP's model surface is the session config option with
        ``category: "model"`` (``session/set_config_option``) — the reliable,
        live path. Agents that don't expose one (or reject the value) keep
        their own default; the requested model then only lives in session_config
        as a next-session hint. Never fails the session.

        Whether or not a set is needed, the actually-active model is reported
        back to session_config so the mid-session gear and the new-session
        choice stay consistent.
        """
        requested = (model or "").strip()
        # "auto" / "default" means "let the agent keep its own default".
        if not requested or requested.lower() in {"auto", "default"}:
            return
        option = next(
            (
                o
                for o in self.session_config_options
                if str(o.get("category") or "") == "model"
            ),
            None,
        )
        if option is None:
            self.log(
                f"[ACP] No model config option advertised; keeping agent default "
                f"(requested {model!r})"
            )
            return
        resolved = self._resolve_model_option_value(requested, option)
        if resolved is None:
            offered = [
                str(o.get("value"))
                for o in (option.get("options") or [])
                if isinstance(o, dict)
            ]
            self.log(
                f"[ACP] Requested model {requested!r} not offered by agent; "
                f"keeping default (offered: {offered})"
            )
            return

        acp = self.acp
        if not acp or not self.session_id:
            return
        if option.get("currentValue") != resolved:
            try:
                response = acp.send_request(
                    "session/set_config_option",
                    {
                        "sessionId": self.session_id,
                        "configId": option.get("id"),
                        "value": resolved,
                    },
                    timeout=10.0,
                )
                response.raise_for_error()
                self._apply_session_state(response.result or {})
                self.log(f"[ACP] Spawn-time model applied: {resolved}")
            except Exception as e:
                self.log(
                    f"[WARNING] Could not apply spawn-time model {resolved!r}: {e}"
                )
                return
        # Reflect the active model (whether just set or already current) so the
        # gear shows what the user picked, not the agent's persisted last model.
        self.current_model_id = resolved
        self._report_live_session_state()

    def _run_event_loop(self) -> None:
        """Main event loop - processes queued messages and flushes streamed chunks.

        User-message delivery from Vicoa is handled by the session-scoped /ws
        subscriber started in :py:meth:`_setup`. ``_on_ws_user_message``
        appends arriving messages to ``message_queue``; this loop drains.
        """
        self.log("[INFO] Starting event loop")

        while self.running:
            try:
                # Process any queued messages, coalescing a burst the user sent
                # while the agent was busy into a single turn.
                self._drain_and_dispatch_queue()

                # Flush streamed chunks when stream has gone quiet.
                if (
                    self._assistant_chunk_buffer
                    and self._assistant_chunk_last_update_at > 0
                    and (
                        time.time() - self._assistant_chunk_last_update_at
                        >= self._assistant_chunk_flush_after_seconds
                    )
                    and self._should_flush_assistant_chunk_buffer()
                ):
                    self._flush_assistant_chunk_buffer()

                time.sleep(0.1)

            except AuthenticationError:
                # Dead credential (401). Don't log-and-continue — break out so
                # run() ends this headless session instead of spinning forever.
                raise
            except Exception as e:
                self.log(f"[ERROR] Error in event loop: {e}")
                import traceback

                self.log(traceback.format_exc())

    def _drain_and_dispatch_queue(self) -> None:
        """Drain the whole inbound queue and dispatch it as a single prompt.

        Called each event-loop tick. Two things make a burst the user sent
        while the agent was busy run as ONE turn instead of one turn each:

        * While a prompt is in flight we leave messages sitting in
          ``message_queue`` (they stay flagged "queued" in the UI, which is
          accurate). We do NOT drip them into the agent per tick.
        * When the turn ends (``_prompt_in_flight`` clears) the next tick drains
          the whole accumulated queue at once and coalesces it. Draining fresh
          at the boundary — rather than per-tick into ``_queued_prompts`` —
          closes the window where a message arriving in the last <tick before
          turn end would miss the batch and run as its own turn.
        """
        if not self.message_queue:
            return
        # Hold everything until the current turn finishes; the boundary drain
        # below runs the whole burst together. ``_prompt_in_flight`` is a plain
        # bool — a stale read only costs one 0.1s tick, and send_prompt re-checks
        # it under the lock before actually starting a turn.
        if self._prompt_in_flight:
            return
        batch = self.message_queue
        self.message_queue = []
        parts: list[tuple[str, tuple[AttachmentRef, ...]]] = []
        for message, attachments, message_id in batch:
            # Drop a message the user cancelled while the turn preceding this
            # drain was running. The cancel arrived as a message-update after
            # the row was already queued, so this boundary is the first point we
            # can honor it. Don't mark it consumed — it's cancelled, not
            # consumed (the backend already stamped it cancelled).
            if message_id and message_id in self._cancelled_message_ids:
                self._cancelled_message_ids.discard(message_id)
                self.log(f"[Vicoa] Dropping cancelled queued message {message_id}")
                continue
            # The turn starts here, so the row is no longer "queued". Must
            # happen before send_prompt: the API stamps
            # ``message_metadata.queue`` on every message that arrives while
            # the instance is ACTIVE (which an ACP session is from daemon
            # registration onward), and nothing else in this wrapper clears
            # it — the web UI would pin the message in its queued-messages bar
            # forever instead of reconciling it into the transcript.
            self._mark_message_consumed(message_id)
            # A control command mixed into the burst (e.g. a model switch) is
            # handled here rather than folded into the coalesced prompt text —
            # same as the per-message send_prompt path this replaces.
            if message and self._handle_control_command(message):
                continue
            parts.append((message, attachments))
        if not parts:
            return
        message, attachments = self._coalesce_prompt_parts(parts)
        self._set_agent_status("ACTIVE")
        self.send_prompt(message, attachments)

    def _start_ws_client(self) -> None:
        """Spin up the session-scoped /ws subscriber on a background thread.

        ``SessionMessagesWsClient`` handles the hello + ``fetch_messages_request``
        catch-up (no separate ``get_pending_messages`` drain), live
        ``new-message`` delivery, and reconnect-with-jitter. Its sync
        callback runs on the WS reader thread and feeds ``message_queue``
        directly — the event loop drains it. Replaces the legacy SSE
        listener (websocket-migration §4 Phase 3 — same migration that
        landed for ``codex_native``).
        """
        if not self.vicoa_client or not self.config.agent_instance_id:
            return
        ws_url = os.environ.get("VICOA_WS_URL") or derive_ws_url(self.config.base_url)
        cli_version = os.environ.get("VICOA_CLI_VERSION")
        self._ws_client = SessionMessagesWsClient(
            ws_url=ws_url,
            api_key=self.config.api_key,
            instance_id=str(self.config.agent_instance_id),
            on_user_message=self._on_ws_user_message,
            cli_version=cli_version,
            on_message_update=self._on_ws_message_update,
            on_instance_update=self._on_ws_instance_update,
        )
        self._ws_thread = threading.Thread(
            target=self._ws_client.run,
            name=f"{self.config.agent_type}-ws-{str(self.config.agent_instance_id)[:8]}",
            daemon=True,
        )
        self._ws_thread.start()
        self.log(f"[Vicoa] WS subscriber connected to {ws_url}")

    def _on_ws_user_message(self, body: Dict[str, Any]) -> None:
        """WS-thread callback. Filter to USER messages and feed the queue.

        ``body`` shape matches the ``new-message`` payload: ``{id, content,
        sender_type, ...}``. Broadcast also includes AGENT echoes of our own
        posts, so filter by sender. ``_suspend_vicoa_polling`` is honored so
        permission long-polling (which reads queued user messages inline via
        ``send_message(requires_user_input=True)``) doesn't double-deliver.
        Exceptions raised here would crash the WS reader thread silently —
        catch and log.
        """
        try:
            sender = (body.get("sender_type") or "").lower()
            content = body.get("content") or ""
            attachments = tuple(extract_attachment_refs(body.get("message_metadata")))
            if sender not in {"user", "human"} or (not content and not attachments):
                return
            if self._suspend_vicoa_polling:
                return
            message_id = body.get("id")
            self._ingest_user_message(
                content, attachments, str(message_id) if message_id else None
            )
        except Exception:
            self.log("[Vicoa] WS callback raised")
            import traceback

            self.log(traceback.format_exc())

    def _on_ws_instance_update(self, body: Dict[str, Any]) -> None:
        """WS-thread callback for instance row changes.

        Stops the wrapper when the session is archived/closed from another
        client. Setting ``running = False`` lets the event loop exit on its
        next tick (~0.1s), after which ``_cleanup`` runs and the process exits.
        """
        try:
            if instance_update_requests_stop(body):
                self.log("[Vicoa] Session closed elsewhere; stopping wrapper")
                self._stopping = True
                self.running = False
        except Exception:
            self.log("[Vicoa] instance-update callback raised")

    def _on_ws_message_update(self, body: Dict[str, Any]) -> None:
        """WS-thread callback for message row changes.

        The only change we act on is the user cancelling a still-queued message:
        the backend stamps ``message_metadata.queue.status = "cancelled"`` and
        broadcasts it. We remember the id so ``_drain_and_dispatch_queue`` skips
        it instead of folding it into the next turn. Runs on the WS reader
        thread; a bare ``set.add`` is atomic under the GIL — same as the
        ``message_queue`` append this callback path already does off-thread.
        Mirrors claude_code._on_ws_message_update.
        """
        try:
            md = body.get("message_metadata") or {}
            status = (md.get("queue") or {}).get("status")
            message_id = body.get("id")
            if status == "cancelled" and message_id:
                self._cancelled_message_ids.add(str(message_id))
                self.log(f"[Vicoa] User cancelled queued message {message_id}")
        except Exception:
            self.log("[Vicoa] message-update callback raised")

    def _ingest_user_message(
        self,
        content: str,
        attachments: tuple[AttachmentRef, ...] = (),
        message_id: Optional[str] = None,
    ) -> None:
        """Route user message to priority handler or normal queue.

        ``message_id`` is optional: catch-up paths (queued messages fetched on
        an awaiting-input turn) don't carry one, and a priority message is
        handled inline rather than queued, so neither needs a consumed stamp.
        """
        normalized = str(content or "").strip()
        if not normalized and not attachments:
            return
        if normalized and self.handle_priority_message(normalized):
            return
        self.message_queue.append((normalized, attachments, message_id))

    def _mark_message_consumed(self, message_id: Optional[str]) -> None:
        """Clear the ``message_metadata.queue`` stamp for a dequeued message.

        Best effort — failing to clear the badge must never abort the turn the
        user is waiting on.
        """
        if not message_id or not self.vicoa_client:
            return
        try:
            self.vicoa_client.mark_message_consumed(message_id)
        except Exception as exc:
            self.log(f"[WARNING] Failed to mark message {message_id} consumed: {exc}")

    def handle_priority_message(self, content: str) -> bool:
        """Handle high-priority user messages immediately.

        Returns True if message was consumed and should not be queued.
        Subclasses can override for control commands like interrupt or mode switch.
        """
        return self._handle_control_command(content)

    def _parse_control_command(self, content: str) -> Dict[str, str] | None:
        """Parse JSON control command from text (can be embedded).

        Supported formats:
        - {"type": "control", "setting": "X", "value": "Y"}
        - {"type": "control", "action": "interrupt"}
        """
        if not content:
            return None

        # Only when the control token actually *trails* the message — a user
        # message that merely quotes control JSON amid prose must route as
        # ordinary input, not be swallowed as a control command. Same guard the
        # headless claude/codex path uses (control_command.is_control_envelope).
        if not is_control_envelope(content):
            return None

        match = CONTROL_JSON_PATTERN.search(content)
        if not match:
            return None

        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

        if not isinstance(parsed, dict) or parsed.get("type") != "control":
            return None

        setting = parsed.get("setting") or parsed.get("action")
        if not setting:
            return None

        result: Dict[str, str] = {"setting": str(setting)}
        value = parsed.get("value")
        if value is not None:
            result["value"] = str(value)
        return result

    def _handle_control_command(self, content: str) -> bool:
        """Handle JSON control message and return whether it was consumed."""
        control = self._parse_control_command(content)
        if not control:
            return False

        self._apply_control_command(control)
        self._set_awaiting_input_state()
        return True

    def _apply_control_command(self, control: Dict[str, str]) -> None:
        """Apply parsed control command."""
        setting = control.get("setting", "")
        value = control.get("value")
        self.log(
            f"[Vicoa] Control command received: {setting}"
            + (f"={value}" if value is not None else "")
        )

        if setting == "interrupt":
            self._handle_interrupt_control()
            return

        # The mobile gear sends `permission_mode` uniformly; older clients
        # used `agent_type` for mode-style agents (OpenCode overrides this
        # method and keeps its own handling).
        if setting in {"permission_mode", "mode", "agent_type"}:
            self._handle_set_mode_control(value)
            return

        if setting == "model":
            self._handle_model_control(value)
            return

        self._send_feedback_message(f"Unknown control setting '{setting}'.")

    def _handle_set_mode_control(self, value: Optional[str]) -> None:
        """Switch the ACP session mode from a UI control command."""
        requested = (value or "").strip()
        if not requested:
            self._send_feedback_message("Invalid mode: empty value.")
            return
        if requested == self.current_mode_id:
            self._send_feedback_message(f"Mode is already {requested}.")
            return
        self._set_session_mode(requested)

    def _set_session_mode(self, mode_id: str, announce: bool = True) -> bool:
        """Send ``session/set_mode`` after validating against availableModes.

        Returns True when the mode is now active. On an invalid id the
        feedback message lists the agent's real mode ids — catalog hints can
        drift from what a given CLI version actually advertises.
        """
        acp = self.acp
        if not acp or not self.session_id:
            if announce:
                self._send_feedback_message("Failed to change mode: session not ready.")
            return False

        if not self.available_modes:
            if announce:
                self._send_feedback_message(
                    "Mode switching is not supported by this agent."
                )
            return False

        available_ids = [str(m.get("id")) for m in self.available_modes if m.get("id")]
        if mode_id not in available_ids:
            if announce:
                self._send_feedback_message(
                    f"Invalid mode '{mode_id}'. Available modes: "
                    f"{', '.join(available_ids)}."
                )
            return False

        try:
            response = acp.send_request(
                "session/set_mode",
                {"sessionId": self.session_id, "modeId": mode_id},
                timeout=10.0,
            )
            response.raise_for_error()
        except Exception as e:
            self.log(f"[WARNING] session/set_mode failed for {mode_id!r}: {e}")
            if announce:
                self._send_feedback_message(f"Failed to change mode to {mode_id}.")
            return False

        self.current_mode_id = mode_id
        # `permission_mode` for the existing pill; `current_mode` for the
        # runtime-sourced gear (which renders from available_modes/current_mode).
        self._patch_session_config(
            {"permission_mode": mode_id, "current_mode": mode_id}
        )
        if announce:
            self._send_feedback_message(f"Mode changed to {mode_id}.")
        return True

    def _handle_model_control(self, value: Optional[str]) -> None:
        """Best-effort mid-session model change via session config options.

        ACP's model-selection surface is the config option with
        ``category: "model"`` (``session/set_config_option``). When the agent
        doesn't expose one, the change is persisted for the next session only.
        """
        requested = (value or "").strip()
        if not requested:
            self._send_feedback_message("Invalid model: empty value.")
            return

        option = next(
            (
                o
                for o in self.session_config_options
                if str(o.get("category") or "") == "model"
            ),
            None,
        )
        acp = self.acp
        if option and acp and self.session_id:
            try:
                response = acp.send_request(
                    "session/set_config_option",
                    {
                        "sessionId": self.session_id,
                        "configId": option.get("id"),
                        "value": requested,
                    },
                    timeout=10.0,
                )
                response.raise_for_error()
                self._apply_session_state(response.result or {})
                self.current_model_id = requested
                self._report_live_session_state()
                self._patch_session_config(
                    {"model": requested, "current_model": requested}
                )
                self._send_feedback_message(f"Model changed to {requested}.")
                return
            except Exception as e:
                self.log(f"[WARNING] session/set_config_option failed: {e}")
                self._send_feedback_message(
                    f"Failed to change model to {requested}: the agent rejected it."
                )
                return

        # Agents that expose models via the dedicated `models` block
        # (gemini/kimi) don't have a live config-option to flip; persist the
        # choice so it applies on the next session. (A dedicated set-model
        # wire method exists upstream but is unstable/unversioned — verify at
        # runtime before driving it live.)
        self.current_model_id = requested
        self._patch_session_config({"model": requested, "current_model": requested})
        self._send_feedback_message(
            f"Model set to {requested}. It will take effect on the next session."
        )

    def _session_config_agent_id(self) -> str:
        """Catalog agent id used in session_config PATCHes."""
        catalog_id = getattr(self.config, "catalog_agent_id", None)
        return str(catalog_id) if catalog_id else self.config.agent_type.lower()

    def _patch_session_config(self, updates: Dict[str, Any]) -> None:
        """Persist a session_config change so the chat-header pill updates."""
        if not self.vicoa_client:
            return
        try:
            self.vicoa_client.patch_agent_instance(
                self.config.agent_instance_id,
                session_config={"agent": self._session_config_agent_id(), **updates},
            )
        except Exception as e:
            self.log(f"[WARNING] Failed to PATCH session_config: {e}")

    def _handle_interrupt_control(self) -> None:
        """Interrupt the active ACP session."""
        acp = self.acp
        if not acp or not self.session_id:
            self._send_feedback_message("Failed to interrupt: session not ready.")
            return

        self._interrupt_active = True
        self._prompt_cancel_event.set()

        # Drop the cancelled turn's tail: whatever was worth showing already
        # reached the chat, and letting the trailing chunks land would both
        # append orphan text after the "Interrupted." notice and bounce the
        # status back to ACTIVE.
        self._awaiting_after_next_agent_output = False
        self._assistant_chunk_buffer = ""
        self._thought_chunk_buffer = ""
        self._drop_stream_output_until_next_prompt = True

        try:
            acp.send_notification("session/cancel", {"sessionId": self.session_id})
        except Exception as e:
            self.log(f"[WARNING] Failed to send session/cancel notification: {e}")

        if self._hard_interrupt_fallback_delay_seconds > 0:
            self._schedule_hard_interrupt_fallback()
        else:
            try:
                interrupted = acp.interrupt_process()
                if interrupted:
                    self.log("[ACP] Used SIGINT fallback for interrupt")
            except Exception as e:
                self.log(f"[WARNING] SIGINT fallback failed: {e}")

        self._send_feedback_message("Interrupted.")
        self._set_awaiting_input_state()

    def _schedule_hard_interrupt_fallback(self) -> None:
        """Send SIGINT only if the prompt hasn't settled within the fallback delay."""
        acp = self.acp
        if not acp:
            return

        def _fallback() -> None:
            try:
                threading.Event().wait(self._hard_interrupt_fallback_delay_seconds)
                if not self.running or self._permission_request_active:
                    return
                with self._prompt_state_lock:
                    still_in_flight = self._prompt_in_flight
                if not still_in_flight:
                    return
                interrupted = acp.interrupt_process()
                if interrupted:
                    self.log(
                        "[ACP] Used delayed SIGINT fallback for active prompt interrupt"
                    )
            except Exception as e:
                self.log(f"[WARNING] Delayed SIGINT fallback failed: {e}")

        threading.Thread(target=_fallback, daemon=True).start()

    def _send_feedback_message(self, content: str) -> None:
        """Send a non-blocking status message to UI."""
        if not self.vicoa_client:
            return
        try:
            response = self.vicoa_client.send_message(
                content=content,
                agent_type=self.config.agent_type,
                agent_instance_id=self.config.agent_instance_id,
                requires_user_input=False,
            )
            if response and hasattr(response, "message_id"):
                self.last_message_id = response.message_id
        except Exception as e:
            self.log(f"[WARNING] Failed to send feedback message: {e}")

    @staticmethod
    def _coalesce_prompt_parts(
        parts: list[tuple[str, tuple[AttachmentRef, ...]]],
    ) -> tuple[str, tuple[AttachmentRef, ...]]:
        """Merge several queued user messages into a single prompt.

        A burst of messages the user sent while the agent was busy should run
        as one turn — so the agent sees them together — instead of one turn
        each. Non-empty texts are joined by a blank line; attachments
        concatenate in arrival order.
        """
        text = "\n\n".join(part for part, _ in parts if part)
        attachments: tuple[AttachmentRef, ...] = tuple(
            att for _, atts in parts for att in atts
        )
        return text, attachments

    def send_prompt(
        self, message: str, attachments: tuple[AttachmentRef, ...] = ()
    ) -> None:
        """Send user message to agent via session/prompt ACP request.

        Dispatches to a background thread so the event loop stays responsive.
        Subclasses that need a different wire format should override
        _run_prompt_request() rather than this method.
        """
        if not self.acp or not self.session_id:
            self.log("[WARNING] Cannot send message: ACP not ready")
            return

        if message and self._handle_control_command(message):
            return

        with self._prompt_state_lock:
            if self._prompt_in_flight:
                self._queued_prompts.append((message, attachments))
                self.log("[ACP] Prompt queued while another prompt is running")
                return
            self._prompt_in_flight = True
            self._prepare_for_new_prompt()

        worker = threading.Thread(
            target=self._run_prompt_request,
            args=(message, attachments),
            daemon=True,
        )
        worker.start()

    def _build_prompt_blocks(
        self, message: str, attachments: tuple[AttachmentRef, ...]
    ) -> list[Dict[str, Any]]:
        """Build ACP ``session/prompt`` content blocks for text + attachments.

        Images go inline as ACP image blocks when the agent advertised image
        prompt support; every other case (non-image files, or an agent without
        image support) parks bytes under ``~/.vicoa/attachments/<instance>``
        and references them by path in the text. Failed downloads degrade to a
        text note either way.
        """
        image_blocks: list[Dict[str, Any]] = []
        notes: list[str] = []
        for ref in attachments:
            try:
                if not self.vicoa_client:
                    raise RuntimeError("vicoa client not ready")
                data, mime_type = self.vicoa_client.download_attachment(ref.id)
                if is_image_mime(mime_type) and self._supports_image_prompts:
                    image_blocks.append(
                        {
                            "type": "image",
                            "data": base64.b64encode(data).decode("ascii"),
                            "mimeType": mime_type,
                        }
                    )
                else:
                    local = save_attachment(
                        attachments_dir(str(self.config.agent_instance_id)),
                        ref,
                        data,
                        mime_type,
                    )
                    notes.append(attachment_note(local))
            except Exception as e:
                self.log(f"[ERROR] Failed to download attachment {ref.id}: {e}")
                notes.append(unavailable_note(ref))

        full_text = "\n".join(part for part in [message, *notes] if part)
        blocks: list[Dict[str, Any]] = []
        if full_text:
            blocks.append({"type": "text", "text": full_text})
        blocks.extend(image_blocks)
        return blocks

    def _run_prompt_request(
        self, message: str, attachments: tuple[AttachmentRef, ...] = ()
    ) -> None:
        """Execute a session/prompt request on a background thread."""
        try:
            acp = self.acp
            if not acp or not self.session_id:
                raise RuntimeError("ACP client not ready")

            payload = {
                "sessionId": self.session_id,
                "prompt": self._build_prompt_blocks(message, attachments)
                if attachments
                else [{"type": "text", "text": message}],
            }
            response = acp.send_request(
                "session/prompt",
                payload,
                timeout=self._prompt_timeout_seconds,
                cancel_event=self._prompt_cancel_event,
                cancel_grace_period=self._prompt_cancel_grace_period_seconds,
            )
            response.raise_for_error()
            result = response.result or {}
            stop_reason = str(result.get("stopReason") or "")
            self._handle_stop_reason(stop_reason)
            self._awaiting_after_next_agent_output = True
            self._flush_assistant_chunk_buffer()
            # The request "succeeded" but the agent streamed nothing and ran no
            # tools: don't let that silently look like the agent ignored the
            # user. Surface it (with whatever the agent printed to stderr). Skip
            # when the turn was cancelled — that quiet is expected.
            if (
                not self._turn_produced_output
                and not self._prompt_cancel_event.is_set()
            ):
                self._report_empty_turn(stop_reason)
            self._set_awaiting_input_state()
        except Exception as e:
            interrupted = (
                self._prompt_cancel_event.is_set() or "interrupted locally" in str(e)
            )
            if not interrupted:
                self._awaiting_after_next_agent_output = True
                self._flush_assistant_chunk_buffer()
            self._set_awaiting_input_state()
            if interrupted:
                self.log("[ACP] Prompt interrupted")
            else:
                self.log(f"[ERROR] Failed to send prompt: {e}")
                self._send_feedback_message(f"Prompt failed: {e}")
        finally:
            next_prompt: Optional[tuple[str, tuple[AttachmentRef, ...]]] = None
            with self._prompt_state_lock:
                self._prompt_in_flight = False
                if self._queued_prompts:
                    # Coalesce every prompt that queued up during this turn into
                    # one, so a burst of user messages runs as a single next
                    # turn instead of one turn per message.
                    batch = self._queued_prompts
                    self._queued_prompts = []
                    next_prompt = self._coalesce_prompt_parts(batch)
                    self._prompt_in_flight = True
                    self._prepare_for_new_prompt()

            if next_prompt:
                worker = threading.Thread(
                    target=self._run_prompt_request,
                    args=next_prompt,
                    daemon=True,
                )
                worker.start()

    def _prepare_for_new_prompt(self) -> None:
        """Reset transient interrupt/cancellation state before each prompt."""
        self._prompt_cancel_event.clear()
        self._interrupt_active = False
        self._drop_stream_output_until_next_prompt = False
        self._turn_produced_output = False
        self._turn_stderr.clear()

    def _handle_stop_reason(self, stop_reason: str) -> None:
        """Surface non-routine prompt-turn stop reasons to the user.

        ``end_turn`` is the normal case and ``cancelled`` is already
        narrated by the interrupt path — both stay silent. The remaining
        spec values (``refusal``, ``max_tokens``, ``max_turn_requests``)
        would otherwise look like the agent silently going idle.
        """
        if stop_reason == "refusal":
            self._send_feedback_message(
                "The agent declined to continue with this request."
            )
        elif stop_reason == "max_tokens":
            self._send_feedback_message("The turn stopped early: token limit reached.")
        elif stop_reason == "max_turn_requests":
            self._send_feedback_message(
                "The turn stopped early: maximum model requests reached."
            )

    def _report_empty_turn(self, stop_reason: str) -> None:
        """Tell the user when a turn finished without producing any output.

        The ``session/prompt`` request returned success, but the agent streamed
        no text, ran no tools, and raised no ``session/error`` — so nothing
        reached the transcript and the session would otherwise just go quiet.
        This is the shape a swallowed provider error takes over ACP. The
        concrete case that motivated it: Kimi with ``thinking`` enabled on a
        model that rejects it returns HTTP 400 upstream, and kimi-code reports
        the failed turn as ``stopReason: end_turn`` with no ACP error — so the
        real cause ("thinking is not supported by this model") is only in the
        agent's own logs. We can't always recover that exact message, but we
        can stop pretending the turn succeeded, echo the stop reason, and
        attach any error the agent printed to stderr.
        """
        stderr_tail = [ln for ln in self._turn_stderr if ln.strip()]
        detail = ""
        if stderr_tail:
            joined = "\n".join(stderr_tail[-5:])
            detail = f"\n\nLast agent error output:\n```\n{joined}\n```"
        reason = f" (stop reason: {stop_reason})" if stop_reason else ""
        self._send_feedback_message(
            f"{self.config.agent_type} ended the turn without producing any "
            f"output{reason}. The request reached the agent but nothing came "
            f"back. This usually means the model rejected it, e.g. an option "
            f"(such as thinking/reasoning mode) that the selected model does "
            f"not support. Try a different model, or check the agent's logs "
            f"for the underlying error.{detail}"
        )

    def handle_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent-originated ACP requests.

        Permission requests get the interactive flow; anything else is
        offered to :py:meth:`handle_extension_request` (vendor extensions
        like ``cursor/ask_question``) and otherwise rejected with JSON-RPC
        method-not-found, as the spec requires — we advertise no fs/terminal
        capabilities, so conformant agents never call those here.
        """
        if method in {"permission/request", "session/request_permission"}:
            option_id = self._handle_permission_request(params)
            if option_id == self._permission_cancelled_option_id:
                return {"outcome": {"outcome": "cancelled"}}
            return {"outcome": {"outcome": "selected", "optionId": option_id}}

        extension_result = self.handle_extension_request(method, params)
        if extension_result is not None:
            return extension_result

        raise ACPMethodNotFound(method)

    def handle_extension_request(
        self, method: str, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Hook for vendor-extension agent→client requests.

        Return a result dict to answer the request; return None to reject it
        with method-not-found.
        """
        return None

    def _handle_permission_request(self, params: Dict[str, Any]) -> str:
        """Present a permission request to the user and return the chosen option ID."""
        # Asking the user to approve a tool is real turn activity, so this turn
        # is not an empty/failed one even if it later ends with no text.
        self._turn_produced_output = True
        tool_call = params.get("toolCall", {})
        options = params.get("options", [])

        tool_kind = str(
            tool_call.get("kind", "") or tool_call.get("title", "") or "tool"
        ).strip()
        # Per the ACP spec, toolCall.locations is a list of objects
        # ({path, line?}), not strings — joining them directly crashes the
        # permission handler ("expected str instance, dict found"), which made
        # Gemini surface our JSON-RPC error as "[object Object]". Pull the
        # path out of each entry; tolerate plain strings defensively.
        location_paths: list[str] = []
        for loc in tool_call.get("locations") or []:
            if isinstance(loc, dict):
                path = str(loc.get("path") or "").strip()
                if path:
                    location_paths.append(path)
            elif isinstance(loc, str) and loc.strip():
                location_paths.append(loc.strip())

        message = f"Permission required: {tool_kind}\n"
        if location_paths:
            message += f"Locations: {', '.join(location_paths)}\n"

        option_lines: list[str] = []
        normalized_options: list[dict[str, str]] = []
        for idx, opt in enumerate(options):
            option_id = str(opt.get("optionId", "")).strip()
            option_name = (
                str(opt.get("name", "")).strip()
                or str(opt.get("title", "")).strip()
                or option_id
                or f"Option {idx + 1}"
            )
            option_kind = str(opt.get("kind", "")).strip()
            if option_id:
                normalized_options.append(
                    {"option_id": option_id, "name": option_name, "kind": option_kind}
                )
            option_lines.append(f"{idx + 1}. {option_name}")
        if option_lines:
            message += f"\n[OPTIONS]\n{chr(10).join(option_lines)}\n[/OPTIONS]"

        if self._interrupt_active:
            return self._permission_cancelled_option_id

        self._permission_request_active = True
        try:
            selected = self._wait_for_permission_decision(message, normalized_options)
            self.log(f"[ACP] Permission selected: {selected}")
            if selected != self._permission_cancelled_option_id:
                # The agent resumes the turn as soon as we answer — flip the
                # status back so the UI doesn't sit on AWAITING_INPUT while
                # the agent is actually working.
                self._set_agent_status("ACTIVE")
            return selected
        finally:
            self._permission_request_active = False

    def _wait_for_permission_decision(
        self, prompt_message: str, options: list[dict[str, str]]
    ) -> str:
        """Request permission choice from UI and parse user response."""
        fallback_option = self._select_default_permission_option(
            [{"optionId": opt["option_id"], "kind": opt.get("kind")} for opt in options]
        )
        if not self.vicoa_client:
            return fallback_option

        self._set_agent_status("AWAITING_INPUT")
        self._suspend_vicoa_polling = True

        try:
            if self._interrupt_active:
                return self._permission_cancelled_option_id

            response = self.vicoa_client.send_message(
                content=prompt_message,
                agent_type=self.config.agent_type,
                agent_instance_id=self.config.agent_instance_id,
                requires_user_input=True,
                timeout_minutes=self._permission_wait_timeout_minutes,
                poll_interval=self._permission_wait_poll_interval_seconds,
            )

            permission_message_id = getattr(response, "message_id", None)
            if permission_message_id:
                self.last_message_id = permission_message_id

            queued_messages = list(getattr(response, "queued_user_messages", []) or [])
            for raw_message in queued_messages:
                content = str(raw_message or "").strip()
                if not content:
                    continue

                control = self._parse_control_command(content)
                if control:
                    setting = control.get("setting")
                    if setting == "interrupt":
                        self._handle_interrupt_control()
                        return self._permission_cancelled_option_id
                    self._apply_control_command(control)
                    continue

                selected = self._parse_permission_reply(content, options)
                if selected:
                    return selected

            self._send_feedback_message(
                f"No valid permission response received. Defaulting to '{fallback_option}'."
            )
            return fallback_option
        except Exception as e:
            self.log(
                f"[WARNING] Permission request failed, defaulting to {fallback_option}: {e}"
            )
            return fallback_option
        finally:
            self._suspend_vicoa_polling = False

    def _parse_permission_reply(
        self, message: str, options: list[dict[str, str]]
    ) -> Optional[str]:
        """Parse a user reply into an ACP option ID. Returns None if unrecognized."""
        normalized = message.strip().lower()
        if not normalized:
            return None

        if normalized.isdigit():
            idx = int(normalized) - 1
            if 0 <= idx < len(options):
                return options[idx]["option_id"]

        for opt in options:
            option_id = opt["option_id"]
            option_name = opt["name"]
            option_kind = opt.get("kind", "")
            if normalized in {
                option_id.lower(),
                option_name.lower(),
                option_kind.lower(),
            }:
                return option_id

        keyword_map = {
            "once": {"allow", "allow once", "once", "yes", "approve", "y", "ok", "1"},
            "always": {"always", "allow always", "forever", "2"},
            "reject": {"reject", "deny", "no", "n", "cancel", "3"},
        }
        for opt in options:
            option_id = opt["option_id"]
            option_kind = opt.get("kind", "").lower()
            if option_kind in keyword_map and normalized in keyword_map[option_kind]:
                return option_id

        return None

    def _select_default_permission_option(self, options: list[Dict[str, Any]]) -> str:
        """Pick default permission option, preferring one-time allow."""
        if not options:
            return "once"

        normalized: list[tuple[str, str]] = []
        for opt in options:
            option_id = str(opt.get("optionId") or "").strip()
            kind = str(opt.get("kind") or "").strip()
            if option_id:
                normalized.append((option_id, kind))

        preferred_order = [
            "once",
            "allow_once",
            "always",
            "allow_always",
            "reject",
            "reject_once",
        ]
        for target in preferred_order:
            for option_id, kind in normalized:
                if option_id == target or kind == target:
                    return option_id

        return normalized[0][0] if normalized else "once"

    def _handle_acp_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Handle ACP notifications from agent.

        Args:
            method: Notification method name
            params: Notification parameters
        """
        if method not in {"session/update", "session/message"}:
            self.log(f"[ACP Notification] {method}")

        # Common notifications
        if method == "session/message":
            self._handle_session_message(params)
        elif method == "session/update":
            self._handle_session_update(params)
        elif method == "session/error":
            self._handle_session_error(params)
        elif method == "session/idle":
            self._handle_session_idle(params)
        else:
            self.handle_notification(method, params)

    def _handle_acp_request(
        self, method: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle ACP requests from agent that require JSON-RPC responses."""
        self.log(f"[ACP Request] {method}")
        return self.handle_request(method, params)

    def handle_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Handle agent-specific ACP notifications not handled by the base class.

        Override in subclasses to respond to agent-specific methods. The base
        implementation logs unhandled notifications.
        """
        self.log(f"[ACP] Unhandled notification: {method}")

    def _handle_session_message(self, params: Dict[str, Any]) -> None:
        """Handle session message from agent (agent output)."""
        message = params.get("message", {})

        text_parts = self._extract_text_fragments_from_content_payload(
            message.get("content", [])
        )
        # Preserve contiguous text fragments; some ACP providers split a single
        # token/word across adjacent parts (e.g. "1" + "px"). Joining with a
        # newline introduces artificial line breaks in user-visible responses.
        full_text = "".join(part for part in text_parts if part)

        if full_text:
            self._turn_produced_output = True
            self._append_assistant_chunk_block(full_text)

    def _handle_session_update(self, params: Dict[str, Any]) -> None:
        """Handle ACP session/update notifications.

        OpenCode primarily streams assistant output through this notification.
        """
        if self._replaying_session:
            # ``session/load`` replays the whole prior conversation through this
            # same notification, so the client can rebuild its UI. Vicoa already
            # has that transcript in the database — forwarding the replay would
            # append a second copy of the conversation on every resume (observed
            # with Cursor: one more agent reply each time Resume was clicked).
            return

        update = params.get("update") or {}
        update_type = update.get("sessionUpdate")

        # Real agent activity this turn (streamed text or a tool run). Recorded
        # even for tool updates we don't render, so a turn that did work but
        # emitted no user-visible text is not mistaken for an empty/failed turn.
        if update_type in {"agent_message_chunk", "tool_call", "tool_call_update"}:
            self._turn_produced_output = True

        if update_type == "agent_thought_chunk":
            # Model reasoning: accumulate and surface as a collapsed "thinking"
            # card (flushed ahead of the answer), rather than hiding it or
            # letting it flood the transcript as flat text.
            content = update.get("content")
            for text in self._extract_text_fragments_from_content_payload(content):
                if text:
                    self._thought_chunk_buffer += text
            return

        if update_type == "current_mode_update":
            # Agent-initiated mode change (e.g. a plan-mode exit tool).
            new_mode = update.get("currentModeId")
            if new_mode and new_mode != self.current_mode_id:
                self.current_mode_id = str(new_mode)
                self._patch_session_config(
                    {
                        "permission_mode": self.current_mode_id,
                        "current_mode": self.current_mode_id,
                    }
                )
                self.log(f"[ACP] Agent switched mode to {self.current_mode_id}")
            return

        if update_type == "available_commands_update":
            self.available_commands = [
                c
                for c in (update.get("availableCommands") or [])
                if isinstance(c, dict)
            ]
            return

        if update_type == "config_option_update":
            config_options = update.get("configOptions")
            if isinstance(config_options, list):
                self.session_config_options = [
                    o for o in config_options if isinstance(o, dict)
                ]
                model_value = self._current_model_config_value()
                if model_value:
                    self.current_model_id = model_value
                # Re-surface the refreshed model/mode lists to the gear.
                self._report_live_session_state()
            return

        if update_type in {
            "plan",
            "session_info_update",
            "usage_update",
            "user_message_chunk",
            "tool_call",
        }:
            # Known v1 updates we deliberately don't render: plans and the
            # initial tool_call announcement (tool output lands via
            # tool_call_update on completion), echoes of our own prompt,
            # titles, and context-usage meters.
            return

        if update_type == "agent_message_chunk":
            content = update.get("content")
            for text in self._extract_text_fragments_from_content_payload(content):
                if text:
                    self._append_assistant_chunk(text)
            return

        # Shell and tool executions are often surfaced as completed tool updates.
        if update_type == "tool_call_update":
            if not self._show_tool_updates:
                if update.get("status") not in {"completed", "failed"}:
                    return

                rendered_parts: list[str] = []
                change_preview = self._extract_tool_change_preview(update)
                if change_preview:
                    file_target = self._extract_tool_target_file(update)
                    rendered_parts.append(
                        f"Updated `{file_target}`.\n\n{change_preview}"
                        if file_target
                        else change_preview
                    )

                tool_text = self._extract_tool_update_text(update)
                compact_tool_text = self._compact_tool_output(tool_text)
                if compact_tool_text:
                    if (
                        not change_preview
                        or compact_tool_text.strip() != change_preview.strip()
                    ):
                        rendered_parts.append(compact_tool_text)

                if not rendered_parts:
                    return

                rendered = "\n\n".join(part for part in rendered_parts if part.strip())
                signature = rendered.strip()
                if signature and signature != self._last_tool_change_signature:
                    self._emit_acp_tool_card(update, rendered)
                    self._last_tool_change_signature = signature
                return

            if update.get("status") not in {"completed", "failed"}:
                return

            extracted_chunks: list[str] = []
            extracted_chunks.extend(
                self._extract_text_fragments_from_content_payload(update.get("content"))
            )

            if not extracted_chunks:
                raw_output = update.get("rawOutput")
                if isinstance(raw_output, dict):
                    fallback_text = self._coerce_tool_output_to_text(
                        raw_output.get("output")
                    ) or self._coerce_tool_output_to_text(raw_output.get("error"))
                    if fallback_text:
                        extracted_chunks.append(fallback_text)

            change_preview = self._extract_tool_change_preview(update)
            if change_preview and not any(
                change_preview.strip() in chunk for chunk in extracted_chunks
            ):
                extracted_chunks.append(change_preview)

            body = "\n\n".join(chunk for chunk in extracted_chunks if chunk)
            self._emit_acp_tool_card(update, body)

            return

    def _extract_tool_update_text(self, update: Dict[str, Any]) -> str:
        """Extract raw text payloads from tool_call_update structures."""
        if not isinstance(update, dict):
            return ""

        extracted_chunks = self._extract_text_fragments_from_content_payload(
            update.get("content")
        )

        if not extracted_chunks:
            raw_output = update.get("rawOutput")
            if isinstance(raw_output, dict):
                fallback_text = self._coerce_tool_output_to_text(
                    raw_output.get("output")
                ) or self._coerce_tool_output_to_text(raw_output.get("error"))
                if fallback_text:
                    extracted_chunks.append(fallback_text)

        return "\n\n".join(chunk for chunk in extracted_chunks if chunk)

    def _extract_text_fragments_from_content_payload(self, payload: Any) -> list[str]:
        """Normalize ACP content payloads into textual fragments."""
        fragments: list[str] = []
        if payload is None:
            return fragments

        if isinstance(payload, str):
            text = payload.strip("\n")
            return [text] if text else []

        if isinstance(payload, dict):
            # Filter structured diff payloads (they are too noisy for chat output).
            if str(payload.get("type", "")).strip().lower() == "diff":
                return []

            # Standard ACP content object.
            text = self._extract_text_from_acp_content(payload)
            if text:
                fragments.append(text)

            # Common wrappers: {"type":"content","content":{...}}
            nested_content = payload.get("content")
            if nested_content is not None:
                fragments.extend(
                    self._extract_text_fragments_from_content_payload(nested_content)
                )

            # Common list wrappers.
            for key in ("contents", "items", "parts"):
                if key in payload and isinstance(payload.get(key), list):
                    fragments.extend(
                        self._extract_text_fragments_from_content_payload(
                            payload.get(key)
                        )
                    )

            if not fragments:
                fallback = self._coerce_tool_output_to_text(payload).strip()
                if fallback:
                    fragments.append(fallback)
            return fragments

        if isinstance(payload, list):
            for item in payload:
                fragments.extend(
                    self._extract_text_fragments_from_content_payload(item)
                )
            return fragments

        fallback = self._coerce_tool_output_to_text(payload).strip()
        return [fallback] if fallback else []

    def _extract_text_from_acp_content(self, content: Dict[str, Any]) -> str:
        """Extract text payload from ACP content blocks."""
        if not isinstance(content, dict):
            return ""

        content_type = content.get("type")
        if content_type == "text":
            text = content.get("text")
            return text if isinstance(text, str) else ""

        # Some ACP content wrappers carry textual resource payloads.
        if content_type == "resource":
            resource = content.get("resource") or {}
            text = self._coerce_tool_output_to_text(resource.get("text"))
            return text if isinstance(text, str) else ""

        return ""

    def _coerce_tool_output_to_text(self, value: Any) -> str:
        """Best-effort conversion of ACP tool outputs into displayable text."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip("\n")
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, list):
            parts = [self._coerce_tool_output_to_text(item) for item in value]
            return "\n".join(part for part in parts if part)
        if isinstance(value, dict):
            if str(value.get("type", "")).strip().lower() == "diff":
                return ""
            preferred_keys = (
                "stdout",
                "stderr",
                "diff",
                "patch",
                "unifiedDiff",
                "text",
                "output",
                "message",
                "error",
            )
            parts: list[str] = []
            for key in preferred_keys:
                if key in value:
                    text = self._coerce_tool_output_to_text(value.get(key))
                    if text:
                        parts.append(text)
            if parts:
                return "\n".join(parts)
            try:
                import json

                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)
        return str(value)

    def _forward_agent_text(
        self, text: str, message_metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Send assistant text output to Vicoa.

        ``message_metadata`` rides through unchanged — used to tag a reasoning
        message with ``thinking`` so clients render it as a collapsed card.
        """
        if not text or not self.vicoa_client:
            return
        text = self._sanitize_agent_text(text)
        if not text:
            return

        try:
            response = self.vicoa_client.send_message(
                content=text,
                agent_type=self.config.agent_type,
                agent_instance_id=self.config.agent_instance_id,
                requires_user_input=False,
                message_metadata=message_metadata,
            )

            if response and hasattr(response, "message_id"):
                new_message_id = response.message_id
                if new_message_id != self.last_message_id:
                    self._awaiting_input_requested_for_message_id = None
                self.last_message_id = new_message_id

            if self._awaiting_after_next_agent_output:
                self._set_awaiting_input_state()

        except AuthenticationError:
            # Dead credential (401) — surface it so run() ends the session.
            raise
        except Exception as e:
            self.log(f"[ERROR] Failed to send message to Vicoa: {e}")

    #: ACP ``kind`` enum → a clean, hyphen-free tool name for the card header.
    #: The name MUST stay hyphen-free: the clients' tool-name parser splits the
    #: header on the first " - " (``tool-use-parsing.ts`` / ``_isToolUseMessage``),
    #: so a hyphenated name (e.g. a path like ``pricing-cards.tsx``) would be
    #: severed mid-filename. The (possibly hyphenated) title/path rides in the
    #: arg slot after " - ", which the parser captures whole.
    _ACP_KIND_TO_TOOL = {
        "read": "Read",
        "edit": "Edit",
        "delete": "Delete",
        "move": "Move",
        "search": "Search",
        "execute": "Execute",
        "fetch": "Fetch",
        "think": "Think",
        "switch_mode": "Mode",
    }

    def _acp_tool_header(self, update: Dict[str, Any]) -> str:
        """A "🔧 Using tool: <name>[ - `<detail>`]" header for a tool_call_update.

        The web/mobile clients collapse any message whose content starts with
        this prefix into a tool card, exactly as Claude/Codex tool calls render.
        Crucially the NAME (before the first " - ") must not contain a hyphen,
        or the client splits a filename mid-way — ACP agents put the file path
        in ``title`` (e.g. ``apps/web/…/pricing-cards.tsx``), which is why the
        name comes from the clean ``kind`` enum and the title/path goes in the
        arg slot.
        """
        kind = str(update.get("kind") or "").strip().lower()
        title = str(update.get("title") or "").strip()
        name = self._ACP_KIND_TO_TOOL.get(kind)
        detail = ""
        if name:
            detail = title or self._extract_tool_target_file(update)
        elif title and "-" not in title and "*" not in title:
            # Unknown kind, but a hyphen/asterisk-free title is safe as the name.
            name = title
        else:
            # Unknown kind + a path-like/hyphenated title: keep the name generic
            # so the client never severs a filename; show the title as the arg.
            name = "Tool"
            detail = title or self._extract_tool_target_file(update)
        if detail:
            return f"🔧 Using tool: {name} - `{detail}`"
        return f"🔧 Using tool: {name}"

    def _emit_acp_tool_card(self, update: Dict[str, Any], body: str) -> None:
        """Send a tool_call_update's output as its own collapsed tool card.

        Previously tool output was appended into the shared assistant-narration
        buffer (``_append_assistant_chunk_block``), so raw results — file reads,
        grep hits, "File not found", diffs — landed inline as flat text and
        flooded the transcript. Instead we flush any pending reasoning + narration
        (so this card is its own message and its content leads with the tool
        prefix the clients detect), then forward a "Using tool:" card. The model's
        own narration still streams as normal text; only tool *output* is carded.
        """
        body = (body or "").strip()
        if not body:
            return
        self._flush_assistant_chunk_buffer()
        header = self._acp_tool_header(update)
        self._forward_agent_text(f"{header}\n{body}")

    def _set_agent_status(self, status: str) -> None:
        """Best-effort status update for current agent instance."""
        if not self.vicoa_client or not self.config.agent_instance_id:
            return

        # If the session was closed from another client, an in-flight turn
        # could still try to write AWAITING_INPUT/ACTIVE and re-open the row we
        # were told to shut down. Suppress non-terminal writes once stopping.
        if self._stopping and status.upper() not in WRAPPER_STOP_STATUSES:
            return

        try:
            self.vicoa_client.update_agent_instance_status(
                self.config.agent_instance_id, status
            )
            self.log(f"[Vicoa] Agent status set to {status}")
        except AuthenticationError:
            # Dead credential (401). Let it reach run() so the headless session
            # ends instead of looping on as an invisible orphan.
            raise
        except Exception as e:
            self.log(f"[WARNING] Failed to update agent status to {status}: {e}")

    def _set_awaiting_input_state(self) -> None:
        """Mark session as awaiting input and trigger user-input request."""
        self._awaiting_after_next_agent_output = False
        self._set_agent_status("AWAITING_INPUT")

        if self.vicoa_client and self.last_message_id:
            if self._awaiting_input_requested_for_message_id == self.last_message_id:
                return
            try:
                queued_messages = self.vicoa_client.mark_message_requires_input(
                    self.last_message_id
                )
                self._awaiting_input_requested_for_message_id = self.last_message_id
                for queued in queued_messages:
                    content = queued.get("content") or ""
                    refs = tuple(
                        extract_attachment_refs(queued.get("message_metadata"))
                    )
                    if content or refs:
                        self._ingest_user_message(content, refs)
            except Exception as e:
                self.log(f"[ERROR] Failed to request user input: {e}")

    def _flush_thought_buffer(self) -> None:
        """Flush buffered model reasoning as a collapsed "thinking" card.

        Sent ahead of the narration/answer (it's flushed at the top of
        ``_flush_assistant_chunk_buffer`` and before every tool card), tagged
        with ``message_metadata.thinking`` so clients render it collapsed. Runs
        even when there is no narration this turn, so a reasoning-only turn still
        surfaces its card.
        """
        text = self._thought_chunk_buffer.strip()
        self._thought_chunk_buffer = ""
        if not text:
            return
        self._forward_agent_text(
            text, message_metadata=build_thinking_metadata(self.config.agent_type)
        )

    def _flush_assistant_chunk_buffer(self) -> None:
        """Flush buffered assistant chunks as one user-visible message."""
        # Any pending reasoning goes out first, so the thinking card precedes
        # the answer it reasoned toward.
        self._flush_thought_buffer()
        if not self._assistant_chunk_buffer:
            return

        buffered_text = self._sanitize_agent_text(self._assistant_chunk_buffer)
        self._assistant_chunk_buffer = ""
        self._assistant_chunk_first_update_at = 0.0
        self._assistant_chunk_last_update_at = 0.0
        if buffered_text:
            self._forward_agent_text(buffered_text)

    def _append_assistant_chunk(self, text: str) -> None:
        """Append assistant stream text preserving source chunk boundaries."""
        if not text:
            return
        if not self._should_buffer_assistant_chunk(text):
            return
        if not self._assistant_chunk_buffer:
            self._assistant_chunk_first_update_at = time.time()
        self._assistant_chunk_buffer += text
        self._assistant_chunk_last_update_at = time.time()

    def _append_assistant_chunk_block(self, text: str) -> None:
        """Append a logical message block with spacing when needed."""
        if not text:
            return
        if not self._should_buffer_assistant_chunk(text):
            return
        if not self._assistant_chunk_buffer:
            self._assistant_chunk_first_update_at = time.time()
        if self._assistant_chunk_buffer and not self._assistant_chunk_buffer.endswith(
            "\n\n"
        ):
            if self._assistant_chunk_buffer.endswith("\n"):
                self._assistant_chunk_buffer += "\n"
            else:
                self._assistant_chunk_buffer += "\n\n"
        self._assistant_chunk_buffer += text
        self._assistant_chunk_last_update_at = time.time()

    def _should_flush_assistant_chunk_buffer(self) -> bool:
        """Avoid flushing while a markdown fenced code block is still open."""
        if not self._assistant_chunk_buffer:
            return False

        # If fence count is balanced, flush immediately.
        fence_count = self._assistant_chunk_buffer.count("```")
        if fence_count % 2 == 0:
            return True

        # Otherwise wait for more chunks, but force-flush after a safety window.
        if self._assistant_chunk_first_update_at <= 0:
            return False
        return (
            time.time() - self._assistant_chunk_first_update_at
            >= self._assistant_chunk_force_flush_after_seconds
        )

    def _should_buffer_assistant_chunk(self, text: str) -> bool:
        """Hook for wrappers to suppress streamed output for specific states."""
        return not self._drop_stream_output_until_next_prompt

    #: Recoverable stream errors an agent emits as *reply text* rather than on
    #: the ``session/error`` channel (see ``_TRANSIENT_SESSION_ERRORS``). Cursor
    #: does this: mid-stream it hits ``RetriableError: WritableIterable is
    #: closed``, prints it as an assistant message, then retries and answers
    #: normally — leaving a bogus "Error:" line above a good reply. Matched
    #: against the *whole* trimmed message (single line, ``fullmatch``), so a
    #: real reply that merely mentions the error is never dropped.
    _TRANSIENT_AGENT_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"(?:error:\s*)?retriableerror:[^\n]*", re.IGNORECASE),
        re.compile(r"(?:error:\s*)?writableiterable is closed\.?", re.IGNORECASE),
    )

    @classmethod
    def _is_transient_agent_text(cls, text: str) -> bool:
        """True when a message is *nothing but* a transient stream error the
        agent recovers from on its own. Whole-message match keeps the list from
        swallowing real replies."""
        stripped = (text or "").strip()
        if not stripped:
            return False
        return any(p.fullmatch(stripped) for p in cls._TRANSIENT_AGENT_TEXT_PATTERNS)

    def _sanitize_agent_text(self, text: str) -> str:
        """Remove verbose raw file dumps from assistant-visible output."""
        if not text:
            return ""
        sanitized = FILE_DUMP_BLOCK_PATTERN.sub("", text)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
        if self._is_transient_agent_text(sanitized):
            # The agent surfaced a recoverable stream error as its reply; it
            # retries and answers normally, so forwarding this would put a
            # false failure line in the transcript. Drop it (logged only).
            self.log("[ACP] Suppressed transient agent-text error (agent recovers)")
            return ""
        return sanitized

    def _compact_tool_output(self, text: str) -> str:
        """Keep concise tool output and truncate oversized outputs."""
        sanitized = self._sanitize_agent_text(text)
        if not sanitized:
            return ""

        lines = sanitized.splitlines()
        if (
            len(lines) <= self._tool_output_max_lines
            and len(sanitized) <= self._tool_output_max_chars
        ):
            return sanitized

        preview_lines = lines[: self._tool_output_preview_lines]
        preview = "\n".join(preview_lines)
        if len(preview) > self._tool_output_preview_chars:
            preview = preview[: self._tool_output_preview_chars].rstrip()

        remaining_lines = max(0, len(lines) - len(preview_lines))
        if remaining_lines > 0:
            preview += f"\n\n(Output truncated: {remaining_lines} more lines)"
        else:
            preview += "\n\n(Output truncated)"
        return preview

    def _extract_tool_change_preview(self, update: Dict[str, Any]) -> str:
        """Best-effort extraction of edit patch/diff previews from tool updates."""
        if not isinstance(update, dict):
            return ""

        diff_texts: list[str] = []
        seen: set[str] = set()
        for node in self._iter_nested_dicts(update):
            for key in ("diff", "patch", "unifiedDiff"):
                value = node.get(key)
                if isinstance(value, str):
                    normalized = value.strip()
                    if normalized and normalized not in seen:
                        seen.add(normalized)
                        diff_texts.append(normalized)
                elif isinstance(value, list):
                    text_value = self._coerce_tool_output_to_text(value).strip()
                    if text_value and text_value not in seen:
                        seen.add(text_value)
                        diff_texts.append(text_value)

        if diff_texts:
            rendered: list[str] = []
            for value in diff_texts[:2]:
                if "```" in value:
                    rendered.append(value)
                else:
                    rendered.append(f"```diff\n{value}\n```")
            return "\n\n".join(rendered)

        edit_blocks: list[str] = []
        seen_blocks: set[str] = set()
        for node in self._iter_nested_dicts(update):
            old_value = self._first_non_none(
                node, ("old_string", "oldText", "old", "before")
            )
            new_value = self._first_non_none(
                node, ("new_string", "newText", "new", "after")
            )
            if old_value is None and new_value is None:
                continue

            old_text = self._coerce_tool_output_to_text(old_value)
            new_text = self._coerce_tool_output_to_text(new_value)
            if not old_text and not new_text:
                continue

            diff_block = self._build_diff_block(old_text, new_text)
            if diff_block and diff_block not in seen_blocks:
                seen_blocks.add(diff_block)
                edit_blocks.append(diff_block)

        return "\n\n".join(edit_blocks[:2])

    def _extract_tool_target_file(self, update: Dict[str, Any]) -> str:
        """Best-effort extraction of edited file path from tool payload."""
        if not isinstance(update, dict):
            return ""

        for node in self._iter_nested_dicts(update):
            for key in ("file_path", "filePath", "filepath", "path", "targetPath"):
                value = node.get(key)
                if isinstance(value, str):
                    cleaned = value.strip()
                    if cleaned and len(cleaned) < 2048 and "/" in cleaned:
                        return cleaned
        return ""

    def _iter_nested_dicts(self, value: Any) -> list[Dict[str, Any]]:
        """Collect nested dict nodes from mixed ACP payload structures."""
        nodes: list[Dict[str, Any]] = []
        stack: list[Any] = [value]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                nodes.append(current)
                for item in current.values():
                    if isinstance(item, (dict, list)):
                        stack.append(item)
            elif isinstance(current, list):
                for item in current:
                    if isinstance(item, (dict, list)):
                        stack.append(item)
        return nodes

    def _first_non_none(self, source: Dict[str, Any], keys: tuple[str, ...]) -> Any:
        """Return first non-None value for known key aliases."""
        for key in keys:
            if key in source and source.get(key) is not None:
                return source.get(key)
        return None

    def _build_diff_block(self, old_text: str, new_text: str) -> str:
        """Render a compact unified diff block for edit previews."""
        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()
        if not old_lines and not new_lines:
            return ""

        diff_lines = list(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile="before",
                tofile="after",
                lineterm="",
                n=2,
            )
        )
        if not diff_lines:
            return ""
        return "```diff\n" + "\n".join(diff_lines[:240]) + "\n```"

    #: Agent errors the agent recovers from on its own. They arrive on the
    #: session-error channel like real failures, but the turn still completes
    #: — Cursor emits "RetriableError: WritableIterable is closed" mid-stream
    #: and then answers normally. Surfacing them puts an "Error:" bubble above
    #: a perfectly good reply, which reads as the agent having failed.
    #:
    #: Matched case-insensitively as substrings; keep this list narrow, since
    #: anything added here becomes invisible to the user.
    _TRANSIENT_SESSION_ERRORS: tuple[str, ...] = (
        "retriableerror",
        "writableiterable is closed",
    )

    @classmethod
    def _is_transient_session_error(cls, message: str) -> bool:
        lowered = (message or "").lower()
        return any(needle in lowered for needle in cls._TRANSIENT_SESSION_ERRORS)

    def _handle_session_error(self, params: Dict[str, Any]) -> None:
        """Handle session error from agent."""
        error = params.get("error", {})
        message = error.get("message", "Unknown error")
        self.log(f"[ERROR] Agent session error: {message}")

        if self._is_transient_session_error(message):
            # Logged above, not shown. The agent retries and the turn still
            # produces its answer, so a visible error would be a lie.
            self.log("[ACP] Suppressed transient session error (agent recovers)")
            return

        if self.vicoa_client:
            try:
                self.vicoa_client.send_message(
                    content=f"Error: {message}",
                    agent_type=self.config.agent_type,
                    agent_instance_id=self.config.agent_instance_id,
                    requires_user_input=False,
                )
            except Exception as e:
                self.log(f"[ERROR] Failed to send error to Vicoa: {e}")

    def _handle_session_idle(self, params: Dict[str, Any]) -> None:
        """Handle session idle notification from agent."""
        self.log("[ACP] Agent session is idle")

        self._flush_assistant_chunk_buffer()
        self._set_awaiting_input_state()

    def _handle_late_acp_response(self, request_id: int, response: ACPResponse) -> None:
        """Handle a response that arrived after its local timeout. Subclasses can override."""
        self.log(
            f"[ACP] Late response received for request {request_id} (base handler: no-op)"
        )

    def _handle_acp_error(self, line: str) -> None:
        """Handle stderr output from agent.

        Args:
            line: stderr line
        """
        # Not forwarded to the transcript (stderr is mostly logs), but retained
        # per-turn so ``_report_empty_turn`` can surface whatever the agent last
        # printed as the likely cause when a turn produces no other output.
        if line and line.strip():
            self._turn_stderr.append(line.rstrip())

    def _cleanup(self, final_status: Optional[str] = None) -> None:
        """Cleanup before exit."""
        self.running = False

        # Stop heartbeating before we write the terminal status, so an in-flight
        # beat can't make a finished session look freshly alive. getattr because
        # _cleanup runs from a finally and may see a partially-built wrapper.
        heartbeat = getattr(self, "_heartbeat", None)
        if heartbeat is not None:
            try:
                heartbeat.stop()
            except Exception as exc:
                self.log(f"[ERROR] Heartbeat stop failed: {exc}")

        # Stop WS subscriber first so the callback thread can't try to push
        # into the queue (or call into vicoa_client) while the rest tears
        # down. Daemon thread will be reaped on process exit even if join
        # times out.
        if self._ws_client is not None:
            try:
                self._ws_client.stop()
            except Exception as exc:
                self.log(f"[ERROR] WS client stop failed: {exc}")
        if self._ws_thread is not None and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=5.0)

        # Stop ACP client
        if self.acp:
            self.log("[ACP] Stopping ACP client")
            self.acp.stop()

        # Mark the instance with a terminal status before closing the session.
        if self.vicoa_client and self.config.agent_instance_id:
            try:
                if final_status == "COMPLETED":
                    self.vicoa_client.end_session(self.config.agent_instance_id)
                elif final_status in {"FAILED", "KILLED"}:
                    self.vicoa_client.update_agent_instance_status(
                        self.config.agent_instance_id, final_status
                    )
            except Exception as e:
                self.log(
                    f"[ERROR] Failed to finalize Vicoa session with status {final_status}: {e}"
                )

        # Close Vicoa client
        if self.vicoa_client:
            try:
                self.vicoa_client.close()
            except Exception as e:
                self.log(f"[ERROR] Failed to close Vicoa client: {e}")

        # Close log file
        if self.debug_log_file:
            try:
                self.log(f"=== {self.config.agent_type} Wrapper Log Ended ===")
                self.debug_log_file.flush()
                self.debug_log_file.close()
            except Exception:
                pass

    def _log_dir_name(self) -> str:
        """Filesystem-safe ``<slug>_wrapper`` dir name for this agent's logs.

        Prefers the catalog id ("gemini", "cursor", …), else the display
        ``agent_type`` lowercased, then collapses any run of non-alphanumerics
        to a single "_". Keeps ``~/.vicoa/`` log folders uniformly lowercase and
        space-free — the display name would otherwise yield "Gemini CLI_wrapper"
        / "Copilot CLI_wrapper" next to the lowercase "codex_native" /
        "claude_headless" ones.
        """
        raw = self.config.catalog_agent_id or self.config.agent_type
        slug = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_") or "acp"
        return f"{slug}_wrapper"

    def _init_logging(self) -> None:
        """Initialize debug logging."""
        try:
            log_dir = Path.home() / ".vicoa" / self._log_dir_name()
            log_dir.mkdir(exist_ok=True, parents=True)

            log_file_path = log_dir / f"{self.config.agent_instance_id}.log"
            self.debug_log_file = open(log_file_path, "w")

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            milliseconds = int((time.time() % 1) * 1000)
            self.log(
                f"=== {self.config.agent_type} Wrapper - {timestamp}.{milliseconds:03d} ==="
            )
        except Exception as e:
            print(f"Failed to create debug log file: {e}", file=sys.stderr)

    def _init_vicoa_client(self) -> None:
        """Initialize Vicoa SDK client."""
        if not self.config.api_key:
            raise ValueError("Vicoa API key is required")

        self.vicoa_client = VicoaClient(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            max_retries=1440,
            backoff_factor=1.0,
            backoff_max=60.0,
            log_func=self.log,
        )

    def log(self, message: str) -> None:
        """Write to debug log file."""
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
