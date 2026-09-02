#!/usr/bin/env python3
"""
Headless Claude Code Integration for Vicoa

This module provides a headless version of Claude Code that integrates with the Vicoa SDK,
allowing human users to interact with Claude through the web dashboard while Claude runs
autonomously using the Claude Agent SDK.

See ``docs/design/mcp-headless-refactor.md`` for the architectural overview.

Submodules (sibling files in this package):

* ``auq.py`` — AskUserQuestion wire format + Future-based reply registry.
* ``permission.py`` — permission cache and prompt rendering.
* ``control_command.py`` — control-command parser.
"""

import argparse
import asyncio
import base64
import logging
import os
import signal
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Optional, List, Dict, Union, cast

from vicoa.attachments import (
    AttachmentRef,
    attachment_note,
    attachments_dir,
    extract_attachment_refs,
    is_image_mime,
    save_attachment,
    unavailable_note,
)
from vicoa.sdk.async_client import AsyncVicoaClient
from vicoa.session_ws_client import SessionMessagesWsClient
from vicoa.utils import derive_ws_url, get_project_path
from integrations.headless.session_lifecycle import instance_update_requests_stop
from integrations.utils.heartbeat import AsyncSessionHeartbeat
from integrations.headless.format_tools import format_tool_use
from integrations.headless import auq
from integrations.headless import permission as permission_module
from integrations.headless import control_command
from integrations.headless import usage as usage_mod
from integrations.headless.usage import UsageState
from integrations.headless.claude_usage_fetcher import (
    fetch_claude_usage,
    read_claude_oauth_token,
)
from integrations.headless.claude_model_catalog import build_claude_available_models
from integrations.headless.permission import (
    format_dict_as_markdown as _format_dict_as_markdown,  # re-exported for tests
)
from integrations.headless.subagent import SubAgentTracker, build_metadata
from integrations.headless.thinking import build_thinking_metadata

try:
    from claude_agent_sdk import (
        ClaudeSDKClient,
        ClaudeAgentOptions,
        AssistantMessage,
        UserMessage,
        SystemMessage,
        ResultMessage,
        TextBlock,
        ThinkingBlock,
        ToolUseBlock,
        ToolResultBlock,
        CLINotFoundError,
        CLIJSONDecodeError,
        ProcessError,
        PermissionMode,
        PermissionResultAllow,
        PermissionResultDeny,
        ThinkingConfigAdaptive,
        ThinkingConfigEnabled,
        ThinkingConfigDisabled,
        ToolPermissionContext,
        RateLimitEvent,
        RateLimitInfo,
        TaskStartedMessage,
        TaskNotificationMessage,
    )
except ImportError as e:
    print(
        "Error: Claude Agent SDK not found. Please install it with: pip install claude-agent-sdk"
    )
    print(f"Import error: {e}")
    sys.exit(1)

from vicoa.sdk.exceptions import TimeoutError as VicoaTimeoutError


# Re-exported for backward compatibility with tests that import the symbol
# directly from this module.
__all__ = ["HeadlessClaudeRunner", "main", "_format_dict_as_markdown"]


# Maximum time the AskUserQuestion callback waits for a user reply before it
# gives up and returns Deny. 24 hours mirrors the prior MCP-path behaviour.
ASK_USER_QUESTION_TIMEOUT_SECONDS = 24 * 60 * 60

# Minimum spacing between out-of-band Claude plan-usage fetches. Rate-limit
# windows move slowly, so once per minute is plenty and keeps the vendor API
# untaxed.
_CLAUDE_LIMITS_FETCH_INTERVAL = 60.0

# How long to wait for the aborted turn's closing ``ResultMessage`` after an
# interrupt before forcing the foreground turn closed (see
# ``_await_foreground_turn_close``). The CLI normally emits it within a second
# of honouring the interrupt; the budget only exists so a CLI that never
# closes the turn can't wedge the session. The stream reader itself keeps
# running either way — this only bounds how long the run loop stays parked.
_INTERRUPT_RESULT_TIMEOUT = 15.0

# Status-only watchdog (``_run_status_watchdog``): when autonomous work
# (background sub-agents, CLI-initiated turns) goes silent for this long with
# no human reply pending, settle the *status row* to AWAITING_INPUT so the
# dashboard doesn't show a spinner forever. Unlike the old
# ``_BACKGROUND_TASK_IDLE_TIMEOUT`` give-up this NEVER stops stream
# consumption — the reader stays on the stream, and any later output simply
# re-opens an autonomous turn and re-marks the session ACTIVE.
_STATUS_SETTLE_IDLE_SECONDS = 600.0
_STATUS_WATCHDOG_INTERVAL = 30.0

# Cadence for the message-reconcile backstop (``_run_reconcile_backstop``).
# Every user message reaches the runner over ONE fire-and-forget path (the
# backend→server ``post_broadcast`` bridge — best-effort, never raises), and
# the runner opted out of polling (``poll_for_reply=False``). A dropped push is
# silent, stranding either a pending AUQ/permission reply or the first message
# to a just-woken session. Re-issuing the WS catch-up on this cadence — while
# idle or a reply is pending — recovers it within one tick; the WS
# ``CatchUpBuffer`` dedupes already-delivered rows, so it never double-delivers.
# 10 s trades a small worst-case recovery latency against near-zero idle cost.
_RECONCILE_INTERVAL = 10.0

# Max bytes the SDK's subprocess transport will buffer for a *single* CLI
# stdout message (one line of stream-json). The SDK default is 1 MiB, but a
# single message embeds an entire tool result — a large file Read, a big
# Bash/grep output, an MCP result, or base64 image/attachment blocks — so
# 1 MiB is easily exceeded (a single hi-res screenshot base64 alone clears it).
# When it is, the SDK raises ``CLIJSONDecodeError`` ("JSON message exceeded
# maximum buffer size") and the turn dies. Bump it well clear of any realistic
# message. Env-overridable so it can be retuned without a redeploy.
_CLAUDE_STDOUT_MAX_BUFFER_SIZE = int(
    os.environ.get("VICOA_CLAUDE_MAX_BUFFER_SIZE", str(50 * 1024 * 1024))
)
# Raw-byte ceiling for delivering a file inline as a base64 block. Base64
# inflates by ~4/3, so 20MB encodes to ~27MB — safely under Anthropic's 32MB
# per-request limit. Larger files are handed to the agent by path instead.
_MAX_INLINE_ATTACHMENT_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class InboundUserMessage:
    """A dequeued user message plus any image attachments riding its metadata."""

    content: str
    attachments: tuple[AttachmentRef, ...] = ()
    message_id: Optional[str] = None


# Human-readable labels for the SDK's ``RateLimitType`` literal. Keys mirror
# ``claude_agent_sdk/types.py:1181`` — keep in sync if the SDK adds new windows.
_RATE_LIMIT_WINDOW_LABELS = {
    "five_hour": "5-hour",
    "seven_day": "7-day",
    "seven_day_opus": "7-day Opus",
    "seven_day_sonnet": "7-day Sonnet",
    "overage": "overage",
}


def _rate_limit_utilization(info: RateLimitInfo) -> Optional[float]:
    """Utilization to feed into the usage-window projection.

    The SDK doesn't always attach a utilization figure to the terminal
    ``"rejected"`` event, but a rejection IS 100% used by definition — without
    this fallback, ``claude_window()`` drops the window entirely and
    ``rate_limited_until`` never gets set server-side even though the session
    is genuinely blocked (and the chat banner below says so).
    """
    utilization = info.utilization
    if utilization is None and info.status == "rejected":
        return 1.0
    return utilization


def _format_rate_limit_event(event: "RateLimitEvent") -> Optional[str]:
    """Format a Claude SDK ``RateLimitEvent`` for display in Vicoa.

    The CLI emits this event on every status *transition*, including
    transitions back to ``"allowed"`` — those are not user-visible problems
    and would otherwise show up in the dashboard as a raw dataclass repr
    (the reported bug). We suppress them and only forward warnings and
    rejections, formatted as readable Markdown.

    Returns ``None`` when the event should be suppressed. This is pure
    formatting — repeat-warning dedupe lives in ``_RateLimitNoticeGate``.
    """
    info = event.rate_limit_info
    status = info.status
    if status == "allowed":
        return None

    window_label = (
        _RATE_LIMIT_WINDOW_LABELS.get(info.rate_limit_type, info.rate_limit_type)
        if info.rate_limit_type
        else "rate"
    )

    if info.resets_at:
        try:
            reset_str = f"resets {datetime.fromtimestamp(info.resets_at).isoformat(sep=' ', timespec='minutes')}"
        except (OSError, ValueError, OverflowError):
            reset_str = f"resets at epoch {info.resets_at}"
    else:
        reset_str = "reset time unknown"

    if status == "allowed_warning":
        headline = f"⚠️ Approaching {window_label} rate limit"
    elif status == "rejected":
        headline = f"🛑 {window_label} rate limit reached"
    else:
        # Future-proofing for any new RateLimitStatus literals.
        headline = f"ℹ️ {window_label} rate limit status: {status}"

    parts = [headline]
    if info.utilization is not None:
        parts.append(f"{int(info.utilization * 100)}% used")
    parts.append(reset_str)
    if status == "rejected" and info.overage_disabled_reason:
        parts.append(f"overage disabled: {info.overage_disabled_reason}")

    return " · ".join(parts)


class _RateLimitNoticeGate:
    """Decide which rate-limit events deserve a chat notice.

    Once utilization enters warning territory the CLI re-reports the window
    on effectively every turn, so forwarding each ``allowed_warning`` event
    would repeat the same ⚠️ line for days (the live meter on
    ``instance_metadata.usage`` already tracks the exact number). Instead,
    each window (5-hour, 7-day, …) gets at most one notice per escalation
    step — the first crossing of 75%, 90% and 95% — per reset period. A
    change in ``resets_at`` marks a new period and re-arms all the steps,
    so after a reset the next climb past 75% notifies again.

    ``rejected`` events always pass: when the CLI refuses to run, the user
    needs to see why on every attempt.
    """

    _STEPS = (95, 90, 75)

    def __init__(self) -> None:
        # window type -> (resets_at defining the period, highest step notified)
        self._notified: dict[str, tuple[Optional[int], int]] = {}

    def text_for(self, event: "RateLimitEvent") -> Optional[str]:
        """Format ``event`` for chat, or return None when it should stay quiet."""
        text = _format_rate_limit_event(event)
        if text is None:
            return None
        info = event.rate_limit_info
        if info.status == "rejected":
            return text
        key = info.rate_limit_type or "unknown"
        step = self._step(info.utilization)
        last = self._notified.get(key)
        if last is not None and last[0] == info.resets_at and last[1] >= step:
            return None
        self._notified[key] = (info.resets_at, step)
        return text

    @classmethod
    def _step(cls, utilization: Optional[float]) -> int:
        # Step 0 covers warnings below 75% or without a utilization figure:
        # still worth one notice per period, then quiet until 75% crosses.
        if utilization is None:
            return 0
        pct = utilization * 100
        for threshold in cls._STEPS:
            if pct >= threshold:
                return threshold
        return 0


def setup_logging(session_id: str, console_output: bool = True, debug: bool = False):
    """Setup logging with session-specific log file.

    Args:
        session_id: Session ID for the log file name
        console_output: Whether to also log to console (default True for standalone, False for webhook)
        debug: If True, set the module logger to DEBUG so logger.debug(...)
            calls (e.g. "User message (not forwarding): ...") actually
            reach the file handler. Without this they're filtered at the
            logger level — the file handler being set to DEBUG isn't
            enough because the logger gate applies first.
    """
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    logger.handlers.clear()

    vicoa_dir = Path.home() / ".vicoa"
    claude_headless_dir = vicoa_dir / "claude_headless"
    claude_headless_dir.mkdir(exist_ok=True, parents=True)

    log_file = claude_headless_dir / f"{session_id}.log"

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler: Optional[logging.Handler] = None
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        logger.info(f"Logging to: {log_file}")

    # Route the session WebSocket client's logger into the *same per-session
    # log file* (never the UI). Its reconnect/drop/refetch lines live under the
    # ``vicoa.session_ws_client`` namespace and otherwise vanish — a lost
    # broadcast, a reconnect storm, or a wedged catch-up left no trace in the
    # session log, which is exactly what made the "idle-session message
    # swallow" so hard to see. Handlers are attached directly (not via root)
    # and the logger is de-propagated so nothing double-prints elsewhere.
    ws_logger = logging.getLogger("vicoa.session_ws_client")
    ws_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    ws_logger.handlers.clear()
    ws_logger.addHandler(file_handler)
    if console_handler is not None:
        ws_logger.addHandler(console_handler)
    ws_logger.propagate = False

    if debug:
        logger.info("DEBUG logging enabled")

    return logger


class HeadlessClaudeRunner:
    """Headless Claude Code runner that integrates with Vicoa SDK."""

    def __init__(
        self,
        vicoa_api_key: str,
        session_id: str,
        vicoa_base_url: str = "https://agents.vicoa.ai",
        initial_prompt: Optional[str] = None,
        extra_args: Optional[Dict[str, Optional[str]]] = None,
        permission_mode: Optional[PermissionMode] = None,
        allowed_tools: Optional[List[str]] = None,
        disallowed_tools: Optional[List[str]] = None,
        cwd: Optional[Union[str, Path]] = None,
        console_output: bool = True,
        agent_name: str = "Claude Code",
        enable_thinking: bool = True,
        model: Optional[str] = None,
        thinking_effort: Optional[str] = None,
        debug: bool = False,
        is_resuming: bool = False,
    ):
        self.vicoa_api_key = vicoa_api_key
        self.vicoa_base_url = vicoa_base_url
        self.initial_prompt = initial_prompt
        self.session_id = session_id
        self.last_message_id: Optional[str] = None
        self.cwd = str(cwd) if cwd else os.getcwd()
        self.agent_name = agent_name
        self.project_path = get_project_path(self.cwd)

        self.enable_thinking = enable_thinking
        self.model = model
        # When thinking_effort is passed it takes precedence over the legacy
        # enable_thinking boolean (plan §3.6 dual-write contract). `off`
        # maps to ThinkingConfigDisabled; everything else to adaptive thinking.
        self.thinking_effort = thinking_effort
        self.permission_mode = permission_mode
        self.allowed_tools = allowed_tools
        self.disallowed_tools = disallowed_tools
        self.extra_args = extra_args
        self.debug = debug

        setup_logging(session_id, console_output=console_output, debug=debug)
        self.logger = logging.getLogger(__name__)

        # Flips to True after the first successful ``connect()``. On reconnect
        # the SDK's process-internal registry still owns the session_id, so
        # ``_build_claude_options`` must emit ``resume=`` instead of
        # ``session_id=`` — otherwise the CLI dies with
        # "Session ID … is already in use" and the mobile mid-session model /
        # effort toggle reports "Failed to change model".
        self._initial_connect_done = False

        # Resuming a session that already has a transcript on this machine.
        # Same requirement as a reconnect — the transcript at
        # ~/.claude/projects/<cwd-slug>/<session_id>.jsonl already owns the id,
        # so a cold start must also emit ``resume=``. Keyed separately from
        # ``_initial_connect_done`` because that one answers "have I connected
        # before in *this process*", which is always False on a relaunch.
        self.is_resuming = is_resuming

        self.claude_options = self._build_claude_options()

        self.vicoa_client: Optional[AsyncVicoaClient] = None
        self.claude_client: Optional[ClaudeSDKClient] = None
        self._heartbeat: Optional[AsyncSessionHeartbeat] = None
        self.running = True
        # Set when the session is closed from another client; suppresses the
        # turn-end AWAITING_INPUT write so a racing turn can't re-open the row.
        self._stopping = False
        self.conversation_started = False
        self.interrupt_requested = False

        # Live context-window + rate-limit usage, stamped onto
        # instance_metadata.usage. ``_usage_last_core`` dedupes redundant
        # PATCHes (each carries a websocket broadcast).
        self._usage = UsageState()
        self._usage_last_core: Optional[dict] = None
        # Out-of-band Claude plan-usage (Session/Weekly) snapshot fetch. The
        # SDK only emits RateLimitEvents on a status transition, so we poll the
        # OAuth usage API to show windows even when comfortably under the limit.
        # Throttled + non-blocking; ``_limits_fetch_task`` keeps a reference so
        # the background task isn't GC'd mid-flight.
        self._last_limits_fetch = 0.0
        self._limits_fetch_task: "Optional[asyncio.Task[None]]" = None
        # Chat-notice dedupe for rate-limit warnings: one ⚠️ per escalation
        # step (75/90/95%) per window per reset period, rejections always
        # shown. See ``_RateLimitNoticeGate``.
        self._rate_limit_gate = _RateLimitNoticeGate()

        self._user_message_queue: asyncio.Queue[InboundUserMessage] = asyncio.Queue()

        # Cross-channel dedupe: the same user message can arrive both via the
        # WS queue (``_route``) and via the REST ``already_queued`` remainder
        # returned by ``mark_message_requires_input`` (``_enqueue_already_queued``).
        # Bounded so long-running sessions don't leak memory; 1024 comfortably
        # covers any turn's worth of in-flight message ids.
        self._seen_user_message_ids: set[str] = set()
        self._seen_user_message_order: deque[str] = deque(maxlen=1024)

        # Message ids cancelled mid-turn. Fully wired in Task B5 (interrupt
        # handling); initialised here (harmless, always empty pre-B5) so
        # ``_enqueue_already_queued`` can reference it now.
        self._cancelled_message_ids: set[str] = set()

        # User-message transport: session-scoped /ws connection, mirroring
        # ``codex_native.py``. ``SessionMessagesWsClient`` runs a sync
        # ``websocket`` reconnect loop on a background thread; its callback
        # bridges into the asyncio loop captured below via
        # ``run_coroutine_threadsafe``. Replaces the legacy SSE per-instance
        # stream — the WS client handles ``fetch_messages_request`` catch-up
        # itself, so there's no separate ``get_pending_messages`` drain.
        self._ws_client: Optional[SessionMessagesWsClient] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Out-of-band queue for settings control commands (model / effort /
        # permission_mode). The ``_route`` callback enqueues without awaiting
        # the multi-second reconnect; a dedicated worker drains and
        # dispatches in order. Without this, back-to-back gear-pill changes
        # would each block the inbound message path on the SDK reconnect,
        # serializing what should be quick UX updates behind the slowest
        # change. Interrupts bypass the queue — see
        # ``_maybe_route_control_command``.
        self._control_command_queue: asyncio.Queue[str] = asyncio.Queue()
        self._control_worker_task: Optional[asyncio.Task[None]] = None

        # Backstop task that re-fetches the persisted message tail while the
        # session is idle or a reply is outstanding, so a message whose realtime
        # broadcast the fire-and-forget bridge dropped still lands (a stranded
        # AUQ/permission reply, or the lost first message to a just-woken
        # session). See ``_run_reconcile_backstop`` and ``_RECONCILE_INTERVAL``.
        self._reconciler_task: Optional[asyncio.Task[None]] = None

        # True while the runner is blocked in ``_wait_for_user_input`` (idle,
        # between turns). The reconcile backstop reads it to decide whether a
        # dropped inbound message has anything else to recover it — see
        # ``_run_reconcile_backstop``.
        self._awaiting_input: bool = False

        # The asyncio task running ``run()``. Captured so the SIGTERM
        # handler can cancel it, which routes shutdown through the normal
        # ``finally`` cleanup (end_session → status COMPLETED) instead of
        # the process being killed outright.
        self._main_task: Optional[asyncio.Task[Any]] = None

        # Permission cache. The exposed ``_permission_state`` dict is the
        # SAME object the cache mutates, so tests that inspect it (and the
        # cache's own reads/writes) stay in sync.
        self._permission_state: Dict[str, Any] = {}
        self._permission_cache = permission_module.PermissionCache(
            self._permission_state
        )

        # AskUserQuestion futures resolved by the SSE listener. See
        # ``integrations/headless/auq.py`` for why this is a registry and
        # not the polling path it used to be.
        self._auq_registry = auq.AskUserQuestionRegistry()

        # Permission-prompt futures, same shape as the AUQ registry.
        # Replaces the long-polling ``send_message(requires_user_input=True)``
        # call inside ``_handle_permission_prompt`` — fixes the §2c
        # double-delivery that caused "Allow once" to leak as the next turn's
        # user input (session ``269d5bf3-…``) and removes the §2g cursor race
        # for this call too.
        self._permission_registry = permission_module.PermissionReplyRegistry()

        # Serializes outgoing agent POSTs from this process. Eliminates the
        # in-process source of the §2g cursor race — every ``send_to_vicoa``
        # POST completes before the next one starts, so two concurrent
        # AssistantMessages can no longer fight over
        # ``instance.last_read_message_id``. We *don't* hold this around
        # long-polling permission prompts (which call
        # ``send_message(requires_user_input=True)`` and can block for 24 h);
        # the AUQ path uses ``requires_user_input=False`` so holding the lock
        # there is cheap.
        self._send_lock: asyncio.Lock = asyncio.Lock()

        # Tracks the Claude SDK's internal session_id seen on init SystemMessages.
        # A change between turns would mean the SDK created a new conversation —
        # which is what the old code mistakenly warned about on every turn.
        self._last_sdk_session_id: Optional[str] = None

        # Labels Task/Agent tool launches on the main stream so child SDK
        # messages (stamped with matching ``parent_tool_use_id``) can be
        # tagged with ``subagent`` metadata instead of falling through flat.
        # See ``integrations.headless.subagent`` and ``run_conversation_turn``.
        self._subagent_tracker = SubAgentTracker()

        # ``task_id``s of sub-agents the CLI has announced (``task_started``)
        # but not yet reported on (``task_notification``). Non-empty when a
        # foreground ``ResultMessage`` lands means the agent launched a
        # background sub-agent (``run_in_background: true``) and finished its
        # own turn without waiting — the awaiting-input settle is then
        # deferred to the autonomous close (``_settle_after_autonomous_turn``).
        self._pending_background_tasks: set[str] = set()

        # ------------------------------------------------------------------
        # Session-lifetime stream reader + event-derived turn state.
        #
        # The SDK stream is consumed by ONE reader task from connect to
        # disconnect (``_run_stream_reader``), never per turn. Turn state is
        # a FIFO of open turns: ``run_conversation_turn`` appends
        # "foreground" before ``query()``; CLI-initiated output with no open
        # turn (a background sub-agent's report turn) appends "autonomous".
        # A ``ResultMessage`` closes the oldest entry; one with no open turn
        # is dropped as stale. This is what prevents the SDK's 100-slot
        # buffer from ever filling (which backpressured the CLI's stdout
        # pipe and stalled sub-agents mid-work) and stops a stale Result
        # from terminating the next user turn early (the lag-by-one bug).
        # Modeled on Paseo's ``runQueryPump`` / autonomous-turn design.
        # ------------------------------------------------------------------
        self._open_turns: deque[str] = deque()
        # Set by the reader when it closes the current foreground turn;
        # ``run_conversation_turn`` parks on it instead of reading the stream.
        self._foreground_turn_done: Optional[asyncio.Event] = None
        # Captured by the reader AT close time: whether background sub-agents
        # were still outstanding when the foreground result landed, i.e. the
        # settle belongs to the later autonomous close. The run loop must not
        # re-derive this from ``_pending_background_tasks`` after waking — the
        # reader may have processed the notifications (and settled) already.
        self._foreground_settle_deferred: bool = False
        self._stream_reader_task: Optional[asyncio.Task[None]] = None
        # The client instance the running reader serves. A reconnect swaps
        # ``claude_client``; the identity check keeps a retiring reader from
        # being mistaken for the live one (mirrors Paseo's activeQuery guard).
        self._reader_client: Optional[Any] = None
        # Keeps the stream-recovery task (reconnect after a died stream)
        # referenced so it isn't GC'd mid-flight.
        self._stream_recovery_task: Optional[asyncio.Task[None]] = None
        self._status_watchdog_task: Optional[asyncio.Task[None]] = None
        # loop.time() of the last SDK message; read by the status watchdog.
        self._last_stream_activity: float = 0.0

    def _build_claude_options(self) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions with current configuration.

        Permission prompts and AskUserQuestion answers are handled in-process
        via the ``can_use_tool`` SDK callback. We no longer spawn the
        ``vicoa mcp`` STDIO server from this path — see
        ``docs/design/mcp-headless-refactor.md``.
        """
        # `thinking_effort` (new in plan §3.6) wins over `enable_thinking` if
        # both are present — the SDK's adaptive config carries an `effort`
        # tier the agent uses instead of a fixed budget.
        thinking_config: (
            ThinkingConfigAdaptive | ThinkingConfigEnabled | ThinkingConfigDisabled
        )
        effort_for_options: Optional[str] = None
        if self.thinking_effort is not None:
            if self.thinking_effort == "off":
                thinking_config = ThinkingConfigDisabled(type="disabled")
                self.logger.info("Building options with thinking_effort=off (disabled)")
            else:
                thinking_config = ThinkingConfigAdaptive(type="adaptive")
                effort_for_options = self.thinking_effort
                self.logger.info(
                    "Building options with thinking_effort=%s (adaptive)",
                    self.thinking_effort,
                )
        elif self.enable_thinking:
            thinking_config = ThinkingConfigEnabled(type="enabled", budget_tokens=1024)
            self.logger.info(
                "Building options with thinking enabled (budget_tokens=1024)"
            )
        else:
            thinking_config = ThinkingConfigDisabled(type="disabled")
            self.logger.info("Building options with thinking disabled")

        # Pass Vicoa's session_id through to the Claude SDK so the transcript
        # at ~/.claude/projects/<cwd>/<session_id>.jsonl shares the same id
        # the dashboard shows. The SDK requires a valid UUID and reads this
        # at connect() time; if Vicoa's id isn't a UUID for some reason
        # (shouldn't happen on current code paths but is cheap to guard),
        # let the SDK auto-generate one rather than crash.
        sdk_session_id: Optional[str] = None
        if self.session_id:
            try:
                uuid.UUID(self.session_id)
                sdk_session_id = self.session_id
            except ValueError:
                self.logger.warning(
                    "session_id %r is not a valid UUID; Claude SDK will "
                    "generate its own and transcript filenames won't match",
                    self.session_id,
                )

        # On reconnect *or* resume, swap session_id → resume. See ``__init__``:
        # in both cases the id is already owned (by the SDK's in-process
        # registry, or by the on-disk transcript), and passing session_id=
        # would fail with "Session ID … is already in use".
        resume_session_id: Optional[str] = None
        if (self._initial_connect_done or self.is_resuming) and (
            sdk_session_id is not None
        ):
            resume_session_id = sdk_session_id
            sdk_session_id = None

        options_kwargs: Dict[str, Any] = dict(
            permission_mode=cast(PermissionMode, self.permission_mode)
            if self.permission_mode
            else None,
            allowed_tools=self.allowed_tools or [],
            disallowed_tools=self.disallowed_tools or [],
            can_use_tool=self._handle_tool_use,
            cwd=self.cwd,
            extra_args=self.extra_args or {},
            system_prompt={"type": "preset", "preset": "claude_code"},
            setting_sources=["user", "project", "local"],
            thinking=thinking_config,
            session_id=sdk_session_id,
            resume=resume_session_id,
            max_buffer_size=_CLAUDE_STDOUT_MAX_BUFFER_SIZE,
        )
        if self.model:
            options_kwargs["model"] = self.model
        if effort_for_options is not None:
            options_kwargs["effort"] = effort_for_options
        return ClaudeAgentOptions(**options_kwargs)

    # ------------------------------------------------------------------
    # Tool-use callback (replaces the MCP `approve` tool)
    # ------------------------------------------------------------------

    async def _handle_tool_use(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        context: "ToolPermissionContext",
    ) -> Union[PermissionResultAllow, PermissionResultDeny]:
        """``can_use_tool`` callback invoked before every Claude tool execution.

        Dispatches on tool name:

        * ``AskUserQuestion`` → register a Future, push the questions to
          Vicoa, await the future, return ``updated_input`` so Claude closes
          the tool_use → tool_result loop.
        * everything else → unified permission prompt with session-scoped
          caching.
        """
        try:
            if tool_name == "AskUserQuestion":
                return await self._handle_ask_user_question(tool_input, context)
            return await self._handle_permission_prompt(tool_name, tool_input)
        except VicoaTimeoutError as exc:
            # Logged at WARN so future stale-cursor / actual-timeout cases
            # are diagnosable.
            self.logger.warning("can_use_tool for %s timed out: %s", tool_name, exc)
            return PermissionResultDeny(message="Permission request timed out")
        except Exception as exc:
            self.logger.exception(
                "can_use_tool callback raised for %s; denying", tool_name
            )
            return PermissionResultDeny(message=f"Permission callback failed: {exc}")

    async def _handle_ask_user_question(
        self,
        tool_input: Dict[str, Any],
        context: "ToolPermissionContext",
    ) -> Union[PermissionResultAllow, PermissionResultDeny]:
        """Intercept Claude's built-in AskUserQuestion and return structured answers.

        Flow:

        1. Register an ``asyncio.Future`` in the AUQ registry keyed by a
           freshly minted ``request_id``.
        2. POST the structured prompt to Vicoa with
           ``requires_user_input=False``. The dashboard renders the picker
           from ``message_metadata.ask_user_question`` and echoes the user's
           selection back as a control reply on the WS subscriber.
        3. Bind the future to the returned ``message_id`` too (for clients
           that echo the prompt id instead of ``request_id``).
        4. Await the future. ``_route`` (driven by the WS callback) resolves it when the
           control reply arrives.
        5. Reshape the answers onto Claude's ``{question_text: answer}``
           schema and return ``updated_input``.

        See ``auq.AskUserQuestionRegistry`` for the rationale (no polling →
        no §2g cursor race).
        """
        if not self.vicoa_client or not self.session_id:
            return PermissionResultDeny(message="Vicoa client not initialized")

        questions = tool_input.get("questions") or []
        if not isinstance(questions, list) or not questions:
            # Nothing structured to ask — allow with original input so Claude
            # can surface its own error if the schema is malformed.
            return PermissionResultAllow(updated_input=tool_input)

        request_id = uuid.uuid4().hex
        future = self._auq_registry.create(request_id)
        metadata = auq.build_metadata(
            questions=questions,
            prompt=format_tool_use("AskUserQuestion", tool_input),
            tool_use_id=getattr(context, "tool_use_id", None),
            request_id=request_id,
        )

        try:
            # The lock keeps this POST and any concurrent ``send_to_vicoa``
            # POSTs strictly serialized — eliminates the in-process race even
            # though we no longer poll in this callback.
            #
            # ``requires_user_input=True, poll_for_reply=False`` keeps the
            # semantic side of the message intact (push/email/SMS
            # notifications, dashboard "question" rendering) while opting
            # out of the SDK's polling loop — the registry + WS subscriber resolves
            # the reply instead. Without the explicit ``poll_for_reply=False``
            # the SDK would default to polling, re-introducing §2g.
            async with self._send_lock:
                response = await self.vicoa_client.send_message(
                    agent_instance_id=self.session_id,
                    content=auq.ASK_USER_QUESTION_PROMPT_LABEL,
                    requires_user_input=True,
                    poll_for_reply=False,
                    message_metadata=metadata,
                )
            message_id = getattr(response, "message_id", None)
            self._auq_registry.bind_message_id(request_id, message_id)

            try:
                decoded = await asyncio.wait_for(
                    future, timeout=ASK_USER_QUESTION_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                self.logger.warning(
                    "AskUserQuestion request %s timed out after %ds; denying",
                    request_id,
                    ASK_USER_QUESTION_TIMEOUT_SECONDS,
                )
                return PermissionResultDeny(message="AskUserQuestion timed out")
            except asyncio.CancelledError:
                self.logger.info(
                    "AskUserQuestion request %s cancelled (shutdown)", request_id
                )
                raise
        finally:
            # Belt-and-braces: drop our entry whether the future was
            # resolved, timed out, or never POSTed at all.
            self._auq_registry.cancel(request_id)

        if decoded.get("cancelled"):
            return PermissionResultDeny(message="User cancelled AskUserQuestion")

        answers = auq.reshape_answers(
            questions,
            decoded.get("answers") or [],
            decoded.get("display_answers") or [],
        )
        return PermissionResultAllow(updated_input={**tool_input, "answers": answers})

    # -- backward-compat shims for tests -----------------------------------
    #
    # These thin wrappers preserve the runner-method API the existing test
    # suite asserts against. The real work lives in the sibling modules.

    @staticmethod
    def _decode_ask_user_question_reply(reply: str) -> Optional[Dict[str, Any]]:
        return auq.decode_reply(reply)

    @staticmethod
    def _is_persist_only_message(content: str) -> bool:
        return auq.is_persist_only_message(content)

    def _bash_command_prefix(self, tool_input: Dict[str, Any]) -> Optional[str]:
        return permission_module.bash_command_prefix(tool_input)

    def _is_cached_permission(self, tool_name: str, tool_input: Dict[str, Any]) -> bool:
        return self._permission_cache.is_cached(tool_name, tool_input)

    def _cache_permission(self, tool_name: str, tool_input: Dict[str, Any]) -> None:
        self._permission_cache.cache(tool_name, tool_input)

    def _render_permission_prompt(
        self, tool_name: str, tool_input: Dict[str, Any]
    ) -> str:
        return permission_module.render_permission_prompt(tool_name, tool_input)

    def _parse_control_command(self, content: str) -> Optional[Dict[str, str]]:
        return control_command.parse_control_command(content)

    # ----------------------------------------------------------------------

    async def _handle_permission_prompt(
        self, tool_name: str, tool_input: Dict[str, Any]
    ) -> Union[PermissionResultAllow, PermissionResultDeny]:
        """Generic permission prompt for tools other than AskUserQuestion.

        Replaces what ``servers/mcp/stdio_server.py:approve_tool`` used to do
        out-of-process. The flow:

        1. Short-circuit if this tool/command was approved earlier this
           session.
        2. POST the prompt with
           ``requires_user_input=True, poll_for_reply=False``.
           ``requires_user_input`` keeps push/email/SMS notifications firing
           (see ``servers/shared/notification_utils.py``); ``poll_for_reply
           =False`` keeps the SDK from long-polling, so the §2g cursor race
           and the §2c SSE double-delivery can't happen.
        3. Register an ``asyncio.Future`` in ``_permission_registry``.
           ``_maybe_route_permission_reply`` resolves it from the WS subscriber
           when the user clicks a button (or types free text).
        4. Cache the answer if the user chose "Always allow".

        Only one permission prompt can be in flight at a time because
        ``can_use_tool`` is sequential per session, so a FIFO match in the
        registry is unambiguous in Phase 1 even though dashboards don't
        echo a ``request_id`` yet.
        """
        if not self.vicoa_client or not self.session_id:
            return PermissionResultDeny(message="Vicoa client not initialized")

        if self._permission_cache.is_cached(tool_name, tool_input):
            return PermissionResultAllow(updated_input=tool_input)

        prompt_text = permission_module.render_permission_prompt(tool_name, tool_input)

        # 1s pause matches the prior MCP path — avoids a UI race where the
        # tool call appears in the dashboard slightly after the permission
        # prompt.
        await asyncio.sleep(1)

        request_id = uuid.uuid4().hex
        future = self._permission_registry.create(request_id)

        try:
            async with self._send_lock:
                await self.vicoa_client.send_message(
                    agent_instance_id=self.session_id,
                    content=prompt_text,
                    requires_user_input=True,
                    poll_for_reply=False,
                )
            try:
                raw_answer = await asyncio.wait_for(
                    future, timeout=ASK_USER_QUESTION_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                self.logger.warning(
                    "Permission request %s for %s timed out after %ds; denying",
                    request_id,
                    tool_name,
                    ASK_USER_QUESTION_TIMEOUT_SECONDS,
                )
                return PermissionResultDeny(message="Permission request timed out")
            except asyncio.CancelledError:
                self.logger.info(
                    "Permission request %s cancelled (shutdown)", request_id
                )
                raise
        finally:
            # Belt-and-braces: drop our entry whether the future was
            # resolved, timed out, or never POSTed at all.
            self._permission_registry.cancel(request_id)

        raw_answer = (raw_answer or "").strip()
        answer = raw_answer.lower()

        if answer == permission_module.ALLOW_ONCE.lower():
            return PermissionResultAllow(updated_input=tool_input)
        if answer == permission_module.ALLOW_ALWAYS.lower():
            self._permission_cache.cache(tool_name, tool_input)
            return PermissionResultAllow(updated_input=tool_input)
        if answer == permission_module.DENY.lower():
            return PermissionResultDeny(message="Permission denied by user")
        return PermissionResultDeny(message=f"Permission denied by user: {raw_answer}")

    # ------------------------------------------------------------------
    # Reconnect / lifecycle
    # ------------------------------------------------------------------

    async def _reconnect_claude_client(self) -> bool:
        """Disconnect and reconnect Claude client with updated options.

        Returns:
            True if reconnection successful, False otherwise
        """
        try:
            self.logger.info("Reconnecting Claude client with updated settings...")

            # Retire the old reader FIRST so it can't observe the teardown as
            # a stream failure and schedule a second, competing reconnect.
            # Force-close open turns so the run loop is never left parked on
            # an event no reader will set.
            await self._stop_stream_reader()
            self._force_close_open_turns()

            if self.claude_client:
                self.logger.info("Disconnecting existing Claude client...")
                try:
                    await self.claude_client.disconnect()
                    self.claude_client = None
                except Exception as e:
                    self.logger.warning(f"Error during disconnect: {e}")

            self.claude_options = self._build_claude_options()

            self.logger.info("Creating new Claude client...")
            self.claude_client = ClaudeSDKClient(options=self.claude_options)
            self.logger.info("Connecting new Claude client...")
            await self.claude_client.connect()
            self._ensure_stream_reader()

            self.logger.info("✅ Claude client reconnected successfully")
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to reconnect Claude client: {e}")
            return False

    def _build_session_config(self) -> dict:
        """Snapshot of spawn-time config for the chat-header pill.

        Persisted by the backend on the agent_instances row (single source of
        truth) so the mobile header doesn't have to derive model/effort from
        scanning the message history. None-valued keys are stripped — the
        backend treats absent vs explicit-null differently in the activate-
        existing branch, and the mobile pill skips rows for missing fields.
        """
        sc = {
            "agent": "claude",
            "model": self.model,
            "thinking_effort": self.thinking_effort,
            "permission_mode": self.permission_mode,
        }
        return {k: v for k, v in sc.items() if v is not None}

    async def discover_and_report_models(self) -> None:
        """Report Claude's available models onto ``session_config`` for the
        mid-session gear, mirroring codex's ``discover_and_report_models``.

        Claude Code has no ``model/list`` RPC, so the set is the static catalog
        plus the machine's custom models (``~/.claude/settings.json`` +
        ``ANTHROPIC_*_MODEL`` env) — see ``claude_model_catalog``. Writing it to
        the same ``session_config.available_models`` field every other agent
        already reports lets the mobile gear read one field regardless of agent.

        Best-effort: any failure leaves ``available_models`` unset and the
        static agent-catalog list stays the picker fallback.
        """
        try:
            models = build_claude_available_models()
        except Exception:
            self.logger.warning(
                "claude: failed to build available_models (non-fatal)",
                exc_info=True,
            )
            return
        if not models or not self.vicoa_client or not self.session_id:
            return
        delta: dict = {"available_models": models}
        # current_model lets the gear open on the running model. Only the user's
        # explicit spawn pick is known here (Claude reports no default); when it
        # is unset the app resolves the picker default itself.
        if self.model:
            delta["current_model"] = self.model
        try:
            await self.vicoa_client.patch_agent_instance(
                self.session_id, session_config=delta
            )
            self.logger.info(
                "claude: reported %d available models (current=%s)",
                len(models),
                self.model,
            )
        except Exception:
            self.logger.warning(
                "claude: failed to PATCH available_models (non-fatal)",
                exc_info=True,
            )

    async def initialize(self):
        """Initialize the Vicoa and Claude clients and create initial session."""
        self.logger.info("Initializing Vicoa client...")

        self.vicoa_client = AsyncVicoaClient(
            api_key=self.vicoa_api_key, base_url=self.vicoa_base_url
        )

        if self.is_resuming:
            # The row already exists, and re-registering the same id is
            # rejected (409). Just reopen it so the UI stops showing the
            # session as stopped while the agent comes back up.
            self.logger.info("Resuming agent instance %s", self.session_id)
            try:
                # AWAITING_INPUT, not ACTIVE: the agent is idle waiting for the
                # user, and ACTIVE renders a "working" spinner for an agent that
                # isn't doing anything.
                await self.vicoa_client.update_agent_instance_status(
                    self.session_id, "AWAITING_INPUT"
                )
            except Exception:
                self.logger.warning(
                    "Failed to reopen instance %s on resume",
                    self.session_id,
                    exc_info=True,
                )
        else:
            try:
                registration = await asyncio.wait_for(
                    self.vicoa_client.register_agent_instance(
                        agent_type=self.agent_name,
                        agent_instance_id=self.session_id,
                        project=self.project_path,
                        home_dir=str(Path.home()),
                        session_config=self._build_session_config(),
                        source="app",
                    ),
                    timeout=10.0,
                )
                updated_session_id = registration.agent_instance_id
                if updated_session_id and updated_session_id != self.session_id:
                    self.logger.info(
                        f"Session ID updated from {self.session_id} to {updated_session_id}"
                    )
                    self.session_id = updated_session_id
                    self.claude_options = self._build_claude_options()
                    self.logger.info(
                        "Rebuilt Claude options with updated session ID for MCP server"
                    )
            except asyncio.TimeoutError:
                # Re-raise so the headless process exits immediately. The
                # daemon's _wait_for_process_ready will detect the early exit
                # and mark the spawn request as error — preventing a 30-second
                # retry loop that would keep the request "pending" long enough
                # for _catchup_poll to re-dispatch it to a second session.
                self.logger.error(
                    "Agent instance registration timed out for session %s — aborting",
                    self.session_id,
                )
                raise
            except Exception as exc:
                # Previously logged-and-continued, which left the process
                # running as an invisible zombie: the daemon's spawn RPC had
                # already returned success with this instance id, so the
                # mobile/web caller polls for a row that will now never
                # exist, times out ("instance_never_registered"), and shows a
                # generic failure — while this process keeps running
                # unregistered, burning the user's agent usage with no way to
                # see or stop it (e.g. a monthly-limit 402 would silently
                # spawn a session anyway instead of blocking it). Re-raise so
                # `run()`'s fatal-error path exits the process immediately,
                # matching the TimeoutError handling above.
                self.logger.error(
                    "Failed to register agent instance for session %s: %s — aborting",
                    self.session_id,
                    exc,
                )
                raise

        # Session id is settled now (registration can hand back a different
        # one). Keep the session reading as alive while it sits idle awaiting
        # user input — see integrations/utils/heartbeat.py.
        self._heartbeat = AsyncSessionHeartbeat(
            agent_instance_id=self.session_id,
            vicoa_client=self.vicoa_client,
        )
        self._heartbeat.start()

        self.logger.info("Initializing Claude Agent SDK client...")
        self.claude_client = ClaudeSDKClient(options=self.claude_options)
        await self.claude_client.connect()
        # Initial connect succeeded — subsequent rebuilds (model / effort /
        # thinking toggle) must use resume= so the SDK doesn't refuse the
        # already-live session_id.
        self._initial_connect_done = True
        # Session-lifetime SDK stream consumer — runs from here until
        # shutdown, independent of turn state. See ``_run_stream_reader``.
        self._ensure_stream_reader()

        self._start_ws_client()
        self._control_worker_task = asyncio.create_task(self._run_control_worker())
        self._reconciler_task = asyncio.create_task(self._run_reconcile_backstop())
        self._status_watchdog_task = asyncio.create_task(self._run_status_watchdog())

        # Report the machine's real Claude models (catalog + the user's
        # ~/.claude custom models) onto session_config so the mid-session gear
        # shows the actual switchable set, mirroring codex's model/list
        # discovery. Best-effort; never blocks bring-up.
        try:
            await self.discover_and_report_models()
        except Exception:
            self.logger.warning(
                "claude: model discovery failed (non-fatal)", exc_info=True
            )

        self.logger.info("Creating initial Vicoa session...")
        if not self.vicoa_client:
            raise RuntimeError("Vicoa client not initialized")

        if self.initial_prompt and self.initial_prompt.strip():
            # POST the prompt as a user message so the dashboard shows it in
            # chat. Do NOT also feed it directly to ``run_conversation_turn``
            # — vicoa-server broadcasts the POSTed row back to our own /ws
            # subscription, which routes through ``_on_ws_user_message`` ->
            # ``_route`` -> ``_user_message_queue``, and ``run()`` dequeues
            # it as the first turn input. Calling ``run_conversation_turn``
            # directly here would cause two turns for the same input
            # (session 40e02f0a-…). Mirrors ``codex_native.run()`` 2026-06.
            #
            # Wait for the WS subscriber to finish its catch-up handshake
            # before POSTing. Otherwise the broadcast from this POST can
            # land in the gap between subscription-registration and the
            # catch-up SELECT, and the prompt is silently dropped on first
            # session (subsequent messages work because by then the
            # subscriber is fully attached).
            if self._ws_client is not None:
                ready = await asyncio.to_thread(self._ws_client.wait_until_ready, 10.0)
                if not ready:
                    self.logger.warning(
                        "WS catch-up not ready after 10s; POSTing initial prompt anyway"
                    )
            try:
                await self.vicoa_client.send_user_message(
                    agent_instance_id=self.session_id,
                    content=self.initial_prompt,
                )
            except Exception:
                self.logger.exception("Failed to POST initial prompt as user message")

    async def send_to_vicoa(
        self, content: str, message_metadata: Optional[dict] = None
    ) -> None:
        """Send an intermediate (non-blocking) agent message to Vicoa.

        Held under ``_send_lock`` so concurrent calls — including the AUQ
        callback's POST — are serialized and cannot race on the backend's
        ``instance.last_read_message_id`` cursor.
        """
        if not self.vicoa_client or not self.session_id:
            self.logger.error("Vicoa client not initialized")
            return

        try:
            async with self._send_lock:
                response = await self.vicoa_client.send_message(
                    content=content,
                    agent_type=self.agent_name,
                    agent_instance_id=self.session_id,
                    requires_user_input=False,
                    message_metadata=message_metadata,
                )

            if hasattr(response, "message_id"):
                self.last_message_id = response.message_id

        except Exception as e:
            self.logger.error(f"Failed to send message to Vicoa: {e}")

    def format_message_content(self, message) -> str:
        """Format a Claude SDK message for display in Vicoa."""
        if isinstance(message, AssistantMessage):
            # AskUserQuestion is rendered by the dashboard's interactive
            # picker, which ``_handle_ask_user_question`` sends as its own
            # message with structured ``message_metadata``. Skip the *entire*
            # AssistantMessage that contains the tool_use — see
            # ``auq.AskUserQuestionRegistry`` for the race rationale.
            if any(
                isinstance(b, ToolUseBlock) and b.name == "AskUserQuestion"
                for b in message.content
            ):
                return ""

            parts = []
            for block in message.content:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    tool_name = block.name
                    tool_input = block.input if hasattr(block, "input") else {}
                    formatted = format_tool_use(tool_name, tool_input)
                    parts.append(formatted)
                elif isinstance(block, ToolResultBlock):
                    if hasattr(block, "content") and block.content:
                        result_summary = str(block.content)[:200]
                        if len(str(block.content)) > 200:
                            result_summary += "..."
                        parts.append(f"   Result: {result_summary}")

            # No renderable parts → suppress. This is the common
            # thinking-only AssistantMessage (adaptive thinking emits
            # ThinkingBlock-only turns; with display="omitted" on Opus 4.7+ /
            # Fable 5 the thinking text is empty too). The run loop skips
            # falsy content, so returning "" drops it instead of POSTing a
            # bogus "Claude is thinking..." agent message to the user.
            return "\n".join(parts)

        elif isinstance(message, UserMessage):
            content = getattr(message, "content", str(message))
            return f"User: {content}"
        elif isinstance(message, SystemMessage):
            content = getattr(
                message, "content", getattr(message, "text", str(message))
            )
            return f"System: {content}"
        elif isinstance(message, ResultMessage):
            content = getattr(
                message,
                "content",
                getattr(message, "text", "Claude completed this task."),
            )
            return content if content != str(message) else "Claude completed this task."
        elif isinstance(message, RateLimitEvent):
            return self._rate_limit_gate.text_for(message) or ""

        # Unknown message type: don't leak a raw dataclass repr into the
        # dashboard. ``run_conversation_turn`` calls us only after filtering
        # out the routed types, so reaching here means the SDK added a type
        # we don't recognise — log it and stay quiet.
        self.logger.debug(
            "format_message_content: unhandled message type %s; suppressing",
            type(message).__name__,
        )
        return ""

    @staticmethod
    def _thinking_text(message) -> str:
        """Concatenated text of every ``ThinkingBlock`` in an AssistantMessage.

        ``format_message_content`` deliberately ignores ``ThinkingBlock`` (it
        renders only text + tool-use), so the model's reasoning is surfaced
        separately as its own metadata-tagged "thinking" card — see
        ``integrations.headless.thinking``. Returns ``""`` when there is no
        thinking to show, which is the common case on models that emit
        ``display="omitted"`` thinking (Opus 4.7+ / Fable 5) where the block
        carries a signature but no text.
        """
        if not isinstance(message, AssistantMessage):
            return ""
        parts = [
            block.thinking
            for block in message.content
            if isinstance(block, ThinkingBlock) and getattr(block, "thinking", "")
        ]
        return "\n\n".join(p.strip() for p in parts if p and p.strip())

    def _remember_tasks_in_message(self, message) -> None:
        """Cache Task/Agent launch inputs so child messages can be labelled.

        Called on every main-stream message in ``run_conversation_turn``
        (parent_tool_use_id is None there), before children with a matching
        ``parent_tool_use_id`` arrive on the same stream.
        """
        if not isinstance(message, AssistantMessage):
            return
        for block in message.content:
            if isinstance(block, ToolUseBlock) and block.name in ("Task", "Agent"):
                self._subagent_tracker.remember_task(
                    block.id,
                    (block.input or {}).get("subagent_type", "agent"),
                    (block.input or {}).get("description", ""),
                )

    def _track_task_lifecycle(self, message) -> None:
        """Maintain ``_pending_background_tasks`` from the CLI's task events.

        ``task_started`` fires when any sub-agent launches; ``task_notification``
        fires once it settles (``completed`` / ``failed`` / ``stopped``). For a
        *foreground* sub-agent both land before the turn's ``ResultMessage``, so
        the set is empty by then and nothing changes. For a background one the
        notification arrives *after* it.
        """
        if isinstance(message, TaskStartedMessage):
            self._pending_background_tasks.add(message.task_id)
        elif isinstance(message, TaskNotificationMessage):
            self._pending_background_tasks.discard(message.task_id)

    # ------------------------------------------------------------------
    # Session-lifetime stream reader (Paseo's "query pump") + turn state
    # ------------------------------------------------------------------

    def _ensure_stream_reader(self) -> None:
        """Start the session-lifetime SDK stream reader for the live client.

        Idempotent per client instance: called from ``initialize``,
        ``_reconnect_claude_client``, and defensively at every turn start.
        A reader still serving a *replaced* client is retired first.
        """
        client = self.claude_client
        if client is None:
            return
        task = self._stream_reader_task
        if task is not None and not task.done() and self._reader_client is client:
            return
        if task is not None and not task.done():
            task.cancel()
        self._reader_client = client
        self._stream_reader_task = asyncio.create_task(self._run_stream_reader(client))

    async def _stop_stream_reader(self) -> None:
        """Cancel the reader and wait for it to unwind (no-op from itself)."""
        task = self._stream_reader_task
        self._stream_reader_task = None
        self._reader_client = None
        if task is None or task.done() or task is asyncio.current_task():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            self.logger.debug("stream reader raised during stop", exc_info=True)

    async def _run_stream_reader(self, client: Any) -> None:
        """Consume the SDK stream from connect to disconnect, forwarding
        every message as it arrives regardless of turn state.

        This is the load-bearing loop of the runner. It must never park on
        anything but the stream itself: the moment consumption stops while
        the CLI keeps producing, the SDK's 100-slot buffer fills, its read
        task blocks, the CLI's stdout pipe backpressures, and sub-agents
        stall mid-work — the "UI stuck until my next message" family of
        bugs. Turn bookkeeping happens inside ``_process_sdk_message``; the
        run loop waits on ``_foreground_turn_done`` instead of reading.

        A stream that ends or errors while the session is live is routed to
        ``_recover_stream`` (reconnect with ``resume=``); a reader retired
        by a reconnect is cancelled and schedules nothing.
        """
        stream = cast(AsyncGenerator[Any, None], client.receive_messages())
        message_count = 0
        failure: Optional[BaseException] = None
        try:
            try:
                while True:
                    try:
                        message = await stream.__anext__()
                    except StopAsyncIteration:
                        break
                    message_count += 1
                    self.logger.info(
                        f"Message #{message_count} - Type: {type(message).__name__}"
                    )
                    self._last_stream_activity = asyncio.get_running_loop().time()
                    try:
                        await self._process_sdk_message(message)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        self.logger.exception(
                            "Error processing SDK message; continuing with the stream"
                        )
            finally:
                await stream.aclose()
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # noqa: BLE001 — routed to recovery below
            failure = exc
        self._schedule_stream_recovery(client, failure)

    def _schedule_stream_recovery(
        self, client: Any, failure: Optional[BaseException]
    ) -> None:
        """The reader exited on its own (stream ended or errored) — recover.

        No-op when the runner is shutting down or the client was already
        replaced (a reconnect retires its reader by cancelling it, which
        never reaches here).
        """
        if not self.running or self._stopping or self.claude_client is not client:
            return
        if failure is None:
            self.logger.error("Claude SDK stream ended unexpectedly; recovering")
        else:
            self.logger.error(
                "Claude SDK stream failed (%s: %s); recovering",
                type(failure).__name__,
                failure,
            )
        try:
            self._stream_recovery_task = asyncio.create_task(
                self._recover_stream(failure)
            )
        except RuntimeError:
            # Event loop already closing (process shutdown) — nothing left
            # to recover into.
            self.logger.debug("stream recovery skipped: event loop closed")

    async def _recover_stream(self, failure: Optional[BaseException]) -> None:
        """Reconnect in place after the stream died mid-session.

        ``_reconnect_claude_client`` reconnects with ``resume=`` (see
        ``_build_claude_options``) so the on-disk transcript — and the
        conversation — survives. Open turns are force-closed first so the
        run loop can never be left parked on an event no reader will set.
        """
        self._force_close_open_turns()
        if isinstance(failure, CLIJSONDecodeError):
            # A single CLI stdout message blew past ``max_buffer_size`` —
            # almost always a giant tool result. The rebuilt options carry
            # the larger ``max_buffer_size``, so a message that only just
            # cleared the old cap won't trip the new client.
            await self.send_to_vicoa(
                "⚠️ A response from Claude was too large to read in one piece and "
                "was dropped. Reconnecting your session."
            )
        elif isinstance(failure, ProcessError):
            await self.send_to_vicoa(
                f"⚠️ Claude Code process error: {failure}. Reconnecting your session."
            )
        if await self._reconnect_claude_client():
            return
        await self.send_to_vicoa(
            "❌ Claude Code stopped responding and could not be reconnected. "
            "Please restart the session."
        )
        await self._settle_turn_end()

    def _force_close_open_turns(self) -> None:
        """Drop all turn state and unblock the run loop (stream loss/reconnect)."""
        self._open_turns.clear()
        self._pending_background_tasks.clear()
        event = self._foreground_turn_done
        if event is not None and not event.is_set():
            event.set()

    @staticmethod
    def _is_activity_message(message: Any) -> bool:
        """True for messages that mean the CLI is actively working.

        Mirrors Paseo's ``isAssistantishMessage``: agent output, sub-agent
        child frames (``parent_tool_use_id`` set), and task lifecycle events
        re-open "working"; bare init / result / rate-limit frames don't.
        """
        if isinstance(
            message, (AssistantMessage, TaskStartedMessage, TaskNotificationMessage)
        ):
            return True
        return bool(getattr(message, "parent_tool_use_id", None))

    async def _open_autonomous_turn(self, message: Any) -> None:
        """CLI produced output with no open turn: background/CLI-initiated
        work (typically a background sub-agent's report turn). Track it so
        its ``ResultMessage`` has something to close, and show the session
        as working."""
        self._open_turns.append("autonomous")
        self.logger.info(
            "SDK output (%s) with no open turn; opening an autonomous turn",
            type(message).__name__,
        )
        await self._mark_active_for_turn()

    async def _close_current_turn(self) -> None:
        """A ``ResultMessage`` arrived: close the oldest open turn.

        The CLI serializes its turns, so FIFO association is unambiguous. A
        result with no open turn is stale (an interrupt force-close beat it,
        or a reconnect cleared state) and is dropped — forwarding-wise its
        content already streamed; letting it close a *later* turn is exactly
        the lag-by-one bug.
        """
        if not self._open_turns:
            self.logger.info("ResultMessage with no open turn; dropping as stale")
            return
        kind = self._open_turns.popleft()
        if kind == "foreground":
            # Snapshot the deferral decision NOW — by the time the run loop
            # wakes, this reader may already have consumed the notifications
            # (and run the autonomous settle), so re-reading the pending set
            # there would double-settle.
            self._foreground_settle_deferred = bool(self._pending_background_tasks)
            event = self._foreground_turn_done
            if event is not None:
                event.set()
            return
        self.logger.info("Autonomous turn completed")
        await self._settle_after_autonomous_turn()

    async def _settle_after_autonomous_turn(self) -> None:
        """Decide whether an autonomous close should settle the session."""
        if self._open_turns:
            # A foreground turn is queued behind this one; its own close
            # settles the session.
            return
        if self.interrupt_requested:
            # The interrupt path already posted its notice; just re-assert
            # the idle status it wrote (a racing agent POST re-opens ACTIVE).
            await self._settle_awaiting_input_after_interrupt()
            return
        if self._pending_background_tasks:
            self.logger.info(
                "Autonomous turn closed with %d background task(s) outstanding "
                "(%s); staying ACTIVE",
                len(self._pending_background_tasks),
                ", ".join(sorted(self._pending_background_tasks)),
            )
            return
        await self._settle_turn_end()

    async def _settle_turn_end(self) -> None:
        """End-of-turn bookkeeping shared by foreground and autonomous closes.

        Flip the tail agent message to requires-user-input — which drives
        AWAITING_INPUT, push/email notifications, and returns the
        ``already_queued`` remainder — or fall back to a bare status write
        when nothing new was posted. ``last_message_id`` is consumed so a
        later settle can't re-mark the same row (the API 400s on that).
        """
        if self._stopping or not self.vicoa_client:
            return
        if self.last_message_id:
            self.logger.info(
                f"Marking last message {self.last_message_id} as awaiting input"
            )
            try:
                already_queued = await self.vicoa_client.mark_message_requires_input(
                    self.last_message_id
                )
                if already_queued:
                    await self._enqueue_already_queued(already_queued)
                    self.interrupt_requested = False
            except Exception as e:
                self.logger.error(f"Failed to mark message as requiring input: {e}")
            self.last_message_id = None
            return
        try:
            await self.vicoa_client.update_agent_instance_status(
                self.session_id, "AWAITING_INPUT"
            )
        except Exception as exc:
            self.logger.warning(
                "Failed to set status=AWAITING_INPUT at turn end: %s", exc
            )

    async def _await_foreground_turn_close(self) -> bool:
        """Park until the reader closes this turn's foreground entry.

        Deliberately unbounded: a legitimately quiet turn (a long-running
        Bash command, a pending permission or AskUserQuestion reply) can go
        silent for hours, and stream *failure* is the reader's job to detect
        (``_recover_stream`` force-closes open turns). The one bounded wait
        is the interrupt unwind: the CLI normally closes an interrupted turn
        with a ResultMessage within a second — if it doesn't within
        ``_INTERRUPT_RESULT_TIMEOUT`` the close is forced so the session
        can't wedge. Returns True when the turn ended interrupted.
        """
        event = self._foreground_turn_done
        if event is None:
            return self.interrupt_requested
        loop = asyncio.get_running_loop()
        interrupt_deadline: Optional[float] = None
        while not event.is_set():
            if self.interrupt_requested and interrupt_deadline is None:
                interrupt_deadline = loop.time() + _INTERRUPT_RESULT_TIMEOUT
            timeout = 1.0
            if interrupt_deadline is not None:
                remaining = interrupt_deadline - loop.time()
                if remaining <= 0.0:
                    self.logger.warning(
                        "Interrupted turn did not close within %.0fs; forcing "
                        "it closed (the stream reader stays on the stream)",
                        _INTERRUPT_RESULT_TIMEOUT,
                    )
                    try:
                        self._open_turns.remove("foreground")
                    except ValueError:
                        pass
                    event.set()
                    break
                timeout = min(timeout, remaining)
            try:
                await asyncio.wait_for(event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                continue
        return self.interrupt_requested

    async def _run_status_watchdog(self) -> None:
        """Cosmetic settle for autonomous work that went permanently quiet.

        Replaces the old ``_BACKGROUND_TASK_IDLE_TIMEOUT`` give-up, which
        stopped *reading* the stream — stranding everything the CLI said
        afterwards and, worse, firing while the CLI was legitimately quiet
        because a permission/AskUserQuestion reply was pending with the
        human. This version only touches the status row: consumption never
        stops, a pending human reply always defers it, and any later output
        simply re-opens an autonomous turn and re-marks the session ACTIVE.
        """
        while self.running:
            try:
                await asyncio.sleep(_STATUS_WATCHDOG_INTERVAL)
            except asyncio.CancelledError:
                return
            if self._stopping:
                continue
            if "foreground" in self._open_turns:
                # The run loop owns this settle; quiet is legitimate here
                # (long Bash runs, the model thinking).
                continue
            if not self._open_turns and not self._pending_background_tasks:
                continue
            if (
                self._auq_registry.has_pending()
                or self._permission_registry.has_pending()
            ):
                continue
            idle = asyncio.get_running_loop().time() - self._last_stream_activity
            if idle < _STATUS_SETTLE_IDLE_SECONDS:
                continue
            self.logger.warning(
                "No SDK output for %.0fs with %d background task(s) outstanding "
                "(%s) and %d autonomous turn(s) open; settling status to "
                "AWAITING_INPUT (the stream reader stays open — later output "
                "re-activates the session)",
                idle,
                len(self._pending_background_tasks),
                ", ".join(sorted(self._pending_background_tasks)) or "-",
                len(self._open_turns),
            )
            self._pending_background_tasks.clear()
            self._open_turns.clear()
            await self._settle_turn_end()

    async def _process_sdk_message(self, message: Any) -> None:
        """Handle one SDK message: forward, track lifecycle, close turns.

        This is the per-message body that used to live inside the turn loop,
        now driven unconditionally by the session-lifetime reader.
        """
        # Task lifecycle + Task-launch labelling always run — even during an
        # interrupt unwind — so tracker state stays truthful.
        self._track_task_lifecycle(message)
        self._remember_tasks_in_message(message)

        # Mirror the old drain-and-discard: while an interrupt is unwinding
        # (Stop pressed, closing ResultMessage not yet seen) nothing is
        # forwarded — anything worth showing already streamed before the
        # Stop. ResultMessages still close turns and bank usage below.
        suppressing = self.interrupt_requested and bool(self._open_turns)

        if (
            not self._open_turns
            and not suppressing
            and self._is_activity_message(message)
        ):
            await self._open_autonomous_turn(message)

        if isinstance(message, ResultMessage) and not getattr(
            message, "parent_tool_use_id", None
        ):
            # Close the turn out with the authoritative window size and the
            # running cost (also banks an interrupted turn's usage — the work
            # still happened).
            await self._stamp_context_usage(
                usage_mod.claude_context_used_from_result(
                    getattr(message, "usage", None)
                ),
                model_usage=getattr(message, "model_usage", None),
                cost_usd=getattr(message, "total_cost_usd", None),
            )
            # Refresh the Session/Weekly plan-usage snapshot out-of-band
            # (throttled, non-blocking).
            self._schedule_limits_fetch()
            await self._close_current_turn()
            return

        if suppressing:
            return

        # Divert sub-agent child messages (parent_tool_use_id set) before the
        # flat-send / UserMessage-skip branches below.
        if await self._maybe_handle_subagent_message(message):
            return

        # Context fill rides every main-stream assistant message, so the
        # meter tracks a long turn instead of only landing once it ends.
        if isinstance(message, AssistantMessage):
            await self._stamp_context_usage(
                usage_mod.claude_context_used_tokens(getattr(message, "usage", None)),
                model=getattr(message, "model", None),
            )

        if isinstance(message, SystemMessage):
            # A settled sub-agent's report arrives here (SystemMessage
            # subclass) — forward it before the blanket skip below.
            if isinstance(message, TaskNotificationMessage):
                await self._send_subagent_result(message)
                return
            # Compaction shrinks the window; stamp it so a turn ending right
            # after compacting doesn't leave a stale near-full reading up.
            if getattr(message, "subtype", None) == "compact_boundary":
                await self._stamp_context_usage(
                    usage_mod.claude_compaction_post_tokens(
                        getattr(message, "data", None)
                    )
                )
            # An ``init`` SystemMessage fires at the start of every turn; it
            # does NOT mean context was reset. Only warn if the inner
            # session_id actually changed.
            if hasattr(message, "subtype") and message.subtype == "init":
                sdk_session_id = None
                data = getattr(message, "data", None)
                if isinstance(data, dict):
                    sdk_session_id = data.get("session_id")
                prior = getattr(self, "_last_sdk_session_id", None)
                if sdk_session_id and prior and sdk_session_id != prior:
                    self.logger.warning(
                        "Claude SDK session_id changed (%s -> %s); "
                        "context may have been reset",
                        prior,
                        sdk_session_id,
                    )
                if sdk_session_id:
                    self._last_sdk_session_id = sdk_session_id
            self.logger.debug(f"System message: {message}")
            return

        if isinstance(message, UserMessage):
            self.logger.debug(f"User message (not forwarding): {message}")
            return

        # Rate-limit events feed two channels: every event updates the
        # structured usage meter, but only a few become chat messages — see
        # ``_RateLimitNoticeGate``.
        if isinstance(message, RateLimitEvent):
            info = message.rate_limit_info
            if self._usage.upsert_window(
                usage_mod.claude_window(
                    getattr(info, "rate_limit_type", None),
                    _rate_limit_utilization(info),
                    getattr(info, "resets_at", None),
                )
            ):
                await self._flush_usage()
            rate_limit_text = self._rate_limit_gate.text_for(message)
            if rate_limit_text:
                await self.send_to_vicoa(rate_limit_text)
            else:
                self.logger.debug(
                    "Suppressing RateLimitEvent (status=%s, utilization=%s)",
                    getattr(info, "status", None),
                    getattr(info, "utilization", None),
                )
            return

        # Surface the model's reasoning as its own collapsed "thinking" card
        # (metadata-tagged) BEFORE the turn's text/tool-use, matching the
        # order the blocks arrive in. ``_thinking_text`` returns "" when
        # there's nothing to show, so non-thinking turns POST nothing extra.
        thinking_text = self._thinking_text(message)
        if thinking_text:
            self.logger.info("thinking card: emitting %d chars", len(thinking_text))
            await self.send_to_vicoa(thinking_text, build_thinking_metadata("claude"))
        elif isinstance(message, AssistantMessage) and any(
            isinstance(b, ThinkingBlock) for b in message.content
        ):
            # Diagnostic: the model emitted a ThinkingBlock but its text is empty
            # (display="omitted" on Opus 4.7+ / Fable 5), so there's no card to
            # show. Distinguishes "model omitted thinking" from "no thinking at
            # all" (thinking disabled / model didn't reason) when debugging why a
            # session shows no Thinking card.
            self.logger.info(
                "thinking card: ThinkingBlock present but text empty "
                "(model display=omitted); nothing to show"
            )

        formatted_content = self.format_message_content(message)
        if formatted_content:
            await self.send_to_vicoa(formatted_content)

    async def _send_subagent_result(self, message: TaskNotificationMessage) -> None:
        """Forward a settled sub-agent's report as a tagged message.

        The report reaches us twice and both copies were being dropped: once as
        this ``task_notification`` (a ``SystemMessage`` subclass, swallowed by
        the blanket skip in ``_process_sdk_message``) and once as the Agent
        tool_result, which rides a *main-stream* ``UserMessage`` — i.e.
        ``parent_tool_use_id`` is None, so ``_maybe_handle_subagent_message``
        never sees it and the tool-result skip drops it. Net effect: the
        dashboard showed a sub-agent's intermediate tool calls but never what
        it actually concluded.

        We forward this copy rather than the tool_result because it carries the
        ``task_id``/``status`` and none of the tool_result's internal plumbing
        (the "agentId: … use SendMessage to continue" block).
        """
        tool_use_id = message.tool_use_id
        summary = (message.summary or "").strip()
        if not tool_use_id or not summary:
            return

        subagent_type, description = self._subagent_tracker.label_for(tool_use_id)
        if message.status != "completed":
            summary = f"⚠️ Sub-agent {message.status}\n\n{summary}"

        await self.send_to_vicoa(
            summary,
            build_metadata(tool_use_id, subagent_type, description, role="result"),
        )

    async def _maybe_handle_subagent_message(self, message) -> bool:
        """If ``message`` belongs to a sub-agent, format + send it tagged and
        return True. Otherwise return False so it falls through to the
        normal flat-send handling.

        Sub-agent output is surfaced *symmetrically with the main stream*.
        The main loop renders an agent's text + tool-use blocks
        (``format_message_content``) but drops every tool-result
        ``UserMessage`` via the blanket ``isinstance(message, UserMessage)``
        skip in ``_process_sdk_message``. We mirror that here:
        sub-agent tool-result ``UserMessage``s are dropped too, so a
        sub-agent's chat reads the same way the main agent's does — tool-use
        lines (which for Edit/Write already carry the diff/content from the
        tool *input*), with no raw "Result: …" echoes.

        A message with a truthy ``parent_tool_use_id`` always returns True —
        it must never fall through to the flat send/skip branches below,
        even when it renders to nothing (a thinking-only child turn) or is a
        dropped tool result.
        """
        parent_id = getattr(message, "parent_tool_use_id", None)
        if not parent_id:
            return False

        # Mirror the main stream: tool results ride on ``UserMessage``s and
        # are dropped there. Return True (handled, so it doesn't reach the
        # flat-send path) but forward nothing.
        if isinstance(message, UserMessage):
            return True

        subagent_type, description = self._subagent_tracker.label_for(parent_id)

        # A sub-agent reasons too. Surface its thinking as a collapsed card
        # that stays grouped under the sub-agent (both metadata keys present),
        # emitted before the sub-agent's own text/tool-use for correct order.
        thinking_text = self._thinking_text(message)
        if thinking_text:
            await self.send_to_vicoa(
                thinking_text,
                {
                    **build_metadata(parent_id, subagent_type, description),
                    **build_thinking_metadata("claude"),
                },
            )

        formatted = self.format_message_content(message)
        if not formatted:
            return True

        await self.send_to_vicoa(
            formatted, build_metadata(parent_id, subagent_type, description)
        )
        return True

    async def _handle_interrupt(self) -> None:
        """Handle interrupt command by stopping the current task.

        Three layers of stop, applied fast-to-slow so the user-visible
        latency is dominated by the SDK call rather than a vicoa POST:

        1. ``interrupt_requested = True`` — cooperative flag that the
           ``receive_response`` loop and ``_wait_for_user_input`` poll.
        2. ``claude_client.interrupt()`` — SDK-level cancel of the
           in-flight response stream.
        3. ``cancel_all()`` on the AUQ + permission registries — needed
           because ``claude_client.interrupt()`` alone can't reach a
           runner that's blocked inside ``can_use_tool`` awaiting a
           pending permission/AUQ reply. Without this, an interrupt
           sent while a permission prompt was open did nothing.

        The user-facing feedback message goes out BEFORE the status
        write, and the status write is repeated by ``run_conversation_turn``
        once the aborted turn has finished unwinding. Ordering matters:
        every agent message POST runs through ``create_agent_message``,
        which sets ``instance.status = ACTIVE`` whenever
        ``requires_user_input`` is False. Writing AWAITING_INPUT first
        (the old order) meant this very feedback message immediately
        flipped the row back to ACTIVE, so the dashboard sat on "active"
        forever after a Stop.

        We deliberately do NOT use ``send_message(requires_user_input=True)``
        here because that path fires push / email / SMS notifications —
        the user just pressed Stop and is already in the app; pinging
        them is noise. ``update_agent_instance_status`` is a pure DB
        field write.
        """
        if self.interrupt_requested:
            return

        self.interrupt_requested = True
        self.logger.info("Interrupt command received; stopping current task")

        if self.claude_client:
            try:
                await self.claude_client.interrupt()
                self.logger.info("Sent interrupt to Claude client")
            except Exception as exc:
                self.logger.error(f"Failed to interrupt Claude client: {exc}")

        self._auq_registry.cancel_all()
        self._permission_registry.cancel_all()

        await self._send_feedback_message(
            "Interrupted · What should Claude do instead?"
        )
        await self._settle_awaiting_input_after_interrupt()

    async def _settle_awaiting_input_after_interrupt(self) -> None:
        """Write status=AWAITING_INPUT so the dashboard shows the runner idle.

        Called twice per interrupt — once from ``_handle_interrupt`` (so a
        Stop pressed while nothing is running still settles the row) and
        once from ``run_conversation_turn`` after the aborted turn has fully
        unwound. The second call is what makes the status stick: the turn
        loop can still be mid-``send_to_vicoa`` when the interrupt lands,
        and that POST would otherwise re-set the row to ACTIVE after us.

        Idempotent (a plain field write) and best-effort — a failed status
        push is a cosmetic regression, never a reason to unwind the stop.
        """
        if not (self.vicoa_client and self.session_id) or self._stopping:
            return
        try:
            await self.vicoa_client.update_agent_instance_status(
                self.session_id, "AWAITING_INPUT"
            )
        except Exception as exc:
            self.logger.warning(
                "Failed to set status=AWAITING_INPUT after interrupt: %s", exc
            )

    async def _mark_awaiting_input_after_settings_change(self, setting: str) -> None:
        """Flip the agent_instance status to AWAITING_INPUT.

        Called after a successful mid-session model / effort / permission_mode
        change. The mobile gear toggle fires while the session is idle, so
        without this flip the chat header keeps showing whatever status the
        row carried before the toggle (often a stale ``ACTIVE`` from the
        prior turn) until the next message arrives.

        Failures are warning-logged only; the user-facing change already
        succeeded — a stale status row is a soft regression, not a reason to
        unwind the change.
        """
        if not (self.vicoa_client and self.session_id):
            return
        try:
            await self.vicoa_client.update_agent_instance_status(
                self.session_id, "AWAITING_INPUT"
            )
        except Exception as exc:
            self.logger.warning(
                "Failed to set status=AWAITING_INPUT after %s change: %s",
                setting,
                exc,
            )

    async def _mark_active_for_turn(self) -> None:
        """Flip the instance to ACTIVE at the start of processing a user turn.

        Mirrors the ACP/codex dequeue (``acp_base.py`` calls
        ``_set_agent_status("ACTIVE")`` before ``send_prompt``), which the Claude
        headless path was missing. ``mark_message_consumed`` is status-neutral
        and nothing else here re-asserts ACTIVE, so a message queued while the
        agent was busy and then delivered over live WS could be processed while
        the row still read AWAITING_INPUT. Two user-visible symptoms followed:
        the dashboard showed the agent idle mid-work, and the web's
        "ACTIVE → settled" queued-message self-heal (which reconciles a lost
        ``consumed`` patch) never armed, so a stale ``queued`` pill stayed
        pinned. Best-effort — a failed status write is a cosmetic regression.
        """
        if not (self.vicoa_client and self.session_id) or self._stopping:
            return
        try:
            await self.vicoa_client.update_agent_instance_status(
                self.session_id, "ACTIVE"
            )
        except Exception as exc:
            self.logger.warning("Failed to set status=ACTIVE at turn start: %s", exc)

    async def _send_feedback_message(self, content: str) -> None:
        """Send a feedback message to the web UI (non-blocking)."""
        try:
            if self.vicoa_client and self.session_id:
                async with self._send_lock:
                    await self.vicoa_client.send_message(
                        content=content,
                        agent_type=self.agent_name,
                        agent_instance_id=self.session_id,
                        requires_user_input=False,
                    )
                self.logger.info(f"Sent feedback message: {content}")
        except Exception as e:
            self.logger.error(f"Failed to send feedback message: {e}")

    # ------------------------------------------------------------------
    # WS subscriber routing
    # ------------------------------------------------------------------

    async def _maybe_route_ask_user_question_reply(self, content: str) -> bool:
        """Resolve a pending AskUserQuestion future from an inbound reply.

        Called eagerly from ``_route`` — *not* from the user-message queue
        — because ``_handle_ask_user_question`` is awaiting on the future at
        the same time the SDK has the runner blocked in ``can_use_tool``.
        ``_wait_for_user_input`` (which drains the queue) doesn't run until
        the next conversation turn boundary, so routing here is the only
        way a reply can unblock the callback.

        Returns True when the future was resolved (caller drops the message
        from the queue).
        """
        decoded = auq.decode_reply(content)
        if decoded is None:
            return False
        return self._auq_registry.resolve(decoded)

    async def _maybe_route_free_text_auq_answer(
        self, content: str, message_id: Optional[str] = None
    ) -> bool:
        """Treat a plain-text chat message as the answer to a pending question.

        The dashboard picker sends a structured control payload that
        ``_maybe_route_ask_user_question_reply`` resolves. But users often just
        type the answer in the chat box instead of clicking an option — and that
        plain text is not a control payload, so it used to fall through to the
        user-message queue while ``_handle_ask_user_question`` stayed blocked on
        its future (up to the 24 h timeout). The turn froze and no follow-up came
        back until a *later* picker submit or interrupt happened to resolve the
        future — the reported "answer doesn't come back until I send another
        message" bug.

        We map the typed text onto the first question as a ``text``-mode answer
        (``auq.reshape_answers`` leaves any further questions blank) and resolve
        the oldest pending future via the registry's FIFO fallback, so the turn
        continues immediately. Only fires when a question is actually open;
        otherwise returns False so the message routes normally. Called from
        ``_route`` *after* control-command routing, so an interrupt or gear-pill
        change typed while a question is open still wins.

        Unlike a picker submit (a control message the turn-end filters swallow),
        this is a *plain* user row. Consumed as the answer, it must not also
        resurface as a fresh prompt: the turn-end ``mark_message_requires_input``
        returns it in ``already_queued`` and it would run as a spurious extra
        turn. So we remember its id (``_enqueue_already_queued`` dedupes on it)
        and mark it consumed server-side (clears the web's queued-message pill).
        """
        if not content or not self._auq_registry.has_pending():
            return False
        payload: Dict[str, Any] = {
            "cancelled": False,
            "answers": [{"mode": "text", "text": content}],
            "display_answers": [{"label": content}],
            "request_id": None,
            "message_id": None,
        }
        resolved = self._auq_registry.resolve(payload)
        if resolved:
            self.logger.info(
                "Resolved pending AskUserQuestion from a typed chat answer"
            )
            # This row was consumed as the answer — keep it out of the next
            # turn's queue (both our local dedupe and the server's cursor).
            self._remember_message_id(message_id)
            if message_id and self.vicoa_client:
                try:
                    await self.vicoa_client.mark_message_consumed(message_id)
                except Exception:
                    self.logger.debug(
                        "mark_message_consumed for free-text AUQ answer failed",
                        exc_info=True,
                    )
        return resolved

    async def _maybe_route_permission_reply(self, content: str) -> bool:
        """Resolve a pending permission-prompt future from an inbound reply.

        Mirrors ``_maybe_route_ask_user_question_reply``. The dashboard
        currently sends plain text ("Allow once" / "Always allow" / "Deny")
        rather than a structured control message, so we resolve via the
        registry's FIFO match — unambiguous because only one permission
        prompt can be in flight per session at a time. Anything else falls
        through to the user-message queue path so it reaches
        ``_wait_for_user_input`` normally.

        Returns True when a future was resolved (caller drops the message
        from the queue — this is what prevents the §2c "Allow once" leak).
        """
        if not self._permission_registry.has_pending():
            return False
        return self._permission_registry.resolve_text(content)

    async def _maybe_route_control_command(self, content: str) -> bool:
        """Route a control command out of the user-message path.

        Most controls (model / effort / permission_mode) are pushed onto
        ``_control_command_queue`` and dispatched by ``_run_control_worker``.
        This is the fix for back-to-back gear-pill changes serializing:
        ``_handle_control_command`` for a ``model`` or ``effort`` change
        awaits ``_reconnect_claude_client`` (multi-second SDK reconnect),
        and inline-awaiting here would block ``_route`` from processing
        subsequent control messages until the reconnect finishes.

        Interrupts bypass the queue and run inline. They're time-sensitive
        (the user just pressed Stop) and must preempt any reconnect already
        running on the worker. ``_handle_interrupt`` itself is fast — it
        flips a flag, calls ``claude_client.interrupt()``, and cancels any
        pending AUQ / permission futures.

        Called from ``_route`` AFTER the AUQ and permission routers so AUQ
        submit/cancel replies and permission button clicks keep their
        existing paths.

        Returns True when the message was a control command (caller drops
        from queue), False otherwise.
        """
        # Display artifacts (e.g. AskUserQuestion answer summaries) must
        # not be queued OR routed as a real control — same logic as in
        # ``_handle_control_command``.
        if auq.is_persist_only_message(content):
            self.logger.info("eager route: ack persist_only message (not queued)")
            return True

        parsed = control_command.parse_control_command(content)
        if parsed is None:
            return False

        if parsed.get("setting") == "interrupt":
            await self._handle_control_command(content)
            return True

        await self._control_command_queue.put(content)
        return True

    async def _run_control_worker(self) -> None:
        """Drain ``_control_command_queue`` serially.

        Lives alongside the WS subscriber so ``_route`` never blocks on
        the multi-second reconnect inside a model / effort change. Each
        dispatch is independent: an exception in one control command is
        logged and the worker moves on to the next.
        """
        while self.running:
            try:
                content = await self._control_command_queue.get()
            except asyncio.CancelledError:
                return
            try:
                await self._handle_control_command(content)
            except Exception:
                self.logger.exception("control worker raised for %r", content[:160])
            finally:
                self._control_command_queue.task_done()

    async def _run_reconcile_backstop(self) -> None:
        """Re-fetch the persisted tail so a dropped realtime broadcast self-heals.

        Every user message reaches the runner over ONE fire-and-forget path:
        the backend commits, then ``post_broadcast`` POSTs the realtime update
        across the backend→server bridge (best-effort, never retried), the
        server fans it to this WS, and ``_route`` consumes it. There is no ack
        and — while the WS stays connected — no re-fetch. A dropped POST is
        therefore silent. Two user-visible failures follow, both reported:

        * An AskUserQuestion / permission **reply** is lost, so the
          ``poll_for_reply=False`` Future in ``_handle_ask_user_question`` /
          ``_handle_permission_prompt`` hangs until its 24 h timeout ("answer
          doesn't come back until I send another message").
        * The first message to a **just-woken** session (cold ``--resume``) is
          lost to the subscribe/catch-up race documented in ``initialize`` —
          it "activates" the session but the turn never runs; the *second*
          message works. On a cold start the WS watermark is ``None``, so this
          re-fetch replays ``after=None`` → the server's consumption-based
          ``last_read_message_id`` cursor, which returns exactly the
          unprocessed tail (no re-run of already-consumed turns) once the wake
          message has committed.

        So we re-issue the WS catch-up whenever the runner is **idle**
        (awaiting the next message) OR a **reply Future is pending** — the two
        states where a lost message has nothing else to recover it. During an
        active turn we skip: a mid-turn message dropped now is re-read at
        turn end by ``mark_message_requires_input``'s ``already_queued``
        remainder, and re-fetching mid-stream could race the turn. The
        ``CatchUpBuffer`` dedupes already-delivered rows, so a re-fetch is a
        no-op whenever the live push already worked.

        The WS re-fetch above only recovers a reply while the socket is up.
        A long AskUserQuestion wait (a multi-question picker takes far longer
        to fill in than a single one — median answer time in prod is ~5 min vs
        ~3 min) routinely outlives the connection: an idle disconnect or a
        laptop sleep leaves ``request_refetch`` a no-op (it writes to a dead
        socket), so the submit stays stranded until the WS finally reconnects
        or the *next* user message unblocks it — the reported "the answer only
        comes back after I send another message" bug. So when a **reply Future
        is pending** we additionally recover over REST
        (``_recover_pending_reply_via_rest``): a plain request/response that
        works regardless of socket state and resolves the future with the real
        structured answers, not the free-text fallback's best-effort guess.

        Neither sibling wrapper needs this: Paseo resolves in the same process
        that owns the client socket, and Happy's reply is an acked RPC. Vicoa's
        backend/server split forces the bridge hop *and* persists every message,
        so a periodic catch-up is both necessary and cheap.
        """
        while self.running:
            try:
                await asyncio.sleep(_RECONCILE_INTERVAL)
            except asyncio.CancelledError:
                return
            if not self._should_reconcile():
                continue
            ws = self._ws_client
            if ws is not None:
                try:
                    # request_refetch does a blocking socket write; keep it off
                    # the event loop so a slow send can't stall the turn.
                    await asyncio.to_thread(ws.request_refetch)
                    self.logger.debug("reconcile backstop re-fetched tail")
                except Exception:
                    self.logger.debug(
                        "reconcile backstop refetch failed", exc_info=True
                    )
            # WS-independent recovery for a stranded reply. Gated on a pending
            # reply Future (not the idle case) so it stays transient: Claude is
            # blocked inside ``can_use_tool`` with no agent POSTs in flight, so
            # the cursor advance this GET performs can't race a concurrent write
            # (the §2g hazard that moved this path off polling in the first
            # place).
            if (
                self._auq_registry.has_pending()
                or self._permission_registry.has_pending()
            ):
                await self._recover_pending_reply_via_rest()

    async def _recover_pending_reply_via_rest(self) -> None:
        """Recover a stranded AUQ/permission reply via a direct REST fetch.

        The WS re-fetch in ``_run_reconcile_backstop`` only fires on a live
        socket; this is the fallback for when the socket is down (idle drop,
        sleep) with a reply outstanding. Reads the persisted unread tail and
        routes each row through ``_route`` — exactly the path a websocket
        ``new-message`` takes — so the submit resolves the pending Future and
        any co-arriving chat message queues normally. Idempotent against the
        WS: ``_route`` dedupes queued rows by id and ``resolve`` is a no-op once
        the Future is settled, so a row delivered by both paths lands once.

        Best-effort: a failed GET (or a ``stale`` read from a concurrent
        reader) just retries on the next reconcile tick.
        """
        if not (self.vicoa_client and self.session_id):
            return
        try:
            messages, status = await self.vicoa_client.get_pending_messages_raw(
                self.session_id
            )
        except Exception:
            self.logger.debug("reconcile REST recovery fetch failed", exc_info=True)
            return
        if status != "ok" or not messages:
            return
        self.logger.info(
            "reconcile REST recovery fetched %d pending message(s) for a stranded reply",
            len(messages),
        )
        for msg in messages:
            sender = (msg.get("sender_type") or "").lower()
            if sender not in {"user", "human"}:
                continue
            content = msg.get("content") or ""
            attachments = tuple(extract_attachment_refs(msg.get("message_metadata")))
            if not content and not attachments:
                continue
            await self._route(content, attachments, msg.get("id"))

    def _should_reconcile(self) -> bool:
        """True when a dropped inbound message has nothing else to recover it.

        Two states: the runner is **idle** (``_awaiting_input`` — the wake
        message / next turn input would otherwise be stranded), or an
        AUQ/permission **reply Future is pending** (a lost reply would hang the
        ``can_use_tool`` callback). During an active turn both are False — a
        mid-turn drop is re-read at turn end via ``already_queued``.
        """
        return (
            self._awaiting_input
            or self._auq_registry.has_pending()
            or self._permission_registry.has_pending()
        )

    def _start_ws_client(self) -> None:
        """Spin up the session-scoped /ws subscriber on a background thread.

        Replaces the legacy SSE per-instance stream. ``SessionMessagesWsClient``
        handles hello, ``fetch_messages_request`` catch-up (so we don't need
        a separate ``get_pending_messages`` drain), live ``new-message``
        delivery, and reconnect-with-jitter. The sync callback is bridged
        into the asyncio loop via ``run_coroutine_threadsafe``.
        """
        ws_url = os.environ.get("VICOA_WS_URL") or derive_ws_url(self.vicoa_base_url)
        cli_version = os.environ.get("VICOA_CLI_VERSION")
        self._ws_client = SessionMessagesWsClient(
            ws_url=ws_url,
            api_key=self.vicoa_api_key,
            instance_id=self.session_id,
            on_user_message=self._on_ws_user_message,
            cli_version=cli_version,
            on_message_update=self._schedule_message_update,
            on_instance_update=self._schedule_instance_update,
        )
        self._ws_thread = threading.Thread(
            target=self._ws_client.run,
            name=f"claude-headless-ws-{self.session_id[:8]}",
            daemon=True,
        )
        self._ws_thread.start()
        self.logger.info("[Vicoa] WS subscriber connected to %s", ws_url)

    def _on_ws_user_message(self, body: Dict[str, Any]) -> None:
        """WS-thread callback: filter to USER messages and bridge to asyncio.

        ``body`` shape matches the ``new-message`` payload: ``{id, content,
        sender_type, created_at, ...}``. Broadcast also includes AGENT echoes
        of our own posts, so filter by sender. Exceptions raised here would
        otherwise crash the WS reader thread silently — catch and log.
        """
        try:
            sender = (body.get("sender_type") or "").lower()
            content = body.get("content") or ""
            attachments = tuple(extract_attachment_refs(body.get("message_metadata")))
            if sender not in {"user", "human"} or (not content and not attachments):
                return
            loop = self._loop
            if loop is None or loop.is_closed():
                return
            asyncio.run_coroutine_threadsafe(
                self._route(content, attachments, body.get("id")), loop
            )
        except Exception:
            self.logger.exception("[Vicoa] WS callback raised")

    def _schedule_instance_update(self, body: Dict[str, Any]) -> None:
        """WS-reader-thread entrypoint for instance row changes.

        Stops the runner when the session is archived/closed elsewhere. Hops
        onto the loop thread so the cancel is issued from the right place.
        """
        try:
            if not instance_update_requests_stop(body):
                return
            loop = self._loop
            if loop is None or loop.is_closed():
                return
            loop.call_soon_threadsafe(self._stop_from_instance_update)
        except Exception:
            self.logger.exception("[Vicoa] instance-update callback raised")

    def _stop_from_instance_update(self) -> None:
        self.logger.info("Session closed elsewhere; stopping headless runner")
        self._stopping = True
        self.running = False
        task = self._main_task
        if task is not None and not task.done():
            task.cancel()

    def _schedule_message_update(self, body: Dict[str, Any]) -> None:
        """WS-reader-thread entrypoint: hop onto the event loop thread.

        Exceptions raised here would otherwise crash the WS reader thread
        silently — catch and log (mirrors ``_on_ws_user_message`` above).
        """
        try:
            loop = self._loop
            if loop is None or loop.is_closed():
                return
            loop.call_soon_threadsafe(self._on_ws_message_update, body)
        except Exception:
            self.logger.exception("[Vicoa] WS callback raised")

    def _on_ws_message_update(self, body: Dict[str, Any]) -> None:
        md = body.get("message_metadata") or {}
        status = (md.get("queue") or {}).get("status")
        mid = body.get("id")
        if status == "cancelled" and mid:
            self._cancelled_message_ids.add(mid)
            self.logger.info(f"User cancelled queued message {mid}")

    def _remember_message_id(self, message_id: Optional[str]) -> bool:
        """Return True if newly seen; False if a duplicate. Unidentified
        messages (message_id is None) are always treated as new."""
        if not message_id:
            return True
        if message_id in self._seen_user_message_ids:
            return False
        if len(self._seen_user_message_order) == self._seen_user_message_order.maxlen:
            self._seen_user_message_ids.discard(self._seen_user_message_order[0])
        self._seen_user_message_order.append(message_id)
        self._seen_user_message_ids.add(message_id)
        return True

    async def _enqueue_already_queued(self, queued: List[Dict[str, Any]]) -> None:
        """Merge REST already_queued messages into the inbound queue, deduped
        against the WS channel. Preserves order; drops nothing but duplicates
        and cancelled ids."""
        for msg in queued:
            mid = msg.get("id")
            if mid in self._cancelled_message_ids:  # defined in Task B5
                continue
            if not self._remember_message_id(mid):
                continue
            content = msg.get("content") or ""
            attachments = tuple(extract_attachment_refs(msg.get("message_metadata")))
            if not content and not attachments:
                continue
            await self._user_message_queue.put(
                InboundUserMessage(content, attachments, mid)
            )

    async def _route(
        self,
        content: str,
        attachments: tuple[AttachmentRef, ...] = (),
        message_id: Optional[str] = None,
    ) -> None:
        """Route an inbound user message — the same fan-out as the legacy
        listener, just driven by the WS callback instead of the SSE for-loop.

        Order matters: AUQ and permission replies resolve in-flight futures
        before they're seen as plain user input; control commands queue
        out-of-band so a slow reconnect doesn't block this routing.
        """
        if content:
            if await self._maybe_route_ask_user_question_reply(content):
                return
            if await self._maybe_route_permission_reply(content):
                return
            if (
                permission_module.looks_like_permission_reply(content)
                and not self._permission_registry.has_pending()
                and not self._auq_registry.has_pending()
            ):
                # Only an *orphan* permission reply (no permission prompt AND no
                # open question). With a question open, a typed "Deny" / "Allow
                # once" is the user's answer to it — fall through to the
                # free-text AUQ handler below instead of dropping it.
                self.logger.info(
                    "Dropping orphan permission reply with no pending prompt"
                )
                return
            if await self._maybe_route_control_command(content):
                return
            # Last resort before the queue: if a question is open and this
            # wasn't a picker submit / permission / control reply, take the
            # typed text as the answer rather than stranding the paused turn.
            if await self._maybe_route_free_text_auq_answer(content, message_id):
                return
        if not self._remember_message_id(message_id):
            return
        await self._user_message_queue.put(
            InboundUserMessage(content, attachments, message_id)
        )

    async def _wait_for_user_input(self) -> Optional[InboundUserMessage]:
        """Wait for the next non-control user message from the inbound queue.

        Sets ``_awaiting_input`` for its duration so the reconcile backstop
        knows the runner is idle — the state where a message dropped by the
        fire-and-forget broadcast bridge has nothing else to recover it (no
        active turn to re-read it via ``already_queued``). See
        ``_run_reconcile_backstop``.
        """
        self._awaiting_input = True
        try:
            while self.running:
                try:
                    message = await asyncio.wait_for(
                        self._user_message_queue.get(), timeout=5.0
                    )
                except asyncio.TimeoutError:
                    if self.interrupt_requested:
                        return None
                    continue

                accepted = await self._accept_user_message(message)
                if accepted is None:
                    if self.interrupt_requested:
                        return None
                    continue
                # Coalesce any other messages the user already queued so a
                # burst runs as a single turn instead of one turn per message.
                return await self._coalesce_ready_messages(accepted)
            return None
        finally:
            self._awaiting_input = False

    async def _accept_user_message(
        self, message: InboundUserMessage
    ) -> Optional[InboundUserMessage]:
        """Filter one dequeued message.

        Returns the message when it is real user input, or ``None`` when it was
        a cancelled id (dropped) or a control command (handled inline). Shared
        by the blocking wait and the non-blocking coalesce drain so both apply
        identical filtering.
        """
        if message.message_id in self._cancelled_message_ids:
            self._cancelled_message_ids.discard(message.message_id)
            return None
        if message.content and await self._handle_control_command(message.content):
            return None
        return message

    async def _coalesce_ready_messages(
        self, first: InboundUserMessage
    ) -> InboundUserMessage:
        """Merge ``first`` with any messages already waiting in the queue.

        Only messages enqueued at call time are pulled (non-blocking
        ``get_nowait``); we never wait for more to arrive. Each is filtered
        like ``first`` (cancelled ids dropped, control commands handled). When
        nothing else is ready this returns ``first`` unchanged, so the common
        single-message path is untouched.
        """
        accepted = [first]
        while True:
            try:
                message = self._user_message_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            extra = await self._accept_user_message(message)
            if extra is not None:
                accepted.append(extra)
        if len(accepted) == 1:
            return first
        return await self._merge_inbound_messages(accepted)

    async def _merge_inbound_messages(
        self, messages: List[InboundUserMessage]
    ) -> InboundUserMessage:
        """Combine several user messages into one turn's input.

        Texts join on a blank line; attachments concatenate in arrival order.
        The primary (first) id rides the merged message so
        ``run_conversation_turn`` marks it consumed and tracks it as usual; the
        remaining ids are marked consumed here so their queued badges clear too.
        """
        primary = messages[0]
        content = "\n\n".join(m.content for m in messages if m.content)
        attachments: tuple[AttachmentRef, ...] = tuple(
            att for m in messages for att in m.attachments
        )
        for extra in messages[1:]:
            if extra.message_id and self.vicoa_client:
                try:
                    await self.vicoa_client.mark_message_consumed(extra.message_id)
                except Exception as e:
                    self.logger.warning(f"mark_message_consumed failed: {e}")
        return InboundUserMessage(
            content=content,
            attachments=attachments,
            message_id=primary.message_id,
        )

    async def _handle_control_command(self, content: str) -> bool:
        """Handle control commands from web UI.

        Returns: True if this was a control command (even if failed), False otherwise
        """
        # ``action: persist_only`` messages (e.g. AskUserQuestion answer
        # summaries) are display artifacts. Silently swallow them so they
        # don't flow back to Claude as the next turn's user input and don't
        # emit "Unknown setting" feedback.
        if auq.is_persist_only_message(content):
            self.logger.info("ack persist_only control message (no-op, not queued)")
            return True

        control = control_command.parse_control_command(content)
        if not control:
            return False

        setting = control["setting"]
        value = control.get("value")

        self.logger.info(
            f"Received control command: {setting}{'=' + str(value) if value is not None else ''}"
        )

        if setting == "permission_mode":
            # Mirrors claude_agent_sdk.types.PermissionMode. "auto" is the
            # Opus-4.7/4.8 mode the TUI exposes; "dontAsk" is also in the SDK
            # literal — surface both so the dashboard can drive them.
            valid_modes = [
                "default",
                "acceptEdits",
                "bypassPermissions",
                "plan",
                "auto",
                "dontAsk",
            ]
            if value not in valid_modes:
                await self._send_feedback_message(
                    f"Invalid permission mode '{value}'. Valid options: {', '.join(valid_modes)}"
                )
            else:
                previous_mode = self.permission_mode
                applied = False
                via_reconnect = False
                try:
                    if self.claude_client:
                        await self.claude_client.set_permission_mode(
                            cast(PermissionMode, value)
                        )
                        applied = True
                    else:
                        await self._send_feedback_message(
                            "Cannot change permission mode: Claude client not initialized"
                        )
                except Exception as e:
                    # ``auto`` is the one permission mode the CLI validates
                    # against the *live* model — a model classifier gates it, so
                    # the CLI refuses with "auto mode unavailable for this model"
                    # when the live client's model isn't auto-capable (e.g. the
                    # model the CLI actually resolved drifted from ``self.model``).
                    # Recover in two steps, cheapest first, so the common case
                    # keeps the *live* client and its status/feedback flow — the
                    # signal the mobile/desktop "vibing" indicator rides on —
                    # instead of the disruptive reconnect:
                    #   1. Re-assert the model on the SAME live client and retry.
                    #      No teardown, so clients see the change apply exactly
                    #      like any other live permission toggle.
                    #   2. Only if that can't take, fall back to a full reconnect
                    #      (re-asserts model + auto together at connect, but tears
                    #      the client down — slower, and it interrupts the live
                    #      status/feedback flow, so keep it a last resort).
                    # Other modes have no model gate, so their failures are real.
                    if value == "auto":
                        self.logger.warning(
                            "Live set_permission_mode('auto') failed (%s); recovering",
                            e,
                        )
                        if self.claude_client and self.model:
                            try:
                                await self.claude_client.set_model(self.model)
                                await self.claude_client.set_permission_mode(
                                    cast(PermissionMode, value)
                                )
                                applied = True
                                self.logger.info(
                                    "Recovered 'auto' by re-asserting model %s "
                                    "on the live client",
                                    self.model,
                                )
                            except Exception as retry_exc:
                                self.logger.info(
                                    "Live model re-assert didn't take 'auto' "
                                    "(%s); reconnecting",
                                    retry_exc,
                                )
                        if not applied:
                            self.permission_mode = cast(PermissionMode, value)
                            if await self._reconnect_claude_client():
                                applied = True
                                via_reconnect = True
                            else:
                                self.permission_mode = previous_mode
                                await self._send_feedback_message(
                                    f"Failed to change permission mode: {str(e)}"
                                )
                    else:
                        self.logger.error(f"Failed to change permission mode: {e}")
                        await self._send_feedback_message(
                            f"Failed to change permission mode: {str(e)}"
                        )

                if applied:
                    # Cache the new mode so subsequent ClaudeAgentOptions
                    # rebuilds reflect it (idempotent when the reconnect path
                    # already set it above).
                    self.permission_mode = cast(PermissionMode, value)
                    # Persist so the mobile gear sheet shows it. The live SDK
                    # call only flips runtime state; without this PATCH the
                    # agent_instances row keeps the old value (the TUI path
                    # PATCHes at the JSON-parse layer in input_request_manager;
                    # the headless path runs the control loop here).
                    if self.vicoa_client and self.session_id:
                        try:
                            await self.vicoa_client.patch_agent_instance(
                                self.session_id,
                                session_config={"permission_mode": value},
                            )
                            self.logger.info(
                                f"PATCH session_config {{permission_mode: {value!r}}}"
                            )
                        except Exception as exc:
                            self.logger.warning(
                                "Failed to PATCH session_config: %s", exc
                            )
                    await self._send_feedback_message(
                        f"Permission mode changed to {value}"
                    )
                    await self._mark_awaiting_input_after_settings_change(
                        "permission_mode"
                    )
                    self.logger.info(
                        "Successfully changed permission mode to: %s%s",
                        value,
                        " (via reconnect)" if via_reconnect else "",
                    )

        elif setting == "thinking":
            target_state = value == "on"

            if target_state == self.enable_thinking:
                state_name = "on" if target_state else "off"
                await self._send_feedback_message(f"Thinking is already {state_name}")
            else:
                self.logger.info(
                    f"Toggling thinking from {self.enable_thinking} to {target_state}"
                )
                self.enable_thinking = target_state
                success = await self._reconnect_claude_client()

                if success:
                    state_name = "on" if target_state else "off"
                    await self._send_feedback_message(f"Thinking turned {state_name}")
                    self.logger.info(f"Successfully toggled thinking to {state_name}")
                else:
                    self.enable_thinking = not target_state
                    await self._send_feedback_message(
                        "Failed to toggle thinking. Please try again or restart the session."
                    )
                    self.logger.error("Failed to toggle thinking, rolled back state")

        elif setting == "model":
            if value == self.model:
                await self._send_feedback_message(f"Model is already {value}")
            else:
                previous = self.model
                self.model = value
                success = await self._reconnect_claude_client()
                if success and self.vicoa_client and self.session_id:
                    try:
                        await self.vicoa_client.patch_agent_instance(
                            self.session_id, session_config={"model": value}
                        )
                    except Exception:
                        self.logger.warning(
                            "Failed to PATCH session_config", exc_info=True
                        )
                    await self._send_feedback_message(f"Model changed to {value}")
                    await self._mark_awaiting_input_after_settings_change("model")
                elif not success:
                    self.model = previous
                    await self._send_feedback_message(
                        "Failed to change model. Please try again or restart the session."
                    )

        elif setting == "effort":
            # Claude SDK calls this `thinking_effort`; mobile sends the unified
            # `effort` wire setting (cross-agent). Mapping is internal.
            if value == self.thinking_effort:
                await self._send_feedback_message(f"Effort is already {value}")
            else:
                previous = self.thinking_effort
                self.thinking_effort = value
                success = await self._reconnect_claude_client()
                if success and self.vicoa_client and self.session_id:
                    try:
                        await self.vicoa_client.patch_agent_instance(
                            self.session_id,
                            session_config={"thinking_effort": value},
                        )
                    except Exception:
                        self.logger.warning(
                            "Failed to PATCH session_config", exc_info=True
                        )
                    await self._send_feedback_message(f"Effort changed to {value}")
                    await self._mark_awaiting_input_after_settings_change("effort")
                elif not success:
                    self.thinking_effort = previous
                    await self._send_feedback_message(
                        "Failed to change effort. Please try again or restart the session."
                    )

        elif setting == "interrupt":
            await self._handle_interrupt()

        elif setting == "ask_user_question":
            # ``_route`` already tried to resolve a pending future via
            # ``_maybe_route_ask_user_question_reply`` before enqueueing. If
            # we reach here it's because no pending future matched — either
            # a stale echo for an already-resolved request, or a reply that
            # arrived while the queue was being drained between turns.
            # Either way, silently acknowledge. The original decoding
            # happens inline in ``_handle_ask_user_question``.
            decoded = auq.decode_reply(content)
            if decoded is not None and self._auq_registry.resolve(decoded):
                self.logger.debug("resolved pending AUQ future from queue path")
            else:
                self.logger.debug(
                    "ack ask_user_question control reply (no pending future)"
                )

        else:
            await self._send_feedback_message(f"Unknown setting '{setting}'")

        return True

    async def _process_control_messages(self, messages: List[str]) -> None:
        """Process control commands from queued messages without returning content."""
        for message in messages:
            await self._handle_control_command(message)

    async def _filter_control_commands(
        self, messages: List[Dict[str, Any]]
    ) -> List[InboundUserMessage]:
        """Filter out control commands from queued message dicts and handle them."""
        filtered: List[InboundUserMessage] = []
        for msg in messages:
            content = msg.get("content") or ""
            if content and await self._handle_control_command(content):
                continue
            attachments = tuple(extract_attachment_refs(msg.get("message_metadata")))
            if content or attachments:
                filtered.append(InboundUserMessage(content, attachments))
        return filtered

    def _attachment_block(
        self,
        ref: AttachmentRef,
        data: bytes,
        mime_type: str,
        notes: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Pick the best inline block for one attachment, or park it on disk.

        Images become base64 image blocks and PDFs that fit under the request
        limit become base64 document blocks — both read natively by the model.
        Everything else (and oversized PDFs) is written under
        ``~/.vicoa/attachments/<instance>/`` and referenced by path in a note;
        Claude's Read tool opens it. Returns the inline block, or ``None`` when
        the attachment was delivered by path (a note is appended instead).
        """
        b64 = base64.b64encode(data).decode("ascii")
        if is_image_mime(mime_type):
            return {
                "type": "image",
                "source": {"type": "base64", "media_type": mime_type, "data": b64},
            }
        if mime_type == "application/pdf" and len(data) <= _MAX_INLINE_ATTACHMENT_BYTES:
            return {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": b64,
                },
            }
        local = save_attachment(attachments_dir(self.session_id), ref, data, mime_type)
        notes.append(attachment_note(local))
        return None

    async def _build_query_input(self, message: InboundUserMessage) -> Union[str, Any]:
        """Build the SDK ``query()`` input for a user message.

        Plain text goes through as a string (unchanged legacy path). When
        attachments are present, bytes are fetched from Vicoa and delivered by
        type (see ``_attachment_block``): images and small PDFs inline as
        base64 blocks, everything else written to disk and referenced by path.
        Failed downloads degrade to a text note so the agent knows something
        was meant to be attached.
        """
        if not message.attachments:
            return message.content

        blocks: List[Dict[str, Any]] = []
        notes: List[str] = []
        for ref in message.attachments:
            try:
                if not self.vicoa_client:
                    raise RuntimeError("vicoa client not initialized")
                data, mime_type = await self.vicoa_client.download_attachment(ref.id)
                block = self._attachment_block(ref, data, mime_type, notes)
                if block is not None:
                    blocks.append(block)
            except Exception:
                self.logger.exception(
                    "[Vicoa] Failed to download attachment %s; sending note instead",
                    ref.id,
                )
                notes.append(unavailable_note(ref))

        text = "\n".join(part for part in [message.content, *notes] if part)
        if not blocks:
            # No inline blocks (downloads failed, or all delivered by path) —
            # fall back to the plain-text path carrying any path/failure notes.
            return text
        if text:
            blocks.append({"type": "text", "text": text})

        message_dict = {
            "type": "user",
            "message": {"role": "user", "content": blocks},
            "parent_tool_use_id": None,
            "session_id": "default",
        }

        async def _single() -> Any:
            yield message_dict

        return _single()

    async def _flush_usage(self) -> None:
        """PATCH the merged usage blob onto instance_metadata.usage.

        Best-effort: skips when nothing changed (dedupe), and swallows any
        error so a usage stamp can never break a turn.
        """
        if not (self.vicoa_client and self.session_id):
            return
        core = self._usage.core()
        if core is None or core == self._usage_last_core:
            return
        blob = self._usage.blob()
        if blob is None:
            return
        try:
            await self.vicoa_client.patch_agent_instance(
                self.session_id, instance_metadata={"usage": blob}
            )
            self._usage_last_core = core
        except Exception:
            self.logger.debug("Failed to flush usage blob", exc_info=True)

    async def _stamp_context_usage(
        self,
        used_tokens: Optional[int],
        *,
        model: Optional[str] = None,
        model_usage: Optional[dict] = None,
        cost_usd: Optional[float] = None,
    ) -> None:
        """Record the context fill carried by a message we already received.

        ``used_tokens`` must come from a **single request** — see
        ``usage.claude_context_used_tokens`` for why summing a turn is wrong.

        Deliberately derived in-band rather than via the SDK's
        ``get_context_usage()`` control request: that added a round-trip which
        could time out (blanking the reading), only ran at end-of-turn, and was
        skipped entirely on turns that left background sub-agents running.
        """
        changed = self._usage.latch_context_max(
            usage_mod.claude_context_window_from_model_usage(model_usage)
        )
        # Seeds only fill the gap until ``model_usage`` reports the real size.
        # The configured slug (``self.model``) goes first: it is what the user
        # picked and carries the ``[1m]`` marker, which the runtime id on
        # AssistantMessage never does — seeding from the runtime id alone made
        # 1M sessions show a 200k window until the first turn completed.
        changed |= self._usage.latch_context_max(
            usage_mod.claude_context_window_for_model(self.model), seed=True
        )
        changed |= self._usage.latch_context_max(
            usage_mod.claude_context_window_for_model(model), seed=True
        )
        changed |= self._usage.set_context_usage(used_tokens, cost_usd)
        if changed:
            await self._flush_usage()

    def _schedule_limits_fetch(self) -> None:
        """Throttled, non-blocking trigger for the Claude plan-usage fetch.

        Runs the fetch as a background task so a slow/hanging usage API can't
        delay turn completion. The throttle stamp is set before spawning so a
        burst of turns schedules at most one fetch per interval.
        """
        now = time.monotonic()
        if now - self._last_limits_fetch < _CLAUDE_LIMITS_FETCH_INTERVAL:
            return
        if self._limits_fetch_task is not None and not self._limits_fetch_task.done():
            return
        self._last_limits_fetch = now
        self._limits_fetch_task = asyncio.create_task(self._fetch_claude_limits())

    async def _fetch_claude_limits(self) -> None:
        """Fetch the OAuth plan-usage snapshot and merge Session/Weekly windows.

        Best-effort: only updates when the fetch returns usable windows, so an
        API-key setup / expired token / offline / error leaves the limits
        section hidden (never wipes a previously-shown snapshot).
        """
        try:
            token = read_claude_oauth_token()
            if not token:
                return
            response = await fetch_claude_usage(token)
            limits = usage_mod.claude_limits_from_oauth(response)
            if limits and self._usage.set_limits(limits):
                await self._flush_usage()
        except Exception:
            self.logger.debug("Failed to fetch Claude plan usage", exc_info=True)

    async def run_conversation_turn(
        self, user_input: InboundUserMessage
    ) -> Optional[InboundUserMessage]:
        """Run a single conversation turn with Claude and return next user input.

        The turn does not read the SDK stream itself — the session-lifetime
        reader does (``_run_stream_reader``), forwarding messages as they
        arrive. This method opens a "foreground" turn entry, sends the
        ``query()``, and parks on ``_foreground_turn_done`` until the reader
        closes the entry at the turn's ``ResultMessage``.
        """
        if user_input.message_id in self._cancelled_message_ids:
            self._cancelled_message_ids.discard(user_input.message_id)
            return await self._wait_for_user_input()

        self.logger.info(
            f"Starting conversation turn with input: {user_input.content[:100]}... "
            f"({len(user_input.attachments)} attachment(s))"
        )

        self.interrupt_requested = False
        # Reset so the post-turn mark-requires-input call only ever fires
        # against a message the CURRENT turn produced. Without this, an
        # interrupted turn (which posted nothing) leaves the previous
        # turn's id in place, and the next turn that also produces no
        # agent content re-marks the old message — API returns 400
        # "Message already requires user input". Observed in session
        # d736c51d-… at 23:59:13.
        self.last_message_id = None

        if user_input.message_id and self.vicoa_client:
            try:
                await self.vicoa_client.mark_message_consumed(user_input.message_id)
            except Exception as e:
                self.logger.warning(f"mark_message_consumed failed: {e}")

        # Re-assert ACTIVE now the turn is actually starting — see
        # ``_mark_active_for_turn`` for the AWAITING_INPUT-while-working bug this
        # closes. Runs after mark_message_consumed, mirroring the ACP order.
        await self._mark_active_for_turn()

        if not self.claude_client:
            self.logger.error("Claude client not initialized")
            return None

        try:
            query_input = await self._build_query_input(user_input)
            # The reader normally already runs (started at connect); this is
            # a cheap defensive re-arm for tests and edge paths.
            self._ensure_stream_reader()
            # Open the foreground turn BEFORE query() so its ResultMessage
            # can't race the bookkeeping. FIFO with any autonomous turn the
            # CLI already has open: the CLI serializes turns, so results
            # close entries oldest-first.
            self._foreground_turn_done = asyncio.Event()
            self._foreground_settle_deferred = False
            self._open_turns.append("foreground")
            try:
                await self.claude_client.query(query_input)
            except BaseException:
                # The turn never started; don't leave a phantom entry for a
                # later Result to close.
                try:
                    self._open_turns.remove("foreground")
                except ValueError:
                    pass
                raise
            self.conversation_started = True

            interrupted = await self._await_foreground_turn_close()

            if interrupted:
                self.logger.info(
                    "Skipping input request because current task was interrupted"
                )
                # Background sub-agents from the aborted turn are abandoned
                # with it. Re-assert AWAITING_INPUT — any message POSTed
                # between the Stop and the closing Result set the row back
                # to ACTIVE.
                self._pending_background_tasks.clear()
                await self._settle_awaiting_input_after_interrupt()
                return None

            self.logger.info("Conversation turn completed")

            if self._foreground_settle_deferred:
                # The agent finished its own turn but left background
                # sub-agent(s) running (snapshot taken by the reader at close
                # time). Defer the awaiting-input settle (and its push
                # notification) to the autonomous close that fires when they
                # report — the reader keeps streaming their output meanwhile,
                # and the user can already send the next message.
                self.logger.info(
                    "Turn completed with background sub-agent(s) still "
                    "running; deferring the awaiting-input settle"
                )
            else:
                if not self.last_message_id:
                    # Turn produced no agent content (e.g. Claude SDK returned
                    # only a ResultMessage immediately). Post a fallback prompt
                    # so the user has something to act on; the settle below
                    # marks it as awaiting input.
                    await self.send_to_vicoa("What would you like me to do next?")
                await self._settle_turn_end()

            return await self._wait_for_user_input()

        except CLINotFoundError:
            error_msg = "❌ Claude Code CLI not found. Please install it with: npm install -g @anthropic-ai/claude-code"
            await self.send_to_vicoa(error_msg)
            self.logger.error(error_msg)
            return None
        except ProcessError as e:
            # Raised here only from query() (a write to a dead CLI). Stream-
            # side failures — including CLIJSONDecodeError buffer overflows —
            # surface in the reader task and go through ``_recover_stream``.
            error_msg = f"❌ Claude Code process error: {e}"
            await self.send_to_vicoa(error_msg)
            self.logger.error(error_msg)
            return None
        except Exception as e:
            error_msg = f"❌ Error during conversation turn: {e}"
            await self.send_to_vicoa(error_msg)
            self.logger.error(error_msg)
            return None

    def _install_signal_handlers(self) -> None:
        """Route SIGTERM through graceful shutdown.

        ``vicoa stop sessions`` (and the daemon, when it learns to reap its
        children) sends SIGTERM. The default SIGTERM action terminates the
        process immediately — the ``finally`` block in ``run()`` never
        executes, so ``end_session()`` is never called and the dashboard
        shows the instance stuck in ACTIVE / AWAITING_INPUT forever.

        Cancelling ``_main_task`` instead raises ``CancelledError`` inside
        ``run()``, which is caught alongside ``KeyboardInterrupt`` and falls
        through to the cleanup path that calls ``end_session()`` (→ status
        COMPLETED). SIGINT already worked this way via KeyboardInterrupt;
        this gives SIGTERM the same treatment.
        """

        def _on_sigterm() -> None:
            self.logger.info("Received SIGTERM; shutting down gracefully")
            self.running = False
            if self._main_task is not None and not self._main_task.done():
                self._main_task.cancel()

        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGTERM, _on_sigterm)
        except (NotImplementedError, RuntimeError, ValueError):
            # add_signal_handler is unavailable on Windows and outside the
            # main thread. Headless normally runs as the main thread of its
            # own process, so this only no-ops on Windows — where the stop
            # path uses `taskkill /F` and graceful cleanup isn't reachable
            # anyway.
            self.logger.debug("SIGTERM handler not installed (unsupported here)")

    async def run(self):
        """Main run loop for the headless Claude runner.

        ``initialize()`` POSTs the optional ``--prompt`` as a user message
        and returns; the broadcast arrives back through our own /ws
        subscription and enters the loop below via
        ``_user_message_queue``. There is no special first-turn path —
        turn 1 and turn N go through the same dequeue+``run_conversation_turn``
        sequence. Mirrors ``codex_native.run()`` for symmetry across
        wrappers and removes the duplicate-first-turn bug observed in
        session 40e02f0a-….
        """
        self._main_task = asyncio.current_task()
        # The WS callback runs on a non-asyncio thread; capture the loop here
        # so ``run_coroutine_threadsafe`` can schedule ``_route(content)``.
        self._loop = asyncio.get_running_loop()
        self._install_signal_handlers()
        try:
            await self.initialize()

            current_input: Optional[InboundUserMessage] = None
            while self.running:
                if not current_input:
                    self.logger.debug("No current input, waiting for user message...")
                    current_input = await self._wait_for_user_input()

                if not current_input:
                    continue

                next_input = await self.run_conversation_turn(current_input)
                current_input = next_input

        except (KeyboardInterrupt, asyncio.CancelledError):
            self.logger.info("Received interrupt/cancel signal, shutting down...")
            self.running = False
        except Exception as e:
            self.logger.error(f"Fatal error in headless runner: {e}")
            if self.vicoa_client and self.session_id:
                await self.send_to_vicoa(
                    f"Headless Claude encountered a fatal error: {e}"
                )
        finally:
            self.running = False
            self._auq_registry.cancel_all()
            self._permission_registry.cancel_all()

            # Stop heartbeating before the terminal status is written, so an
            # in-flight beat can't make a finished session look freshly alive.
            if self._heartbeat is not None:
                try:
                    await self._heartbeat.stop()
                except Exception:
                    self.logger.exception("Heartbeat stop failed")

            if self._ws_client is not None:
                try:
                    self._ws_client.stop()
                except Exception:
                    self.logger.exception("WS client stop failed")
            if self._ws_thread is not None and self._ws_thread.is_alive():
                # Daemon thread: process exit will reap it even if join times out.
                self._ws_thread.join(timeout=5.0)

            if self._control_worker_task:
                self._control_worker_task.cancel()
                try:
                    await self._control_worker_task
                except asyncio.CancelledError:
                    pass

            if self._reconciler_task:
                self._reconciler_task.cancel()
                try:
                    await self._reconciler_task
                except asyncio.CancelledError:
                    pass

            if self._status_watchdog_task:
                self._status_watchdog_task.cancel()
                try:
                    await self._status_watchdog_task
                except asyncio.CancelledError:
                    pass

            if self._stream_recovery_task and not self._stream_recovery_task.done():
                self._stream_recovery_task.cancel()
                try:
                    await self._stream_recovery_task
                except asyncio.CancelledError:
                    pass

            # Stop the reader before disconnecting so the teardown isn't
            # mistaken for a mid-session stream failure.
            await self._stop_stream_reader()

            if self.claude_client:
                try:
                    await self.claude_client.disconnect()
                    self.logger.info("Claude client closed")
                except Exception as e:
                    self.logger.error(f"Error closing Claude client: {e}")

            if self.vicoa_client and self.session_id:
                try:
                    await self.vicoa_client.end_session(self.session_id)
                    self.logger.info("Session ended successfully")
                except Exception as e:
                    self.logger.error(f"Error ending session: {e}")

            if self.vicoa_client:
                await self.vicoa_client.close()


def parse_list_argument(value: str) -> List[str]:
    """Parse a comma-separated list argument."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def main():
    """Main entry point for headless Claude Code integration."""
    parser = argparse.ArgumentParser(
        description="Headless Claude Code integration with Vicoa",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--api-key",
        default=os.environ.get("VICOA_API_KEY"),
        help="Vicoa API key (defaults to VICOA_API_KEY env var)",
    )
    parser.add_argument(
        "--base-url",
        default="https://agents.vicoa.ai",
        help="Vicoa base URL",
    )

    parser.add_argument(
        "--prompt",
        default=None,
        help="Optional initial prompt to POST as the first user message. "
        "When omitted, the session starts empty and waits for user input "
        "(matches codex_native / opencode_acp).",
    )
    parser.add_argument(
        "--permission-mode",
        choices=["acceptEdits", "auto", "bypassPermissions", "default", "plan"],
        help="Permission mode for Claude Code (auto = Sonnet 4.6+ / Opus 4.7+ only)",
    )
    parser.add_argument(
        "--allowed-tools",
        type=str,
        help="Comma-separated list of allowed tools (e.g., 'Read,Write,Bash')",
    )
    parser.add_argument(
        "--disallowed-tools", type=str, help="Comma-separated list of disallowed tools"
    )
    parser.add_argument(
        "--cwd",
        type=str,
        help="Working directory for Claude (defaults to current directory)",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=os.environ.get("VICOA_AGENT_INSTANCE_ID"),
        help="Custom session ID (defaults to VICOA_AGENT_INSTANCE_ID env var or random UUID)",
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help=(
            "Resume an existing agent instance, continuing its prior "
            "conversation. Takes the instance id, which is also Claude's own "
            "session id. Requires the transcript to still be on this machine, "
            "under the same working directory."
        ),
    )
    parser.add_argument(
        "--name",
        type=str,
        default=os.environ.get("VICOA_AGENT_TYPE", "Claude Code"),
        help="Name/type of the agent (defaults to VICOA_AGENT_TYPE env var or 'Claude Code')",
    )
    parser.add_argument(
        "--enable-thinking",
        action="store_true",
        help="Enable thinking mode (budget_tokens=1024)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Claude model id (e.g. claude-sonnet-4-6). Catalog ids only; "
        "see plans/new-session-model-selection.md §4.1.",
    )
    parser.add_argument(
        "--thinking-effort",
        type=str,
        default=None,
        choices=["off", "low", "medium", "high", "max", "xhigh"],
        help="Adaptive thinking effort tier. `off` disables thinking; any "
        "other value enables adaptive thinking and takes precedence over "
        "--enable-thinking when both are passed (plan §3.6 dual-write).",
    )
    # Honor VICOA_DEBUG=1/true/yes/on as a fallback so daemon-spawned
    # sessions can be flipped to debug without rebuilding the spawn-request
    # metadata — just export the env var and restart the daemon.
    parser.add_argument(
        "--debug",
        action="store_true",
        default=os.environ.get("VICOA_DEBUG", "").strip().lower()
        in {"1", "true", "yes", "on"},
        help=(
            "Enable DEBUG logging in ~/.vicoa/claude_headless/<session>.log "
            "(surfaces 'User message (not forwarding)' and other filter trace)."
        ),
    )

    args, unknown_args = parser.parse_known_args()

    if not args.api_key:
        logger = logging.getLogger(__name__)
        logger.error(
            "Error: Vicoa API key is required. Provide via --api-key or set VICOA_API_KEY environment variable."
        )
        sys.exit(1)

    # --resume names the instance to continue. Vicoa pins Claude's own session
    # id to the instance id at first launch (session_id=), so the id to resume
    # on IS the instance id — no separate handle to look up.
    resume_session_id = getattr(args, "resume", None)
    session_id = (
        resume_session_id
        or (
            args.session_id if hasattr(args, "session_id") and args.session_id else None
        )
        or str(uuid.uuid4())
    )
    logger = setup_logging(session_id, debug=args.debug)

    allowed_tools = (
        parse_list_argument(args.allowed_tools) if args.allowed_tools else None
    )
    disallowed_tools = (
        parse_list_argument(args.disallowed_tools) if args.disallowed_tools else None
    )

    extra_args: Dict[str, Optional[str]] = {}
    i = 0
    while i < len(unknown_args):
        arg = unknown_args[i]
        if arg.startswith("--"):
            key = arg[2:]
            if i + 1 < len(unknown_args) and not unknown_args[i + 1].startswith("-"):
                extra_args[key] = unknown_args[i + 1]
                i += 2
            else:
                extra_args[key] = None
                i += 1
        else:
            i += 1

    runner = HeadlessClaudeRunner(
        vicoa_api_key=args.api_key,
        session_id=session_id,
        vicoa_base_url=args.base_url,
        initial_prompt=args.prompt,
        extra_args=extra_args,
        permission_mode=args.permission_mode,
        allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,
        cwd=args.cwd,
        agent_name=args.name,
        enable_thinking=args.enable_thinking,
        model=args.model,
        thinking_effort=args.thinking_effort,
        debug=args.debug,
        is_resuming=bool(resume_session_id),
    )

    logger.info("Starting headless Claude Code session...")

    try:
        asyncio.run(runner.run())
    except (KeyboardInterrupt, asyncio.CancelledError):
        # CancelledError can surface here if a SIGTERM-triggered cancel
        # propagates past run()'s own handler. The cleanup (end_session)
        # already ran in run()'s finally block — just exit quietly.
        logger.info("Headless Claude session interrupted")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
