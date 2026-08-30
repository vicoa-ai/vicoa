"""Detection module for Claude Code Wrapper.

This module contains detectors for various Claude CLI UI patterns including:
- Permission prompts
- Plan mode prompts
- AskUserQuestion prompts
- Control commands
"""

from .base import BaseDetector, DetectionResult
from .control_detector import ControlDetector
from .permission_detector import PermissionDetector
from .plan_detector import PlanDetector
from .question_detector import QuestionDetector

__all__ = [
    "BaseDetector",
    "DetectionResult",
    "ControlDetector",
    "PermissionDetector",
    "PlanDetector",
    "QuestionDetector",
]
