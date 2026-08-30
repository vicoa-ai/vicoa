"""Vicoa - Agent Dashboard and Python SDK

This package provides:
1. MCP Server for agent communication (vicoa CLI command)
2. Python SDK for interacting with the Vicoa API
"""

# Import SDK components for easy access
from .sdk.client import VicoaClient
from .sdk.async_client import AsyncVicoaClient
from .sdk.exceptions import (
    VicoaError,
    AuthenticationError,
    TimeoutError,
    APIError,
)

try:
    from importlib.metadata import version

    __version__ = version("vicoa")
except Exception:
    __version__ = "unknown"
__all__ = [
    "VicoaClient",
    "AsyncVicoaClient",
    "VicoaError",
    "AuthenticationError",
    "TimeoutError",
    "APIError",
]
