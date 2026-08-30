"""Messaging module for Claude Code Wrapper.

This module handles message processing, queueing, and deduplication
for bidirectional communication between Claude CLI and Vicoa servers.
"""

from .ask_question import AskQuestionCollector, build_ask_question_metadata
from .deduplicator import MessageDeduplicator
from .input_request_manager import InputRequestManager
from .processor import MessageProcessor
from .queue_manager import MessageQueue

__all__ = [
    "AskQuestionCollector",
    "build_ask_question_metadata",
    "MessageDeduplicator",
    "InputRequestManager",
    "MessageProcessor",
    "MessageQueue",
]
