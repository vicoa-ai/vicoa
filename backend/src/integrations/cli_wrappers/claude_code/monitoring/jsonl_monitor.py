"""JSONL log file monitoring for Claude CLI.

This module monitors Claude's JSONL log file for messages and events.
"""

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from ..config import CLAUDE_LOG_BASE
from ..format_utils import format_content_block


# Reverse map from Claude model labels ("Sonnet 4.6") to slugs
# ("claude-sonnet-4-6"). When the user picks a model via the `/model`
# picker, the JSONL stdout echo only carries the human label, not the
# slug — this is how we recover it to PATCH session_config.
#
# Kept in sync with shared/agent_catalog.py's Claude `models` entries.
# Sourcing from that module at runtime is blocked by a shadowed `shared`
# package on the import path (cli_wrappers/shared/ wins over src/shared/),
# so the table is maintained in lock-step with the catalog. When upstream
# adds a model, add it here too — existing tests guard the parsing path.
_CLAUDE_LABEL_TO_SLUG: Dict[str, str] = {
    "Opus 5": "claude-opus-5",
    "Opus 4.8": "claude-opus-4-8",
    "Opus 4.8 1M": "claude-opus-4-8[1m]",
    "Opus 4.7": "claude-opus-4-7",
    "Opus 4.7 1M": "claude-opus-4-7[1m]",
    "Opus 4.6": "claude-opus-4-6",
    "Opus 4.6 1M": "claude-opus-4-6[1m]",
    "Sonnet 4.6": "claude-sonnet-4-6",
    "Sonnet 4.6 1M": "claude-sonnet-4-6[1m]",
    "Haiku 4.5": "claude-haiku-4-5",
}


if TYPE_CHECKING:
    from ..session_reset_handler import SessionResetHandler
    from ..messaging.processor import MessageProcessor
    from ..messaging.queue_manager import MessageQueue


class JSONLMonitor:
    """Monitors Claude's JSONL log file.

    Responsibilities:
    - Finding and watching the JSONL log file
    - Processing log entries
    - Handling session resets
    - Detecting subtasks
    """

    def __init__(
        self,
        agent_instance_id: str,
        message_processor: "MessageProcessor",
        reset_handler: "SessionResetHandler",
        log_func: Callable[[str], None],
        skip_existing_entries: bool = False,
        message_queue: Optional["MessageQueue"] = None,
        send_message_lock: Optional[threading.Lock] = None,
        requested_input_messages: Optional[Set[str]] = None,
        pending_permission_options: Optional[Dict[str, str]] = None,
        terminal_ask_dispatched_func: Optional[Callable[[], bool]] = None,
        vicoa_client: Optional[Any] = None,
    ):
        """Initialize JSONL monitor.

        Args:
            agent_instance_id: Agent instance ID
            message_processor: Message processor instance
            reset_handler: Session reset handler
            log_func: Logging function
            skip_existing_entries: Whether to skip existing entries on start
            message_queue: Message queue for queuing web messages to CLI
            send_message_lock: Lock for thread-safe message sending
            requested_input_messages: Set of messages we've requested input for
            pending_permission_options: Dict of pending permission options
            vicoa_client: Optional sync VicoaClient used to PATCH session_config
                when the monitor observes a model or permission_mode change in
                the Claude jsonl. None disables the patch path (tests, replay).
        """
        self.agent_instance_id = agent_instance_id
        self.message_processor = message_processor
        self.reset_handler = reset_handler
        self.log = log_func
        self.skip_existing_entries = skip_existing_entries

        # Dependencies for message processing
        self.message_queue = message_queue
        self.send_message_lock = send_message_lock or threading.Lock()
        self.requested_input_messages = requested_input_messages or set()
        self.pending_permission_options = pending_permission_options or {}
        self.terminal_ask_dispatched_func = terminal_ask_dispatched_func

        self.claude_jsonl_path: Optional[Path] = None
        self.running = True
        self.thread: Optional[threading.Thread] = None

        # Post-init session_config patching (plan §3.3 Post-init PATCH).
        # Cache of fields we've already reported so we PATCH only on change —
        # without this, every assistant turn would re-send the same model.
        self.vicoa_client = vicoa_client
        self._last_session_config: Dict[str, Any] = {}

    def start(self) -> None:
        """Start monitoring the JSONL file in a background thread."""
        if self.thread is not None:
            self.log("[WARNING] JSONL monitor thread already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        self.log("[INFO] Started JSONL monitor thread")

    def stop(self) -> None:
        """Stop monitoring.

        Note: This is a daemon thread, so we just signal it to stop.
        The thread will exit on its own when the main process exits.
        """
        self.running = False
        self.log("[INFO] Signaled JSONL monitor thread to stop")

    def get_project_log_dir(self) -> Optional[Path]:
        """Get the Claude project log directory for current working directory."""
        cwd = os.getcwd()
        # Convert path to Claude's format
        project_name = re.sub(r"[^a-zA-Z0-9]", "-", cwd)
        project_dir = CLAUDE_LOG_BASE / project_name
        return project_dir if project_dir.exists() else None

    def _monitor_loop(self) -> None:
        """Main monitoring loop (runs in background thread)."""
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
                    if self.skip_existing_entries:
                        f.seek(0, os.SEEK_END)
                        self.log(
                            "[INFO] Skipping existing Claude JSONL entries due to resume"
                        )
                        self.skip_existing_entries = False
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
                                # Process directly
                                self._process_entry(data)
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

    # Known catalog thinking-effort ids (kept narrow to avoid PATCHing a
    # bogus slug if Claude ever adds a new label we haven't catalogued).
    _KNOWN_EFFORT_SLUGS = frozenset({"off", "low", "medium", "high", "xhigh", "max"})

    # Matches Claude's `/effort` stdout echo:
    #   "Set effort level to <slug>: <description>"
    # The slug is the first word after "to "; the description (and
    # decorations like "max (this session only)") are ignored.
    _SET_EFFORT_RE = re.compile(r"Set effort level to\s+([a-z]+)", re.IGNORECASE)

    # User-typed TUI slash commands arrive as `<command-name>/X</command-name>
    # [<command-message>X</command-message>] <command-args>SLUG</command-args>`.
    # The optional `<command-message>` element sits between name and args in
    # real Claude jsonl entries — earlier regex without that allowance never
    # matched. For /model + /effort we extract the slug from command-args
    # when present so the row PATCHes immediately.
    #
    # In practice command-args is empty almost always because users go
    # through the `/model` picker. The picker flow leaves args blank and
    # the actual slug only appears as a HUMAN LABEL in the next
    # local-command-stdout line — see _SET_MODEL_RE + _CLAUDE_LABEL_TO_SLUG.
    _COMMAND_NAME_RE = re.compile(
        r"<command-name>\s*/(\w+)\s*</command-name>"
        r"(?:\s*<command-message>[^<]*</command-message>)?"
        r"\s*<command-args>\s*([^<]*?)\s*</command-args>",
        re.IGNORECASE | re.DOTALL,
    )

    # Matches the `<command-name>/foo-bar</command-name>` element for skill
    # / project slash commands so we can forward the typed command name
    # (e.g. `/ideabrowser-daily-idea`) as a user message. Hyphens are
    # allowed — skill names commonly contain them.
    _SKILL_COMMAND_NAME_RE = re.compile(r"<command-name>\s*(/[\w-]+)\s*</command-name>")

    # Strip ANSI styling (`\x1b[1m...\x1b[22m`) wrapping the label in
    # Claude's `Set model to ...` stdout confirmation.
    _ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

    # Match the stdout-echo line for /model. Captures everything between
    # "Set model to " and the next sentinel ("and saved", "(this session
    # only)", end of string). Label has ANSI codes; strip via _ANSI_RE.
    _SET_MODEL_RE = re.compile(
        r"Set model to\s+(.+?)(?:\s+(?:and saved|\(|$))",
        re.IGNORECASE | re.DOTALL,
    )

    def _maybe_extract_model_from_set_model_stdout(self, content: Any) -> None:
        """Parse the `<local-command-stdout>Set model to LABEL …` confirmation
        and PATCH session_config.model when LABEL maps to a known catalog slug.

        Picker-driven /model selections leave `<command-args>` empty — the
        only place the new model appears is this stdout echo, and only as
        the human-friendly LABEL ("Sonnet 4.6", "Opus 4.7 1M"). We reverse-
        map label → slug via the catalog (built lazily at first call so the
        wrapper start path isn't slowed by an import on the cold path).
        """
        if not isinstance(content, str) or "Set model to" not in content:
            return
        match = self._SET_MODEL_RE.search(content)
        if not match:
            return
        label = self._ANSI_RE.sub("", match.group(1)).strip()
        if not label:
            return
        slug = _CLAUDE_LABEL_TO_SLUG.get(label)
        if not slug:
            self.log(
                f"[DEBUG] /model stdout label not in catalog, skipping PATCH: {label!r}"
            )
            return
        self._patch_session_config_fields({"model": slug})

    def _maybe_extract_model_or_effort_from_command(self, content: Any) -> None:
        """If this user-entry is a `<command-name>/model</command-name>
        <command-args>SLUG</command-args>` (same for /effort), PATCH
        session_config with the slug.

        Covers the TUI-initiated path: the user typed `/model X` (or
        `/effort X`) in the TUI directly. `message.model` on the next
        assistant turn would eventually self-heal a model change, but the
        user may not send a follow-up message — the mobile gear pill would
        then show a stale value indefinitely. Reading the command-args
        block closes this gap synchronously.
        """
        if not isinstance(content, str) or "<command-name>" not in content:
            return
        match = self._COMMAND_NAME_RE.search(content)
        if not match:
            return
        command = match.group(1).strip().lower()
        slug = match.group(2).strip()
        if not slug:
            # `/model` with no args opens the picker; we'll catch the actual
            # change via message.model on the next assistant reply.
            return
        if command == "model":
            self._patch_session_config_fields({"model": slug})
        elif command == "effort":
            if slug.lower() in self._KNOWN_EFFORT_SLUGS:
                self._patch_session_config_fields({"thinking_effort": slug.lower()})

    def _maybe_extract_effort_from_user_content(self, content: Any) -> None:
        """If this user-entry content is the `/effort` stdout echo, PATCH
        session_config.thinking_effort.

        Claude doesn't emit a structured event for /effort changes; the
        only signal is the local-command-stdout line. Reference jsonl:
        d2ceea17 cycled through every effort slug (low/medium/high/xhigh/max).
        """
        if not isinstance(content, str) or "Set effort level" not in content:
            return
        match = self._SET_EFFORT_RE.search(content)
        if not match:
            return
        slug = match.group(1).lower()
        if slug not in self._KNOWN_EFFORT_SLUGS:
            self.log(f"[DEBUG] /effort slug not in catalog, skipping PATCH: {slug!r}")
            return
        self._patch_session_config_fields({"thinking_effort": slug})

    def notify_permission_mode_observed(self, slug: Optional[str]) -> None:
        """PATCH session_config.permission_mode from a wrapper-level signal.

        The toggle_manager detects Shift+Tab in the TUI and fires a
        "Permission mode changed to X" feedback message *before* Claude
        writes the next jsonl entry that carries the new mode. Calling this
        as soon as the feedback message fires closes the lag (~7s in
        practice). The shared dedup cache makes the later jsonl-event PATCH
        a no-op for the same value.
        """
        if not slug or not isinstance(slug, str):
            return
        self._patch_session_config_fields({"permission_mode": slug})

    def _patch_session_config_fields(self, fields: Dict[str, Any]) -> None:
        """PATCH the agent_instances row with only the keys whose value
        differs from what we last reported. Network/auth failures are
        swallowed and logged — a failed PATCH must not kill the monitor
        thread, and it leaves _last_session_config untouched so the next
        change of the same key still tries again.
        """
        if self.vicoa_client is None:
            return
        diff = {
            k: v for k, v in fields.items() if self._last_session_config.get(k) != v
        }
        if not diff:
            return
        try:
            self.vicoa_client.patch_agent_instance(
                self.agent_instance_id,
                session_config=diff,
            )
        except Exception as e:
            self.log(f"[WARNING] Failed to PATCH session_config {diff}: {e}")
            return
        self._last_session_config.update(diff)
        self.log(f"[DEBUG] Patched session_config {diff}")

    def _process_entry(self, data: Dict[str, Any]) -> None:
        """Process a single JSONL log entry.

        Args:
            data: Parsed JSON data from log entry
        """
        try:
            msg_type = data.get("type")

            # Standalone permission-mode event — fires at init AND on
            # /permission changes. Both flow through the same PATCH.
            if msg_type == "permission-mode":
                pm = data.get("permissionMode")
                if isinstance(pm, str) and pm:
                    self._patch_session_config_fields({"permission_mode": pm})
                return

            # Queued TUI input — user typed while Claude was busy, so it
            # landed in Claude's pending queue instead of as a normal
            # ``type:"user"`` entry. The enqueue line carries the prompt;
            # the later ``remove`` event and the ``attachment.queued_command``
            # echo carry the same text and must be ignored to avoid
            # double-posting. Without this branch the message is silently
            # dropped — backend never sees it, mobile/web shows nothing.
            if msg_type == "queue-operation":
                if data.get("operation") == "enqueue":
                    content = data.get("content", "")
                    if (
                        isinstance(content, str)
                        and content.strip()
                        and self.message_queue is not None
                    ):
                        self.message_processor.process_user_message(
                            content=content,
                            from_web=False,
                            input_queue=self.message_queue,
                        )
                return

            # Inline `permissionMode` on any entry (Shift+Tab in TUI does NOT
            # emit a standalone event but DOES stamp the new mode on every
            # subsequent user/assistant entry). Evidence: session 6837b5b8
            # changed from bypassPermissions → auto via Shift+Tab and only
            # the inline field reflected it. The dedup cache makes this a
            # no-op when the standalone event also fires.
            inline_pm = data.get("permissionMode")
            if isinstance(inline_pm, str) and inline_pm:
                self._patch_session_config_fields({"permission_mode": inline_pm})

            # Handle "progress" type entries (newer JSONL format)
            # These have nested messages at data.message
            if msg_type == "progress":
                nested_data = data.get("data", {})
                nested_message = nested_data.get("message", {})
                nested_type = nested_message.get("type")

                # Skip messages from subtasks
                is_subtask = data.get("isSidechain")
                if is_subtask and (nested_type == "assistant" or nested_type == "user"):
                    return

                # Process based on nested message type
                if nested_type == "user":
                    self._process_user_entry(nested_message)
                elif nested_type == "assistant":
                    self._process_assistant_entry(nested_message)
                return

            # Handle direct message types (older JSONL format)
            # Skip messages from subtasks
            is_subtask = data.get("isSidechain")
            if is_subtask and (msg_type == "assistant" or msg_type == "user"):
                return

            if msg_type == "user":
                msg_content = (data.get("message") or {}).get("content")
                # /effort stdout echo arrives as user-entry content — check
                # before the normal processing path so we PATCH the new
                # thinking_effort regardless of dedup/echo handling below.
                self._maybe_extract_effort_from_user_content(msg_content)
                # /model stdout echo carries only the LABEL ("Sonnet 4.6"),
                # not the slug. Reverse-map via the catalog. This is the
                # primary signal for picker-driven model changes since
                # <command-args> stays empty in that flow.
                self._maybe_extract_model_from_set_model_stdout(msg_content)
                # `<command-name>/model</command-name><command-args>SLUG…`
                # — the inline-args case. Covers `/model X` typed directly
                # (when args is non-empty). The UI-driven path PATCHes
                # optimistically at PTY-write time, separately.
                self._maybe_extract_model_or_effort_from_command(msg_content)
                self._process_user_entry(data)
            elif msg_type == "assistant":
                self._process_assistant_entry(data)
            elif msg_type == "summary":
                self._process_summary_entry(data)

        except Exception as e:
            self.log(f"[ERROR] Error processing Claude log entry: {e}")

    def _process_user_entry(self, data: Dict[str, Any]) -> None:
        """Process a user message entry."""
        # Skip meta messages
        if data.get("isMeta", False):
            return

        message = data.get("message", {})
        content = message.get("content", "")

        # Handle both string content and structured content blocks
        if isinstance(content, str) and content:
            now = time.time()
            if now < getattr(
                self.message_processor, "suppress_cli_user_echo_until", 0.0
            ):
                self.log(
                    f"[DEBUG] Suppressing CLI user echo during AskUserQuestion automation: {content[:80]!r}"
                )
                return

            # Skip empty command output
            if content.strip() == "<local-command-stdout></local-command-stdout>":
                return

            # `<command-name>/X</command-name>` covers two distinct shapes:
            #
            # 1. TUI built-in (`/model`, `/effort`, `/clear`, …) — has a
            #    `<command-args>` element. Only mutates terminal state; the
            #    user already saw the result locally, and the
            #    `<local-command-stdout>` confirmation (handled below)
            #    carries any visible side-effect text. Drop entirely.
            #
            # 2. Skill / project command (`/ideabrowser-daily-idea`,
            #    `.claude/commands/*.md`, …) — has `<command-message>` but
            #    NO `<command-args>`. The next user entry is the expanded
            #    skill body (list-content, intentionally not forwarded
            #    because it can be multi-KB). Forward the typed command
            #    name so the user's intent appears on mobile/web —
            #    otherwise the session looks empty until Claude reaches
            #    for a permission prompt the user has no context for.
            if "<command-name>" in content:
                if "<command-args>" in content:
                    return
                match = self._SKILL_COMMAND_NAME_RE.search(content)
                if match and self.message_queue is not None:
                    self.message_processor.process_user_message(
                        content=match.group(1),
                        from_web=False,
                        input_queue=self.message_queue,
                    )
                return

            # Non-empty stdout from a TUI slash command (e.g. "Set model to
            # Opus 4.8 (1M context)" or "Set effort level to high: …").
            # Visible to the user, but not a real chat message — route it
            # as AGENT so it doesn't trip session title generation or get
            # re-dispatched into Claude.
            if "<local-command-stdout>" in content:
                self.message_processor.send_cli_command_echo(content)
                return

            # Process user message (this will send to Vicoa if not from web)
            if self.message_queue is not None:
                self.message_processor.process_user_message(
                    content=content,
                    from_web=False,  # Message from CLI
                    input_queue=self.message_queue,
                )

        elif isinstance(content, list):
            # Handle structured content (e.g., tool results)
            formatted_parts = []
            for block in content:
                if isinstance(block, dict):
                    formatted_content = format_content_block(block)
                    if formatted_content:
                        formatted_parts.append(formatted_content)

    def _process_assistant_entry(self, data: Dict[str, Any]) -> None:
        """Process an assistant message entry."""
        message = data.get("message", {})
        # Authoritative model id — actual model the request was served by.
        # Patches on first read AND on every mid-session /model switch.
        model = message.get("model")
        if isinstance(model, str) and model:
            self._patch_session_config_fields({"model": model})
        content_blocks = message.get("content", [])
        formatted_parts = []
        tools_used = []
        ask_user_question_metadata: Optional[Dict[str, Any]] = None

        for block in content_blocks:
            if isinstance(block, dict):
                # AskUserQuestion is handled entirely by the terminal path.
                # Skip the block without adding it to tools_used — otherwise the
                # JSONL entry registers as a tool use and makes the wrapper's
                # fast-path prompt check busy-spin while the user is responding.
                if (
                    block.get("type") == "tool_use"
                    and block.get("name") == "AskUserQuestion"
                ):
                    continue

                ask_metadata = self._extract_ask_user_question_metadata(block)
                if ask_metadata:
                    ask_user_question_metadata = ask_metadata
                    continue

                formatted_content = format_content_block(block)
                if formatted_content:
                    formatted_parts.append(formatted_content)
                    # Track if this was a tool use
                    if block.get("type") == "tool_use":
                        tools_used.append(formatted_content)

        # When only an AskUserQuestion is present (no text blocks), derive the
        # message content from the first question text.  The app requires a
        # non-empty content field to render the message and for push
        # notifications; the structured form is driven by message_metadata.
        if ask_user_question_metadata and not formatted_parts:
            formatted_parts = ["🔧 Using tool: AskUserQuestion"]

        # Send one message combining regular content and/or AskUserQuestion metadata.
        # Using a single call avoids the race window that existed when they were
        # sent as two separate process_assistant_message calls.
        if formatted_parts or ask_user_question_metadata:
            message_content = "\n".join(formatted_parts)
            if ask_user_question_metadata:
                # If Claude is no longer idle the user already responded via the
                # terminal path — this JSONL entry is stale, skip it.
                if (
                    self.terminal_ask_dispatched_func
                    and self.terminal_ask_dispatched_func()
                ):
                    self.log(
                        "[DEBUG] Skipping JSONL AskUserQuestion: terminal path already dispatched it"
                    )
                    return
                self.log(
                    f"[INFO] Sending AskUserQuestion to Vicoa: {len(ask_user_question_metadata.get('questions', []))} question(s), content={message_content[:60]!r}"
                )

            queued_responses = self.message_processor.process_assistant_message(
                content=message_content,
                tools_used=tools_used,
                send_message_lock=self.send_message_lock,
                requested_input_messages=self.requested_input_messages,
                pending_permission_options=self.pending_permission_options,
                requires_user_input=ask_user_question_metadata is not None,
                message_metadata=(
                    {"ask_user_question": ask_user_question_metadata}
                    if ask_user_question_metadata
                    else None
                ),
            )

            if queued_responses and self.message_queue:
                for response in queued_responses:
                    self.message_queue.append(response)

    def _extract_ask_user_question_metadata(
        self, block: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Extract AskUserQuestion payload from a Claude tool_use block."""
        if block.get("type") != "tool_use":
            return None
        if block.get("name") != "AskUserQuestion":
            return None

        tool_input = block.get("input")
        if not isinstance(tool_input, dict):
            return None

        questions_raw = tool_input.get("questions")
        if not isinstance(questions_raw, list) or not questions_raw:
            return None

        parsed_questions: List[Dict[str, Any]] = []
        for index, item in enumerate(questions_raw):
            if not isinstance(item, dict):
                continue

            question_text = str(item.get("question") or "").strip()
            header = str(item.get("header") or f"Question {index + 1}").strip()
            options_raw = item.get("options")

            parsed_options: List[Dict[str, str]] = []
            if isinstance(options_raw, list):
                for option in options_raw:
                    if not isinstance(option, dict):
                        continue
                    label = str(option.get("label") or "").strip()
                    description = str(option.get("description") or "").strip()
                    if not label:
                        continue
                    parsed_options.append({"label": label, "description": description})

            if not question_text:
                continue

            parsed_questions.append(
                {
                    "question": question_text,
                    "header": header or f"Question {index + 1}",
                    "options": parsed_options,
                    "multi_select": bool(item.get("multiSelect", False)),
                }
            )

        if not parsed_questions:
            return None

        return {
            "tool_use_id": block.get("id"),
            "questions": parsed_questions,
        }

    def _process_summary_entry(self, data: Dict[str, Any]) -> None:
        """Process a summary entry (session started)."""
        pass

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False
