"""Base detector interface for Claude CLI output detection.

This module provides the abstract base class that all detectors inherit from.
Each detector is responsible for identifying specific patterns in terminal output
and extracting structured data.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class DetectionResult:
    """Result of a detection operation.

    Attributes:
        detected: Whether the pattern was detected
        data: Extracted structured data (optional)
    """

    detected: bool
    data: Optional[dict] = None

    @classmethod
    def not_detected(cls) -> "DetectionResult":
        """Create a result indicating pattern was not detected."""
        return cls(detected=False, data=None)

    @classmethod
    def success(cls, data: dict) -> "DetectionResult":
        """Create a successful detection result with data."""
        return cls(detected=True, data=data)


class BaseDetector(ABC):
    """Abstract base class for terminal output detectors.

    Each detector is responsible for:
    1. Detecting specific patterns in terminal output
    2. Extracting structured data from those patterns
    3. Providing pattern information for documentation/debugging

    Subclasses should:
    - Define pattern constants as class variables
    - Implement detect() to check if pattern is present
    - Implement extract() to parse structured data
    - Optionally override get_patterns() to expose pattern info
    """

    @abstractmethod
    def detect(self, clean_buffer: str) -> bool:
        """Check if the pattern is present in the terminal buffer.

        Args:
            clean_buffer: Terminal buffer with ANSI codes removed

        Returns:
            True if pattern is detected, False otherwise
        """
        pass

    @abstractmethod
    def extract(self, clean_buffer: str) -> DetectionResult:
        """Extract structured data from the terminal buffer.

        This method should only be called if detect() returns True.

        Args:
            clean_buffer: Terminal buffer with ANSI codes removed

        Returns:
            DetectionResult with extracted data or not_detected
        """
        pass

    def detect_and_extract(self, clean_buffer: str) -> DetectionResult:
        """Convenience method to detect and extract in one call.

        Args:
            clean_buffer: Terminal buffer with ANSI codes removed

        Returns:
            DetectionResult with extracted data or not_detected
        """
        if not self.detect(clean_buffer):
            return DetectionResult.not_detected()

        return self.extract(clean_buffer)

    def get_patterns(self) -> Dict[str, str]:
        """Get the patterns used by this detector.

        This is useful for debugging and documentation. Subclasses can
        override this to expose their pattern constants.

        Returns:
            Dictionary mapping pattern names to pattern strings/descriptions
        """
        return {}

    def get_description(self) -> str:
        """Get a human-readable description of what this detector detects.

        Returns:
            Description string
        """
        return self.__class__.__doc__ or "No description available"
