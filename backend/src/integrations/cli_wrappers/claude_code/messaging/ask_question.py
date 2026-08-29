"""AskUserQuestion tab collection, metadata formatting, and dispatch."""

import select
import time
import uuid
from typing import Callable, Optional

from ..terminal.terminal_parser import TerminalRenderer


class AskQuestionCollector:
    """Navigates AskUserQuestion tabs in the PTY, collects tab data, and dispatches to Vicoa."""

    def __init__(
        self,
        pty_manager,
        terminal_buffer,
        ansi_cleaner,
        read_pty_func: Callable[[], Optional[str]],
        log_func: Callable[[str], None],
        session_state,
        message_processor,
        message_queue,
        send_message_lock,
        requested_input_messages: set,
        normalize_options_map_func: Callable,
    ):
        self._pty = pty_manager
        self._buffer = terminal_buffer
        self._ansi_cleaner = ansi_cleaner
        self._read_pty = read_pty_func
        self._log = log_func
        self._session_state = session_state
        self._message_processor = message_processor
        self._message_queue = message_queue
        self._send_message_lock = send_message_lock
        self._requested_input_messages = requested_input_messages
        self._normalize_options_map = normalize_options_map_func

        # Suppress re-detection while a Vicoa response is pending.
        # Readable by the wrapper's _check_for_prompts.
        self.suppress_until: float = 0.0

    def handle(self, data: dict) -> None:
        """Dispatch an AskUserQuestion prompt to Vicoa."""
        all_tabs = data.get("_all_tabs", [data])
        ask_metadata = build_ask_question_metadata(all_tabs)
        message_content = "🔧 Using tool: AskUserQuestion"
        first_tab = all_tabs[0] if all_tabs else data
        options = first_tab.get("options", [])
        options_map = self._normalize_options_map(
            first_tab.get("options_map") or {}, options
        )
        self.suppress_until = time.time() + 120.0

        # NOTE: requires_user_input=False is intentional. The sync SDK's
        # send_message(requires_user_input=True) blocks the caller polling
        # for the user's response (up to timeout_minutes, default 1440 min).
        # We run on the main event loop thread, so blocking here freezes
        # stdin/PTY processing — the "TUI hang". The idle monitor in
        # InputRequestManager separately PATCHes the message to
        # request-input, which sets AWAITING_INPUT and fires notifications.
        #
        # process_assistant_message internally clears pending_permission_options,
        # so we set the AUQ options AFTER this call. Otherwise the user's later
        # UI response can't be mapped to an option number.
        queued_responses = self._message_processor.process_assistant_message(
            content=message_content,
            tools_used=[],
            send_message_lock=self._send_message_lock,
            requested_input_messages=self._requested_input_messages,
            pending_permission_options=self._session_state.pending_permission_options,
            requires_user_input=False,
            message_metadata={"ask_user_question": ask_metadata},
        )

        if options_map:
            self._session_state.set_pending_permission_options(options_map)

        # Do NOT append queued_responses to message_queue here. Anything the
        # server returns at this point is pre-AUQ context — typically the
        # SSE-echo of the TUI message that triggered Claude to call
        # AskUserQuestion. Typing those into the PTY now would be received by
        # Claude CLI's AUQ widget as keystrokes, and the trailing Enter would
        # confirm the highlighted (first) option, auto-resolving the question
        # without user input. The user's actual AUQ reply will arrive later
        # via the SSE listener.
        if queued_responses:
            previews = [str(r)[:60] for r in queued_responses[:3]]
            self._log(
                f"[DEBUG] AskUserQuestion dispatch dropped "
                f"{len(queued_responses)} queued message(s) to avoid "
                f"auto-resolving the question: {previews!r}"
            )

    def collect_all_tabs(self, detector, first_result) -> list:
        """Navigate through all AskUserQuestion tabs and return each tab's data."""
        nav_tabs = first_result.data.get("nav_tabs", [])
        remaining = len(nav_tabs) - 1
        if remaining <= 0:
            return [first_result.data]

        all_data = [first_result.data]

        for tab_idx in range(remaining):
            self._pty.write_to_pty(b"\x1b[C")

            last_output = time.time()
            got_output = False
            deadline = time.time() + 2.0
            while time.time() < deadline:
                rlist, _, _ = select.select([self._pty.master_fd], [], [], 0.05)
                if rlist:
                    text = self._read_pty()
                    if text:
                        got_output = True
                        last_output = time.time()
                elif got_output and time.time() - last_output > 0.4:
                    break

            while self._read_pty():
                pass

            raw = self._buffer.get_last_n_chars(10000)
            try:
                clean = TerminalRenderer().render(raw)
            except Exception:
                clean = self._ansi_cleaner.clean_all(raw)

            result = detector.detect_and_extract(clean)
            if result.detected and result.data:
                all_data.append(result.data)
            else:
                self._log(
                    f"[WARNING] No question detected on tab {tab_idx + 2} of {len(nav_tabs)}"
                )

        # Navigate back to the first tab
        for _ in range(remaining):
            self._pty.write_to_pty(b"\x1b[D")
            time.sleep(0.1)

        deadline = time.time() + 1.0
        while time.time() < deadline:
            rlist, _, _ = select.select([self._pty.master_fd], [], [], 0.05)
            if rlist:
                self._read_pty()
            else:
                break

        return all_data


def build_ask_question_metadata(all_tabs: list) -> dict:
    """Convert per-tab QuestionDetector results to JSONL AskUserQuestion metadata."""
    nav_tabs = all_tabs[0].get("nav_tabs", []) if all_tabs else []
    parsed_questions = []

    for idx, data in enumerate(all_tabs):
        options_map = data.get("options_map") or {}
        multi_select = data.get("multi_select", False)
        header = nav_tabs[idx] if idx < len(nav_tabs) else f"Question {idx + 1}"

        parsed_options = []
        for key in sorted(
            options_map.keys(), key=lambda k: int(k) if k.isdigit() else 0
        ):
            option_str = options_map[key]
            dot_idx = option_str.find(". ")
            without_num = (
                option_str[dot_idx + 2 :]
                if dot_idx != -1 and option_str[:dot_idx].isdigit()
                else option_str
            )
            parts = without_num.split(" - ", 1)
            label = parts[0].strip().rstrip(".")
            description = parts[1].strip() if len(parts) > 1 else ""
            if label.lower() in ("type something", "chat about this"):
                continue
            parsed_options.append({"label": label, "description": description})

        parsed_questions.append(
            {
                "question": data.get("question", ""),
                "header": header,
                "options": parsed_options,
                "multi_select": multi_select,
            }
        )

    return {
        "tool_use_id": str(uuid.uuid4()),
        "questions": parsed_questions,
    }
