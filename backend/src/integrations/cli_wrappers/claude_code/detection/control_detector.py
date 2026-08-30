"""Control command detector for Claude CLI.

This detector identifies and parses control commands embedded in terminal output.
Control commands are JSON-formatted messages that Claude uses to communicate
state changes (like toggle settings).
"""

import json
import re
from typing import Dict

from .base import BaseDetector, DetectionResult


class ControlDetector(BaseDetector):
    """Detects control commands in terminal output.

    Control commands are JSON objects with a "type": "control" field.
    Example: {"type": "control", "action": "toggle", "setting": "thinking", "value": "on"}
    """

    # Pattern to detect control JSON in terminal output
    CONTROL_JSON_PATTERN = re.compile(r'\{[^}]*"type"\s*:\s*"control"[^}]*\}')

    def detect(self, clean_buffer: str) -> bool:
        """Check if a control command is present in the buffer.

        Args:
            clean_buffer: Terminal buffer with ANSI codes removed

        Returns:
            True if control command detected, False otherwise
        """
        return self.CONTROL_JSON_PATTERN.search(clean_buffer) is not None

    def extract(self, clean_buffer: str) -> DetectionResult:
        """Extract control command from the buffer.

        Args:
            clean_buffer: Terminal buffer with ANSI codes removed

        Returns:
            DetectionResult with control command data, or not_detected
        """
        match = self.CONTROL_JSON_PATTERN.search(clean_buffer)
        if not match:
            return DetectionResult.not_detected()

        json_str = match.group(0)

        try:
            control_data = json.loads(json_str)

            # Validate that it's actually a control command
            if control_data.get("type") != "control":
                return DetectionResult.not_detected()

            return DetectionResult.success(
                {
                    "control_command": control_data,
                    "raw_json": json_str,
                }
            )

        except json.JSONDecodeError:
            # Invalid JSON - not a valid control command
            return DetectionResult.not_detected()

    def extract_all(self, clean_buffer: str) -> list[dict]:
        """Extract all control commands from the buffer.

        Args:
            clean_buffer: Terminal buffer with ANSI codes removed

        Returns:
            List of control command dictionaries
        """
        matches = self.CONTROL_JSON_PATTERN.findall(clean_buffer)
        commands = []

        for json_str in matches:
            try:
                control_data = json.loads(json_str)
                if control_data.get("type") == "control":
                    commands.append(control_data)
            except json.JSONDecodeError:
                continue

        return commands

    def get_patterns(self) -> Dict[str, str]:
        """Get the patterns used by this detector.

        Returns:
            Dictionary of pattern names to pattern strings
        """
        return {
            "control_json_pattern": self.CONTROL_JSON_PATTERN.pattern,
        }
