"""Shared components for agent CLI wrappers.

This module provides reusable infrastructure for wrapping different AI coding agents
(Claude Code, OpenCode, Codex, etc.) with Vicoa integration.
"""

from integrations.headless.acp_client import ACPClient, ACPError, ACPResponse

from .async_lifecycle import close_async_on_loop

__all__ = ["ACPClient", "ACPError", "ACPResponse", "close_async_on_loop"]
