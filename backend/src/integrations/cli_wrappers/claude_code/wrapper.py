"""New modular Claude Code wrapper.

This is the main orchestrator that composes all refactored modules
into a cohesive wrapper implementation.
"""

import argparse
import logging
import os
import select
import signal
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional, TextIO

from vicoa.utils import get_project_path

from .config import ClaudeWrapperConfig, VICOA_WRAPPER_LOG_DIR
from .detection import (
    PermissionDetector,
    PlanDetector,
    QuestionDetector,
    ControlDetector,
)
from .messaging import (
    AskQuestionCollector,
    MessageProcessor,
    MessageQueue,
    InputRequestManager,
)
from .monitoring import HeartbeatManager, JSONLMonitor
from .session_reset_handler import SessionResetHandler
from .state import SessionState, ToggleManager
from .terminal import ANSICleaner, TerminalBuffer, PTYManager
from .terminal.terminal_parser import TerminalRenderer
from .utils import find_claude_cli, InputHandler
from integrations.cli_wrappers.shared import close_async_on_loop
from vicoa.sdk.async_client import AsyncVicoaClient
from vicoa.sdk.client import VicoaClient


class _WrapperLogHandler(logging.Handler):
    """Routes Python ``logging`` records through ``ClaudeWrapper.log``.

    Defined at module scope (not nested in ``_install_root_logging_handler``)
    so ``isinstance`` checks succeed across multiple installs — re-running
    install in the same process must replace the prior handler, not append.
    """

    def __init__(self, log_func: Callable[[str], None]) -> None:
        super().__init__()
        self.log_func = log_func

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.log_func(f"[{record.levelname}] {record.name}: {record.getMessage()}")
        except Exception:
            pass


class ClaudeWrapper:
    """Modular Claude Code wrapper using composition.

    This wrapper composes specialized modules to provide a clean,
    maintainable architecture that's easy to modify when Claude CLI changes.
    """

    # A single detector no-detect tick is not enough to trust that a modal
    # really disappeared from the terminal: the renderer can produce a
    # slightly different clean_buffer one tick to the next, a Claude CLI
    # spinner repaint can briefly disrupt structure, or the user can move
    # the cursor onto a non-default option (our strict detector requires
    # the cursor on ``1``). Require N consecutive no-detects (~4.5s at
    # 1.5s poll interval) before treating the modal as gone and clearing
    # any cached pending state.
    SELF_HEAL_DARK_TICKS_REQUIRED: int = 3

    # Graceful shutdown timing on SIGTERM/SIGHUP.
    # Claude's TUI treats the first Ctrl+C as "interrupt current turn / show
    # exit-confirm" and the second as "exit now" — only the second triggers
    # the resume-hint render. The gap must be long enough for the TUI to
    # finish handling the first key (interrupt-and-reprompt takes ~150 ms on
    # a snappy session) and short enough that the "Press Ctrl+C again to
    # exit" prompt hasn't timed out. 300 ms is well inside that window.
    # SHUTDOWN_GRACE_S bounds the total wait so ``vicoa stop`` callers with
    # a SIGKILL timer always see a clean wrapper exit; if Claude refuses to
    # die we SIGTERM the child as a backstop before flipping ``running``.
    SHUTDOWN_SECOND_CTRLC_DELAY_S: float = 0.3
    SHUTDOWN_GRACE_S: float = 3.0

    def __init__(self, config: ClaudeWrapperConfig):
        """Initialize wrapper with configuration.

        Args:
            config: Wrapper configuration
        """
        self.config = config
        self.running = True

        # Setup logging
        self.debug_log_file: Optional[TextIO] = None
        self._init_logging()

        # Initialize Vicoa clients
        self.vicoa_client_sync: Optional[VicoaClient] = None
        self.vicoa_client_async: Optional[AsyncVicoaClient] = None
        self._init_vicoa_clients()

        # Initialize terminal management
        self.pty_manager = PTYManager(log_func=self.log)
        self.terminal_buffer = TerminalBuffer(max_size=config.terminal_buffer_max_size)
        self.ansi_cleaner = ANSICleaner()

        # Initialize detectors
        # Order matters: more specific detectors should come first
        # PlanDetector is more specific than PermissionDetector for "Would you like to proceed" prompts
        from collections import OrderedDict

        self.detectors = OrderedDict(
            [
                ("plan", PlanDetector()),
                ("permission", PermissionDetector()),
                ("question", QuestionDetector()),
                ("control", ControlDetector()),
            ]
        )

        # Initialize state management
        self.session_state = SessionState(
            is_resuming=config.is_resuming,
            idle_delay=config.idle_delay,
            terminal_buffer=self.terminal_buffer,
        )
        self.toggle_manager = ToggleManager(
            initial_permission_mode=config.permission_mode,
            write_to_pty_func=self.pty_manager.write_to_pty,
            read_pty_func=self._read_pty_as_str,
            log_func=self.log,
        )

        # Initialize messaging
        self.message_queue = MessageQueue()
        self.message_processor = MessageProcessor(
            agent_instance_id=config.agent_instance_id,
            agent_name=config.name,
            vicoa_client=self.vicoa_client_sync,
            log_func=self.log,
        )

        # Session reset handler
        self.reset_handler = SessionResetHandler(log_func=self.log)

        # Initialize monitoring
        self.heartbeat = HeartbeatManager(
            agent_instance_id=config.agent_instance_id,
            base_url=config.base_url,
            vicoa_client=self.vicoa_client_sync,
            interval=config.heartbeat_interval,
            log_func=self.log,
        )
        # Input handler
        self.input_handler = InputHandler()

        # Threading
        self.send_message_lock = threading.Lock()
        self.requested_input_messages: set[str] = set()
        self.last_pty_output_time: float = 0.0

        # Prompt checking optimization
        self._prompt_check_start_time: Optional[float] = None
        self._last_checked_buffer_size: int = 0
        self._last_prompt_check_time: float = 0.0

        # Detector-result stability gate: dispatch only once the same prompt
        # signature has been seen twice in a row (≥1s apart), so spinner frames
        # and progressive renders can't trigger a partial dispatch.
        self._candidate_signature: Optional[str] = None
        self._candidate_first_seen: float = 0.0

        # Graceful shutdown state. On SIGTERM/SIGHUP we send Ctrl+C twice
        # to Claude (interrupt-then-exit) so its TUI can print the
        # "Resume this session with: claude --resume <id>" hint before we
        # tear down. ``_shutdown_started_at`` sentinels "in shutdown"; the
        # event loop sends the second Ctrl+C ~300 ms later and forces exit
        # at SHUTDOWN_GRACE_S so a stuck child can't hang ``vicoa stop``.
        self._shutdown_started_at: Optional[float] = None
        self._second_ctrlc_sent: bool = False

        # Self-heal no-detect counters. Increment on consecutive polls
        # where the relevant detector returns False; reset to 0 the moment
        # we see a True. Once a counter crosses
        # SELF_HEAL_DARK_TICKS_REQUIRED we treat the modal as truly gone
        # and clear pending state. Two counters because AUQ runs in a
        # special ``suppress_until`` branch and the general path serves
        # permission/plan.
        self._auq_dark_ticks: int = 0
        self._dark_ticks: int = 0

        # AskUserQuestion tab collector and dispatcher
        self.ask_question_collector = AskQuestionCollector(
            pty_manager=self.pty_manager,
            terminal_buffer=self.terminal_buffer,
            ansi_cleaner=self.ansi_cleaner,
            read_pty_func=self._read_pty_as_str,
            log_func=self.log,
            session_state=self.session_state,
            message_processor=self.message_processor,
            message_queue=self.message_queue,
            send_message_lock=self.send_message_lock,
            requested_input_messages=self.requested_input_messages,
            normalize_options_map_func=self._normalize_options_map,
        )

        # Initialize JSONL monitor with all dependencies. vicoa_client lets it
        # PATCH session_config when it observes a model or permission_mode
        # change in the Claude jsonl (plan §3.3 Post-init PATCH).
        self.jsonl_monitor = JSONLMonitor(
            agent_instance_id=config.agent_instance_id,
            message_processor=self.message_processor,
            reset_handler=self.reset_handler,
            log_func=self.log,
            skip_existing_entries=config.is_resuming,
            message_queue=self.message_queue,
            send_message_lock=self.send_message_lock,
            requested_input_messages=self.requested_input_messages,
            pending_permission_options=self.session_state.pending_permission_options,
            terminal_ask_dispatched_func=lambda: time.time()
            < self.ask_question_collector.suppress_until,
            vicoa_client=self.vicoa_client_sync,
        )

        # Initialize input request manager
        self.input_request_manager = InputRequestManager(
            agent_instance_id=config.agent_instance_id,
            agent_name=config.name,
            vicoa_client_async=self.vicoa_client_async,
            vicoa_client_sync=self.vicoa_client_sync,
            message_processor=self.message_processor,
            message_queue=self.message_queue,
            session_state=self.session_state,
            toggle_manager=self.toggle_manager,
            pty_manager=self.pty_manager,
            log_func=self.log,
            on_ask_user_question_submitted=self._on_ask_question_submitted,
        )

    def run(self) -> int:
        """Main entry point - run the wrapper.

        Returns:
            Exit code (0 for success, 1 for error)
        """
        try:
            self._setup()
            self._run_event_loop()
            return 0
        except KeyboardInterrupt:
            self.log("[INFO] Interrupted by user")
            return 0
        except FileNotFoundError as e:
            print("Error: Claude Code not installed")
            print("Get started: https://code.claude.com/docs")
            self.log(f"[ERROR] Fatal error: {e}")
            return 1
        except Exception as e:
            self.log(f"[ERROR] Fatal error: {e}")
            import traceback

            self.log(traceback.format_exc())
            return 1
        finally:
            self._cleanup()

    def _setup(self) -> None:
        """Setup before main loop."""
        self.log("[INFO] Setting up Vicoa...")
        # Register agent instance only if starting a new session
        if self.config.is_resuming:
            self.log(f"[INFO] Resuming session: {self.config.agent_instance_id}")
        else:
            if self.vicoa_client_sync:
                try:
                    # Best-effort initial session_config from ANTHROPIC_MODEL +
                    # the wrapper's own CLI args. The JSONLMonitor will PATCH
                    # the authoritative values from the jsonl as soon as Claude
                    # writes them (assistant.message.model on first reply,
                    # permission-mode event at init). Including these at
                    # register time closes the brief null-row window users see
                    # when they open the chat page right after spawn.
                    from .utils.initial_session_config import (
                        build_initial_session_config,
                    )

                    initial_session_config: Optional[dict] = (
                        build_initial_session_config(
                            anthropic_model_env=os.environ.get("ANTHROPIC_MODEL"),
                            permission_mode=self.config.permission_mode,
                            dangerously_skip_permissions=bool(
                                self.config.dangerously_skip_permissions
                            ),
                        )
                    )
                    registration = self.vicoa_client_sync.register_agent_instance(
                        agent_type=self.config.name,
                        transport="local",
                        agent_instance_id=self.config.agent_instance_id,
                        name=None,
                        project=get_project_path(),
                        home_dir=str(Path.home()),
                        session_config=initial_session_config,
                        source="terminal",
                    )
                    # Update agent_instance_id from registration response
                    self.config.agent_instance_id = registration.agent_instance_id

                    # Update all components with the new agent_instance_id
                    self.message_processor.agent_instance_id = (
                        self.config.agent_instance_id
                    )
                    self.heartbeat.agent_instance_id = self.config.agent_instance_id
                    self.jsonl_monitor.agent_instance_id = self.config.agent_instance_id

                    # No initial "session started" message: the user just
                    # launched the TUI themselves and is sitting in front of
                    # it — a synthetic "waiting for input" row only adds
                    # noise to the chat list and triggers a useless push
                    # notification to the same device. ``last_message_id``
                    # gets bootstrapped from Claude's first jsonl entry via
                    # JSONLMonitor, so the idle-monitor → AWAITING_INPUT
                    # path still arms naturally once Claude writes anything.
                except Exception as e:
                    self.log(f"[ERROR] Failed to register agent instance: {e}")
                    # Continue anyway - wrapper can still function locally

        # Register SIGTERM/SIGHUP handlers so `vicoa stop` triggers clean shutdown.
        # Instead of killing Claude immediately (which skips its exit-render
        # and the "Resume this session with: claude --resume <id>" hint), we
        # type Ctrl+C into the PTY and let the event loop drain Claude's
        # final output. The second Ctrl+C is sent from the event loop in
        # ``_progress_shutdown`` after SHUTDOWN_SECOND_CTRLC_DELAY_S, and
        # ``running`` flips to False at SHUTDOWN_GRACE_S (or earlier on
        # natural child exit via the empty-read branch in
        # ``_handle_pty_output``).
        def _sigterm_handler(sig: int, _: object) -> None:
            if self._shutdown_started_at is not None:
                # Re-entry — a second SIGTERM arrives e.g. when ``vicoa stop``
                # retries. Don't restart the grace window; the original is
                # already counting down and starting over would only delay
                # the resume-hint print we're waiting on.
                self.log(f"[INFO] Signal {sig} during shutdown, ignoring")
                return
            self.log(
                f"[INFO] Received signal {sig}; sending Ctrl+C to Claude "
                "for graceful exit"
            )
            # First Ctrl+C: interrupts the current turn if Claude is busy,
            # or opens the "Press Ctrl+C again to exit" prompt if idle.
            try:
                self.pty_manager.write_to_pty(b"\x03")
            except Exception:
                pass
            self._shutdown_started_at = time.monotonic()

        signal.signal(signal.SIGTERM, _sigterm_handler)
        signal.signal(signal.SIGHUP, _sigterm_handler)

        # Start heartbeat
        self.heartbeat.start()

        # Start JSONL monitor
        self.jsonl_monitor.start()

        # Start input request manager
        self.input_request_manager.start()

        # Start PTY
        self._start_claude_pty()

    def _start_claude_pty(self) -> None:
        """Start Claude CLI in PTY."""
        claude_path = find_claude_cli()

        # Build command
        cmd = self._build_claude_command(claude_path)

        # Create PTY
        env = {"CLAUDE_CODE_ENTRYPOINT": "jsonlog-wrapper"}
        self.pty_manager.create_pty(cmd, env)
        self.pty_manager.set_raw_mode()

    def _build_claude_command(self, claude_path: str) -> list:
        """Build Claude CLI command with arguments."""
        if self.config.is_resuming:
            cmd = [claude_path, "--resume", self.config.agent_instance_id]
        else:
            cmd = [claude_path, "--session-id", self.config.agent_instance_id]

        if self.config.permission_mode:
            cmd.extend(["--permission-mode", self.config.permission_mode])

        if self.config.dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")

        return cmd

    def _run_event_loop(self) -> None:
        """Main event loop."""
        while self.running:
            try:
                # Check for input from stdin or PTY
                rlist, _, _ = select.select(
                    [sys.stdin, self.pty_manager.master_fd], [], [], 0.01
                )

                # Handle PTY output
                if self.pty_manager.master_fd in rlist:
                    self._handle_pty_output()

                # Handle stdin input
                if sys.stdin in rlist:
                    self._handle_stdin_input()

                # During the shutdown grace window suppress queue processing
                # and prompt detection — we want to drain Claude's exit
                # render to stdout, not start a new turn or send fresh
                # request-input calls. ``_progress_shutdown`` fires the
                # second Ctrl+C and bounds the wait.
                if self._shutdown_started_at is None:
                    if self.message_queue:
                        self._process_queued_message()
                    if self._should_check_for_prompts():
                        self._check_for_prompts()
                else:
                    self._progress_shutdown()

            except Exception as e:
                self.log(f"[ERROR] Error in event loop: {e}")
                import traceback

                self.log(traceback.format_exc())

    def _progress_shutdown(self) -> None:
        """Drive the SIGTERM/SIGHUP graceful-exit state machine.

        Sends the second Ctrl+C ~300 ms after the first so Claude's TUI
        treats it as "exit now" (the single Ctrl+C only interrupts), then
        forces the event loop to exit at SHUTDOWN_GRACE_S. On the deadline
        we SIGTERM the child as a backstop — without it a Claude process
        that ignored Ctrl+C would survive into ``_cleanup`` and block
        ``pty_manager.close()`` on waitpid.
        """
        started = self._shutdown_started_at
        if started is None:
            return
        elapsed = time.monotonic() - started

        if (
            not self._second_ctrlc_sent
            and elapsed >= self.SHUTDOWN_SECOND_CTRLC_DELAY_S
        ):
            try:
                self.pty_manager.write_to_pty(b"\x03")
            except Exception:
                pass
            self._second_ctrlc_sent = True
            self.log("[INFO] Sent second Ctrl+C; awaiting Claude exit")

        if elapsed >= self.SHUTDOWN_GRACE_S:
            self.log(
                f"[INFO] Shutdown grace window elapsed ({elapsed:.1f}s); "
                "SIGTERM child as backstop and exiting event loop"
            )
            if self.pty_manager and self.pty_manager.child_pid:
                try:
                    os.kill(self.pty_manager.child_pid, signal.SIGTERM)
                except Exception:
                    pass
            self.running = False

    def _handle_pty_output(self) -> None:
        """Handle output from Claude CLI."""
        try:
            data = self.pty_manager.read_from_pty()
            if data:
                self.last_pty_output_time = time.time()
                # Write to stdout
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()

                # Add to buffer
                text = data.decode("utf-8", errors="replace")
                self.terminal_buffer.append(text)

                # Mark terminal activity whenever we receive output
                # The idle check will use buffer content to distinguish
                # between real work and status line updates
                self.session_state.mark_terminal_activity()

                # Detect local toggle changes and sync to UI
                # Only check if text contains relevant keywords (matching v2_0 optimization)
                text_lower = text.lower()
                if (
                    "shift+tab" in text_lower
                    or "tab to toggle" in text_lower
                    or "? for shortcut" in text_lower
                ):
                    # Only clean ANSI when we need to check toggle state
                    clean_text = self.ansi_cleaner.clean_csi_sequences(text)
                    feedback_messages = self.toggle_manager.update_from_terminal(
                        clean_text
                    )
                    for message in feedback_messages:
                        self._send_feedback_message(message)
                    # When toggle_manager confirms a permission_mode change (it
                    # only returns a feedback message when the slug actually
                    # changed), PATCH session_config immediately. The jsonl
                    # entry that records the new mode lands ~seconds later;
                    # closing that gap means the mobile pill reflects the
                    # change without lag. Dedup cache makes the later PATCH
                    # a no-op for the same value.
                    if feedback_messages:
                        info = self.toggle_manager.get_toggle_info("permission_mode")
                        if info:
                            self.jsonl_monitor.notify_permission_mode_observed(
                                info.get("current_slug")
                            )

                # Track interrupts for idle detection
                # Check for "esc to interrupt" or "ctrl+b to run in background" text
                # (not just the escape byte, which appears in ANSI codes)
                if (
                    "esc to interrupt" in text_lower
                    or "ctrl+b to run in background" in text_lower
                    or "esc to cancel" in text_lower
                ):
                    self.session_state.mark_interrupt()

            else:
                # Empty data means child process has exited
                self.log(
                    "[INFO] Claude process exited (empty read), shutting down wrapper"
                )
                self.running = False

        except OSError as e:
            # OSError during read typically means the child process has exited
            self.log(
                f"[INFO] Claude process exited (OSError: {e}), shutting down wrapper"
            )
            self.running = False
        except Exception as e:
            self.log(f"[ERROR] Error reading PTY: {e}")
            # Don't set running = False for other exceptions

    def _read_pty_as_str(self) -> Optional[str]:
        """Read pending PTY output, echo it to stdout/buffer, and return as str.

        Used by ToggleManager's send-one-observe loop so it can see the mode
        label that Claude CLI redraws after each Shift+Tab press without the
        data being silently swallowed.
        """
        try:
            data = self.pty_manager.read_from_pty()
            if not data:
                return None
            self.last_pty_output_time = time.time()
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
            text = data.decode("utf-8", errors="replace")
            self.terminal_buffer.append(text)
            self.session_state.mark_terminal_activity()
            return text
        except Exception:
            return None

    def _handle_stdin_input(self) -> None:
        """Handle input from stdin."""
        try:
            char = os.read(sys.stdin.fileno(), 1)
            if char:
                # Check for Ctrl+Z
                if char == b"\x1a":
                    self.pty_manager.suspend_for_ctrl_z()
                    return

                # Write to PTY
                self.pty_manager.write_to_pty(char)

                # Process through input handler
                # JSONL monitor handles forwarding to Vicoa to avoid duplicates.
                self.input_handler.process_char(char)

        except Exception as e:
            self.log(f"[ERROR] Error reading stdin: {e}")

    def _should_check_for_prompts(self) -> bool:
        """Determine if we should check for prompts.

        Polls the terminal every ~1.5s regardless of `is_claude_idle()`. The
        Claude CLI spinner re-renders frequently and keeps the idle check False,
        so an idle-based gate would never fire while a permission prompt is
        waiting. Stability of the detector result (see `_check_for_prompts`)
        handles the progressive-render race instead.

        Returns:
            True if a poll should run this tick, False otherwise.
        """
        if self.message_queue:
            return False
        if self.message_processor.pending_input_message_id:
            return False
        if time.time() - self._last_prompt_check_time < 1.5:
            return False
        return True

    def _check_for_prompts(self) -> None:
        """Check terminal buffer for prompts that need handling."""
        # Record poll time so `_should_check_for_prompts` honours the 1.5s
        # cadence. Settling is handled by the stability gate below — waiting on
        # `last_pty_output_time` would block forever while the spinner ticks.
        self._last_prompt_check_time = time.time()
        self._last_checked_buffer_size = self.terminal_buffer.size()

        # Get more buffer history to maintain screen state
        # Claude CLI uses cursor positioning to update parts of the screen,
        # so we need the full screen content, not just the last update
        # Increased from 2000 to 10000 to capture complete screen state
        raw_buffer = self.terminal_buffer.get_last_n_chars(10000)

        # Use terminal renderer to properly handle cursor positioning
        # Claude CLI uses cursor forward (\x1b[NC) between characters for spacing
        # Simple ANSI cleaning replaces these with spaces, creating garbled text
        # The renderer simulates actual terminal behavior by tracking cursor position
        try:
            renderer = TerminalRenderer()
            clean_buffer = renderer.render(raw_buffer)
        except Exception as e:
            # Fallback to simple ANSI cleaning if renderer fails
            self.log(
                f"[WARNING] TerminalRenderer failed: {e}, falling back to ANSI cleaner"
            )
            clean_buffer = self.ansi_cleaner.clean_all(raw_buffer)

        # Check each detector
        for detector_name, detector in self.detectors.items():
            # Suppress AskUserQuestion re-detection while a Vicoa response is pending.
            # Run the detector anyway to clear suppression when the UI closes.
            if (
                detector_name == "question"
                and time.time() < self.ask_question_collector.suppress_until
            ):
                result = detector.detect_and_extract(clean_buffer)
                if result.detected:
                    # Still seeing the AUQ modal in buffer — reset counter.
                    self._auq_dark_ticks = 0
                else:
                    # N consecutive no-detects in the AUQ suppress window
                    # → trust that the modal disappeared (UI submit, UI
                    # decline, Claude process resolved it, etc.) and
                    # clear AUQ pending state. Safe to clear here because
                    # suppress_until is set ONLY by the AUQ path, so any
                    # pending options under suppression are AUQ's.
                    self._auq_dark_ticks = self._self_heal_clear_if_dark(
                        self._auq_dark_ticks,
                        "AUQ",
                        clear_auq_suppress=True,
                    )
                continue

            result = detector.detect_and_extract(clean_buffer)
            if result.detected:
                # Any detector firing means the buffer still shows a modal —
                # reset the self-heal dark-tick counter.
                self._dark_ticks = 0
                self.log(f"[DEBUG] Detector '{detector_name}': detected=True")

                # Ensure data is present (should always be true when detected=True)
                if not result.data:
                    self.log(
                        f"[WARNING] Detector {detector_name} detected but returned no data"
                    )
                    break

                signature = self._build_prompt_signature(detector_name, result.data)

                # Stability gate: dispatch only after the same signature has
                # been observed ≥1s. Filters out partial renders and ignores
                # spinner activity (the spinner re-renders below the options
                # box so the parsed signature is invariant across frames).
                if self._candidate_signature != signature:
                    self.log(
                        f"[DEBUG] New signature observed; awaiting stability: "
                        f"detector={detector_name!r} sig={signature[:80]!r}"
                    )
                    self._candidate_signature = signature
                    self._candidate_first_seen = time.time()
                    break
                if time.time() - self._candidate_first_seen < 1.0:
                    self.log(
                        f"[DEBUG] Signature not yet stable: "
                        f"sig={signature[:40]!r} age="
                        f"{time.time() - self._candidate_first_seen:.2f}s < 1.0s"
                    )
                    break

                if not self.session_state.should_send_prompt(signature):
                    self.log(
                        f"[DEBUG] Signature already sent (dedup); skipping: "
                        f"sig={signature[:40]!r}"
                    )
                    break

                # For AskUserQuestion, navigate through all tabs before dispatching
                if detector_name == "question":
                    all_tabs = self.ask_question_collector.collect_all_tabs(
                        detector, result
                    )
                    result.data["_all_tabs"] = all_tabs

                self._handle_detected_prompt(detector_name, result.data)
                self.session_state.mark_prompt_sent(signature)

                # Intentionally NOT calling terminal_buffer.clear() here.
                # Gate C (signature dedup via should_send_prompt) is enough
                # to prevent re-dispatch while the same modal is rendered.
                # Clearing the buffer would force the next poll's detector
                # to return False (the modal's structural rendering is no
                # longer in buffer — Claude CLI doesn't redraw a static
                # modal frame by frame), which then trips the self-heal
                # path into thinking the modal disappeared even though it
                # is still on screen.

                # self.terminal_buffer.clear()
                # self._last_checked_buffer_size = 0
                self._candidate_signature = None

                break  # Handle one prompt at a time
        else:
            # No detector matched this tick. A single no-detect tick is
            # unreliable (transient renderer glitch, cursor navigation,
            # spinner repaint), so we don't immediately clear cached
            # state. Accumulate consecutive no-detects; only clear once we
            # cross SELF_HEAL_DARK_TICKS_REQUIRED. This is the self-heal
            # path for permission/plan modals — AUQ has its own self-heal
            # in the suppress_until branch above and we leave its state
            # alone here to avoid double-clearing.
            in_auq_suppress = time.time() < self.ask_question_collector.suppress_until
            if not in_auq_suppress:
                self._dark_ticks = self._self_heal_clear_if_dark(
                    self._dark_ticks, "Permission/plan"
                )

    def _self_heal_clear_if_dark(
        self,
        dark_ticks: int,
        context: str,
        *,
        clear_auq_suppress: bool = False,
    ) -> int:
        """Self-heal accounting + clearing helper.

        Shared between the AUQ suppress branch and the permission/plan
        for-else in ``_check_for_prompts``. Increments the caller's
        consecutive no-detect counter and, once it crosses
        ``SELF_HEAL_DARK_TICKS_REQUIRED``, clears the wrapper's cached
        pending state so a subsequent UI message isn't mis-translated
        through a stale options map. Returns the updated counter value
        — caller assigns back to its own attribute. Resets to 0 after
        firing so we don't repeatedly re-run the (already idempotent)
        clears on every subsequent dark tick.

        Args:
            dark_ticks: Current value of the caller's no-detect counter.
            context: Display label used in the "modal disappeared" log
                message — either ``"AUQ"`` or ``"Permission/plan"``.
            clear_auq_suppress: If True (AUQ caller), also reset
                ``ask_question_collector.suppress_until`` so the next
                AUQ detection can dispatch normally.

        Returns:
            The new counter value (incremented, or 0 if the threshold
            fired this tick).
        """
        ticks = dark_ticks + 1
        if ticks < self.SELF_HEAL_DARK_TICKS_REQUIRED:
            return ticks

        if self.session_state.pending_permission_options:
            self.log(
                f"[INFO] {context} modal disappeared from terminal "
                f"({ticks} consecutive no-detects) — "
                "clearing pending_permission_options"
            )
            self.session_state.clear_pending_permission_options()
        self.session_state.clear_prompt_signature()
        self._candidate_signature = None
        if clear_auq_suppress:
            self.ask_question_collector.suppress_until = 0.0
        return 0

    def _handle_detected_prompt(self, prompt_type: str, data: dict) -> None:
        """Handle a detected prompt.

        Args:
            prompt_type: Type of prompt detected
            data: Extracted data from detector
        """
        if prompt_type == "control":
            # Handle control command (legacy format from detector)
            self._handle_control_command_from_dict(data)
        else:
            # Handle user input prompt (permission, plan, question)
            self._handle_input_prompt(data)
            self.session_state.mark_prompt_detected(prompt_type)

    def _handle_control_command_from_dict(self, data: dict) -> None:
        """Handle a control command from dict (legacy format from detector).

        Note: This is for backwards compatibility. New code should use
        the JSON string format handled by _handle_control_command().
        """
        control = data.get("control_command", {})
        setting = control.get("setting")

        if setting == "interrupt":
            # Send escape key
            self.pty_manager.write_to_pty(b"\x1b")
            self.message_queue.clear()

        elif setting in self.toggle_manager.get_all_settings():
            # Handle toggle setting
            value = control.get("value")
            target = self.toggle_manager.normalize_value(setting, value)
            if target:
                self.toggle_manager.set_toggle(setting, target)

    def _handle_input_prompt(self, data: dict) -> None:
        """Handle an input prompt (permission, plan, question)."""
        # AskUserQuestion is handled first — it must override any existing pending idle
        # input request, so it bypasses the pending_input_message_id guard below.
        if data.get("type") == "ask_user_question":
            self.ask_question_collector.handle(data)
            return

        # For all other prompt types (permission, plan): guard against re-sends
        # when a previous requires_user_input cycle is still open.
        if self.message_processor.pending_input_message_id:
            self.log(
                "[DEBUG] Skipping terminal prompt re-send; pending_input_message_id already set"
            )
            return

        question = data.get("question", "")
        options = data.get("options", [])
        options_map = self._normalize_options_map(
            data.get("options_map") or {}, options
        )

        # Store pending options so UI selections can be converted to numbers
        if options_map:
            self.session_state.set_pending_permission_options(options_map)

        # Send to Vicoa as requires_user_input message
        if self.vicoa_client_sync and self.config.agent_instance_id:
            try:
                # Build message - use ONLY the terminal buffer context from the detector
                # The question already contains rich context extracted from terminal
                # No need to add JSONL tool context separately (would cause duplication)
                message_parts = [question]

                # Format message with options
                if options:
                    options_text = "\n".join(options)
                    message_parts.append("")
                    message_parts.append("[OPTIONS]")
                    message_parts.append(options_text)
                    message_parts.append("[/OPTIONS]")

                message = "\n".join(message_parts)

                response = self.vicoa_client_sync.send_message(
                    content=message,
                    agent_type=self.config.name,
                    agent_instance_id=self.config.agent_instance_id,
                    requires_user_input=False,
                )

                if response and hasattr(response, "message_id"):
                    self.message_processor.last_message_id = response.message_id
                    self.message_processor.last_message_time = time.time()
                    # Allow input requests to flow for prompt responses
                    self.message_processor.last_was_tool_use = False
                    # Let idle detection handle input requests naturally

            except Exception as e:
                self.log(f"[ERROR] Failed to send prompt to Vicoa: {e}")

    def _normalize_options_map(
        self, options_map: dict, options: list[str]
    ) -> dict[str, str]:
        """Normalize option mapping to a text -> number map."""
        if not options_map and not options:
            return {}

        # If keys are numbers, invert using option text
        if options_map and all(
            str(key).strip().isdigit() for key in options_map.keys()
        ):
            inverted = {}
            for number, text in options_map.items():
                text = str(text).strip()
                if text:
                    inverted[text] = str(number).strip()
                    if ". " in text:
                        _, stripped = text.split(". ", 1)
                        stripped = stripped.strip()
                        if stripped:
                            inverted[stripped] = str(number).strip()
            return inverted

        # Build from options list if needed
        normalized = dict(options_map)
        for option in options or []:
            option_text = str(option).strip()
            if not option_text:
                continue
            if ". " in option_text:
                number, text = option_text.split(". ", 1)
                number = number.strip()
                text = text.strip()
                if number.isdigit() and text:
                    normalized[text] = number
                    normalized[option_text] = number
        return normalized

    def _build_prompt_signature(self, prompt_type: str, data: dict) -> str:
        """Build a stable signature for de-duplicating prompt sends."""
        question = (data.get("question") or "").strip()
        options = data.get("options") or []
        options_sig = "|".join(opt.strip() for opt in options if opt is not None)
        return f"{prompt_type}:{question}:{options_sig}"

    def _process_queued_message(self) -> None:
        """Process next message from queue."""
        if self.message_queue.is_empty():
            return

        try:
            content = self.message_queue.popleft()
            has_pending_options = bool(self.session_state.pending_permission_options)
            self.log(
                f"[DEBUG] Processing queued message: {content[:80]!r} "
                f"(pending_options={has_pending_options})"
            )

            # Defense in depth: Filter control commands before sending to Claude
            # (Primary filtering happens in _process_user_responses, this catches edge cases)
            try:
                if self.input_request_manager._handle_control_command(content):
                    return
            except Exception as e:
                self.log(
                    f"[WARNING] Error checking control command: {e}, continuing..."
                )

            # Check if this is a permission prompt response
            if self.session_state.pending_permission_options:
                content_stripped = content.strip()
                options_map = self.session_state.pending_permission_options
                matched = False

                if content_stripped in options_map:
                    converted = options_map[content_stripped]
                    content = converted
                    matched = True
                else:
                    lowered = content_stripped.lower()
                    for key, value in options_map.items():
                        if key.strip().lower() == lowered:
                            content = value
                            matched = True
                            break

                if not matched and content_stripped.isdigit():
                    if content_stripped in options_map.values():
                        content = content_stripped
                        matched = True

                if not matched:
                    # The user declined the AUQ / permission prompt in the UI
                    # and sent a free-form reply (or the options map is stale
                    # for some other reason). The terminal modal is still open;
                    # if we just typed the content into the PTY it would be
                    # received as keystrokes by the modal and the trailing Enter
                    # would confirm the highlighted (first) option — exactly
                    # what the old defense-in-depth ``return`` was protecting
                    # against. Send Esc first to dismiss the modal cleanly,
                    # then fall through to type the content into Claude's
                    # normal chat input. The original ``return`` silently
                    # dropped legitimate post-decline messages, which is worse
                    # UX than the rare case of an Esc dismissing a modal that
                    # the user actually wanted to keep open.
                    self.log(
                        f"[INFO] Queued message does not match pending options "
                        f"— dismissing terminal modal with Esc and forwarding: "
                        f"{content_stripped[:80]!r}"
                    )
                    self.pty_manager.write_to_pty(b"\x1b")
                    time.sleep(0.1)

                # Either matched (content rewritten to option number) or
                # unmatched free-form (modal dismissed above, content unchanged).
                # Clear pending state in both paths and fall through to write
                # the content into the PTY.
                self.session_state.clear_pending_permission_options()
                self.terminal_buffer.clear()

                self.session_state.clear_prompt_timing()
                self.session_state.clear_prompt_signature()
                # Clear last_was_tool_use for ANY prompt type (permission, plan, question)
                # This allows input requests to resume after user responds
                self.message_processor.last_was_tool_use = False
                # Clear tool context after permission is handled
                self.message_processor.last_tool_context = None
                self._prompt_check_start_time = None

            # Check for session reset commands from web UI
            if self.reset_handler.check_for_reset_command(content.strip()):
                self.reset_handler.mark_reset_detected(content.strip())

            # Record the injection so the JSONL monitor can recognize Claude's
            # transcription of this content as a UI echo and skip writing a
            # duplicate row to the DB. Marked here (post-rewrite, pre-PTY) so
            # permission-option rewrites are captured in the form Claude will
            # actually transcribe.
            self.message_processor.injection_tracker.mark_injected(content)

            # Send to Claude - send message content first
            self.pty_manager.write_to_pty(content.encode("utf-8"))
            time.sleep(0.25)  # Wait a bit for Claude to process

            # Clear state when user sends input
            # NOTE: We do NOT update last_message_time - that only tracks Claude's output
            # NOTE: We keep last_message_id so idle detection can work - JSONL monitor will update it
            self.message_processor.pending_input_message_id = None

            # Send carriage return (Enter key) to submit
            self.pty_manager.write_to_pty(b"\r")

            # Don't immediately request input here - let the normal flow handle it:
            # - If Claude is busy: control poller will pick up messages
            # - If Claude is idle: idle detection will request input after minimum delay
            # This prevents unwanted push notifications (Use Case #5)

        except Exception as e:
            self.log(f"[ERROR] Failed to process queued message: {e}")

    def _cleanup(self) -> None:
        """Cleanup before exit."""
        self.running = False

        # Close the async client's aiohttp session on the InputRequestManager's
        # loop, while that loop is still running. The session/connector are
        # bound to that loop; awaiting close() on any other loop raises
        # "Future ... attached to a different loop" from inside aiohttp.
        if self.vicoa_client_async:
            try:
                t0 = time.monotonic()
                close_async_on_loop(
                    self.vicoa_client_async.close,
                    self.input_request_manager.async_loop,
                    log=self.log,
                    label="async client",
                )
                self.log(
                    f"[INFO] async client close took {(time.monotonic() - t0) * 1000:.0f}ms"
                )
            except Exception as e:
                self.log(f"[ERROR] async client close failed: {e}")

        try:
            # Stop input request manager (this stops the async loop)
            self.input_request_manager.stop()
        except Exception as e:
            self.log(f"[ERROR] input_request_manager stop failed: {e}")

        try:
            self.heartbeat.stop()
        except Exception as e:
            self.log(f"[ERROR] heartbeat stop failed: {e}")

        try:
            self.jsonl_monitor.stop()
        except Exception as e:
            self.log(f"[ERROR] jsonl_monitor stop failed: {e}")

        # End session BEFORE closing PTY: pty_manager.close() can block on
        # waitpid() while Claude CLI winds down, and if the caller times out
        # and sends SIGKILL we'd never reach end_session(). Calling it here
        # while the sync client is still open guarantees the status update
        # lands regardless of how long PTY teardown takes.
        if self.vicoa_client_sync and self.config.agent_instance_id:
            try:
                self.vicoa_client_sync.end_session(self.config.agent_instance_id)
            except Exception as e:
                self.log(f"[ERROR] Failed to end session: {e}")

        # Close PTY (restores the user's terminal mode so prints land cleanly).
        try:
            self.pty_manager.close()
        except Exception as e:
            self.log(f"[ERROR] pty_manager close failed: {e}")

        # Close Vicoa clients
        if self.vicoa_client_sync:
            try:
                self.vicoa_client_sync.close()
            except Exception as e:
                self.log(f"[ERROR] Failed to close sync client: {e}")

        # Tell the user how to resume this session. Use the agent-explicit form
        # (`vicoa claude --resume …`) so the command keeps working even if the
        # user has changed their default agent via `vicoa --set-default`.
        if self.config.agent_instance_id:
            print(
                f"Resume vicoa session with:\nvicoa claude --resume {self.config.agent_instance_id}",
                flush=True,
            )

        # Close log file
        if self.debug_log_file:
            try:
                self.log("=== Claude Wrapper (Modular) Log Ended ===")
                # Detach our root logging handler before closing the file —
                # otherwise late `logger.warning` calls from background
                # threads finishing up would invoke ``self.log`` against a
                # closed file handle, and the handler's ``except Exception``
                # would swallow the IOError silently.
                root = logging.getLogger()
                for existing in list(root.handlers):
                    if isinstance(existing, _WrapperLogHandler):
                        root.removeHandler(existing)
                self.debug_log_file.flush()
                self.debug_log_file.close()
            except Exception:
                pass

    def _init_logging(self) -> None:
        """Initialize debug logging."""
        try:
            VICOA_WRAPPER_LOG_DIR.mkdir(exist_ok=True, parents=True)
            log_file_path = (
                VICOA_WRAPPER_LOG_DIR / f"{self.config.agent_instance_id}.log"
            )
            self.debug_log_file = open(log_file_path, "w")
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            milliseconds = int((time.time() % 1) * 1000)
            self.log(
                f"=== Claude Wrapper (Modular) - {timestamp}.{milliseconds:03d} ==="
            )
            # Route the Python `logging` module into this debug file.
            # Without a handler attached anywhere in the root chain,
            # `logger.warning(...)` calls (e.g. session_ws_client's
            # "session WS connection lost: ...") fall back to
            # logging.lastResort -> StreamHandler(sys.stderr). In this
            # wrapper, sys.stderr is the same fd as the Claude TUI, so
            # those warnings get painted over the rendered terminal.
            self._install_root_logging_handler()
        except Exception as e:
            print(f"Failed to create debug log file: {e}", file=sys.stderr)

    def _install_root_logging_handler(self) -> None:
        """Attach a root handler that writes through ``self.log``.

        Gates at the handler level (not on the root logger) so a caller that
        intentionally raised ``root.level`` to ERROR/CRITICAL for noise
        suppression is not silently overridden — their WARNING records stay
        filtered at the logger chain, lastResort still never fires (records
        filtered by level never reach any handler), and the TUI stays clean
        either way.

        Idempotent: a previously installed ``_WrapperLogHandler`` (e.g. from
        a re-init or test reconstruction) is removed before the new one is
        attached so warnings are not double-written.
        """
        root = logging.getLogger()
        for existing in list(root.handlers):
            if isinstance(existing, _WrapperLogHandler):
                root.removeHandler(existing)
        handler = _WrapperLogHandler(self.log)
        handler.setLevel(logging.WARNING)
        root.addHandler(handler)

    def _init_vicoa_clients(self) -> None:
        """Initialize Vicoa SDK clients."""
        if not self.config.api_key:
            raise ValueError("API key is required to initialize Vicoa clients")

        self.vicoa_client_sync = VicoaClient(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            max_retries=1440,
            backoff_factor=1.0,
            backoff_max=60.0,
            log_func=self.log,
        )

        self.vicoa_client_async = AsyncVicoaClient(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            max_retries=1440,
            backoff_factor=1.0,
            backoff_max=60.0,
            log_func=self.log,
        )

    def _send_feedback_message(self, message: str) -> None:
        """Send a status update to Vicoa about local control actions."""
        if not self.vicoa_client_sync or not self.config.agent_instance_id:
            self.log(
                "[WARNING] Cannot send feedback: vicoa_client_sync or agent_instance_id not initialized"
            )
            return

        try:
            response = self.vicoa_client_sync.send_message(
                content=message,
                agent_type=self.config.name,
                agent_instance_id=self.config.agent_instance_id,
                requires_user_input=False,
            )
            if response and getattr(response, "queued_user_messages", None):
                for queued in response.queued_user_messages:
                    self.message_processor.process_user_message_sync(
                        queued, from_web=True
                    )
                    # injection_tracker.mark_injected is called from
                    # _process_queued_message (post permission-option rewrite,
                    # pre-PTY write).
                    self.message_queue.append(queued)
        except Exception as e:
            self.log(f"[ERROR] Failed to send feedback message '{message}': {e}")

    def _on_ask_question_submitted(self) -> None:
        """Clear AskUserQuestion suppression and option state after answers submit.

        Resetting suppress_until allows the next AskUserQuestion call to be
        detected and dispatched without waiting 120 seconds for the window to
        expire. Clearing pending_permission_options is critical: the AUQ
        submission path (InputRequestManager → PTY keys) bypasses
        _process_queued_message, which is where pending_permission_options is
        normally cleared after a matched response. Without the clear here,
        the next fresh UI message gets dropped by the defense-in-depth check
        in _process_queued_message because it doesn't match any old AUQ option.
        """
        self.ask_question_collector.suppress_until = 5.0
        self.session_state.clear_prompt_signature()
        self.session_state.clear_pending_permission_options()

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


def main() -> int:
    """Main entry point for modular wrapper.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    parser = argparse.ArgumentParser(description="Claude Code Wrapper (Modular)")
    parser.add_argument("--api-key", help="Vicoa API key")
    parser.add_argument("--base-url", default=None, help="Vicoa base URL")
    parser.add_argument("--permission-mode", help="Initial permission mode")
    parser.add_argument("--dangerously-skip-permissions", action="store_true")
    parser.add_argument("--name", default="Claude Code", help="Agent display name")
    parser.add_argument("--agent-instance-id", help="Agent instance ID")
    parser.add_argument("--resume", help="Resume session ID")
    args = parser.parse_args()

    # Use resume as agent_instance_id if provided
    agent_instance_id = args.resume or args.agent_instance_id or str(uuid.uuid4())
    is_resuming = bool(args.resume)

    config = ClaudeWrapperConfig.from_args(
        api_key=args.api_key,
        base_url=args.base_url,
        permission_mode=args.permission_mode,
        dangerously_skip_permissions=args.dangerously_skip_permissions,
        name=args.name,
        agent_instance_id=agent_instance_id,
        is_resuming=is_resuming,
    )

    wrapper = ClaudeWrapper(config)
    return wrapper.run()


if __name__ == "__main__":
    sys.exit(main())
