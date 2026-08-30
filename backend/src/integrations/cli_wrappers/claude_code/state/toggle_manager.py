"""Toggle management for Claude CLI settings.

This module manages toggle settings like permission mode and thinking mode,
handling cycling between values and syncing state with Claude CLI.
"""

import re
import time
from typing import Callable, Dict, Optional

from ..config import (
    ToggleConfig,
    create_default_toggles,
    PERMISSION_MODE_PATTERN,
    THINKING_TOGGLE_PATTERN,
)


class ToggleManager:
    """Manages toggle settings for Claude CLI.

    Handles:
    - Permission mode toggling (default, acceptEdits, plan, bypassPermissions, auto, ...)
    - Thinking toggle (on, off)
    - State synchronization with Claude CLI
    - Normalization of user input values
    """

    def __init__(
        self,
        initial_permission_mode: Optional[str] = None,
        write_to_pty_func: Optional[Callable[[bytes], None]] = None,
        read_pty_func: Optional[Callable[[], Optional[str]]] = None,
        log_func: Optional[Callable[[str], None]] = None,
    ):
        """Initialize toggle manager.

        Args:
            initial_permission_mode: Initial permission mode to set
            write_to_pty_func: Function to write bytes to PTY
            read_pty_func: Function that reads pending PTY output and returns it as a
                string (or None).  Used by set_toggle to observe the mode after each
                key press rather than relying on a pre-calculated step count.
            log_func: Logging function
        """
        self._toggles: Dict[str, ToggleConfig] = create_default_toggles()
        self.write_to_pty = write_to_pty_func or (lambda data: None)
        self.read_pty = read_pty_func
        self.log = log_func or (lambda msg: None)

        # Set initial permission mode if provided
        if initial_permission_mode:
            normalized = self.normalize_value(
                "permission_mode", initial_permission_mode
            )
            if normalized:
                self._toggles["permission_mode"].current_slug = normalized

        # Control detection buffer (shared for parsing toggle state from terminal)
        self.control_detection_buffer = ""

    def set_toggle(self, setting: str, target_slug: str) -> bool:
        """Cycle toggle until the detected mode matches the target.

        When a read_pty_func is available we use a send-one-observe loop: press
        the key once, wait briefly, read the terminal output, check whether the
        displayed mode matches the target, and repeat until it does (up to a
        safety cap).  This works regardless of how many modes exist in the cycle
        or what order Claude CLI cycles through them.

        When no read_pty_func is available we fall back to the legacy approach of
        calculating steps from the stored cycle and sending them all at once.

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
        key_sequence = toggle.key_sequence

        # Already there?
        if toggle.current_slug == target_slug:
            return True

        # --- Send-one-observe loop (preferred) ---
        if self.read_pty is not None:
            # Safety cap: never press more than the known cycle length + a few
            # extra in case new modes have been inserted since startup.
            max_presses = max(len(toggle.cycle) + 4, 10)
            self.log(
                f"[INFO] Cycling {setting} toward '{target_slug}' (observe mode, cap={max_presses})"
            )
            for attempt in range(max_presses):
                self.write_to_pty(key_sequence)
                # Give Claude CLI time to redraw the status line.
                time.sleep(0.15)

                raw = self.read_pty()
                if raw:
                    # Parse the terminal output to update current_slug only —
                    # do NOT call update_from_terminal here because that would
                    # clear pending_target and emit a feedback message, causing
                    # a duplicate when the wrapper's terminal monitor loop later
                    # processes the same output.
                    detected_slug = self._parse_slug_from_output(setting, raw)
                    if detected_slug:
                        toggle.current_slug = detected_slug

                detected = toggle.current_slug
                self.log(
                    f"[DEBUG] set_toggle attempt {attempt + 1}: detected='{detected}' target='{target_slug}'"
                )
                if detected == target_slug:
                    self.log(
                        f"[INFO] Set {setting} to {self.humanize_value(setting, target_slug)}"
                    )
                    return True

                # Auto mode shows a confirmation overlay ("Enable auto mode?") that
                # blocks Shift+Tab. Only send Escape if the overlay is actually visible.
                if attempt == 5 and detected == "auto":
                    self.log(
                        f"[INFO] set_toggle: auto overlay detected at attempt {attempt + 1}; sending Escape"
                    )
                    self.write_to_pty(b"\x1b")
                    time.sleep(0.15)
                    raw = self.read_pty()
                    if raw:
                        detected_slug = self._parse_slug_from_output(setting, raw)
                        if detected_slug:
                            toggle.current_slug = detected_slug

            self.log(
                f"[WARNING] set_toggle: reached cap ({max_presses}) without matching '{target_slug}'; "
                f"last detected='{toggle.current_slug}'"
            )
            # Optimistically accept whatever we landed on — better than lying.
            return False

        # --- Legacy fallback: pre-calculate steps from stored cycle ---
        cycle = toggle.cycle
        current_slug = toggle.current_slug or cycle[0]

        try:
            current_index = cycle.index(current_slug)
        except ValueError:
            self.log(
                f"[WARNING] Current {setting} '{current_slug}' not in cycle. Assuming first."
            )
            current_index = 0

        try:
            target_index = cycle.index(target_slug)
        except ValueError:
            self.log(f"[ERROR] Target {setting} '{target_slug}' not in cycle.")
            return False

        steps_needed = (target_index - current_index + len(cycle)) % len(cycle)
        self.log(
            f"[INFO] Sending {steps_needed} key presses to cycle {setting} "
            f"from '{current_slug}' to '{target_slug}' (legacy mode)"
        )

        for _ in range(steps_needed):
            self.write_to_pty(key_sequence)
            time.sleep(0.1)

        # Optimistically update state
        toggle.current_slug = target_slug
        toggle.last_display = self.humanize_value(setting, target_slug)
        self.log(f"[INFO] Set {setting} to {toggle.last_display}")
        return True

    def normalize_value(self, setting: str, value: Optional[str]) -> Optional[str]:
        """Normalize toggle value to canonical slug.

        Examples:
          - permission_mode: "auto accept" → "acceptEdits"
          - thinking: "enabled" → "on"

        Args:
            setting: Setting name
            value: Value to normalize

        Returns:
            Normalized slug, or None if invalid
        """
        if not value:
            return None

        if setting not in self._toggles:
            return None

        keywords = self._toggles[setting].keywords

        # Normalize input
        cleaned = value.lower().strip()
        cleaned = cleaned.replace("_", "-")
        collapsed = re.sub(r"[^a-z-]", "", cleaned)
        collapsed = collapsed.replace("-", "")

        # Check keywords
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

        # Fallback for thinking
        if setting == "thinking":
            if any(kw in collapsed for kw in ["on", "enabled", "active"]):
                return "on"
            if any(kw in collapsed for kw in ["off", "disabled", "inactive"]):
                return "off"

        return None

    def humanize_value(self, setting: str, slug: str) -> str:
        """Convert canonical slug to human-readable label.

        Args:
            setting: Setting name
            slug: Canonical slug

        Returns:
            Human-readable label
        """
        if setting not in self._toggles:
            return slug

        labels = self._toggles[setting].labels
        return labels.get(slug, slug)

    def get_current_value(self, setting: str) -> Optional[str]:
        """Get current value of a toggle setting.

        Args:
            setting: Setting name

        Returns:
            Current slug value, or None if unknown
        """
        if setting not in self._toggles:
            return None
        return self._toggles[setting].current_slug

    def get_pending_target(self, setting: str) -> Optional[str]:
        """Get pending target value for a toggle setting.

        Args:
            setting: Setting name

        Returns:
            Pending target slug, or None if no pending target
        """
        if setting not in self._toggles:
            return None
        return self._toggles[setting].pending_target

    def set_pending_target(self, setting: str, target: Optional[str]) -> None:
        """Set pending target value for a toggle setting.

        Args:
            setting: Setting name
            target: Target slug to set
        """
        if setting in self._toggles:
            self._toggles[setting].pending_target = target

    def ensure_mode_in_cycle(self, setting: str, mode: str) -> None:
        """Ensure a mode is in the cycle for a toggle.

        This is useful for adding modes like bypassPermissions that may
        not be in the default cycle.

        Args:
            setting: Setting name
            mode: Mode to ensure is in cycle
        """
        if setting not in self._toggles:
            return

        toggle = self._toggles[setting]
        if mode not in toggle.cycle:
            # Add to cycle
            if setting == "permission_mode" and mode == "bypassPermissions":
                self._toggles[setting].cycle = (mode, *toggle.cycle)
                self.log(f"[INFO] Added {mode} to start of {setting} cycle")
            else:
                self._toggles[setting].cycle = (*toggle.cycle, mode)
                self.log(f"[INFO] Added {mode} to {setting} cycle")

    def update_from_terminal(self, terminal_buffer: str) -> list[str]:
        """Update toggle state from terminal buffer.

        This parses the terminal output to detect the current state of toggles
        displayed by Claude CLI.

        Args:
            terminal_buffer: Terminal buffer to parse
        """
        if not terminal_buffer:
            return []

        self.control_detection_buffer += terminal_buffer.replace("\r", "\n")
        if len(self.control_detection_buffer) > 4000:
            self.control_detection_buffer = self.control_detection_buffer[-4000:]

        permission_entries: list[dict] = []

        # Default mode emits only "? for shortcuts" with no mode name before it,
        # so PERMISSION_MODE_PATTERN never matches it. Handle it explicitly first.
        shortcuts_only = re.search(
            r"\?\s+for\s+shortcuts", self.control_detection_buffer, re.IGNORECASE
        )
        if shortcuts_only:
            permission_entries.append(
                {"slug": "default", "end": shortcuts_only.end(), "is_shortcuts": True}
            )

        for match in PERMISSION_MODE_PATTERN.finditer(self.control_detection_buffer):
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

            slug = self.normalize_value("permission_mode", trimmed)
            if slug:
                permission_entries.append(
                    {
                        "slug": slug,
                        "end": match.end(),
                        "is_shortcuts": is_shortcuts_match,
                    }
                )

        # Fallback if the full "(shift+tab to cycle)" line isn't present
        if not permission_entries:
            fallback_pattern = re.compile(
                r"(default|plan|accept edits|bypass permissions)\s+mode\s+on",
                re.IGNORECASE,
            )
            for match in fallback_pattern.finditer(self.control_detection_buffer):
                raw_mode = match.group(1).strip()
                slug = self.normalize_value("permission_mode", raw_mode)
                if slug:
                    permission_entries.append(
                        {
                            "slug": slug,
                            "end": match.end(),
                            "is_shortcuts": False,
                        }
                    )

        # Bypass permissions is sticky once set — Claude's status line drops
        # both the "(shift+tab to cycle)" hint AND the "mode" word, showing
        # only "⏵⏵ bypass permissions on". Neither the primary pattern nor
        # the fallback above will match, so look for the bare "bypass" /
        # "bypass permissions" keyword and emit a bypassPermissions entry.
        if not permission_entries:
            bypass_match = re.search(
                r"bypass\s*permissions?",
                self.control_detection_buffer,
                re.IGNORECASE,
            )
            if bypass_match:
                permission_entries.append(
                    {
                        "slug": "bypassPermissions",
                        "end": bypass_match.end(),
                        "is_shortcuts": False,
                    }
                )

        thinking_entries: list[dict] = []
        for match in THINKING_TOGGLE_PATTERN.finditer(self.control_detection_buffer):
            state = match.group(1).lower()
            thinking_entries.append({"slug": state, "end": match.end()})

        max_consumed_upto = 0
        feedback_messages: list[str] = []

        if permission_entries:
            selected_entry: Optional[dict] = None
            pending_target = self.get_pending_target("permission_mode")

            if pending_target:
                for entry in reversed(permission_entries):
                    if entry["slug"] == pending_target:
                        selected_entry = entry
                        break

            if not selected_entry:
                non_shortcuts = [
                    e for e in permission_entries if not e.get("is_shortcuts")
                ]
                selected_entry = (
                    non_shortcuts[-1] if non_shortcuts else permission_entries[-1]
                )

            slug = selected_entry["slug"]
            consumed_upto = selected_entry["end"]
            if consumed_upto > max_consumed_upto:
                max_consumed_upto = consumed_upto

            message = self._update_toggle_state("permission_mode", slug)
            if message:
                feedback_messages.append(message)

        if thinking_entries:
            selected_thinking = thinking_entries[-1]
            slug = selected_thinking["slug"]
            consumed_upto = selected_thinking.get("end", 0)
            if consumed_upto > max_consumed_upto:
                max_consumed_upto = consumed_upto

            message = self._update_toggle_state("thinking", slug)
            if message:
                feedback_messages.append(message)

        if max_consumed_upto > 0:
            self.control_detection_buffer = self.control_detection_buffer[
                max_consumed_upto:
            ]

        return feedback_messages

    def _update_toggle_state(self, setting: str, slug: str) -> Optional[str]:
        """Update toggle state and return feedback message if needed."""
        if setting not in self._toggles:
            return None

        toggle = self._toggles[setting]
        current_slug = toggle.current_slug
        last_display = toggle.last_display
        pending_target = toggle.pending_target
        if current_slug == slug:
            if pending_target == slug:
                toggle.pending_target = None
                return self._format_toggle_feedback(setting, slug, "changed")
            return None

        is_initial_detection = last_display is None
        display_mode = self.humanize_value(setting, slug)

        toggle.current_slug = slug
        toggle.last_display = display_mode

        self.ensure_mode_in_cycle(setting, slug)

        should_notify = False
        if pending_target == slug:
            should_notify = True
            toggle.pending_target = None
        elif not is_initial_detection and not pending_target:
            should_notify = True
        elif (
            is_initial_detection
            and setting == "permission_mode"
            and slug == "bypassPermissions"
        ):
            should_notify = True
        if should_notify:
            return self._format_toggle_feedback(setting, slug, "changed")
        return None

    def _format_toggle_feedback(
        self, setting: str, slug: str, message_type: str = "changed"
    ) -> str:
        """Format feedback message for toggle state changes."""
        display_value = self.humanize_value(setting, slug)
        setting_name = setting.replace("_", " ").capitalize()

        if setting == "thinking":
            if message_type == "changed":
                return f"Thinking turned {slug}"
            if message_type == "already":
                return f"Thinking is already {slug}"
            return f"Unable to set thinking to {slug}"

        if message_type == "changed":
            return f"{setting_name} changed to {display_value}"
        if message_type == "already":
            return f"{setting_name} is already {display_value}"
        return f"Unable to set {setting.replace('_', ' ')} to {display_value}"

    def get_cycle(self, setting: str) -> tuple:
        """Get the cycle for a toggle setting.

        Args:
            setting: Setting name

        Returns:
            Tuple of cycle values
        """
        if setting not in self._toggles:
            return tuple()
        return self._toggles[setting].cycle

    def get_all_settings(self) -> list[str]:
        """Get list of all toggle setting names.

        Returns:
            List of setting names
        """
        return list(self._toggles.keys())

    def get_toggle_info(self, setting: str) -> Optional[dict]:
        """Get all information about a toggle setting.

        Args:
            setting: Setting name

        Returns:
            Dictionary with toggle information, or None if not found
        """
        if setting not in self._toggles:
            return None

        toggle = self._toggles[setting]
        return {
            "current_slug": toggle.current_slug,
            "last_display": toggle.last_display,
            "pending_target": toggle.pending_target,
            "cycle": toggle.cycle,
            "keywords": toggle.keywords,
            "labels": toggle.labels,
        }

    def _parse_slug_from_output(self, setting: str, raw: str) -> Optional[str]:
        """Extract the current slug for *setting* from raw terminal output.

        Used by set_toggle's observe loop to update current_slug without
        triggering feedback messages or clearing pending_target.

        """
        buf = raw.replace("\r", "\n")

        if setting == "permission_mode":
            for match in PERMISSION_MODE_PATTERN.finditer(buf):
                matched_text = match.group(0)
                if "? for shortcuts" in matched_text.lower():
                    raw_mode = "shortcuts"
                else:
                    raw_mode = match.group(1).strip()
                if not raw_mode:
                    continue
                normalized = raw_mode.replace("⏵⏵", "").replace("⏸", "").strip()
                normalized = re.sub(r"[\s─-╿■-◿]+", " ", normalized).strip()
                normalized = normalized.strip("- ")
                if not normalized:
                    continue
                has_on = normalized.lower().endswith(" on")
                trimmed = normalized[:-3].strip() if has_on else normalized
                if not trimmed:
                    continue
                slug = self.normalize_value("permission_mode", trimmed)
                if slug:
                    return slug

            # Fallback: "default mode on", "plan mode on", etc. without the cycle hint
            fallback = re.compile(
                r"(default|plan|accept edits|bypass permissions)\s+mode\s+on",
                re.IGNORECASE,
            )
            for match in fallback.finditer(buf):
                slug = self.normalize_value("permission_mode", match.group(1).strip())
                if slug:
                    return slug

            # Bypass permissions is sticky and displays without the cycle hint
            # or the "mode" word ("⏵⏵ bypass permissions on"), so neither the
            # primary pattern nor the fallback above catches it. Recognize the
            # bare keyword. Without this, set_toggle's send-one-observe loop
            # never confirms the bypass target and runs to its attempt cap.
            if re.search(r"bypass\s*permissions?", buf, re.IGNORECASE):
                return "bypassPermissions"

            # Last resort: bare "? for shortcuts" with no mode name means default mode.
            if re.search(r"\?\s+for\s+shortcuts", buf, re.IGNORECASE):
                return "default"

        if setting == "thinking":
            for match in THINKING_TOGGLE_PATTERN.finditer(buf):
                return match.group(1).lower()

        return None

    def handle_toggle_request(self, setting: str, value: str) -> bool:
        """Handle a toggle request from the web UI.

        Args:
            setting: Setting name (e.g., "permission_mode", "thinking")
            value: Value to set (will be normalized)

        Returns:
            True if successful, False otherwise
        """
        if setting not in self._toggles:
            self.log(f"[WARNING] Unknown setting '{setting}'")
            return False

        # Normalize the value
        target_slug = self.normalize_value(setting, value)
        if not target_slug:
            self.log(f"[WARNING] Invalid value '{value}' for {setting}")
            return False

        # Ensure target is in cycle (needed for modes like bypassPermissions)
        self.ensure_mode_in_cycle(setting, target_slug)

        # Check if already at target
        current_slug = self.get_current_value(setting)
        if current_slug == target_slug:
            self.log(f"[INFO] {setting} is already set to {target_slug}")
            return True

        # Set pending target BEFORE cycling keys
        self.set_pending_target(setting, target_slug)

        # Set the toggle (cycles keys, updates state optimistically)
        success = self.set_toggle(setting, target_slug)

        # Clear pending target on failure
        if not success:
            self.set_pending_target(setting, None)

        return success

    def __repr__(self) -> str:
        """Get debug representation of toggle manager.

        Returns:
            String representation
        """
        states = []
        for setting in self._toggles:
            current = self.get_current_value(setting)
            states.append(f"{setting}={current}")
        return f"ToggleManager({', '.join(states)})"
