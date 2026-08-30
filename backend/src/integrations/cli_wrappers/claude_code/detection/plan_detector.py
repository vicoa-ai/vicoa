"""Plan mode detector for Claude CLI.

This detector identifies when Claude enters plan mode and extracts the
plan content and available options.
"""

import re
from typing import Dict

from .base import BaseDetector, DetectionResult


class PlanDetector(BaseDetector):
    """Detects plan mode prompts in terminal output.

    Plan mode is triggered when Claude wants to present a plan for user approval.
    The UI shows:
    - "Ready to code?" marker
    - Plan content
    - "Would you like to proceed" question
    - Three hardcoded options (auto-accept, manual, keep planning)
    """

    # Markers that indicate plan mode
    START_MARKER = "Ready to code?"
    PROCEED_MARKER = "Would you like to proceed"
    KEEP_PLANNING_MARKER = "No, keep planning"

    # Hardcoded options for plan mode (these are always the same)
    OPTIONS = {
        "1": "1. Yes, and auto-accept edits",
        "2": "2. Yes, and manually approve edits",
        "3": "3. No, keep planning",
    }

    # Box drawing characters to clean
    BOX_PATTERN = re.compile(r"^[│\s]+")
    BOX_END_PATTERN = re.compile(r"[│\s]+$")
    BOX_BORDER_PATTERN = re.compile(r"^[╭─╮╰╯]+$")

    def detect(self, clean_buffer: str) -> bool:
        """Check if plan mode prompt is present in the buffer.

        Args:
            clean_buffer: Terminal buffer with ANSI codes removed

        Returns:
            True if plan mode detected, False otherwise
        """
        # Plan mode is detected by:
        # 1. "Would you like to proceed" question
        # 2. Either "auto-accept edits" OR "manually approve edits" in options
        # Note: We no longer require "No, keep planning" because ExitPlanMode
        # uses "Type here to tell Claude what to change" instead
        return self.PROCEED_MARKER in clean_buffer and (
            "auto-accept edits" in clean_buffer
            or "manually approve edits" in clean_buffer
        )

    def extract(self, clean_buffer: str) -> DetectionResult:
        """Extract plan content and options from the buffer.

        Args:
            clean_buffer: Terminal buffer with ANSI codes removed

        Returns:
            DetectionResult with plan data, or not_detected
        """
        if not self.detect(clean_buffer):
            return DetectionResult.not_detected()

        # Extract plan content if available
        plan_content = self._extract_plan_content(clean_buffer)

        # Extract question text
        question = self._extract_question(clean_buffer)

        # Extract options dynamically from the buffer
        options_dict = self._extract_options(clean_buffer)

        # Fallback to hardcoded options if extraction fails
        if not options_dict or len(options_dict) < 2:
            options_dict = self.OPTIONS

        options_list = list(options_dict.values())

        # Build options mapping (option text -> number)
        options_map = {}
        for option_num, option_text in options_dict.items():
            clean_text = option_text.strip()
            options_map[clean_text] = option_num
            if ". " in clean_text:
                _, stripped = clean_text.split(". ", 1)
                stripped = stripped.strip()
                if stripped:
                    options_map[stripped] = option_num

        # Build the result
        data = {
            "question": question,
            "options": options_list,
            "options_map": options_map,
            "plan_content": plan_content,
            "type": "plan_mode",
        }

        return DetectionResult.success(data)

    def _extract_plan_content(self, clean_buffer: str) -> str:
        """Extract the plan content from the buffer.

        Args:
            clean_buffer: Terminal buffer with ANSI codes removed

        Returns:
            Extracted plan content, or empty string if not found
        """
        # Look for "Ready to code?" marker
        plan_start = clean_buffer.rfind(self.START_MARKER)

        if plan_start == -1:
            # No "Ready to code?" found - might be scrolled off or very short plan
            return ""

        # Extract everything after "Ready to code?" up to the prompt
        plan_end = clean_buffer.find(self.PROCEED_MARKER, plan_start)

        if plan_end == -1:
            return ""

        # Extract the content between markers
        raw_plan = clean_buffer[plan_start + len(self.START_MARKER) : plan_end]

        # Clean up the plan content
        lines = []
        for line in raw_plan.split("\n"):
            # Remove box drawing characters
            cleaned = self.BOX_PATTERN.sub("", line)
            cleaned = self.BOX_END_PATTERN.sub("", cleaned)
            cleaned = cleaned.strip()

            # Skip empty lines and box borders
            if cleaned and not self.BOX_BORDER_PATTERN.match(cleaned):
                lines.append(cleaned)

        return "\n".join(lines).strip()

    def _extract_question(self, clean_buffer: str) -> str:
        """Extract the question text from the buffer.

        Args:
            clean_buffer: Terminal buffer with ANSI codes removed

        Returns:
            Extracted question text
        """
        # Look for the PROCEED_MARKER
        if self.PROCEED_MARKER in clean_buffer:
            # Find the marker position
            marker_pos = clean_buffer.find(self.PROCEED_MARKER)
            # Extract from marker to end of line
            remaining = clean_buffer[marker_pos:]
            # Get the first line containing the marker
            first_line = remaining.split("\n")[0]
            # Look for question mark
            if "?" in first_line:
                return first_line[: first_line.index("?") + 1].strip()
            return first_line.strip()

        return "Would you like to proceed with this plan?"

    def _extract_options(self, clean_buffer: str) -> Dict[str, str]:
        """Extract numbered options from the buffer.

        Args:
            clean_buffer: Terminal buffer with ANSI codes removed

        Returns:
            Dictionary mapping option numbers to option text
        """
        # Pattern to match numbered options (same as PermissionDetector)
        option_pattern = re.compile(r"^[^\d]*(\d+)[\.)]\s+(.+)")
        selection_marker_pattern = re.compile(
            r"^[\s\u200b\u200e\u200f\u2060]*(?:[❯>▶▸›»]+)\s*"
        )

        normalized_buffer = clean_buffer.replace("\r", "\n")
        lines = normalized_buffer.split("\n")
        options_dict = {}

        # Find the question line first
        question_idx = -1
        for i, line in enumerate(lines):
            if self.PROCEED_MARKER in line:
                question_idx = i
                break

        if question_idx == -1:
            return {}

        # Scan lines after the question (up to 15 lines)
        start_idx = question_idx + 1
        end_idx = min(len(lines), question_idx + 16)

        for i in range(start_idx, end_idx):
            line = lines[i]
            # Clean the line
            cleaned = line.strip()
            # Remove selection markers
            cleaned = selection_marker_pattern.sub("", cleaned)

            # Skip separator lines
            if not cleaned or self.BOX_BORDER_PATTERN.match(cleaned):
                continue

            # Try to match numbered option pattern
            match = option_pattern.match(cleaned)
            if match:
                option_num = match.group(1)
                option_text = match.group(2).strip()

                # Skip if this looks like metadata
                if option_text and not option_text[0].isdigit():
                    options_dict[option_num] = f"{option_num}. {option_text}"

        return options_dict

    def get_patterns(self) -> Dict[str, str]:
        """Get the patterns used by this detector.

        Returns:
            Dictionary of pattern names to descriptions
        """
        return {
            "start_marker": self.START_MARKER,
            "proceed_marker": self.PROCEED_MARKER,
            "keep_planning_marker": self.KEEP_PLANNING_MARKER,
            "options": str(self.OPTIONS),
        }
